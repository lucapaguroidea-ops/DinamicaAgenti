"""WP-20, the ``sorting.py`` step: the kit's Sorting (``kit/sorting.py``: ``Pack``, ``decide``,
``split``) against the core's, before any replacement.

**What the core has.** The core re-exports no sorting module: ``CORE_MODULES`` has no
``core.triage`` or ``core.sorting``. What it carries for Sorting is data and types: the
``ArticoleSourceDoc`` and ``ArticoleJobs`` rows (``core.catalog``: ``Catalog.source_docs``,
``Catalog.jobs``), ``PrimaryKind``, ``Cui`` and ``cui_is_valid`` (``core.types``). The code lives
outside the core, in ``poarta_contabila.triage`` (``Pack``, ``decide_emit``, ``check_split``,
``child_pack`` and the folder_triage graph, which imports a graph and ``hitl.ask``), and the
packs are built by the runtime's upload routes (``runtime.Runtime.ingest_upload``,
``_ingest_statement``, ``ingest_decont``). Those are compared below as the core's namesakes
outside the core, labelled so. ``decide_emit`` reads its JsonLogic ``emit`` and aisle rules from
``fixtures/architecture.jsonlogic.json``, which the pinned install does not carry (gap
``rules_file_not_installed``): this test reads that file from the pinned checkout, unmodified.
The graph runs on an in-memory checkpointer and job store. Replacement is not possible until the
core exports a sorting module; until then this step's comparison is of pieces, not of a module.

**The corpus** is the core's synthetic quarter (``core.synthetic``, seed 7, 2026-01..03, the
five firms): its 393 uploads as its scenarios send them, 365 invoices (SPV zip, or XML for the
8 foreign), 15 statements and 13 expense reports. The kit sorts each upload's bytes through its
live intake (``kit.steps.intake``); the core's pack of each is built with the core's readers and
the runtime's few lines that assemble a pack, transcribed (the runtime needs its whole stack):
365 invoice packs, 248 statement-line packs, 13 containers, and the 42 parts (19 invoices, 14
receipts, 9 working papers) the core's true ``decont_split`` answers name, through the core's
graph. Left out, counted: 9 payroll statements (no route uploads one) and 6 invoices with no
upload (the quarter's hidden documents). For the decisions, each core pack is given to the kit
in the kit's shape (``_as_kit``: the same facts, the kit's names). The probes, which the
quarter never holds: 5120 packs (every one of the 16 shared source documents × 8 kinds × identity
× 5 counterparty spellings × storno × the receipt fork), 512 of them through the graph for the
questions; eleven ``decont_split`` answers on one container; every invoice upload sent to the
next firm, which is on neither side (365); every RO invoice as its bare XML (357); and 3552
invented B2C variants of the quarter's 148 RO sales, the buyer replaced by one whose tax id is
absent, a valid RO CUI, a RO CUI whose check digit fails or a foreign VAT id, and whose country
is absent, RO or DE, each as an SPV zip and as bare XML.

Compared, field by field: the class each upload is given; the pack (every field both packs
have); the decision (emit, the Job kind under the core's ``job_`` names, the failed gates under
the core's names), the identity gate within it; the question asked first and the split; the
split answer (accepted or asked again) and each child pack; the catalogs' rows the gates read.
Not compared: the core's aisle and the kit's ``job_key`` (``decision_shape``), the reasons'
wording, the store's insert of a Job (both key it on the client's CUI and the source hash).

**What agrees.** Overall, on the 668 corpus packs: emit and the Job kind on 668 (625 emit, 43 do
not); the failed gates on 625; the question and the split on 668 (13 ``decont_split``, 655
none); the identity gate on 668. The 13 true split answers are accepted on both, and 33 of the
42 parts are the same pack field by field. The two catalogs' Job kinds list the same documents.
On the probes: emit on 5078 of 5120 and the Job kind wherever both emit; the failed gates on
1588; the questions on all 512; 8 of the 11 split answers; on all 3552 B2C probes the class,
emit, the Job kind and the failed gates (the kinds differ only as in ``bare_xml_kinds``); the
365 invoices sent to a firm on neither side are refused before any pack on both. Every
difference falls in a declared gap; on the grid emit turns only on ``gates_by_row`` and
``counterparty_cui_spelling``.

**Live paths.** The kit's intake on the 365 invoice uploads gives the core's pack field by field
and the core's decision on all 365 (``kit intake``, whose batch issue the Dispatcher routes).
The same live intake refuses an invoice the client is not on alone before any pack, as the
core does (P13), and calls an invoice foreign as the core does: its counterparty has no RO CUI
and a country other than RO, an absent country meaning RO; its kind is then ``xml``.
The rest is not live on the Dispatcher's path: its intake calls a statement or an expense report
``unknown`` (``class_by_route``), and after ``define_class`` names it the pack keeps
``identity_ok`` false, so no statement emits and no expense report asks for its parts
(``named_after_define_class``). So the 13 containers and the 42 parts are live through
``kit/scenario.py`` only (``kit scenario``); ``split`` is reached on the Dispatcher's path only
after a ``decont_split`` answer, which that path never asks, so the split comparisons have no
asker there (``kit answer --kind decont_split``, ``kit emit --split`` and ``kit verify --role
reader_split`` reach ``split`` through the CLI; ``kit emit`` is a dry run that writes nothing).
The 248 statement lines have no builder in the kit: no kit module builds an
``extras_statement_pdf`` pack (``kit emit`` decides a hand-written one).

**Vacuity.** On the corpus the identity gate passes on both for all 668 packs, the failed gates
agree only where both lists are empty (625), ``define_class`` and ``bon_cui_unclear`` are never
asked, and every true split answer is accepted: so each of those agreements is pinned by these
counts and probed the other way. On the probes the identity gate fails on both in 768, the
failed gates agree non-empty in 1280, ``define_class`` is asked on both 32 times and
``bon_cui_unclear`` 16, and 6 split answers are asked again on both. On the kit's live path
``bon_cui_unclear`` is asked after ``define_class`` names ``bon_fiscal``: the Dispatcher's
question carries its kind (``kit.dispatch._question``), so its hash is not ``define_class``'s,
and its answer settles the fork and the receipt emits (``tests/test_paperclip.py``).

**What it does not prove**, because neither the corpus nor the probes exercise it: a part's
receipt fork in a split (no child of ``decont_cheltuieli`` has ``bon_cui_fork`` on either
catalog); a document listed by two non-storno Job kinds (no row is); the answer paths of
``define_class`` and ``bon_cui_unclear`` on the core's side (the graph's re-decision); the core's
aisle; the bonuri, bank statements in a bank's data format (``extras``), statement PDFs as one
file (``extras_pdf``), scanned foreign invoices, instructions, payroll and the sinks as
uploads, which neither side's routes take here (the probes decide them, the corpus does not);
nor which side's rows are right, which the owner and the catalog decide.

While any gap stands the kit keeps ``kit/sorting.py`` (its callers need its shapes: gap
``caller_shapes``); the owner frames the decision (BUILD WP-20)."""

from __future__ import annotations

import ast
import functools
import hashlib
import io
import re
import subprocess
import tempfile
import typing
import zipfile
from collections import Counter
from contextlib import contextmanager
from functools import cache
from itertools import product
from pathlib import Path
from unittest import mock

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from poarta_contabila import core, jsonlogic, triage
from poarta_contabila.jobs import InMemoryJobStore
from poarta_contabila.synthetic.docs import SIGNATURE, stable_zip
from poarta_contabila.synthetic.months import realistic
from poarta_contabila.types import JobRecord, SourceRef, TenantRef
from test_calendar import _pinned_checkout

from kit import sorting as ksort
from kit import steps as ks
from kit.catalog import CatalogError, load_catalog
from kit.store import open_dossier
from kit.types import cui_is_valid

ROOT = Path(__file__).resolve().parents[1]
PERIODS = ["2026-01", "2026-02", "2026-03"]
SEED = 7
CUI = "41526372"  # invented; passes the check digit
PARTNER = "73645193"  # invented; passes the check digit
BAD = PARTNER[:-1] + "0"  # its check digit changed
SHA = hashlib.sha256(b"probe").hexdigest()

# The kit's gate names → the core's.
GATE = {
    "class": "class_gate",
    "primary": "primary_gate",
    "identity": "identity_gate",
    "bon_fork": "bon_fork",
    "job_kind": "job_kind",
}
# Which row fields each gate reads, kit's name → core's path.
GATE_ROWS = {
    "class_gate": (("posting_eligible", "posting_eligible"),),
    "primary_gate": (
        ("primary_kinds", "primary.required_kinds"),
        ("emit_on_incomplete", "emit_on_incomplete"),
    ),
    "identity_gate": (
        ("needs_client_on_doc", "identity.needs_tenant_on_doc"),
        ("needs_counterparty_cui", "identity.needs_counterparty_cui"),
    ),
    "bon_fork": (("bon_cui_fork", "identity.bon_cui_fork"),),
}
ROW_FIELDS = (
    *(f for fs in GATE_ROWS.values() for f in fs),
    ("fiscal_class", "fiscal_class"),
    ("our_role_default", "our_role_default"),
    ("split.question", "split.hitl"),
    ("split.children", "split.children"),
)


