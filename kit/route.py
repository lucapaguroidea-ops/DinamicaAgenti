"""The router: the next step of an issue, as a function of its stored facts only (P7).

The Dispatcher gathers an issue's facts from the dossier (what the kit wrote, what hanks wrote
after ``kit verify``, what people answered) into a closed ``*Facts`` model and asks ``route``
for the next ``Step``. No model is called here, and nothing that is not a field of the facts can
reach a route: a model's output becomes a fact only after the kit has checked it.

A step is one of: ``kit`` (a deterministic command), ``hank`` (a model step), ``ask`` (a
question issue for its actor), ``wait`` (on another issue or on the import agent), ``hold``
(needs a person; the reason says why) or ``done``. An agent is only ever asked to import, or to
report what SAGA's snapshot shows; Validare, closing a month and restoring a backup are a
person's in SAGA, and a month closed in SAGA gets nothing (P5).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Step(Closed):
    kind: Literal["kit", "hank", "ask", "wait", "hold", "done"]
    name: str
    actor: Literal["person", "saga_agent", "import_agent"] | None = None
    reason: str = ""
    detail: dict = {}


def _kit(name: str, **detail) -> Step:
    return Step(kind="kit", name=name, detail=detail)


def _hank(name: str, **detail) -> Step:
    return Step(kind="hank", name=name, detail=detail)


def _ask(name: str, actor: str = "person", **detail) -> Step:
    return Step(kind="ask", name=name, actor=actor, detail=detail)


def _hold(name: str, reason: str, **detail) -> Step:
    return Step(kind="hold", name=name, actor="person", reason=reason, detail=detail)


def _done(name: str, reason: str = "") -> Step:
    return Step(kind="done", name=name, reason=reason)


# ----- Sorting: batch:{id} -----


class BatchFacts(Closed):
    emit: bool
    failed: list[str]
    question: str | None = None  # define_class | bon_cui_unclear | decont_split
    split: bool = False
    split_answered: bool = False
    children_emitted: bool = False
    job_emitted: bool = False


def route_batch(f: BatchFacts) -> Step:
    if f.split and f.split_answered:
        return _done("split") if f.children_emitted else _kit("emit_children")
    if f.question:
        return _ask(f.question)
    if f.emit:
        return _done("emitted") if f.job_emitted else _kit("emit")
    return _done("not_emitted", f"gates failed: {f.failed}")


# ----- Document path: job:{id} -----


class Verdict(Closed):
    accounts_ok: bool
    risk: Literal["low", "medium", "high", "unknown"]
    needs_human: bool


class JobFacts(Closed):
    job_id: str
    status: str
    has_xml: bool
    extracted: bool = False
    read_runs: int = 0
    read_confirmed: bool | None = None
    candidates: list[str] = []
    bound_articol: str | None = None
    pre_verdict: Literal["absent", "already_posted", "ambiguous", "need_export"] | None = None
    judged: bool = False
    verdict: Verdict | None = None
    policy: Literal["always", "first_n", "never_if_risk_low"] = "always"
    first_n: int | None = None
    packaged_count: int = 0  # Jobs of this articol and client already packaged
    approval: Literal["approve", "reject", "edit"] | None = None
    book_is_saga: bool = False
    mouths_for_class: int = 0
    prefile_failures: list[str] = []
    period_filed: bool = False
    month_closed: bool = False  # the month is closed in SAGA
    packaged: bool = False
    imported: bool = False
    validare: Literal["validated", "not_validated"] | None = None
    intent_ok: bool | None = None
    open_question: str | None = None


_TERMINAL = ("acked", "already_in_sink", "rejected", "failed")


def needs_approval(f: JobFacts) -> bool:
    """The v3_approve gate: a doubtful verdict always asks; else the articol's policy."""
    v = f.verdict
    if v is None or v.needs_human or not v.accounts_ok:
        return True
    if f.policy == "always":
        return True
    if f.policy == "first_n":
        return f.packaged_count < (f.first_n or 0)
    return v.risk != "low"  # never_if_risk_low


def route_job(f: JobFacts) -> Step:
    if f.status in _TERMINAL:
        return _done(f.status)
    if f.open_question:
        return Step(kind="wait", name=f.open_question, reason="a question is open")

    if not f.extracted:
        if f.has_xml:
            return _kit("extract_xml")
        if f.read_runs == 0:
            return _hank("read-document", tier="everyday")
        if f.read_runs == 1 and not f.read_confirmed:
            return _hank("read-document", tier="strong")
        return _done("failed", "the read did not confirm twice: refused, never stored")

    if f.bound_articol is None:
        if len(f.candidates) == 1:
            return _kit("bind", articol=f.candidates[0])
        return _ask("define_articol", candidates=list(f.candidates))

    if f.pre_verdict is None:
        return _kit("pre_check")
    if f.pre_verdict == "already_posted":
        return _done("already_in_sink")
    if f.pre_verdict in ("ambiguous", "need_export"):
        return _hold(
            "needs_human", f"PRE is {f.pre_verdict}: the month's reconcile asks", to="recon"
        )

    if not f.judged:
        return _hank("judge-document")
    if f.approval is None and needs_approval(f) and not f.packaged and f.status != "reopened":
        return _ask("v3_approve")
    if f.approval == "reject":
        return _done("rejected")

    if not f.packaged:
        if f.month_closed:
            return _hold("needs_human", "the month is closed in SAGA: it gets nothing")
        if not f.book_is_saga:
            return _hold("needs_human", "the client's book of record is not SAGA")
        if f.mouths_for_class != 1:
            return _hold("needs_human", f"{f.mouths_for_class} mouths fit the document: not one")
        if f.prefile_failures:
            return _hold("needs_human", "; ".join(f.prefile_failures))
        if f.period_filed:
            return _hold("needs_human", "the period has a filing receipt: no new package")
        return _kit("package")

    if not f.imported:
        return Step(kind="wait", name="saga_import", actor="import_agent", reason="import in SAGA")
    if f.validare is None:
        return _ask("wait_validare", actor="saga_agent")
    if f.validare == "not_validated":
        return _kit("reopen")
    if f.intent_ok is None:
        return _kit("intent_check")
    if f.intent_ok:
        return _done("acked")
    return _hold("needs_human", "SAGA's posting differs from the package")


