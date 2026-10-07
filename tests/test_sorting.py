"""Sorting (WP-06): the emit gates, the Job kind, the container split. Invented CUIs only."""

import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError

from kit.catalog import CatalogError, load_catalog
from kit.sorting import Pack, SplitError, decide, split

ROOT = Path(__file__).resolve().parents[1]
CLIENT, PARTNER = "41526372", "73645193"


def h(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


@pytest.fixture(scope="module")
def cat():
    return load_catalog(ROOT / "catalog")


def pack(**kw) -> Pack:
    base = dict(
        client_cui=CLIENT,
        period="2026-09",
        source_hash=h("doc"),
        source_doc_id="ro_efactura_ubl",
        kinds=["ubl_spv"],
        our_role="inbound",
        counterparty_cui=PARTNER,
        identity_ok=True,
    )
    return Pack(**{**base, **kw})


# ----- emit -----


def test_an_e_invoice_emits_one_job_of_its_kind(cat):
    d = decide(cat, pack())
    assert d.emit and d.job_kind == "ro_efactura" and d.failed == [] and d.question is None
    assert d.job_key == {"client_cui": CLIENT, "source_hash": h("doc")}


def test_a_credit_note_takes_the_storno_kind(cat):
    assert decide(cat, pack(is_storno=True)).job_kind == "storno"


def test_a_storno_of_a_document_without_a_storno_kind_does_not_emit(cat):
    d = decide(cat, pack(source_doc_id="foreign_invoice_xml", kinds=["xml"], is_storno=True))
    assert not d.emit and "job_kind" in d.failed


@pytest.mark.law("P6")
def test_the_pdf_of_an_e_invoice_is_not_primary_and_never_emits(cat):
    d = decide(cat, pack(source_doc_id="ro_efactura_pdf", kinds=["pdf"]))
    assert not d.emit and "class" in d.failed and "primary" in d.failed


def test_an_e_invoice_needs_a_valid_counterparty_cui(cat):
    assert "identity" in decide(cat, pack(counterparty_cui=None)).failed
    assert "identity" in decide(cat, pack(counterparty_cui="73645190")).failed


def test_a_statement_without_the_client_on_it_does_not_emit(cat):
    d = decide(cat, pack(source_doc_id="extras_pdf", kinds=["pdf"], identity_ok=False))
    assert not d.emit and d.failed == ["identity"]
    assert decide(cat, pack(source_doc_id="extras_pdf", kinds=["pdf"])).job_kind == "extras"


def test_primary_kinds_and_incomplete_emit(cat):
    d = decide(cat, pack(kinds=["pdf"]))
    assert not d.emit and "primary" in d.failed
    scan = decide(cat, pack(source_doc_id="foreign_invoice", kinds=["docx"], counterparty_cui=None))
    assert scan.emit and scan.job_kind == "foreign_invoice"


def test_every_failure_is_listed(cat):
    d = decide(
        cat,
        pack(source_doc_id="extras", kinds=["pdf"], identity_ok=False, counterparty_cui=None),
    )
    assert d.failed == ["primary", "identity"]


def test_evidence_and_the_eye_never_emit(cat):
    for doc in ("sink_rj", "sink_balanta", "spv_register", "stat_salarii", "workings"):
        assert not decide(cat, pack(source_doc_id=doc, kinds=[])).emit


# ----- questions -----


def test_an_unknown_file_asks_define_class(cat):
    d = decide(cat, pack(source_doc_id="unknown", kinds=[]))
    assert not d.emit and d.question == "define_class"


def test_a_receipt_asks_whether_the_clients_cui_is_on_it(cat):
    receipt = dict(source_doc_id="bon_fiscal", kinds=["jpeg"], counterparty_cui=None)
    d = decide(cat, pack(**receipt))
    assert not d.emit and d.question == "bon_cui_unclear" and "bon_fork" in d.failed
    answered = decide(cat, pack(**receipt, bon_our_cui_on_doc=False))
    assert answered.emit and answered.job_kind == "bon"


@pytest.mark.law("P10")
def test_a_source_document_missing_from_the_catalog_is_an_error(cat):
    with pytest.raises(CatalogError, match="unknown SourceDoc id 'contract'"):
        decide(cat, pack(source_doc_id="contract"))


@pytest.mark.law("P10")
def test_a_pack_is_closed_and_its_values_checked(cat):
    with pytest.raises(ValidationError):
        pack(colour="blue")
    with pytest.raises(ValidationError):
        pack(client_cui="41526371")
    with pytest.raises(ValidationError):
        pack(source_hash="abc")
    with pytest.raises(ValidationError):
        pack(period="2026-13")


# ----- containers -----

DECONT = dict(source_doc_id="decont_cheltuieli", kinds=["xlsx"], counterparty_cui=None)


def test_a_container_never_emits_and_asks_for_its_parts(cat):
    d = decide(cat, pack(**DECONT))
    assert not d.emit and d.split and d.question == "decont_split"


def test_a_container_without_the_client_on_it_is_not_split(cat):
    d = decide(cat, pack(**DECONT, identity_ok=False))
    assert not d.split and d.question is None and d.failed == ["class", "identity"]


def part(name: str, doc: str, kinds: list[str], **kw) -> dict:
    return {"part_hash": h(name), "source_doc_id": doc, "kinds": kinds, **kw}


def test_confirmed_parts_become_child_packs_through_the_same_gates(cat):
    container = pack(**DECONT)
    answer = {
        "parts": [
            part("inv", "ro_efactura_ubl", ["ubl_spv"], counterparty_cui=PARTNER),
            part("pdf", "ro_efactura_pdf", ["pdf"]),
            part("ev", "decont_part_evidence", ["jpeg"]),
        ]
    }
    children = split(cat, container, answer)
    assert [c.source_hash for c in children] == [h("inv"), h("pdf"), h("ev")]
    assert all(c.client_cui == CLIENT and c.period == "2026-09" and c.identity_ok for c in children)
    assert children[0].our_role == "inbound"  # an expense report holds the client's purchases
    decisions = [decide(cat, c) for c in children]
    assert [(x.emit, x.job_kind) for x in decisions] == [
        (True, "ro_efactura"),
        (False, None),
        (False, None),
    ]


@pytest.mark.parametrize(
    "parts, why",
    [
        ([], "at least one part"),
        ([part("a", "workings", []), part("a", "workings", [])], "unique"),
        ([{**part("x", "workings", []), "part_hash": h("doc")}], "the container's own hash"),
        ([part("b", "bon_fiscal", ["jpeg"])], "not a part of decont_cheltuieli"),
        ([part("c", "ro_efactura_pdf", ["pdf", "xml"])], "its XML: ro_efactura_ubl"),
    ],
)
def test_a_wrong_split_answer_is_asked_again(cat, parts, why):
    with pytest.raises(SplitError, match=why):
        split(cat, pack(**DECONT), {"parts": parts})


@pytest.mark.law("P10")
def test_a_split_answer_is_closed(cat):
    with pytest.raises(SplitError, match="parts.0.colour"):
        split(cat, pack(**DECONT), {"parts": [{**part("a", "workings", []), "colour": "x"}]})
    with pytest.raises(SplitError, match="not a container"):
        split(cat, pack(), {"parts": [part("a", "workings", [])]})
