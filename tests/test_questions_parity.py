"""WP-20, the ``questions.py`` step: the kit's questions (kinds, answer shapes, each kind's check,
the question's key, the answer log) against the core's, before any replacement.

**What the core has.** The core re-exports no questions module: ``CORE_MODULES`` has no
``core.questions`` and no ``core.hitl``. What it does carry for a question to a person is

- data, in ``core.catalog``: the ``ArticoleHITL`` rows (``Catalog.hitl``: each kind's actor, the
  graphs that ask it and its ``resume_schema``), read with ``hitl_kind`` (``UnknownHitlKind``);
- code, in ``core.rules``: the answer models and checks of two kinds, ``ExplainedRuleResume`` /
  ``check_explained_rule`` and ``ControlDispositionResume`` / ``check_control_disposition``;
- code, in ``core.codit``: what a ``v4_codit`` answer may patch and seed (``v4_rules``,
  ``v4_patch``, ``v4_seed``).

Everything else lives outside the core, in the runtime the pin does not share: ``hitl.ask`` (the
interrupt that asks and asks again), ``answers`` (the question's hash and the answer log), the
answer models of twelve kinds (``reconcile``, ``ingest``, ``close``, ``triage``) and their checks,
which are closures inside graph nodes; ``filing_receipt`` is an upload (``operator_api``), with no
answer model. Those are compared below as the core's namesakes outside the core, labelled so,
the way the ``period.py`` step compared ``close_kind``. Replacement is not possible until the core
exports a questions module (``answer_question`` / ``check_record`` / ``parse_type`` /
``question_hash`` or equivalents); until then this step's comparison is of pieces, not of a module.

**The corpus** is invented here, since neither side generates questions: for each of the fifteen
kinds both catalogs name but ``filing_receipt`` (no answer model in the core: gap
``answer_models``), one answer both sides accept, and from it every answer that sets one field (or
one field of a ``decont_split`` part) to each value of a fixed pool (the atoms of both grammars at
their edges, both sides' enum options, null) or leaves it out, adds an unknown field, or is not a
record: 1021 answers (``_res_cases``). For the two kinds the core checks in ``core.rules``, a grid
of 174 questions × answers (``_check_cases``). For the key, the 24 questions the corpus asks, in
the shapes the kit's callers pass.

Compared: which kinds each catalog asks, by which actor and where (the kit's ``procedure`` against
the core's ``graph_ids``); each kind's answer fields, in order, their types and their options (the
catalog rows are data on both sides, rendered in one grammar); whether each answer's shape is
accepted (the kit's ``check_record`` on its row, the core's answer model); the two in-core checks
(accepted or asked again; the reason is prose and is not compared); the question's hash; the
answer log's outcomes; what a ``v4_codit`` answer may edit and seed. Not compared: the reasons'
wording (prose on both sides), the Paperclip card (the kit's only), and the checks the core keeps
outside the core (closures in graph nodes, and ``triage.check_split``), so none of the kit's checks
that stand against them is compared: ``_v2``'s material-month refusal, ``_ambiguous``,
``_need_export``, ``_validare``, ``_v4``'s accept / skip, and ``_split`` against ``check_split``.

**What agrees.** Overall: the actor of all 15 shared kinds; where 14 are asked; 25 of 29 answer
field positions (name, type and options); 4 of 5 enum fields' options, in order; 931 of 1021
answer shapes (119 accepted on both, 812 refused on both); 162 of 174 check cases (18 accepted on
both, 144 asked again on both); the question's hash on all 24 questions given the
same dict, with the ``error`` dropped on both.

**Live paths.** The kit's live callers ask thirteen kinds: the router's asks (``kit/route.py``),
Sorting's questions (``kit/sorting.py`` and the catalog's split question), answered through
``answer_question`` by ``kit/dispatch.py`` and ``kit/scenario.py``; ``kit/cards.py`` turns any
card into an answer, so on those kinds any answer is live. Of the compared answers, the twelve
live kinds' (``filing_receipt`` is live but not compared) agree on 825 of 885 (103 accepted, 722
refused). ``explained_rule`` and ``control_disposition`` have no asker: no route, question or step
of the kit asks them (``kit/cards.py`` would render them; ``kit answer --kind`` can answer them
through the CLI, while ``APPLY`` has no entry for either), and they are the only two kinds whose
core check is in the core: so no in-core check comparison is on a live path, and their answer
shapes are compared off the live paths.

**Vacuity.** No agreement is one-sided: every compared kind has an answer both accept and one both
refuse; each in-core check has a case both accept and one both ask again; the actors include the
SAGA agent's. The hash's agreement is probed with two questions that differ in one value.

**What it does not prove**, because the corpus never exercises it: the checks the core keeps
outside the core (``v3_approve``, ``wait_validare``, ``need_rj_export``, ``recon_ambiguous``,
``v2_close``, ``v4_codit``'s accept / skip pairing, ``decont_split``'s ``check_split``), questions
asked through a running graph (``hitl.ask``) or a Paperclip card, the actor gate (the kit refuses
a wrong actor; the core's catalog names the actor as data and no core code takes one), the twelve
kinds only the core's catalog has, ``decont_split``'s parts against a container's
``split.children`` (the core's grammar names it; neither shape check reads it), the answer log's
rows (who, when, what was proposed), nor which side's shapes are right, which the owner and the
catalog decide.

While any gap stands the kit keeps ``kit/questions.py``; the owner frames the decision (BUILD
WP-20)."""

