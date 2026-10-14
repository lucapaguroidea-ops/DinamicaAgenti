"""Invented firms and their months: documents, and the books SAGA would show if it booked them
as meant (the simulated book). Invented data only: every CUI passes the check digit and names
no real company. VAT rates and amounts are synthetic; the simulated book is a model of SAGA to
be checked against a test firm's real exports (BUILD: the third comparison).
"""

from __future__ import annotations

import hashlib
import io
import random
import zipfile
from dataclasses import dataclass, field
from decimal import Decimal

from kit.recon import JournalLine, SinkDoc, Witness

NS_INV = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
NS_CAC = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
NS_CBC = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
CIUS_RO = "urn:cen.eu:en16931:2017#compliant#urn:efactura.mfinante.ro:CIUS-RO:1.0.1"
RATE = Decimal("21")  # synthetic


@dataclass(frozen=True)
class Firm:
    key: str
    cui: str
    name: str
    axes: dict[str, str]
    folder: str


@dataclass(frozen=True)
class Partner:
    cui: str | None
    vat_id: str
    name: str


FIRMS = {
    "platitor": Firm(
        "platitor",
        "22360671",
        "SINTETIC ALFA SRL",
        {
            "forma": "srl",
            "impozit": "profit_16",
            "tva": "tva_platitor",
            "exig": "tva_la_livrare",
            "cross_border": "none",
            "employees": "has",
        },
        "ALFA",
    ),
    "incasare": Firm(
        "incasare",
        "14142137",
        "SINTETIC BETA SRL",
        {
            "forma": "srl",
            "impozit": "micro_1",
            "tva": "tva_platitor",
            "exig": "tva_la_incasare",
            "cross_border": "none",
            "employees": "none",
        },
        "BETA",
    ),
    "neplatitor": Firm(
        "neplatitor",
        "17320506",
        "SINTETIC GAMA SRL",
        {
            "forma": "srl",
            "impozit": "micro_1",
            "tva": "tva_neplatitor",
            "exig": "tva_la_livrare",
            "cross_border": "inbound_eu_services",
            "employees": "none",
        },
        "GAMA",
    ),
    "abroad": Firm(
        "abroad",
        "26457511",
        "SINTETIC DELTA SRL",
        {
            "forma": "srl",
            "impozit": "profit_16",
            "tva": "tva_platitor",
            "exig": "tva_la_livrare",
            "cross_border": "mixed",
            "employees": "has",
        },
        "DELTA",
    ),
    "bonuri": Firm(
        "bonuri",
        "33166248",
        "SINTETIC EPSILON SRL",
        {
            "forma": "srl",
            "impozit": "micro_1",
            "tva": "tva_platitor",
            "exig": "tva_la_livrare",
            "cross_border": "none",
            "employees": "has",
        },
        "EPSILON",
    ),
}
SUPPLIERS = [
    Partner("69314710", "RO69314710", "FURNIZOR UNU SRL"),
    Partner("41421350", "RO41421350", "FURNIZOR DOI SRL"),
]
CUSTOMERS = [
    Partner("10594636", "RO10594636", "CLIENT UNU SRL"),
    Partner("27182826", "RO27182826", "CLIENT DOI SRL"),
]
FOREIGN = Partner(None, "DE999999999", "KUNDE EINS GMBH")  # an invented foreign VAT id


@dataclass
class GenDoc:
    """One generated document and what it means."""

    name: str
    kind: str  # purchase | sale | foreign_sale | decont
    source_doc_id: str
    number: str
    date: str
    partner: Partner | None
    net: Decimal
    vat: Decimal
    data: bytes  # the UBL, the SPV zip, or the expense report's sheet
    parts: list[GenDoc] = field(default_factory=list)  # an expense report's parts

    @property
    def gross(self) -> Decimal:
        return self.net + self.vat

    @property
    def source_hash(self) -> str:
        return hashlib.sha256(self.data).hexdigest()


def _party(p: Partner | Firm) -> str:
    vat = p.vat_id if isinstance(p, Partner) else f"RO{p.cui}"
    legal = p.cui or ""
    return (
        f"<cac:Party><cac:PartyTaxScheme><cbc:CompanyID>{vat}</cbc:CompanyID>"
        "<cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme></cac:PartyTaxScheme>"
        f"<cac:PartyLegalEntity><cbc:RegistrationName>{p.name}</cbc:RegistrationName>"
        f"{f'<cbc:CompanyID>{legal}</cbc:CompanyID>' if legal else ''}"
        "</cac:PartyLegalEntity></cac:Party>"
    )


