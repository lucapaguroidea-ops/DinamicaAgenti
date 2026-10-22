"""WP-20, the ``period.py`` step: the kit's period difference, close kind, controls and
materiality against the core's (``core.controls``: ``poarta_contabila.period_diff``, pinned by
commit), before any replacement.

The inputs are the core's own synthetic quarter (``core.synthetic``, seed 7, 2026-01..03, the five
firms): its 390 invoices read by the core's UBL reader (``to_canonical``), its 248 bank statement
lines read by the core's statement reader (``statement_line_document``), and its book as the
core's NextUp writers export it and the core's readers read it back (the registru jurnal of the
quarter, the balanță of each month). Left out, as in the ``recon.py`` step and for the same
reasons: the bonuri, the expense reports and the payroll statements. Each side gets the same
facts in its own shape:

- the core: ``build_period_diff`` over an ``ExpectedJob`` per document (status ``acked``, no SAGA
  key, a foreign invoice bound to the articol the core's ``match_articole`` picks for it), an
  ``ExportEye`` over the journal and the month's balanță, the firm's axes, and as ``prior`` the
  same documents of the month's two months before (what the core's close passes);
- the kit: ``period_diff`` over an ``ExpectedItem`` per document (its ``vat_open`` as
  ``kit/steps.py`` ``_items`` sets it), a ``Witness`` of the eye's documents and journal lines
  (each line split into its debit and its credit side, the accounts as booked), the month's
  balanță as ``balances`` (closing credit − debit, the first row of an account kept, as the
  core's eye keeps it), and the firm's axes in the kit's vocabulary (``exig``
  ``tva_exig_livrare`` → ``tva_la_livrare``; BUILD WP-20, ``catalog.py`` step).

The cases: each firm and month (15), with the books covering the month and with books of the
other two months only (×2), the expected set of the invoices alone and of the invoices and the
bank lines (×2), and the kit with ``maps_exist`` false and true (×2; the core has no such input):
120 cases, against 60 core runs. Compared, case by case: the buckets (key, bucket, job, rule,
gross), the outbound holes, the parity on every watched account (expected and books, netted as
credit − debit, the core's per-side figures folded so), every close control's status, the
blockers (by the control or reason they name), the materiality, ``can_file`` and the hard
failures, and the 4428 figures where both compute them (``M1_8_4428_open`` failing on both
sides). Then, apart from the cases: the close kind of every firm, and the pre-package controls
for every PRE verdict either side knows.

**Live paths.** The kit's live callers are ``kit/steps.py`` (``_lock``, ``_period_diff``,
``_post_default``) and ``kit/scenario.py``: they pass invoices only (the kit reads no bank
statement), never ``maps_exist`` (so false) and never an explained rule (no step writes
``_rules``). The live cases are therefore the 30 with the invoices alone and ``maps_exist`` false;
the bank-line and ``maps_exist`` true cases have no live kit caller. ``prefile_failures`` and
``close_action_refused`` have no live kit caller at all (tests only). Agreement is given below
both overall and on the live cases.

What it proves: on this corpus every difference falls in a declared gap (a case may show more than
one); the gaps' counts and the agreeing counts are exact; materiality, ``can_file``, the outbound
holes and C0's status agree on every case. What it does not prove, because the corpus never
exercises it: explained rules (document or line), an outbound hole (every job is ``acked``), a
SAGA key carried by a job, a rejected job, a bank line bound to a partner (none is: so neither
the kit's bound counterpart nor the core's VAT made exigible by a payment under TVA la încasare
runs), ``open_pre`` and ``lock_mismatch`` (the core's close holds those outside
``build_period_diff``), a waiting expense-report part, analytic accounts that do not tie, 4423 /
4424 / 5311 movement, a close kind for ``tva_091``, nor which side's accounts are right, which
the catalog and the SAGA C loops decide. Nor does it prove agreement on a month that could be
filed: no case is non-material (all 120 are material, so ``can_file`` is false, on both sides);
C0 never passes (it fails on both sides in all 120); M1_8 never passes (it fails on both sides in
24 cases and is INFO in 96); the kit's C1 never fails (the core's fails only in the 60 uncovered
cases, gap ``uncovered_month_controls``); so the agreement on materiality, ``can_file`` and C0
says nothing about a month that could be filed. And of the 90 cases whose buckets agree, 60 agree
empty against empty, because no export covers the month. These counts are pinned below, so the
vacuity cannot change silently. Apart from the cases, one empty month per firm is not material on
either side (four firms may file it), which shows only that neither side is material by
construction.

While any gap stands the kit keeps ``kit/period.py``; the owner frames the decision (BUILD WP-20).
"""

from __future__ import annotations

import inspect
import re
import tempfile
from collections import Counter
from decimal import Decimal
from functools import cache
from pathlib import Path

import pytest
from poarta_contabila import core
from poarta_contabila.period_diff import ExpectedJob
from poarta_contabila.sinks.exports import ExportEye
from poarta_contabila.synthetic.months import realistic
from poarta_contabila.types import JobRecord, SourceRef, TenantRef
from test_calendar import _pinned_checkout

from kit import period as kp
from kit import recon as kr
from kit.catalog import load_catalog
from kit.types import cui_is_valid