from __future__ import annotations

import ast
import hashlib
import re
from collections import Counter
from functools import cache
from pathlib import Path

import pytest
from poarta_contabila import core
from poarta_contabila.answers import Outcome as CoreOutcome
from poarta_contabila.answers import question_hash as core_question_hash
from poarta_contabila.close import V2CloseResume, V4CoditResume
from poarta_contabila.ingest import DefineArticolResume, V3ApproveResume, WaitValidareResume
from poarta_contabila.reconcile import (
    AmbiguousResume,
    ContestResume,
    HowMismatchResume,
    NeedExportResume,
)
from poarta_contabila.rules import InMemoryRuleStore, RuleBody
from poarta_contabila.triage import BonCuiResume, DecontSplitResume, DefineClassResume
from pydantic import ValidationError
from test_calendar import _pinned_checkout

from kit import questions as kq
from kit import steps as ks
from kit.catalog import load_catalog
from kit.types import cui_is_valid

ROOT = Path(__file__).resolve().parents[1]
CUI = "41526372"  # invented; passes the check digit
SHA = hashlib.sha256(b"part").hexdigest()

# The kit's procedure → the core's graph.
GRAPH = {
    "sorting": "folder_triage",
    "document": "ingest_source_doc",
    "reconcile": "reconcile_sink",
    "close": "monthly_close",
}

# Each kind's answer model on the core's side, and where it lives.
MODELS = {
    "define_class": DefineClassResume,
    "bon_cui_unclear": BonCuiResume,
    "decont_split": DecontSplitResume,
    "define_articol": DefineArticolResume,
    "v3_approve": V3ApproveResume,
    "wait_validare": WaitValidareResume,
    "need_rj_export": NeedExportResume,
    "recon_ambiguous": AmbiguousResume,
    "recon_review_contest": ContestResume,
    "recon_how_mismatch": HowMismatchResume,
    "v2_close": V2CloseResume,
    "v4_codit": V4CoditResume,
    "explained_rule": core.ExplainedRuleResume,
    "control_disposition": core.ControlDispositionResume,
}

# One answer per kind that both sides accept (the core's field names where they differ).
PART = {
    "part_hash": SHA,
    "source_doc_id": "bon_fiscal",
    "kinds": ["pdf"],
    "bon_our_cui_on_doc": None,
    "counterparty_cui": CUI,
}
BASE = {
    "define_class": {"source_doc_id": "bon_fiscal"},
    "bon_cui_unclear": {"cu_cui": True, "fara_cui": False},
    "decont_split": {"parts": [PART]},
    "define_articol": {"articol_id": "bon_cu_cui"},
    "v3_approve": {"decision": "approve", "edit": None},
    "wait_validare": {"validated": True, "saga_doc_key": "k1"},
    "need_rj_export": {"export_id": "rj_2026_09"},
    "recon_ambiguous": {"action": "already_posted", "sink_line_ids": [0]},
    "recon_review_contest": {"action": "already_posted"},
    "recon_how_mismatch": {"ack_mismatch": True, "open_storno": False},
    "v2_close": {"action": "hold", "explained_rule": None},
    "v4_codit": {"accept": False, "skip": True, "edit": None, "seed_next": None},
    "explained_rule": {"rule_id": "r_a"},
    "control_disposition": {"control_id": "c1_x", "disposition": "hold", "rule_id": None},
}

# The values each field is set to: the atoms of both grammars at their edges.
POOL: tuple = (
    None,
    True,
    False,
    0,
    3,
    -1,
    "",
    "  ",
    "abc",
    "a_b",
    "0abc",
    "a.b",
    "a-b",
    "Abc",
    "x y",
    CUI,
    "RO" + CUI,
    "0" + CUI,
    CUI[:-1] + "1",
    "2026-09",
    "2026-13",
    SHA,
    SHA.upper(),
    {},
    {"a": 1},
    [],
    [0, 2],
    [0, "1"],
    [-1],
)
MISSING = object()


@cache
def _kcat():
    return load_catalog(ROOT / "catalog")


@cache
def _ccat():
    return core.load_catalog(_pinned_checkout())


def _shared() -> list[str]:
    return sorted(set(_kcat().ids("QuestionKind")) & set(_ccat().hitl))


# ----- the catalogs' rows, rendered in one grammar -----


def _kit_render(t: kq.T) -> str:
    if t.kind == "enum":
        out = f"enum({'|'.join(t.values)})"
    elif t.kind == "list":
        out = f"list[{_kit_render(t.item)}]"
    elif t.kind == "record":
        out = "{" + ", ".join(f"{n}: {_kit_render(ft)}" for n, ft in t.fields) + "}"
    else:
        out = t.kind
    return out + ("?" if t.optional else "")


def _split_top(s: str, sep: str) -> list[str]:
    parts, depth, cur = [], 0, ""
    for ch in s:
        depth += ch in "[{"
        depth -= ch in "]}"
        if ch == sep and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    return [*parts, cur]


_WORDS = {
    "bool",
    "int",
    "str",
    "slug",
    "cui",
    "period",
    "sha256",
    "object",
    "date",
    "primary_kind",
}


