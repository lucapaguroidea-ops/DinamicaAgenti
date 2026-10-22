"""A client-month through the Dispatcher from the dossier (WP-18): every kit step an executor,
the questions on cards, the hanks handed to their role agents and run with ``kit hank-run``.

The package step is WP-10's (the SAGA XML renderer, waiting on R4); where a test needs a Job
past it, a stand-in marks it packaged and imported, as SAGA would, and says so."""

import json
import sys
from pathlib import Path

import pytest

from kit.catalog import Catalog, load_catalog
from kit.dispatch import Company, dispatch, finish_hank
from kit.hankrun import run_hank
from kit.hanks import DOUBTFUL
from kit.steps import intake
from kit.store import open_dossier
from kit.synthetic import FIRMS, booked, month, simulated_book

sys.path.insert(0, str(Path(__file__).parent))
from fake_paperclip import Fake  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FIRM = FIRMS["platitor"]
CUI, P = FIRM.cui, "2026-09"
SAGA = "11111111-1111-4111-8111-111111111111"


@pytest.fixture(scope="module")
def cat():
    return load_catalog(ROOT / "catalog")


def pinned(cat: Catalog) -> Catalog:
    rows = {k: dict(v) for k, v in cat.rows.items()}
    for i, rid in enumerate(cat.ids("ModelRole"), 1):
        rows["ModelRole"][rid] = rows["ModelRole"][rid].model_copy(
            update={"model": f"test-model-{i}"}
        )
    return Catalog(rows=rows)


class Month:
    """One client-month: its dossier, a fake Paperclip, and the person and SAGA answering."""

    def __init__(self, cat, tmp_path, books_first=True, firm=FIRM):
        self.cat, self.pc, self.firm = cat, Fake(), firm
        self.d = open_dossier(tmp_path / "dossiers", firm.cui)
        self.d.mark_test_firm()
        self.d.set_codit(P, firm.axes)
        labels = ("batch", "job", "recon", "close", "hank")
        self.co = Company(
            {
                "company": "co",
                f"project:{firm.cui}": "prj",
                "agent:dispatcher": "agt-d",
                "agent:reader": "agt-r",
                "agent:classifier": "agt-c",
                "agent:saga_import": SAGA,
                **{f"label:{n}": f"l-{n}" for n in labels},
            },
            "user-acc",
        )
        self.docs = month(firm, P)
        if books_first:
            self.d.put_export("rj_before", [P], {"covered": [P]})

    def run(self, issue, cat=None):
        return dispatch(cat or self.cat, ROOT, self.d, issue, self.pc, self.co)

    def answer(self, issue, **ans):
        out = []
        for q, v in ans.items():
            if isinstance(v, list):
                out.append({"questionId": q, "optionIds": v})
            else:
                out.append({"questionId": q, "optionIds": [], "otherText": v})
        self.pc.resolve(self.d.paperclip_id(issue), "answered", {"version": 1, "answers": out})

    def card(self, issue):
        return [c for c in self.pc.cards[self.d.paperclip_id(issue)] if c["status"] == "pending"][
            -1
        ]

    def take_in(self) -> list[str]:
        jobs = []
        for gd in self.docs:
            name = gd.name.replace(" ", "_") + (".zip" if gd.data[:2] == b"PK" else ".xml")
            batch, facts = intake(self.cat, self.d, P, name, gd.data)
            assert facts["emit"], facts["failed"]
            assert self.run(batch).steps == ["kit:emit", "done:emitted"]
            jobs.append(self.d.facts(batch)["_job"])
        return jobs

    def saga_stand_in(self, jobs, books_docs=None):
        """What WP-10 and SAGA would do: packaged, imported, and the books exported."""
        for j in jobs:
            for st in ("packaged", "wait_validare"):
                self.d.set_status(j.split(":", 1)[1], st)
            self.d.add_facts(
                j,
                "stand-in",
                "kit",
                {"packaged": True, "imported": True, "status": "wait_validare"},
            )
        w, bal = simulated_book(self.firm, P, booked(books_docs or self.docs))
        self.d.put_export("rj_after", [P], {**w.model_dump(), "balances": bal})
        return {x.number: x.saga_key for x in w.docs}


