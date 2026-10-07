"""The period difference and the month's controls (ARCHITECTURE §4.4). Not a ledger (P4).

Left: the month's expected set (its Jobs and their documents) and the client's explained rules.
Right: what SAGA shows (a ``Witness``). Nothing is plugged: a remainder is a bucket row or a
failed control, never an adjusting entry.

- **Buckets.** Each SAGA document of the month matches an expected Job (by the SAGA key the Job
  carries, else side + number + date + gross) → ``expected``; else a document rule →
  ``explained_sink_only``; else ``unexplained``.
- **Outbound holes.** Expected Jobs not ``acked`` or ``already_in_sink``.
- **Parity (C0).** On each watched account, the net movement (credit − debit) the expected
  documents imply — purchase: 401 Cr gross, 4426 Dr VAT; sale: 4111 Dr gross, 4427 Cr VAT; a bank
  line: 5121 on its side and, when bound to a partner, 4111 / 401 opposite — plus the explained
  postings, against the same movement in SAGA's journal lines. A movement with no expected source
  is a difference, on purpose.
- **Controls.** Each catalog row gives PASS / FAIL / INFO. A blocking control that cannot be
  computed for want of an input FAILs; INFO only when it does not apply (its ``require`` axes)
  or its precondition (client maps) is not met.
- **Material** ⇒ ``file`` is refused (P11): no export covers the month, an outbound hole, an
  unexplained document, a blocking control failed, a lock mismatch, a PRE question still open,
  or no close kind fits the CO.DiT. A model's suggestion never clears it.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Callable
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from kit.catalog import Catalog
from kit.recon import Day, JournalLine, Money, SinkDoc, Witness

_SIDE = {"intrare": "in", "storn_intrare": "in", "iesire": "out", "storn_iesire": "out"}
_DONE = {"acked", "already_in_sink"}


class Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ExpectedItem(Closed):
    """A Job of the month and what its document implies."""

    job_id: str
    status: str
    doc_class: str
    number: str
    date: Day
    partner_cui: str | None
    gross: Money
    vat: Money | None = None
    saga_key: str | None = None  # set once SAGA's snapshot shows the posting
    vat_open: Money | None = None  # TVA la încasare: VAT not yet exigible on this document


class ExplainedRule(Closed):
    """An owner-approved explanation for what SAGA holds and no Job brought."""

    rule_id: str
    kind: Literal["document", "line"]
    partner_cui: str | None = None
    doc_class: str | None = None
    number_prefix: str | None = None
    account: str | None = None  # a line rule: a posting with a line on this account


class BucketRow(Closed):
    saga_key: str
    bucket: Literal["expected", "explained_sink_only", "unexplained"]
    job_id: str | None = None
    rule_id: str | None = None
    gross: Money


class ControlRun(Closed):
    control_id: str
    severity: Literal["blocking", "advisory"]
    status: Literal["PASS", "FAIL", "INFO"]
    reason: str


class PeriodDiff(Closed):
    period: str
    close_kind: str | None
    buckets: list[BucketRow]
    outbound_holes: list[str]
    parity: dict[str, dict[str, str]]
    controls: list[ControlRun]
    blockers: list[str]
    hard_failures: int
    material: bool
    can_file: bool
    snapshot_id: str


def _acct(account: str) -> str:
    """The synthetic account of an analytic one: ``401.00001`` → ``401``."""
    return account.split(".", 1)[0]


def _alnum(s: str) -> str:
    return re.sub(r"[^0-9A-Z]", "", s.upper())


def _fits(axes: dict[str, str], require: dict, forbid: dict | None = None) -> bool:
    if any(axes.get(a) not in vs for a, vs in (require or {}).items()):
        return False
    return not any(axes.get(a) in vs for a, vs in (forbid or {}).items())


def close_kind(cat: Catalog, axes: dict[str, str]) -> str | None:
    """The one close kind whose require / forbid fit the period's CO.DiT, else None."""
    fits = [
        k
        for k in cat.ids("CloseKind")
        if _fits(axes, cat.get("CloseKind", k).require, cat.get("CloseKind", k).forbid)
    ]
    return fits[0] if len(fits) == 1 else None


