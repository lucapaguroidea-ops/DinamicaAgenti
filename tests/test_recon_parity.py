"""WP-20, the ``recon.py`` step: the kit's PRE / POST matching and settlement proposal against the
core's (``core.recon``: ``poarta_contabila.recon.numbers`` / ``.pre`` / ``.post`` / ``.settle``,
pinned by commit), before any replacement.

The inputs are the core's own synthetic quarter (``core.synthetic``, seed 7, 2026-01..03, the five
firms): its invoices read by the core's UBL reader (``to_canonical``), its bank statements read by
the core's statement reader (``statement_line_document``), and its book as the core's writers
export it and the core's readers read it back (registru jurnal and balanță, the SPV register).
Each side gets the same facts in its own shape:

- the core: ``det_match`` / ``how_check`` / ``propose_settlement`` on the canonical documents, an
  ``ExportEye`` over the exports and the register's invoices (the eye and the register's reader
  come from their home modules: the core's recon reads a ``SagaEye`` it does not re-export);
- the kit: a ``Witness`` whose months, documents, journal lines and register entries are the
  eye's (each journal line split into its debit and its credit side; a register entry's partner
  CUI looked up by the supplier's name among the firm's own partners, since the register names no
  CUI), a ``Doc`` per canonical document, an ``OpenInvoice`` per invoice and a ``BankLine`` per
  statement line whose description is the text the core reads.

Each matcher runs under its own catalog's row of the same profile id (the profile the core's
flux picks for the document). The books are the NextUp export of the core's book: the core writes
its SAGA registru jurnal with ``xlwt``, which the pin does not install, while its NextUp journal
and balance are ``.xlsx`` (the core's own writer and reader either way).

Compared, case by case, on every field both sides expose:

- PRE: every invoice and bank line, against the books of the whole quarter and of February and
  March only, for a job of the document's own month and of March: the verdict, the hits, the near
  misses and the months missing; and which profile each side picks;
- POST: every invoice and bank line, with no expected accounts (the profile's fallback) and with
  each list of expected accounts the kit's articole name, the same list to both, against the same
  two books; each bank line once with its own number and once with the bank's reference: the
  verdict, the expected and used accounts (used folded to the synthetic account), which accounts'
  amounts are off and the months missing; and which profile each side picks;
- the settlement proposal: every bank line against every invoice of the quarter, with nothing
  paid and with what the statement's earlier lines paid: the candidates in order (invoice, full or
  partial, open after, number named, partner named), the invoice an edit settles, the groups;
- the number levels on every number the corpus holds.

Not compared, each for its reason: ``snapshot_id`` (each side hashes its own inputs; that a
verdict is keyed by what it read is tested on each side), the ``reason`` prose, and the fields
only one side has (the core's ``witness``, ``level``, ``rows``, ``require_all``, ``amounts`` (its
off accounts are compared), a candidate's ``source`` and the invoice facts it repeats: the kit's
candidate names the invoice by ``ref``, the rest follows from the invoice).

What it proves: on this corpus every difference falls in a declared gap (a case may show more than
one), and the gaps' counts and the agreeing cases' counts are exact. What it does not prove:
agreement where the two codes differ but no case of the corpus tells them apart (a near miss whose
partner is unknown, a foreign invoice a bank line pays, a partner with more than twelve open
invoices smaller than the line), on the SAGA product's journal names or on bonuri, nor which
profile rows are right, which is the catalog's.

While any gap stands the kit keeps ``kit/recon.py`` (its callers need its shapes: gap
``caller_shapes``); the owner frames the decision (BUILD WP-20).
"""

from __future__ import annotations

import ast
import inspect
import re
import tempfile
from collections import Counter
from decimal import Decimal
from functools import cache
from pathlib import Path

import pytest
from poarta_contabila import core
from poarta_contabila.recon.settle import MAX_CANDIDATES
from poarta_contabila.sinks.exports import ExportEye
from poarta_contabila.sinks.spv_register import read_spv_register, register_invoices
from poarta_contabila.synthetic.months import realistic
from poarta_contabila.types import JobRecord, SourceRef, TenantRef
from test_calendar import _pinned_checkout

from kit import recon as kr
from kit.catalog import load_catalog
from kit.types import cui_is_valid

ROOT = Path(__file__).resolve().parents[1]
PERIODS = ["2026-01", "2026-02", "2026-03"]
SEED = 7
COVERS = (tuple(PERIODS), tuple(PERIODS[1:]))  # the books of the quarter; of Feb and Mar only
SRC = SourceRef(
    kind="ubl_spv", bucket_key="k", content_type="application/xml", source_hash="0" * 64
)


@cache
def _kcat():
    return load_catalog(ROOT / "catalog")


@cache
def _ccat():
    return core.load_catalog(_pinned_checkout())


def _synthetic(account: str) -> str:
    return re.match(r"\d+", account).group(0)


# ----- the corpus: the core's quarter, in each side's shape -----