ROOT = Path(__file__).resolve().parents[1]
PERIODS = ["2026-01", "2026-02", "2026-03"]
SEED = 7
SRC = SourceRef(
    kind="ubl_spv", bucket_key="k", content_type="application/xml", source_hash="0" * 64
)
EXIG = {"tva_exig_livrare": "tva_la_livrare", "tva_la_incasare": "tva_la_incasare"}
REGIME = ("t_regime_4428", "t_regime_442x")
MAPS = ("m1_1_payables_tie", "m1_1_trade_ext", "m1_2_receivables_tie", "m1_2_trade_ext")
NOT_COMPUTED = ("m1_9_4424_watched", "c2_waiting_for_xml")


@cache
def _kcat():
    return load_catalog(ROOT / "catalog")


@cache
def _ccat():
    return core.load_catalog(_pinned_checkout())


def _kit_axes(axes: dict[str, str]) -> dict[str, str]:
    out = dict(axes)
    if "exig" in out:
        out["exig"] = EXIG[out["exig"]]
    return out


def _synthetic(account: str) -> str:
    return re.match(r"\d+", account).group(0)


def _articol(firm, doc, foreign: bool) -> str | None:
    """The articol the core's flux binds a foreign invoice to (its reverse charge keys on it)."""
    if not foreign:
        return None
    inbound = doc.doc_class in ("intrare", "storn_intrare")
    ctx = core.MatchContext(
        graph_id="ingest_source_doc",
        fiscal_class="foreign_invoice",
        our_role="inbound" if inbound else "outbound",
        is_storno=doc.doc_class.startswith("storn"),
        axes=dict(firm.axes),
    )
    hits = core.match_articole(_ccat(), ctx)
    return hits[0] if len(hits) == 1 else None


# ----- the corpus: the core's quarter, in each side's shape -----


@cache
def _world(key: str) -> dict:
    firm = core.synthetic.FIRMS[key]
    m = realistic(firm, PERIODS, seed=SEED)
    with tempfile.TemporaryDirectory() as tmp:
        rj = Path(tmp) / "rj.xlsx"
        rj.write_bytes(m.book.nextup_rj())
        lines = core.read_nextup_rj(rj)
        balance = {}
        for p in PERIODS:
            bal = Path(tmp) / f"balanta-{p}.xlsx"
            bal.write_bytes(m.book.nextup_balanta(p))
            balance[p] = core.read_nextup_balanta(bal)
    tenant = TenantRef(cui=firm.cui, saga_firm_folder=firm.folder)
    invoices, bank = [], []
    for inv in m.invoices():
        job = JobRecord(job_id=inv.ref, tenant=tenant, period=inv.period, status="acked")
        doc = core.to_canonical(core.parse_ubl(inv.xml(firm)), job=job, source=SRC)
        job = job.model_copy(update={"articol_id": _articol(firm, doc, inv.foreign)})
        invoices.append(ExpectedJob(job=job, doc=doc))
    for p in PERIODS:
        stmt = m.docs[f"{p[2:4]}{p[5:]}-extras"]
        read = core.parse_statement(stmt.tables(), core.StatementMeta(**stmt.meta()), firm.cui)
        for i, ln in enumerate(read.lines):
            job = JobRecord(job_id=f"{stmt.ref}#{i}", tenant=tenant, period=p, status="acked")
            doc = core.statement_line_document(
                read, ln, job=job, bucket_key="k", source_hash="0" * 64
            )
            bank.append(ExpectedJob(job=job, doc=doc))
    return {
        "firm": firm,
        "kinds": Counter(type(d).__name__ for d in m.docs.values()),
        "lines": lines,
        "balance": balance,
        "invoices": invoices,
        "bank": bank,
    }


def _expected(key: str, period: str, with_bank: bool) -> list[ExpectedJob]:
    w = _world(key)
    jobs = w["invoices"] + (w["bank"] if with_bank else [])
    return [e for e in jobs if e.doc.date[:7] == period]


def _prior(key: str, period: str, with_bank: bool) -> list[ExpectedJob]:
    i = PERIODS.index(period)
    return [e for p in PERIODS[max(0, i - 2) : i] for e in _expected(key, p, with_bank)]


def _eye(key: str, period: str, covered: bool) -> ExportEye:
    """The books of the quarter with the month's balanță, or of the other two months only."""
    w = _world(key)
    return ExportEye(
        product="nextup",
        lines=w["lines"],
        balance=w["balance"][period] if covered else None,
        cui=w["firm"].cui,
        periods=PERIODS if covered else [p for p in PERIODS if p != period],
    )


@cache
def _witness(
    key: str, period: str, covered: bool, fold: bool = False
) -> tuple[kr.Witness, dict[str, str]]:
    """The eye's books as a kit ``Witness`` and ``balances``; ``fold``: every account folded to
    its synthetic account (only to tell the kit's folding apart, never compared as the kit's)."""
    w, eye = _world(key), _eye(key, period, covered)
    cover = sorted(eye.periods)
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
        for d in eye.documents(w["firm"].cui, p)
    ]
    lines = [
        kr.JournalLine(
            saga_key=f"{ln.product}:{ln.journal}:{ln.doc_number or ''}:{ln.date}",
            journal=ln.journal,
            number=ln.doc_number or "",
            date=ln.date,
            account=_synthetic(account) if fold else account,
            side=side,
            amount=ln.amount,
        )
        for ln in w["lines"]
        if ln.date[:7] in cover
        for side, account in (("debit", ln.debit), ("credit", ln.credit))
    ]
    balances: dict[str, str] = {}
    for r in w["balance"][period] if covered else []:
        net = Decimal(r.closing_credit) - Decimal(r.closing_debit)
        balances.setdefault(r.account, f"{net:.2f}")
    return kr.Witness(covered=cover, docs=docs, lines=lines), balances


