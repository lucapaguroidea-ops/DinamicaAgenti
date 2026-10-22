"""WP-20, the ``synthetic.py`` step: the kit's invented firms and months against the core's
(``core.synthetic``, PoartaContabila's ``poarta_contabila.synthetic``, pinned by commit).

The two modules have the same purpose (invented firms, their documents, and what SAGA would book)
but not the same shape, so they are compared where they can be:

- the firms: the same five keys and names; CUIs, folders, partners and one axis differ;
- the documents: not comparable by seed (each draws its own stream, of different documents),
  so each side's invoices are read by the other side's reader;
- the books: the same document is posted by both, the core's own invoices over a quarter: the
  partner and VAT accounts and every amount agree; the cost and revenue accounts do not.

What the book comparison proves: that both books choose the same partner and VAT accounts on the
same sides, and put the same total on the remaining accounts. The amounts agree largely by
construction (the kit is fed the core's net and VAT, not its own), so the kit's own drawing of VAT
rates is not compared here.

Every difference is declared below with its (kit, core) outcome and asserted exactly, so a
change on either side fails here. While any gap stands the kit keeps ``kit/synthetic.py`` (its
callers need its shapes: ``GenDoc`` bytes and a ``kit.recon.Witness``); the owner frames the
decision (BUILD WP-20).
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

import pytest
from poarta_contabila import core
from poarta_contabila.synthetic.months import realistic

from kit import synthetic as kit
from kit.types import cui_is_valid
from kit.ubl import UblError, parse_ubl, read_spv_zip

PERIODS = ["2026-01", "2026-02", "2026-03"]
SEED = 7
PARTNER_AND_VAT = {"401", "4111", "4426", "4427", "4428"}


def _cents(d: Decimal) -> int:
    return int(d * 100)


def _core_invoices() -> list[tuple[str, object]]:
    """The core's invoices over the quarter that both books post: 360 of its 390. Excluded, each
    for its own reason: the 20 credit notes, because the kit never draws one (gap
    ``month_shape``); the 10 foreign purchases in EUR, because the kit does draw them but its book
    refuses to post them and routes them to a person, while the core's posts them (gap
    ``foreign_purchase_posting``, decided by D5)."""
    out = []
    for key, firm in core.synthetic.FIRMS.items():
        for inv in realistic(firm, PERIODS, seed=SEED).invoices():
            if not (inv.is_credit or inv.foreign or inv.currency != "RON"):
                out.append((key, inv))
    return out


def _kit_doc(inv, kind: str) -> kit.GenDoc:
    """The core's invoice as a kit ``GenDoc`` of *kind*."""
    p = inv.partner
    return kit.GenDoc(
        inv.ref,
        kind,
        "ro_efactura_ubl",
        inv.number,
        inv.issued,
        kit.Partner(p.cui, p.tax_id, p.name),
        Decimal(inv.net) / 100,
        Decimal(inv.vat) / 100,
        b"",
    )


def _kit_posting(key: str, inv) -> dict[str, int]:
    """The core's invoice as a kit ``GenDoc``, posted by the kit's simulated book: account →
    debit minus credit, in cents."""
    gd = _kit_doc(inv, "purchase" if inv.side == "in" else "sale")
    witness, _ = kit.simulated_book(kit.FIRMS[key], inv.period, [gd])
    net: dict[str, int] = defaultdict(int)
    for ln in witness.lines:
        net[ln.account] += _cents(Decimal(ln.amount)) * (1 if ln.side == "debit" else -1)
    return {a: v for a, v in net.items() if v}


def _core_posting(key: str, inv) -> dict[str, int]:
    """The same invoice posted by the core's book, analytics folded to their synthetic account."""
    net: dict[str, int] = defaultdict(int)
    for e in core.synthetic.Book(core.synthetic.FIRMS[key]).post(inv).entries:
        net[e.debit.split(".")[0]] += e.amount
        net[e.credit.split(".")[0]] -= e.amount
    return {a: v for a, v in net.items() if v}


