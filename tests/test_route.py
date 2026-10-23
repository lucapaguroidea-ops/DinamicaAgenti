"""The router (WP-13): each procedure's next step is a function of stored facts (P7)."""

import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

from kit.route import (
    BatchFacts,
    CloseFacts,
    JobFacts,
    ReconFacts,
    needs_approval,
    route,
    route_batch,
    route_close,
    route_job,
    route_recon,
)

ROOT = Path(__file__).resolve().parents[1]


def job(**kw) -> JobFacts:
    """A Job that has gone through every step up to the one under test."""
    base = dict(
        job_id="j_1",
        status="bound",
        has_xml=True,
        extracted=True,
        candidates=["ro_efactura_inbound"],
        bound_articol="ro_efactura_inbound",
        pre_verdict="absent",
        judged=True,
        verdict={"accounts_ok": True, "risk": "low", "needs_human": False},
        policy="first_n",
        first_n=5,
        packaged_count=5,
        book_is_saga=True,
        mouths_for_class=1,
    )
    return JobFacts(**{**base, **kw})


def step(s):
    return (s.kind, s.name)


# ----- the document path -----


def test_xml_is_extracted_by_the_kit_and_a_scan_by_the_reader_then_the_strong_tier():
    assert step(route_job(job(extracted=False))) == ("kit", "extract_xml")
    scan = dict(extracted=False, has_xml=False)
    assert step(route_job(job(**scan))) == ("hank", "read-document")
    second = route_job(job(**scan, read_runs=1, read_confirmed=False))
    assert step(second) == ("hank", "read-document") and second.detail == {"tier": "strong"}
    refused = route_job(job(**scan, read_runs=2, read_confirmed=False))
    assert step(refused) == ("done", "failed")


def test_binding_one_candidate_or_ask():
    assert step(route_job(job(bound_articol=None))) == ("kit", "bind")
    two = route_job(job(bound_articol=None, candidates=["bon_cu_cui", "bon_fara_cui"]))
    assert step(two) == ("ask", "define_articol") and two.actor == "person"
    none = route_job(job(bound_articol=None, candidates=[]))
    assert step(none) == ("ask", "define_articol")


def test_pre_decides_before_any_model_runs():
    assert step(route_job(job(pre_verdict=None, judged=False))) == ("kit", "pre_check")
    assert step(route_job(job(pre_verdict="already_posted"))) == ("done", "already_in_sink")
    for v in ("ambiguous", "need_export"):
        held = route_job(job(pre_verdict=v))
        assert step(held) == ("hold", "needs_human") and held.detail == {"to": "recon"}


def test_the_judge_runs_once_then_the_policy_decides_the_question():
    assert step(route_job(job(judged=False, verdict=None))) == ("hank", "judge-document")
    assert step(route_job(job())) == ("kit", "package")  # sixth of its kind, low risk
    assert step(route_job(job(packaged_count=4))) == ("ask", "v3_approve")
    assert step(route_job(job(policy="always", first_n=None))) == ("ask", "v3_approve")
    risky = job(
        policy="never_if_risk_low",
        first_n=None,
        verdict={"accounts_ok": True, "risk": "medium", "needs_human": False},
    )
    assert step(route_job(risky)) == ("ask", "v3_approve")


@pytest.mark.parametrize(
    "verdict",
    [
        {"accounts_ok": False, "risk": "low", "needs_human": False},
        {"accounts_ok": True, "risk": "low", "needs_human": True},
        None,
    ],
)
def test_a_doubtful_verdict_always_asks(verdict):
    assert needs_approval(job(verdict=verdict))


def test_the_answer_moves_the_job():
    assert step(route_job(job(packaged_count=0, approval="approve"))) == ("kit", "package")
    assert step(route_job(job(packaged_count=0, approval="edit"))) == ("kit", "package")
    assert step(route_job(job(packaged_count=0, approval="reject"))) == ("done", "rejected")