def _kit_items(key: str, period: str, with_bank: bool) -> list[kp.ExpectedItem]:
    axes = _kit_axes(dict(_world(key)["firm"].axes))
    out = []
    for e in _expected(key, period, with_bank):
        d = e.doc
        vat_open = None  # as kit/steps.py _items sets it
        if axes.get("exig") == "tva_la_incasare" and d.totals.vat and Decimal(d.totals.vat):
            vat = Decimal(d.totals.vat)
            vat_open = f"{(-vat if d.doc_class.endswith('intrare') else vat):.2f}"
        out.append(
            kp.ExpectedItem(
                job_id=e.job.job_id,
                status=e.job.status,
                doc_class=d.doc_class,
                number=d.number,
                date=d.date,
                partner_cui=d.partner.cui,
                gross=d.totals.gross,
                vat=d.totals.vat,
                saga_key=e.job.saga.get("saga_doc_key"),
                vat_open=vat_open,
            )
        )
    return out


def _kit_run(key, period, covered, with_bank, maps_exist, fold=False) -> kp.PeriodDiff:
    w, balances = _witness(key, period, covered, fold)
    return kp.period_diff(
        _kcat(),
        period,
        _kit_items(key, period, with_bank),
        w,
        axes=_kit_axes(dict(_world(key)["firm"].axes)),
        balances=balances or None,
        maps_exist=maps_exist,
    )


@cache
def _core_run(key, period, covered, with_bank):
    firm = _world(key)["firm"]
    return core.build_period_diff(
        _ccat(),
        firm.cui,
        period,
        _expected(key, period, with_bank),
        _eye(key, period, covered),
        axes=dict(firm.axes),
        prior=_prior(key, period, with_bank),
    )


@cache
def _cases() -> list[tuple]:
    """(key, period, covered, with bank lines, maps_exist): every case, with both results."""
    out = []
    for key in core.synthetic.FIRMS:
        for period in PERIODS:
            for covered in (True, False):
                for with_bank in (False, True):
                    c, runs = _core_run(key, period, covered, with_bank)
                    for maps_exist in (False, True):
                        k = _kit_run(key, period, covered, with_bank, maps_exist)
                        case = (key, period, covered, with_bank, maps_exist)
                        out.append((case, k, c, runs))
    return out


def _live(case: tuple) -> bool:
    _, _, _, with_bank, maps_exist = case
    return not with_bank and not maps_exist


def test_the_corpus_is_the_core_quarter_and_every_invented_cui_is_valid() -> None:
    kinds = sum((_world(k)["kinds"] for k in core.synthetic.FIRMS), Counter())
    assert kinds == {"Invoice": 390, "Statement": 15, "Bon": 14, "ExpenseReport": 13, "Payroll": 9}
    assert core.CORE_MODULES["core.controls"] == ("poarta_contabila.period_diff",)
    worlds = [_world(k) for k in core.synthetic.FIRMS]
    assert sum(len(w["invoices"]) for w in worlds) == 390
    assert sum(len(w["bank"]) for w in worlds) == 248
    # no bank line is bound to a partner: the bound paths are not exercised (docstring)
    assert not any(e.doc.partner.cui for w in worlds for e in w["bank"])
    bound = Counter(
        (w["firm"].cui, e.job.articol_id) for w in worlds for e in w["invoices"] if e.job.articol_id
    )
    abroad, neplatitor = core.synthetic.FIRMS["abroad"], core.synthetic.FIRMS["neplatitor"]
    assert bound == {
        (abroad.cui, "foreign_invoice_inbound"): 7,
        (neplatitor.cui, "foreign_rc_neplatitor"): 3,
    }
    cuis = {e.doc.partner.cui for w in worlds for e in w["invoices"] if e.doc.partner.cui}
    cuis |= {w["firm"].cui for w in worlds}
    assert cuis and all(map(cui_is_valid, cuis))
    assert len(_cases()) == 120 and sum(map(_live, (c for c, *_ in _cases()))) == 30


# ----- each side's view of a case -----


def _head(blocker: str) -> str:
    """What a blocker names: its control (lower case) or its reason's key."""
    return blocker.split(": ")[0].removesuffix(" (advisory)").lower()


def _kit_view(k: kp.PeriodDiff) -> dict:
    return {
        "buckets": {b.saga_key: (b.bucket, b.job_id, b.rule_id, b.gross) for b in k.buckets},
        "holes": list(k.outbound_holes),
        "parity": {a: (v["expected"], v["sink"]) for a, v in k.parity.items()},
        "controls": {r.control_id: r.status for r in k.controls},
        "blockers": [_head(b) for b in k.blockers],
        "material": k.material,
        "can_file": k.can_file,
        "hard_failures": k.hard_failures,
    }