def _core_render(expr) -> str:
    """The core's ``resume_schema`` grammar (``a|b``, ``T|null``, ``[T]``, ``{f: T}``, ``T in
    x``) in the kit's (``enum(a|b)``, ``T?``, ``list[T]``, ``{f: T}``); a qualifier is kept."""
    if isinstance(expr, list):
        (item,) = expr
        return f"list[{_core_render(item)}]"
    if isinstance(expr, dict):
        return "{" + ", ".join(f"{k}: {_core_render(v)}" for k, v in expr.items()) + "}"
    s = expr.strip()
    if s.startswith("[") and s.endswith("]"):
        return f"list[{_core_render(s[1:-1])}]"
    if s.startswith("{") and s.endswith("}"):
        fields = [f.split(":", 1) for f in _split_top(s[1:-1], ",")]
        return "{" + ", ".join(f"{k.strip()}: {_core_render(v)}" for k, v in fields) + "}"
    alts = [a.strip() for a in _split_top(s, "|")]
    optional = "null" in alts
    alts = [a for a in alts if a != "null"]
    if len(alts) == 1 and (alts[0].split(" ")[0] in _WORDS or alts[0].startswith(("[", "{"))):
        out = _core_render(alts[0]) if alts[0].startswith(("[", "{")) else alts[0]
    else:
        out = f"enum({'|'.join(alts)})"
    return out + ("?" if optional else "")


def _kit_fields(kind: str) -> list[tuple[str, str]]:
    row = _kcat().get("QuestionKind", kind)
    return [(f, _kit_render(kq.parse_type(e))) for f, e in row.answer.items()]


def _core_fields(kind: str) -> list[tuple[str, str]]:
    return [(f, _core_render(e)) for f, e in _ccat().hitl[kind]["resume_schema"].items()]


def _row_view() -> dict[str, Counter]:
    """Per shared kind and field position: agree, or the gap it falls in."""
    out: dict[str, Counter] = {"actor": Counter(), "asked": Counter(), "fields": Counter()}
    for kind in _shared():
        krow, crow = _kcat().get("QuestionKind", kind), _ccat().hitl[kind]
        out["actor"]["agree" if krow.actor == crow["actor"] else "differ"] += 1
        same = [GRAPH[krow.procedure]] == sorted(crow["graph_ids"])
        out["asked"]["agree" if same else "differ"] += 1
        for k, c in zip(_kit_fields(kind), _core_fields(kind), strict=True):
            out["fields"]["agree" if k == c else "differ"] += 1
    return out


def _row_diffs() -> dict:
    """What differs in the rows: kind.field → (kit, core) rendered, and where each is asked."""
    shapes, asked = {}, {}
    for kind in _shared():
        for k, c in zip(_kit_fields(kind), _core_fields(kind), strict=True):
            if k != c:
                shapes[f"{kind}.{k[0]}"] = (f"{k[0]}: {k[1]}", f"{c[0]}: {c[1]}")
        krow, crow = _kcat().get("QuestionKind", kind), _ccat().hitl[kind]
        if [GRAPH[krow.procedure]] != sorted(crow["graph_ids"]):
            asked[kind] = (krow.procedure, sorted(crow["graph_ids"]))
    return {"shapes": shapes, "asked": asked}


def _options() -> dict[str, tuple[list[str], list[str]]]:
    """Every enum field of a shared kind: its options on each side, in order."""
    out = {}
    for kind in _shared():
        for (kf, kt), (_, ct) in zip(_kit_fields(kind), _core_fields(kind), strict=True):
            if kt.startswith("enum("):
                out[f"{kind}.{kf}"] = (_enum(kt), _enum(ct))
    return out


def _enum(rendered: str) -> list[str]:
    return rendered.rstrip("?")[5:-1].split("|")


# ----- the answers' shapes -----


def _with(base: dict, field: str, value) -> dict:
    out = dict(base)
    if value is MISSING:
        out.pop(field, None)
    else:
        out[field] = value
    return out


@cache
def _res_cases() -> tuple[tuple[str, str, object, object], ...]:
    """(kind, what is varied, the answer, its value): every answer of the corpus."""
    opts = _options()
    cases = []
    for kind, base in BASE.items():
        cases.append((kind, "base", base, None))
        cases.append((kind, "unknown field", {**base, "colour": 1}, 1))
        for v in ([], "x", None):
            cases.append((kind, "not a record", v, v))
        for field in base:
            extra = tuple(o for pair in opts.get(f"{kind}.{field}", ()) for o in pair)
            for v in (*POOL, *extra, MISSING):
                cases.append((kind, field, _with(base, field, v), v))
        if kind == "decont_split":
            for field in PART:
                for v in (*POOL, "ubl_spv", "pdfx", ["ubl_spv"], ["pdfx"], MISSING):
                    part = _with(PART, field, v)
                    cases.append((kind, f"parts.{field}", {"parts": [part]}, v))
            cases.append((kind, "parts.unknown field", {"parts": [{**PART, "colour": 1}]}, 1))
    return tuple(cases)


def _kit_ok(kind: str, answer) -> bool:
    return kq.check_record(answer, _kcat().get("QuestionKind", kind).answer) == []


def _core_ok(kind: str, answer) -> bool:
    try:
        MODELS[kind].model_validate(answer)
    except ValidationError:
        return False
    return True


def _value_class(v) -> str:
    return "missing" if v is MISSING else repr(v)


_KIT_SLUG = re.compile(r"[a-z][a-z0-9_]*")
_CORE_SLUG = re.compile(r"[a-z0-9][a-z0-9_.-]*")