@cache
def _kcat():
    return load_catalog(ROOT / "catalog")


@cache
def _ccat():
    return core.load_catalog(_pinned_checkout())


@cache
def _rules_path() -> Path:
    """The core's emit and aisle rules, from the pinned checkout (the pin's install lacks them:
    gap ``rules_file_not_installed``); the file must be the pinned commit's, unmodified."""
    path = _pinned_checkout().parent / "fixtures" / "architecture.jsonlogic.json"
    status = subprocess.run(
        ["git", "-C", str(path.parent), "status", "--porcelain", "--", path.name],
        capture_output=True,
        text=True,
        check=True,
    )
    assert path.is_file() and not status.stdout.strip(), path
    return path


@contextmanager
def _core_rules():
    with mock.patch.object(jsonlogic, "rule", functools.partial(_RULE, path=_rules_path())):
        yield


_RULE = jsonlogic.rule


def _dig(row, path: str):
    cur = row
    for part in path.split("."):
        if cur is None:
            return None
        cur = cur.get(part) if isinstance(cur, dict) else getattr(cur, part, None)
    return cur


def _norm(v):
    if v in (None, [], ()):
        return None
    return list(v) if isinstance(v, (list, tuple)) else v


def _kit_row(sid: str, field: str):
    return _norm(_dig(_kcat().get("SourceDoc", sid), field))


def _core_row(sid: str, field: str):
    return _norm(_dig(_ccat().source_docs[sid], field))


def _shared_ids() -> list[str]:
    return sorted(set(_kcat().ids("SourceDoc")) & set(_ccat().source_docs))


def _same(k, c) -> bool:
    """Two row values alike: lists as sets, and an unset flag as false."""
    if isinstance(k, list) and isinstance(c, list):
        return sorted(k) == sorted(c)
    if k in (False, None) and c in (False, None):
        return True
    return k == c


def _rows_differ(sid: str, gate: str) -> bool:
    return any(not _same(_kit_row(sid, a), _core_row(sid, b)) for a, b in GATE_ROWS[gate])


@cache
def _row_diffs() -> dict[str, dict[str, tuple]]:
    """Per shared source document, each row field the two catalogs set differently."""
    out: dict[str, dict[str, tuple]] = {}
    for sid in _shared_ids():
        for kf, cf in ROW_FIELDS:
            k, c = _kit_row(sid, kf), _core_row(sid, cf)
            if kf == "our_role_default" and c == "either":
                c = None  # the core's child_pack reads "either" as none
            if not _same(k, c):
                out.setdefault(sid, {})[kf] = (k, c)
    return out


# ----- the two sides' sorting, each through its own code -----


def _kit_decide(p: ksort.Pack) -> dict:
    d = ksort.decide(_kcat(), p)
    return {
        "emit": d.emit,
        "job_kind": f"job_{d.job_kind}" if d.job_kind else None,
        "failed": sorted(GATE[g] for g in d.failed),
        "question": d.question,
        "split": d.split,
    }


def _core_decide(p: triage.Pack) -> dict:
    with _core_rules():
        d = triage.decide_emit(_ccat(), p)
    return {"emit": d.emit, "job_kind": d.job_kind, "failed": sorted(d.failed)}


class _Graph:
    """The core's folder_triage graph (``poarta_contabila.triage``, outside the core), run on an
    in-memory checkpointer and job store: the questions it asks, its split, its children."""

    def __init__(self) -> None:
        with _core_rules():
            self.g = triage.build_triage_graph(
                _ccat(), InMemoryJobStore(), checkpointer=MemorySaver()
            )
        self.n = 0

    def _asked(self, cfg) -> str | None:
        st = self.g.get_state(cfg)
        kinds = [i.value["kind"] for t in st.tasks for i in t.interrupts]
        return kinds[0] if kinds else None

    def run(self, p: triage.Pack, answer=None) -> dict:
        self.n += 1
        cfg = {"configurable": {"thread_id": f"batch:{self.n}"}}
        with _core_rules():
            self.g.invoke({"pack": p.model_dump()}, cfg)
            asked = self._asked(cfg)
            values = self.g.get_state(cfg).values
            out = {"question": asked, "split": values.get("split")}
            if answer is not None and asked:
                self.g.invoke(Command(resume=answer), cfg)
                again = self._asked(cfg)
                children = self.g.get_state(cfg).values.get("children")
                out["answer"] = "asked_again" if again else "accepted"
                out["children"] = None if again else children
        return out


@cache
def _graph() -> _Graph:
    return _Graph()


def _as_kit(p: triage.Pack) -> ksort.Pack:
    """The core's pack in the kit's shape: the same facts, the kit's field names."""
    return ksort.Pack(
        client_cui=p.tenant_cui,
        period=p.period,
        source_hash=p.source_hash,
        source_doc_id=p.source_doc_id,
        kinds=list(p.kinds),
        our_role={"n/a": "n_a"}.get(p.our_role, p.our_role),
        counterparty_cui=p.counterparty_cui,
        identity_ok=p.identity_ok,
        is_storno=p.is_storno,
        bon_our_cui_on_doc=p.bon_our_cui_on_doc,
    )


# ----- the corpus: the core's quarter, as each side sorts it -----


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _upload(firm, inv) -> tuple[str, bytes]:
    """An invoice as the core's scenarios upload it (``scenarios.Runner.ingest``)."""
    if inv.foreign:
        return f"{inv.ref}.xml", inv.xml(firm)
    return f"{inv.ref}.zip", inv.spv_zip(firm)


def _core_upload_pack(firm, name: str, data: bytes) -> triage.Pack:
    """An invoice upload's pack as the core's runtime builds it (``runtime.Runtime
    .ingest_upload``): the readers are the core's; the few lines that assemble the pack are
    transcribed here, since the runtime needs its whole stack."""
    xml = core.read_spv_zip(data).invoice if zipfile.is_zipfile(io.BytesIO(data)) else data
    invoice = core.parse_ubl(xml, where=name)
    tenant = TenantRef(cui=firm.cui, saga_firm_folder=firm.folder)
    draft = JobRecord(job_id="pending", tenant=tenant, period="2000-01", status="ingested")
    other = invoice.customer if invoice.supplier.cui == firm.cui else invoice.supplier
    abroad = other.cui is None and (other.country or "RO").upper() != "RO"
    sha = _sha(data)
    src = SourceRef(
        kind="xml" if abroad else "ubl_spv",
        bucket_key="k",
        content_type="application/xml",
        source_hash=sha,
    )
    doc = core.to_canonical(invoice, job=draft, source=src)
    sid = "foreign_invoice_xml" if abroad else "ro_efactura_ubl"
    return triage.Pack(
        tenant_cui=firm.cui,
        saga_firm_folder=firm.folder,
        period=doc.period,
        source_hash=sha,
        source_doc_id=sid,
        kinds=["ubl_spv"] if sid == "ro_efactura_ubl" else ["xml"],
        our_role="outbound" if doc.doc_class in ("iesire", "storn_iesire") else "inbound",
        counterparty_cui=doc.partner.cui,
        identity_ok=True,
        is_storno=doc.is_storno,
    )


def _core_line_packs(firm, stmt) -> list[triage.Pack]:
    """A statement upload (``runtime.Runtime._ingest_statement``): one pack per movement line."""
    read = core.parse_statement(stmt.tables(), core.StatementMeta(**stmt.meta()), firm.cui)
    return [
        triage.Pack(
            tenant_cui=firm.cui,
            saga_firm_folder=firm.folder,
            period=ln.date[:7],
            source_hash=core.line_source_hash(read.statement_id, ln.seq),
            source_doc_id="extras_statement_pdf",
            kinds=["pdf"],
            our_role="n/a",
            identity_ok=True,
        )
        for ln in read.lines
    ]


def _core_container(firm, report) -> triage.Pack:
    """An expense report upload (``runtime.Runtime.ingest_decont``, ``tenant_on_doc`` as the
    synthetic upload says)."""
    up = report.upload(firm)
    return triage.Pack(
        tenant_cui=firm.cui,
        saga_firm_folder=firm.folder,
        period=up["period"],
        source_hash=_sha(report.pdf(firm)),
        source_doc_id="decont_cheltuieli",
        kinds=["pdf"],
        our_role="inbound",
        identity_ok=up["tenant_on_doc"],
    )


@cache
def _months() -> dict:
    return {k: (f, realistic(f, PERIODS, seed=SEED)) for k, f in core.synthetic.FIRMS.items()}


