"""End-to-end scenarios on invented firms (WP-16): a month through Sorting, the document path up
to the package (WP-10's) and the close against the simulated book. Invented data only."""

import json
from pathlib import Path

import pytest

from kit.bind import candidates
from kit.catalog import load_catalog
from kit.cli import main
from kit.recon import Witness
from kit.scenario import DEFECTS, PERSON, run_month
from kit.store import open_dossier
from kit.synthetic import CUSTOMERS, FIRMS, SUPPLIERS, month, simulated_book
from kit.types import cui_is_valid
from kit.ubl import parse_ubl, read_spv_zip

ROOT = Path(__file__).resolve().parents[1]
PERIOD = "2026-09"


@pytest.fixture(scope="module")
def cat():
    return load_catalog(ROOT / "catalog")


def ran(cat, tmp_path, firm, **kw):
    return run_month(cat, tmp_path / "dossiers", firm, PERIOD, **kw)


# ----- the invented firms -----


def test_every_invented_cui_passes_the_check_digit():
    for p in [*FIRMS.values(), *SUPPLIERS, *CUSTOMERS]:
        assert cui_is_valid(p.cui), p


def test_months_are_seeded_and_read_back_as_written():
    a, b = month(FIRMS["platitor"], PERIOD), month(FIRMS["platitor"], PERIOD)
    assert [d.source_hash for d in a] == [d.source_hash for d in b]
    assert a[0].source_hash != month(FIRMS["platitor"], PERIOD, seed=8)[0].source_hash
    for d in a:
        doc = parse_ubl(read_spv_zip(d.data).invoice if d.data[:2] == b"PK" else d.data)
        assert (doc.number, doc.totals.gross) == (d.number, f"{d.gross:.2f}")


def test_the_simulated_book_balances_every_document():
    for firm in FIRMS.values():
        w, _ = simulated_book(firm, PERIOD, month(firm, PERIOD))
        assert isinstance(w, Witness)
        for key in {x.saga_key for x in w.lines}:
            lines = [x for x in w.lines if x.saga_key == key]
            debit = sum(float(x.amount) for x in lines if x.side == "debit")
            credit = sum(float(x.amount) for x in lines if x.side == "credit")
            assert round(debit - credit, 2) == 0, key


def test_a_firm_buys_abroad_only_if_its_codit_says_so():
    with pytest.raises(ValueError, match="buys nothing abroad"):
        month(FIRMS["platitor"], PERIOD, eu_service=True)


# ----- binding -----


@pytest.mark.law("P14")
def test_draft_rows_bind_only_when_admitted(cat):
    axes = FIRMS["platitor"].axes
    args = (cat, "ro_efactura", "inbound", False, axes, "2026-09-03")
    assert candidates(*args, allow_draft=True) == ["ro_efactura_inbound"]
    assert candidates(*args) == []  # nothing is active before a SAGA round-trip


def test_the_codit_decides_the_articol(cat):
    args = ("foreign_invoice", "inbound", False)
    payer = candidates(cat, *args, FIRMS["abroad"].axes, "2026-09-15", allow_draft=True)
    non_payer = candidates(cat, *args, FIRMS["neplatitor"].axes, "2026-09-15", allow_draft=True)
    assert payer == ["foreign_invoice_inbound"] and non_payer == ["foreign_rc_neplatitor"]
    assert candidates(cat, *args, FIRMS["abroad"].axes, "2025-12-31", allow_draft=True) == []


# ----- a clean month -----


@pytest.mark.parametrize("firm", list(FIRMS))
def test_a_clean_month_reaches_the_package_and_is_filed(cat, tmp_path, firm):
    r = ran(cat, tmp_path, firm)
    walked = [t for t in r.trails if t.job_id]
    assert walked and all(t.steps[-1] == "stop: the package is WP-10's" for t in walked)
    for t in walked:  # no model ran: every judge refused and a person approved
        assert "refused: no model pinned (D3)" in t.steps and "ask:v3_approve" in t.steps
    assert not r.diff.material and r.diff.blockers == [] and r.v2 == "file"
    assert r.close_steps[-1] == "done:filed"
    filed = r.close_steps.count("ask:filing_receipt")
    assert filed >= 3  # VAT or not, SAF-T and the income tax at least