@pytest.mark.law("P9", "P12")
def test_a_month_from_intake_to_its_filings(cat, tmp_path):
    m = Month(cat, tmp_path)
    jobs = m.take_in()
    assert len(jobs) == 6
    for j in jobs:
        first = m.run(j)
        assert first.steps == [
            "kit:extract_xml",
            "kit:bind",
            "kit:pre_check",
            "hank:judge-document",
            "ask:v3_approve",
        ]
        f = m.d.facts(j)
        assert f["pre_verdict"] == "absent" and f["verdict"] == DOUBTFUL
        m.answer(j, decision=["approve"])
        held = m.run(j)
        assert held.ended.startswith("hold: kit step package: the package is WP-10's")
        assert m.d.job(f["job_id"]).status == "approved"

    keys = m.saga_stand_in(jobs)
    for j in jobs:
        ask = m.run(j)
        assert ask.ended == "ask:wait_validare"
        assert m.card(j)["addresseeAgentId"] == SAGA
        m.answer(j, validated=["true"], saga_doc_key=keys[m.d.facts(j)["_doc"]["number"]])
        assert m.run(j).steps == ["answered:wait_validare", "kit:intent_check", "done:acked"]

    close = f"close:{CUI}:{P}"
    assert m.run(close).steps == [
        "kit:lock",
        "kit:period_diff",
        "hank:close-suggest",
        "ask:v2_close",
    ]
    assert m.d.facts(close)["_diff"]["material"] is False
    m.answer(close, action=["file"])
    assert m.run(close).ended == "ask:v4_codit"
    m.answer(close, accept=["true"], skip=["false"], seed_next='{"impozit": "micro_1"}')
    t = m.run(close)
    assert m.d.codit("2026-10") == {**FIRM.axes, "impozit": "micro_1"}
    while t.ended == "ask:filing_receipt":
        fid = json.loads(
            m.card(close)["payload"]["questionSet"]["description"]
            .split("```json\n")[1]
            .split("\n```")[0]
        )["filing_id"]
        m.answer(close, filing_id=fid, period=P, receipt_key=f"r/{fid}.zip", submitted_by="C")
        t = m.run(close)
    assert t.ended == "done:filed" and m.d.period_filed(P)
    assert m.pc.issues[m.d.paperclip_id(close)]["status"] == "done"

    cards = sum(len(v) for v in m.pc.cards.values())
    facts = m.d.db.execute("SELECT COUNT(*) FROM issue_facts").fetchone()[0]
    for issue in [*jobs, close]:  # a replay of every wake adds nothing
        m.run(issue)
    assert sum(len(v) for v in m.pc.cards.values()) == cards
    assert m.d.db.execute("SELECT COUNT(*) FROM issue_facts").fetchone()[0] == facts


@pytest.mark.law("P11")
def test_a_document_missing_from_the_books_keeps_the_month_open(cat, tmp_path):
    m = Month(cat, tmp_path)
    jobs = m.take_in()
    for j in jobs:
        m.run(j)
        m.answer(j, decision=["approve"])
        m.run(j)
    keys = m.saga_stand_in(jobs, books_docs=m.docs[1:])  # SAGA never booked the first one
    for j in jobs:
        m.run(j)
        number = m.d.facts(j)["_doc"]["number"]
        m.answer(
            j,
            validated=["true" if number in keys else "false"],
            **({"saga_doc_key": keys[number]} if number in keys else {}),
        )
        m.run(j)
    close = f"close:{CUI}:{P}"
    m.run(close)
    diff = m.d.facts(close)["_diff"]
    assert diff["material"] and any(b.startswith("c1_outbound_complete") for b in diff["blockers"])
    m.answer(close, action=["file"])
    again = m.run(close)
    assert "cannot file" in again.steps[0] and again.ended == "ask:v2_close"


def test_no_books_yet_sends_the_job_to_reconcile_and_back(cat, tmp_path):
    m = Month(cat, tmp_path, books_first=False)
    job = m.take_in()[0]
    held = m.run(job)
    assert held.steps[-1] == "hold:needs_human" and m.d.facts(job)["pre_verdict"] == "need_export"
    recon = f"recon:{CUI}:{P}"
    assert m.d.paperclip_id(recon), "the month's Reconcile is opened"
    assert m.run(recon).steps == ["kit:recheck_window", "ask:need_rj_export"]
    m.d.put_export("rj_1", [P], {"covered": [P]})
    m.answer(recon, export_id="rj_1")
    t = m.run(recon)
    assert t.steps == [
        "answered:need_rj_export",
        "kit:recheck_window",
        "hank:review-match",
        "ask:recon_review_contest",
    ]
    assert m.d.facts(recon)["contested"] == [job.split(":", 1)[1]]  # refused review: a person
    m.answer(recon, action=["override_absent"])
    done = m.run(recon)
    assert done.steps == ["answered:recon_review_contest", "done:clear"]
    jid = m.d.paperclip_id(job)
    assert m.pc.issues[jid]["assigneeAgentId"] == "agt-d"  # the Job goes back to the Dispatcher
    assert m.run(job).steps[:2] == ["hank:judge-document", "ask:v3_approve"]


