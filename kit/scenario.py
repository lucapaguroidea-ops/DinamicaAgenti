"""End-to-end scenarios on invented firms: a month's documents through Sorting and the document
path up to the package, then the month's close against the simulated book.

Each step is the router's (``kit.route``); each kit step runs the kit's own function; people's
answers are simulated and go through ``answer_question`` like real ones. Model roles have no
pinned model until D3, so every hank step refuses and the person is asked, as designed (P8).
The package step is WP-10's (the SAGA XML renderer, waiting on R4): a document's walk stops
there. Import and Validare happen in SAGA; here the simulated book stands for what SAGA shows
once they have — a model of SAGA, never proof of it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from kit.bind import candidates
from kit.catalog import Catalog
from kit.hanks import DOUBTFUL, HankRefused, render
from kit.period import ExpectedItem, PeriodDiff, expected_set_hash, period_diff
from kit.questions import answer_question
from kit.recon import Doc, JournalLine, SinkDoc, Witness, pick_profile, pre_check
from kit.route import CloseFacts, JobFacts, Verdict, route_close, route_job
from kit.sorting import Pack, decide, split
from kit.store import Dossier, open_dossier
from kit.synthetic import FIRMS, SUPPLIERS, Firm, GenDoc, booked, month, simulated_book
from kit.ubl import for_client, parse_ubl, read_spv_zip

REPO = Path(__file__).resolve().parents[1]
DEFECTS = ("missing_in_books", "extra_in_books", "cent_off")
PERSON = "Contabil (simulated)"


class ScenarioError(AssertionError):
    """The walk went where the design says it must not."""


@dataclass
class Trail:
    name: str
    job_id: str | None
    articol: str | None = None
    held: bool = False
    steps: list[str] = field(default_factory=list)


@dataclass
class MonthReport:
    firm: str
    period: str
    trails: list[Trail]
    diff: PeriodDiff
    v2: str
    close_steps: list[str]
    answers: int


def _doc_class(our_role: str, storno: bool) -> str:
    base = "intrare" if our_role == "inbound" else "iesire"
    return f"storn_{base}" if storno else base


def _walk_job(cat: Catalog, d: Dossier, firm: Firm, pack: Pack, xml: bytes, trail: Trail) -> None:
    decision = decide(cat, pack)
    if not decision.emit:
        raise ScenarioError(f"{trail.name}: did not emit: {decision.failed}")
    job, _ = d.insert_job(
        pack.client_cui, pack.source_hash, decision.job_kind, pack.source_doc_id, pack.period
    )
    trail.job_id = job.job_id
    ubl = parse_ubl(xml)
    view = for_client(ubl, firm.cui)
    fiscal_class = cat.get("SourceDoc", pack.source_doc_id).fiscal_class
    doc_class = _doc_class(view.our_role, view.is_storno)
    facts = JobFacts(job_id=job.job_id, status="ingested", has_xml=True, book_is_saga=True)

    for _ in range(20):
        s = route_job(facts)
        trail.steps.append(f"{s.kind}:{s.name}")
        upd: dict = {}
        if s.kind == "kit" and s.name == "extract_xml":
            upd = {
                "extracted": True,
                "candidates": candidates(
                    cat,
                    fiscal_class,
                    view.our_role,
                    view.is_storno,
                    firm.axes,
                    ubl.issue_date,
                    allow_draft=True,
                ),
            }
        elif s.kind == "kit" and s.name == "bind":
            art = cat.get("Articol", s.detail["articol"])
            mouths = [m for m in art.mouths if cat.get("Mouth", m).doc_class == doc_class]
            d.set_status(job.job_id, "bound")
            trail.articol = art.id
            upd = {
                "bound_articol": art.id,
                "policy": art.gate.policy,
                "first_n": art.gate.first_n,
                "mouths_for_class": len(mouths),
                "packaged_count": 0,
            }
        elif s.kind == "kit" and s.name == "pre_check":
            d.set_status(job.job_id, "reconcile_pre")
            books_now = Witness(covered=[pack.period])  # nothing imported yet this month
            r = pre_check(
                pick_profile(cat, "pre", fiscal_class),
                Doc(
                    doc_class=doc_class,
                    number=ubl.number,
                    date=ubl.issue_date,
                    partner_cui=view.counterparty_cui,
                    gross=ubl.totals.gross,
                    vat=ubl.totals.vat,
                    period=pack.period,
                ),
                books_now,
            )
            d.put_verdict(job.job_id, "pre", r.snapshot_id, r.verdict, r.model_dump())
            upd = {"pre_verdict": r.verdict}
        elif s.kind == "hank":
            _refuse(cat, d, s.name, f"job:{job.job_id}", trail.steps)
            upd = {
                "judged": True,
                "verdict": Verdict(**DOUBTFUL),
            }  # a refused judge reads as doubtful
        elif s.kind == "ask" and s.name == "v3_approve":
            q = {
                "job_id": job.job_id,
                "document": {"number": ubl.number, "gross": ubl.totals.gross},
            }
            out = answer_question(
                cat,
                d,
                f"job:{job.job_id}",
                "v3_approve",
                q,
                {"decision": "approve"},
                PERSON,
                "person",
            )
            if out.status != "accepted":
                raise ScenarioError(out.error)
            d.set_status(job.job_id, "approved")
            upd = {"approval": "approve"}
        elif s.kind == "kit" and s.name == "package":
            trail.steps.append("stop: the package is WP-10's")
            return
        elif s.kind == "hold":
            d.set_status(job.job_id, "needs_human")
            trail.steps.append(f"held: {s.reason}")
            trail.held = True
            return
        else:
            raise ScenarioError(f"{trail.name}: unexpected step {s.kind}:{s.name} ({s.reason})")
        facts = facts.model_copy(update=upd)
    raise ScenarioError(f"{trail.name}: no end after 20 steps")


def _refuse(cat: Catalog, d: Dossier, hank: str, issue: str, steps: list[str]) -> None:
    """The hank step through the Dispatcher's own gate: no role is pinned until D3, so render
    refuses and nothing runs. A scenario never runs a model."""
    try:
        render(cat, REPO, hank, d.folder / "runs" / issue.replace(":", "_"))
    except HankRefused:
        steps.append("refused: no model pinned (D3)")
        return
    raise ScenarioError(f"{hank} rendered: a scenario runs no model")


def _pack(firm: Firm, period: str, gd: GenDoc, xml: bytes) -> Pack:
    view = for_client(parse_ubl(xml), firm.cui)
    return Pack(
        client_cui=firm.cui,
        period=period,
        source_hash=gd.source_hash,
        source_doc_id=gd.source_doc_id,
        kinds=["ubl_spv"] if gd.source_doc_id == "ro_efactura_ubl" else ["xml"],
        our_role=view.our_role,
        counterparty_cui=view.counterparty_cui,
        identity_ok=True,
        is_storno=view.is_storno,
    )


def _with_defects(firm: Firm, period: str, docs: list[GenDoc], defects: tuple[str, ...]):
    meant = booked(docs)
    missing = meant[0] if "missing_in_books" in defects else None
    w, balances = simulated_book(firm, period, [x for x in meant if x is not missing])
    lines, sink = list(w.lines), list(w.docs)
    if "cent_off" in defects:
        first = sink[0].saga_key
        lines = [
            x.model_copy(update={"amount": f"{Decimal(x.amount) + Decimal('0.01'):.2f}"})
            if x.saga_key == first and x.account in ("401", "628")
            else x
            for x in lines
        ]
    if "extra_in_books" in defects:
        sup = SUPPLIERS[0]
        sink.append(
            SinkDoc(
                saga_key="X-1",
                doc_class="intrare",
                number="FX-999",
                date=f"{period}-25",
                partner_cui=sup.cui,
                gross="50.00",
                validated=True,
            )
        )
        lines += [
            JournalLine(
                saga_key="X-1",
                journal="intrari",
                number="FX-999",
                date=f"{period}-25",
                account=a,
                side=s,
                amount="50.00",
            )
            for a, s in (("401", "credit"), ("628", "debit"))
        ]
    return Witness(covered=w.covered, docs=sink, lines=lines), balances, missing


def run_month(
    cat: Catalog,
    root: Path,
    firm_key: str,
    period: str,
    defects: tuple[str, ...] = (),
    seed: int = 7,
    eu_service: bool = False,
) -> MonthReport:
    unknown = set(defects) - set(DEFECTS)
    if unknown:
        raise ValueError(f"unknown defects {sorted(unknown)}: one of {DEFECTS}")
    firm = FIRMS[firm_key]
    d = open_dossier(root, firm.cui)
    docs = month(firm, period, seed, eu_service=eu_service)
    trails: list[Trail] = []
    jobs: dict[str, str] = {}
    held: set[str] = set()

    for gd in docs:
        if gd.kind == "decont":
            trail = Trail(gd.name, None, steps=["ask:decont_split"])
            container = Pack(
                client_cui=firm.cui,
                period=period,
                source_hash=gd.source_hash,
                source_doc_id="decont_cheltuieli",
                kinds=["xlsx"],
                identity_ok=True,
            )
            if decide(cat, container).question != "decont_split":
                raise ScenarioError("an expense report must ask for its parts")
            answer = {
                "parts": [
                    {
                        "part_hash": p.source_hash,
                        "source_doc_id": p.source_doc_id,
                        "kinds": ["ubl_spv"],
                        "counterparty_cui": p.partner.cui,
                    }
                    for p in gd.parts
                ]
            }
            out = answer_question(
                cat,
                d,
                f"batch:{gd.source_hash[:12]}",
                "decont_split",
                {"pack": container.model_dump()},
                answer,
                PERSON,
                "person",
            )
            if out.status != "accepted":
                raise ScenarioError(out.error)
            trails.append(trail)
            for part, child in zip(gd.parts, split(cat, container, out.answer), strict=True):
                t = Trail(part.name, None)
                _walk_job(cat, d, firm, child, part.data, t)
                jobs[part.number] = t.job_id
                trails.append(t)
            continue
        xml = read_spv_zip(gd.data).invoice if gd.data[:2] == b"PK" else gd.data
        t = Trail(gd.name, None)
        _walk_job(cat, d, firm, _pack(firm, period, gd, xml), xml, t)
        jobs[gd.number] = t.job_id
        if t.held:
            held.add(gd.number)
        trails.append(t)

    w, balances, missing = _with_defects(firm, period, docs, defects)
    incasare = firm.axes["exig"] == "tva_la_incasare"
    items = []
    for gd in booked(docs):
        side = "intrare" if gd.kind in ("purchase", "foreign_purchase") else "iesire"
        status = "acked"
        if gd is missing:
            status = "wait_validare"
        elif gd.number in held:
            status = "needs_human"
        vat_open = None
        if incasare and gd.vat:
            vat_open = f"{(-gd.vat if side == 'intrare' else gd.vat):.2f}"
        items.append(
            ExpectedItem(
                job_id=jobs[gd.number],
                status=status,
                doc_class=side,
                number=gd.number,
                date=gd.date,
                partner_cui=gd.partner.cui if gd.partner else None,
                gross=f"{gd.gross:.2f}",
                vat=f"{gd.vat:.2f}",
                vat_open=vat_open,
            )
        )

    close_steps: list[str] = []
    facts = CloseFacts()
    diff = None
    v2 = ""
    for _ in range(20):
        s = route_close(facts)
        close_steps.append(f"{s.kind}:{s.name}")
        if s.kind == "kit" and s.name == "lock":
            if not d.lock_close(period, expected_set_hash(items)):
                raise ScenarioError("lock mismatch on a fresh dossier")
            facts = facts.model_copy(update={"locked": True})
        elif s.kind == "kit" and s.name == "period_diff":
            diff = period_diff(cat, period, items, w, axes=firm.axes, balances=balances or None)
            facts = facts.model_copy(update={"diffed": True})
        elif s.kind == "hank":
            _refuse(cat, d, s.name, f"close:{firm.cui}:{period}", close_steps)
            facts = facts.model_copy(update={"suggested": True})
        elif s.kind == "ask" and s.name == "v2_close":
            q = {"material": diff.material, "blockers": diff.blockers}
            issue = f"close:{firm.cui}:{period}"
            out = answer_question(
                cat, d, issue, "v2_close", q, {"action": "file"}, PERSON, "person"
            )
            if out.status != "accepted":  # material: file is refused (P11); the person holds
                close_steps.append("asked again: file refused")
                answer_question(
                    cat, d, issue, "v2_close", out.question, {"action": "hold"}, PERSON, "person"
                )
                v2 = "hold"
            else:
                v2 = "file"
            facts = facts.model_copy(update={"v2": v2})
        elif s.kind == "ask" and s.name == "v4_codit":
            answer_question(
                cat,
                d,
                f"close:{firm.cui}:{period}",
                "v4_codit",
                {},
                {"accept": False, "skip": True},
                PERSON,
                "person",
            )
            open_ids = [f for f in cat.ids("Filing") if _fits(firm.axes, cat.get("Filing", f))]
            for fid in open_ids:
                d.open_filing(period, fid)
            facts = facts.model_copy(update={"v4_done": True, "filings_open": open_ids})
        elif s.kind == "ask" and s.name == "filing_receipt":
            fid = s.detail["filing_id"]
            q = {"filing_id": fid, "period": period}
            a = {
                "filing_id": fid,
                "period": period,
                "receipt_key": f"simulated/{fid}.zip",
                "submitted_by": PERSON,
            }
            answer_question(
                cat, d, f"close:{firm.cui}:{period}", "filing_receipt", q, a, PERSON, "person"
            )
            d.file_filing(period, fid, a["receipt_key"], PERSON)
            facts = facts.model_copy(update={"filings_open": facts.filings_open[1:]})
        elif s.kind in ("hold", "done"):
            break
        else:
            raise ScenarioError(f"close: unexpected step {s.kind}:{s.name}")
    answers = d.db.execute("SELECT COUNT(*) FROM answers").fetchone()[0]
    return MonthReport(firm_key, period, trails, diff, v2, close_steps, answers)


def _fits(axes: dict[str, str], row) -> bool:
    if any(axes.get(a) not in vs for a, vs in row.require.items()):
        return False
    return not any(axes.get(a) in vs for a, vs in row.forbid.items())