@cache
def _world(key: str) -> dict:
    firm = core.synthetic.FIRMS[key]
    m = realistic(firm, PERIODS, seed=SEED)
    with tempfile.TemporaryDirectory() as tmp:
        rj = Path(tmp) / "rj.xlsx"
        rj.write_bytes(m.book.nextup_rj())
        lines = core.read_nextup_rj(rj)
        cuis, register = {}, []
        for p in PERIODS:
            bal = Path(tmp) / f"balanta-{p}.xlsx"
            bal.write_bytes(m.book.nextup_balanta(p))
            cuis |= {
                r.account: r.partner_cui for r in core.read_nextup_balanta(bal) if r.partner_cui
            }
            spv = Path(tmp) / f"spv-{p}.xlsx"
            spv.write_bytes(m.book.spv_register(m.invoices(), p))
            register += register_invoices(read_spv_register(spv))
    tenant = TenantRef(cui=firm.cui, saga_firm_folder=firm.folder)
    invoices = []
    for inv in m.invoices():
        job = JobRecord(job_id=inv.ref, tenant=tenant, period=inv.period, status="bound")
        invoices.append(
            (inv, core.to_canonical(core.parse_ubl(inv.xml(firm)), job=job, source=SRC))
        )
    bank = []
    for p in PERIODS:
        stmt = m.docs[f"{p[2:4]}{p[5:]}-extras"]
        read = core.parse_statement(stmt.tables(), core.StatementMeta(**stmt.meta()), firm.cui)
        assert len(read.lines) == len(stmt.lines)
        for i, (ln, drawn) in enumerate(zip(read.lines, stmt.lines, strict=True)):
            job = JobRecord(job_id=f"{stmt.ref}#{i}", tenant=tenant, period=p, status="bound")
            doc = core.statement_line_document(
                read, ln, job=job, bucket_key="k", source_hash="0" * 64
            )
            bank.append((doc, drawn))
    return {
        "firm": firm,
        "kinds": Counter(type(d).__name__ for d in m.docs.values()),
        "lines": lines,
        "cuis": cuis,
        "register": register,
        "invoices": invoices,
        "bank": bank,
    }


def _eye(key: str, cover: tuple[str, ...]):
    w = _world(key)
    return ExportEye(
        product="nextup",
        lines=w["lines"],
        partner_cuis=w["cuis"],
        cui=w["firm"].cui,
        periods=cover,
    )


def _register_cuis(key: str) -> dict[str, str]:
    firm = _world(key)["firm"]
    return {p.name: p.cui for p in (*firm.suppliers, *firm.customers)}


@cache
def _witness(key: str, cover: tuple[str, ...]) -> kr.Witness:
    """The eye's books as a kit ``Witness``: what an export of the covered months holds."""
    w, eye, names = _world(key), _eye(key, cover), _register_cuis(key)
    cui = w["firm"].cui
    docs = [
        kr.SinkDoc(
            saga_key=d.saga_key,
            doc_class=d.doc_class,
            number=d.number,
            date=d.date,
            partner_cui=d.partner_cui,
            gross=d.gross,
            validated=d.validated,
        )
        for p in cover
        for d in eye.documents(cui, p)
    ]
    lines = [
        kr.JournalLine(
            saga_key=f"{ln.product}:{ln.journal}:{ln.doc_number or ''}:{ln.date}",
            journal=ln.journal,
            number=ln.doc_number or "",
            date=ln.date,
            account=account,
            side=side,
            amount=ln.amount,
        )
        for ln in w["lines"]
        if ln.date[:7] in cover
        for side, account in (("debit", ln.debit), ("credit", ln.credit))
    ]
    register = [
        kr.RegisterEntry(
            number=r.number,
            date=r.date,
            partner_cui=names.get(r.supplier),
            gross=r.gross,
            posted=r.posted,
        )
        for r in w["register"]
    ]
    return kr.Witness(covered=list(cover), docs=docs, lines=lines, spv_register=register)


def _kit_doc(doc, period: str, number: str | None = None) -> kr.Doc:
    return kr.Doc(
        doc_class=doc.doc_class,
        number=doc.number if number is None else number,
        date=doc.date,
        partner_cui=doc.partner.cui,
        gross=doc.totals.gross,
        vat=doc.totals.vat,
        period=period,
    )


def _documents(key: str):
    """(fiscal class, canonical document) for every invoice and bank line of the quarter."""
    w = _world(key)
    return [("ro_efactura", d) for _, d in w["invoices"]] + [("extras", d) for d, _ in w["bank"]]