def _core_view(c, runs, watched: list[str]) -> dict:
    def net(account: str, field: str) -> Decimal:
        side = {
            s: Decimal(getattr(c.synthetic_delta[f"{account}:{s}"], field))
            if f"{account}:{s}" in c.synthetic_delta
            else Decimal(0)
            for s in ("debit", "credit")
        }
        return side["credit"] - side["debit"]

    return {
        "buckets": {
            b.sink.saga_key: (
                b.kind,
                b.expected.job_id if b.expected else None,
                b.rule_id,
                b.sink.gross,
            )
            for b in c.inbound
        },
        "holes": list(c.outbound_holes),
        "parity": {a: (f"{net(a, 'expected'):.2f}", f"{net(a, 'sink'):.2f}") for a in watched},
        "controls": {r.control_id.lower(): r.status for r in runs},
        "blockers": [_head(b) for b in c.blockers],
        "material": c.material,
        "can_file": core.can_file(c),
        "hard_failures": c.hard_failures,
    }


def _watched() -> list[str]:
    return list(_kcat().get("Control", "c0_synthetic_parity").watched)


def _m1_8(k: kp.PeriodDiff, runs) -> tuple[tuple, tuple] | None:
    """The 4428 figures where both compute them: (open, 4428) per side, M1_8 failing on both."""
    kit = next(r for r in k.controls if r.control_id == "m1_8_4428_open")
    core_ = next(r for r in runs if r.control_id == "M1_8_4428_open")
    found = re.fullmatch(r"open VAT (\S+) against 4428 (\S+)", kit.reason)
    if kit.status != "FAIL" or core_.status != "FAIL" or not found or core_.target is None:
        return None
    return found.groups(), (core_.target, core_.actual)


def _net_of(triples) -> dict[str, Decimal]:
    out: dict[str, Decimal] = Counter()
    for account, side, amount in triples:
        out[account] += Decimal(amount) if side == "credit" else -Decimal(amount)
    return out


def _core_parts(case: tuple, c) -> tuple[dict, dict]:
    """By the core's own code: what it implies opposite 5121 for the month's bank lines
    (``bank_counterparts``), and what its reverse charge adds (``expected_turnover`` with the
    reverse-charged jobs, less without)."""
    key, period, covered, with_bank, _ = case
    exp = _expected(key, period, with_bank)
    eye = _eye(key, period, covered)
    cui = _world(key)["firm"].cui
    matched = {b.expected.job_id: b.sink for b in c.inbound if b.kind == "expected"}
    lines = eye.journal_lines(cui, period) if covered else []
    counterpart = _net_of(core.bank_counterparts(exp, matched, lines))
    items = [e.item() for e in exp]
    axes = dict(_world(key)["firm"].axes)
    rate = core.standard_rate(_ccat(), period)
    rc = {
        e.job.job_id
        for e in exp
        if e.job.articol_id == "foreign_invoice_inbound" and Decimal(e.doc.totals.vat) == 0
    }

    def turnover(charged) -> dict[str, Decimal]:
        t = core.expected_turnover(items, axes, rate, charged)
        return {a: s["credit"] - s["debit"] for a, s in t.items()}

    with_rc, without = turnover(rc), turnover(frozenset())
    reverse = {a: with_rc.get(a, 0) - without.get(a, 0) for a in with_rc}
    return counterpart, {a: v for a, v in reverse.items() if v}


Tags = list[tuple[str, str, str]]  # (gap, kit outcome, core outcome) per gap a case shows