def _split(posting: dict[str, int]) -> tuple[dict[str, int], int]:
    """(the partner and VAT accounts, the total of the rest)."""
    shared = {a: v for a, v in posting.items() if a in PARTNER_AND_VAT}
    return shared, sum(v for a, v in posting.items() if a not in PARTNER_AND_VAT)


# ----- what agrees -----


def test_both_invent_the_same_five_firms_by_key_and_name() -> None:
    assert list(kit.FIRMS) == list(core.synthetic.FIRMS)
    for key, firm in kit.FIRMS.items():
        assert firm.key == core.synthetic.FIRMS[key].key == key
        assert firm.name == core.synthetic.FIRMS[key].name


def test_every_invented_cui_on_both_sides_passes_the_check_digit() -> None:
    kit_cuis = [f.cui for f in kit.FIRMS.values()] + [
        p.cui for p in (*kit.SUPPLIERS, *kit.CUSTOMERS) if p.cui
    ]
    cf = core.synthetic.firms
    core_cuis = [f.cui for f in core.synthetic.FIRMS.values()] + [
        p.cui for p in (*cf.SUPPLIERS, *cf.CUSTOMERS) if p.cui
    ]
    assert all(map(cui_is_valid, kit_cuis + core_cuis))


def test_the_axes_agree_except_exig() -> None:
    for key, firm in kit.FIRMS.items():
        theirs = core.synthetic.FIRMS[key].axes
        assert {a: v for a, v in firm.axes.items() if a != "exig"} == {
            a: v for a, v in theirs.items() if a != "exig"
        }, key


def test_both_books_agree_on_partner_and_vat_accounts_for_every_core_invoice() -> None:
    invoices = _core_invoices()
    assert len(invoices) == 360  # the comparison posts the corpus it claims to, exactly
    for key, inv in invoices:
        kit_shared, kit_rest = _split(_kit_posting(key, inv))
        core_shared, core_rest = _split(_core_posting(key, inv))
        assert kit_shared == core_shared, (key, inv.ref, kit_shared, core_shared)
        assert kit_rest == core_rest, (key, inv.ref, kit_rest, core_rest)


# ----- declared gaps: the module waits on the owner (BUILD WP-20) -----

