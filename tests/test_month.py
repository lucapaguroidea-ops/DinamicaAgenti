"""A client-month through the Dispatcher from the dossier (WP-18): every kit step an executor,
the questions on cards, the hanks handed to their role agents and run with ``kit hank-run``.

The package step is WP-10's (the SAGA XML renderer, waiting on R4); where a test needs a Job
past it, a stand-in marks it packaged and imported, as SAGA would, and says so."""

import json
import re
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from kit.catalog import Catalog, load_catalog
from kit.cli import main
from kit.dispatch import Company, answer_hank, dispatch, ensure_issue, finish_hank, refuse_held
from kit.hankrun import prepare, run_hank
from kit.hanks import DOUBTFUL, HankHeld, card_hash, input_hash
from kit.steps import intake
from kit.store import open_dossier
from kit.synthetic import (
    FIRMS,
    SUPPLIERS,
    booked,
    month,
    simulated_book,
    spv_zip,
    ubl_invoice,
)

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

    def __init__(self, cat, tmp_path, books_first=True, firm=FIRM, test_firm=True):
        self.cat, self.pc, self.firm = cat, Fake(), firm
        self.d = open_dossier(tmp_path / "dossiers", firm.cui)
        if test_firm:
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
    assert again.fields["_answer_sources"] == run.fields["_answer_sources"]  # the run it read
    for codon, role_id in (("judge", "judge_document"), ("explain", "explain_approve")):
        role = pcat.get("ModelRole", role_id)
        row = m.d.model_answer(role_id, input_hash(rt.seen["input"]), card_hash(ROOT, role))
        assert row.source == "model" and row.operator is None
        assert row.model == role.model  # the pin it ran with, read from the catalog
        assert row.run and (m.d.folder / row.run).is_dir()
        assert again.sources[codon] == run.sources[codon] == {"source": "model", "by": role.model}
        assert again.fields["_answer_sources"][role_id] == {
            "source": "model",
            "model": role.model,
            "run": row.run,
        }


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


def scan_issue(m: Month) -> str:
    """A scanned invoice with no XML: its Job's issue, waiting for a read."""
    batch, _ = intake(m.cat, m.d, P, "scan.pdf", b"%PDF-1.4 invented scan")
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
    return issue


