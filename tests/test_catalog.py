"""The catalog loader (WP-04): row schemas, draft rows, unique ids, additive files, fail closed."""

from pathlib import Path
from textwrap import dedent, indent

import pytest

from kit.catalog import CATALOGS, CatalogError, load_catalog

ROOT = Path(__file__).resolve().parents[1]

BASE = {
    "10_law_firm/axes.yaml": """
        catalog: Axis
        file_schema: 1
        rows:
          - id: tva
            status: draft
            values: [tva_platitor, tva_neplatitor]
    """,
    "50_control/questions.yaml": """
        catalog: QuestionKind
        file_schema: 1
        rows:
          - id: v3_approve
            status: draft
            actor: accountant
            procedure: document
            answer: {decision: "approve|reject|edit", edit: "object?"}
    """,
    "30_path/mouths.yaml": """
        catalog: Mouth
        file_schema: 1
        rows:
          - id: intrare_factura_xml
            status: draft
            saga_path: import_xml
            doc_class: intrare
            validare: person
            backup: before_batch
            gate: {policy: first_n, first_n: 5}
    """,
    "30_path/articole.yaml": """
        catalog: Articol
        file_schema: 1
        rows:
          - id: ro_efactura_inbound
            status: draft
            procedure: document
            filters: {fiscal_class: ro_efactura, our_role: inbound, is_storno: false}
            require: {tva: [tva_platitor]}
            mouths: [intrare_factura_xml]
            gate: {policy: first_n, first_n: 5}
            reconcile:
              match_keys: [number, date]
              expect_accounts: ["401", "4426"]
              tolerance: "0.05"
            valid_from: "2026-01-01"
    """,
    "20_document/source_docs.yaml": """
        catalog: SourceDoc
        file_schema: 1
        rows:
          - id: ro_efactura_ubl
            status: draft
            posting_eligible: true
            primary_kinds: [ubl_spv]
            needs_counterparty_cui: true
            fiscal_class: ro_efactura
    """,
    "20_document/jobs.yaml": """
        catalog: JobKind
        file_schema: 1
        rows:
          - id: ro_efactura
            status: draft
            source_docs: [ro_efactura_ubl]
            articole: [ro_efactura_inbound]
    """,
}


def write(root: Path, files: dict[str, str]) -> Path:
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(dedent(text).lstrip(), encoding="utf-8")
    return root


def with_(name: str, text: str) -> dict[str, str]:
    """BASE with one file replaced or added."""
    return {**BASE, name: text}


def problems(root: Path) -> str:
    with pytest.raises(CatalogError) as err:
        load_catalog(root)
    return "\n".join(err.value.problems)


def articol(body: str) -> str:
    """An Articol file with one row ``ro_efactura_inbound`` and the given fields."""
    head = (
        "catalog: Articol\nfile_schema: 1\nrows:\n  - id: ro_efactura_inbound\n    status: draft\n"
    )
    return head + indent(dedent(body).strip("\n"), "    ") + "\n"


# ----- the repository's own catalog -----


def test_the_repository_catalog_loads():
    load_catalog(ROOT / "catalog")


# ----- loading and lookup -----


def test_a_valid_catalog_loads_and_resolves(tmp_path):
    cat = load_catalog(write(tmp_path, BASE))
    row = cat.get("Articol", "ro_efactura_inbound")
    assert row.procedure == "document" and row.gate.first_n == 5
    assert row.reconcile.tolerance == "0.05" and row.reconcile.expect_accounts == ["401", "4426"]
    assert cat.ids("JobKind") == ["ro_efactura"]
    assert cat.ids("Filing") == []


def test_every_catalog_kind_has_a_row_model():
    assert {
        "Axis",
        "SourceDoc",
        "JobKind",
        "Articol",
        "Mouth",
        "ReconcileProfile",
        "CloseKind",
        "Control",
        "Filing",
        "QuestionKind",
        "ModelRole",
    } <= set(CATALOGS)


def test_money_and_dates_stay_strings(tmp_path):
    cat = load_catalog(write(tmp_path, BASE))
    row = cat.get("Articol", "ro_efactura_inbound")
    assert isinstance(row.valid_from, str) and isinstance(row.reconcile.tolerance, str)


# ----- P10: fail closed -----