PARITY_GAPS: dict[str, tuple[object, object]] = {
    # The firms' CUIs: both invented and valid, never the same.
    "firm_cuis": (
        {
            "platitor": "22360671",
            "incasare": "14142137",
            "neplatitor": "17320506",
            "abroad": "26457511",
            "bonuri": "33166248",
        },
        {
            "platitor": "1001012",
            "incasare": "1001020",
            "neplatitor": "1001039",
            "abroad": "1001047",
            "bonuri": "1001055",
        },
    ),
    # The SAGA firm folder.
    "firm_folders": (
        {
            "platitor": "ALFA",
            "incasare": "BETA",
            "neplatitor": "GAMA",
            "abroad": "DELTA",
            "bonuri": "EPSILON",
        },
        {
            "platitor": "0001",
            "incasare": "0002",
            "neplatitor": "0003",
            "abroad": "0004",
            "bonuri": "0005",
        },
    ),
    # The exig axis: the kit's spelling of "at delivery" (the catalog.py gap), and the
    # non-payer, which has an exig in the kit and none in the core.
    "exig_axis": (
        {
            "platitor": "tva_la_livrare",
            "incasare": "tva_la_incasare",
            "neplatitor": "tva_la_livrare",
            "abroad": "tva_la_livrare",
            "bonuri": "tva_la_livrare",
        },
        {
            "platitor": "tva_exig_livrare",
            "incasare": "tva_la_incasare",
            "neplatitor": None,
            "abroad": "tva_exig_livrare",
            "bonuri": "tva_exig_livrare",
        },
    ),
    # The partners: (tax id, name), none shared.
    "partners": (
        [
            ("DE999999999", "KUNDE EINS GMBH"),
            ("RO10594636", "CLIENT UNU SRL"),
            ("RO27182826", "CLIENT DOI SRL"),
            ("RO41421350", "FURNIZOR DOI SRL"),
            ("RO69314710", "FURNIZOR UNU SRL"),
        ],
        [
            ("20010149", "FURNIZOR DELTA SRL"),  # not a VAT payer: no RO prefix
            ("DE000000001", "EXEMPLU SOFTWARE GMBH"),
            ("ESX0000001X", "MODELO SERVICIOS SL"),
            ("NL000000001B01", "EXEMPLU RETAIL BV"),
            ("RO20010114", "FURNIZOR ALFA SRL"),
            ("RO20010122", "FURNIZOR BETA SRL"),
            ("RO20010130", "FURNIZOR GAMA SRL"),
            ("RO20010211", "CLIENT ALFA SRL"),
            ("RO20010220", "CLIENT BETA SRL"),
            ("RO20010238", "CLIENT GAMA SRL"),
        ],
    ),
    # What a month is made of: the kit's GenDoc kinds, the core's document types.
    "month_shape": (
        ["decont", "foreign_purchase", "foreign_sale", "purchase", "sale"],
        ["Bon", "ExpenseReport", "Invoice", "Payroll", "Statement"],
    ),
    # The kit writes its invoices with no VAT breakdown (cac:TaxSubtotal): its reader accepts
    # them, the core's refuses every one, for one of two reasons: the 81 with VAT because the
    # (absent) subtotals do not sum to TaxAmount, the 18 with zero VAT because no subtotal
    # matches the line categories. D9 decides this gap; it is not a separate decision.
    "kit_invoices_without_vat_breakdown": (
        ["accepted"],
        [
            "refused: VAT subtotals [] do not match line categories",
            "refused: VAT subtotals do not sum to TaxAmount",
        ],
    ),
    # Where the net goes: the kit posts every net to 628 (purchases) or 704 (sales); the core to
    # each item's own account.
    "cost_and_revenue_accounts": (
        ["628", "704"],
        ["604", "611", "612", "624", "626", "628", "704", "707"],
    ),
    # The core's foreign purchases in EUR over the quarter (7 for abroad, 3 for neplatitor): the
    # kit's book refuses every one and routes it to a person (``to_person``), posting nothing; the
    # core's posts each, as (debit, credit) synthetic accounts. D5 decides this gap; it is not a
    # separate decision.
    "foreign_purchase_posting": (
        {"abroad": (7, ["to a person"]), "neplatitor": (3, ["to a person"])},
        {
            "abroad": (7, [("4426", "4427"), ("628", "401")]),
            "neplatitor": (3, [("628", "401")]),
        },
    ),
    # The partner accounts: the kit posts to the synthetic 401 / 4111, the core to analytics.
    "partner_accounts": (
        ["401", "4111"],
        [
            "401.00001",
            "401.00002",
            "401.00003",
            "401.00004",
            "4111.00001",
            "4111.00002",
            "4111.00003",
        ],
    ),
}


def _kit_months() -> list[tuple[str, kit.GenDoc]]:
    out = []
    for key, firm in kit.FIRMS.items():
        eu = firm.axes["cross_border"] in ("inbound_eu_services", "mixed")
        for period in PERIODS:
            out += [(key, d) for d in kit.month(firm, period, SEED, eu_service=eu)]
    return out


def _outcome(read, error, data: bytes) -> str:
    try:
        read(data)
    except error as exc:
        return f"refused: {exc}"
    return "accepted"


def _reason(observed: str, declared: list[str]) -> str:
    """The declared outcome *observed* matches (a refusal must say the declared reason)."""
    for d in declared:
        if observed == d or (
            d.startswith("refused: ")
            and observed.startswith("refused: ")
            and d.removeprefix("refused: ") in observed
        ):
            return d
    return observed