# ----- Reconcile: recon:{cui}:{period} -----


class ReconFacts(Closed):
    checked: bool = False  # the window was checked against the books as they are now
    to_review: list[str] = []  # decisive verdicts the review has not seen
    missing_months: list[str] = []
    contested: list[str] = []
    ambiguous: list[str] = []  # oldest first
    how_mismatch: list[str] = []


def route_recon(f: ReconFacts) -> Step:
    if not f.checked:
        return _kit("recheck_window")
    if f.to_review:
        return _hank("review-match", job_ids=list(f.to_review))
    if f.missing_months:
        return _ask("need_rj_export", months=list(f.missing_months))
    if f.contested:
        return _ask("recon_review_contest", job_id=f.contested[0])
    if f.ambiguous:
        return _ask("recon_ambiguous", job_id=f.ambiguous[0])
    if f.how_mismatch:
        return _ask("recon_how_mismatch", job_id=f.how_mismatch[0])
    return _done("clear")


# ----- Month close: close:{cui}:{period} -----


class CloseFacts(Closed):
    recon_open: bool = False
    locked: bool = False
    diffed: bool = False
    suggested: bool = False
    v2: Literal["file", "hold", "patch_maps", "reopen"] | None = None
    v4_done: bool = False
    filings_open: list[str] = []


def route_close(f: CloseFacts) -> Step:
    if f.recon_open:
        return Step(
            kind="wait", name="recon", reason="a PRE question is open: never close around it"
        )
    if not f.locked:
        return _kit("lock")
    if not f.diffed:
        return _kit("period_diff")
    if not f.suggested:
        return _hank("close-suggest")
    if f.v2 is None:
        return _ask("v2_close")
    if f.v2 == "hold":
        return _hold("hold", "the person held the month")
    if f.v2 == "reopen":
        return _kit("release_lock")
    if f.v2 == "patch_maps":
        return _hold("patch_maps", "the client's maps are being patched")
    if not f.v4_done:
        return _ask("v4_codit")
    if f.filings_open:
        return _ask("filing_receipt", filing_id=f.filings_open[0])
    return _done("filed")


# ----- The calendar: calendar:{cui}:{period} (WP-21) -----


class CalendarFacts(Closed):
    today: str = ""  # derived on every wake (the UTC date), never stored
    computed_on: str | None = None  # the day the core's calendar was last asked
    catalog_commit: str | None = None  # the PoartaContabila commit whose catalog was read
    freshness: str | None = None  # why the register pin may not date anything, or None
    items: list[dict] = []
    refused: list[dict[str, str]] = []
    later: list[dict[str, str]] = []


def calendar_refusal(f: CalendarFacts) -> str:
    """Every reason the calendar refuses, for the person who holds it (P10)."""
    reasons = [f"register: {f.freshness}"] if f.freshness else []
    reasons += [f"{r['form']} ({r['filing_id']}): {r['reason']}" for r in f.refused]
    return "the calendar refuses: " + "; ".join(reasons)


def route_calendar(f: CalendarFacts) -> Step:
    """Ask the core, hold on any refusal or a register not fresh, else done.

    A partially refused calendar asked again on a later day replaces its dated items too (they are
    recomputed with the rest); that is acceptable because nothing acts on a held calendar.
    """
    if f.computed_on is None:
        return _kit("obligations")
    if f.freshness or f.refused:
        if f.today and f.computed_on != f.today:  # a new day: ask the core again
            return _kit("obligations")
        return _hold("calendar_refuses", calendar_refusal(f))
    later = f", {len(f.later)} later" if f.later else ""
    return _done("dated", f"{len(f.items)} dated{later}")


_ROUTES = {
    "batch": (BatchFacts, route_batch),
    "job": (JobFacts, route_job),
    "recon": (ReconFacts, route_recon),
    "close": (CloseFacts, route_close),
    "calendar": (CalendarFacts, route_calendar),
}


def route(procedure: str, facts: dict) -> Step:
    if procedure not in _ROUTES:
        raise ValueError(f"unknown procedure {procedure!r}: one of {sorted(_ROUTES)}")
    model, fn = _ROUTES[procedure]
    return fn(model.model_validate(facts))