# ----- kit hank-run -----


def fake_runtime(outputs: dict[str, object], code: int = 0):
    """Stands for the runtime: writes each codon's file where --output points."""
    seen = {}

    def run(argv, cwd):
        seen["argv"] = argv
        out = Path(argv[argv.index("--output") + 1])
        seen["input"] = json.loads((Path(argv[3]) / "input.json").read_text())
        for name, body in outputs.items():
            target = out / "out" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body if isinstance(body, str) else json.dumps(body))
        return code

    run.seen = seen
    return run


@pytest.mark.law("P8")
def test_a_pinned_judge_runs_on_its_own_issue_and_its_verified_answer_comes_back(cat, tmp_path):
    m = Month(cat, tmp_path)
    job = m.take_in()[0]
    pcat = pinned(cat)
    t = m.run(job, pcat)
    assert t.steps[-1] == "hank:judge-document"
    hank = f"hank:judge-document:{job}"
    assert t.ended == f"wait:{hank}"
    hid, jid = m.d.paperclip_id(hank), m.d.paperclip_id(job)
    assert m.pc.issues[hid]["assigneeAgentId"] == "agt-c" and m.pc.issues[hid]["parentId"] == jid
    assert m.pc.issues[jid]["status"] == "blocked" and m.pc.issues[jid]["blockedByIssueIds"] == [
        hid
    ]
    assert m.run(job, pcat).ended == f"wait:{hank}"  # nothing twice while it runs

    rt = fake_runtime(
        {
            "verdict.json": {"accounts_ok": True, "risk": "low", "needs_human": False},
            "explain.json": {
                "explanation": "Factură de achiziție, conturi uzuale.",
                "facts_cited": ["document.gross"],
                "missing": [],
            },
        }
    )
    run = run_hank(pcat, ROOT, m.d, "judge-document", job, runner=rt)
    assert run.ran and all(v.ok for v in run.verified.values())
    assert rt.seen["argv"][:2] == ["bunx", "hankweave@0.12.0"]
    assert rt.seen["input"]["job_id"] == m.d.facts(job)["job_id"]
    finish_hank(m.d, m.pc, m.co, job, "judge-document", "hank:judge-document:1", run.fields)
    assert m.pc.issues[hid]["status"] == "done" and m.pc.issues[jid]["blockedByIssueIds"] == []
    assert m.d.facts(job)["verdict"]["risk"] == "low"
    asked = m.run(job, pcat)
    assert asked.ended == "ask:v3_approve"  # first_n: the first five of an articol are asked
    assert "conturi uzuale" in m.card(job)["payload"]["questionSet"]["description"]

    again = run_hank(pcat, ROOT, m.d, "judge-document", job, runner=fake_runtime({}))
    assert not again.ran and again.fields["verdict"]["risk"] == "low"  # cached: nothing ran


@pytest.mark.law("P8")
def test_a_bad_or_failed_run_reads_the_cautious_way(cat, tmp_path):
    m = Month(cat, tmp_path)
    job = m.take_in()[0]
    pcat = pinned(cat)
    m.run(job, pcat)
    bad = fake_runtime({"verdict.json": {"accounts_ok": True, "risk": "low"}})  # a field missing
    run = run_hank(pcat, ROOT, m.d, "judge-document", job, runner=bad)
    assert not run.verified["judge"].ok and run.fields["verdict"] == DOUBTFUL
    m2 = Month(cat, tmp_path / "b")
    job2 = m2.take_in()[0]
    m2.run(job2, pcat)
    good = {"accounts_ok": True, "risk": "low", "needs_human": False}
    failed = run_hank(
        pcat,
        ROOT,
        m2.d,
        "judge-document",
        job2,
        runner=fake_runtime({"verdict.json": good}, code=1),
    )
    assert failed.fields["verdict"] == DOUBTFUL
    assert "the runtime exited 1" in failed.verified["judge"].problems[0]