def _res_tag(kind: str, what: str, v, kit: bool, cor: bool) -> str:
    """The declared gap a disagreement falls in, or ``unexplained``."""
    field = what.split(".")[-1]
    if kind == "recon_review_contest" and v in ("how_ok", "ack_mismatch"):
        return "review_contest_options"
    if kind == "recon_ambiguous" and field == "sink_line_ids" and v is MISSING:
        return "sink_line_ids_optional_in_the_core"
    if kind == "need_rj_export" and field == "export_id" and isinstance(v, str):
        return "export_id_is_a_str_in_the_cores_model"
    if kind == "control_disposition" and field == "control_id" and isinstance(v, str):
        return "control_id_pattern"
    if what == "parts.counterparty_cui":
        return "cui_spelling"
    if kind == "decont_split" and what in ("parts", "parts.kinds"):
        return "decont_split_parts"
    if field == "saga_doc_key" and isinstance(v, str) and not v.strip():
        return "blank_str"
    if (
        isinstance(v, str)
        and _CORE_SLUG.fullmatch(v)
        and not _KIT_SLUG.fullmatch(v)
        and not kit
        and cor
    ):
        return "slug_pattern"
    return "unexplained"


_BY_VALUE = ("cui_spelling", "decont_split_parts", "review_contest_options")


@cache
def _res_tally() -> dict[str, tuple[dict, dict]]:
    """Per declared gap, the kit's and the core's outcomes ("<kind>.<what>: accepted|refused")."""
    out: dict[str, tuple[Counter, Counter]] = {}
    for kind, what, answer, v in _res_cases():
        kit, cor = _kit_ok(kind, answer), _core_ok(kind, answer)
        if kit == cor:
            continue
        tag = _res_tag(kind, what, v, kit, cor)
        k, c = out.setdefault(tag, (Counter(), Counter()))
        name = f"{kind}.{what}" + (f" {_value_class(v)}" if tag in _BY_VALUE else "")
        k[f"{name}: {'accepted' if kit else 'refused'}"] += 1
        c[f"{name}: {'accepted' if cor else 'refused'}"] += 1
    return {t: (dict(k), dict(c)) for t, (k, c) in out.items()}


def _res_agreement(kinds) -> dict[tuple[bool, bool], int]:
    out: Counter = Counter()
    for kind, _, answer, _ in _res_cases():
        if kind in kinds:
            out[(_kit_ok(kind, answer), _core_ok(kind, answer))] += 1
    return dict(out)


# ----- the two checks the core holds -----


def _store(rules) -> InMemoryRuleStore:
    store = InMemoryRuleStore()
    for rid in rules or []:
        body = RuleBody(
            description="invented", scope="line", line={"debit": "627", "credit": "5121"}
        )
        store.add(CUI, rid, body)
    return store


@cache
def _check_cases() -> tuple[tuple, ...]:
    """(kind, question's rules, its controls, the answer): the grid of the two in-core checks."""
    cases = []
    for rules in (None, [], ["r_a"], ["r_a", "r_b"]):
        for rid in ("r_a", "r_b", "r_c"):
            cases.append(("explained_rule", rules, None, {"rule_id": rid}))
    for controls in ([], ["c1_x"], ["c1_x", "m1_8_x"]):
        for rules in ([], ["r_a"]):
            for cid in ("c1_x", "m1_8_x", "zz_unknown"):
                for disp in ("explained_rule", "reopen", "hold"):
                    for rid in (None, "r_a", "r_c"):
                        answer = {"control_id": cid, "disposition": disp, "rule_id": rid}
                        cases.append(("control_disposition", rules, controls, answer))
    return tuple(cases)


def _kit_check(kind, rules, controls, answer) -> bool:
    q = {"rules": rules} if kind == "explained_rule" else {"controls": controls, "rules": rules}
    return kq.CHECKS[kind](_kcat(), q, answer) is None


def _core_check(kind, rules, controls, answer) -> bool:
    store = _store(rules)
    if kind == "explained_rule":
        return core.check_explained_rule(store, CUI, core.ExplainedRuleResume(**answer)) is None
    model = core.ControlDispositionResume(**answer)
    return core.check_control_disposition(store, CUI, {c: {} for c in controls}, model) is None


def _check_tag(kind, rules, controls, answer, kit: bool, cor: bool) -> str:
    if kind == "explained_rule" and rules is None:
        return "explained_rule_without_rules"
    if kind == "control_disposition" and answer["disposition"] == "explained_rule":
        if answer["rule_id"] and answer["rule_id"] not in (rules or []):
            return "disposition_rule_unknown"
    return "unexplained"


@cache
def _check_tally() -> dict[str, tuple[dict, dict]]:
    out: dict[str, tuple[Counter, Counter]] = {}
    for case in _check_cases():
        kit, cor = _kit_check(*case), _core_check(*case)
        if kit == cor:
            continue
        k, c = out.setdefault(_check_tag(*case, kit, cor), (Counter(), Counter()))
        k[f"{case[0]}: {'accepted' if kit else 'asked_again'}"] += 1
        c[f"{case[0]}: {'accepted' if cor else 'asked_again'}"] += 1
    return {t: (dict(k), dict(c)) for t, (k, c) in out.items()}


def _check_agreement() -> dict[tuple[str, bool, bool], int]:
    out: Counter = Counter()
    for case in _check_cases():
        out[(case[0], _kit_check(*case), _core_check(*case))] += 1
    return dict(out)


# ----- the key and the log -----


