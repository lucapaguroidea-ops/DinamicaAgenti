"""PRE, POST and the settlement proposal: deterministic, no model (P7), ARCHITECTURE §4.3.

The eye is a ``Witness``: what SAGA's exports show for one client — the months they cover, the
documents (registru jurnal / journals), the journal lines with their accounts, and the SPV
register. Its readers come with the SAGA formats (R4, P16); matching depends only on this shape.

- ``pre_check``: is the document already in the books? ``already_posted`` (one sink document
  agrees on every key of the profile, or the SPV register lists it as posted), ``absent`` (every
  month from the document's to its period is covered and nothing is close), ``ambiguous`` (two
  hits, or two of number / date / gross agree), ``need_export`` (a month is not covered).
  Matching is generous on purpose: a missed match packages a duplicate; a false "close" costs
  one question.
- ``post_check``: how did SAGA post an acked document? Its journal lines against the articol's
  expected accounts (by prefix; all or at least one, per the profile), then the amounts on
  401 / 4111 against gross and 4426 / 4427 / 4428 against VAT, within tolerance.
- ``propose_settlement``: which invoices could a bank line settle? A proposal for the person,
  never a decision.

Money is a two-decimal string outside this module; Decimal inside it (P10).
"""

from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal
from itertools import combinations
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

from kit.catalog import Catalog, ReconcileProfileRow

Money = Annotated[str, StringConstraints(pattern=r"^-?\d+\.\d{2}$")]
Day = Annotated[str, StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}$")]
Month = Annotated[str, StringConstraints(pattern=r"^\d{4}-\d{2}$")]
Level = Literal["exact", "alnum", "digits_core"]
_SIDE = {"intrare": "in", "storn_intrare": "in", "iesire": "out", "storn_iesire": "out"}
_GROSS_ACCOUNTS = ("401", "4111")
_VAT_ACCOUNTS = ("4426", "4427", "4428")


class Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Doc(Closed):
    """The document of a Job, as PRE and POST need it."""

    doc_class: str
    number: str
    date: Day
    partner_cui: str | None
    gross: Money
    vat: Money | None = None
    period: Month


class SinkDoc(Closed):
    """A document as SAGA shows it."""

    saga_key: str
    doc_class: str
    number: str
    date: Day
    partner_cui: str | None
    gross: Money
    validated: bool


class JournalLine(Closed):
    """One line of a posting in SAGA's registru jurnal."""

    saga_key: str
    journal: str
    number: str
    date: Day
    account: str
    side: Literal["debit", "credit"]
    amount: Money


class RegisterEntry(Closed):
    """An invoice in the SPV register; ``posted`` when it reads as recorded in SAGA."""

    number: str
    date: Day
    partner_cui: str | None
    gross: Money
    posted: bool


class Witness(Closed):
    covered: list[Month]
    docs: list[SinkDoc] = []
    lines: list[JournalLine] = []
    spv_register: list[RegisterEntry] = []


class PreResult(Closed):
    verdict: Literal["already_posted", "absent", "ambiguous", "need_export"]
    reason: str
    hits: list[str]
    near: list[str]
    missing: list[Month]
    profile_id: str | None
    snapshot_id: str


class PostResult(Closed):
    verdict: Literal["how_ok", "how_mismatch", "need_export"]
    reason: str
    expected: list[str]
    used: list[str]
    missing: list[Month]
    profile_id: str
    snapshot_id: str


# ----- profiles and numbers -----


def pick_profile(
    cat: Catalog, stage: str, fiscal_class: str | None, default: str | None = None
) -> ReconcileProfileRow | None:
    """The profile of ``stage`` for a fiscal class; else ``default`` (a close kind's profile);
    else the only default of the stage. None = no single profile: a person decides."""
    rows = [cat.get("ReconcileProfile", i) for i in cat.ids("ReconcileProfile")]
    rows = [r for r in rows if r.stage == stage]
    specific = [r for r in rows if fiscal_class and fiscal_class in r.fiscal_classes]
    if len(specific) == 1:
        return specific[0]
    if default is not None:
        return cat.get("ReconcileProfile", default)
    defaults = [r for r in rows if not r.fiscal_classes]
    return defaults[0] if len(defaults) == 1 else None