def expected_set_hash(items: list[ExpectedItem]) -> str:
    """The lock of the month's expected set: Job ids, statuses and gross; rejected left out."""
    body = sorted((i.job_id, i.status, i.gross) for i in items if i.status != "rejected")
    return hashlib.sha256(json.dumps(body).encode()).hexdigest()


def _implied(item: ExpectedItem) -> list[tuple[str, Decimal]]:
    """(account, credit − debit) the expected document implies on the watched accounts."""
    g, v = Decimal(item.gross), Decimal(item.vat or "0")
    side = _SIDE.get(item.doc_class)
    if side == "in":
        return [("401", g), ("4426", -v)]
    if side == "out":
        return [("4111", -g), ("4427", v)]
    if item.doc_class == "incasare":
        return [("5121", -g)] + ([("4111", g)] if item.partner_cui else [])
    if item.doc_class == "plata":
        return [("5121", g)] + ([("401", -g)] if item.partner_cui else [])
    return []


def _net(lines: list[JournalLine]) -> dict[str, Decimal]:
    out: dict[str, Decimal] = defaultdict(Decimal)
    for x in lines:
        amount = Decimal(x.amount)
        out[_acct(x.account)] += amount if x.side == "credit" else -amount
    return out


def period_diff(
    cat: Catalog,
    period: str,
    items: list[ExpectedItem],
    w: Witness,
    axes: dict[str, str],
    rules: list[ExplainedRule] = (),
    balances: dict[str, Money] | None = None,
    maps_exist: bool = False,
    open_pre: list[str] = (),
    lock_mismatch: bool = False,
    waiting_parts: list[tuple[str, str]] = (),
) -> PeriodDiff:
    """Layer 1 for one client-month. ``waiting_parts``: (partner CUI, number) of expense-report
    parts that wait for their SPV XML."""
    expected = [i for i in items if i.status != "rejected"]
    docs = [d for d in w.docs if d.date[:7] == period]
    lines = [x for x in w.lines if x.date[:7] == period]

    # ----- buckets -----
    unused = {i.job_id: i for i in expected}
    buckets: list[BucketRow] = []
    for d in docs:
        match = next((i for i in unused.values() if i.saga_key and i.saga_key == d.saga_key), None)
        if match is None:
            match = next(
                (
                    i
                    for i in unused.values()
                    if _SIDE.get(i.doc_class, i.doc_class) == _SIDE.get(d.doc_class, d.doc_class)
                    and _alnum(i.number) == _alnum(d.number)
                    and i.date == d.date
                    and Decimal(i.gross) == Decimal(d.gross)
                ),
                None,
            )
        if match is not None:
            del unused[match.job_id]
            buckets.append(
                BucketRow(
                    saga_key=d.saga_key, bucket="expected", job_id=match.job_id, gross=d.gross
                )
            )
            continue
        rule = next((r for r in rules if r.kind == "document" and _doc_rule(r, d)), None)
        if rule is not None:
            buckets.append(
                BucketRow(
                    saga_key=d.saga_key,
                    bucket="explained_sink_only",
                    rule_id=rule.rule_id,
                    gross=d.gross,
                )
            )
        else:
            buckets.append(BucketRow(saga_key=d.saga_key, bucket="unexplained", gross=d.gross))
    holes = [i.job_id for i in expected if i.status not in _DONE]
    unexplained = [b.saga_key for b in buckets if b.bucket == "unexplained"]

    # ----- explained postings: document rules, then line rules on postings no Job brought -----
    explained_keys = {b.saga_key for b in buckets if b.bucket == "explained_sink_only"}
    job_keys = {b.saga_key for b in buckets if b.bucket == "expected"} | {
        i.saga_key for i in expected if i.saga_key
    }
    line_rules = [r for r in rules if r.kind == "line" and r.account]
    for key in {x.saga_key for x in lines} - job_keys - explained_keys:
        posting = [x for x in lines if x.saga_key == key]
        if any(any(x.account.startswith(r.account) for x in posting) for r in line_rules):
            explained_keys.add(key)
    explained_lines = [x for x in lines if x.saga_key in explained_keys]

    # ----- parity -----
    implied: dict[str, Decimal] = defaultdict(Decimal)
    for i in expected:
        for account, amount in _implied(i):
            implied[account] += amount
    for account, amount in _net(explained_lines).items():
        implied[account] += amount
    sink = _net(lines)

    ctx = _Ctx(
        cat=cat,
        axes=axes,
        implied=implied,
        sink=sink,
        lines=lines,
        holes=holes,
        unexplained=unexplained,
        explained_keys=explained_keys,
        expected=expected,
        balances=balances,
        maps_exist=maps_exist,
        buckets=buckets,
        docs=docs,
        waiting_parts=list(waiting_parts),
    )
    runs: list[ControlRun] = []
    for cid in cat.ids("Control"):
        row = cat.get("Control", cid)
        if row.layer != "close":
            continue
        if not _fits(axes, row.require):
            runs.append(
                ControlRun(
                    control_id=cid, severity=row.severity, status="INFO", reason="does not apply"
                )
            )
            continue
        evaluate = _EVALUATORS.get(cid)
        if evaluate is None:
            status, reason = (
                ("FAIL", "no evaluator for this control")
                if row.severity == "blocking"
                else ("INFO", "no evaluator")
            )
        else:
            status, reason = evaluate(ctx, row)
        runs.append(ControlRun(control_id=cid, severity=row.severity, status=status, reason=reason))

    watched = next(
        (cat.get("Control", c).watched for c in cat.ids("Control") if c == "c0_synthetic_parity"),
        [],
    )
    parity = {
        a: {
            "expected": f"{implied[a]:.2f}",
            "sink": f"{sink[a]:.2f}",
            "delta": f"{implied[a] - sink[a]:.2f}",
        }
        for a in watched
    }

    # ----- blockers and materiality -----
    blockers: list[str] = []
    if period not in w.covered:
        blockers.append(f"need_rj_export: no export of the books covers {period}")
    kind = close_kind(cat, axes)
    if kind is None:
        blockers.append("no close kind fits the period's CO.DiT (tva / exig)")
    if open_pre:
        blockers.append(f"reconcile: {len(open_pre)} document(s) wait on a PRE answer")
    if lock_mismatch:
        blockers.append("lock mismatch: the month's Jobs changed since the lock; reopen first")
    for r in runs:
        if r.status == "FAIL":
            blockers.append(
                f"{r.control_id}{'' if r.severity == 'blocking' else ' (advisory)'}: {r.reason}"
            )
    hard = sum(1 for r in runs if r.status == "FAIL" and r.severity == "blocking")
    material = bool(
        period not in w.covered
        or holes
        or unexplained
        or hard
        or kind is None
        or open_pre
        or lock_mismatch
    )
    snapshot = hashlib.sha256(
        json.dumps(
            [
                period,
                [i.model_dump() for i in items],
                w.model_dump(),
                axes,
                [r.model_dump() for r in rules],
                balances,
                maps_exist,
            ],
            sort_keys=True,
            default=str,
        ).encode()
    ).hexdigest()[:24]
    return PeriodDiff(
        period=period,
        close_kind=kind,
        buckets=buckets,
        outbound_holes=holes,
        parity=parity,
        controls=runs,
        blockers=blockers,
        hard_failures=hard,
        material=material,
        can_file=not material,
        snapshot_id=snapshot,
    )