def _questions() -> list[tuple[str, dict]]:
    """(kind, question): every question the corpus asks, in the shapes the kit's callers pass."""
    qs = [
        ("define_class", {"issue": "batch:ab12"}),
        ("bon_cui_unclear", {"issue": "batch:ab12"}),
        ("decont_split", {"issue": "batch:ab12", "pack": {"source_doc_id": "decont"}}),
        (
            "define_articol",
            {
                "issue": "job:j1",
                "candidates": ["bon_cu_cui", "bon_fara_cui"],
                "choices": {"articol_id": ["bon_cu_cui", "bon_fara_cui"]},
            },
        ),
        ("v3_approve", {"job_id": "j1", "document": {"number": "FV-1", "gross": "119.00"}}),
        ("wait_validare", {"issue": "job:j1", "validated_keys": ["k1"]}),
        (
            "need_rj_export",
            {"issue": "recon:x", "months": ["2026-09"], "exports": {"rj_1": ["2026-08"]}},
        ),
        ("recon_ambiguous", {"issue": "recon:x", "job_id": "j1"}),
        ("recon_review_contest", {"issue": "recon:x", "job_id": "j1"}),
        ("recon_how_mismatch", {"issue": "recon:x", "job_id": "j1"}),
        ("v2_close", {"material": True, "blockers": ["need_rj_export"]}),
        ("v2_close", {"material": False, "blockers": [], "rules": ["r_a"]}),
        ("v4_codit", {}),
        ("filing_receipt", {"filing_id": "d300", "period": "2026-09"}),
    ]
    for kind, rules, controls, _ in _check_cases():
        q = {"rules": rules} if controls is None else {"rules": rules, "controls": controls}
        if (kind, q) not in qs:
            qs.append((kind, q))
    return qs


def _hash_view() -> dict[str, int]:
    out: Counter = Counter()
    for kind, q in _questions():
        out["same dict"] += kq.question_hash(q) == core_question_hash(q)
        out["error ignored"] += kq.question_hash({**q, "error": "x"}) == core_question_hash(
            {**q, "error": [{"msg": "x"}]}
        )
        out["as asked"] += kq.question_hash(q) == core_question_hash({"kind": kind, **q})
        out["questions"] += 1
    return dict(out)


# ----- the corpus -----


LIVE = (
    "bon_cui_unclear",
    "decont_split",
    "define_articol",
    "define_class",
    "filing_receipt",
    "need_rj_export",
    "recon_ambiguous",
    "recon_how_mismatch",
    "recon_review_contest",
    "v2_close",
    "v3_approve",
    "v4_codit",
    "wait_validare",
)


def test_the_live_kinds_are_what_the_kits_callers_ask() -> None:
    """The router's asks, Sorting's two questions and the catalog's split questions; no kit module
    asks ``explained_rule`` or ``control_disposition`` (``kit/cards.py`` only renders a card)."""
    asks = set(re.findall(r'_ask\("(\w+)"', (ROOT / "kit/route.py").read_text(encoding="utf-8")))
    asks |= set(re.findall(r'question = "(\w+)"', (ROOT / "kit/sorting.py").read_text("utf-8")))
    cat = _kcat()
    asks |= {
        cat.get("SourceDoc", s).split.question
        for s in cat.ids("SourceDoc")
        if getattr(cat.get("SourceDoc", s), "split", None)
    }
    assert sorted(asks) == list(LIVE)
    for kind in ("explained_rule", "control_disposition"):
        users = [
            p.name
            for p in (ROOT / "kit").glob("*.py")
            if f'"{kind}"' in p.read_text(encoding="utf-8") and p.name != "questions.py"
        ]
        assert users == ["cards.py"], kind


def test_the_corpus_and_every_invented_cui_is_valid() -> None:
    """Fifteen shared kinds; 1021 answers over fourteen of them (``filing_receipt`` has no answer
    model in the core, so none of its answers is compared: gap ``answer_models``); 174 check
    cases; 24 questions. The one invented CUI passes the check digit on both sides; the pool's
    other CUI-like values are spelled to fail one side or both (``RO`` + it, ``0`` + it, its last
    digit changed)."""
    assert len(_shared()) == 15 and set(BASE) == set(_shared()) - {"filing_receipt"}
    assert len(_res_cases()) == 1021
    assert Counter(k for k, *_ in _res_cases())["filing_receipt"] == 0
    assert len(_check_cases()) == 174
    assert len(_questions()) == 24
    assert cui_is_valid(CUI) and core.cui_is_valid(CUI)
    assert all(_kit_ok(k, BASE[k]) and _core_ok(k, BASE[k]) for k in BASE)


# ----- what agrees -----


def test_both_catalogs_name_the_same_actor_and_most_shapes_for_every_shared_kind() -> None:
    """Per shared kind: the actor (15 of 15, ``wait_validare`` the SAGA agent's on both); where it
    is asked (14 of 15); each answer field's position, name, type and options (25 of 29 field
    positions; the field order agrees wherever the names do)."""
    assert _row_view() == {
        "actor": Counter({"agree": 15}),
        "asked": Counter({"agree": 14, "differ": 1}),
        "fields": Counter({"agree": 25, "differ": 4}),
    }
    actors = Counter(_kcat().get("QuestionKind", k).actor for k in _shared())
    assert actors == {"accountant": 14, "saga_agent": 1}
    # the options of four of the five enum fields agree, in order
    assert sum(k == c for k, c in _options().values()) == 4 and len(_options()) == 5