def normalize_number(number: str, level: Level) -> str:
    """exact: trimmed, upper; alnum: letters and digits only; digits_core: digits without
    leading zeros (counts only with the same partner CUI)."""
    s = number.strip().upper()
    if level == "alnum":
        return re.sub(r"[^0-9A-Z]", "", s)
    if level == "digits_core":
        return re.sub(r"\D", "", s).lstrip("0")
    return s


def _number_agrees(a: str, b: str, levels: list[str], same_partner: bool) -> bool:
    for level in levels or ["exact"]:
        if level == "digits_core" and not same_partner:
            continue
        na, nb = normalize_number(a, level), normalize_number(b, level)
        if na and na == nb:
            return True
    return False


def _months(first: str, last: str) -> list[str]:
    (y, m), (ly, lm) = map(int, first.split("-")), map(int, last.split("-"))
    if (y, m) > (ly, lm):
        (y, m), (ly, lm) = (ly, lm), (y, m)
    out = []
    while (y, m) <= (ly, lm):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _snapshot(*parts: object) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:24]


# ----- PRE -----


def pre_check(profile: ReconcileProfileRow | None, doc: Doc, w: Witness) -> PreResult:
    months = _months(doc.date[:7], doc.period)
    missing = [m for m in months if m not in w.covered]
    scope = [s for s in w.docs if s.date[:7] in months]
    snap = _snapshot(
        profile.id if profile else None,
        [s.model_dump() for s in scope],
        [r.model_dump() for r in w.spv_register],
    )

    def result(verdict, reason, hits=(), near=()):
        return PreResult(
            verdict=verdict,
            reason=reason,
            hits=list(hits),
            near=list(near),
            missing=missing,
            profile_id=profile.id if profile else None,
            snapshot_id=snap,
        )

    if profile is None:
        return result("ambiguous", "no single PRE profile for this document")
    if missing:
        return result("need_export", f"no export of the books covers {missing}")

    tol = Decimal(profile.tolerance)
    keys = profile.match_keys
    side = _SIDE.get(doc.doc_class, doc.doc_class)
    hits, near = [], []
    for s in scope:
        if _SIDE.get(s.doc_class, s.doc_class) != side:
            continue
        conflict = bool(doc.partner_cui and s.partner_cui and doc.partner_cui != s.partner_cui)
        same_partner = bool(doc.partner_cui and doc.partner_cui == s.partner_cui)
        agree = {
            "number": _number_agrees(doc.number, s.number, profile.number_levels, same_partner),
            "date": doc.date == s.date,
            "gross": abs(Decimal(doc.gross) - Decimal(s.gross)) <= tol,
        }
        if all(agree[k] for k in keys) and not conflict:
            hits.append(s.saga_key)
        elif len(keys) == 3 and sum(agree[k] for k in keys) >= 2:
            near.append(s.saga_key)
    if len(hits) == 1:
        return result("already_posted", f"in the books as {hits[0]}", hits, near)
    if len(hits) > 1:
        return result("ambiguous", f"{len(hits)} documents in the books agree", hits, near)

    for r in w.spv_register:
        if r.posted and side == "in" and doc.partner_cui and r.partner_cui == doc.partner_cui:
            if (
                _number_agrees(doc.number, r.number, profile.number_levels, True)
                and r.date == doc.date
                and abs(Decimal(doc.gross) - Decimal(r.gross)) <= tol
            ):
                return result("already_posted", f"the SPV register lists {r.number} as posted")
    if near:
        return result("ambiguous", "something close but not decisive", hits, near)
    return result("absent", f"not in the books of {months}")


# ----- POST -----