@cache
def _corpus() -> dict:
    """Every upload of the core's quarter, sorted by both sides.

    ``uploads``: (route, kit intake facts, core packs); ``packs``: every core pack with the kit's
    and the core's decision and question; ``splits``: each container's true answer on both."""
    uploads, packs, splits = [], [], []
    graph = _graph()
    with tempfile.TemporaryDirectory() as tmp:
        for key, (firm, m) in _months().items():
            d = open_dossier(Path(tmp), firm.cui)
            for u in m.uploads:
                if u.route == "ingest":
                    name, data = _upload(firm, u.doc)
                    cp = _core_upload_pack(firm, name, data)
                    cps, where = [cp], "invoice"
                    period = cp.period
                elif u.route == "extras":
                    cps, where = _core_line_packs(firm, u.doc), "line"
                    name, data = f"{u.ref}.pdf", u.doc.pdf()
                    period = u.doc.meta()["statement_date"][:7]
                else:
                    cps, where = [_core_container(firm, u.doc)], "container"
                    name, data = f"{u.ref}.pdf", u.doc.pdf(firm)
                    period = u.doc.period
                _, facts = ks.intake(_kcat(), d, period, name, data)
                uploads.append((key, u.route, facts, cps))
                for cp in cps:
                    answer = u.doc.split_answer(firm) if where == "container" else None
                    run = graph.run(cp, answer)
                    packs.append((key, where, cp, run))
                    if answer is not None:
                        splits.append((key, cp, answer, run))
                        for child in run["children"] or []:
                            cc = triage.Pack.model_validate(child["pack"])
                            packs.append((key, "child", cc, graph.run(cc)))
    return {"uploads": uploads, "packs": packs, "splits": splits}


# ----- the probes: every shared source document under every fact both packs carry -----

KINDS = ([], ["pdf"], ["xml"], ["ubl_spv"], ["xlsx"], ["mt940"], ["jpeg"], ["unknown"])
CPS = (None, PARTNER, "RO" + PARTNER, "0" + PARTNER, BAD)


@cache
def _grid() -> tuple[triage.Pack, ...]:
    out = []
    for sid, kinds, ident, cp, storno, bon in product(
        _shared_ids(), KINDS, (False, True), CPS, (False, True), (None, True)
    ):
        out.append(
            triage.Pack(
                tenant_cui=CUI,
                saga_firm_folder="0001",
                period="2026-01",
                source_hash=SHA,
                source_doc_id=sid,
                kinds=kinds,
                our_role="inbound",
                counterparty_cui=cp,
                identity_ok=ident,
                is_storno=storno,
                bon_our_cui_on_doc=bon,
            )
        )
    return tuple(out)


@cache
def _grid_questions() -> tuple:
    """The questions on the grid, through the core's graph: one valid counterparty, no storno
    (neither reads them), every source document, kinds, identity and receipt fork."""
    return tuple(
        (p, _graph().run(p)) for p in _grid() if p.counterparty_cui == PARTNER and not p.is_storno
    )


# ----- the comparisons, each difference tagged with the declared gap that explains it -----


def _spelled(cp: str | None) -> str | None:
    if cp and cp.upper().startswith("RO"):
        return "'RO…'"
    if cp and cp.startswith("0"):
        return "'0…'"
    return None


def _decision_tags(kp: ksort.Pack, cp: triage.Pack) -> list[tuple[str, str, str]]:
    """(gap, the kit's outcome, the core's) for every way the two decisions on one pack differ;
    a difference no declared gap explains is tagged ``unexplained``."""
    k, c = _kit_decide(kp), _core_decide(cp)
    kf, cf = set(k["failed"]), set(c["failed"])
    sid = cp.source_doc_id
    tags = []
    for g in sorted(kf ^ cf):
        mine = g in kf
        out = ("failed", "passed") if mine else ("passed", "failed")
        if g == "emit_rule":
            tags.append(("emit_rule", "emit_rule: absent", "emit_rule: failed"))
        elif g == "job_kind" and not mine and "class_gate" in kf & cf:
            tags.append(
                ("job_kind_when_not_eligible", "job_kind: not evaluated", "job_kind: failed")
            )
        elif g in GATE_ROWS and _rows_differ(sid, g):
            tags.append(("source_doc_rows", f"{sid}.{g}: {out[0]}", f"{sid}.{g}: {out[1]}"))
        elif g == "identity_gate" and _spelled(cp.counterparty_cui):
            s = _spelled(cp.counterparty_cui)
            tags.append(("counterparty_cui_spelling", f"{g} {s}: {out[0]}", f"{g} {s}: {out[1]}"))
        else:
            tags.append(("unexplained", f"{sid}.{g}: {out[0]}", f"{sid}.{g}: {out[1]}"))
    explained = all(t[0] != "unexplained" for t in tags)
    if k["emit"] != c["emit"] and not (tags and explained):
        tags.append(("unexplained", f"emit {k['emit']}", f"emit {c['emit']}"))
    if k["emit"] and c["emit"] and k["job_kind"] != c["job_kind"]:
        tags.append(("unexplained", f"{k['job_kind']}", f"{c['job_kind']}"))
    return tags


def _agree(kp: ksort.Pack, cp: triage.Pack) -> bool:
    k, c = _kit_decide(kp), _core_decide(cp)
    return k["emit"] == c["emit"] and k["job_kind"] == c["job_kind"] and k["failed"] == c["failed"]


def _tally(tags) -> dict[str, tuple[dict, dict]]:
    out: dict[str, tuple[Counter, Counter]] = {}
    for gap, kit, cor in tags:
        a, b = out.setdefault(gap, (Counter(), Counter()))
        a[kit] += 1
        b[cor] += 1
    return {g: (dict(a), dict(b)) for g, (a, b) in out.items()}


@cache
def _corpus_pairs() -> tuple[tuple[str, ksort.Pack, triage.Pack], ...]:
    return tuple((where, _as_kit(cp), cp) for _, where, cp, _ in _corpus()["packs"])


@cache
def _live_invoice_pairs() -> tuple[tuple[dict, triage.Pack], ...]:
    """The kit's live path on every invoice upload: ``kit.steps.intake`` (its own reader, its own
    pack and decision) against the core's pack and decision of the same bytes."""
    return tuple(
        (facts, cps[0]) for _, route, facts, cps in _corpus()["uploads"] if route == "ingest"
    )


PACK_FIELDS = (
    ("client_cui", "tenant_cui"),
    ("period", "period"),
    ("source_hash", "source_hash"),
    ("source_doc_id", "source_doc_id"),
    ("kinds", "kinds"),
    ("our_role", "our_role"),
    ("counterparty_cui", "counterparty_cui"),
    ("identity_ok", "identity_ok"),
    ("is_storno", "is_storno"),
    ("bon_our_cui_on_doc", "bon_our_cui_on_doc"),
)


def _pack_diffs(kit: dict, cor: dict) -> list[tuple[str, object, object]]:
    out = []
    for kf, cf in PACK_FIELDS:
        a, b = kit.get(kf), cor.get(cf)
        if kf == "our_role" and a == "n_a":
            a = "n/a"
        if a != b:
            out.append((kf, a, b))
    return out


def _kit_split(container: triage.Pack, answer) -> list[ksort.Pack] | None:
    try:
        return ksort.split(_kcat(), _as_kit(container), answer)
    except (ksort.SplitError, ValueError):
        return None


@cache
def _split_view() -> dict:
    """Each container's true answer (the core's ``split_answer``) on both sides: accepted or not,
    and each child pack field by field, in the answer's order."""
    accepted, fields, children = Counter(), Counter(), 0
    for _, cp, answer, run in _corpus()["splits"]:
        mine = _kit_split(cp, answer)
        accepted[(mine is not None, run["answer"])] += 1
        theirs = [c["pack"] for c in run["children"] or []]
        if mine is None:
            continue
        for kc, cc in zip(mine, theirs, strict=True):
            children += 1
            for f, a, b in _pack_diffs(kc.model_dump(), cc):
                src = cc["source_doc_id"]
                fields[f"{src}.{f}: {a!r}"] += 1
                fields[f"{src}.{f} (core): {b!r}"] += 1
    return {"accepted": dict(accepted), "children": children, "fields": dict(fields)}