def test_the_answer_shapes_agree_outside_the_declared_gaps_overall_and_live() -> None:
    """Accepted on both or refused on both, over the 1021 answers: 931 agree (119 accepted, 812
    refused), 90 fall in a declared gap. On the 12 compared live kinds (``filing_receipt`` is live
    but not compared): 825 of 885 agree (103 accepted, 722 refused). Every compared kind has an
    answer both accept and one both refuse, so no kind's agreement is vacuous."""
    assert _res_agreement(set(BASE)) == {
        (True, True): 119,
        (False, False): 812,
        (False, True): 86,
        (True, False): 4,
    }
    assert _res_agreement(set(LIVE)) == AGREE_LIVE_SHAPES
    for kind in BASE:
        seen = {(_kit_ok(kind, a), _core_ok(kind, a)) for k, _, a, _ in _res_cases() if k == kind}
        assert {(True, True), (False, False)} <= seen, kind
    tally = _res_tally()
    assert "unexplained" not in tally, tally.get("unexplained")
    assert set(tally) == RES_GAPS


def test_the_two_in_core_checks_agree_outside_the_declared_gaps() -> None:
    """``check_explained_rule`` and ``check_control_disposition`` against the kit's checks of the
    same kinds, on the 174 grid cases (no live kit caller asks either kind): 162 agree, both
    outcomes on both kinds; 12 fall in a declared gap."""
    assert _check_agreement() == {
        ("explained_rule", True, True): 3,
        ("explained_rule", False, False): 6,
        ("explained_rule", True, False): 3,
        ("control_disposition", True, True): 15,
        ("control_disposition", False, False): 138,
        ("control_disposition", True, False): 9,
    }
    tally = _check_tally()
    assert "unexplained" not in tally, tally.get("unexplained")
    assert set(tally) == CHECK_GAPS


def test_the_question_hash_agrees_on_the_same_dict_and_ignores_the_error_on_both() -> None:
    """The kit's ``question_hash`` and the core's namesake (``poarta_contabila.answers``, outside
    the core) on all 24 questions: the same digest for the same dict, and the ``error`` dropped
    on both. As asked, the core's question also carries its ``kind`` (``hitl.ask``), so no key
    agrees (gap ``question_key``). A probe: questions that differ in one value hash apart on both
    sides, so a hash that ignored the question would fail here."""
    assert _hash_view() == {"same dict": 24, "error ignored": 24, "as asked": 0, "questions": 24}
    a, b = {"rules": ["r_a"]}, {"rules": ["r_b"]}
    assert kq.question_hash(a) != kq.question_hash(b)
    assert core_question_hash(a) != core_question_hash(b)


# ----- declared gaps: the module waits on the owner (BUILD WP-20) -----