def post_check(
    profile: ReconcileProfileRow, expect_accounts: list[str], doc: Doc, w: Witness
) -> PostResult:
    expected = list(expect_accounts) or list(profile.fallback_accounts)
    month = doc.date[:7]
    missing = [] if month in w.covered else [month]

    def result(verdict, reason, used=(), lines=()):
        return PostResult(
            verdict=verdict,
            reason=reason,
            expected=expected,
            used=sorted(set(used)),
            missing=missing,
            profile_id=profile.id,
            snapshot_id=_snapshot(profile.model_dump(), expected, [x.model_dump() for x in lines]),
        )

    if missing or not w.lines:
        return result("need_export", f"no journal lines of the books cover {month}")
    if not expected:
        return result("how_mismatch", "no expected accounts: a person decides")

    tol = Decimal(profile.tolerance)
    levels = [lv for lv in profile.number_levels if lv != "digits_core"]  # lines carry no partner
    if "number" in profile.match_keys:
        posting = [
            x
            for x in w.lines
            if x.date == doc.date and _number_agrees(doc.number, x.number, levels, False)
        ]
    else:
        keys = {
            x.saga_key
            for x in w.lines
            if x.date == doc.date and abs(Decimal(x.amount) - Decimal(doc.gross)) <= tol
        }
        posting = [x for x in w.lines if x.saga_key in keys] if len(keys) == 1 else []
    if not posting:
        return result("how_mismatch", f"no posting of {doc.number or doc.gross} on {doc.date}")

    used = [x.account for x in posting]
    present = [a for a in expected if any(u.startswith(a) for u in used)]
    absent = [a for a in expected if a not in present]
    if profile.require_all_accounts and absent:
        return result("how_mismatch", f"expected accounts not used: {absent}", used, posting)
    if not present:
        return result(
            "how_mismatch", f"none of the expected accounts {expected} is used", used, posting
        )

    wrong = []
    for a in present:
        target = doc.gross if a in _GROSS_ACCOUNTS else doc.vat if a in _VAT_ACCOUNTS else None
        if target is None:
            continue
        moved = sum((Decimal(x.amount) for x in posting if x.account.startswith(a)), Decimal(0))
        if abs(moved - Decimal(target)) > tol:
            wrong.append(f"{a} moves {moved} against {target}")
    if wrong:
        return result("how_mismatch", "; ".join(wrong), used, posting)
    return result("how_ok", f"posted on {present}", used, posting)


# ----- the settlement proposal -----


class OpenInvoice(Closed):
    ref: str  # the Job id or SAGA key
    doc_class: str
    number: str
    date: Day
    partner_cui: str | None
    partner_name: str | None
    gross: Money
    paid: Money = "0.00"


class BankLine(Closed):
    doc_class: Literal["incasare", "plata"]
    date: Day
    gross: Money
    description: str = ""


class Candidate(Closed):
    ref: str
    kind: Literal["full", "partial"]
    open_after: Money
    named_number: bool
    named_partner: bool


class Proposal(Closed):
    candidates: list[Candidate]
    edit: dict | None
    groups: list[list[str]]


_SETTLES = {"incasare": "iesire", "plata": "intrare"}


def _alnum(s: str | None) -> str:
    return re.sub(r"[^0-9A-Z]", "", (s or "").upper())


def propose_settlement(line: BankLine, invoices: list[OpenInvoice]) -> Proposal:
    amount, desc = Decimal(line.gross), _alnum(line.description)
    open_ = [
        (i, Decimal(i.gross) - Decimal(i.paid))
        for i in invoices
        if i.doc_class == _SETTLES[line.doc_class] and i.date <= line.date
    ]
    open_ = [(i, o) for i, o in open_ if o > 0]

    scored = []
    for i, o in open_:
        named_number = bool(_alnum(i.number)) and _alnum(i.number) in desc
        named_partner = bool(_alnum(i.partner_name)) and _alnum(i.partner_name) in desc
        if o == amount:
            kind = "full"
        elif o > amount and (named_number or named_partner):
            kind = "partial"
        else:
            continue
        score = (named_number, named_partner, kind == "full")
        c = Candidate(
            ref=i.ref,
            kind=kind,
            open_after=f"{(o - amount):.2f}",
            named_number=named_number,
            named_partner=named_partner,
        )
        scored.append((score, c, i))
    scored.sort(key=lambda t: t[0], reverse=True)
    candidates = [c for _, c, _ in scored]

    edit = None
    if scored and (len(scored) == 1 or scored[0][0] > scored[1][0]):
        _, best, inv = scored[0]
        edit = {"settles": best.ref, "partner_cui": inv.partner_cui}

    groups: list[list[str]] = []
    if not any(c.kind == "full" for c in candidates):
        by_partner: dict[str | None, list] = {}
        for i, o in open_:
            if o < amount:
                by_partner.setdefault(i.partner_cui, []).append((i, o))
        for items in by_partner.values():
            for n in (2, 3, 4):
                for combo in combinations(items, n):
                    if sum((o for _, o in combo), Decimal(0)) == amount:
                        groups.append(sorted(i.ref for i, _ in combo))
    return Proposal(candidates=candidates, edit=edit, groups=sorted(groups))
