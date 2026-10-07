"""Questions to a person (or the SAGA agent): closed answer schemas, each kind's check, the log.

A question kind is a catalog row: its actor and its answer shape, written in a small grammar::

    bool | int | str | slug | cui | period | sha256 | object
    enum(a|b|c)          one of the named values
    list[T]              a list of T
    {field: T, ...}      a closed record (unknown fields refused)
    T?                   optional: absent or null

``answer_question`` checks who answers (a person's question is never answered by an agent, nor
the SAGA agent's by a person), validates the answer against the shape (P10), runs the kind's
check against the question it answers, and appends the outcome to the client's answer log (P12):
``accepted``, or ``asked_again`` with the reason — the same question is asked again with an
``error`` field, and the node that asked it never moves on a refused answer.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from kit.catalog import Catalog
from kit.sorting import Pack, SplitError, split
from kit.store import Dossier
from kit.types import cui_is_valid, is_period

_ATOMS = {
    "bool": lambda v: isinstance(v, bool),
    "int": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "str": lambda v: isinstance(v, str) and v.strip() != "",
    "slug": lambda v: isinstance(v, str) and re.fullmatch(r"[a-z][a-z0-9_]*", v) is not None,
    "cui": lambda v: isinstance(v, str) and cui_is_valid(v),
    "period": lambda v: isinstance(v, str) and is_period(v),
    "sha256": lambda v: isinstance(v, str) and re.fullmatch(r"[0-9a-f]{64}", v) is not None,
    "object": lambda v: isinstance(v, dict),
}


class AnswerError(ValueError):
    """The answer is refused before it is an answer (wrong actor); nothing is recorded."""


# ----- the type grammar -----


@dataclass(frozen=True)
class T:
    kind: str  # an atom, "enum", "list" or "record"
    optional: bool = False
    values: tuple[str, ...] = ()
    item: T | None = None
    fields: tuple[tuple[str, T], ...] = ()


def parse_type(expr: str) -> T:
    t, rest = _parse(expr.strip())
    if rest.strip():
        raise ValueError(f"unknown type {expr!r}: trailing {rest!r}")
    return t


def _parse(s: str) -> tuple[T, str]:
    s = s.lstrip()
    if s.startswith("{"):
        fields, s = [], s[1:]
        while True:
            s = s.lstrip()
            if s.startswith("}"):
                s = s[1:]
                break
            m = re.match(r"([a-z][a-z0-9_]*)\s*:", s)
            if not m:
                raise ValueError(f"unknown type: bad record near {s[:20]!r}")
            ft, s = _parse(s[m.end() :])
            fields.append((m.group(1), ft))
            s = s.lstrip()
            if s.startswith(","):
                s = s[1:]
        t = T("record", fields=tuple(fields))
    elif s.startswith("list["):
        item, s = _parse(s[5:])
        s = s.lstrip()
        if not s.startswith("]"):
            raise ValueError("unknown type: list[ without ]")
        t, s = T("list", item=item), s[1:]
    elif s.startswith("enum("):
        end = s.index(")")
        t, s = T("enum", values=tuple(v.strip() for v in s[5:end].split("|"))), s[end + 1 :]
    else:
        m = re.match(r"[a-z0-9]+", s)
        if not m or m.group(0) not in _ATOMS:
            raise ValueError(f"unknown type {s[:20]!r}")
        t, s = T(m.group(0)), s[m.end() :]
    if s.startswith("?"):
        t, s = T(t.kind, True, t.values, t.item, t.fields), s[1:]
    return t, s


def validate(value: Any, expr: str | T, path: str = "") -> list[str]:
    """Every way ``value`` misses the shape; empty when it fits."""
    t = parse_type(expr) if isinstance(expr, str) else expr
    where = path or "answer"
    if value is None:
        return [] if t.optional else [f"{where}: required"]
    if t.kind == "enum":
        return [] if value in t.values else [f"{where}: one of {list(t.values)}"]
    if t.kind == "list":
        if not isinstance(value, list):
            return [f"{where}: a list"]
        return [e for i, v in enumerate(value) for e in validate(v, t.item, f"{where}.{i}")]
    if t.kind == "record":
        return _record(value, dict(t.fields), path)
    return [] if _ATOMS[t.kind](value) else [f"{where}: not a {t.kind}"]


def _record(value: Any, fields: dict[str, T], path: str) -> list[str]:
    where = path or "answer"
    if not isinstance(value, dict):
        return [f"{where}: a record"]
    errors = [
        f"{where}.{k}: unknown field" if path else f"{k}: unknown field"
        for k in value
        if k not in fields
    ]
    for name, ft in fields.items():
        sub = f"{path}.{name}" if path else name
        errors += validate(value.get(name), ft, sub)
    return errors


def question_hash(question: dict) -> str:
    body = {k: v for k, v in question.items() if k != "error"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()


# ----- each kind's check: (catalog, question, answer) -> reason or None -----


def _bon(cat, q, a):
    return None if a["cu_cui"] != a["fara_cui"] else "choose exactly one of cu_cui and fara_cui"


def _define_class(cat, q, a):
    sid = a["source_doc_id"]
    if sid == "unknown" or sid not in cat.ids("SourceDoc"):
        return f"{sid} is not a known source document"
    return None


def _define_articol(cat, q, a):
    aid, candidates = a["articol_id"], q.get("candidates") or []
    if candidates:
        return None if aid in candidates else f"{aid} is not among {candidates}"
    if aid in cat.ids("Articol") and cat.get("Articol", aid).procedure == "document":
        return None
    return f"{aid} is not an articol on the document path"


def _approve(cat, q, a):
    edit = a.get("edit")
    if a["decision"] == "edit":
        return None if edit else "edit carries the patch"
    return "approve and reject carry no edit" if edit else None


def _validare(cat, q, a):
    key = a.get("saga_doc_key")
    if not a["validated"]:
        return "not validated: no saga_doc_key" if key else None
    if not key:
        return "validated: name the saga_doc_key"
    if key not in (q.get("validated_keys") or []):
        return f"SAGA's snapshot does not show {key} validated"
    return None


def _need_export(cat, q, a):
    months = (q.get("exports") or {}).get(a["export_id"])
    if months is None:
        return f"{a['export_id']} is not an uploaded export of the books"
    return (
        None
        if set(months) & set(q.get("months") or [])
        else f"it covers {months}, none of {q.get('months')}"
    )


def _ambiguous(cat, q, a):
    ids, shown = a.get("sink_line_ids") or [], len(q.get("sink_lines") or [])
    if a["action"] == "already_posted":
        if not ids:
            return "already_posted names the sink line(s) it is posted as"
        if any(i < 0 or i >= shown for i in ids):
            return f"sink_line_ids are among 0..{shown - 1}"
        return None
    return "override_absent names no sink line" if ids else None


def _how(cat, q, a):
    return None if a["ack_mismatch"] != a["open_storno"] else "choose ack_mismatch or open_storno"


def _v2(cat, q, a):
    if a["action"] == "file" and q.get("material", True):
        return (
            "cannot file: the month is material (" + "; ".join((q.get("blockers") or [])[:3]) + ")"
        )
    rule = a.get("explained_rule")
    if rule and rule not in (q.get("rules") or []):
        return f"{rule} is not an active explained rule of this client"
    return None


def _v4(cat, q, a):
    if a["accept"] == a["skip"]:
        return "choose accept or skip"
    if a["skip"] and (a.get("edit") or a.get("seed_next") is not None):
        return "skip writes nothing: leave edit and seed_next empty"
    return None


def _rule(cat, q, a):
    rules = q.get("rules")
    return (
        None if rules is None or a["rule_id"] in rules else f"{a['rule_id']} is not a drafted rule"
    )


def _disposition(cat, q, a):
    if a["control_id"] not in (q.get("controls") or []):
        return f"{a['control_id']} is not a failed control of this month"
    if (a["disposition"] == "explained_rule") != bool(a.get("rule_id")):
        return "rule_id is given exactly when the disposition is explained_rule"
    return None


def _receipt(cat, q, a):
    if a["filing_id"] != q.get("filing_id") or a["period"] != q.get("period"):
        return f"this question is about {q.get('filing_id')} for {q.get('period')}"
    return None


def _split(cat, q, a):
    try:
        split(cat, Pack.model_validate(q.get("pack") or {}), a)
    except (SplitError, ValueError) as exc:
        return str(exc)
    return None


CHECKS: dict[str, Callable[[Catalog, dict, dict], str | None]] = {
    "bon_cui_unclear": _bon,
    "define_class": _define_class,
    "define_articol": _define_articol,
    "v3_approve": _approve,
    "wait_validare": _validare,
    "need_rj_export": _need_export,
    "recon_ambiguous": _ambiguous,
    "recon_how_mismatch": _how,
    "v2_close": _v2,
    "v4_codit": _v4,
    "explained_rule": _rule,
    "control_disposition": _disposition,
    "filing_receipt": _receipt,
    "decont_split": _split,
}


# ----- answering -----


@dataclass(frozen=True)
class Outcome:
    status: Literal["accepted", "asked_again"]
    error: str | None
    question_hash: str
    question: dict  # the question as asked next: with ``error`` when asked again


def answer_question(
    cat: Catalog,
    dossier: Dossier,
    issue: str,
    kind: str,
    question: dict,
    answer: Any,
    operator: str,
    actor: Literal["person", "saga_agent"],
) -> Outcome:
    row = cat.get("QuestionKind", kind)  # an unknown kind is an error (P10)
    if row.actor == "accountant" and actor != "person":
        raise AnswerError(f"{kind} is a question for a person; an agent never answers it")
    if row.actor == "saga_agent" and actor != "saga_agent":
        raise AnswerError(f"{kind} is a question for the SAGA agent")
    qhash = question_hash(question)
    errors = _record(answer, {f: parse_type(e) for f, e in row.answer.items()}, "")
    error = "; ".join(errors) if errors else None
    if error is None and kind in CHECKS:
        error = CHECKS[kind](cat, question, answer)
    proposed = question.get("proposed")
    if error is not None:
        dossier.record_answer(issue, kind, qhash, answer, proposed, "asked_again", operator)
        return Outcome("asked_again", error, qhash, {**question, "error": error})
    dossier.record_answer(issue, kind, qhash, answer, proposed, "accepted", operator)
    return Outcome("accepted", None, qhash, question)