def _tags(case: tuple, k: kp.PeriodDiff, c, runs) -> Tags:
    """The declared gaps one case shows; ``unexplained`` when a difference is left. Each gap's
    difference is set aside once tagged, so a case may show several."""
    _, _, covered, _, maps_exist = case
    kv, cv, tags = _kit_view(k), _core_view(c, runs, _watched()), []

    # buckets: a bank document the core matches by date and amount, the kit by number
    for key in sorted(set(kv["buckets"]) | set(cv["buckets"])):
        kb, cb = kv["buckets"].get(key), cv["buckets"].get(key)
        if kb == cb:
            continue
        if (
            kb
            and cb
            and kb[0] == "unexplained"
            and cb[0] == "expected"
            and key.endswith((":incasare", ":plata"))
        ):
            tags.append(("bank_line_match", "bank document unexplained", "bank document expected"))
            kv["buckets"][key] = cb
        else:
            tags.append(("unexplained", f"bucket {key}: {kb}", str(cb)))
    k_unexplained = any(b[0] == "unexplained" for b in kv["buckets"].values())
    aside: set[str] = set()  # controls whose difference is set aside
    if kv["controls"]["c2_unexplained_empty"] == "FAIL" and not k_unexplained:
        tags.append(("bank_line_match", "c2_unexplained_empty FAIL", "c2_unexplained_empty PASS"))
        kv["controls"]["c2_unexplained_empty"] = "PASS"
        aside.add("c2_unexplained_empty")

    # parity: the books as each side folds them; what each side implies
    folded = None
    counterpart, reverse = _core_parts(case, c)
    for account in _watched():
        (ke, ks), (ce, cs) = kv["parity"][account], cv["parity"][account]
        if ks != cs:
            if folded is None:
                folded = _kit_run(*case, fold=True)
            if folded.parity[account]["sink"] == cs:
                tags.append(("analytic_folding", f"{account}: as booked", f"{account}: folded"))
            else:
                tags.append(("unexplained", f"{account} books {ks}", cs))
        if ke != ce:
            delta = Decimal(ce) - Decimal(ke)
            if counterpart.get(account) and delta == counterpart[account]:
                tags.append(
                    (
                        "bank_line_counterpart",
                        f"{account}: nothing for an unbound line",
                        f"{account}: the books' counterpart",
                    )
                )
            elif reverse.get(account) and delta == reverse[account]:
                tags.append(("reverse_charge", f"{account}: none", f"{account}: reverse charged"))
            else:
                tags.append(("unexplained", f"{account} expected {ke}", ce))
        kv["parity"][account] = cv["parity"][account]

    # controls
    for cid in sorted(set(kv["controls"]) | set(cv["controls"])):
        ks, cs = kv["controls"].get(cid), cv["controls"].get(cid)
        if ks == cs:
            continue
        if not covered and ks in ("PASS", "INFO") and cs == "FAIL":
            tags.append(("uncovered_month_controls", ks, cs))
        elif cid in REGIME and (ks, cs) == ("INFO", "PASS"):
            tags.append(("regime_controls_on_a_payer", ks, cs))
        elif cid in MAPS and (ks, cs) == (("PASS", "INFO") if maps_exist else ("INFO", "PASS")):
            tags.append(("maps_precondition", f"maps_exist {maps_exist}: {ks}", cs))
        elif cid in NOT_COMPUTED and cs == "INFO":
            tags.append(("not_computed_by_the_core", ks, cs))
        else:
            tags.append(("unexplained", f"{cid}: {ks}", str(cs)))
        aside.add(cid)

    # what follows from the statuses: blockers and hard failures, less the controls set aside
    kb = [b for b in kv["blockers"] if b not in aside]
    cb = [b for b in cv["blockers"] if b not in aside]
    if kb != cb:
        tags.append(("unexplained", f"blockers {kb}", str(cb)))
    k_runs = {r.control_id: r for r in k.controls}
    k_hard = kv["hard_failures"] - sum(
        1 for cid in aside if k_runs[cid].status == "FAIL" and k_runs[cid].severity == "blocking"
    )
    c_rows = {cid.lower(): row for cid, row in _ccat().controls.items()}
    c_hard = cv["hard_failures"] - sum(
        1
        for cid in aside
        if cv["controls"].get(cid) == "FAIL" and c_rows[cid].get("severity") == "blocking"
    )
    if k_hard != c_hard:
        tags.append(("unexplained", f"hard {k_hard}", str(c_hard)))
    for field in ("holes", "material", "can_file"):
        if kv[field] != cv[field]:
            tags.append(("unexplained", f"{field} {kv[field]}", str(cv[field])))

    figures = _m1_8(k, runs)
    if figures and figures[0] != figures[1]:
        (ko, kh), (co, ch) = figures
        tags.append(("m1_8_figures", f"open {ko}, 4428 {kh}", f"open {co}, 4428 {ch}"))
    return tags


def _tally(rows) -> dict[str, tuple[dict, dict]]:
    """``{gap: (kit outcomes, core outcomes)}`` with counts (a case showing a gap twice counts
    twice)."""
    kit_seen: dict[str, Counter] = {}
    core_seen: dict[str, Counter] = {}
    for tags in rows:
        for gap, kl, cl in tags:
            kit_seen.setdefault(gap, Counter())[kl] += 1
            core_seen.setdefault(gap, Counter())[cl] += 1
    return {g: (dict(kit_seen[g]), dict(core_seen[g])) for g in kit_seen}


@cache
def _case_tally() -> dict[str, tuple[dict, dict]]:
    return _tally(_tags(case, k, c, runs) for case, k, c, runs in _cases())


def test_every_difference_falls_in_a_declared_gap() -> None:
    tally = _case_tally()
    assert "unexplained" not in tally, tally.get("unexplained")
    case_gaps = set(PARITY_GAPS) - {"close_kind_outside_the_core", "caller_shapes", "inputs"}
    assert set(tally) == case_gaps


def _agreement(cases) -> dict[str, int]:
    """Per field (and per control's status), the cases where both sides agree with nothing set
    aside; ``every field``: the cases that show no gap at all."""
    out: Counter = Counter()
    for case, k, c, runs in cases:
        kv, cv = _kit_view(k), _core_view(c, runs, _watched())
        for field in kv:
            out[field] += kv[field] == cv[field]
        for cid in kv["controls"]:
            out[f"control {cid}"] += kv["controls"][cid] == cv["controls"].get(cid)
        out["every field"] += not _tags(case, k, c, runs)
    return dict(out)


def test_what_agrees_overall_and_on_the_live_paths() -> None:
    cases = _cases()
    assert _agreement(cases) == AGREE_ALL
    assert _agreement([x for x in cases if _live(x[0])]) == AGREE_LIVE


def test_the_4428_figures_are_what_gap_m1_8_figures_says() -> None:
    """Where M1_8 fails on both sides, each figure is recomputed from its side's inputs: the
    kit's open VAT is the absolute of this month's ``vat_open``, its 4428 the absolute of the
    balance; the core's open VAT is its ``open_4428`` over this month and ``prior``, its 4428 the
    signed balance (debit +)."""
    seen = 0
    for case, k, _, runs in _cases():
        figures = _m1_8(k, runs)
        if figures is None:
            continue
        key, period, _, with_bank, _ = case
        (ko, kh), (co, ch) = figures
        items = _kit_items(key, period, with_bank)
        balance = Decimal(_witness(key, period, True)[1]["4428"])
        assert Decimal(ko) == abs(sum(Decimal(i.vat_open) for i in items if i.vat_open))
        assert Decimal(kh) == abs(balance) and Decimal(ch) == -balance
        want = core.open_4428(_expected(key, period, with_bank), _prior(key, period, with_bank))
        assert Decimal(co) == want
        seen += 1
    assert seen == 12