def _doc_rule(r: ExplainedRule, d: SinkDoc) -> bool:
    return (
        (r.partner_cui is None or r.partner_cui == d.partner_cui)
        and (r.doc_class is None or r.doc_class == d.doc_class)
        and (r.number_prefix is None or d.number.upper().startswith(r.number_prefix.upper()))
        and any(v is not None for v in (r.partner_cui, r.doc_class, r.number_prefix))
    )


class _Ctx:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def _c0(ctx, row):
    eps = Decimal(row.epsilon or "0.01")
    off = [
        f"{a}: {ctx.implied[a] - ctx.sink[a]:+.2f}"
        for a in row.watched
        if abs(ctx.implied[a] - ctx.sink[a]) >= eps
    ]
    return ("FAIL", "; ".join(off)) if off else ("PASS", "the watched accounts tie")


def _c1(ctx, row):
    return (
        ("FAIL", f"outbound holes: {ctx.holes}")
        if ctx.holes
        else ("PASS", "every expected Job is in the books")
    )


def _c2(ctx, row):
    return (
        ("FAIL", f"unexplained: {ctx.unexplained}")
        if ctx.unexplained
        else ("PASS", "nothing unexplained")
    )


def _maps(ctx, row):
    if not ctx.maps_exist:
        return "INFO", "after client maps exist"
    if ctx.balances is None:
        return "FAIL", "cannot be computed: no balanță"
    off = []
    for parent in row.watched:
        analytic = [Decimal(v) for k, v in ctx.balances.items() if k.startswith(parent + ".")]
        if (
            analytic
            and parent in ctx.balances
            and sum(analytic, Decimal(0)) != Decimal(ctx.balances[parent])
        ):
            off.append(parent)
    return ("FAIL", f"analytics do not tie: {off}") if off else ("PASS", "analytics tie")