def _probe_answers(container: triage.Pack) -> dict[str, dict]:
    """Wrong and edge answers to one container's ``decont_split``, each changing one thing of a
    part both sides accept."""
    part = {
        "part_hash": hashlib.sha256(b"part").hexdigest(),
        "source_doc_id": "ro_efactura_ubl",
        "kinds": ["ubl_spv"],
        "bon_our_cui_on_doc": None,
        "counterparty_cui": PARTNER,
    }
    other = {**part, "part_hash": hashlib.sha256(b"other").hexdigest()}
    return {
        "good": {"parts": [part, other]},
        "no parts": {"parts": []},
        "same hash twice": {"parts": [part, {**other, "part_hash": part["part_hash"]}]},
        "the container's hash": {"parts": [{**part, "part_hash": container.source_hash}]},
        "not a child": {"parts": [{**part, "source_doc_id": "bon_fiscal", "kinds": ["pdf"]}]},
        "a pdf part with its xml": {"parts": [{**part, "source_doc_id": "ro_efactura_pdf"}]},
        "an unknown field": {"parts": [{**part, "x": 1}]},
        "no kind": {"parts": [{**part, "kinds": []}]},
        "counterparty 'RO…'": {"parts": [{**part, "counterparty_cui": "RO" + PARTNER}]},
        "counterparty '0…'": {"parts": [{**part, "counterparty_cui": "0" + PARTNER}]},
        "counterparty check digit": {"parts": [{**part, "counterparty_cui": BAD}]},
    }


@cache
def _split_probes() -> dict[str, tuple[str, str]]:
    container = _corpus()["splits"][0][1]
    out = {}
    for name, answer in _probe_answers(container).items():
        mine = _kit_split(container, answer)
        run = _Graph().run(container, answer)
        out[name] = ("accepted" if mine is not None else "refused", run["answer"])
    return out


@cache
def _foreign_probes() -> dict:
    """Live-path probes the quarter never holds: each firm's uploaded invoices sent to the next
    firm (the client on neither side), and each RO invoice as its bare XML (no SPV zip)."""
    keys = list(_months())
    stranger, bare = Counter(), Counter()
    with tempfile.TemporaryDirectory() as tmp:
        for i, key in enumerate(keys):
            firm, m = _months()[key]
            other = _months()[keys[(i + 1) % len(keys)]][0]
            d_other, d_own = open_dossier(Path(tmp), other.cui), open_dossier(Path(tmp), firm.cui)
            for u in m.uploads:
                if u.route != "ingest":
                    continue
                name, data = _upload(firm, u.doc)
                _, facts = ks.intake(_kcat(), d_other, u.doc.period, name, data)
                sid = "foreign_invoice_xml" if u.doc.foreign else "ro_efactura_ubl"
                if "refused" in facts:
                    verdict = "refused before a pack"
                    assert "_pack" not in facts and "P13" in facts["refused"]
                else:
                    verdict = "emitted" if facts["emit"] else f"not emitted {facts['failed']}"
                stranger[f"{sid}: {verdict}"] += 1
                try:
                    _core_upload_pack(other, name, data)
                    stranger[f"{sid} (core): a pack"] += 1
                except core.UblError:
                    stranger[f"{sid} (core): refused before a pack"] += 1
                if u.doc.foreign:
                    continue
                name, data = f"{u.ref}.xml", u.doc.xml(firm)
                _, facts = ks.intake(_kcat(), d_own, u.doc.period, name, data)
                cp = _core_upload_pack(firm, name, data)
                kc = _core_decide(cp)
                bare[f"kinds {facts['_pack']['kinds']} emit {facts['emit']}"] += 1
                bare[f"kinds {cp.kinds} emit {kc['emit']} (core)"] += 1
    return {"stranger": dict(stranger), "bare": dict(bare)}


# The buyer's tax id: none (a person), a valid RO CUI, a RO CUI whose check digit fails, a
# foreign VAT id (invented).
B2C_IDS = {
    "no CUI": None,
    "RO CUI": "RO" + PARTNER,
    "bad check digit": "RO" + BAD,
    "foreign VAT id": "DE999999999",
}
B2C_COUNTRIES = (None, "RO", "DE")


def _b2c_buyer(vat: str | None, country: str | None) -> str:
    """An invented buyer: a person (no tax id) or a firm with the tax id given, its country
    absent or given."""
    address = "<cac:PostalAddress><cbc:StreetName>Strada Sintetica 2</cbc:StreetName>"
    address += "<cbc:CityName>Exempla</cbc:CityName>"
    if country:
        address += f"<cac:Country><cbc:IdentificationCode>{country}</cbc:IdentificationCode>"
        address += "</cac:Country>"
    address += "</cac:PostalAddress>"
    tax = (
        f"<cac:PartyTaxScheme><cbc:CompanyID>{vat}</cbc:CompanyID>"
        "<cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme></cac:PartyTaxScheme>"
        if vat
        else ""
    )
    legal = "<cac:PartyLegalEntity><cbc:RegistrationName>CUMPARATOR EXEMPLU</cbc:RegistrationName>"
    legal += "<cbc:CompanyID>J00/2/2021</cbc:CompanyID>" if vat else ""
    legal += "</cac:PartyLegalEntity>"
    return (
        f"<cac:AccountingCustomerParty><cac:Party>{address}{tax}{legal}</cac:Party>"
        "</cac:AccountingCustomerParty>"
    )


@cache
def _b2c_probes() -> tuple[tuple[str, str, str, dict, dict], ...]:
    """Live-path probes the quarter never holds: each of the quarter's 148 RO sales (140
    invoices, 8 credit notes; the client is the seller) with its buyer replaced by an invented
    one, the buyer's tax id (``B2C_IDS``) × its country absent, RO or DE, each as an SPV zip
    and as its bare XML (3552). Each side sorts the same bytes: the kit through
    ``kit.steps.intake``, the core through its runtime's pack assembly and ``decide_emit``.
    Rows: (form, tax id, country, the kit's outcome, the core's)."""
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        for firm, m in _months().values():
            d = open_dossier(Path(tmp), firm.cui)
            for u in m.uploads:
                inv = u.doc
                if u.route != "ingest" or inv.foreign or inv.side != "out":
                    continue
                base = inv.xml(firm).decode("utf-8")
                for (who, vat), country in product(B2C_IDS.items(), B2C_COUNTRIES):
                    xml = re.sub(
                        r"<cac:AccountingCustomerParty>.*?</cac:AccountingCustomerParty>",
                        _b2c_buyer(vat, country),
                        base,
                        flags=re.S,
                    ).encode("utf-8")
                    spv = stable_zip(
                        [(f"{inv.spv_id}.xml", xml), (f"semnatura_{inv.spv_id}.xml", SIGNATURE)]
                    )
                    for form, data in (("zip", spv), ("xml", xml)):
                        name = f"{inv.ref}-{vat or 'none'}-{country or 'none'}.{form}"
                        _, f = ks.intake(_kcat(), d, inv.period, name, data)
                        cp = _core_upload_pack(firm, name, data)
                        c = _core_decide(cp)
                        kit = {
                            "source_doc_id": f["_pack"]["source_doc_id"],
                            "kinds": f["_pack"]["kinds"],
                            "emit": f["emit"],
                            "job_kind": f"job_{f['_job_kind']}" if f["_job_kind"] else None,
                            "failed": sorted(GATE[g] for g in f["failed"]),
                        }
                        cor = {"source_doc_id": cp.source_doc_id, "kinds": cp.kinds, **c}
                        out.append((form, who, country or "absent", kit, cor))
    return tuple(out)


def _b2c_outcome(o: dict) -> str:
    job = f" {o['job_kind']}" if o["job_kind"] else ""
    return f"{o['source_doc_id']} {o['kinds']}: emit {o['emit']}{job}, failed {o['failed']}"


def _b2c_tally(rows) -> tuple[dict, dict]:
    kit, cor = Counter(), Counter()
    for form, cui, country, k, c in rows:
        where = f"{form}, {cui}, country {country}"
        kit[f"{where}: {_b2c_outcome(k)}"] += 1
        cor[f"{where}: {_b2c_outcome(c)}"] += 1
    return dict(kit), dict(cor)


def _after_define_class() -> tuple[dict, dict]:
    """The kit's live answer path on the statements and expense reports its intake calls
    ``unknown``: ``define_class`` answered with the core's class (``kit.steps.APPLY``), then the
    gates again; the core's packs of the same uploads, which its routes name."""
    kit, cor = Counter(), Counter()
    named = {"extras": "extras_statement_pdf", "decont": "decont_cheltuieli"}
    for _, route, facts, cps in _corpus()["uploads"]:
        if route not in named:
            continue
        after = ks.APPLY["define_class"](
            _kcat(), None, "batch:x", facts, {}, {"source_doc_id": named[route]}
        )
        kit[
            f"{named[route]}: failed {after['failed']}, asks {after['question']},"
            f" split {after['split']}"
        ] += 1
        for cp in cps:
            c = _core_decide(cp)
            run = next(r for _, _, p, r in _corpus()["packs"] if p is cp)
            cor[
                f"{cp.source_doc_id}: emit {c['emit']} {c['job_kind']}, asks {run['question']}"
            ] += 1
    return dict(kit), dict(cor)