READ = {
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


def test_a_read_of_a_scan_becomes_the_document(cat, tmp_path):
    m = Month(cat, tmp_path)
    issue = scan_issue(m)
    read = READ
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


def operator_read(m: Month, tmp_path: Path, operator: str = "op-ana") -> dict:
    """``kit verify --dossiers`` on a read an operator wrote by hand, for the input
    ``kit hank-run`` would prepare for the scan (the cache key is reproducible)."""
    inp = {"client_cui": m.d.client_cui, "expected": "invoice", "files": ["scan.pdf"]}
    (tmp_path / "input.json").write_text(json.dumps(inp))
    (tmp_path / "read.json").write_text(json.dumps(READ))
    argv = ["verify", "--role", "reader_document", "--input", str(tmp_path / "input.json")]
    argv += ["--output", str(tmp_path / "read.json"), "--operator", operator]
    argv += ["--dossiers", str(m.d.folder.parent), "--cui", m.d.client_cui]
    assert main([*argv, "--root", str(ROOT), "--catalog", str(ROOT / "catalog")]) == 0
    return inp


def never_runs(argv, cwd):
    raise AssertionError("the runtime ran")


@pytest.mark.law("P8")
@pytest.mark.law("P12")
def test_an_operators_read_never_stands_in_for_a_model_run_on_a_real_dossier(cat, tmp_path, capsys):
    m = Month(cat, tmp_path, test_firm=False)
    issue = scan_issue(m)
    inp = operator_read(m, tmp_path)
    assert json.loads(capsys.readouterr().out)["stored"] is True
    role = cat.get("ModelRole", "reader_document")
    row = m.d.model_answer(role.id, input_hash(inp), card_hash(ROOT, role))
    assert (row.source, row.operator, row.model) == ("operator", "op-ana", None)
    with pytest.raises(HankHeld, match="op-ana") as held:
        run_hank(cat, ROOT, m.d, "read-document", issue, runner=never_runs)
    assert held.value.roles == ["reader_document"]
    hank = f"hank:read-document:{issue}"
    ensure_issue(m.d, m.pc, m.co, issue)
    hid = ensure_issue(m.d, m.pc, m.co, hank, parent=issue, assignee="agent:reader")
    refuse_held(m.d, m.pc, m.co, issue, "read-document", held.value)
    f = m.d.facts(issue)
    assert "_doc" not in f and "extracted" not in f and "candidates" not in f
    assert "op-ana" in f["_hank_held"]["reason"] and f["_hank_held"]["hank"] == "read-document"
    assert f["read_runs"] == 1 and f["read_confirmed"] is False and f["_hank"] is None
    jid = m.d.paperclip_id(issue)
    assert m.pc.issues[hid]["status"] == "done"  # the hank refused: the work issue moves on
    assert m.pc.issues[jid]["assigneeAgentId"] == "agt-d"
    assert m.pc.issues[jid]["blockedByIssueIds"] == []
    assert m.d.jobs(P)[0].status == "ingested"  # no Job result from it
    assert m.run(issue).ended == "done:failed"  # unpinned here: the strong read refuses too
    assert "_doc" not in m.d.facts(issue) and not m.d.facts(issue).get("candidates")
    row = m.d.model_answer(role.id, input_hash(inp), card_hash(ROOT, role))
    assert (row.source, row.operator) == ("operator", "op-ana")  # kept, never superseded


SCAN_INPUT = {"client_cui": CUI, "expected": "invoice", "files": ["scan.pdf"]}


def legacy_rows(m: Month, rows: list[tuple[str, str, str, dict]]) -> None:
    """A store migrated from before provenance: the columns added, no CHECK, and answers
    written then, with no recorded source."""
    m.d.db.executescript(
        "DROP TABLE model_answers;"
        "CREATE TABLE model_answers (client_cui TEXT NOT NULL, role_id TEXT NOT NULL,"
        " input_hash TEXT NOT NULL, card_hash TEXT NOT NULL, body TEXT NOT NULL,"
        " at TEXT NOT NULL, source TEXT, model TEXT, operator TEXT, run TEXT,"
        " PRIMARY KEY (role_id, input_hash, card_hash));"
    )
    with m.d.db:
        for role_id, ih, ch, body in rows:
            m.d.db.execute(
                "INSERT INTO model_answers (client_cui, role_id, input_hash, card_hash, body, at)"
                " VALUES (?, ?, ?, ?, ?, '2026-10-01T00:00:00+00:00')",
                (CUI, role_id, ih, ch, json.dumps(body)),
            )


@pytest.mark.law("P8")
@pytest.mark.law("P12")
@pytest.mark.parametrize("cached", ["operator_on_a_real_dossier", "no_source_on_a_test_firm"])
def test_a_held_read_moves_on_to_the_strong_tier(cat, tmp_path, cached):
    m = Month(cat, tmp_path, test_firm=cached != "operator_on_a_real_dossier")
    pcat = pinned(cat)
    issue = scan_issue(m)
    hank = f"hank:read-document:{issue}"
    assert m.run(issue, pcat).ended == f"wait:{hank}"
    role = pcat.get("ModelRole", "reader_document")
    key = (role.id, input_hash(SCAN_INPUT), card_hash(ROOT, role))
    if cached == "operator_on_a_real_dossier":
        m.d.put_model_answer(*key, READ, operator="op-ana")
    else:
        legacy_rows(m, [(*key, READ)])
    with pytest.raises(HankHeld) as held:
        run_hank(pcat, ROOT, m.d, "read-document", issue, runner=never_runs)
    refuse_held(m.d, m.pc, m.co, issue, "read-document", held.value)
    f = m.d.facts(issue)
    assert "_doc" not in f and not f.get("candidates") and f["_hank_held"]["roles"] == [role.id]
    assert m.run(issue, pcat).ended == f"wait:{hank}"  # the route goes on: the strong tier
    assert m.d.facts(issue)["_hank"]["tier"] == "strong"
    hid = m.d.paperclip_id(hank)
    assert m.pc.issues[hid]["status"] == "todo" and m.pc.issues[hid]["assigneeAgentId"] == "agt-r"
    rt = fake_runtime({"read.json": READ})
    run = run_hank(pcat, ROOT, m.d, "read-document", issue, runner=rt, tier="strong")
    assert run.ran and run.fields["read_confirmed"]
    strong = pcat.get("ModelRole", "reader_document_strong")
    assert run.sources == {"read": {"source": "model", "by": strong.model}}
    assert run.fields["_answer_sources"] == {
        strong.id: {"source": "model", "model": strong.model, "run": run.runs["read"]}
    }  # the strong run's, never the held answer's
    assert m.d.model_answer(*key).source == (
        "operator" if cached == "operator_on_a_real_dossier" else None
    )  # the held row stands as it was; the strong run is its own key


@pytest.mark.law("P8")
def test_a_held_judge_reads_doubtful_and_asks_a_person(cat, tmp_path):
    m = Month(cat, tmp_path)
    pcat = pinned(cat)
    job = m.take_in()[0]
    assert m.run(job, pcat).ended == f"wait:hank:judge-document:{job}"
    inp, _ = prepare(pcat, m.d, "judge-document", job, m.d.facts(job))
    role = pcat.get("ModelRole", "judge_document")
    good = {"accounts_ok": True, "risk": "low", "needs_human": False}
    legacy_rows(m, [(role.id, input_hash(inp), card_hash(ROOT, role), good)])
    with pytest.raises(HankHeld, match="no recorded source") as held:
        run_hank(pcat, ROOT, m.d, "judge-document", job, runner=never_runs)
    refuse_held(m.d, m.pc, m.co, job, "judge-document", held.value)
    assert m.d.facts(job)["verdict"] == DOUBTFUL
    assert m.run(job, pcat).ended == "ask:v3_approve"  # a person is asked, on a card
    assert m.card(job)["status"] == "pending"


@pytest.mark.law("P9")
def test_a_partial_cache_hit_never_mixes_two_runs(cat, tmp_path):
    m = Month(cat, tmp_path)
    pcat = pinned(cat)
    job = m.take_in()[0]
    m.run(job, pcat)
    inp, _ = prepare(pcat, m.d, "judge-document", job, m.d.facts(job))
    judge = pcat.get("ModelRole", "judge_document")
    old = {"accounts_ok": True, "risk": "low", "needs_human": False}
    key = (judge.id, input_hash(inp), card_hash(ROOT, judge))
    m.d.put_model_answer(*key, old, model=judge.model, run="runs/old")
    fresh = {"accounts_ok": True, "risk": "medium", "needs_human": False}
    explain = {"explanation": "Risc mediu.", "facts_cited": ["document.gross"], "missing": []}
    outputs = {"verdict.json": fresh, "explain.json": explain}
    run = run_hank(pcat, ROOT, m.d, "judge-document", job, runner=fake_runtime(outputs))
    assert run.ran and run.fields["verdict"] == fresh  # the verdict the explanation read
    assert m.d.model_answer(*key).body == old  # the stored one is never replaced
    explain_role = pcat.get("ModelRole", "explain_approve")
    ekey = (explain_role.id, input_hash(inp), card_hash(ROOT, explain_role))
    assert m.d.model_answer(*ekey).run != "runs/old"
    again = run_hank(pcat, ROOT, m.d, "judge-document", job, runner=fake_runtime(outputs))
    assert again.ran and again.fields["verdict"] == fresh  # two runs' rows: never one hit


@pytest.mark.law("P9")
def test_a_run_stores_its_answers_together_or_not_at_all(cat, tmp_path):
    m = Month(cat, tmp_path)
    pcat = pinned(cat)
    job = m.take_in()[0]
    m.run(job, pcat)
    verdict = {"accounts_ok": True, "risk": "low", "needs_human": False}
    first = run_hank(
        pcat, ROOT, m.d, "judge-document", job, runner=fake_runtime({"verdict.json": verdict})
    )
    assert first.ran and first.verified["judge"].ok and not first.verified["explain"].ok
    judge = pcat.get("ModelRole", "judge_document")
    inp, _ = prepare(pcat, m.d, "judge-document", job, m.d.facts(job))
    assert m.d.model_answer(judge.id, input_hash(inp), card_hash(ROOT, judge)) is None
    explain = {"explanation": "Uzual.", "facts_cited": ["document.gross"], "missing": []}
    rt = fake_runtime({"verdict.json": verdict, "explain.json": explain})
    second = run_hank(pcat, ROOT, m.d, "judge-document", job, runner=rt)  # its own run directory
    assert second.ran and all(v.ok for v in second.verified.values())
    third = run_hank(pcat, ROOT, m.d, "judge-document", job, runner=never_runs)
    assert not third.ran and third.fields["verdict"] == verdict


@pytest.mark.law("P12")
def test_a_partly_passing_run_names_the_model_and_run_behind_its_facts(cat, tmp_path):
    m = Month(cat, tmp_path)
    pcat = pinned(cat)
    job = m.take_in()[0]
    m.run(job, pcat)
    verdict = {"accounts_ok": True, "risk": "low", "needs_human": False}
    run = run_hank(
        pcat, ROOT, m.d, "judge-document", job, runner=fake_runtime({"verdict.json": verdict})
    )
    assert run.verified["judge"].ok and not run.verified["explain"].ok
    assert run.fields["verdict"] == verdict  # the passing verdict is a fact, its answer unstored
    judge = pcat.get("ModelRole", "judge_document")
    sources = run.fields["_answer_sources"]
    assert list(sources) == [judge.id]  # the failed explanation gives no fact, so no source
    assert sources[judge.id]["source"] == "model" and sources[judge.id]["model"] == judge.model
    where = sources[judge.id]["run"]
    assert (m.d.folder / where / "out").is_dir()
    second = run_hank(
        pcat, ROOT, m.d, "judge-document", job, runner=fake_runtime({"verdict.json": verdict})
    )
    assert second.fields["_answer_sources"][judge.id]["run"] == f"{where}-2"  # its own run


@pytest.mark.law("P8")
@pytest.mark.law("P12")
def test_on_a_test_firm_an_operators_read_is_used_and_says_whose_it_is(cat, tmp_path):
    m = Month(cat, tmp_path)
    issue = scan_issue(m)
    operator_read(m, tmp_path)
    run = run_hank(cat, ROOT, m.d, "read-document", issue, runner=never_runs)
    assert not run.ran and run.fields["_doc"]["gross"] == "121.00"
    assert run.sources == {"read": {"source": "operator", "by": "op-ana"}}
    assert run.fields["_answer_sources"] == {
        "reader_document": {"source": "operator", "by": "op-ana"}
    }


def facts_rows(m: Month, issue: str, prefix: str) -> list[str]:
    rows = m.d.db.execute("SELECT key FROM issue_facts WHERE issue = ?", (issue,)).fetchall()
    return [k for (k,) in rows if k.startswith(prefix)]


@pytest.mark.law("P9")
@pytest.mark.parametrize("read", ["confirmed", "not_confirmed"])
def test_a_replayed_hank_run_writes_its_facts_once(cat, tmp_path, read):
    m = Month(cat, tmp_path)
    pcat = pinned(cat)
    issue = scan_issue(m)
    hank = f"hank:read-document:{issue}"
    assert m.run(issue, pcat).ended == f"wait:{hank}"
    body = READ if read == "confirmed" else {"doc_type": "invoice"}  # the second fails verify
    first = answer_hank(
        pcat, ROOT, m.d, m.pc, m.co, "read-document", issue, fake_runtime({"read.json": body})
    )
    assert first is not None and first.ran
    assert answer_hank(pcat, ROOT, m.d, m.pc, m.co, "read-document", issue, never_runs) is None
    assert facts_rows(m, issue, "hank:read-document:") == [first.key]
    f = m.d.facts(issue)
    assert f["read_runs"] == 1 and f["_hank"] is None
    assert f["read_confirmed"] is (read == "confirmed")
    assert m.pc.issues[m.d.paperclip_id(hank)]["status"] == "done"
    assert m.pc.issues[m.d.paperclip_id(issue)]["blockedByIssueIds"] == []


@pytest.mark.law("P9")
@pytest.mark.law("P8")
def test_a_replayed_held_hank_run_writes_its_refusal_once(cat, tmp_path):
    m = Month(cat, tmp_path, test_firm=False)
    pcat = pinned(cat)
    issue = scan_issue(m)
    assert m.run(issue, pcat).ended == f"wait:hank:read-document:{issue}"
    role = pcat.get("ModelRole", "reader_document")
    key = (role.id, input_hash(SCAN_INPUT), card_hash(ROOT, role))
    m.d.put_model_answer(*key, READ, operator="op-ana")
    with pytest.raises(HankHeld):
        answer_hank(pcat, ROOT, m.d, m.pc, m.co, "read-document", issue, never_runs)
    assert answer_hank(pcat, ROOT, m.d, m.pc, m.co, "read-document", issue, never_runs) is None
    assert len(facts_rows(m, issue, "held:read-document:")) == 1
    assert not facts_rows(m, issue, "hank:")
    f = m.d.facts(issue)
    assert f["read_runs"] == 1 and f["read_confirmed"] is False and f["_hank"] is None


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


# ----- intake: whose invoice it is, and whether it is from abroad (P13) -----

DE_SELLER = ("DE999999999", "LIEFERANT EINS GMBH")  # invented foreign VAT ids
DE_BUYER = ("DE888888888", "KAEUFER ZWEI GMBH")
RO_OTHER = (f"RO{SUPPLIERS[0].cui}", SUPPLIERS[0].name)  # another RO firm, a valid CUI
PERSON = (None, "ION EXEMPLU")  # a person: no tax id


def _party(tag: str, who: tuple[str | None, str], country: str | None) -> str:
    vat, name = who
    address = (
        f"<cac:PostalAddress><cac:Country><cbc:IdentificationCode>{country}"
        "</cbc:IdentificationCode></cac:Country></cac:PostalAddress>"
        if country
        else ""
    )
    tax = (
        f"<cac:PartyTaxScheme><cbc:CompanyID>{vat}</cbc:CompanyID>"
        "<cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme></cac:PartyTaxScheme>"
        if vat
        else ""
    )
    legal = f"<cac:PartyLegalEntity><cbc:RegistrationName>{name}</cbc:RegistrationName>"
    legal += f"<cbc:CompanyID>{vat[2:]}</cbc:CompanyID>" if vat and vat[:2] == "RO" else ""
    legal += "</cac:PartyLegalEntity>"
    return f"<cac:{tag}><cac:Party>{address}{tax}{legal}</cac:Party></cac:{tag}>"


CLIENT = (f"RO{CUI}", FIRM.name)


def invoice(seller, s_country, buyer, b_country, number="X-1") -> bytes:
    """An invented invoice between any two parties, each with its country or none."""
    xml = ubl_invoice(FIRM, SUPPLIERS[0], number, f"{P}-05", Decimal("100.00"), Decimal(0), "K")
    xml = re.sub(
        rb"<cac:AccountingSupplierParty>.*?</cac:AccountingSupplierParty>",
        _party("AccountingSupplierParty", seller, s_country).encode(),
        xml,
        flags=re.S,
    )
    return re.sub(
        rb"<cac:AccountingCustomerParty>.*?</cac:AccountingCustomerParty>",
        _party("AccountingCustomerParty", buyer, b_country).encode(),
        xml,
        flags=re.S,
    )


def _rows(d) -> dict[str, int]:
    tables = [r[0] for r in d.db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
    tables = [t for t in tables if not t.startswith("sqlite_")]
    return {t: d.db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}


def _files(d) -> set[str]:
    return {str(p.relative_to(d.folder)) for p in d.folder.rglob("*") if p.is_file()}


@pytest.mark.law("P13")
@pytest.mark.parametrize(
    "seller, s_country, buyer, b_country",
    [
        (DE_SELLER, "DE", RO_OTHER, "RO"),
        (DE_SELLER, "DE", DE_BUYER, "DE"),
        (RO_OTHER, "RO", DE_BUYER, "DE"),
        (RO_OTHER, None, PERSON, None),
        (CLIENT, "RO", CLIENT, "RO"),
    ],
    ids=["de-to-ro-firm", "de-to-de", "ro-firm-to-de", "ro-firm-to-person", "client-both-sides"],
)
def test_an_invoice_the_client_is_not_on_alone_is_refused_no_pack_no_job(
    cat, tmp_path, seller, s_country, buyer, b_country
):
    """Upload → intake → Dispatcher: an invoice the client is on neither side of (or on both)
    ends its batch refused, with the reason; no pack, no Job, no source stored. What the dossier
    keeps is the refusal fact and the batch issue's link, as for any refusal."""
    m = Month(cat, tmp_path)
    rows, files = _rows(m.d), _files(m.d)
    for form, data in (
        ("xml", invoice(seller, s_country, buyer, b_country)),
        ("zip", spv_zip(invoice(seller, s_country, buyer, b_country), "4242")),
    ):
        batch, facts = intake(cat, m.d, P, f"other.{form}", data)
        assert "_pack" not in facts and not facts["emit"]
        assert "the client" in facts["refused"] and "P13" in facts["refused"]
        tick = m.run(batch)
        assert tick.steps == ["done:refused"], tick
        pid = m.d.paperclip_id(batch)
        assert m.pc.issues[pid]["status"] == "cancelled"
        assert facts["refused"] in m.pc.comments[pid][-1]
    assert m.d.jobs(P) == []
    after = _rows(m.d)
    assert {t: after[t] - rows[t] for t in after if after[t] != rows[t]} == {
        "issue_facts": 2,
        "paperclip_links": 2,
    }
    assert _files(m.d) == files  # no source written


@pytest.mark.parametrize("country", [None, "RO"])
@pytest.mark.parametrize("form", ["xml", "zip"])
def test_a_sale_to_a_person_in_romania_is_a_ro_invoice_not_a_foreign_one(
    cat, tmp_path, form, country
):
    """The client sells to a person (no tax id), the buyer's country absent (read as RO, as the
    core reads it) or RO: an RO e-invoice that fails the identity gate (no counterparty CUI),
    never a ``foreign_invoice`` Job."""
    m = Month(cat, tmp_path)
    xml = invoice(CLIENT, "RO", PERSON, country)
    data = spv_zip(xml, "4243") if form == "zip" else xml
    batch, facts = intake(cat, m.d, P, f"b2c.{form}", data)
    assert facts["_pack"]["source_doc_id"] == "ro_efactura_ubl"
    assert facts["_pack"]["our_role"] == "outbound" and not facts["emit"]
    assert facts["failed"] == ["identity"]
    assert m.run(batch).steps == ["done:not_emitted"]
    assert m.d.jobs(P) == []


@pytest.mark.parametrize("form", ["xml", "zip"])
@pytest.mark.parametrize("side", ["outbound", "inbound"])
def test_an_invoice_from_abroad_the_client_is_on_emits_a_foreign_invoice_job(
    cat, tmp_path, side, form
):
    """A real invoice from abroad (the counterparty with no RO CUI and a country other than
    RO), the client its seller or its buyer, as bare XML or in an SPV zip: a
    ``foreign_invoice_xml`` whose kind is its XML, emitted as one ``foreign_invoice`` Job."""
    m = Month(cat, tmp_path)
    xml = (
        invoice(CLIENT, "RO", DE_BUYER, "DE")
        if side == "outbound"
        else invoice(DE_SELLER, "DE", CLIENT, None)
    )
    data = spv_zip(xml, "4244") if form == "zip" else xml
    batch, facts = intake(cat, m.d, P, f"abroad.{form}", data)
    pack = facts["_pack"]
    assert (pack["source_doc_id"], pack["kinds"], pack["our_role"]) == (
        "foreign_invoice_xml",
        ["xml"],
        side,
    )
    assert pack["identity_ok"] and pack["counterparty_cui"] is None
    assert facts["emit"], facts["failed"]
    assert m.run(batch).steps == ["kit:emit", "done:emitted"]
    (job,) = m.d.jobs(P)
    assert (job.job_kind, job.source_doc_id, job.status) == (
        "foreign_invoice",
        "foreign_invoice_xml",
        "ingested",
    )


def test_the_synthetic_months_invoices_from_abroad_are_read_as_from_abroad(cat, tmp_path):
    """The kit's own month for a firm that trades abroad: its foreign sale and its EU service
    carry the partner's country, so intake reads them as the generator means them."""
    firm = FIRMS["abroad"]
    m = Month(cat, tmp_path, firm=firm)
    seen = []
    for gd in month(firm, P, eu_service=True):
        if gd.kind == "decont":
            continue
        name = "doc.zip" if gd.data[:2] == b"PK" else "doc.xml"
        _, facts = intake(cat, m.d, P, name, gd.data)
        assert facts["_pack"]["source_doc_id"] == gd.source_doc_id and facts["emit"], gd.name
        seen.append(gd.kind)
    assert {"foreign_sale", "foreign_purchase"} <= set(seen)
