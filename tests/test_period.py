"""The period difference and the month's controls (WP-11, ARCHITECTURE §4.4). Not a ledger."""

from pathlib import Path

import pytest

from kit.catalog import load_catalog
from kit.period import (
    ExpectedItem,
    ExplainedRule,
    close_action_refused,
    close_kind,
    expected_set_hash,
    period_diff,
    prefile_failures,
    weigh_suggestion,
)
from kit.recon import JournalLine, SinkDoc, Witness

ROOT = Path(__file__).resolve().parents[1]
PARTNER, BUYER = "73645193", "31415920"
PAYER = {"tva": "tva_platitor", "exig": "tva_la_livrare"}


@pytest.fixture(scope="module")
def cat():
    return load_catalog(ROOT / "catalog")


def item(
    job="j1",
    status="acked",
    doc_class="intrare",
    number="FV-1",
    gross="119.00",
    vat="19.00",
    partner=PARTNER,
    saga_key=None,
    **kw,
) -> ExpectedItem:
    return ExpectedItem(
        job_id=job,
        status=status,
        doc_class=doc_class,
        number=number,
        date="2026-09-15",
        partner_cui=partner,
        gross=gross,
        vat=vat,
        saga_key=saga_key,
        **kw,
    )


def sdoc(key="I-1", doc_class="intrare", number="FV-1", gross="119.00", partner=PARTNER):
    return SinkDoc(
        saga_key=key,
        doc_class=doc_class,
        number=number,
        date="2026-09-15",
        partner_cui=partner,
        gross=gross,
        validated=True,
    )


def jl(key, account, side, amount, journal="intrari"):
    return JournalLine(
        saga_key=key,
        journal=journal,
        number="x",
        date="2026-09-15",
        account=account,
        side=side,
        amount=amount,
    )


PURCHASE_LINES = [
    jl("I-1", "401.00001", "credit", "119.00"),
    jl("I-1", "4426", "debit", "19.00"),
    jl("I-1", "628", "debit", "100.00"),
]


def witness(docs=None, lines=PURCHASE_LINES, months=("2026-09",)):
    docs = [sdoc()] if docs is None else docs
    return Witness(covered=list(months), docs=list(docs), lines=list(lines))


def diff(cat, items=None, w=None, axes=PAYER, **kw):
    items = [item()] if items is None else items
    return period_diff(cat, "2026-09", list(items), w or witness(), axes=axes, **kw)


def status(d, cid):
    return next(r for r in d.controls if r.control_id == cid).status


# ----- a clean month -----


def test_a_clean_month_is_not_material(cat):
    d = diff(cat)
    assert [b.bucket for b in d.buckets] == ["expected"] and d.outbound_holes == []
    assert status(d, "c0_synthetic_parity") == "PASS"
    assert status(d, "c1_outbound_complete") == status(d, "c2_unexplained_empty") == "PASS"
    assert not d.material and d.hard_failures == 0 and d.can_file


def test_controls_that_do_not_apply_are_info(cat):
    d = diff(cat)
    assert status(d, "m1_8_4428_open") == "INFO"  # not TVA la încasare
    assert status(d, "t_regime_4428") == "INFO"  # a VAT payer
    assert status(d, "m1_1_payables_tie") == "INFO"  # no client maps yet


# ----- buckets -----


def test_a_sink_document_matches_by_saga_key_first(cat):
    d = diff(cat, [item(saga_key="I-1", number="OTHER")])
    assert [(b.bucket, b.job_id) for b in d.buckets] == [("expected", "j1")]


def test_an_explained_document_is_sink_only_and_the_rest_unexplained(cat):
    rent = sdoc("I-2", number="CHIRIE-9", gross="500.00", partner=BUYER)
    other = sdoc("I-3", number="X-1", gross="10.00", partner=BUYER)
    rules = [
        ExplainedRule(
            rule_id="chirie_lunara", kind="document", partner_cui=BUYER, number_prefix="CHIRIE"
        )
    ]
    lines = PURCHASE_LINES + [
        jl("I-2", "401", "credit", "500.00"),
        jl("I-2", "612", "debit", "500.00"),
        jl("I-3", "401", "credit", "10.00"),
        jl("I-3", "628", "debit", "10.00"),
    ]
    d = diff(cat, w=witness([sdoc(), rent, other], lines), rules=rules)
    assert {(b.saga_key, b.bucket, b.rule_id) for b in d.buckets} == {
        ("I-1", "expected", None),
        ("I-2", "explained_sink_only", "chirie_lunara"),
        ("I-3", "unexplained", None),
    }
    assert status(d, "c2_unexplained_empty") == "FAIL"
    assert d.material and "c2_unexplained_empty" in " ".join(d.blockers)


def test_an_expected_job_not_in_the_books_is_an_outbound_hole(cat):
    d = diff(cat, [item(), item("j2", status="wait_validare", number="FV-2")])
    assert d.outbound_holes == ["j2"] and status(d, "c1_outbound_complete") == "FAIL"
    assert d.material


def test_a_rejected_job_is_not_expected(cat):
    d = diff(cat, [item(), item("j2", status="rejected", number="FV-2")])
    assert d.outbound_holes == [] and not d.material


# ----- parity on the watched accounts -----


def test_a_watched_account_difference_of_a_cent_is_material(cat):
    lines = [jl("I-1", "401", "credit", "119.01"), jl("I-1", "4426", "debit", "19.00")]
    d = diff(cat, w=witness(lines=lines))
    assert status(d, "c0_synthetic_parity") == "FAIL" and d.material
    assert d.parity["401"]["delta"] == "-0.01"


