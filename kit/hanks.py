"""Hanks: render a run with the catalog's pins, and verify what a codon wrote (P8).

A hank in ``hanks/{name}/hank.json`` carries the placeholder model ``unpinned`` on every codon;
the runtime itself refuses it. ``render`` copies the hank into a run directory and writes each
codon's model from its role row (by codon and tier). A role with no pin refuses the whole run:
``HankRefused``, and the route's question goes to a person. ``command`` is the one way the
Dispatcher starts the runtime: the exact version, headless, with cost and time limits, never a
model override or ``--ignore-rig-failures``.

``verify`` is the gate between a codon's file and a fact. The file must fit the role's ``answer``
shape exactly (the questions grammar, unknown fields refused, P10) and pass the role's own check:
a statement read must tie and belong to the client; a part must be a file of the container; a
cited fact must be in the input; a review keeps its Job; a drafted rule must match an
unexplained document. A refused judge reads as the doubtful verdict, which always asks; a close
suggestion on a material month keeps no ``file`` (P11). Nothing here runs a model or writes the
dossier.

A passing answer is stored under (role, input hash, card hash) with who gave it (P12):
``kit hank-run`` stores its run's answers as the role's pinned model's, with the run;
``kit verify --dossiers --operator`` stores a file someone supplied as that operator's. An
operator's answer never stands in for a model run on a real client's dossier: there
``kit hank-run`` refuses the hank the way an unpinned role does (``HankHeld``, its reason
kept) and writes no fact from that answer. Only on a dossier marked a test firm
(``kit dossier mark-test-firm``) is it used, as the operator's, for rigs and development loops
with no live model.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from kit.catalog import Catalog, ModelRoleRow
from kit.period import ExplainedRule, doc_rule_matches, weigh_suggestion
from kit.questions import check_record
from kit.recon import SinkDoc
from kit.sorting import Pack, SplitError, split
from kit.types import cui_is_valid, normalize_cui

RUNTIME = "hankweave@0.12.0"
UNPINNED = "unpinned"
NEVER_PASSED = ("-m", "--model", "--ignore-rig-failures", "-f", "--force", "--proxy")
DOUBTFUL = {"accounts_ok": False, "risk": "unknown", "needs_human": True}
EXPLAIN_MAX = 1200

_AMOUNT = re.compile(r"^-?\d+\.\d{2}$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class HankError(ValueError):
    """The hank folder and the catalog disagree: a build error, never a model's."""


class HankRefused(Exception):
    """A role of the hank has no pinned model: the hank refuses and a person is asked (P8)."""

    def __init__(self, hank: str, roles: list[str]):
        self.hank, self.roles = hank, roles
        super().__init__(f"{hank}: no pinned model for {', '.join(roles)} (D3): a person is asked")


class HankHeld(Exception):
    """A cached answer of the hank's is not a model run's output, and the dossier is a real
    client's: nothing runs and nothing of that answer becomes a fact; the hank refuses, with the
    reason, and a person is asked on the route (P8, P10)."""

    def __init__(self, hank: str, roles: list[str], reason: str, input_hash: str):
        self.hank, self.roles, self.reason, self.input_hash = hank, roles, reason, input_hash
        super().__init__(f"{hank}: {reason}")


# ----- the hank and its roles -----


def roles_for(cat: Catalog, hank: str, tier: str = "everyday") -> dict[str, ModelRoleRow]:
    """Each codon's role: the row of this tier when the codon has one, else the everyday row."""
    rows = [cat.get("ModelRole", r) for r in cat.ids("ModelRole")]
    rows = [r for r in rows if r.hank == hank]
    if not rows:
        raise HankError(f"no model role names hank {hank!r}")
    out: dict[str, ModelRoleRow] = {}
    for r in sorted(rows, key=lambda r: r.tier != tier):
        out.setdefault(r.codon, r)
    return out