def ubl_invoice(
    seller, buyer, number: str, date: str, net: Decimal, vat: Decimal, category: str
) -> bytes:
    gross = net + vat
    rate = "0" if vat == 0 else str(RATE)
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n<Invoice xmlns="{NS_INV}" xmlns:cac="{NS_CAC}" '
        f'xmlns:cbc="{NS_CBC}"><cbc:CustomizationID>{CIUS_RO}</cbc:CustomizationID>'
        f"<cbc:ID>{number}</cbc:ID><cbc:IssueDate>{date}</cbc:IssueDate>"
        "<cbc:InvoiceTypeCode>380</cbc:InvoiceTypeCode>"
        "<cbc:DocumentCurrencyCode>RON</cbc:DocumentCurrencyCode>"
        f"<cac:AccountingSupplierParty>{_party(seller)}</cac:AccountingSupplierParty>"
        f"<cac:AccountingCustomerParty>{_party(buyer)}</cac:AccountingCustomerParty>"
        f'<cac:TaxTotal><cbc:TaxAmount currencyID="RON">{vat:.2f}</cbc:TaxAmount></cac:TaxTotal>'
        "<cac:LegalMonetaryTotal>"
        f'<cbc:LineExtensionAmount currencyID="RON">{net:.2f}</cbc:LineExtensionAmount>'
        f'<cbc:TaxExclusiveAmount currencyID="RON">{net:.2f}</cbc:TaxExclusiveAmount>'
        f'<cbc:TaxInclusiveAmount currencyID="RON">{gross:.2f}</cbc:TaxInclusiveAmount>'
        f'<cbc:PayableAmount currencyID="RON">{gross:.2f}</cbc:PayableAmount>'
        "</cac:LegalMonetaryTotal><cac:InvoiceLine><cbc:ID>1</cbc:ID>"
        '<cbc:InvoicedQuantity unitCode="H87">1</cbc:InvoicedQuantity>'
        f'<cbc:LineExtensionAmount currencyID="RON">{net:.2f}</cbc:LineExtensionAmount>'
        f"<cac:Item><cbc:Name>Servicii {number}</cbc:Name>"
        f"<cac:ClassifiedTaxCategory><cbc:ID>{category}</cbc:ID>"
        f"<cbc:Percent>{rate}</cbc:Percent><cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme>"
        "</cac:ClassifiedTaxCategory></cac:Item>"
        f'<cac:Price><cbc:PriceAmount currencyID="RON">{net:.2f}</cbc:PriceAmount></cac:Price>'
        "</cac:InvoiceLine></Invoice>"
    ).encode()