PARITY_GAPS: dict[str, tuple[object, object]] = {
    # The core's catalog asks twelve kinds the kit's catalog has no row for; every kit kind is
    # one of the core's.
    "core_only_kinds": (
        [],
        [
            "articol_bon",
            "codit_combo",
            "codit_premise",
            "decision_menu",
            "define_module",
            "name_ambiguous",
            "no_counterparty",
            "patch_maps",
            "request_devalidare",
            "stmt_no_identity",
            "which_cui",
            "xml_pdf_pair",
        ],
    ),
    # need_rj_export: the kit asks it in reconcile only, the core in folder_triage as well.
    "asked_where": (
        {"need_rj_export": "reconcile"},
        {"need_rj_export": ["folder_triage", "reconcile_sink"]},
    ),
    # The catalogs' answer shapes, rendered in one grammar, where they differ.
    "answer_shapes": (
        {
            "decont_split.parts": "parts: list[{part_hash: sha256, source_doc_id: slug, "
            "kinds: list[slug], bon_our_cui_on_doc: bool?, counterparty_cui: cui?}]",
            "filing_receipt.period": "period: period",
            "filing_receipt.receipt_key": "receipt_key: str",
            "recon_review_contest.action": "action: enum(already_posted|override_absent)",
        },
        {
            "decont_split.parts": "parts: list[{part_hash: sha256, source_doc_id: slug in "
            "split.children, kinds: list[primary_kind], bon_our_cui_on_doc: bool?, "
            "counterparty_cui: cui?}]",
            "filing_receipt.period": "period: str",
            "filing_receipt.receipt_key": "receipt_bucket_key: str",
            "recon_review_contest.action": "action: "
            "enum(already_posted|override_absent|how_ok|ack_mismatch)",
        },
    ),
    # Where each side's answer shape is checked: the kit's grammar on its catalog row for every
    # kind; the core's answer model, in the core for two kinds, outside it for twelve, and none
    # for filing_receipt (an upload, poarta_contabila.operator_api).
    "answer_models": (
        "kit.questions",
        {
            "bon_cui_unclear": "poarta_contabila.triage",
            "control_disposition": "poarta_contabila.rules",
            "decont_split": "poarta_contabila.triage",
            "define_articol": "poarta_contabila.ingest",
            "define_class": "poarta_contabila.triage",
            "explained_rule": "poarta_contabila.rules",
            "filing_receipt": "none",
            "need_rj_export": "poarta_contabila.reconcile",
            "recon_ambiguous": "poarta_contabila.reconcile",
            "recon_how_mismatch": "poarta_contabila.reconcile",
            "recon_review_contest": "poarta_contabila.reconcile",
            "v2_close": "poarta_contabila.close",
            "v3_approve": "poarta_contabila.ingest",
            "v4_codit": "poarta_contabila.close",
            "wait_validare": "poarta_contabila.ingest",
        },
    ),
    # Each kind's check: the kit's CHECKS for fourteen kinds; the core's in the core for two.
    "checks_outside_the_core": (
        [
            "bon_cui_unclear",
            "control_disposition",
            "decont_split",
            "define_articol",
            "define_class",
            "explained_rule",
            "filing_receipt",
            "need_rj_export",
            "recon_ambiguous",
            "recon_how_mismatch",
            "v2_close",
            "v3_approve",
            "v4_codit",
            "wait_validare",
        ],
        ["control_disposition", "explained_rule"],
    ),
    # The answer shapes, answer by answer (accepted / refused), where they differ.
    # A slug: the kit's [a-z][a-z0-9_]*, the core's [a-z0-9][a-z0-9_.-]*: a slug that starts
    # with a digit or holds a dot or a dash is refused by the kit, accepted by the core.
    "slug_pattern": (
        {
            "control_disposition.rule_id: refused": 9,
            "decont_split.parts.source_doc_id: refused": 9,
            "define_articol.articol_id: refused": 9,
            "define_class.source_doc_id: refused": 9,
            "explained_rule.rule_id: refused": 9,
            "v2_close.explained_rule: refused": 9,
        },
        {
            "control_disposition.rule_id: accepted": 9,
            "decont_split.parts.source_doc_id: accepted": 9,
            "define_articol.articol_id: accepted": 9,
            "define_class.source_doc_id: accepted": 9,
            "explained_rule.rule_id: accepted": 9,
            "v2_close.explained_rule: accepted": 9,
        },
    ),
    # control_id: the kit's slug, the core's model ^[A-Za-z0-9][A-Za-z0-9_.-]*$ (the core's own
    # control ids are upper case, C0_…, M1_…).
    "control_id_pattern": (
        {"control_disposition.control_id: refused": 12},
        {"control_disposition.control_id: accepted": 12},
    ),
    # export_id: a slug on both catalogs, but the core's model takes any non-empty str.
    "export_id_is_a_str_in_the_cores_model": (
        {"need_rj_export.export_id: refused": 14},
        {"need_rj_export.export_id: accepted": 14},
    ),
    # saga_doc_key "" or blank: the kit's str is not blank, the core's model takes any str.
    "blank_str": (
        {"wait_validare.saga_doc_key: refused": 2},
        {"wait_validare.saga_doc_key: accepted": 2},
    ),
    # sink_line_ids left out: required on both catalogs; the core's model defaults it to [].
    "sink_line_ids_optional_in_the_core": (
        {"recon_ambiguous.sink_line_ids: refused": 1},
        {"recon_ambiguous.sink_line_ids: accepted": 1},
    ),
    # recon_review_contest: the core's options how_ok and ack_mismatch are not the kit's.
    "review_contest_options": (
        {
            "recon_review_contest.action 'ack_mismatch': refused": 1,
            "recon_review_contest.action 'how_ok': refused": 1,
        },
        {
            "recon_review_contest.action 'ack_mismatch': accepted": 1,
            "recon_review_contest.action 'how_ok': accepted": 1,
        },
    ),
    # A decont part's counterparty CUI: the kit strips RO and refuses a leading zero, the core
    # refuses RO and takes a leading zero. This is the answer grammar (check_record, cui?); the
    # sorting step's split_part_cui is kit.sorting.split called directly, past this grammar.
    "cui_spelling": (
        {
            "decont_split.parts.counterparty_cui '041526372': refused": 1,
            "decont_split.parts.counterparty_cui 'RO41526372': accepted": 1,
        },
        {
            "decont_split.parts.counterparty_cui '041526372': accepted": 1,
            "decont_split.parts.counterparty_cui 'RO41526372': refused": 1,
        },
    ),
    # No part, a part with no kind, a kind outside the core's PrimaryKind: the kit accepts, the
    # core refuses (min_length=1, PrimaryKind). The part with no kind is the same fact as the
    # sorting step's split_part_without_kind.
    "decont_split_parts": (
        {
            "decont_split.parts []: accepted": 1,
            "decont_split.parts.kinds []: accepted": 1,
            "decont_split.parts.kinds ['pdfx']: accepted": 1,
        },
        {
            "decont_split.parts []: refused": 1,
            "decont_split.parts.kinds []: refused": 1,
            "decont_split.parts.kinds ['pdfx']: refused": 1,
        },
    ),
    # The checks. explained_rule asked with no rules: the kit accepts any rule_id, the core
    # (an empty store) asks again.
    "explained_rule_without_rules": (
        {"explained_rule: accepted": 3},
        {"explained_rule: asked_again": 3},
    ),
    # control_disposition explained_rule naming a rule the client has not written: the kit does
    # not look (its question has no rules), the core asks again.
    "disposition_rule_unknown": (
        {"control_disposition: accepted": 9},
        {"control_disposition: asked_again": 9},
    ),
    # v4_codit's edit and seed_next: the kit's check takes any keys (kit/steps.py refuses all but
    # its ALLOWED_EDIT / ALLOWED_SEED when it applies the answer); the core's v4_patch and v4_seed
    # refuse all but v4_rules' may_patch / seed_next_period_on.
    "v4_edit_fields": (
        {"check refuses": [], "apply edits": ["exig"], "apply seeds": ["impozit", "tva"]},
        {
            "edit refused": ["impozit", "tva", "zzz"],
            "seed refused": ["auto", "exig", "saf_t", "zzz"],
        },
    ),
    # The key: as asked, the core's question carries its kind (hitl.ask), the kit's does not, so
    # the same question has another hash (all 24); the core's question_hash is outside the core.
    "question_key": (
        {"as asked": 0, "home": "kit.questions"},
        {"as asked": 0, "home": "poarta_contabila.answers"},
    ),
    # The answer log's outcomes; the core's log is outside the core (poarta_contabila.answers).
    "answer_log": (["accepted", "asked_again"], ["accepted", "asked_again", "no_question"]),
    # What the kit's other modules import from kit.questions; the core has none of those names.
    "caller_shapes": (
        ["AnswerError", "T", "answer_question", "check_record", "parse_type", "question_hash"],
        {
            "AnswerError": "absent",
            "T": "absent",
            "answer_question": "absent",
            "check_record": "absent",
            "parse_type": "absent",
            "question_hash": "absent",
        },
    ),
}

