"""The UBL reader: an RO e-Factura (UBL 2.1, EN 16931, CIUS-RO) read into closed strings.

XML first (P6): where a document exists as XML, the XML is the document and the only extract
source. ``read_spv_zip`` takes the SPV download apart by XML root element, never by file name:
exactly one UBL ``Invoice`` or ``CreditNote``; every other member (the signature, a PDF) is a
companion and is not read. ``parse_ubl`` reads the bindings and enforces the rules quoted in
RESEARCH_LOG R3 (EN 16931 validation artefacts 1.3.16); anything missing, malformed or not tying
is refused (P10). ``for_client`` places the document on the client's side: seller = outbound,
buyer = inbound, neither = refused.

Amounts are strings with two decimals (P10); arithmetic is Decimal, inside this module only.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal
from xml.etree.ElementTree import Element, ParseError

from defusedxml import DefusedXmlException
from defusedxml.ElementTree import fromstring
from pydantic import BaseModel, ConfigDict

from kit.types import cui_is_valid, normalize_cui

UBL = {
    "Invoice": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
    "CreditNote": "urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2",
}
NS = {
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
}
_CENT = Decimal("0.01")


class UblError(ValueError):
    """The document is refused; the message names the rule that failed."""


class Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Party(Closed):
    name: str | None
    vat_id: str | None  # BT-31 / BT-48, with its country prefix
    legal_id: str | None  # BT-30 / BT-47
    cui: str | None  # a Romanian CUI that passes its check digit, else None


class Totals(Closed):
    lines: str  # BT-106
    net: str  # BT-109, tax exclusive
    vat: str  # BT-110, in the document currency
    gross: str  # BT-112, tax inclusive
    payable: str  # BT-115


class Line(Closed):
    id: str
    name: str
    quantity: str | None
    unit_code: str | None
    net: str
    vat_category: str | None
    vat_rate: str | None


class UblDocument(Closed):
    root: Literal["Invoice", "CreditNote"]
    customization_id: str | None
    number: str
    issue_date: str
    type_code: str
    currency: str
    seller: Party
    buyer: Party
    totals: Totals
    lines: list[Line]
    is_storno: bool


class ClientView(Closed):
    client_cui: str
    our_role: Literal["inbound", "outbound"]
    counterparty_cui: str | None
    is_storno: bool


# ----- the SPV zip -----


@dataclass(frozen=True)
class SpvRead:
    invoice: bytes
    invoice_name: str
    companions: list[str]


def _root(data: bytes) -> tuple[str, str] | None:
    """(namespace, local name) of an XML document's root, or None if it is not safe XML."""
    try:
        tag = fromstring(data, forbid_dtd=True).tag
    except (ParseError, DefusedXmlException, ValueError):
        return None
    if tag.startswith("{"):
        ns, local = tag[1:].split("}", 1)
        return ns, local
    return "", tag


def read_spv_zip(data: bytes) -> SpvRead:
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise UblError("not a zip archive") from exc
    invoices: list[tuple[str, bytes]] = []
    companions: list[str] = []
    for info in z.infolist():
        name = info.filename
        if info.is_dir():
            continue
        if name.startswith("/") or ".." in name.split("/"):
            raise UblError(f"unsafe member name {name!r}")
        if not name.lower().endswith(".xml"):
            companions.append(name)  # a PDF or other companion: never read (P6)
            continue
        body = z.read(info)
        root = _root(body)
        if root is not None and UBL.get(root[1]) == root[0]:
            invoices.append((name, body))
        else:
            companions.append(name)  # the signature, or other XML
    if not invoices:
        raise UblError("no UBL invoice in the archive")
    if len(invoices) > 1:
        raise UblError(f"two UBL invoices in one archive: {[n for n, _ in invoices]}")
    ((name, body),) = invoices
    return SpvRead(invoice=body, invoice_name=name, companions=sorted(companions))


# ----- the document -----