def _kit_imports() -> list[str]:
    names = set()
    for path in sorted((ROOT / "kit").glob("*.py")):
        if path.name == "sorting.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module == "kit.sorting":
                names |= {a.name for a in node.names}
    return sorted(names)


def _required(model) -> list[str]:
    return sorted(n for n, f in model.model_fields.items() if f.is_required())


def _literal(model, field: str) -> list:
    """A field's options: a Literal's values, ``None`` where it is optional."""
    ann = model.model_fields[field].annotation
    if typing.get_origin(ann) is typing.Literal:
        return list(typing.get_args(ann))
    out: list = []
    for a in typing.get_args(ann):
        out += [None] if a is type(None) else list(typing.get_args(a))
    return out


TAGGED = ("gates_by_row", "emit_rule", "job_kind_when_not_eligible", "counterparty_cui_spelling")


@cache
def _tags() -> tuple[tuple[str, str, str], ...]:
    """Every decision difference, corpus and probes, as (the kit's, the core's, gap)."""
    corpus = [
        ("corpus: " + k, "corpus: " + c, g)
        for _, kp, cp in _corpus_pairs()
        for g, k, c in _decision_tags(kp, cp)
    ]
    probes = [
        ("probes: " + k, "probes: " + c, g)
        for p in _grid()
        for g, k, c in _decision_tags(_as_kit(p), p)
    ]
    return tuple(corpus + probes)


def _observed(gap: str) -> tuple[object, object]:
    kcat, ccat = _kcat(), _ccat()
    if gap in TAGGED:
        tag = "source_doc_rows" if gap == "gates_by_row" else gap
        return _tally((tag, k, c) for k, c, g in _tags() if g == tag).get(tag, ({}, {}))
    if gap == "class_by_route":
        kit, cor = Counter(), Counter()
        for _, route, facts, cps in _corpus()["uploads"]:
            kit[f"{route}: {facts['_pack']['source_doc_id']}"] += 1
            cor[f"{route}: {cps[0].source_doc_id}"] += 1
        return dict(kit), dict(cor)
    if gap == "statement_grain":
        ups = [(f, cps) for _, r, f, cps in _corpus()["uploads"] if r == "extras"]
        return {"statements": len(ups), "packs": len(ups)}, {
            "statements": len(ups),
            "packs": sum(len(cps) for _, cps in ups),
        }
    if gap == "named_after_define_class":
        return _after_define_class()
    if gap == "bare_xml_kinds":
        b = _foreign_probes()["bare"]
        return (
            {k: v for k, v in b.items() if "(core)" not in k},
            {k: v for k, v in b.items() if "(core)" in k},
        )
    if gap == "source_doc_ids":
        mine, theirs = set(kcat.ids("SourceDoc")), set(ccat.source_docs)
        return sorted(mine - theirs), sorted(theirs - mine)
    if gap == "source_doc_rows":
        rows = _row_diffs()
        return (
            {f"{s}.{f}": v[0] for s, fs in rows.items() for f, v in fs.items()},
            {f"{s}.{f}": v[1] for s, fs in rows.items() for f, v in fs.items()},
        )
    if gap == "split_part_cui":
        probes = _split_probes()
        names = ("counterparty 'RO…'", "counterparty check digit")
        return {n: probes[n][0] for n in names}, {n: probes[n][1] for n in names}
    if gap == "split_part_without_kind":
        k, c = _split_probes()["no kind"]
        return {"no kind": k}, {"no kind": c}
    if gap == "child_role":
        f = _split_view()["fields"]
        return (
            {k: v for k, v in f.items() if "(core)" not in k},
            {k.replace(" (core)", ""): v for k, v in f.items() if "(core)" in k},
        )
    if gap == "job_kind_ids":
        mine = {
            j: (sorted(kcat.get("JobKind", j).source_docs), kcat.get("JobKind", j).storno)
            for j in kcat.ids("JobKind")
        }
        theirs = {
            j: (sorted(r.get("source_doc_ids") or []), j == "job_storno")
            for j, r in ccat.jobs.items()
        }
        return sorted(mine), sorted(theirs)
    if gap == "gate_names":
        seen = {g for p in _grid() for g in _core_decide(p)["failed"]}
        return list(ksort.GATES), sorted(seen)
    if gap == "decision_shape":
        return list(ksort.Decision.model_fields), list(triage.EmitDecision.model_fields)
    if gap == "pack_shape":
        return (
            {
                "fields": list(ksort.Pack.model_fields),
                "required": _required(ksort.Pack),
                "our_role": _literal(ksort.Pack, "our_role"),
            },
            {
                "fields": list(triage.Pack.model_fields),
                "required": _required(triage.Pack),
                "our_role": _literal(triage.Pack, "our_role"),
            },
        )
    if gap == "rules_file_not_installed":
        try:
            triage.decide_emit(ccat, _grid()[0])
            theirs = "ran"
        except FileNotFoundError:
            theirs = "FileNotFoundError"
        return None, {"installed": jsonlogic.RULES_PATH.is_file(), "decide_emit": theirs}
    if gap == "caller_shapes":
        names = _kit_imports()
        return names, {n: "present" if hasattr(core, n) else "absent" for n in names}
    raise KeyError(gap)


# ----- the corpus -----


def test_the_corpus_is_the_cores_quarter_and_every_invented_cui_is_valid() -> None:
    """393 uploads (365 invoices, 15 statements, 13 expense reports) give 668 core packs: 365
    invoices, 248 statement lines, 13 containers and the 42 parts their true answers name (19
    invoices, 14 receipts, 9 working papers). Left out, counted: 9 payroll statements (no route
    uploads one on the core's side) and 6 invoices with no upload (the quarter's hidden
    documents). Every firm's CUI and the probes' invented CUIs pass both check digits; the
    probes' other spellings are made to fail one side or both."""
    c = _corpus()
    assert Counter(r for _, r, _, _ in c["uploads"]) == {"ingest": 365, "extras": 15, "decont": 13}
    assert Counter(w for _, w, _, _ in c["packs"]) == {
        "invoice": 365,
        "line": 248,
        "container": 13,
        "child": 42,
    }
    parts = Counter(
        type(doc).__name__
        for _, m in _months().values()
        for u in m.uploads
        if u.route == "decont"
        for doc, _ in u.doc.parts
    )
    assert parts == {"Invoice": 19, "Bon": 14, "Workings": 9}
    left = Counter()
    for _, m in _months().values():
        up = {u.ref for u in m.uploads}
        named = {d.ref for u in m.uploads if u.route == "decont" for d, _ in u.doc.parts}
        left["payroll"] += sum(type(d).__name__ == "Payroll" for d in m.docs.values())
        left["hidden"] += sum(i.ref not in up | named for i in m.invoices())
    assert left == {"payroll": 9, "hidden": 6}
    for firm in core.synthetic.FIRMS.values():
        assert cui_is_valid(firm.cui) and core.cui_is_valid(firm.cui)
    for x in (CUI, PARTNER):
        assert cui_is_valid(x) and core.cui_is_valid(x)
    assert not cui_is_valid(BAD) and not core.cui_is_valid(BAD)
    assert len(_grid()) == 5120 and len(_grid_questions()) == 512


def test_the_cores_sorting_is_outside_the_core() -> None:
    """The core re-exports no sorting module: ``poarta_contabila.triage`` (``Pack``,
    ``decide_emit``, ``check_split``, ``child_pack``, the folder_triage graph) is not among
    ``CORE_MODULES``, and imports a graph and the question interrupt. What the core does carry
    for sorting is data and types: the ``ArticoleSourceDoc`` and ``ArticoleJobs`` rows
    (``core.catalog``), ``PrimaryKind``, ``Cui`` and ``cui_is_valid`` (``core.types``)."""
    assert triage.__name__ not in core.CORE_MODULES_FLAT
    assert not any(n.startswith("core.sort") or n == "core.triage" for n in core.CORE_MODULES)
    assert {"PrimaryKind", "Cui", "cui_is_valid", "load_catalog"} <= set(core.__all__)
    text = Path(triage.__file__).read_text(encoding="utf-8")
    assert "from langgraph.graph import" in text and "from poarta_contabila.hitl import ask" in text


# ----- what agrees -----