def _vacuity(cases) -> dict[tuple, int]:
    """Per (what, kit, core): materiality, ``can_file``, C0, M1_8 and C1 as each side has them,
    and the agreeing buckets by whether they are empty and the month covered."""
    out: Counter = Counter()
    for (_, _, covered, _, _), k, c, runs in cases:
        kv, cv = _kit_view(k), _core_view(c, runs, _watched())
        out[("material", kv["material"], cv["material"])] += 1
        out[("can_file", kv["can_file"], cv["can_file"])] += 1
        for cid in ("c0_synthetic_parity", "m1_8_4428_open", "c1_outbound_complete"):
            out[(cid, kv["controls"][cid], cv["controls"][cid])] += 1
        if kv["buckets"] == cv["buckets"]:
            out[("buckets agree", bool(kv["buckets"]), covered)] += 1
    return dict(out)


def test_the_agreement_on_materiality_can_file_and_c0_is_vacuous_here() -> None:
    """Pinned so the vacuity cannot change silently (docstring, "does not prove"): every case is
    material on both sides, so ``can_file`` is false; C0 fails on both; M1_8 never passes; the
    kit's C1 never fails; 60 of the 90 bucket agreements are empty against empty, uncovered."""
    assert _vacuity(_cases()) == {
        ("material", True, True): 120,
        ("can_file", False, False): 120,
        ("c0_synthetic_parity", "FAIL", "FAIL"): 120,
        ("m1_8_4428_open", "FAIL", "FAIL"): 24,
        ("m1_8_4428_open", "INFO", "INFO"): 96,
        ("c1_outbound_complete", "PASS", "PASS"): 60,
        ("c1_outbound_complete", "PASS", "FAIL"): 60,
        ("buckets agree", True, True): 30,
        ("buckets agree", False, False): 60,
    }
    assert _vacuity(x for x in _cases() if _live(x[0])) == {
        ("material", True, True): 30,
        ("can_file", False, False): 30,
        ("c0_synthetic_parity", "FAIL", "FAIL"): 30,
        ("m1_8_4428_open", "FAIL", "FAIL"): 6,
        ("m1_8_4428_open", "INFO", "INFO"): 24,
        ("c1_outbound_complete", "PASS", "PASS"): 15,
        ("c1_outbound_complete", "PASS", "FAIL"): 15,
        ("buckets agree", True, True): 15,
        ("buckets agree", False, False): 15,
    }


def test_an_empty_month_is_not_material_on_either_side() -> None:
    """Apart from the cases: a covered month with no document, no line and no balanță, each firm.
    Both sides agree on materiality, ``can_file`` and C0, and four firms may file; under TVA la
    încasare M1_8 fails on both for want of 4428's balance. This shows only that neither side is
    material by construction, nothing about a month with documents."""
    period, seen = PERIODS[0], {}
    for key, firm in core.synthetic.FIRMS.items():
        k = kp.period_diff(
            _kcat(),
            period,
            [],
            kr.Witness(covered=[period], docs=[], lines=[]),
            axes=_kit_axes(dict(firm.axes)),
        )
        eye = ExportEye(product="nextup", lines=[], balance=[], cui=firm.cui, periods=[period])
        c, runs = core.build_period_diff(
            _ccat(), firm.cui, period, [], eye, axes=dict(firm.axes), prior=[]
        )
        kv, cv = _kit_view(k), _core_view(c, runs, _watched())
        for field in ("material", "can_file"):
            assert kv[field] == cv[field], (key, field)
        assert kv["controls"]["c0_synthetic_parity"] == cv["controls"]["c0_synthetic_parity"]
        seen[key] = (kv["can_file"], kv["controls"]["c0_synthetic_parity"])
    assert seen == {
        "platitor": (True, "PASS"),
        "incasare": (False, "PASS"),
        "neplatitor": (True, "PASS"),
        "abroad": (True, "PASS"),
        "bonuri": (True, "PASS"),
    }


# ----- apart from the cases -----


def test_the_close_kind_of_every_firm_agrees_with_the_cores_namesake_outside_the_core() -> None:
    """The kit's ``close_kind`` against ``poarta_contabila.close.close_kind``, which is not a core
    module (gap ``close_kind_outside_the_core``): each under its own catalog's rows."""
    from poarta_contabila.close import close_kind as core_close_kind

    for key, firm in core.synthetic.FIRMS.items():
        kit = kp.close_kind(_kcat(), _kit_axes(dict(firm.axes)))
        assert kit is not None and kit == core_close_kind(_ccat(), dict(firm.axes)), key
    for case, k, _, _ in _cases():
        assert k.close_kind == kp.close_kind(_kcat(), _kit_axes(dict(_world(case[0])["firm"].axes)))