def test_the_corpus_is_the_core_quarter_and_every_invented_cui_is_valid() -> None:
    """Every invoice (the expense reports' 19 invoice parts among them) and every statement line
    of the quarter. Left out, each for its reason: the 14 bonuri, since neither side has a reader
    that makes them a document (the core's readers, ``CORE_MODULES["core.readers"]``, read UBL,
    statements and SAGA / NextUp exports; the kit reads UBL); the 13 expense reports, containers
    whose parts a person names; the 9 payroll statements, which neither side's recon takes
    as a document."""
    kinds = sum((_world(k)["kinds"] for k in core.synthetic.FIRMS), Counter())
    assert kinds == {
        "Invoice": 390,
        "Statement": 15,
        "Bon": 14,
        "ExpenseReport": 13,
        "Payroll": 9,
    }
    assert core.CORE_MODULES["core.readers"] == (
        "poarta_contabila.extract.ubl",
        "poarta_contabila.extract.statement",
        "poarta_contabila.sinks.exports",
    )
    docs = {k: _documents(k) for k in core.synthetic.FIRMS}
    assert sum(1 for v in docs.values() for fc, _ in v if fc == "ro_efactura") == 390
    assert sum(1 for v in docs.values() for fc, _ in v if fc == "extras") == 248
    cuis = {d.partner.cui for v in docs.values() for _, d in v if d.partner.cui}
    cuis |= {f.cui for f in core.synthetic.FIRMS.values()}
    assert cuis and all(map(cui_is_valid, cuis))
    # every register entry's supplier is one of the firm's partners: no CUI is left out
    for key in core.synthetic.FIRMS:
        names = _register_cuis(key)
        assert all(r.supplier in names for r in _world(key)["register"]), key


# ----- PRE -----


def _pre_cases() -> list[tuple[str, object, object]]:
    out = []
    kcat, ccat = _kcat(), _ccat()
    for key in core.synthetic.FIRMS:
        firm, register = _world(key)["firm"], _world(key)["register"]
        for cover in COVERS:
            eye, w = _eye(key, cover), _witness(key, cover)
            for fc, doc in _documents(key):
                cp = core.pre_profile(ccat, doc, fiscal_class=fc, axes=dict(firm.axes))
                kp = kcat.get("ReconcileProfile", cp["profile_id"])
                for period in sorted({doc.period, PERIODS[-1]}):
                    job = JobRecord(
                        job_id=doc.job_id, tenant=doc.tenant, period=period, status="bound"
                    )
                    k = kr.pre_check(kp, _kit_doc(doc, period), w)
                    c = core.det_match(cp, job, doc, core.Witnesses(eye=eye, register=register))
                    out.append((f"{key}:{doc.job_id}:{period}:{cover[0]}", k, c))
    return out


def _pre_view(r) -> list:
    return [r.verdict, list(r.hits), list(r.near), list(r.missing)]


def _hit_kinds(hits: list[str]) -> str:
    kinds = sorted(
        {"spv_register" if h.startswith("register:") else "registru_jurnal" for h in hits}
    )
    return "hits: " + (" + ".join(kinds) or "none")


Tags = list[tuple[str, str, str]]  # (gap, kit outcome, core outcome) per gap a case shows


def _pre_tags(k, c) -> Tags:
    """The declared gaps one PRE case shows; ``unexplained`` when a difference is left."""
    kv, cv, tags = _pre_view(k), _pre_view(c), []
    if k.verdict == "need_export" and c.verdict == "already_posted" and c.witness == "spv_register":
        tags.append(("pre_missing_month_first", k.verdict, f"{c.verdict} by {c.witness}"))
        if not (k.hits or k.near) and k.missing:
            return tags  # the core never reached its missing months
    if k.verdict == "need_export" and c.verdict == "ambiguous" and c.missing:
        tags.append(("pre_need_export_vocabulary", k.verdict, f"{c.verdict}: need_rj_export"))
        cv[0] = k.verdict
    book_hits = [h for h in c.hits if not h.startswith("register:")]
    if book_hits != c.hits:
        tags.append(("pre_register_hits_listed", _hit_kinds(k.hits), _hit_kinds(c.hits)))
        cv[1] = book_hits
    if kv != cv:
        tags.append(("unexplained", str(kv), str(_pre_view(c))))
    return tags


def _tally(cases) -> dict[str, tuple[dict, dict]]:
    """``{gap: (kit outcomes, core outcomes)}`` with counts; ``agree`` for the cases with no gap,
    by verdict (a case showing two gaps counts under each)."""
    kit_seen: dict[str, Counter] = {}
    core_seen: dict[str, Counter] = {}
    for tags, k_agree, c_agree in cases:
        for gap, kl, cl in tags or [("agree", k_agree, c_agree)]:
            kit_seen.setdefault(gap, Counter())[kl] += 1
            core_seen.setdefault(gap, Counter())[cl] += 1
    return {g: (dict(kit_seen[g]), dict(core_seen[g])) for g in kit_seen}


@cache
def _pre_tally() -> dict[str, tuple[dict, dict]]:
    cases = _pre_cases()
    assert len(cases) == 2102  # the comparison runs the cases it claims to, exactly
    return _tally((_pre_tags(k, c), k.verdict, c.verdict) for _, k, c in cases)


