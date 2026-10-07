"""PRE / POST matching and the settlement proposal (WP-09, ARCHITECTURE §4.3). Deterministic."""

from pathlib import Path

import pytest

from kit.catalog import load_catalog
from kit.recon import (
    BankLine,
    Doc,
    JournalLine,
    OpenInvoice,
    RegisterEntry,
    SinkDoc,
    Witness,
    normalize_number,
    pick_profile,
    post_check,
    pre_check,
    propose_settlement,
)

ROOT = Path(__file__).resolve().parents[1]
PARTNER, OTHER = "73645193", "31415920"


@pytest.fixture(scope="module")
def cat():
    return load_catalog(ROOT / "catalog")


def doc(**kw) -> Doc:
    base = dict(
        doc_class="intrare",
        number="FV-0042",
        date="2026-09-15",
        partner_cui=PARTNER,
        gross="119.00",
        vat="19.00",
        period="2026-09",
    )
    return Doc(**{**base, **kw})


def sink(**kw) -> SinkDoc:
    base = dict(
        saga_key="I-1",
        doc_class="intrare",
        number="FV-0042",
        date="2026-09-15",
        partner_cui=PARTNER,
        gross="119.00",
        validated=True,
    )
    return SinkDoc(**{**base, **kw})


def witness(docs=(), lines=(), months=("2026-09",), register=()) -> Witness:
    return Witness(
        covered=list(months), docs=list(docs), lines=list(lines), spv_register=list(register)
    )


# ----- profiles -----


def test_the_profile_follows_the_fiscal_class(cat):
    assert pick_profile(cat, "pre", "ro_efactura").id == "pre_doc_nr_date"
    assert pick_profile(cat, "pre", "bon").id == "pre_bon_date_gross"
    assert pick_profile(cat, "pre", "extras").id == "pre_extras_date_gross"
    assert pick_profile(cat, "post", "bon").id == "post_bon_how"
    assert pick_profile(cat, "post", "ro_efactura", default="post_how_4428").id == "post_how_4428"


def test_no_single_profile_is_none(cat):
    assert pick_profile(cat, "post", "ro_efactura") is None  # two defaults, no close kind named


# ----- numbers -----


@pytest.mark.parametrize(
    "a, b, level",
    [
        (" fv-0042 ", "FV-0042", "exact"),
        ("FV 0042", "FV-0042", "alnum"),
        ("FV-42", "0042", "digits_core"),
        ("FV-42", "FV-43", None),
    ],
)
def test_number_levels(a, b, level):
    def match(x, y):
        for lvl in ("exact", "alnum", "digits_core"):
            if normalize_number(x, lvl) == normalize_number(y, lvl) != "":
                return lvl
        return None

    assert match(a, b) == level


# ----- PRE -----


def pre(cat, d, w):
    return pre_check(pick_profile(cat, "pre", "ro_efactura"), d, w)


def test_one_document_agreeing_on_every_key_is_already_posted(cat):
    r = pre(cat, doc(), witness([sink()]))
    assert r.verdict == "already_posted" and r.hits == ["I-1"]


def test_nothing_close_in_covered_months_is_absent(cat):
    r = pre(cat, doc(), witness([sink(number="FV-0099", date="2026-09-20", gross="50.00")]))
    assert r.verdict == "absent" and r.hits == [] and r.near == []


def test_absent_needs_every_month_covered(cat):
    r = pre(cat, doc(date="2026-08-30"), witness([]))
    assert r.verdict == "need_export" and r.missing == ["2026-08"]


def test_gross_within_the_tolerance_still_matches(cat):
    assert pre(cat, doc(), witness([sink(gross="119.05")])).verdict == "already_posted"
    assert pre(cat, doc(), witness([sink(gross="119.06")])).verdict == "ambiguous"


def test_two_hits_or_two_of_three_keys_are_ambiguous(cat):
    two = pre(cat, doc(), witness([sink(), sink(saga_key="I-2")]))
    assert two.verdict == "ambiguous" and two.hits == ["I-1", "I-2"]
    near = pre(cat, doc(), witness([sink(date="2026-09-16")]))
    assert near.verdict == "ambiguous" and near.near == ["I-1"] and near.hits == []


def test_a_conflicting_partner_cui_is_not_a_hit(cat):
    r = pre(cat, doc(), witness([sink(partner_cui=OTHER)]))
    assert r.verdict == "ambiguous" and r.hits == []


def test_digits_core_counts_only_with_the_same_partner(cat):
    assert pre(cat, doc(number="FV-42"), witness([sink(number="42")])).verdict == "already_posted"
    no_partner = pre(cat, doc(number="FV-42"), witness([sink(number="42", partner_cui=None)]))
    assert no_partner.verdict != "already_posted"


def test_the_other_side_is_never_a_match(cat):
    assert pre(cat, doc(), witness([sink(doc_class="iesire")])).verdict == "absent"


def test_the_spv_register_can_say_already_posted(cat):
    reg = RegisterEntry(
        number="FV-0042", date="2026-09-15", partner_cui=PARTNER, gross="119.00", posted=True
    )
    assert pre(cat, doc(), witness([], register=[reg])).verdict == "already_posted"
    unposted = reg.model_copy(update={"posted": False})
    assert pre(cat, doc(), witness([], register=[unposted])).verdict == "absent"


def test_a_receipt_matches_on_date_and_gross(cat):
    profile = pick_profile(cat, "pre", "bon")
    r = pre_check(
        profile, doc(number="", partner_cui=None), witness([sink(number="BON 7", partner_cui=None)])
    )
    assert r.verdict == "already_posted"