def test_the_pre_package_controls_agree_on_every_pre_verdict() -> None:
    """``prefile_failures`` for each PRE verdict of either side's vocabulary and none: the same
    controls fail (by id, lower case; the reason prose is not compared). The kit's has no live
    caller."""
    verdicts = [None, "absent", "already_posted", "ambiguous", "need_export"]
    for v in verdicts:
        kit = [f.split(":")[0] for f in kp.prefile_failures(_kcat(), v)]
        core_ = [f.split(":")[0].lower() for f in core.prefile_failures(_ccat(), pre_verdict=v)]
        assert kit == core_, v


# ----- declared gaps: the module waits on the owner (BUILD WP-20) -----

PARITY_GAPS: dict[str, tuple[object, object]] = {
    # The books' bank documents (JB) of a month whose bank lines are expected: the core matches a
    # statement line by side, date and amount (it carries no SAGA number), the kit by side,
    # number, date and gross, and the line's number is not the bank's reference SAGA holds it
    # under; so the kit leaves them unexplained, and C2 fails where it would pass. No live kit
    # caller passes bank lines.
    "bank_line_match": (
        {"bank document unexplained": 496, "c2_unexplained_empty FAIL": 10},
        {"bank document expected": 496, "c2_unexplained_empty PASS": 10},
    ),
    # The kit folds an analytic account to its synthetic one only at a dot (401.00001 → 401);
    # the books here hold analytics as 401_X / 4111_X / 5121_X, which the core folds and the kit
    # keeps apart, so its books' movement on 401, 4111 and 5121 differs (C0 fails on both sides
    # either way). The kit given the same lines folded agrees.
    "analytic_folding": (
        {"401: as booked": 60, "4111: as booked": 60, "5121: as booked": 60},
        {"401: folded": 60, "4111: folded": 60, "5121: folded": 60},
    ),
    # A bank line bound to no partner: the kit implies nothing opposite 5121, the core the books'
    # own counterpart when the bank document is one line of 401 (payment) or 4111 (receipt) of
    # exactly the line's amount. No live kit caller passes bank lines.
    "bank_line_counterpart": (
        {"401: nothing for an unbound line": 30, "4111: nothing for an unbound line": 30},
        {"401: the books' counterpart": 30, "4111: the books' counterpart": 30},
    ),
    # A payer's foreign purchase with no VAT (the core binds it to foreign_invoice_inbound): the
    # core implies 4426 Dr = 4427 Cr on the net at the year's standard rate, the kit nothing
    # (its ExpectedItem has no articol and no net). Only the abroad firm has such invoices.
    "reverse_charge": (
        {"4426: none": 24, "4427: none": 24},
        {"4426: reverse charged": 24, "4427: reverse charged": 24},
    ),
    # A month no export covers: the core fails every control that applies ("no export of the
    # books for the period"), the kit evaluates each on an empty book; blockers and hard failures
    # follow. Both are material and name need_rj_export first.
    "uncovered_month_controls": (
        {"PASS": 264, "INFO": 216},
        {"FAIL": 480},
    ),
    # T_regime_4428 / T_regime_442x on a VAT payer: the kit's rows require a non-payer, so INFO
    # (does not apply); the core's rows have no require and pass the payer inside the check.
    # The cause is the catalogs' rows: the kit's t_regime_4428 and t_regime_442x carry
    # require: {tva: [tva_neplatitor, tva_scutire_mici]} (catalog/60_practice/controls.yaml), the
    # core's T_regime_4428 and T_regime_442x carry no require; so this is the catalog.py step's
    # ground.
    "regime_controls_on_a_payer": ({"INFO": 96}, {"PASS": 96}),
    # The analytic ties (M1_1 / M1_2 and their trade extensions): the kit takes maps_exist as an
    # input (INFO while false, which every live caller passes), the core infers it from the
    # balanță showing analytics under the account (PASS when it does, INFO when it shows none).
    # The kit's PASS with maps_exist true is blind here: it looks for analytics at a dot only.
    "maps_precondition": (
        {"maps_exist False: INFO": 60, "maps_exist True: PASS": 60},
        {"PASS": 60, "INFO": 60},
    ),
    # M1_9_4424_watched and C2_waiting_for_xml: the kit computes both, the core neither
    # ("not computed in v1", advisory: INFO).
    "not_computed_by_the_core": ({"PASS": 120}, {"INFO": 120}),
    # TVA la încasare, M1_8 failing on both sides: the kit's open VAT is this month's
    # documents' (as an absolute) against the balance of 4428 as an absolute; the core's is this
    # and the two months before's, signed (debit +), against the signed balance.
    "m1_8_figures": (
        {
            "open 2595.87, 4428 1293.56": 4,
            "open 2002.39, 4428 1209.16": 4,
            "open 1819.26, 4428 2595.31": 4,
        },
        {
            "open 2595.87, 4428 -1293.56": 4,
            "open 4598.26, 4428 -1209.16": 4,
            "open 2779.00, 4428 -2595.31": 4,
        },
    ),
    # The close kind: the kit's period_diff chooses it (and blocks on none); the core's
    # build_period_diff does not, and its close_kind lives in poarta_contabila.close, which is
    # not a core module (it imports the close graph). On the five firms the namesake agrees.
    "close_kind_outside_the_core": (
        {
            "abroad": "close_standard",
            "bonuri": "close_standard",
            "incasare": "close_tva_incasare",
            "neplatitor": "close_standard",
            "platitor": "close_standard",
        },
        "absent",
    ),
    # The inputs: the kit takes the books as a Witness plus balances and maps_exist, and the
    # close's own blockers (open_pre, lock_mismatch, waiting_parts); the core takes the firm's
    # CUI, an eye, ExpectedJobs, the stalled jobs and the prior months' documents.
    "inputs": (
        [
            "cat",
            "period",
            "items",
            "w",
            "axes",
            "rules",
            "balances",
            "maps_exist",
            "open_pre",
            "lock_mismatch",
            "waiting_parts",
        ],
        ["cat", "cui", "period", "expected", "eye", "axes", "rules", "stalled", "prior"],
    ),
    # What the kit's other modules import from kit.period, and the core's namesake: the fields of
    # the models (or None for a function), "absent" where the core has none.
    "caller_shapes": (
        {
            "ExpectedItem": [
                "date",
                "doc_class",
                "gross",
                "job_id",
                "number",
                "partner_cui",
                "saga_key",
                "status",
                "vat",
                "vat_open",
            ],
            "ExplainedRule": [
                "account",
                "doc_class",
                "kind",
                "number_prefix",
                "partner_cui",
                "rule_id",
            ],
            "PeriodDiff": [
                "blockers",
                "buckets",
                "can_file",
                "close_kind",
                "controls",
                "hard_failures",
                "material",
                "outbound_holes",
                "parity",
                "period",
                "snapshot_id",
            ],
            "close_kind": None,
            "doc_rule_matches": None,
            "expected_set_hash": None,
            "period_diff": None,
            "weigh_suggestion": None,
        },
        {
            "ExpectedItem": [
                "analytic",
                "date",
                "doc_class",
                "gross",
                "job_id",
                "net",
                "number",
                "partner_cui",
                "vat",
            ],
            "ExplainedRule": [
                "cui",
                "description",
                "document",
                "line",
                "rule_id",
                "scope",
                "valid_from",
                "valid_to",
                "version",
            ],
            "PeriodDiff": [
                "analytic_delta",
                "blockers",
                "cui",
                "hard_failures",
                "inbound",
                "material",
                "outbound_holes",
                "period",
                "snapshot_id",
                "synthetic_delta",
            ],
            "close_kind": "absent",
            "doc_rule_matches": "absent",
            "expected_set_hash": "absent",
            "period_diff": "absent",
            "weigh_suggestion": "absent",
        },
    ),
}

