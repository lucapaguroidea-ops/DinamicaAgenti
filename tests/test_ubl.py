"""The UBL reader (WP-07): XML first, EN 16931 bindings and total rules (RESEARCH_LOG R3)."""

import io
import zipfile

import pytest

from kit.ubl import UblError, for_client, parse_ubl, read_spv_zip

CLIENT, PARTNER, OTHER = "41526372", "73645193", "31415920"
CIUS_RO = "urn:cen.eu:en16931:2017#compliant#urn:efactura.mfinante.ro:CIUS-RO:1.0.1"
NS = {
    "Invoice": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
    "CreditNote": "urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2",
}


def party(vat: str | None, legal: str | None, name: str) -> str:
    tax = (
        f"<cac:PartyTaxScheme><cbc:CompanyID>{vat}</cbc:CompanyID>"
        "<cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme></cac:PartyTaxScheme>"
        if vat
        else ""
    )
    legal_id = f"<cbc:CompanyID>{legal}</cbc:CompanyID>" if legal else ""
    return (
        f"<cac:Party>{tax}<cac:PartyLegalEntity><cbc:RegistrationName>{name}</cbc:RegistrationName>"
        f"{legal_id}</cac:PartyLegalEntity></cac:Party>"
    )


def ubl(
    root: str = "Invoice",
    number: str = "FV-0042",
    type_code: str = "380",
    seller=("RO" + PARTNER, None),
    buyer=("RO" + CLIENT, None),
    lines=(("1", "Servicii", "2", "50.00", "100.00", "S", "19"),),
    line_ext="100.00",
    exclusive="100.00",
    tax="19.00",
    inclusive="119.00",
    payable="119.00",
    extra_totals="",
    currency="RON",
) -> bytes:
    line_tag = "InvoiceLine" if root == "Invoice" else "CreditNoteLine"
    qty_tag = "InvoicedQuantity" if root == "Invoice" else "CreditedQuantity"
    body = "".join(
        f"<cac:{line_tag}><cbc:ID>{i}</cbc:ID>"
        f'<cbc:{qty_tag} unitCode="H87">{q}</cbc:{qty_tag}>'
        f'<cbc:LineExtensionAmount currencyID="{currency}">{net}</cbc:LineExtensionAmount>'
        f"<cac:Item><cbc:Name>{name}</cbc:Name><cac:ClassifiedTaxCategory><cbc:ID>{cat}</cbc:ID>"
        f"<cbc:Percent>{rate}</cbc:Percent><cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme>"
        f"</cac:ClassifiedTaxCategory></cac:Item>"
        f'<cac:Price><cbc:PriceAmount currencyID="{currency}">{price}</cbc:PriceAmount></cac:Price>'
        f"</cac:{line_tag}>"
        for i, name, q, price, net, cat, rate in lines
    )
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n<{root} xmlns="{NS[root]}" '
        'xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2" '
        'xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">'
        f"<cbc:CustomizationID>{CIUS_RO}</cbc:CustomizationID>"
        f"<cbc:ID>{number}</cbc:ID><cbc:IssueDate>2026-09-15</cbc:IssueDate>"
        f"<cbc:{root}TypeCode>{type_code}</cbc:{root}TypeCode>"
        f"<cbc:DocumentCurrencyCode>{currency}</cbc:DocumentCurrencyCode>"
        "<cac:AccountingSupplierParty>"
        f"{party(*seller, 'Furnizor SRL')}</cac:AccountingSupplierParty>"
        f"<cac:AccountingCustomerParty>{party(*buyer, 'Client SRL')}</cac:AccountingCustomerParty>"
        f'<cac:TaxTotal><cbc:TaxAmount currencyID="{currency}">{tax}</cbc:TaxAmount></cac:TaxTotal>'
        "<cac:LegalMonetaryTotal>"
        f'<cbc:LineExtensionAmount currencyID="{currency}">{line_ext}</cbc:LineExtensionAmount>'
        f'<cbc:TaxExclusiveAmount currencyID="{currency}">{exclusive}</cbc:TaxExclusiveAmount>'
        f'<cbc:TaxInclusiveAmount currencyID="{currency}">{inclusive}</cbc:TaxInclusiveAmount>'
        f"{extra_totals}"
        f'<cbc:PayableAmount currencyID="{currency}">{payable}</cbc:PayableAmount>'
        f"</cac:LegalMonetaryTotal>{body}</{root}>"
    ).encode()


# ----- reading -----


def test_an_invoice_is_read_into_strings():
    doc = parse_ubl(ubl())
    assert (doc.number, doc.issue_date, doc.type_code, doc.currency) == (
        "FV-0042",
        "2026-09-15",
        "380",
        "RON",
    )
    assert doc.customization_id == CIUS_RO
    assert doc.seller.cui == PARTNER and doc.seller.vat_id == "RO" + PARTNER
    assert doc.buyer.cui == CLIENT and doc.seller.name == "Furnizor SRL"
    assert (doc.totals.net, doc.totals.vat, doc.totals.gross, doc.totals.payable) == (
        "100.00",
        "19.00",
        "119.00",
        "119.00",
    )
    (line,) = doc.lines
    assert (
        line.name,
        line.quantity,
        line.unit_code,
        line.net,
        line.vat_category,
        line.vat_rate,
    ) == (
        "Servicii",
        "2",
        "H87",
        "100.00",
        "S",
        "19",
    )
    assert not doc.is_storno


def test_whole_amounts_are_written_with_two_decimals():
    doc = parse_ubl(ubl(line_ext="100", exclusive="100", tax="19", inclusive="119", payable="119"))
    assert doc.totals.gross == "119.00"