def test_both_pick_the_same_pre_profile_for_every_document() -> None:
    kcat, ccat = _kcat(), _ccat()
    seen = Counter()
    for key in core.synthetic.FIRMS:
        axes = dict(_world(key)["firm"].axes)
        for fc, doc in _documents(key):
            cp = core.pre_profile(ccat, doc, fiscal_class=fc, axes=axes)
            kp = kr.pick_profile(kcat, "pre", fc)
            assert kp is not None and cp is not None and kp.id == cp["profile_id"], doc.job_id
            seen[kp.id] += 1
    assert seen == {"pre_doc_nr_date": 390, "pre_extras_date_gross": 248}


def test_pre_agrees_on_every_shared_field_outside_the_declared_gaps() -> None:
    tally = _pre_tally()
    assert "unexplained" not in tally, tally.get("unexplained")
    assert tally["agree"] == AGREE_PRE
    assert set(tally) - {"agree"} == {g for g in PARITY_GAPS if g.startswith("pre_")}


# ----- POST -----


def _expects() -> list[tuple[str, ...]]:
    """No expected accounts (the profile's fallback), and every list the kit's articole name."""
    kcat = _kcat()
    lists = {()}
    for i in kcat.ids("Articol"):
        row = kcat.get("Articol", i)
        if row.reconcile is not None:
            lists.add(tuple(row.reconcile.expect_accounts))
    return sorted(lists)


def _kit_off(r) -> list[str]:
    """The accounts whose amounts the kit finds off (its reason is its only report of them)."""
    return sorted(re.findall(r"(\S+) moves ", r.reason)) if r.verdict == "how_mismatch" else []


def _post_view(k, c) -> tuple[list, list]:
    kit = [
        k.verdict,
        list(k.expected),
        sorted({_synthetic(u) for u in k.used}),
        _kit_off(k),
        list(k.missing),
    ]
    off = sorted(a.account for a in c.amounts if not a.ok)
    return kit, [c.verdict, list(c.expected), list(c.used), off, list(c.missing)]


def _post_cases() -> list[tuple[str, str, bool, tuple, str, object, object]]:
    """(case, fiscal class, by reference, expected, profile, kit, core). The kit is given each
    document's own number; each bank line once more with the bank's reference as its number
    (``core.packaged_number``, what SAGA holds the line under), *by reference*."""
    out = []
    kcat, ccat = _kcat(), _ccat()
    for key in core.synthetic.FIRMS:
        firm = _world(key)["firm"]
        for cover in COVERS:
            eye, w = _eye(key, cover), _witness(key, cover)
            for fc, doc in _documents(key):
                cp = core.pre_profile(
                    ccat, doc, fiscal_class=fc, axes=dict(firm.axes), stage="post"
                )
                kp = kcat.get("ReconcileProfile", cp["profile_id"])
                numbers = [(False, doc.number)]
                if fc == "extras":
                    numbers.append((True, core.packaged_number(doc)))
                for by_reference, number in numbers:
                    kd = _kit_doc(doc, doc.period, number=number)
                    for expect in _expects():
                        k = kr.post_check(kp, list(expect), kd, w)
                        articol = {"reconcile": {"expect_accounts": list(expect)}}
                        c = core.how_check(doc, articol, cp, eye, firm.cui)
                        case = f"{key}:{doc.job_id}:{cover[0]}"
                        out.append((case, fc, by_reference, expect, cp["profile_id"], k, c))
    return out


def _post_tags(fc: str, by_reference: bool, expect: tuple, pid: str, k, c) -> Tags:
    """The declared gaps one POST case shows; ``unexplained`` when a difference is left. Each
    gap's difference is set aside once tagged, so a case may show several."""
    (kv, cv), tags = _post_view(k, c), []
    if fc == "extras" and not by_reference and not k.used and c.rows:
        found = "posting found"
        return [
            ("post_bank_line_number", f"{k.verdict}, no posting found", f"{c.verdict}, {found}")
        ]
    if k.verdict == "need_export" and c.verdict == "need_rj_export":
        tags.append(("post_need_export_vocabulary", k.verdict, c.verdict))
        cv[0] = k.verdict
    if set(cv[2]) < set(kv[2]):
        other = " ".join(sorted(set(kv[2]) - set(cv[2])))
        tags.append(("post_other_journals", f"used also {other}", "the posting's journal only"))
        cv[2] = kv[2]
    listed = set(_ccat().recon_profiles[pid].get("account_amounts") or {})
    unlisted = [a for a in kv[3] if a not in listed]
    if unlisted:
        tags.append(
            ("post_amount_accounts", f"amounts off on {' '.join(unlisted)}", "amounts not compared")
        )
        kv[3] = [a for a in kv[3] if a in listed]
        if not kv[3] and c.verdict == "how_ok":
            kv[0] = c.verdict  # the kit's only complaint was an amount the core does not compare
    if not expect and kv[1] != cv[1]:
        tags.append(
            ("post_fallback_accounts", f"{pid}: {' '.join(kv[1])}", f"{pid}: {' '.join(cv[1])}")
        )
        cv[1] = kv[1]
        cv[3] = [a for a in cv[3] if a in kv[1]]  # the core checks the amounts of more accounts
    if pid == "post_how_4428" and k.reason.startswith("expected accounts not used"):
        if c.verdict == "how_ok" or cv[3]:
            core_saw = c.verdict + (f": amounts off on {' '.join(cv[3])}" if cv[3] else "")
            tags.append(("post_how_4428_require_all", "how_mismatch: not all used", core_saw))
            cv[0], cv[3] = kv[0], kv[3]
    if kv != cv:
        tags.append(("unexplained", str(_post_view(k, c)[0]), str(_post_view(k, c)[1])))
    return tags