@pytest.mark.parametrize(
    "kw, why",
    [
        ({"book_is_saga": False}, "book"),
        ({"mouths_for_class": 0}, "mouth"),
        ({"mouths_for_class": 2}, "mouth"),
        ({"prefile_failures": ["p_prefile_duplicate: PRE is 'ambiguous'"]}, "p_prefile_duplicate"),
        ({"period_filed": True}, "filing receipt"),
    ],
)
def test_a_package_is_held_when_a_gate_is_closed(kw, why):
    s = route_job(job(**kw))
    assert step(s) == ("hold", "needs_human") and why in s.reason


def test_after_the_package_saga_imports_a_person_validates_and_the_kit_checks():
    packaged = dict(status="packaged", packaged=True)
    wait = route_job(job(**packaged))
    assert step(wait) == ("wait", "saga_import") and wait.actor == "import_agent"
    ask = route_job(job(**packaged, imported=True))
    assert step(ask) == ("ask", "wait_validare") and ask.actor == "saga_agent"
    assert step(route_job(job(**packaged, imported=True, validare="not_validated"))) == (
        "kit",
        "reopen",
    )
    assert step(route_job(job(**packaged, imported=True, validare="validated"))) == (
        "kit",
        "intent_check",
    )
    assert step(
        route_job(job(**packaged, imported=True, validare="validated", intent_ok=True))
    ) == ("done", "acked")
    held = route_job(job(**packaged, imported=True, validare="validated", intent_ok=False))
    assert step(held) == ("hold", "needs_human")


def test_a_reopened_job_is_packaged_again():
    assert step(route_job(job(status="reopened", packaged=False))) == ("kit", "package")


def test_terminal_and_waiting_jobs():
    for status in ("acked", "already_in_sink", "rejected", "failed"):
        assert step(route_job(job(status=status))) == ("done", status)
    assert step(route_job(job(open_question="v3_approve"))) == ("wait", "v3_approve")


# ----- P5: a person validates, closes and restores; a closed month gets nothing -----


@pytest.mark.law("P5")
def test_a_month_closed_in_saga_gets_nothing():
    s = route_job(job(month_closed=True))
    assert step(s) == ("hold", "needs_human") and "closed in SAGA" in s.reason
    assert step(route_job(job(month_closed=True, status="reopened", packaged=False)))[0] == "hold"


@pytest.mark.law("P5")
def test_no_route_gives_an_agent_validare_closing_or_a_restore():
    """Walk every route over many fact sets: an agent is only ever asked to import or to report
    what SAGA's snapshot shows; the close and every judgement are a person's."""
    seen = []
    for kw in [
        {},
        {"packaged": True, "status": "packaged"},
        {"packaged": True, "status": "packaged", "imported": True},
        {"packaged_count": 0},
        {"bound_articol": None, "candidates": []},
    ]:
        seen.append(route_job(job(**kw)))
    for kw in [
        {},
        {"locked": True, "diffed": True, "suggested": True},
        {"locked": True, "diffed": True, "suggested": True, "v2": "file"},
        {
            "locked": True,
            "diffed": True,
            "suggested": True,
            "v2": "file",
            "v4_done": True,
            "filings_open": ["d300_platitor"],
        },
    ]:
        seen.append(route_close(CloseFacts(**kw)))
    seen.append(route_recon(ReconFacts(checked=True, ambiguous=["j_1"])))
    for s in seen:
        assert not any(w in s.name for w in ("validate", "devalid", "close_month", "restore"))
        if s.actor in ("saga_agent", "import_agent"):
            assert s.name in ("saga_import", "wait_validare")
        if s.kind == "ask" and s.name != "wait_validare":
            assert s.actor == "person"


# ----- Sorting -----


def batch(**kw) -> BatchFacts:
    return BatchFacts(**{"emit": False, "failed": [], **kw})


def test_sorting_routes():
    assert step(route_batch(batch(question="define_class", failed=["class"]))) == (
        "ask",
        "define_class",
    )
    assert step(route_batch(batch(question="decont_split", split=True, failed=["class"]))) == (
        "ask",
        "decont_split",
    )
    assert step(route_batch(batch(split=True, split_answered=True, failed=["class"]))) == (
        "kit",
        "emit_children",
    )
    assert step(route_batch(batch(emit=True))) == ("kit", "emit")
    assert step(route_batch(batch(emit=True, job_emitted=True))) == ("done", "emitted")
    done = route_batch(batch(failed=["class", "primary"]))
    assert step(done) == ("done", "not_emitted") and "primary" in done.reason
    refused = route_batch(batch(refused="neither party is the client (P13)", emit=True))
    assert step(refused) == ("done", "refused") and "P13" in refused.reason