def load_hank(root: Path, hank: str) -> dict:
    return json.loads((root / "hanks" / hank / "hank.json").read_text(encoding="utf-8"))


def check_hank(cat: Catalog, root: Path, hank: str) -> list[str]:
    """Every way the hank folder misses its role rows and the conventions (hanks/README.md)."""
    problems = []
    doc = load_hank(root, hank)
    roles = roles_for(cat, hank)
    codons = [c for c in doc.get("hank", []) if c.get("type", "codon") == "codon"]
    if len(codons) != len(doc.get("hank", [])):
        problems.append("a hank of this kit has codons only, no loops")
    if [c["id"] for c in codons] != list(dict.fromkeys(c["id"] for c in codons)):
        problems.append("codon ids repeat")
    if {c["id"] for c in codons} != set(roles):
        problems.append(f"codons {sorted(c['id'] for c in codons)} ≠ roles {sorted(roles)}")
    for c in codons:
        role = roles.get(c["id"])
        where = f"codon {c['id']}"
        if c.get("model") != UNPINNED:
            problems.append(f"{where}: model is {c.get('model')!r}; the folder holds {UNPINNED!r}")
        if c.get("continuationMode") != "fresh":
            problems.append(f"{where}: continuationMode is not fresh")
        if "budget" not in c:
            problems.append(f"{where}: no budget")
        if c.get("rigSetup") or c.get("onFailure", "abort") != "abort":
            problems.append(f"{where}: no rig and onFailure abort (fail closed)")
        if role is None:
            continue
        if f"hanks/{hank}/{c.get('promptFile')}" != role.card:
            problems.append(f"{where}: promptFile is not the role's card {role.card}")
        if c.get("outputFiles") != [{"copy": [f"out/{role.output}"]}]:
            problems.append(f"{where}: outputFiles copy only out/{role.output}")
        if not (root / role.card).is_file():
            problems.append(f"{where}: card {role.card} is missing")
    return problems


def card_hash(root: Path, role: ModelRoleRow, hank_doc: dict | None = None) -> str:
    """The pin, the hank's system prompt and the role card: a cached answer is reused only for
    the same three (ARCHITECTURE §6)."""
    doc = hank_doc or load_hank(root, role.hank)
    h = hashlib.sha256()
    h.update((role.model or UNPINNED).encode() + b"\n")
    system = doc.get("globalSystemPromptFile")
    if system:
        h.update((root / "hanks" / role.hank / system).read_bytes())
    h.update(b"\n" + (root / role.card).read_bytes())
    return h.hexdigest()