# What agrees with nothing set aside, per field: of the 120 cases, and of the 30 live ones.
AGREE_ALL = {
    "buckets": 90,
    "holes": 120,
    "parity": 48,
    "controls": 0,
    "blockers": 50,
    "material": 120,
    "can_file": 120,
    "hard_failures": 50,
    "control c0_synthetic_parity": 120,
    "control c1_outbound_complete": 60,
    "control c2_unexplained_empty": 50,
    "control m1_1_payables_tie": 60,
    "control m1_1_trade_ext": 60,
    "control m1_2_receivables_tie": 60,
    "control m1_2_trade_ext": 60,
    "control m1_8_4428_open": 120,
    "control m1_9_4424_watched": 0,
    "control t_regime_4428": 12,
    "control t_regime_442x": 12,
    "control c2_waiting_for_xml": 0,
    "every field": 0,
}
AGREE_LIVE = {
    "buckets": 30,
    "holes": 30,
    "parity": 12,
    "controls": 0,
    "blockers": 15,
    "material": 30,
    "can_file": 30,
    "hard_failures": 15,
    "control c0_synthetic_parity": 30,
    "control c1_outbound_complete": 15,
    "control c2_unexplained_empty": 15,
    "control m1_1_payables_tie": 0,
    "control m1_1_trade_ext": 15,
    "control m1_2_receivables_tie": 0,
    "control m1_2_trade_ext": 15,
    "control m1_8_4428_open": 30,
    "control m1_9_4424_watched": 0,
    "control t_regime_4428": 3,
    "control t_regime_442x": 3,
    "control c2_waiting_for_xml": 0,
    "every field": 0,
}


def _caller_names() -> list[str]:
    """The names the kit's other modules import from ``kit.period``."""
    import ast

    names = set()
    for path in sorted((ROOT / "kit").glob("*.py")):
        if path.name == "period.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module == "kit.period":
                names |= {a.name for a in node.names}
    return sorted(names)


def _fields(obj) -> list[str] | None:
    return sorted(obj.model_fields) if hasattr(obj, "model_fields") else None


def _observed(gap: str) -> tuple[object, object]:
    if gap in _case_tally():
        return _case_tally()[gap]
    if gap == "close_kind_outside_the_core":
        kit = {
            key: kp.close_kind(_kcat(), _kit_axes(dict(firm.axes)))
            for key, firm in sorted(core.synthetic.FIRMS.items())
        }
        return kit, "absent" if not hasattr(core, "close_kind") else "present"
    if gap == "inputs":

        def params(f):
            return list(inspect.signature(f).parameters)

        return params(kp.period_diff), params(core.build_period_diff)
    if gap == "caller_shapes":
        names = _caller_names()
        return (
            {n: _fields(getattr(kp, n)) for n in names},
            {n: _fields(getattr(core, n)) if hasattr(core, n) else "absent" for n in names},
        )
    raise KeyError(gap)


@pytest.mark.parametrize("gap", sorted(PARITY_GAPS))
def test_each_declared_gap_still_holds_exactly(gap: str) -> None:
    assert _observed(gap) == PARITY_GAPS[gap]