@pytest.mark.law("P10")
def test_an_unknown_field_is_refused(tmp_path):
    out = problems(
        write(
            tmp_path,
            with_(
                "30_path/articole.yaml",
                articol("""
        procedure: document
        mouths: [intrare_factura_xml]
        gate: {policy: always}
        colour: blue
    """),
            ),
        )
    )
    assert "ro_efactura_inbound" in out and "colour" in out


@pytest.mark.law("P10")
def test_an_unknown_catalog_is_refused(tmp_path):
    out = problems(write(tmp_path, with_("x.yaml", "catalog: Ledger\nfile_schema: 1\nrows: []\n")))
    assert "unknown catalog 'Ledger'" in out


@pytest.mark.law("P10")
def test_an_unknown_reference_is_refused(tmp_path):
    out = problems(
        write(
            tmp_path,
            with_(
                "30_path/articole.yaml",
                articol("""
        procedure: document
        mouths: [plata_xml]
        gate: {policy: always}
    """),
            ),
        )
    )
    assert "unknown Mouth id 'plata_xml'" in out


@pytest.mark.law("P10")
def test_an_unknown_axis_or_axis_value_is_refused(tmp_path):
    out = problems(
        write(
            tmp_path,
            with_(
                "30_path/articole.yaml",
                articol("""
        procedure: document
        mouths: [intrare_factura_xml]
        gate: {policy: always}
        require: {tva: [tva_lunar]}
        forbid: {regim: [x]}
    """),
            ),
        )
    )
    assert "unknown value 'tva_lunar' of axis 'tva'" in out and "unknown axis 'regim'" in out


@pytest.mark.law("P10")
def test_looking_up_an_unknown_id_or_kind_is_an_error(tmp_path):
    cat = load_catalog(write(tmp_path, BASE))
    with pytest.raises(CatalogError, match="unknown Articol id 'nope'"):
        cat.get("Articol", "nope")
    with pytest.raises(CatalogError, match="unknown catalog 'Ledger'"):
        cat.ids("Ledger")


@pytest.mark.law("P10")
def test_a_repeated_yaml_key_is_refused(tmp_path):
    out = problems(
        write(
            tmp_path,
            with_(
                "30_path/articole.yaml",
                articol("""
        procedure: document
        procedure: close
        mouths: [intrare_factura_xml]
        gate: {policy: always}
    """),
            ),
        )
    )
    assert "repeated key 'procedure'" in out


@pytest.mark.law("P10")
def test_a_file_with_unknown_top_level_keys_or_schema_is_refused(tmp_path):
    out = problems(
        write(tmp_path, with_("y.yaml", "catalog: Filing\nfile_schema: 2\nrows: []\nextra: 1\n"))
    )
    assert "file_schema" in out and "extra" in out


def test_a_yml_file_is_refused(tmp_path):
    out = problems(write(tmp_path, with_("z.yml", "catalog: Filing\nfile_schema: 1\nrows: []\n")))
    assert "z.yml" in out and ".yaml" in out


# ----- P2: an articol names its path and its gate -----


@pytest.mark.law("P2")
def test_an_articol_that_names_no_path_is_refused(tmp_path):
    out = problems(
        write(
            tmp_path,
            with_(
                "30_path/articole.yaml",
                articol("""
        mouths: [intrare_factura_xml]
        gate: {policy: always}
    """),
            ),
        )
    )
    assert "names no path" in out


@pytest.mark.law("P2")
def test_an_articol_with_no_gate_is_refused(tmp_path):
    out = problems(
        write(
            tmp_path,
            with_(
                "30_path/articole.yaml",
                articol("""
        procedure: document
        mouths: [intrare_factura_xml]
    """),
            ),
        )
    )
    assert "has no gate" in out


@pytest.mark.law("P2")
def test_never_is_not_a_gate(tmp_path):
    out = problems(
        write(
            tmp_path,
            with_(
                "30_path/articole.yaml",
                articol("""
        procedure: document
        mouths: [intrare_factura_xml]
        gate: {policy: never}
    """),
            ),
        )
    )
    assert "policy" in out


@pytest.mark.law("P2")
def test_a_document_path_ends_in_a_mouth_and_no_other_path_has_one(tmp_path):
    no_mouth = problems(
        write(
            tmp_path / "a",
            with_(
                "30_path/articole.yaml",
                articol("""
        procedure: document
        gate: {policy: always}
    """),
            ),
        )
    )
    assert "names no mouth" in no_mouth
    close_mouth = problems(
        write(
            tmp_path / "b",
            with_(
                "30_path/articole.yaml",
                articol("""
        procedure: close
        mouths: [intrare_factura_xml]
        gate: {policy: always}
    """),
            ),
        )
    )
    assert "only a document path names a mouth" in close_mouth


