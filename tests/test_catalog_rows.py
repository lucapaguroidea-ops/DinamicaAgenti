"""The repository's catalog rows (WP-05) say what ARCHITECTURE.md §4–§6 say."""

from pathlib import Path

import pytest

from kit.catalog import load_catalog

ROOT = Path(__file__).resolve().parents[1]
WATCHED = ["401", "4111", "4426", "4427", "4428", "5121", "5311"]
QUESTIONS = {
    "define_class": ("accountant", "sorting"),
    "bon_cui_unclear": ("accountant", "sorting"),
    "decont_split": ("accountant", "sorting"),
    "define_articol": ("accountant", "document"),
    "v3_approve": ("accountant", "document"),
    "wait_validare": ("saga_agent", "document"),
    "need_rj_export": ("accountant", "reconcile"),
    "recon_ambiguous": ("accountant", "reconcile"),
    "recon_review_contest": ("accountant", "reconcile"),
    "recon_how_mismatch": ("accountant", "reconcile"),
    "v2_close": ("accountant", "close"),
    "v4_codit": ("accountant", "close"),
    "explained_rule": ("accountant", "close"),
    "control_disposition": ("accountant", "close"),
    "filing_receipt": ("accountant", "close"),
}


@pytest.fixture(scope="module")
def cat():
    return load_catalog(ROOT / "catalog")


def rows(cat, kind):
    return [cat.get(kind, i) for i in cat.ids(kind)]


def test_every_row_enters_as_draft(cat):
    assert [(k, i) for k in cat.rows for i, r in cat.rows[k].items() if r.status != "draft"] == []


def test_every_catalog_has_rows(cat):
    assert [k for k, r in cat.rows.items() if not r] == []


def test_each_emitting_source_document_has_exactly_one_job_kind(cat):
    """The job-kind gate: exactly one non-storno Job kind lists a posting-eligible document."""
    plain = [j for j in rows(cat, "JobKind") if not j.storno]
    wrong = {
        d.id: [j.id for j in plain if d.id in j.source_docs]
        for d in rows(cat, "SourceDoc")
        if d.posting_eligible
    }
    assert {d: js for d, js in wrong.items() if len(js) != 1} == {}


def test_storno_is_taken_only_from_the_e_invoice_xml(cat):
    assert [j.source_docs for j in rows(cat, "JobKind") if j.storno] == [["ro_efactura_ubl"]]


def test_a_job_kinds_articole_read_its_documents_fiscal_class(cat):
    wrong = []
    for job in rows(cat, "JobKind"):
        classes = {cat.get("SourceDoc", d).fiscal_class for d in job.source_docs}
        for aid in job.articole:
            art = cat.get("Articol", aid)
            if art.filters.fiscal_class not in classes:
                wrong.append((job.id, aid))
            if bool(art.filters.is_storno) != job.storno:
                wrong.append((job.id, aid, "storno"))
    assert wrong == []


def test_pdf_of_an_e_invoice_never_emits_and_containers_split(cat):
    assert not cat.get("SourceDoc", "ro_efactura_pdf").posting_eligible
    decont = cat.get("SourceDoc", "decont_cheltuieli")
    assert not decont.posting_eligible and decont.split.question == "decont_split"
    assert {s.id for s in rows(cat, "SourceDoc") if s.id.startswith("sink_")} and not any(
        s.posting_eligible for s in rows(cat, "SourceDoc") if s.id.startswith("sink_")
    )


def test_every_mouth_is_used_and_every_posting_mouth_is_validated_by_a_person(cat):
    used = {m for a in rows(cat, "Articol") for m in a.mouths}
    assert sorted(set(cat.ids("Mouth")) - used) == []
    assert [m.id for m in rows(cat, "Mouth") if m.doc_class and m.validare != "person"] == []


def test_approval_policies(cat):
    policy = {a.id: (a.gate.policy, a.gate.first_n) for a in rows(cat, "Articol")}
    assert policy["ro_efactura_inbound"] == policy["ro_efactura_outbound"] == ("first_n", 5)
    assert policy["extras_statement"] == ("first_n", 3)
    for aid in ("foreign_invoice_inbound", "foreign_rc_neplatitor", "bon_cu_cui", "storno_intrare"):
        assert policy[aid] == ("always", None)


def test_the_question_kinds_of_the_architecture(cat):
    have = {q.id: (q.actor, q.procedure) for q in rows(cat, "QuestionKind")}
    assert have == QUESTIONS


def test_the_controls_of_the_month(cat):
    c0 = cat.get("Control", "c0_synthetic_parity")
    assert c0.watched == WATCHED and c0.epsilon == "0.01" and c0.severity == "blocking"
    assert len(cat.ids("Control")) == 14
    blocking_prefile = {c.id for c in rows(cat, "Control") if c.layer == "prefile"}
    assert blocking_prefile == {"p_prefile_duplicate", "p_prefile_hard_failures"}


def test_close_kinds_split_on_exigibility(cat):
    assert cat.get("CloseKind", "close_tva_incasare").watched_extra == ["4428"]
    assert cat.get("CloseKind", "close_standard").forbid == {"exig": ["tva_la_incasare"]}


def test_every_model_role_is_unpinned_until_d3(cat):
    """D3 (the model per role) is the owner's: until then every role refuses (P8)."""
    assert [r.id for r in rows(cat, "ModelRole") if r.model is not None] == []


def test_pre_matching_is_generous(cat):
    pre = cat.get("ReconcileProfile", "pre_doc_nr_date")
    assert pre.number_levels == ["exact", "alnum", "digits_core"] and pre.tolerance == "0.05"