def test_the_client_side_decides_inbound_or_outbound():
    inbound = for_client(parse_ubl(ubl()), CLIENT)
    assert (inbound.our_role, inbound.counterparty_cui) == ("inbound", PARTNER)
    sale = ubl(seller=("RO" + CLIENT, None), buyer=("RO" + PARTNER, None))
    assert for_client(parse_ubl(sale), CLIENT).our_role == "outbound"


def test_a_document_of_another_client_is_refused():
    with pytest.raises(UblError, match=f"neither party is the client {OTHER}"):
        for_client(parse_ubl(ubl()), OTHER)


def test_a_party_without_a_vat_number_is_identified_by_its_legal_registration():
    doc = parse_ubl(ubl(seller=(None, PARTNER)))
    assert doc.seller.cui == PARTNER and doc.seller.vat_id is None


def test_a_foreign_party_has_no_cui():
    doc = parse_ubl(ubl(seller=("DE123456789", None)))
    assert doc.seller.cui is None and doc.seller.vat_id == "DE123456789"
    view = for_client(doc, CLIENT)
    assert view.our_role == "inbound" and view.counterparty_cui is None


# ----- storno -----


def test_a_credit_note_is_storno():
    assert parse_ubl(ubl(root="CreditNote", type_code="381")).is_storno


def test_an_invoice_typed_381_or_with_negative_totals_is_storno():
    assert parse_ubl(ubl(type_code="381")).is_storno
    negative = ubl(
        lines=(("1", "Retur", "-2", "50.00", "-100.00", "S", "19"),),
        line_ext="-100.00",
        exclusive="-100.00",
        tax="-19.00",
        inclusive="-119.00",
        payable="-119.00",
    )
    assert parse_ubl(negative).is_storno


# ----- fail closed (P10) -----


@pytest.mark.law("P10")
@pytest.mark.parametrize(
    "kw, rule",
    [
        (
            {"line_ext": "90.00", "exclusive": "90.00", "inclusive": "109.00", "payable": "109.00"},
            "BR-CO-10",
        ),
        ({"exclusive": "90.00", "inclusive": "109.00", "payable": "109.00"}, "BR-CO-13"),
        ({"inclusive": "120.00", "payable": "120.00"}, "BR-CO-15"),
        ({"payable": "100.00"}, "BR-CO-16"),
        ({"tax": "19.001", "inclusive": "119.001", "payable": "119.001"}, "BR-DEC"),
        ({"number": ""}, "BR-02"),
    ],
)
def test_totals_that_do_not_tie_are_refused(kw, rule):
    with pytest.raises(UblError, match=rule):
        parse_ubl(ubl(**kw))


def test_prepaid_and_rounding_enter_the_amount_due():
    extra = (
        '<cbc:PrepaidAmount currencyID="RON">19.00</cbc:PrepaidAmount>'
        '<cbc:PayableRoundingAmount currencyID="RON">0.01</cbc:PayableRoundingAmount>'
    )
    assert parse_ubl(ubl(extra_totals=extra, payable="100.01")).totals.payable == "100.01"


@pytest.mark.law("P10")
def test_not_a_ubl_invoice_is_refused():
    with pytest.raises(UblError, match="not a UBL Invoice or CreditNote"):
        parse_ubl(b'<?xml version="1.0"?><Order xmlns="urn:x"/>')
    with pytest.raises(UblError, match="not well-formed"):
        parse_ubl(b"<Invoice>")


@pytest.mark.law("P10")
def test_entities_and_dtds_are_refused():
    bomb = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><x>&a;</x>'
    with pytest.raises(UblError, match="refused"):
        parse_ubl(bomb)


@pytest.mark.law("P10")
def test_a_seller_with_no_identifier_is_refused():
    with pytest.raises(UblError, match="BR-CO-26"):
        parse_ubl(ubl(seller=(None, None)))


# ----- the SPV zip (P6: XML first) -----


def spv(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in members.items():
            z.writestr(name, data)
    return buf.getvalue()


SIGNATURE = (
    b'<?xml version="1.0"?><Signature xmlns="http://www.w3.org/2000/09/xmldsig#">'
    b"<SignatureValue>x</SignatureValue></Signature>"
)


def test_the_invoice_is_told_from_its_signature_by_root_element_not_by_name():
    read = read_spv_zip(spv({"semnatura_123.xml": ubl(), "123.xml": SIGNATURE}))
    assert parse_ubl(read.invoice).number == "FV-0042"
    assert read.invoice_name == "semnatura_123.xml" and read.companions == ["123.xml"]


@pytest.mark.law("P6")
def test_a_pdf_beside_the_xml_is_a_companion_and_is_never_read():
    read = read_spv_zip(spv({"123.xml": ubl(), "123.pdf": b"%PDF-1.7 not read"}))
    assert read.invoice_name == "123.xml" and read.companions == ["123.pdf"]


@pytest.mark.law("P10")
@pytest.mark.parametrize(
    "members, why",
    [
        ({"a.xml": SIGNATURE}, "no UBL invoice"),
        ({"a.xml": ubl(), "b.xml": ubl(number="FV-0043")}, "two UBL invoices"),
        ({"../a.xml": ubl()}, "unsafe member name"),
    ],
)
def test_a_wrong_spv_zip_is_refused(members, why):
    with pytest.raises(UblError, match=why):
        read_spv_zip(spv(members))


def test_not_a_zip_is_refused():
    with pytest.raises(UblError, match="not a zip"):
        read_spv_zip(b"plain text")