@cache
def _post_tally() -> dict[str, tuple[dict, dict]]:
    cases = _post_cases()
    # (390 invoices + 248 bank lines + the 248 again by reference) × 6 lists × 2 books
    assert len(cases) == 10632
    out = _tally(
        (_post_tags(fc, ref, e, pid, k, c), k.verdict, c.verdict)
        for _, fc, ref, e, pid, k, c in cases
    )
    analytic = sum(
        1
        for *_, k, c in cases
        if sorted(set(k.used)) != c.used and sorted({_synthetic(u) for u in k.used}) == c.used
    )
    out["post_used_accounts"] = ({"analytic accounts": analytic}, {"synthetic accounts": analytic})
    return out


def test_post_agrees_on_every_shared_field_outside_the_declared_gaps() -> None:
    tally = _post_tally()
    assert "unexplained" not in tally, tally.get("unexplained")
    assert tally["agree"] == AGREE_POST
    assert set(tally) - {"agree"} == {g for g in PARITY_GAPS if g.startswith("post_")} - {
        "post_profile_selection"
    }


# ----- the settlement proposal -----


def _settle_key(doc) -> tuple[str, str]:
    return core.settle_key(doc.partner.cui or "", doc.number)


def _settle_cases() -> list[tuple[str, object, object]]:
    """Every bank line against every invoice of the quarter; with nothing paid, and with what the
    statement's earlier lines paid (the core's ``paid`` by ``settle_key``, the kit's ``paid``)."""
    out = []
    for key in core.synthetic.FIRMS:
        w = _world(key)
        by_ref = {inv.ref: doc for inv, doc in w["invoices"]}
        jobs = [core.InvoiceJob(inv.ref, doc) for inv, doc in w["invoices"]]
        for with_paid in (False, True):
            paid: dict[tuple[str, str], Decimal] = {}
            for line, drawn in w["bank"]:
                text = " ".join([*(ln.desc for ln in line.lines), line.partner.name or ""])
                kit_line = kr.BankLine(
                    doc_class=line.doc_class,
                    date=line.date,
                    gross=line.totals.gross,
                    description=text,
                )
                kit_invoices = [
                    kr.OpenInvoice(
                        ref=inv.ref,
                        doc_class=doc.doc_class,
                        number=doc.number,
                        date=doc.date,
                        partner_cui=doc.partner.cui,
                        partner_name=doc.partner.name,
                        gross=doc.totals.gross,
                        paid=f"{paid.get(_settle_key(doc), 0):.2f}",
                    )
                    for inv, doc in w["invoices"]
                ]
                k = kr.propose_settlement(kit_line, kit_invoices)
                c = core.propose_settlement(line, jobs, paid=dict(paid))
                out.append((f"{key}:{line.job_id}:{'paid' if with_paid else 'open'}", k, c))
                for ref, cents in drawn.settles if with_paid else ():
                    key_ = _settle_key(by_ref[ref])
                    paid[key_] = paid.get(key_, Decimal(0)) + Decimal(cents) / 100
    return out


def _settle_view(k, c) -> tuple[tuple, tuple]:
    kit = (
        [(x.ref, x.kind, x.open_after, x.named_number, x.named_partner) for x in k.candidates],
        (k.edit["settles"], k.edit["partner_cui"]) if k.edit else None,
        [list(g) for g in k.groups],
    )
    core_ = (
        [
            (
                x.factura_id,
                x.cover,
                x.open_after,
                "number_in_text" in x.hits,
                "name_in_text" in x.hits,
            )
            for x in c.candidates
        ],
        (c.edit["maps"]["factura_id"], c.edit["partner"]["cui"]) if c.edit else None,
        [sorted(i.factura_id for i in g.invoices) for g in c.groups],
    )
    return kit, core_


def _settle_tags(k, c) -> Tags:
    """The declared gap one settlement case shows; ``unexplained`` when a difference is left."""
    kv, cv = _settle_view(k, c)
    if kv == cv:
        return []
    if kv[1:] == cv[1:] and len(cv[0]) == MAX_CANDIDATES < len(kv[0]) and set(cv[0]) <= set(kv[0]):
        return [("settle_at_most_five", f"{len(kv[0])} candidates", f"{len(cv[0])} candidates")]
    if kv[1:] == cv[1:] and sorted(kv[0]) == sorted(cv[0]):
        return [("settle_tie_order", "ties in the invoices' order", "ties newest first")]
    if kv[0] == cv[0] and kv[2] == cv[2] and cv[2] and kv[1] and not cv[1]:
        return [("settle_edit_beside_a_group", "an edit", "no edit")]
    return [("unexplained", str(kv), str(cv))]