def test_the_decisions_agree_on_the_corpus_overall_and_on_the_live_paths() -> None:
    """On all 668 packs, the same pack to both: emit and the Job kind agree on 668 (625 emit:
    337 ``job_ro_efactura``, 20 ``job_storno``, 8 ``job_foreign_invoice``, 248
    ``job_extras_line``, 12 parts; 43 do not); the failed gates agree on 625, all of them empty
    against empty, so no non-empty list of failed gates agrees on the corpus (the probes' do,
    below). The 43 others are the 13 containers and the 30 parts that do not emit, each in a
    declared gap.

    Live: the kit's intake (``kit.steps.intake``: its own reader, pack and decision) on all 365
    invoice uploads gives the core's pack field by field and the core's decision, all 365. The
    42 parts are live through ``kit/scenario.py`` only (see ``named_after_define_class``):
    emit and Job kind agree on 42, the failed gates on 12. The 13 containers are live through
    ``kit/scenario.py`` only. The 248 statement lines have no builder in the kit: no kit module
    builds an ``extras_statement_pdf`` pack, though ``kit emit`` decides a hand-written one."""
    pairs = _corpus_pairs()
    kits = [_kit_decide(k) for _, k, _ in pairs]
    cores = [_core_decide(c) for _, _, c in pairs]
    same = Counter(
        (w, k["emit"] == c["emit"] and k["job_kind"] == c["job_kind"], k["failed"] == c["failed"])
        for (w, _, _), k, c in zip(pairs, kits, cores, strict=True)
    )
    assert same == {
        ("invoice", True, True): 365,
        ("line", True, True): 248,
        ("child", True, True): 12,
        ("child", True, False): 30,
        ("container", True, False): 13,
    }
    assert Counter(c["job_kind"] for c in cores if c["emit"]) == {
        "job_ro_efactura": 337 + 12,
        "job_storno": 20,
        "job_foreign_invoice": 8,
        "job_extras_line": 248,
    }
    assert all(
        not k["failed"] for k, c in zip(kits, cores, strict=True) if k["failed"] == c["failed"]
    )
    assert sum(k["failed"] == c["failed"] for k, c in zip(kits, cores, strict=True)) == 625
    live = _live_invoice_pairs()
    assert all(not _pack_diffs(f["_pack"], cp.model_dump()) for f, cp in live) and len(live) == 365
    assert Counter(
        (f["emit"], f"job_{f['_job_kind']}" == _core_decide(cp)["job_kind"], tuple(f["failed"]))
        for f, cp in live
    ) == {(True, True, ()): 365}
    unexplained = [t for t in _tags() if t[2] == "unexplained"]
    assert not unexplained, unexplained[:5]
    assert {t[2] for t in _tags() if t[0].startswith("corpus")} == {
        "emit_rule",
        "job_kind_when_not_eligible",
        "source_doc_rows",
    }


def test_the_probes_show_every_gate_both_ways_and_emit_turns_only_on_declared_gaps() -> None:
    """The 5120 probes (16 shared source documents × 8 kinds × identity × 5 counterparty
    spellings × storno × the receipt fork): emit agrees on 5078 (4770 refused, 308 emitted on
    both), the Job kind wherever both emit; the failed gates agree on 1588, 1280 of them
    non-empty. Emit differs on 42 (24 the kit's only, 18 the core's), each in
    ``gates_by_row`` or ``counterparty_cui_spelling``; ``emit_rule`` never fails alone, so it
    never decides emit."""
    emit, gates, why, alone = Counter(), Counter(), Counter(), 0
    for p in _grid():
        kp = _as_kit(p)
        k, c = _kit_decide(kp), _core_decide(p)
        emit[(k["emit"], c["emit"])] += 1
        if k["emit"] and c["emit"]:
            assert k["job_kind"] == c["job_kind"], p
        if _agree(kp, p):
            gates["non-empty" if k["failed"] else "empty"] += 1
        if k["emit"] != c["emit"]:
            why[tuple(sorted({t[0] for t in _decision_tags(kp, p)}))] += 1
        alone += c["failed"] == ["emit_rule"]
    assert emit == {(False, False): 4770, (True, True): 308, (True, False): 24, (False, True): 18}
    assert gates == {"non-empty": 1280, "empty": 308}
    assert why == {
        ("source_doc_rows",): 18,
        ("counterparty_cui_spelling",): 16,
        ("counterparty_cui_spelling", "source_doc_rows"): 8,
    }
    assert alone == 0
    seen = Counter(g for p in _grid() for g in _core_decide(p)["failed"])
    assert set(seen) == {GATE[g] for g in ksort.GATES} | {"emit_rule"}
    seen_kit = Counter(g for p in _grid() for g in ksort.decide(_kcat(), _as_kit(p)).failed)
    assert set(seen_kit) == set(ksort.GATES)


def test_the_identity_gate_agrees_where_the_rows_and_spellings_do() -> None:
    """On the corpus the identity gate passes on both sides for all 668 packs, so its agreement
    there is vacuous. On the probes: both fail 768, both pass 3904; the core alone fails 384
    (``spv_register`` and ``stat_salarii`` 160 each, a counterparty spelled ``RO…`` 64), the
    kit alone 64 (a counterparty spelled ``0…``). Live, an invoice sent to a firm on neither
    side never reaches the gate: both refuse it before a pack (P13, below)."""
    corpus = Counter(
        ("identity_gate" in _kit_decide(k)["failed"], "identity_gate" in _core_decide(c)["failed"])
        for _, k, c in _corpus_pairs()
    )
    assert corpus == {(False, False): 668}
    probes = Counter(
        (
            "identity_gate" in _kit_decide(_as_kit(p))["failed"],
            "identity_gate" in _core_decide(p)["failed"],
        )
        for p in _grid()
    )
    assert probes == {
        (False, False): 3904,
        (True, True): 768,
        (False, True): 384,
        (True, False): 64,
    }


def test_the_questions_and_the_split_flag_agree_everywhere() -> None:
    """The kit's ``Decision.question`` and ``split`` against the first question the core's
    folder_triage graph asks and its ``split``. Corpus: 13 ``decont_split`` with the split on
    both, 655 none. ``define_class`` and ``bon_cui_unclear`` are never asked on the corpus;
    the 512 graph probes ask each on both sides (32 and 16), ``decont_split`` 4, none 460, so
    no question's agreement is vacuous."""
    corpus = Counter()
    for (_, _, cp, run), (_, kp, _) in zip(_corpus()["packs"], _corpus_pairs(), strict=True):
        k = _kit_decide(kp)
        assert (k["question"], k["split"]) == (run["question"], run["split"]), cp
        corpus[k["question"]] += 1
    assert corpus == {None: 655, "decont_split": 13}
    probes = Counter()
    for p, run in _grid_questions():
        k = _kit_decide(_as_kit(p))
        assert k["question"] == run["question"], p
        if run["question"] in (None, "decont_split"):
            assert k["split"] == run["split"], p
        probes[k["question"]] += 1
    assert probes == {None: 460, "define_class": 32, "bon_cui_unclear": 16, "decont_split": 4}


def test_the_splits_agree_on_the_true_answers_and_on_most_probes() -> None:
    """The 13 containers' true answers: accepted on both; 42 parts, 33 the same pack field by
    field, 9 working papers in ``child_role``. Eleven probe answers on one container: 8 agree
    (2 accepted on both, 6 refused on both: no part, a hash twice, the container's hash, a
    source document that is not a child, a PDF part with its XML, an unknown field), 3 in the
    declared gaps ``split_part_cui`` and ``split_part_without_kind``."""
    view = _split_view()
    assert view["accepted"] == {(True, "accepted"): 13} and view["children"] == 42
    diffs = sum(v for k, v in view["fields"].items() if "(core)" not in k)
    assert diffs == 9
    probes = _split_probes()
    both = {("accepted", "accepted"), ("refused", "asked_again")}
    agree = {n: v for n, v in probes.items() if v in both}
    assert sorted(agree) == [
        "a pdf part with its xml",
        "an unknown field",
        "counterparty '0…'",
        "good",
        "no parts",
        "not a child",
        "same hash twice",
        "the container's hash",
    ]
    assert Counter(v for v in agree.values()) == {
        ("accepted", "accepted"): 2,
        ("refused", "asked_again"): 6,
    }


def test_the_b2c_probes_agree_on_the_class_emit_the_job_kind_and_the_gates() -> None:
    """The 3552 B2C probes (148 sales × the buyer's tax id: none, a valid RO CUI, a RO CUI whose
    check digit fails, a foreign VAT id × its country absent, RO or DE × SPV zip or bare XML):
    the class, emit, the Job kind and the failed gates agree on all 3552. Both read a buyer as
    abroad only when it has no valid RO CUI and a country other than RO, an absent country
    meaning RO (888: 840 ``job_foreign_invoice``, the 48 credit notes failing ``job_kind``, in
    a zip as in XML, the kinds ``xml`` on both); a buyer with a valid RO CUI is a RO sale
    wherever it is (888 emit: 840 ``job_ro_efactura``, 48 ``job_storno``); the rest, with no
    valid RO CUI and no country or RO, is a RO sale that fails ``identity_gate`` (1776). The
    kinds differ only on a RO sale as bare XML, ``xml`` vs ``ubl_spv``, the fact of
    ``bare_xml_kinds`` (1332)."""
    rows = _b2c_probes()
    assert len(rows) == 3552
    keys = ("source_doc_id", "emit", "job_kind", "failed")
    outcomes, kinds = Counter(), Counter()
    for form, who, country, k, c in rows:
        assert all(k[x] == c[x] for x in keys), (form, who, country, k, c)
        outcomes[(k["source_doc_id"], k["emit"], k["job_kind"], tuple(k["failed"]))] += 1
        if k["kinds"] != c["kinds"]:
            assert (form, k["source_doc_id"], k["kinds"], c["kinds"]) == (
                "xml",
                "ro_efactura_ubl",
                ["xml"],
                ["ubl_spv"],
            )
        kinds[k["kinds"] == c["kinds"]] += 1
    assert outcomes == {
        ("foreign_invoice_xml", True, "job_foreign_invoice", ()): 840,
        ("foreign_invoice_xml", False, None, ("job_kind",)): 48,
        ("ro_efactura_ubl", True, "job_ro_efactura", ()): 840,
        ("ro_efactura_ubl", True, "job_storno", ()): 48,
        ("ro_efactura_ubl", False, None, ("identity_gate",)): 1776,
    }
    assert kinds == {True: 3552 - 1332, False: 1332}