def test_each_client_type_binds_its_own_articole(cat, tmp_path):
    bound = {f: {t.articol for t in ran(cat, tmp_path / f, f).trails} for f in FIRMS}
    assert bound["platitor"] == {"ro_efactura_inbound", "ro_efactura_outbound"}
    assert "foreign_invoice_outbound" in bound["abroad"]
    assert None in bound["bonuri"]  # the expense report itself is split, never bound


def test_the_expense_report_is_split_by_a_person_and_its_part_walked(cat, tmp_path):
    r = ran(cat, tmp_path, "bonuri")
    names = [t.name for t in r.trails]
    report = names.index(f"expense report {PERIOD}")
    assert r.trails[report].steps == ["ask:decont_split"] and r.trails[report].job_id is None
    part = r.trails[report + 1]
    assert part.name.startswith("expense invoice") and part.articol == "ro_efactura_inbound"


def test_tva_la_incasare_closes_on_4428(cat, tmp_path):
    r = ran(cat, tmp_path, "incasare")
    m18 = next(c for c in r.diff.controls if c.control_id == "m1_8_4428_open")
    assert m18.status == "PASS"


@pytest.mark.law("P5")
def test_a_scenario_asks_no_agent_to_validate_or_close(cat, tmp_path):
    r = ran(cat, tmp_path, "abroad")
    steps = [s for t in r.trails for s in t.steps] + r.close_steps
    assert not any(w in s for s in steps for w in ("validate", "close_month", "restore"))
    d = open_dossier(tmp_path / "dossiers", FIRMS["abroad"].cui)
    assert {row[0] for row in d.db.execute("SELECT operator FROM answers")} == {PERSON}


# ----- defects: the month is material and the right control says why -----


@pytest.mark.law("P11")
@pytest.mark.parametrize(
    "defect, control",
    [
        ("missing_in_books", "c1_outbound_complete"),
        ("extra_in_books", "c2_unexplained_empty"),
        ("cent_off", "c0_synthetic_parity"),
    ],
)
def test_a_defect_makes_the_month_material_and_file_is_refused(cat, tmp_path, defect, control):
    r = ran(cat, tmp_path, "platitor", defects=(defect,))
    assert r.diff.material and r.v2 == "hold"
    assert any(b.startswith(control) for b in r.diff.blockers), r.diff.blockers
    assert "asked again: file refused" in r.close_steps and r.close_steps[-1] == "hold:hold"
    assert "ask:filing_receipt" not in r.close_steps


def test_every_defect_is_tested_and_an_unknown_one_refused(cat, tmp_path):
    assert set(DEFECTS) == {"missing_in_books", "extra_in_books", "cent_off"}
    with pytest.raises(ValueError, match="unknown defects"):
        ran(cat, tmp_path, "platitor", defects=("typo",))


def test_a_non_payers_eu_service_goes_to_a_person_until_d5(cat, tmp_path):
    r = ran(cat, tmp_path, "neplatitor", eu_service=True)
    eu = next(t for t in r.trails if t.name.startswith("EU service"))
    assert eu.articol == "foreign_rc_neplatitor" and eu.held
    assert "ask:v3_approve" in eu.steps and eu.steps[-1].startswith("held: 0 mouths")
    assert r.diff.material and r.v2 == "hold"
    assert eu.job_id in r.diff.outbound_holes


# ----- the command -----


def test_scenario_command(tmp_path, capsys):
    args = ["scenario", "bonuri", "--period", PERIOD, "--dossiers", str(tmp_path)]
    assert main([*args, "--catalog", str(ROOT / "catalog")]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["close"]["v2"] == "file" and len(out["documents"]) == 8
    bad = ["scenario", "nobody", "--period", PERIOD, "--dossiers", str(tmp_path)]
    assert main(bad) == 1 and "unknown firm" in capsys.readouterr().err