@cache
def _settle_tally() -> dict[str, tuple[dict, dict]]:
    cases = _settle_cases()
    assert len(cases) == 496  # 248 bank lines, with nothing paid and with what was paid before
    return _tally(
        (_settle_tags(k, c), f"{len(k.candidates)} candidates", f"{len(c.candidates)} candidates")
        for _, k, c in cases
    )


def test_the_settlement_proposals_agree_outside_the_declared_gaps() -> None:
    tally = _settle_tally()
    assert "unexplained" not in tally, tally.get("unexplained")
    assert tally["agree"] == AGREE_SETTLE
    assert set(tally) - {"agree"} == {g for g in PARITY_GAPS if g.startswith("settle_")} - {
        "settle_inputs",
        "settle_edit_shape",
    }


# ----- the number levels -----


def test_both_normalize_every_number_of_the_corpus_alike() -> None:
    """The kit's ``normalize_number`` and the core's ``normalize`` on every invoice, book and
    register number at each level. Nothing is left empty on this corpus (the kit says ``""``,
    the core ``None``)."""
    numbers = set()
    for key in core.synthetic.FIRMS:
        w = _world(key)
        numbers |= {d.number for _, d in _documents(key)}
        numbers |= {ln.doc_number for ln in w["lines"] if ln.doc_number}
        numbers |= {r.number for r in w["register"]}
    assert len(numbers) == 944
    for n in numbers:
        for level in ("exact", "alnum", "digits_core"):
            kit_n, core_n = kr.normalize_number(n, level), core.normalize(n, level)
            assert kit_n and kit_n == core_n, (n, level, kit_n, core_n)


# ----- declared gaps: the module waits on the owner (BUILD WP-20) -----

