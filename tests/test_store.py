"""The dossier store (WP-08): SQLite per client, unique keys, append-only logs (ARCHITECTURE §7)."""

import hashlib
import sqlite3

import pytest

from kit.store import Dossier, StoreError, open_dossier

CLIENT, OTHER = "41526372", "73645193"


def h(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


@pytest.fixture
def d(tmp_path):
    return open_dossier(tmp_path, CLIENT)


def job(d: Dossier, name: str = "doc", **kw):
    args = dict(
        client_cui=CLIENT,
        source_hash=h(name),
        job_kind="ro_efactura",
        source_doc_id="ro_efactura_ubl",
        period="2026-09",
    )
    return d.insert_job(**{**args, **kw})


# ----- the client boundary (P13) -----


def test_a_dossier_is_one_folder_per_client(tmp_path, d):
    root = tmp_path / CLIENT
    assert (root / "store.db").is_file()
    assert {p.name for p in root.iterdir()} >= {"sources", "extracts", "outbox", "eye", "runs"}
    assert d.client_cui == CLIENT


@pytest.mark.law("P13")
def test_a_dossier_opened_under_another_cui_is_refused(tmp_path, d):
    d.db.close()
    (tmp_path / OTHER).mkdir()
    (tmp_path / CLIENT / "store.db").rename(tmp_path / OTHER / "store.db")
    with pytest.raises(StoreError, match=f"belongs to {CLIENT}"):
        open_dossier(tmp_path, OTHER)


@pytest.mark.law("P13")
def test_a_record_of_another_client_is_refused(d):
    with pytest.raises(StoreError, match=f"{OTHER} in the dossier of {CLIENT}"):
        job(d, client_cui=OTHER)


@pytest.mark.law("P13")
def test_the_database_itself_refuses_another_clients_row(d):
    with pytest.raises(sqlite3.IntegrityError, match="another client"):
        d.db.execute(
            "INSERT INTO jobs (job_id, client_cui, source_hash, job_kind, source_doc_id, period,"
            " status, created_at) VALUES ('x', ?, ?, 'k', 'd', '2026-09', 'ingested', 'now')",
            (OTHER, h("raw")),
        )


def test_an_invalid_cui_has_no_dossier(tmp_path):
    with pytest.raises(StoreError, match="not a valid CUI"):
        open_dossier(tmp_path, "41526371")


# ----- unique keys: a second write is a no-op (P9) -----


@pytest.mark.law("P9")
def test_one_job_per_source_file(d):
    first, created = job(d)
    again, created_again = job(d)
    assert created and not created_again and again.job_id == first.job_id
    other, _ = job(d, "doc-2")
    assert other.job_id != first.job_id and len(d.jobs("2026-09")) == 2


@pytest.mark.law("P9")
def test_a_package_is_written_once(tmp_path, d):
    j, _ = job(d)
    key = f"intrare_factura_xml:{j.job_id}:1"
    first = d.write_package(
        key, j.job_id, "intrare_factura_xml", "1", "2026-09", "F_1.xml", b"<a/>"
    )
    again = d.write_package(
        key, j.job_id, "intrare_factura_xml", "1", "2026-09", "F_1.xml", b"<a/>"
    )
    assert first == again and (tmp_path / CLIENT / first.path).read_bytes() == b"<a/>"
    with pytest.raises(StoreError, match="already written with other content"):
        d.write_package(key, j.job_id, "intrare_factura_xml", "1", "2026-09", "F_1.xml", b"<b/>")


@pytest.mark.law("P9")
def test_a_verdict_is_stored_once_per_snapshot(d):
    j, _ = job(d)
    first = d.put_verdict(j.job_id, "pre", "snap-1", "absent", {"hits": []})
    again = d.put_verdict(j.job_id, "pre", "snap-1", "already_posted", {"hits": ["x"]})
    assert first.verdict == again.verdict == "absent"
    assert (
        d.put_verdict(j.job_id, "pre", "snap-2", "already_posted", {}).verdict == "already_posted"
    )


@pytest.mark.law("P9")
@pytest.mark.law("P12")
def test_a_model_answer_is_paid_once_and_carries_who_gave_it(d):
    key = ("judge_document", h("in"), h("card"))
    assert d.put_model_answer(*key, {"risk": "low"}, model="pinned-model", run="runs/r1")
    got = d.model_answer(*key)
    assert got.body == {"risk": "low"} and got.source == "model" and got.at
    assert (got.model, got.run, got.operator) == ("pinned-model", "runs/r1", None)
    # the same answer again is a no-op (P9); another one is refused, never silently ignored
    assert not d.put_model_answer(*key, {"risk": "low"}, model="pinned-model", run="runs/r1")
    with pytest.raises(StoreError, match="refused"):
        d.put_model_answer(*key, {"risk": "high"}, model="pinned-model", run="runs/r2")
    with pytest.raises(StoreError, match="refused"):
        d.put_model_answer(*key, {"risk": "low"}, operator="Ana")
    assert d.model_answer(*key).body == {"risk": "low"}
    assert d.model_answer("judge_document", h("in"), h("other card")) is None
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        d.db.execute("UPDATE model_answers SET body = '{}'")


@pytest.mark.law("P12")
def test_an_answer_written_meanwhile_by_another_process_is_refused_the_same_way(d):
    key = ("judge_document", h("in"), h("card"))
    other = sqlite3.connect(d.folder / "store.db")  # another process, after any check of ours
    with other:
        other.execute(
            "INSERT INTO model_answers (client_cui, role_id, input_hash, card_hash, body, at,"
            " source, model, operator, run) VALUES (?, ?, ?, ?, ?, ?, 'operator', NULL, 'Ana',"
            " NULL)",
            (CLIENT, *key, '{"risk": "low"}', "2026-10-01T00:00:00+00:00"),
        )
    other.close()
    with pytest.raises(StoreError, match="refused"):
        d.put_model_answer(*key, {"risk": "high"}, model="pinned-model", run="runs/r1")
    assert not d.put_model_answer(*key, {"risk": "low"}, operator="Ana")
    assert d.model_answer(*key).operator == "Ana"


@pytest.mark.law("P12")
def test_a_model_answer_names_one_source(d):
    key = ("review_match", h("in"), h("card"))
    for bad in (
        {},
        {"model": "pinned-model"},  # a model's answer names its run
        {"operator": ""},
        {"model": "pinned-model", "run": "runs/r1", "operator": "Ana"},
    ):
        with pytest.raises(StoreError):
            d.put_model_answer(*key, {"decision": "confirm"}, **bad)
    assert d.model_answer(*key) is None
    assert d.put_model_answer(*key, {"decision": "confirm"}, operator="Ana")
    got = d.model_answer(*key)
    assert (got.source, got.operator, got.model, got.run) == ("operator", "Ana", None, None)


@pytest.mark.law("P12")
def test_an_answer_stored_before_provenance_reads_as_of_no_known_source(tmp_path):
    folder = tmp_path / CLIENT
    folder.mkdir()
    old = sqlite3.connect(folder / "store.db")
    old.executescript(
        "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);"
        f"INSERT INTO meta VALUES ('client_cui', '{CLIENT}');"
        "CREATE TABLE model_answers (client_cui TEXT NOT NULL, role_id TEXT NOT NULL,"
        " input_hash TEXT NOT NULL, card_hash TEXT NOT NULL, body TEXT NOT NULL,"
        " at TEXT NOT NULL, PRIMARY KEY (role_id, input_hash, card_hash));"
        f"INSERT INTO model_answers VALUES ('{CLIENT}', 'judge_document', '{h('in')}',"
        f" '{h('card')}', '{{\"risk\": \"low\"}}', '2026-10-01T00:00:00+00:00');"
    )
    old.commit()
    old.close()
    d = open_dossier(tmp_path, CLIENT)
    got = d.model_answer("judge_document", h("in"), h("card"))
    assert got.body == {"risk": "low"} and got.source is None
    with pytest.raises(StoreError, match="refused"):
        d.put_model_answer("judge_document", h("in"), h("card"), {"risk": "low"}, operator="Ana")
    assert d.put_model_answer("judge_document", h("in"), h("c2"), {"risk": "low"}, operator="Ana")


@pytest.mark.law("P9")
def test_the_same_answer_twice_reaches_the_same_state(d):
    a = dict(issue="job:j1", kind="v3_approve", question_hash=h("q"), operator="Ana")
    d.record_answer(**a, answer={"decision": "approve"}, proposed=None, outcome="accepted")
    d.record_answer(**a, answer={"decision": "approve"}, proposed=None, outcome="accepted")
    assert len(d.answers("job:j1")) == 1
    with pytest.raises(StoreError, match="already answered"):
        d.record_answer(**a, answer={"decision": "reject"}, proposed=None, outcome="accepted")
    d.record_answer(**a, answer={"decision": "x"}, proposed=None, outcome="asked_again")
    assert [r["outcome"] for r in d.answers("job:j1")] == ["accepted", "asked_again"]


def test_the_close_lock_holds_one_expected_set(d):
    assert d.lock_close("2026-09", h("set")) is True
    assert d.lock_close("2026-09", h("set")) is True
    assert d.lock_close("2026-09", h("changed")) is False  # a lock mismatch: material
    d.release_close("2026-09")
    assert d.lock_close("2026-09", h("changed")) is True


def test_a_filing_closes_only_on_its_receipt(d):
    d.open_filing("2026-09", "d300_platitor")
    d.open_filing("2026-09", "d300_platitor")
    with pytest.raises(StoreError, match="receipt"):
        d.file_filing("2026-09", "d300_platitor", receipt_key="", submitted_by="Ana")
    d.file_filing("2026-09", "d300_platitor", receipt_key="spv/123.zip", submitted_by="Ana")
    assert d.filing("2026-09", "d300_platitor")["state"] == "filed"
    assert d.period_filed("2026-09") and not d.period_filed("2026-10")


@pytest.mark.law("P13")
def test_a_backup_label_names_this_client(d):
    d.record_backup(f"{CLIENT}:FIRMA:2026-10-07T08:00:00Z")
    with pytest.raises(StoreError, match="another client"):
        d.record_backup(f"{OTHER}:FIRMA:2026-10-07T08:00:00Z")


# ----- the Job's status moves forward only -----


def test_status_moves_forward_and_logs_each_change(d):
    j, _ = job(d)
    for status in ("bound", "reconcile_pre", "approved", "packaged", "wait_validare", "acked"):
        d.set_status(j.job_id, status)
    d.set_status(j.job_id, "acked")  # no change: no event
    assert [e["status"] for e in d.events(j.job_id)] == [
        "ingested",
        "bound",
        "reconcile_pre",
        "approved",
        "packaged",
        "wait_validare",
        "acked",
    ]
    d.set_status(j.job_id, "reopened")
    d.set_status(j.job_id, "packaged")


def test_a_status_jump_is_refused(d):
    j, _ = job(d)
    with pytest.raises(StoreError, match="ingested → packaged"):
        d.set_status(j.job_id, "packaged")
    with pytest.raises(StoreError, match="unknown status"):
        d.set_status(j.job_id, "posted")


def test_logs_are_append_only(d):
    job(d)
    d.record_answer(
        "job:j1", "v3_approve", h("q"), {"decision": "approve"}, None, "accepted", "Ana"
    )
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        d.db.execute("DELETE FROM job_events")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        d.db.execute("UPDATE answers SET operator = 'x'")


# ----- not a ledger (P4) -----


@pytest.mark.law("P4")
def test_the_store_keeps_no_books(d):
    names = [
        r[0].lower()
        for r in d.db.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view')")
    ]
    columns = [
        c[1].lower()
        for n in names
        if not n.startswith("sqlite_")
        for c in d.db.execute(f"PRAGMA table_info('{n}')")
    ]
    words = ("journal", "ledger", "chart", "trial", "balance", "debit", "credit", "account")
    assert [x for x in names + columns if any(w in x for w in words)] == []