def test_a_read_of_a_scan_becomes_the_document(cat, tmp_path):
    m = Month(cat, tmp_path)
    batch, _ = intake(cat, m.d, P, "scan.pdf", b"%PDF-1.4 invented scan")
    job, _ = m.d.insert_job(
        CUI, m.d.facts(batch)["_pack"]["source_hash"], "ro_efactura", "ro_efactura_pdf", P
    )
    issue = f"job:{job.job_id}"
    m.d.add_facts(
        issue,
        "seed",
        "kit",
        {
            "job_id": job.job_id,
            "status": "ingested",
            "has_xml": False,
            "book_is_saga": True,
            "_source_hash": job.source_hash,
            "_period": P,
            "_source_doc_id": "ro_efactura_pdf",
        },
    )
    read = {
        "doc_type": "invoice",
        "statement": None,
        "invoice": {
            "number": "FS-7",
            "date": "2026-09-08",
            "seller_cui": "69314710",
            "buyer_cui": CUI,
            "currency": "RON",
            "net": "100.00",
            "vat": "21.00",
            "gross": "121.00",
        },
    }
    rt = fake_runtime({"read.json": read})
    run = run_hank(pinned(cat), ROOT, m.d, "read-document", issue, runner=rt)
    assert rt.seen["input"] == {"client_cui": CUI, "expected": "invoice", "files": ["scan.pdf"]}
    f = run.fields
    assert f["read_confirmed"] and f["extracted"] and f["_doc"]["gross"] == "121.00"
    assert f["_doc_class"] == "intrare" and f["candidates"] == ["ro_efactura_inbound"]
    off = {**read, "invoice": {**read["invoice"], "gross": "121.01"}}
    m2 = Month(cat, tmp_path / "b")
    b2, _ = intake(cat, m2.d, P, "scan.pdf", b"%PDF-1.4 invented scan")
    j2, _ = m2.d.insert_job(
        CUI, m2.d.facts(b2)["_pack"]["source_hash"], "ro_efactura", "ro_efactura_pdf", P
    )
    i2 = f"job:{j2.job_id}"
    m2.d.add_facts(
        i2,
        "seed",
        "kit",
        {
            "job_id": j2.job_id,
            "status": "ingested",
            "has_xml": False,
            "book_is_saga": True,
            "_source_hash": j2.source_hash,
            "_period": P,
            "_source_doc_id": "ro_efactura_pdf",
        },
    )
    unconfirmed = run_hank(
        pinned(cat), ROOT, m2.d, "read-document", i2, runner=fake_runtime({"read.json": off})
    )
    assert unconfirmed.fields == {"read_runs": 1, "read_confirmed": False}


# ----- the month's Reconcile over acked Jobs (POST) -----


def acked_month(m: Month) -> list[str]:
    """Every e-invoice of the month approved, imported and acked with its bound articol."""
    jobs = m.take_in()
    for j in jobs:
        assert m.run(j).ended == "ask:v3_approve"
        m.answer(j, decision=["approve"])
        m.run(j)
    keys = m.saga_stand_in(jobs)
    for j in jobs:
        assert m.run(j).ended == "ask:wait_validare"
        m.answer(j, validated=["true"], saga_doc_key=keys[m.d.facts(j)["_doc"]["number"]])
        assert m.run(j).ended == "done:acked"
        assert m.d.facts(j)["bound_articol"]
    return jobs


def spy_post(monkeypatch) -> list[str]:
    import kit.steps

    seen: list[str] = []
    real = kit.steps.post_check

    def spy(profile, *args):
        seen.append(getattr(profile, "id", None))
        return real(profile, *args)

    monkeypatch.setattr(kit.steps, "post_check", spy)
    return seen


@pytest.mark.parametrize("firm_key", ["platitor", "incasare"])
def test_the_months_reconcile_checks_acked_jobs_on_the_close_kinds_post_profile(
    cat, tmp_path, monkeypatch, firm_key
):
    firm = FIRMS[firm_key]
    m = Month(cat, tmp_path, firm=firm)
    jobs = acked_month(m)
    seen = spy_post(monkeypatch)
    recon = f"recon:{firm.cui}:{P}"
    t = m.run(recon)
    assert t.steps[0] == "kit:recheck_window" and not t.ended.startswith("hold")
    assert m.d.facts(recon)["checked"] is True
    kinds = {"platitor": "close_standard", "incasare": "close_tva_incasare"}
    expected = cat.get("CloseKind", kinds[firm_key]).recon_profile
    assert seen == [expected] * len(jobs)


@pytest.mark.law("P10")
def test_no_close_kind_for_the_period_holds_the_reconcile_never_guesses_a_profile(
    cat, tmp_path, monkeypatch
):
    m = Month(cat, tmp_path)
    acked_month(m)
    seen = spy_post(monkeypatch)
    rows = {k: dict(v) for k, v in cat.rows.items()}
    rows["CloseKind"] = {}
    t = m.run(f"recon:{CUI}:{P}", cat=Catalog(rows=rows))
    assert t.ended.startswith("hold") and "close kind" in t.ended
    assert seen == []