def test_a_first_n_gate_names_its_n(tmp_path):
    out = problems(
        write(
            tmp_path,
            with_(
                "30_path/articole.yaml",
                articol("""
        procedure: document
        mouths: [intrare_factura_xml]
        gate: {policy: first_n}
    """),
            ),
        )
    )
    assert "first_n" in out


# ----- status, ids, additive files -----


def test_status_is_required_and_active_needs_the_owners_approval(tmp_path):
    missing = problems(
        write(
            tmp_path / "a",
            with_(
                "50_control/roles.yaml",
                """
        catalog: ModelRole
        file_schema: 1
        rows:
          - id: judge
            system: one
            hank: judge-document
            codon: judge
    """,
            ),
        )
    )
    assert "status" in missing
    unapproved = problems(
        write(
            tmp_path / "b",
            with_(
                "50_control/roles.yaml",
                """
        catalog: ModelRole
        file_schema: 1
        rows:
          - id: judge
            status: active
            system: one
            hank: judge-document
            codon: judge
    """,
            ),
        )
    )
    assert "active only with the owner's approval" in unapproved
    approved = with_(
        "50_control/roles.yaml",
        """
        catalog: ModelRole
        file_schema: 1
        rows:
          - id: judge
            status: active
            approved: "owner, 2026-10-07"
            system: one
            hank: judge-document
            codon: judge
    """,
    )
    assert load_catalog(write(tmp_path / "c", approved)).get("ModelRole", "judge").model is None


def test_ids_are_unique_across_base_and_additive_files(tmp_path):
    out = problems(
        write(
            tmp_path,
            with_(
                "60_practice/more_docs.yaml",
                """
        catalog: SourceDoc
        file_schema: 1
        mode: additive
        rows:
          - id: ro_efactura_ubl
            status: draft
            posting_eligible: false
    """,
            ),
        )
    )
    assert "SourceDoc id 'ro_efactura_ubl' appears twice" in out


def test_additive_rows_append_to_their_base(tmp_path):
    cat = load_catalog(
        write(
            tmp_path,
            with_(
                "60_practice/more_docs.yaml",
                """
        catalog: SourceDoc
        file_schema: 1
        mode: additive
        rows:
          - id: workings
            status: draft
            posting_eligible: false
    """,
            ),
        )
    )
    assert cat.ids("SourceDoc") == ["ro_efactura_ubl", "workings"]


def test_an_additive_file_needs_its_base_and_a_catalog_has_one_base(tmp_path):
    orphan = problems(
        write(
            tmp_path / "a",
            with_(
                "60_practice/filings.yaml",
                """
        catalog: Filing
        file_schema: 1
        mode: additive
        rows: []
    """,
            ),
        )
    )
    assert "additive" in orphan and "no base file" in orphan
    twice = problems(
        write(
            tmp_path / "b",
            with_(
                "60_practice/axes2.yaml",
                """
        catalog: Axis
        file_schema: 1
        rows: []
    """,
            ),
        )
    )
    assert "two base files" in twice


def test_every_problem_is_reported_at_once(tmp_path):
    out = problems(
        write(
            tmp_path,
            with_(
                "30_path/articole.yaml",
                articol("""
        mouths: [plata_xml]
    """),
            ),
        )
    )
    assert "names no path" in out and "has no gate" in out


@pytest.mark.law("P10")
@pytest.mark.parametrize("day", ["2026-02-30", "2026-1-01", "20260101", "1 Jan 2026"])
def test_a_date_is_a_real_iso_day(tmp_path, day):
    out = problems(
        write(
            tmp_path,
            with_(
                "30_path/articole.yaml",
                articol(f"""
        procedure: document
        mouths: [intrare_factura_xml]
        gate: {{policy: always}}
        valid_from: "{day}"
    """),
            ),
        )
    )
    assert "valid_from" in out


def test_a_job_kind_lists_only_document_path_articole(tmp_path):
    out = problems(
        write(
            tmp_path,
            with_(
                "30_path/articole.yaml",
                articol("""
        procedure: close
        gate: {policy: always}
    """),
            ),
        )
    )
    assert "articol 'ro_efactura_inbound' is not on the document path" in out