def test_a_buyer_whose_cui_fails_its_check_digit_or_is_a_foreign_vat_id_reads_alike() -> None:
    """The probes R8's review asked for, pinned on both sides: a buyer whose RO CUI fails its
    check digit, or whose tax id is a foreign VAT id, has no CUI on either side; with its
    country absent or RO it is a RO sale failing the identity gate, with DE an invoice from
    abroad (the kinds ``xml``, from a zip too). Only a RO sale's kinds as bare XML differ."""
    kit, cor = _b2c_tally(r for r in _b2c_probes() if r[1] in ("bad check digit", "foreign VAT id"))
    expected = {}
    for who, form in product(("bad check digit", "foreign VAT id"), ("xml", "zip")):
        ro = f"ro_efactura_ubl ['{'xml' if form == 'xml' else 'ubl_spv'}']"
        for country in ("absent", "RO"):
            expected[
                f"{form}, {who}, country {country}: {ro}: emit False, failed ['identity_gate']"
            ] = 148
        abroad = f"{form}, {who}, country DE: foreign_invoice_xml ['xml']"
        expected[f"{abroad}: emit True job_foreign_invoice, failed []"] = 140
        expected[f"{abroad}: emit False, failed ['job_kind']"] = 8
    assert kit == expected
    assert cor == {
        k.replace("ro_efactura_ubl ['xml']", "ro_efactura_ubl ['ubl_spv']"): v
        for k, v in expected.items()
    }


@pytest.mark.law("P13")
def test_an_invoice_sent_to_a_firm_on_neither_side_is_refused_before_a_pack_on_both() -> None:
    """Live: each of the 365 invoice uploads sent to the next firm, which is on neither side,
    through ``kit.steps.intake``: the kit refuses all 365 before any pack (no source stored, no
    pack, no Job; the batch issue holds the reason), as the core's ``to_canonical`` does, the 8
    foreign as the 357 RO."""
    s = _foreign_probes()["stranger"]
    assert s == {
        "foreign_invoice_xml: refused before a pack": 8,
        "ro_efactura_ubl: refused before a pack": 357,
        "foreign_invoice_xml (core): refused before a pack": 8,
        "ro_efactura_ubl (core): refused before a pack": 357,
    }


def test_both_catalogs_list_the_same_documents_under_each_job_kind() -> None:
    """Under the core's ``job_`` prefix, each Job kind lists the same source documents and the
    same storno flag on both catalogs; only the names differ (``job_kind_ids``)."""
    kcat, ccat = _kcat(), _ccat()
    for j in kcat.ids("JobKind"):
        row = kcat.get("JobKind", j)
        theirs = ccat.jobs[f"job_{j}"]
        assert sorted(row.source_docs) == sorted(theirs["source_doc_ids"]), j
        assert row.storno == (j == "storno"), j


def test_an_unknown_source_document_is_refused_on_both_sides() -> None:
    p = _grid()[0].model_copy(update={"source_doc_id": "nope"})
    with pytest.raises(CatalogError):
        ksort.decide(_kcat(), _as_kit(p))
    with pytest.raises(core.CatalogError), _core_rules():
        triage.decide_emit(_ccat(), p)


def test_the_kit_split_takes_part_cuis_unchecked_and_keeps_their_spelling() -> None:
    """``Part.counterparty_cui`` and ``Pack.counterparty_cui`` are plain ``str`` in the kit
    (``kit/sorting.py``): a part's CUI that fails its check digit, or is spelled ``RO…``, is
    accepted by ``split`` and copied as written into the child pack; only the child's identity
    gate reads it, and only where the row needs a counterparty CUI. The core's ``SplitPart``
    types it ``Cui`` (the probes ``split_part_cui``), though its ``Pack`` keeps a plain str."""
    container = _as_kit(_corpus()["splits"][0][1])
    answer = _probe_answers(_corpus()["splits"][0][1])["counterparty 'RO…'"]
    (child,) = ksort.split(_kcat(), container, answer)
    assert child.counterparty_cui == "RO" + PARTNER and ksort.decide(_kcat(), child).emit
    bad = {"parts": [{**answer["parts"][0], "source_doc_id": "workings", "counterparty_cui": BAD}]}
    (child,) = ksort.split(_kcat(), container, bad)
    assert child.counterparty_cui == BAD and "identity" not in ksort.decide(_kcat(), child).failed
    assert ksort.Pack.model_fields["counterparty_cui"].annotation == str | None
    assert triage.Pack.model_fields["counterparty_cui"].annotation == str | None


# ----- declared gaps: the module waits on the owner (BUILD WP-20) -----

