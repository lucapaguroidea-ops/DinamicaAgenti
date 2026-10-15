"""WP-20: the kit and the shared core (PoartaContabila's ``poarta_contabila.core``, pinned by
commit in ``pyproject.toml``) read the same e-invoices the same way, before any kit module is
replaced by the core's (the module review's direction, owner 2026-10-14, Q-9 and Q-13).

Parity is checked on every synthetic invoice of the core's five invented firms over a quarter:
both readers accept each one and agree on every field they share. Where they differ, the gap is
declared below and asserted exactly, so a change on either side fails here until the owner has
chosen which rule the core keeps.
"""

from __future__ import annotations

import pytest
from poarta_contabila import core
from poarta_contabila.synthetic.months import realistic
from test_ubl import ubl

from kit.ubl import UblError, parse_ubl

PERIODS = ["2026-01", "2026-02", "2026-03"]


def _shared(kit_doc, core_doc) -> dict[str, tuple]:
    """The fields both readers return, side by side (kit, core)."""
    return {
        "number": (kit_doc.number, core_doc.number),
        "issue_date": (kit_doc.issue_date, core_doc.issue_date),
        "type_code": (kit_doc.type_code, core_doc.type_code),
        "currency": (kit_doc.currency, core_doc.currency),
        "root": (kit_doc.root, core_doc.root),
        "seller_cui": (kit_doc.seller.cui, core_doc.supplier.cui),
        "buyer_cui": (kit_doc.buyer.cui, core_doc.customer.cui),
        "net": (kit_doc.totals.net, core_doc.net),
        "vat": (kit_doc.totals.vat, core_doc.vat),
        "gross": (kit_doc.totals.gross, core_doc.gross),
        "payable": (kit_doc.totals.payable, core_doc.payable),
    }


def _corpus() -> list[tuple[str, bytes]]:
    docs = []
    for key, firm in core.synthetic.FIRMS.items():
        for i, invoice in enumerate(realistic(firm, PERIODS, seed=7).invoices()):
            docs.append((f"{key}#{i}", invoice.xml(firm)))
    return docs


def test_the_core_is_pinned_and_imports_no_runtime_stack() -> None:
    import subprocess
    import sys

    assert core.CORE_VERSION == "0.3.0"
    code = (
        "import sys, poarta_contabila.core\n"
        "print(sorted({k.split('.')[0] for k in sys.modules} & "
        "{'langgraph', 'fastapi', 'psycopg', 'httpx', 'boto3', 'google'}))"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "[]"


def test_both_readers_agree_on_every_synthetic_invoice() -> None:
    docs = _corpus()
    assert len(docs) > 100  # the comparison reads the corpus it claims to
    for name, data in docs:
        kit_doc, core_doc = parse_ubl(data), core.parse_ubl(data)
        different = {f: v for f, v in _shared(kit_doc, core_doc).items() if v[0] != v[1]}
        assert not different, (name, different)


# ----- declared gaps: the owner chooses which rule the core keeps (BUILD D9) -----

PARITY_GAPS = {
    # An invoice with no VAT breakdown (cac:TaxTotal/cac:TaxSubtotal): the kit accepts it, the
    # core refuses it ("VAT subtotals do not sum to TaxAmount"). Whether EN 16931 requires the
    # breakdown is [de confirmat] in the artefacts RESEARCH_LOG R3 cites.
    "no_vat_breakdown": ("accepted", "refused"),
}


def _outcome(read, error, data: bytes) -> str:
    try:
        read(data)
    except error:
        return "refused"
    return "accepted"


@pytest.mark.parametrize("gap", sorted(PARITY_GAPS))
def test_each_declared_gap_still_holds_exactly(gap: str) -> None:
    data = {"no_vat_breakdown": ubl()}[gap]  # the kit's own test invoice has no breakdown
    observed = (_outcome(parse_ubl, UblError, data), _outcome(core.parse_ubl, core.UblError, data))
    assert observed == PARITY_GAPS[gap]