def _text(el: Element | None, path: str) -> str | None:
    if el is None:
        return None
    found = el.find(path, NS)
    if found is None or found.text is None or not found.text.strip():
        return None
    return found.text.strip()


def _party(root: Element, role: str) -> Party:
    p = root.find(f"cac:{role}/cac:Party", NS)
    vat_id = None
    if p is not None:
        for scheme in p.findall("cac:PartyTaxScheme", NS):
            if (_text(scheme, "cac:TaxScheme/cbc:ID") or "").upper() == "VAT":
                vat_id = _text(scheme, "cbc:CompanyID")
                break
    legal_id = _text(p, "cac:PartyLegalEntity/cbc:CompanyID")
    cui = None
    for candidate in (vat_id, legal_id):
        if candidate and (candidate.upper().startswith("RO") or candidate[:1].isdigit()):
            if cui_is_valid(candidate):
                cui = normalize_cui(candidate)
                break
    return Party(
        name=_text(p, "cac:PartyLegalEntity/cbc:RegistrationName"),
        vat_id=vat_id,
        legal_id=legal_id,
        cui=cui,
    )


def _amount(raw: str | None, what: str, problems: list[str]) -> Decimal | None:
    if raw is None:
        return None
    try:
        value = Decimal(raw)
    except InvalidOperation:
        problems.append(f"{what}: {raw!r} is not an amount")
        return None
    if "." in raw and len(raw.split(".", 1)[1]) > 2:
        problems.append(f"BR-DEC: {what} {raw!r} has more than two decimals")
    return value


def _money(value: Decimal) -> str:
    return str(value.quantize(_CENT))