PARITY_GAPS: dict[str, tuple[object, object]] = {
    # What each upload is: the kit's intake reads the file (an invoice's XML, else unknown);
    # the core's routes name it (/ingest, /extras, /decont), so it never meets an unknown here.
    "class_by_route": (
        {
            "decont: unknown": 13,
            "extras: unknown": 15,
            "ingest: foreign_invoice_xml": 8,
            "ingest: ro_efactura_ubl": 357,
        },
        {
            "decont: decont_cheltuieli": 13,
            "extras: extras_statement_pdf": 15,
            "ingest: foreign_invoice_xml": 8,
            "ingest: ro_efactura_ubl": 357,
        },
    ),
    # A statement: one pack per file in the kit, one per movement line in the core.
    "statement_grain": (
        {"packs": 15, "statements": 15},
        {"packs": 248, "statements": 15},
    ),
    # The kit's answer path: define_class naming the core's class keeps the intake's
    # identity_ok false (kit.steps._redecide sets only source_doc_id), so no statement emits and
    # no expense report asks for its parts; the core's routes set identity_ok. It waits on the
    # owner: the kit has no fact for identity_ok on a file that is not UBL (R8d), so the owner
    # decides whether a person may state that the client is on it, in which question, or
    # whether a statement reader comes first.
    "named_after_define_class": (
        {
            "decont_cheltuieli: failed ['class', 'identity'], asks None, split False": 13,
            "extras_statement_pdf: failed ['identity'], asks None, split False": 15,
        },
        {
            "decont_cheltuieli: emit False None, asks decont_split": 13,
            "extras_statement_pdf: emit True job_extras_line, asks None": 248,
        },
    ),
    # A RO invoice as its bare XML (no SPV zip): the kit's intake writes kinds ['xml'], the
    # core's runtime ['ubl_spv']; both emit, since the kit's ro_efactura_ubl row takes xml.
    "bare_xml_kinds": (
        {"kinds ['xml'] emit True": 357},
        {"kinds ['ubl_spv'] emit True (core)": 357},
    ),
    # Source documents only one catalog has.
    "source_doc_ids": (
        ["sink_balanta", "sink_jurnal_cumparari", "sink_jurnal_vanzari"],
        ["recon_vendor", "sink_balanta_nextup", "sink_balanta_saga", "sink_rj_nextup"],
    ),
    # The shared rows' fields where the catalogs differ (the core's "either" is read as none,
    # as its child_pack reads it): the catalog.py step's ground, and the cause of gates_by_row.
    "source_doc_rows": (
        {
            "bon_fiscal.our_role_default": "inbound",
            "decont_cheltuieli.fiscal_class": None,
            "decont_part_evidence.fiscal_class": None,
            "decont_part_evidence.our_role_default": None,
            "decont_part_evidence.primary_kinds": None,
            "extras.our_role_default": None,
            "extras.primary_kinds": ["mt940", "sta", "xlsx", "csv"],
            "extras_pdf.our_role_default": None,
            "extras_statement_pdf.our_role_default": None,
            "instructions.fiscal_class": None,
            "instructions.our_role_default": None,
            "ro_efactura_ubl.primary_kinds": ["ubl_spv", "xml"],
            "sink_rj.fiscal_class": None,
            "sink_rj.our_role_default": None,
            "sink_rj.primary_kinds": None,
            "spv_register.fiscal_class": None,
            "spv_register.needs_client_on_doc": False,
            "spv_register.our_role_default": None,
            "spv_register.primary_kinds": None,
            "stat_salarii.fiscal_class": None,
            "stat_salarii.needs_client_on_doc": False,
            "stat_salarii.our_role_default": None,
            "stat_salarii.primary_kinds": None,
            "unknown.fiscal_class": None,
            "unknown.our_role_default": None,
            "unknown.primary_kinds": None,
            "workings.fiscal_class": None,
            "workings.our_role_default": None,
            "workings.primary_kinds": None,
        },
        {
            "bon_fiscal.our_role_default": "n/a",
            "decont_cheltuieli.fiscal_class": "decont",
            "decont_part_evidence.fiscal_class": "decont",
            "decont_part_evidence.our_role_default": "inbound",
            "decont_part_evidence.primary_kinds": ["pdf", "jpeg", "png"],
            "extras.our_role_default": "n/a",
            "extras.primary_kinds": ["mt940", "sta", "xlsx", "csv", "pdf"],
            "extras_pdf.our_role_default": "n/a",
            "extras_statement_pdf.our_role_default": "n/a",
            "instructions.fiscal_class": "instructions",
            "instructions.our_role_default": "n/a",
            "ro_efactura_ubl.primary_kinds": ["ubl_spv"],
            "sink_rj.fiscal_class": "recon",
            "sink_rj.our_role_default": "n/a",
            "sink_rj.primary_kinds": ["xls", "xlsx", "csv", "pdf"],
            "spv_register.fiscal_class": "recon",
            "spv_register.needs_client_on_doc": True,
            "spv_register.our_role_default": "n/a",
            "spv_register.primary_kinds": ["xlsx", "csv"],
            "stat_salarii.fiscal_class": "payroll",
            "stat_salarii.needs_client_on_doc": True,
            "stat_salarii.our_role_default": "n/a",
            "stat_salarii.primary_kinds": ["pdf", "xls", "xlsx"],
            "unknown.fiscal_class": "unknown",
            "unknown.our_role_default": "n/a",
            "unknown.primary_kinds": ["unknown"],
            "workings.fiscal_class": "workings",
            "workings.our_role_default": "n/a",
            "workings.primary_kinds": ["xlsx", "csv", "pdf"],
        },
    ),
    # The gates those rows turn: the same pack passes on one side and fails on the other.
    "gates_by_row": (
        {
            "corpus: decont_part_evidence.primary_gate: failed": 16,
            "corpus: workings.primary_gate: failed": 9,
            "probes: decont_part_evidence.primary_gate: failed": 80,
            "probes: extras.primary_gate: failed": 40,
            "probes: ro_efactura_ubl.primary_gate: passed": 40,
            "probes: sink_rj.primary_gate: failed": 80,
            "probes: spv_register.identity_gate: passed": 160,
            "probes: spv_register.primary_gate: failed": 40,
            "probes: stat_salarii.identity_gate: passed": 160,
            "probes: stat_salarii.primary_gate: failed": 80,
            "probes: unknown.primary_gate: failed": 40,
            "probes: workings.primary_gate: failed": 80,
        },
        {
            "corpus: decont_part_evidence.primary_gate: passed": 16,
            "corpus: workings.primary_gate: passed": 9,
            "probes: decont_part_evidence.primary_gate: passed": 80,
            "probes: extras.primary_gate: passed": 40,
            "probes: ro_efactura_ubl.primary_gate: failed": 40,
            "probes: sink_rj.primary_gate: passed": 80,
            "probes: spv_register.identity_gate: failed": 160,
            "probes: spv_register.primary_gate: passed": 40,
            "probes: stat_salarii.identity_gate: failed": 160,
            "probes: stat_salarii.primary_gate: passed": 80,
            "probes: unknown.primary_gate: passed": 40,
            "probes: workings.primary_gate: passed": 80,
        },
    ),
    # The core's JsonLogic emit rule, a gate the kit does not have; it never fails alone.
    "emit_rule": (
        {"corpus: emit_rule: absent": 43, "probes: emit_rule: absent": 3360},
        {"corpus: emit_rule: failed": 43, "probes: emit_rule: failed": 3360},
    ),
    # A document that is not posting-eligible: the kit does not look for its Job kind, the core
    # lists the job_kind gate failed as well.
    "job_kind_when_not_eligible": (
        {"corpus: job_kind: not evaluated": 43, "probes: job_kind: not evaluated": 2880},
        {"corpus: job_kind: failed": 43, "probes: job_kind: failed": 2880},
    ),
    # A counterparty CUI spelled RO… passes the kit's check digit and fails the core's; one
    # spelled with a leading zero fails the kit's and passes the core's.
    "counterparty_cui_spelling": (
        {"probes: identity_gate '0…': failed": 64, "probes: identity_gate 'RO…': passed": 64},
        {"probes: identity_gate '0…': passed": 64, "probes: identity_gate 'RO…': failed": 64},
    ),
    # A split part's CUI: the kit's Part takes any str, the core's SplitPart a valid key. This
    # is kit.sorting.split called directly: on the Dispatcher's and kit answer's path the answer
    # record check (cui?) strips RO and refuses a bad check digit first (the questions step's
    # cui_spelling, the answer grammar), so it is reachable only through kit emit --split (a dry
    # run: it prints the children and writes nothing) and kit/scenario.py.
    "split_part_cui": (
        {"counterparty 'RO…'": "accepted", "counterparty check digit": "accepted"},
        {"counterparty 'RO…'": "asked_again", "counterparty check digit": "asked_again"},
    ),
    # A split part with no kind: the kit accepts it (the child then fails its primary gate),
    # the core's SplitPart needs one. The same fact as the no-kind part of the questions step's
    # decont_split_parts, there in the answer grammar.
    "split_part_without_kind": ({"no kind": "accepted"}, {"no kind": "asked_again"}),
    # A working-papers part's role: the container's in the kit (no default on its row), n/a in
    # the core (its row's default).
    "child_role": (
        {"workings.our_role: 'inbound'": 9},
        {"workings.our_role: 'n/a'": 9},
    ),
    # The Job kinds' names; their documents and storno flag agree.
    "job_kind_ids": (
        ["bon", "extras", "extras_line", "foreign_invoice", "ro_efactura", "storno"],
        [
            "job_bon",
            "job_extras",
            "job_extras_line",
            "job_foreign_invoice",
            "job_ro_efactura",
            "job_storno",
        ],
    ),
    # The gates' names (and the core's emit_rule).
    "gate_names": (
        ["class", "primary", "identity", "bon_fork", "job_kind"],
        ["bon_fork", "class_gate", "emit_rule", "identity_gate", "job_kind", "primary_gate"],
    ),
    # The decision: the kit's carries its question, split and Job key; the core's its aisle,
    # while its questions and split are the graph's (outside the core).
    "decision_shape": (
        ["emit", "job_kind", "failed", "question", "split", "job_key"],
        ["emit", "job_kind", "aisle", "failed"],
    ),
    # The pack: field names, what is required, the role's options.
    "pack_shape": (
        {
            "fields": [
                "client_cui",
                "period",
                "source_hash",
                "source_doc_id",
                "kinds",
                "our_role",
                "counterparty_cui",
                "identity_ok",
                "is_storno",
                "bon_our_cui_on_doc",
            ],
            "our_role": ["inbound", "outbound", "n_a", None],
            "required": ["client_cui", "period", "source_doc_id", "source_hash"],
        },
        {
            "fields": [
                "tenant_cui",
                "saga_firm_folder",
                "punct",
                "period",
                "source_hash",
                "source_doc_id",
                "kinds",
                "our_role",
                "counterparty_cui",
                "identity_ok",
                "is_storno",
                "bon_our_cui_on_doc",
            ],
            "our_role": ["inbound", "outbound", "n/a"],
            "required": [
                "kinds",
                "our_role",
                "period",
                "saga_firm_folder",
                "source_doc_id",
                "source_hash",
                "tenant_cui",
            ],
        },
    ),
    # The core's decide_emit reads its emit and aisle rules from fixtures/ beside the package,
    # which the pinned install does not carry: from the pin it raises; this test reads the rules
    # from the pinned checkout.
    "rules_file_not_installed": (None, {"decide_emit": "FileNotFoundError", "installed": False}),
    # What the kit's other modules import from kit.sorting; the core has none of those names.
    "caller_shapes": (
        ["Pack", "SplitError", "decide", "split"],
        {"Pack": "absent", "SplitError": "absent", "decide": "absent", "split": "absent"},
    ),
}


@pytest.mark.parametrize("gap", sorted(PARITY_GAPS))
def test_each_declared_gap_still_holds_exactly(gap: str) -> None:
    assert _observed(gap) == PARITY_GAPS[gap]