RES_GAPS = {
    "slug_pattern",
    "control_id_pattern",
    "export_id_is_a_str_in_the_cores_model",
    "blank_str",
    "sink_line_ids_optional_in_the_core",
    "review_contest_options",
    "cui_spelling",
    "decont_split_parts",
}
CHECK_GAPS = {"explained_rule_without_rules", "disposition_rule_unknown"}
AGREE_LIVE_SHAPES = {(True, True): 103, (False, False): 722, (False, True): 56, (True, False): 4}


def _caller_names() -> list[str]:
    names = set()
    for path in sorted((ROOT / "kit").glob("*.py")):
        if path.name == "questions.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module == "kit.questions":
                names |= {a.name for a in node.names}
    return sorted(names)


def _v4_observed() -> tuple[dict, dict]:
    keys = ["auto", "exig", "impozit", "saf_t", "tva", "zzz"]
    kit_refuses = [
        k
        for k in keys
        if kq.CHECKS["v4_codit"](_kcat(), {}, {"accept": True, "skip": False, "edit": {k: None}})
        or kq.CHECKS["v4_codit"](_kcat(), {}, {"accept": True, "skip": False, "seed_next": {k: 1}})
    ]

    def refused(f, k) -> bool:
        try:
            f(k)
        except ValueError as exc:
            return "only" in str(exc)
        except AttributeError:  # past the field gate, on to the (absent) CO.DiT
            return False
        return False

    edit = [k for k in keys if refused(lambda k: core.v4_patch(_ccat(), None, {k: None}), k)]
    seed = [k for k in keys if refused(lambda k: core.v4_seed(_ccat(), None, {k: None}, None), k)]
    return (
        {
            "check refuses": kit_refuses,
            "apply edits": sorted(ks.ALLOWED_EDIT),
            "apply seeds": sorted(ks.ALLOWED_SEED),
        },
        {"edit refused": edit, "seed refused": seed},
    )


def _observed(gap: str) -> tuple[object, object]:
    if gap in _res_tally():
        return _res_tally()[gap]
    if gap in _check_tally():
        return _check_tally()[gap]
    kit_kinds, core_kinds = set(_kcat().ids("QuestionKind")), set(_ccat().hitl)
    if gap == "core_only_kinds":
        return sorted(kit_kinds - core_kinds), sorted(core_kinds - kit_kinds)
    if gap == "asked_where":
        asked = _row_diffs()["asked"]
        return {k: v[0] for k, v in asked.items()}, {k: v[1] for k, v in asked.items()}
    if gap == "answer_shapes":
        shapes = _row_diffs()["shapes"]
        return {k: v[0] for k, v in shapes.items()}, {k: v[1] for k, v in shapes.items()}
    if gap == "answer_models":
        homes = {k: MODELS[k].__module__ if k in MODELS else "none" for k in _shared()}
        return kq.check_record.__module__, homes
    if gap == "checks_outside_the_core":
        mine = sorted(set(kq.CHECKS) & set(_shared()))
        theirs = sorted(
            n[6:] for n in core.__all__ if n.startswith("check_") and n[6:] in _ccat().hitl
        )
        return mine, theirs
    if gap == "v4_edit_fields":
        return _v4_observed()
    if gap == "question_key":
        as_asked = _hash_view()["as asked"]
        return (
            {"as asked": as_asked, "home": kq.question_hash.__module__},
            {"as asked": as_asked, "home": core_question_hash.__module__},
        )
    if gap == "answer_log":
        import typing

        status = typing.get_type_hints(kq.Outcome)["status"]
        return list(typing.get_args(status)), list(typing.get_args(CoreOutcome))
    if gap == "caller_shapes":
        names = _caller_names()
        return names, {n: "present" if hasattr(core, n) else "absent" for n in names}
    raise KeyError(gap)


def test_the_answer_models_and_logs_are_outside_the_core() -> None:
    """Of the modules the core's answer models, checks, key and log live in, only
    ``poarta_contabila.rules`` (``core.rules``) is a core module."""
    homes = {MODELS[k].__module__ for k in MODELS} | {core_question_hash.__module__}
    assert sorted(h for h in homes if h in core.CORE_MODULES_FLAT) == ["poarta_contabila.rules"]
    assert "core.questions" not in core.CORE_MODULES and "core.hitl" not in core.CORE_MODULES


@pytest.mark.parametrize("gap", sorted(PARITY_GAPS))
def test_each_declared_gap_still_holds_exactly(gap: str) -> None:
    assert _observed(gap) == PARITY_GAPS[gap]