def parse_ubl(data: bytes) -> UblDocument:
    try:
        root = fromstring(data, forbid_dtd=True)
    except (DefusedXmlException, ValueError) as exc:
        raise UblError(f"refused: {type(exc).__name__}: DTDs and entities are not read") from exc
    except ParseError as exc:
        raise UblError(f"not well-formed XML: {exc}") from exc
    kind = next((k for k, ns in UBL.items() if root.tag == f"{{{ns}}}{k}"), None)
    if kind is None:
        raise UblError(f"not a UBL Invoice or CreditNote: root {root.tag}")

    problems: list[str] = []
    number = _text(root, "cbc:ID")
    issue_date = _text(root, "cbc:IssueDate")
    type_code = _text(root, f"cbc:{kind}TypeCode")
    currency = _text(root, "cbc:DocumentCurrencyCode")
    for value, rule, what in (
        (number, "BR-02", "invoice number"),
        (issue_date, "BR-03", "issue date"),
        (type_code, "BR-04", "type code"),
        (currency, "BR-05", "currency"),
    ):
        if value is None:
            problems.append(f"{rule}: no {what}")

    seller, buyer = _party(root, "AccountingSupplierParty"), _party(root, "AccountingCustomerParty")
    if not (seller.vat_id or seller.legal_id):
        problems.append("BR-CO-26: the seller has no VAT or legal registration identifier")

    lmt = root.find("cac:LegalMonetaryTotal", NS)
    amounts = {}
    for tag, rule in (
        ("LineExtensionAmount", "BR-12"),
        ("TaxExclusiveAmount", "BR-13"),
        ("TaxInclusiveAmount", "BR-14"),
        ("PayableAmount", "BR-15"),
        ("AllowanceTotalAmount", None),
        ("ChargeTotalAmount", None),
        ("PrepaidAmount", None),
        ("PayableRoundingAmount", None),
    ):
        amounts[tag] = _amount(_text(lmt, f"cbc:{tag}"), tag, problems)
        if rule and amounts[tag] is None:
            problems.append(f"{rule}: no {tag}")
    tax_amounts = [
        t
        for t in root.findall("cac:TaxTotal/cbc:TaxAmount", NS)
        if t.get("currencyID") == currency and t.text
    ]
    if len(tax_amounts) != 1:
        problems.append("BR-CO-15: exactly one total VAT amount in the document currency")
    tax = _amount(tax_amounts[0].text.strip(), "TaxAmount", problems) if tax_amounts else None

    line_tag, qty_tag = (
        ("InvoiceLine", "InvoicedQuantity")
        if kind == "Invoice"
        else ("CreditNoteLine", "CreditedQuantity")
    )
    lines: list[Line] = []
    nets: list[Decimal] = []
    elements = root.findall(f"cac:{line_tag}", NS)
    if not elements:
        problems.append("BR-16: no invoice line")
    for el in elements:
        lid, name = _text(el, "cbc:ID"), _text(el, "cac:Item/cbc:Name")
        raw_net = _text(el, "cbc:LineExtensionAmount")
        net = _amount(raw_net, f"line {lid} LineExtensionAmount", problems)
        if lid is None:
            problems.append("BR-21: a line has no identifier")
        if name is None:
            problems.append(f"BR-25: line {lid} has no item name")
        if net is None:
            problems.append(f"BR-24: line {lid} has no net amount")
            continue
        nets.append(net)
        qty = el.find(f"cbc:{qty_tag}", NS)
        lines.append(
            Line(
                id=lid or "",
                name=name or "",
                quantity=qty.text.strip() if qty is not None and qty.text else None,
                unit_code=qty.get("unitCode") if qty is not None else None,
                net=_money(net),
                vat_category=_text(el, "cac:Item/cac:ClassifiedTaxCategory/cbc:ID"),
                vat_rate=_text(el, "cac:Item/cac:ClassifiedTaxCategory/cbc:Percent"),
            )
        )

    a = amounts
    if not problems:
        zero = Decimal(0)
        if a["LineExtensionAmount"] != sum(nets, zero).quantize(_CENT):
            problems.append("BR-CO-10: the sum of line net amounts differs from BT-106")
        expect_net = (
            a["LineExtensionAmount"]
            - (a["AllowanceTotalAmount"] or zero)
            + (a["ChargeTotalAmount"] or zero)
        )
        if a["TaxExclusiveAmount"] != expect_net:
            problems.append("BR-CO-13: BT-109 differs from lines - allowances + charges")
        if a["TaxInclusiveAmount"] != a["TaxExclusiveAmount"] + tax:
            problems.append("BR-CO-15: BT-112 differs from BT-109 + BT-110")
        expect_due = (
            a["TaxInclusiveAmount"]
            - (a["PrepaidAmount"] or zero)
            + (a["PayableRoundingAmount"] or zero)
        )
        if a["PayableAmount"] != expect_due:
            problems.append("BR-CO-16: BT-115 differs from BT-112 - paid + rounding")
    if problems:
        raise UblError("; ".join(problems))

    return UblDocument(
        root=kind,
        customization_id=_text(root, "cbc:CustomizationID"),
        number=number,
        issue_date=issue_date,
        type_code=type_code,
        currency=currency,
        seller=seller,
        buyer=buyer,
        totals=Totals(
            lines=_money(a["LineExtensionAmount"]),
            net=_money(a["TaxExclusiveAmount"]),
            vat=_money(tax),
            gross=_money(a["TaxInclusiveAmount"]),
            payable=_money(a["PayableAmount"]),
        ),
        lines=lines,
        # a credit note, a 381 type code, or an invoice with negative totals (R3: to confirm)
        is_storno=kind == "CreditNote" or type_code == "381" or a["TaxInclusiveAmount"] < 0,
    )


def for_client(doc: UblDocument, client_cui: str) -> ClientView:
    client = normalize_cui(client_cui)
    seller, buyer = doc.seller.cui == client, doc.buyer.cui == client
    if seller == buyer:
        why = "both parties are" if seller else "neither party is"
        raise UblError(f"{why} the client {client}")
    counterparty = doc.buyer if seller else doc.seller
    return ClientView(
        client_cui=client,
        our_role="outbound" if seller else "inbound",
        counterparty_cui=counterparty.cui,
        is_storno=doc.is_storno,
    )