def test_the_verdict_names_its_snapshot(cat):
    a = pre(cat, doc(), witness([sink()]))
    b = pre(cat, doc(), witness([sink(), sink(saga_key="I-9", number="X", gross="1.00")]))
    assert (
        a.snapshot_id != b.snapshot_id
        and a.snapshot_id == pre(cat, doc(), witness([sink()])).snapshot_id
    )


# ----- POST -----


def jl(account, amount, side="credit", **kw) -> JournalLine:
    base = dict(saga_key="I-1", journal="intrari", number="FV-0042", date="2026-09-15")
    return JournalLine(**{**base, **kw, "account": account, "amount": amount, "side": side})


PURCHASE = [jl("401.00001", "119.00"), jl("4426", "19.00", "debit"), jl("628", "100.00", "debit")]


def post(cat, d, lines, expect=("401", "4426"), profile="post_doc_how"):
    return post_check(cat.get("ReconcileProfile", profile), list(expect), d, witness(lines=lines))


def test_a_posting_with_the_expected_accounts_and_amounts_is_how_ok(cat):
    r = post(cat, doc(), PURCHASE)
    assert r.verdict == "how_ok" and r.used == ["401.00001", "4426", "628"]


def test_an_amount_that_differs_is_a_mismatch(cat):
    lines = [jl("401", "119.00"), jl("4426", "18.00", "debit")]
    r = post(cat, doc(), lines)
    assert r.verdict == "how_mismatch" and "4426" in r.reason


def test_accounts_not_used_are_a_mismatch_unless_one_is_enough(cat):
    only_supplier = [jl("401", "119.00"), jl("628", "119.00", "debit")]
    assert post(cat, doc(), only_supplier).verdict == "how_ok"  # require_all_accounts: false
    strict = post(cat, doc(), only_supplier, expect=("401", "4428"), profile="post_how_4428")
    assert strict.verdict == "how_mismatch" and "4428" in strict.reason


def test_no_posting_found_is_a_mismatch_and_no_lines_need_an_export(cat):
    assert post(cat, doc(), [jl("401", "119.00", number="OTHER")]).verdict == "how_mismatch"
    r = post_check(cat.get("ReconcileProfile", "post_doc_how"), ["401"], doc(), witness(months=()))
    assert r.verdict == "need_export"


def test_no_expected_accounts_at_all_is_a_mismatch(cat):
    r = post(cat, doc(), PURCHASE, expect=())
    assert r.verdict == "how_ok"  # falls back to the profile's accounts (401, 4111)
    bare = post(cat, doc(), PURCHASE, expect=(), profile="post_bon_how")
    assert bare.verdict == "how_mismatch" and "no expected accounts" in bare.reason


def test_an_account_class_matches_by_prefix(cat):
    lines = [jl("401", "119.00"), jl("4426", "19.00", "debit"), jl("6022", "100.00", "debit")]
    assert post(cat, doc(), lines, expect=("401", "4426", "6")).verdict == "how_ok"


# ----- the settlement proposal -----


def inv(
    number,
    gross,
    paid="0.00",
    partner=PARTNER,
    name="Furnizor SRL",
    date="2026-09-01",
    doc_class="intrare",
) -> OpenInvoice:
    return OpenInvoice(
        ref=number,
        doc_class=doc_class,
        number=number,
        date=date,
        partner_cui=partner,
        partner_name=name,
        gross=gross,
        paid=paid,
    )


def line(gross, desc="", doc_class="plata", date="2026-09-20") -> BankLine:
    return BankLine(doc_class=doc_class, date=date, gross=gross, description=desc)


def test_a_payment_settles_a_purchase_of_exactly_its_amount():
    p = propose_settlement(line("119.00"), [inv("FV-1", "119.00"), inv("FV-2", "50.00")])
    assert [(c.ref, c.kind) for c in p.candidates] == [("FV-1", "full")]
    assert p.edit == {"settles": "FV-1", "partner_cui": PARTNER}


def test_the_wrong_side_a_later_date_or_a_paid_invoice_is_no_candidate():
    invoices = [
        inv("S-1", "119.00", doc_class="iesire"),
        inv("L-1", "119.00", date="2026-09-25"),
        inv("P-1", "119.00", paid="119.00"),
        inv("ST-1", "119.00", doc_class="storn_intrare"),
    ]
    p = propose_settlement(line("119.00"), invoices)
    assert p.candidates == [] and p.edit is None


def test_a_partial_payment_needs_the_description_to_name_the_invoice_or_partner():
    silent = propose_settlement(line("50.00"), [inv("FV-1", "119.00")])
    assert silent.candidates == []
    named = propose_settlement(line("50.00", "plata fact FV-1"), [inv("FV-1", "119.00")])
    (c,) = named.candidates
    assert c.kind == "partial" and c.open_after == "69.00"


def test_the_description_ranks_candidates_and_a_tie_gives_no_edit():
    two = [inv("FV-1", "119.00"), inv("FV-2", "119.00", partner=OTHER, name="Alt SRL")]
    tie = propose_settlement(line("119.00"), two)
    assert len(tie.candidates) == 2 and tie.edit is None
    led = propose_settlement(line("119.00", "Alt SRL factura FV-2"), two)
    assert led.candidates[0].ref == "FV-2" and led.edit["settles"] == "FV-2"


def test_a_group_of_one_partners_invoices_adding_up_is_shown_never_an_edit():
    invoices = [inv("FV-1", "60.00"), inv("FV-2", "59.00"), inv("FV-3", "500.00")]
    p = propose_settlement(line("119.00"), invoices)
    assert p.candidates == [] and p.edit is None
    assert p.groups == [["FV-1", "FV-2"]]


def test_a_receipt_settles_a_sale():
    p = propose_settlement(
        line("119.00", doc_class="incasare"), [inv("S-1", "119.00", doc_class="iesire")]
    )
    assert p.edit == {"settles": "S-1", "partner_cui": PARTNER}