def test_a_line_rule_explains_movements_on_the_parity_side(cat):
    fee = [jl("B-1", "627", "debit", "5.00", "banca"), jl("B-1", "5121", "credit", "5.00", "banca")]
    plain = diff(cat, w=witness(lines=PURCHASE_LINES + fee))
    assert status(plain, "c0_synthetic_parity") == "FAIL"
    rules = [ExplainedRule(rule_id="comision_banca", kind="line", account="627")]
    explained = diff(cat, w=witness(lines=PURCHASE_LINES + fee), rules=rules)
    assert status(explained, "c0_synthetic_parity") == "PASS"


def test_a_bank_line_bound_to_a_supplier_implies_401_and_5121(cat):
    pay = item("j2", doc_class="plata", number="OP-1", gross="119.00", vat=None, saga_key="B-1")
    lines = PURCHASE_LINES + [
        jl("B-1", "401", "debit", "119.00", "banca"),
        jl("B-1", "5121", "credit", "119.00", "banca"),
    ]
    d = diff(cat, [item(), pay], witness([sdoc()], lines))
    assert status(d, "c0_synthetic_parity") == "PASS", d.parity


# ----- regimes and încasare -----


def test_unexplained_4428_for_a_non_payer_is_material(cat):
    axes = {"tva": "tva_neplatitor"}
    lines = PURCHASE_LINES + [jl("I-1", "4428", "debit", "19.00")]
    d = diff(cat, w=witness(lines=lines), axes=axes)
    assert status(d, "t_regime_4428") == "FAIL" and d.material


def test_4428_open_needs_the_balance_and_ties_to_the_open_vat(cat):
    axes = {"tva": "tva_platitor", "exig": "tva_la_incasare"}
    it = item(vat_open="19.00")
    assert (
        status(diff(cat, [it], axes=axes), "m1_8_4428_open") == "FAIL"
    )  # no balance: cannot compute
    ok = diff(cat, [it], axes=axes, balances={"4428": "19.00"})
    assert status(ok, "m1_8_4428_open") == "PASS"
    off = diff(cat, [it], axes=axes, balances={"4428": "25.00"})
    assert status(off, "m1_8_4428_open") == "FAIL"


def test_advisory_controls_never_make_the_month_material(cat):
    lines = PURCHASE_LINES + [
        jl("I-1", "4424", "debit", "1.00"),
        jl("I-1", "401", "credit", "1.00"),
    ]
    d = diff(cat, w=witness(lines=lines))
    assert status(d, "m1_9_4424_watched") == "FAIL"
    advisory = [r.control_id for r in d.controls if r.status == "FAIL" and r.severity == "advisory"]
    assert "m1_9_4424_watched" in advisory
    assert d.hard_failures == len(
        [r for r in d.controls if r.status == "FAIL" and r.severity == "blocking"]
    )


# ----- blockers -----


def test_a_month_without_an_export_is_material(cat):
    d = diff(cat, w=witness(months=()))
    assert d.material and any("need_rj_export" in b for b in d.blockers)


def test_open_pre_questions_and_a_lock_mismatch_block(cat):
    d = diff(cat, open_pre=["j9"], lock_mismatch=True)
    assert d.material and any("reconcile" in b for b in d.blockers)
    assert any("lock mismatch" in b for b in d.blockers)


def test_the_close_kind_follows_the_co_dit(cat):
    assert close_kind(cat, PAYER) == "close_standard"
    assert (
        close_kind(cat, {"tva": "tva_platitor", "exig": "tva_la_incasare"}) == "close_tva_incasare"
    )
    assert close_kind(cat, {}) is None
    d = diff(cat, axes={})
    assert d.material and any("no close kind" in b for b in d.blockers)


# ----- P11: a material month is never filed -----


@pytest.mark.law("P11")
def test_file_is_refused_while_the_month_is_material(cat):
    material = diff(cat, [item(), item("j2", status="packaged", number="FV-2")])
    assert close_action_refused(material, "file") is not None
    assert close_action_refused(material, "hold") is None
    assert close_action_refused(diff(cat), "file") is None


@pytest.mark.law("P11")
def test_a_model_cannot_clear_material(cat):
    material = diff(cat, [item(), item("j2", status="packaged", number="FV-2")])
    kept = weigh_suggestion(material, {"action": "file", "books_support_declaration": True})
    assert kept["action"] != "file" and kept["dropped"]
    assert weigh_suggestion(diff(cat), {"action": "file"})["action"] == "file"
    assert weigh_suggestion(material, None) is None


# ----- the expected set and pre-package controls -----


def test_the_expected_set_hash_ignores_rejected_jobs_and_order(cat):
    a = expected_set_hash([item(), item("j2", number="FV-2")])
    b = expected_set_hash([item("j2", number="FV-2"), item(), item("j3", status="rejected")])
    assert a == b and a != expected_set_hash([item()])


def test_prefile_controls_gate_a_package(cat):
    assert prefile_failures(cat, "absent") == []
    out = prefile_failures(cat, "already_posted")
    assert any("p_prefile_duplicate" in f for f in out) and any(
        "p_prefile_hard_failures" in f for f in out
    )


def test_the_diff_names_its_snapshot(cat):
    assert (
        diff(cat).snapshot_id
        == diff(cat).snapshot_id
        != diff(cat, items=[item(gross="120.00")]).snapshot_id
    )