def input_hash(inp: dict) -> str:
    return hashlib.sha256(
        json.dumps(inp, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


# ----- rendering a run -----


@dataclass
class Rendered:
    hank: str
    run_dir: Path
    models: dict[str, str]  # codon -> exact model id
    roles: dict[str, str]  # codon -> role id
    card_hashes: dict[str, str]  # role id -> card hash
    max_dollars: float
    max_seconds: int


def render(cat: Catalog, root: Path, hank: str, run_dir: Path, tier: str = "everyday") -> Rendered:
    problems = check_hank(cat, root, hank)
    if problems:
        raise HankError(f"{hank}: " + "; ".join(problems))
    roles = roles_for(cat, hank, tier)
    unpinned = sorted(r.id for r in roles.values() if r.model is None)
    if unpinned:
        raise HankRefused(hank, unpinned)
    doc = load_hank(root, hank)
    if run_dir.exists():
        raise HankError(f"{run_dir} exists: a run directory is written once")
    shutil.copytree(root / "hanks" / hank, run_dir)
    for c in doc["hank"]:
        c["model"] = roles[c["id"]].model
    (run_dir / "hank.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    budget = doc["overrides"]["budget"]
    return Rendered(
        hank=hank,
        run_dir=run_dir,
        models={c: r.model for c, r in roles.items()},
        roles={c: r.id for c, r in roles.items()},
        card_hashes={r.id: card_hash(root, r, doc) for r in roles.values()},
        max_dollars=budget["maxDollars"],
        max_seconds=int(budget["maxTimeSeconds"]),
    )


def command(r: Rendered, data_dir: Path, out_dir: Path) -> list[str]:
    """The runtime's command line for a rendered run. The input is the data directory, mounted
    read-only by the runtime; outputs are copied to ``out_dir``."""
    argv = [
        "bunx",
        RUNTIME,
        str(r.run_dir / "hank.json"),
        str(data_dir),
        "--headless",
        "--start-new",
        "--max-cost",
        f"{r.max_dollars:.2f}",
        "--max-time",
        str(r.max_seconds),
        "--output",
        str(out_dir),
    ]
    if set(argv) & set(NEVER_PASSED):  # a path that spells a flag is refused too
        raise HankError(f"the runtime is never passed {sorted(set(argv) & set(NEVER_PASSED))}")
    return argv


# ----- verifying a codon's file -----


@dataclass
class Verified:
    role_id: str
    ok: bool
    body: dict | None  # the fact to store: the answer, weighed; the doubtful verdict if refused
    problems: list[str] = field(default_factory=list)


def _amount(v: str, where: str, problems: list[str]) -> Decimal:
    if not isinstance(v, str) or not _AMOUNT.match(v):
        problems.append(f"{where}: {v!r} is not an amount (digits, '.', two decimals)")
        return Decimal(0)
    return Decimal(v)


def _date(v: str, where: str, problems: list[str]) -> None:
    if not _DATE.match(v):
        problems.append(f"{where}: {v!r} is not a date YYYY-MM-DD")


def _cui(v: str, where: str, problems: list[str]) -> str:
    if not cui_is_valid(v):
        problems.append(f"{where}: {v!r} fails the CUI check digit")
        return ""
    return normalize_cui(v)


def _read(cat, inp: dict, out: dict) -> list[str]:
    p: list[str] = []
    kind = out["doc_type"]
    other = "invoice" if kind == "statement" else "statement"
    if out.get(kind) is None:
        return [f"doc_type is {kind} but {kind} is missing"]
    if out.get(other) is not None:
        p.append(f"doc_type is {kind} but {other} is filled")
    if inp.get("expected") and inp["expected"] != kind:
        p.append(f"expected a {inp['expected']}, read a {kind}")
    client = normalize_cui(str(inp.get("client_cui", "")))
    if kind == "statement":
        s = out["statement"]
        if _cui(s["holder_cui"], "statement.holder_cui", p) not in ("", client):
            p.append(f"the holder {s['holder_cui']} is not the client {client}")
        _date(s["period_from"], "statement.period_from", p)
        _date(s["period_to"], "statement.period_to", p)
        total = _amount(s["opening"], "statement.opening", p)
        for i, line in enumerate(s["lines"]):
            _date(line["date"], f"statement.lines.{i}.date", p)
            debit = _amount(line["debit"], f"statement.lines.{i}.debit", p)
            credit = _amount(line["credit"], f"statement.lines.{i}.credit", p)
            if debit < 0 or credit < 0 or (debit and credit):
                p.append(f"statement.lines.{i}: one side, not negative")
            total += credit - debit
        closing = _amount(s["closing"], "statement.closing", p)
        if not p and total != closing:
            p.append(f"the lines do not tie: opening − debits + credits = {total}, not {closing}")
    else:
        v = out["invoice"]
        _date(v["date"], "invoice.date", p)
        seller = _cui(v["seller_cui"], "invoice.seller_cui", p)
        buyer = _cui(v["buyer_cui"], "invoice.buyer_cui", p)
        if (seller == client) == (buyer == client):
            p.append(f"the client {client} is not exactly one of seller and buyer")
        net, vat = _amount(v["net"], "invoice.net", p), _amount(v["vat"], "invoice.vat", p)
        gross = _amount(v["gross"], "invoice.gross", p)
        if not p and net + vat != gross:
            p.append(f"net + VAT = {net + vat}, not the gross {gross}")
    return p


def _split(cat, inp: dict, out: dict) -> list[str]:
    files = {f["part_hash"] for f in inp.get("files", [])}
    allowed = set(inp.get("source_docs", []))
    p = [
        f"part {x['part_hash'][:12]}: not a file of the container"
        for x in out["parts"]
        if x["part_hash"] not in files
    ]
    p += [
        f"part {x['part_hash'][:12]}: {x['source_doc_id']} is not one of the input's"
        for x in out["parts"]
        if allowed and x["source_doc_id"] not in allowed
    ]
    if not p:
        try:
            split(cat, Pack.model_validate(inp["pack"]), out)
        except (SplitError, ValueError, KeyError) as exc:
            p.append(str(exc))
    return p


def _explain(prefix: str, fields: tuple[str, ...]):
    def check(cat, inp: dict, out: dict) -> list[str]:
        p = []
        if len(out["explanation"]) > EXPLAIN_MAX:
            p.append(f"the explanation is over {EXPLAIN_MAX} characters")
        known = set(inp.get("facts", {})) | {f"{prefix}.{f}" for f in fields}
        p += [
            f"cites {k!r}, which the input does not hold"
            for k in out["facts_cited"]
            if k not in known
        ]
        return p

    return check


def _review(cat, inp: dict, out: dict) -> list[str]:
    if out["job_id"] != inp.get("job_id"):
        return [f"reviews {out['job_id']!r}, not the input's Job {inp.get('job_id')!r}"]
    return []


def _rules(cat, inp: dict, out: dict) -> list[str]:
    p = []
    docs = []
    for d in inp.get("unexplained", []):
        accounts = set(d.get("accounts", []))
        docs.append(
            (SinkDoc.model_validate({k: v for k, v in d.items() if k != "accounts"}), accounts)
        )
    ids = [r["rule_id"] for r in out["rules"]]
    if len(ids) != len(set(ids)):
        p.append("rule ids repeat")
    for raw in out["rules"]:
        try:
            rule = ExplainedRule.model_validate(raw)
        except ValueError as exc:
            p.append(f"rule {raw.get('rule_id')}: {exc}")
            continue
        if rule.kind == "line":
            if not rule.account:
                p.append(f"rule {rule.rule_id}: a line rule names its account")
            hit = any(rule.account in accts for _, accts in docs)
        else:
            if rule.account:
                p.append(f"rule {rule.rule_id}: a document rule names no account")
            hit = any(doc_rule_matches(rule, d) for d, _ in docs)
        if not hit:
            p.append(f"rule {rule.rule_id}: matches no unexplained document")
    return p


CHECKS = {
    "reader_document": _read,
    "reader_document_strong": _read,
    "reader_split": _split,
    "explain_approve": _explain("verdict", ("accounts_ok", "risk", "needs_human")),
    "review_match": _review,
    "explain_close": _explain("suggest", ("action", "books_support_declaration")),
    "draft_rule": _rules,
}


def verify(cat: Catalog, role_id: str, inp: dict, output: bytes | None) -> Verified:
    role = cat.get("ModelRole", role_id)  # an unknown role is an error (P10)
    problems: list[str] = []
    body: Any = None
    if output is None:
        problems.append(f"{role.output} was not written")
    else:
        try:
            body = json.loads(output.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            problems.append(f"{role.output} is not JSON: {exc}")
    if not problems:
        problems = check_record(body, role.answer)
    if not problems and role_id in CHECKS:
        problems = CHECKS[role_id](cat, inp, body)
    if problems:
        fallback = dict(DOUBTFUL) if role_id == "judge_document" else None
        return Verified(role_id, False, fallback, problems)
    if role_id == "close_suggest":
        body = weigh_suggestion(SimpleNamespace(material=bool(inp.get("material", True))), body)
    return Verified(role_id, True, body)