PARITY_GAPS: dict[str, tuple[object, object]] = {
    # A month the books do not cover: the kit says need_export, the core ambiguous with the
    # reason need_rj_export (its PRE verdicts have no need_export); the missing months agree.
    "pre_need_export_vocabulary": ({"need_export": 230}, {"ambiguous: need_rj_export": 230}),
    # A month not covered while the SPV register lists the invoice as posted: the kit stops at the
    # missing month, the core matches first and finds the invoice in the register.
    "pre_missing_month_first": ({"need_export": 142}, {"already_posted by spv_register": 142}),
    # In the books and in the SPV register: the core lists the register's invoice among the
    # hits, the kit only the books' document (the verdict agrees).
    "pre_register_hits_listed": (
        {"hits: registru_jurnal": 598},
        {"hits: registru_jurnal + spv_register": 598},
    ),
    # Which POST profile, per firm: the kit's pick_profile, by fiscal class alone, finds two
    # defaults and returns None for every document (its caller must name a close kind's profile);
    # the core's flux picks one by the firm's axes.
    "post_profile_selection": (
        {
            "platitor": [None],
            "incasare": [None],
            "neplatitor": [None],
            "abroad": [None],
            "bonuri": [None],
        },
        {
            "platitor": ["post_doc_how"],
            "incasare": ["post_how_4428"],
            "neplatitor": ["post_doc_how"],
            "abroad": ["post_doc_how"],
            "bonuri": ["post_doc_how"],
        },
    ),
    # The month not covered: need_export in the kit, need_rj_export in the core.
    "post_need_export_vocabulary": ({"need_export": 1488}, {"need_rj_export": 1488}),
    # No expected accounts: each falls back to its own row's accounts (gap profile_rows); where
    # the core checks the amounts of more accounts, only the kit's are compared.
    "post_fallback_accounts": (
        {"post_doc_how: 401 4111": 1089, "post_how_4428: 401 4111 4428": 249},
        {"post_doc_how: 401 4111 4426 4427": 1089, "post_how_4428: 4428": 249},
    ),
    # VAT at collection (post_how_4428): the kit's row requires every expected account, the
    # core's one, so the kit refuses a posting that misses one; the core passes it, or refuses it
    # for an amount.
    "post_how_4428_require_all": (
        {"how_mismatch: not all used": 289},
        {
            "how_ok": 226,
            "how_mismatch: amounts off on 4111": 1,
            "how_mismatch: amounts off on 4428": 62,
        },
    ),
    # The kit checks the amounts on 401 / 4111 (gross) and 4426 / 4427 / 4428 (VAT) whatever the
    # profile, the core only on the accounts its profile's account_amounts lists: on the
    # VAT-at-collection firm's bank lines (VAT 0.00) the kit finds 4426 / 4427 off where the core
    # compares nothing.
    "post_amount_accounts": (
        {"amounts off on 4427": 30, "amounts off on 4426": 32},
        {"amounts not compared": 62},
    ),
    # The kit reads every journal's lines under the number and date, the core only the posting's
    # journal (JC / JV for an invoice, JB for a bank line): a salary payment's reference also
    # names the payroll entry.
    "post_other_journals": (
        {"used also 4315 4316 436 444 641 646": 90},
        {"the posting's journal only": 90},
    ),
    # Given a bank line's own number (EXT-...), the kit finds no posting of any bank line: SAGA
    # holds the line under the bank's reference, which the core reads from the document
    # (packaged_number) and the kit's Doc cannot carry. Given the reference (the cases "by
    # reference"), the kit finds the posting and compares like an invoice.
    "post_bank_line_number": (
        {"how_mismatch, no posting found": 2604},
        {"how_mismatch, posting found": 1062, "how_ok, posting found": 1542},
    ),
    # used: the kit lists the accounts as booked (analytics), the core folded to synthetic
    # accounts; they agree once folded.
    "post_used_accounts": ({"analytic accounts": 6186}, {"synthetic accounts": 6186}),
    # More than five candidates: the kit lists them all, the core the first five; those five
    # are among the kit's, and the edit and the groups agree.
    "settle_at_most_five": (
        {
            "8 candidates": 9,
            "10 candidates": 7,
            "9 candidates": 5,
            "6 candidates": 22,
            "11 candidates": 5,
            "7 candidates": 12,
            "13 candidates": 2,
            "12 candidates": 2,
        },
        {"5 candidates": 64},
    ),
    # Candidates of equal rank: the kit keeps the invoices' order, the core puts the newest first.
    "settle_tie_order": ({"ties in the invoices' order": 103}, {"ties newest first": 103}),
    # One candidate leads but a group of invoices fits as well: the kit proposes the edit,
    # the core none.
    "settle_edit_beside_a_group": ({"an edit": 1}, {"no edit": 1}),
    # The parameters: the core also proposes the invoices the books show (books), leaves out those
    # settled elsewhere (settled_ids, settled_numbers) and takes what was paid by settle_key; the
    # kit takes paid per invoice and has no books. Here the core's books and settled sets stay
    # empty (the kit has no such input) and what was paid goes to both.
    "settle_inputs": (
        ["line", "invoices"],
        ["line", "invoices", "books", "settled_ids", "settled_numbers", "paid"],
    ),
    # The edit's keys (and the core's maps): compared above as the invoice and the partner CUI.
    "settle_edit_shape": (
        [("partner_cui", "settles")],
        [("maps", "partner", "factura_id", "factura_numar")],
    ),
    # The two catalogs' rows of the same six profile ids, (kit, core) per differing field. They
    # are catalog rows (the catalog.py step); the POST gaps on fallback, require_all and amounts
    # follow from them.
    "profile_rows": (
        {
            "post_bon_how": {"account_amounts": None, "fallback_accounts": []},
            "post_doc_how": {"account_amounts": None, "fallback_accounts": ["401", "4111"]},
            "post_how_4428": {
                "account_amounts": None,
                "fallback_accounts": ["401", "4111", "4428"],
                "require_all_accounts": True,
            },
            "pre_bon_date_gross": {"fallback_accounts": []},
            "pre_doc_nr_date": {"match_keys": ["number", "date", "gross"]},
            "pre_extras_date_gross": {"fallback_accounts": []},
        },
        {
            "post_bon_how": {
                "account_amounts": {"4426": "vat"},
                "fallback_accounts": ["6", "4426"],
            },
            "post_doc_how": {
                "account_amounts": {"401": "gross", "4111": "gross", "4426": "vat", "4427": "vat"},
                "fallback_accounts": ["401", "4111", "4426", "4427"],
            },
            "post_how_4428": {
                "account_amounts": {"401": "gross", "4111": "gross", "4428": "vat"},
                "fallback_accounts": ["4428"],
                "require_all_accounts": False,
            },
            "pre_bon_date_gross": {"fallback_accounts": ["6"]},
            "pre_doc_nr_date": {"match_keys": ["number", "date"]},
            "pre_extras_date_gross": {"fallback_accounts": ["5121", "5311"]},
        },
    ),
    # What the kit's other modules import from kit.recon, and the core's namesake: Witness, Doc,
    # JournalLine and the three functions have none (the core takes a SagaEye, a CanonicalDocument
    # and a JobRecord), and the core's SinkDoc has more fields.
    "caller_shapes": (
        {
            "Day": None,
            "Doc": ["date", "doc_class", "gross", "number", "partner_cui", "period", "vat"],
            "JournalLine": ["account", "amount", "date", "journal", "number", "saga_key", "side"],
            "Money": None,
            "SinkDoc": [
                "date",
                "doc_class",
                "gross",
                "number",
                "partner_cui",
                "saga_key",
                "validated",
            ],
            "Witness": ["covered", "docs", "lines", "spv_register"],
            "pick_profile": None,
            "post_check": None,
            "pre_check": None,
        },
        {
            "Day": "absent",
            "Doc": "absent",
            "JournalLine": "absent",
            "Money": None,
            "SinkDoc": [
                "analytic",
                "date",
                "doc_class",
                "gross",
                "net",
                "number",
                "partner_cui",
                "saga_key",
                "validated",
                "vat",
            ],
            "Witness": "absent",
            "pick_profile": "absent",
            "post_check": "absent",
            "pre_check": "absent",
        },
    ),
}