def _m1_8(ctx, row):
    if ctx.balances is None or "4428" not in ctx.balances:
        return "FAIL", "cannot be computed: no balance of 4428"
    open_vat = sum((Decimal(i.vat_open) for i in ctx.expected if i.vat_open), Decimal(0))
    held = abs(Decimal(ctx.balances["4428"]))
    if abs(open_vat - held) >= Decimal("0.01"):
        return "FAIL", f"open VAT {open_vat} against 4428 {held}"
    return "PASS", "4428 holds the open VAT"


def _lines_on(ctx, accounts):
    return sorted(
        {
            x.saga_key
            for x in ctx.lines
            if _acct(x.account) in accounts and x.saga_key not in ctx.explained_keys
        }
    )


def _on_accounts(ctx, row):
    keys = _lines_on(ctx, set(row.watched))
    return (
        ("FAIL", f"unexplained movement on {row.watched}: {keys}")
        if keys
        else ("PASS", "no unexplained movement")
    )


def _waiting(ctx, row):
    waiting = {(p, _alnum(n)) for p, n in ctx.waiting_parts}
    named = [
        d.saga_key
        for d in ctx.docs
        if d.saga_key in ctx.unexplained and (d.partner_cui, _alnum(d.number)) in waiting
    ]
    return ("FAIL", f"waiting for their SPV XML: {named}") if named else ("PASS", "none waiting")


_EVALUATORS: dict[str, Callable] = {
    "c0_synthetic_parity": _c0,
    "c1_outbound_complete": _c1,
    "c2_unexplained_empty": _c2,
    "m1_1_payables_tie": _maps,
    "m1_1_trade_ext": _maps,
    "m1_2_receivables_tie": _maps,
    "m1_2_trade_ext": _maps,
    "m1_8_4428_open": _m1_8,
    "m1_9_4424_watched": _on_accounts,
    "t_regime_4428": _on_accounts,
    "t_regime_442x": _on_accounts,
    "c2_waiting_for_xml": _waiting,
}


def close_action_refused(diff: PeriodDiff, action: str) -> str | None:
    """The reason ``v2_close`` with this action is refused, or None. ``file`` is refused while
    the month is material (P11)."""
    if action == "file" and diff.material:
        return "cannot file: the month is material (" + "; ".join(diff.blockers[:3]) + ")"
    return None


def weigh_suggestion(diff: PeriodDiff, suggestion: dict | None) -> dict | None:
    """A model's close suggestion, kept only where it may stand: on a material month its
    ``file`` and any reading that the books support the declaration are dropped (P11)."""
    if suggestion is None:
        return None
    if not diff.material:
        return dict(suggestion)
    kept, dropped = dict(suggestion), []
    if kept.get("action") == "file":
        kept["action"] = "hold"
        dropped.append("action: file")
    if kept.get("books_support_declaration"):
        kept["books_support_declaration"] = False
        dropped.append("books_support_declaration")
    kept["dropped"] = dropped
    return kept


def prefile_failures(cat: Catalog, pre_verdict: str | None) -> list[str]:
    """The blocking pre-package controls that fail for a Job about to be packaged."""
    failed = []
    if "p_prefile_duplicate" in cat.ids("Control") and pre_verdict != "absent":
        failed.append(f"p_prefile_duplicate: PRE is {pre_verdict!r}, not 'absent'")
    if failed and "p_prefile_hard_failures" in cat.ids("Control"):
        failed.append(f"p_prefile_hard_failures: {len(failed)} blocking failure(s)")
    return failed