def spv_zip(invoice: bytes, upload_id: str) -> bytes:
    """An SPV-style download: the invoice and a signature companion (R3: names to confirm)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(f"{upload_id}.xml", invoice)
        z.writestr(
            f"semnatura_{upload_id}.xml",
            b'<Signature xmlns="http://www.w3.org/2000/09/xmldsig#"><SignatureValue>x</SignatureValue></Signature>',
        )
    return buf.getvalue()


def month(
    firm: Firm,
    period: str,
    seed: int = 7,
    purchases: int = 3,
    sales: int = 3,
    eu_service: bool = False,
) -> list[GenDoc]:
    """A small month (BUILD: 10–30 documents at first; fewer here) for one firm, seeded.
    ``eu_service`` adds a service bought from the EU (reverse charge; only where the firm's
    ``cross_border`` admits it)."""
    rnd = random.Random(f"{firm.key}:{period}:{seed}")
    payer = firm.axes["tva"] == "tva_platitor"
    docs: list[GenDoc] = []

    def amount() -> Decimal:
        return Decimal(rnd.randrange(5_000, 500_000)) / 100

    for i in range(purchases):
        sup = SUPPLIERS[i % len(SUPPLIERS)]
        net, date, number = (
            amount(),
            f"{period}-{3 + i:02d}",
            f"FA-{period[2:4]}{period[5:]}{i + 1:03d}",
        )
        vat = (net * RATE / 100).quantize(Decimal("0.01"))  # suppliers are payers
        data = spv_zip(
            ubl_invoice(sup, firm, number, date, net, vat, "S"), f"{rnd.randrange(10**9)}"
        )
        docs.append(
            GenDoc(
                f"purchase {number}",
                "purchase",
                "ro_efactura_ubl",
                number,
                date,
                sup,
                net,
                vat,
                data,
            )
        )
    for i in range(sales):
        net, date = amount(), f"{period}-{10 + i:02d}"
        number = f"{firm.folder}-{period[2:4]}{period[5:]}{i + 1:03d}"
        if firm.axes["cross_border"] == "mixed" and i == sales - 1:
            data = ubl_invoice(firm, FOREIGN, number, date, net, Decimal(0), "K")
            docs.append(
                GenDoc(
                    f"foreign sale {number}",
                    "foreign_sale",
                    "foreign_invoice_xml",
                    number,
                    date,
                    FOREIGN,
                    net,
                    Decimal(0),
                    data,
                )
            )
            continue
        cus = CUSTOMERS[i % len(CUSTOMERS)]
        vat = (net * RATE / 100).quantize(Decimal("0.01")) if payer else Decimal(0)
        data = spv_zip(
            ubl_invoice(firm, cus, number, date, net, vat, "S" if payer else "O"),
            f"{rnd.randrange(10**9)}",
        )
        docs.append(
            GenDoc(f"sale {number}", "sale", "ro_efactura_ubl", number, date, cus, net, vat, data)
        )
    if eu_service:
        if firm.axes["cross_border"] not in ("inbound_eu_services", "mixed"):
            raise ValueError(
                f"{firm.key}: cross_border {firm.axes['cross_border']} buys nothing abroad"
            )
        net, date, number = amount(), f"{period}-15", f"EU-{period[2:4]}{period[5:]}001"
        data = ubl_invoice(FOREIGN, firm, number, date, net, Decimal(0), "AE")
        docs.append(
            GenDoc(
                f"EU service {number}",
                "foreign_purchase",
                "foreign_invoice_xml",
                number,
                date,
                FOREIGN,
                net,
                Decimal(0),
                data,
            )
        )
    if firm.key == "bonuri":
        sup, net, date = SUPPLIERS[1], amount(), f"{period}-20"
        number = f"FD-{period[2:4]}{period[5:]}001"
        vat = (net * RATE / 100).quantize(Decimal("0.01"))
        inner = GenDoc(
            f"expense invoice {number}",
            "purchase",
            "ro_efactura_ubl",
            number,
            date,
            sup,
            net,
            vat,
            ubl_invoice(sup, firm, number, date, net, vat, "S"),
        )
        sheet = f"decont {firm.folder} {period}: {number}".encode()
        docs.append(
            GenDoc(
                f"expense report {period}",
                "decont",
                "decont_cheltuieli",
                "",
                date,
                None,
                Decimal(0),
                Decimal(0),
                sheet,
                parts=[inner],
            )
        )
    return docs


def booked(docs: list[GenDoc]) -> list[GenDoc]:
    """The documents the books should hold: an expense report's parts, not the report itself."""
    out = []
    for d in docs:
        out.extend(d.parts if d.kind == "decont" else [d])
    return out


def to_person(d: GenDoc) -> bool:
    """A document the kit cannot package yet: a non-payer's reverse charge waits on D5."""
    return d.kind == "foreign_purchase"


def simulated_book(firm: Firm, period: str, docs: list[GenDoc]) -> tuple[Witness, dict[str, str]]:
    """What SAGA would show had it booked every document as meant: its documents, journal lines,
    and the balance of 4428 under TVA la încasare. A model of SAGA, never proof of it."""
    payer = firm.axes["tva"] == "tva_platitor"
    vat_account_in = "4428" if firm.axes["exig"] == "tva_la_incasare" else "4426"
    vat_account_out = "4428" if firm.axes["exig"] == "tva_la_incasare" else "4427"
    sink, lines, b4428 = [], [], Decimal(0)
    for n, d in enumerate([x for x in booked(docs) if not to_person(x)], start=1):
        side = "intrare" if d.kind == "purchase" else "iesire"
        key = f"{'I' if side == 'intrare' else 'E'}-{n}"
        cui = d.partner.cui if d.partner else None
        sink.append(
            SinkDoc(
                saga_key=key,
                doc_class=side,
                number=d.number,
                date=d.date,
                partner_cui=cui,
                gross=f"{d.gross:.2f}",
                validated=True,
            )
        )

        def line(account, s, amount, journal, key=key, d=d):
            lines.append(
                JournalLine(
                    saga_key=key,
                    journal=journal,
                    number=d.number,
                    date=d.date,
                    account=account,
                    side=s,
                    amount=f"{amount:.2f}",
                )
            )

        if side == "intrare":
            line("401", "credit", d.gross, "intrari")
            if payer and d.vat:
                line(vat_account_in, "debit", d.vat, "intrari")
                line("628", "debit", d.net, "intrari")
                if vat_account_in == "4428":
                    b4428 -= d.vat
            else:
                line("628", "debit", d.gross, "intrari")
        else:
            line("4111", "debit", d.gross, "iesiri")
            if d.vat:
                line(vat_account_out, "credit", d.vat, "iesiri")
                if vat_account_out == "4428":
                    b4428 += d.vat
            line("704", "credit", d.net, "iesiri")
    balances = {"4428": f"{b4428:.2f}"} if firm.axes["exig"] == "tva_la_incasare" else {}
    return Witness(covered=[period], docs=sink, lines=lines), balances