# ----- Reconcile -----


def test_reconcile_checks_first_then_asks_one_question_in_order():
    assert step(route_recon(ReconFacts())) == ("kit", "recheck_window")
    assert step(route_recon(ReconFacts(checked=True, to_review=["j_2"]))) == (
        "hank",
        "review-match",
    )
    full = ReconFacts(
        checked=True,
        missing_months=["2026-08"],
        contested=["j_3"],
        ambiguous=["j_1"],
        how_mismatch=["j_4"],
    )
    assert step(route_recon(full)) == ("ask", "need_rj_export")
    assert step(route_recon(full.model_copy(update={"missing_months": []}))) == (
        "ask",
        "recon_review_contest",
    )
    nxt = route_recon(ReconFacts(checked=True, ambiguous=["j_1", "j_5"], how_mismatch=["j_4"]))
    assert step(nxt) == ("ask", "recon_ambiguous") and nxt.detail == {"job_id": "j_1"}
    assert step(route_recon(ReconFacts(checked=True, how_mismatch=["j_4"]))) == (
        "ask",
        "recon_how_mismatch",
    )
    assert step(route_recon(ReconFacts(checked=True))) == ("done", "clear")


# ----- Month close -----


def test_the_close_waits_for_reconcile_then_locks_diffs_and_asks():
    assert step(route_close(CloseFacts(recon_open=True))) == ("wait", "recon")
    assert step(route_close(CloseFacts())) == ("kit", "lock")
    assert step(route_close(CloseFacts(locked=True))) == ("kit", "period_diff")
    assert step(route_close(CloseFacts(locked=True, diffed=True))) == ("hank", "close-suggest")
    ready = dict(locked=True, diffed=True, suggested=True)
    ask = route_close(CloseFacts(**ready))
    assert step(ask) == ("ask", "v2_close") and ask.actor == "person"
    assert step(route_close(CloseFacts(**ready, v2="hold"))) == ("hold", "hold")
    assert step(route_close(CloseFacts(**ready, v2="reopen"))) == ("kit", "release_lock")
    assert step(route_close(CloseFacts(**ready, v2="patch_maps"))) == ("hold", "patch_maps")
    filed = dict(**ready, v2="file")
    assert step(route_close(CloseFacts(**filed))) == ("ask", "v4_codit")
    receipts = route_close(
        CloseFacts(**filed, v4_done=True, filings_open=["d300_platitor", "d394_platitor"])
    )
    assert step(receipts) == ("ask", "filing_receipt") and receipts.detail == {
        "filing_id": "d300_platitor"
    }
    assert step(route_close(CloseFacts(**filed, v4_done=True))) == ("done", "filed")


# ----- P7: routes read facts -----


@pytest.mark.law("P7")
def test_facts_are_closed_so_nothing_else_reaches_a_route():
    with pytest.raises(ValidationError):
        job(model_says="file it")
    with pytest.raises(ValidationError):
        CloseFacts(suggestion={"action": "file"})


@pytest.mark.law("P7")
def test_the_same_facts_give_the_same_step():
    f = job(packaged_count=2)
    assert route_job(f) == route_job(f.model_copy())
    assert route("job", f.model_dump()) == route_job(f)


@pytest.mark.law("P7")
def test_the_router_imports_no_model_code():
    tree = ast.parse((ROOT / "kit" / "route.py").read_text(encoding="utf-8"))
    imported = {
        (n.module or "") if isinstance(n, ast.ImportFrom) else a.name
        for n in ast.walk(tree)
        if isinstance(n, (ast.Import, ast.ImportFrom))
        for a in (n.names if isinstance(n, ast.Import) else [None])
    }
    allowed = {"__future__", "typing", "pydantic"}
    assert {m for m in imported if m not in allowed and not m.startswith("kit.")} == set()
    assert not any(m.startswith(("kit.hank", "kit.model")) for m in imported)


def test_an_unknown_procedure_is_an_error():
    with pytest.raises(ValueError, match="unknown procedure"):
        route("payroll", {})