def _observed(gap: str) -> tuple[object, object]:
    cf = core.synthetic.firms
    if gap == "firm_cuis":
        return (
            {k: f.cui for k, f in kit.FIRMS.items()},
            {k: f.cui for k, f in core.synthetic.FIRMS.items()},
        )
    if gap == "firm_folders":
        return (
            {k: f.folder for k, f in kit.FIRMS.items()},
            {k: f.folder for k, f in core.synthetic.FIRMS.items()},
        )
    if gap == "exig_axis":
        return (
            {k: f.axes.get("exig") for k, f in kit.FIRMS.items()},
            {k: f.axes.get("exig") for k, f in core.synthetic.FIRMS.items()},
        )
    if gap == "partners":
        return (
            sorted((p.vat_id, p.name) for p in (*kit.SUPPLIERS, *kit.CUSTOMERS, kit.FOREIGN)),
            sorted(
                (p.tax_id, p.name)
                for p in (*cf.SUPPLIERS, *cf.CUSTOMERS, *cf.FOREIGN, *cf.FOREIGN_CUSTOMERS)
            ),
        )
    if gap == "month_shape":
        core_types = {
            type(d).__name__
            for f in core.synthetic.FIRMS.values()
            for d in realistic(f, PERIODS, seed=SEED).docs.values()
        }
        return sorted({d.kind for _, d in _kit_months()}), sorted(core_types)
    if gap == "kit_invoices_without_vat_breakdown":
        declared_kit, declared_core = PARITY_GAPS[gap]
        kit_seen, core_seen, n = set(), set(), 0
        for _, d in _kit_months():
            for part in d.parts if d.kind == "decont" else [d]:
                xml = read_spv_zip(part.data).invoice if part.data[:2] == b"PK" else part.data
                kit_seen.add(_reason(_outcome(parse_ubl, UblError, xml), declared_kit))
                core_seen.add(_reason(_outcome(core.parse_ubl, core.UblError, xml), declared_core))
                n += 1
        assert n == 99  # every invoice the kit draws over the quarter, its parts included
        return sorted(kit_seen), sorted(core_seen)
    if gap == "foreign_purchase_posting":
        kit_seen: dict[str, tuple[int, set]] = {}
        core_seen: dict[str, tuple[int, set]] = {}
        for key, firm in core.synthetic.FIRMS.items():
            for inv in realistic(firm, PERIODS, seed=SEED).invoices():
                if inv.is_credit or not (inv.foreign or inv.currency != "RON"):
                    continue
                assert inv.side == "in" and inv.foreign and inv.currency == "EUR"
                gd = _kit_doc(inv, "foreign_purchase")
                witness, _ = kit.simulated_book(kit.FIRMS[key], inv.period, [gd])
                routed = "to a person" if kit.to_person(gd) and not witness.lines else "booked"
                n, seen = kit_seen.get(key, (0, set()))
                kit_seen[key] = (n + 1, seen | {routed})
                pairs = {
                    (e.debit.split(".")[0], e.credit.split(".")[0])
                    for e in core.synthetic.Book(firm).post(inv).entries
                }
                n, seen = core_seen.get(key, (0, set()))
                core_seen[key] = (n + 1, seen | pairs)
        return (
            {k: (n, sorted(s)) for k, (n, s) in kit_seen.items()},
            {k: (n, sorted(s)) for k, (n, s) in core_seen.items()},
        )
    invoices = _core_invoices()
    if gap == "cost_and_revenue_accounts":
        kit_rest, core_rest = set(), set()
        for key, inv in invoices:
            kit_rest |= set(_kit_posting(key, inv)) - PARTNER_AND_VAT
            core_rest |= set(_core_posting(key, inv)) - PARTNER_AND_VAT
        return sorted(kit_rest), sorted(core_rest)
    if gap == "partner_accounts":
        kit_acc, core_acc = set(), set()
        firms = core.synthetic.FIRMS
        for key, inv in invoices:
            kit_acc |= {a for a in _kit_posting(key, inv) if a in ("401", "4111")}
            for e in core.synthetic.Book(firms[key]).post(inv).entries:
                core_acc |= {a for a in (e.debit, e.credit) if a.split(".")[0] in ("401", "4111")}
        return sorted(kit_acc), sorted(core_acc)
    raise KeyError(gap)


@pytest.mark.parametrize("gap", sorted(PARITY_GAPS))
def test_each_declared_gap_still_holds_exactly(gap: str) -> None:
    assert _observed(gap) == PARITY_GAPS[gap]