# What agrees, by verdict (PRE, POST) or by the number of candidates (settlement): (kit, core).
AGREE_PRE = (
    {"already_posted": 1058, "ambiguous": 44, "absent": 30},
    {"already_posted": 1058, "ambiguous": 44, "absent": 30},
)
AGREE_POST = ({"how_ok": 2240, "how_mismatch": 2943}, {"how_ok": 2240, "how_mismatch": 2943})
AGREE_SETTLE = (
    {
        "0 candidates": 116,
        "1 candidates": 114,
        "2 candidates": 79,
        "4 candidates": 3,
        "3 candidates": 16,
    },
    {
        "0 candidates": 116,
        "1 candidates": 114,
        "2 candidates": 79,
        "4 candidates": 3,
        "3 candidates": 16,
    },
)


def _profile_fields(kit_row, core_row) -> tuple[dict, dict]:
    kit = {
        "match_keys": list(kit_row.match_keys),
        "number_levels": list(kit_row.number_levels),
        "tolerance": kit_row.tolerance,
        "require_all_accounts": kit_row.require_all_accounts,
        "fallback_accounts": list(kit_row.fallback_accounts),
        "account_amounts": None,
    }
    core_ = {
        "match_keys": list(core_row.get("match_keys") or []),
        "number_levels": list(core_row.get("number_match") or []),
        "tolerance": str(core_row.get("tolerance")),
        "require_all_accounts": bool(core_row.get("require_all_accounts")),
        "fallback_accounts": [str(a) for a in core_row.get("fallback_accounts") or []],
        "account_amounts": dict(core_row["account_amounts"])
        if "account_amounts" in core_row
        else None,
    }
    return kit, core_


def _caller_names() -> list[str]:
    """The names the kit's other modules import from ``kit.recon``."""
    names = set()
    for path in sorted((ROOT / "kit").glob("*.py")):
        if path.name == "recon.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module == "kit.recon":
                names |= {a.name for a in node.names}
    return sorted(names)


def _fields(obj) -> list[str] | None:
    return sorted(obj.model_fields) if hasattr(obj, "model_fields") else None


def _observed(gap: str) -> tuple[object, object]:
    if gap.startswith("pre_") and gap in _pre_tally():
        return _pre_tally()[gap]
    if gap.startswith("post_") and gap in _post_tally():
        return _post_tally()[gap]
    if gap.startswith("settle_") and gap in _settle_tally():
        return _settle_tally()[gap]
    if gap == "profile_rows":
        kcat, ccat = _kcat(), _ccat()
        assert sorted(kcat.ids("ReconcileProfile")) == sorted(ccat.recon_profiles)
        kit, core_ = {}, {}
        for pid in sorted(ccat.recon_profiles):
            k, c = _profile_fields(kcat.get("ReconcileProfile", pid), ccat.recon_profiles[pid])
            differ = sorted(f for f in k if k[f] != c[f])
            if differ:
                kit[pid] = {f: k[f] for f in differ}
                core_[pid] = {f: c[f] for f in differ}
        return kit, core_
    if gap == "post_profile_selection":
        kcat, ccat = _kcat(), _ccat()
        kit, core_ = {}, {}
        for key in core.synthetic.FIRMS:
            axes = dict(_world(key)["firm"].axes)
            for fc, doc in _documents(key):
                kp = kr.pick_profile(kcat, "post", fc)
                cp = core.pre_profile(ccat, doc, fiscal_class=fc, axes=axes, stage="post")
                kit.setdefault(key, set()).add(kp.id if kp else None)
                core_.setdefault(key, set()).add(cp["profile_id"] if cp else None)
        return (
            {k: sorted(v, key=str) for k, v in kit.items()},
            {k: sorted(v, key=str) for k, v in core_.items()},
        )
    if gap == "settle_inputs":

        def params(f):
            return [p for p in inspect.signature(f).parameters]

        return params(kr.propose_settlement), params(core.propose_settlement)
    if gap == "settle_edit_shape":
        kit, core_ = set(), set()
        for _, k, c in _settle_cases():
            if k.edit:
                kit.add(tuple(sorted(k.edit)))
            if c.edit:
                core_.add(tuple(sorted(c.edit)) + tuple(sorted(c.edit["maps"])))
        return sorted(kit), sorted(core_)
    if gap == "caller_shapes":
        names = _caller_names()
        return (
            {n: _fields(getattr(kr, n)) for n in names},
            {n: _fields(getattr(core, n)) if hasattr(core, n) else "absent" for n in names},
        )
    raise KeyError(gap)


@pytest.mark.parametrize("gap", sorted(PARITY_GAPS))
def test_each_declared_gap_still_holds_exactly(gap: str) -> None:
    assert _observed(gap) == PARITY_GAPS[gap]
