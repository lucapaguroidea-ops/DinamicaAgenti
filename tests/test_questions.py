"""Questions (WP-12): closed answer schemas, each kind's check, the answer log (ARCHITECTURE §5)."""

import hashlib
from pathlib import Path

import pytest

from kit.catalog import CatalogError, load_catalog
from kit.questions import AnswerError, answer_question, parse_type, question_hash, validate
from kit.store import open_dossier

ROOT = Path(__file__).resolve().parents[1]
CLIENT = "41526372"


def h(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


@pytest.fixture(scope="module")
def cat():
    return load_catalog(ROOT / "catalog")


@pytest.fixture
def d(tmp_path):
    return open_dossier(tmp_path, CLIENT)


def ask(cat, d, kind, question, answer, actor="person", issue="job:j1"):
    return answer_question(cat, d, issue, kind, question, answer, operator="Ana", actor=actor)


# ----- the type grammar -----


def test_every_answer_shape_in_the_catalog_parses(cat):
    for kind in cat.ids("QuestionKind"):
        for expr in cat.get("QuestionKind", kind).answer.values():
            parse_type(expr)  # raises on a shape the grammar does not know


@pytest.mark.parametrize(
    "expr, good, bad",
    [
        ("bool", True, "true"),
        ("int", 3, True),
        ("slug", "ro_efactura_ubl", "Ro-Efactura"),
        ("cui", "73645193", "73645190"),
        ("period", "2026-09", "2026-9"),
        ("sha256", h("x"), "abc"),
        ("enum(file|hold)", "hold", "close"),
        ("list[int]", [0, 2], [0, "2"]),
        ("object", {"a": 1}, [1]),
        ("str", "spv/1.zip", ""),
    ],
)
def test_types(expr, good, bad):
    assert validate(good, expr) == []
    assert validate(bad, expr) != []


def test_records_in_lists_are_closed():
    expr = "list[{part_hash: sha256, kinds: list[slug], counterparty_cui: cui?}]"
    assert validate([{"part_hash": h("p"), "kinds": ["pdf"]}], expr) == []
    assert any(
        "colour" in e for e in validate([{"part_hash": h("p"), "kinds": [], "colour": 1}], expr)
    )
    assert any("part_hash" in e for e in validate([{"kinds": []}], expr))


def test_an_unknown_type_is_an_error():
    with pytest.raises(ValueError, match="unknown type"):
        parse_type("money")


# ----- answering -----


@pytest.mark.law("P10")
def test_an_unknown_field_or_a_missing_one_asks_again(cat, d):
    q = {"job_id": "j1", "document": {}}
    out = ask(cat, d, "v3_approve", q, {"decision": "approve", "colour": "blue"})
    assert out.status == "asked_again" and "colour" in out.error
    out = ask(cat, d, "v3_approve", q, {"edit": None})
    assert out.status == "asked_again" and "decision" in out.error
    assert [r["outcome"] for r in d.answers("job:j1")] == ["asked_again", "asked_again"]


@pytest.mark.law("P10")
def test_an_unknown_question_kind_is_an_error(cat, d):
    with pytest.raises(CatalogError, match="unknown QuestionKind id 'guess'"):
        ask(cat, d, "guess", {}, {})


def test_an_accepted_answer_is_recorded_with_who_and_what_was_proposed(cat, d):
    q = {"job_id": "j1", "proposed": {"accounts_ok": True, "risk": "low"}}
    out = ask(cat, d, "v3_approve", q, {"decision": "approve", "edit": None})
    assert out.status == "accepted" and out.question_hash == question_hash(q)
    (rec,) = d.answers("job:j1")
    assert rec["operator"] == "Ana" and rec["proposed"] == q["proposed"]
    assert rec["answer"] == {"decision": "approve", "edit": None}


def test_the_question_hash_ignores_the_error_it_was_asked_again_with(cat):
    assert question_hash({"a": 1}) == question_hash({"a": 1, "error": "x"})


def test_the_same_answer_twice_is_one_record(cat, d):
    q = {"job_id": "j1"}
    ask(cat, d, "v3_approve", q, {"decision": "reject", "edit": None})
    ask(cat, d, "v3_approve", q, {"decision": "reject", "edit": None})
    assert len(d.answers("job:j1")) == 1


def test_a_question_for_a_person_is_never_answered_by_an_agent(cat, d):
    with pytest.raises(AnswerError, match="for a person"):
        ask(cat, d, "v3_approve", {"job_id": "j1"}, {"decision": "approve"}, actor="saga_agent")
    with pytest.raises(AnswerError, match="for the SAGA agent"):
        ask(cat, d, "wait_validare", {"job_id": "j1"}, {"validated": False}, actor="person")
    assert d.answers("job:j1") == []


# ----- each kind's check -----


@pytest.mark.parametrize(
    "kind, question, answer, ok",
    [
        ("bon_cui_unclear", {}, {"cu_cui": True, "fara_cui": False}, True),
        ("bon_cui_unclear", {}, {"cu_cui": True, "fara_cui": True}, False),
        ("define_class", {}, {"source_doc_id": "bon_fiscal"}, True),
        ("define_class", {}, {"source_doc_id": "unknown"}, False),
        ("define_class", {}, {"source_doc_id": "contract"}, False),
        (
            "define_articol",
            {"candidates": ["bon_cu_cui", "bon_fara_cui"]},
            {"articol_id": "bon_fara_cui"},
            True,
        ),
        ("define_articol", {"candidates": ["bon_cu_cui"]}, {"articol_id": "bon_fara_cui"}, False),
        ("define_articol", {"candidates": []}, {"articol_id": "extras_statement"}, True),
        ("v3_approve", {}, {"decision": "edit", "edit": {"number": "FV-1"}}, True),
        ("v3_approve", {}, {"decision": "edit", "edit": None}, False),
        ("v3_approve", {}, {"decision": "approve", "edit": {"number": "FV-1"}}, False),
        (
            "recon_ambiguous",
            {"sink_lines": [{}, {}]},
            {"action": "already_posted", "sink_line_ids": [1]},
            True,
        ),
        (
            "recon_ambiguous",
            {"sink_lines": [{}, {}]},
            {"action": "already_posted", "sink_line_ids": []},
            False,
        ),
        (
            "recon_ambiguous",
            {"sink_lines": [{}, {}]},
            {"action": "already_posted", "sink_line_ids": [2]},
            False,
        ),
        (
            "recon_ambiguous",
            {"sink_lines": [{}]},
            {"action": "override_absent", "sink_line_ids": [0]},
            False,
        ),
        ("recon_how_mismatch", {}, {"ack_mismatch": True, "open_storno": False}, True),
        ("recon_how_mismatch", {}, {"ack_mismatch": False, "open_storno": False}, False),
        (
            "need_rj_export",
            {"months": ["2026-08"], "exports": {"rj_9": ["2026-08", "2026-09"]}},
            {"export_id": "rj_9"},
            True,
        ),
        (
            "need_rj_export",
            {"months": ["2026-08"], "exports": {"rj_9": ["2026-09"]}},
            {"export_id": "rj_9"},
            False,
        ),
        ("need_rj_export", {"months": ["2026-08"], "exports": {}}, {"export_id": "rj_9"}, False),
        (
            "v4_codit",
            {},
            {"accept": True, "skip": False, "edit": {"exig": "tva_la_incasare"}},
            True,
        ),
        ("v4_codit", {}, {"accept": True, "skip": True}, False),
        ("v4_codit", {}, {"accept": False, "skip": True, "seed_next": {}}, False),
        (
            "control_disposition",
            {"controls": ["c2_unexplained_empty"]},
            {
                "control_id": "c2_unexplained_empty",
                "disposition": "explained_rule",
                "rule_id": "chirie",
            },
            True,
        ),
        (
            "control_disposition",
            {"controls": ["c2_unexplained_empty"]},
            {"control_id": "c2_unexplained_empty", "disposition": "explained_rule"},
            False,
        ),
        (
            "control_disposition",
            {"controls": ["c2_unexplained_empty"]},
            {"control_id": "c1_outbound_complete", "disposition": "hold"},
            False,
        ),
        (
            "filing_receipt",
            {"filing_id": "d300_platitor", "period": "2026-09"},
            {
                "filing_id": "d300_platitor",
                "period": "2026-09",
                "receipt_key": "spv/1.zip",
                "submitted_by": "Ana",
            },
            True,
        ),
        (
            "filing_receipt",
            {"filing_id": "d300_platitor", "period": "2026-09"},
            {
                "filing_id": "d394_platitor",
                "period": "2026-09",
                "receipt_key": "spv/1.zip",
                "submitted_by": "Ana",
            },
            False,
        ),
    ],
)
def test_kind_checks(cat, d, kind, question, answer, ok):
    actor = "saga_agent" if kind == "wait_validare" else "person"
    out = ask(cat, d, kind, question, answer, actor=actor)
    assert (out.status == "accepted") == ok, out.error


def test_validare_is_accepted_only_when_sagas_snapshot_shows_it(cat, d):
    q = {"job_id": "j1", "validated_keys": ["I-7"]}
    assert (
        ask(
            cat, d, "wait_validare", q, {"validated": True, "saga_doc_key": "I-8"}, "saga_agent"
        ).status
        == "asked_again"
    )
    assert (
        ask(cat, d, "wait_validare", q, {"validated": True}, "saga_agent").status == "asked_again"
    )
    assert (
        ask(
            cat, d, "wait_validare", q, {"validated": True, "saga_doc_key": "I-7"}, "saga_agent"
        ).status
        == "accepted"
    )


@pytest.mark.law("P11")
def test_v2_close_file_is_asked_again_while_material(cat, d):
    material = {"material": True, "blockers": ["c1_outbound_complete: holes"]}
    out = ask(cat, d, "v2_close", material, {"action": "file"}, issue="close:41526372:2026-09")
    assert out.status == "asked_again" and "material" in out.error
    assert (
        ask(cat, d, "v2_close", material, {"action": "hold"}, issue="close:41526372:2026-09").status
        == "accepted"
    )
    unknown = ask(cat, d, "v2_close", {}, {"action": "file"}, issue="close:41526372:2026-10")
    assert unknown.status == "asked_again"  # materiality not stated: fail closed
    clean = {"material": False, "rules": ["chirie"]}
    assert (
        ask(
            cat,
            d,
            "v2_close",
            clean,
            {"action": "file", "explained_rule": "chirie"},
            issue="close:41526372:2026-11",
        ).status
        == "accepted"
    )
    assert (
        ask(
            cat,
            d,
            "v2_close",
            clean,
            {"action": "file", "explained_rule": "other"},
            issue="close:41526372:2026-12",
        ).status
        == "asked_again"
    )


def test_decont_split_reuses_sortings_check(cat, d):
    container = {
        "client_cui": CLIENT,
        "period": "2026-09",
        "source_hash": h("decont"),
        "source_doc_id": "decont_cheltuieli",
        "kinds": ["xlsx"],
        "identity_ok": True,
    }
    good = {"parts": [{"part_hash": h("w"), "source_doc_id": "workings", "kinds": []}]}
    assert (
        ask(cat, d, "decont_split", {"pack": container}, good, issue="batch:b1").status
        == "accepted"
    )
    bad = {"parts": [{"part_hash": h("b"), "source_doc_id": "bon_fiscal", "kinds": ["jpeg"]}]}
    out = ask(cat, d, "decont_split", {"pack": container}, bad, issue="batch:b2")
    assert out.status == "asked_again" and "not a part of" in out.error
