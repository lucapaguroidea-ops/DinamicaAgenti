"""Kit steps as the Dispatcher's executors: each reads its inputs from the client's dossier and
returns the facts it established (WP-18, ARCHITECTURE §4).

An executor is ``(cat, dossier, issue, facts, detail) -> fields``. It never talks to Paperclip:
an issue it opens is named in ``_spawn`` (``[[issue, parent], …]``) and the Dispatcher creates
it. A step that cannot run raises ``StepError`` with the reason, and the Dispatcher holds the
issue for a person with it. Inputs:

- **sources**: the documents as received (``put_source``), read XML first (P6);
- **books**: the latest books export that covers each month (``put_export``): the kit's reading
  of SAGA's reports as a ``Witness`` (+ ``balances``). Reading SAGA's own export files is R4's;
  until then an export is stored in this form;
- **CO.DiT**: the client's axes for the period (``set_codit``), checked against the catalog;
- **test firm**: only a test firm binds ``draft`` rows (P14).

The package step is WP-10's (the SAGA XML renderer, waiting on R4): it refuses with that reason.
``APPLY`` turns an accepted answer into facts, here or on the issue it is about.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from decimal import Decimal

from kit import calendar
from kit.bind import candidates
from kit.catalog import Catalog
from kit.period import ExpectedItem, ExplainedRule, close_kind, expected_set_hash, period_diff
from kit.questions import question_hash
from kit.recon import Doc, Witness, pick_profile, post_check, pre_check
from kit.route import ReconFacts, route_recon
from kit.sorting import Pack, decide, split
from kit.store import Dossier, StoreError
from kit.ubl import UblError, for_client, parse_ubl, read_spv_zip

Executor = Callable[[Catalog, Dossier, str, dict, dict], dict]
UNDECIDED_PRE = ("ambiguous", "need_export")


class StepError(ValueError):
    """The step cannot run on what the dossier holds; the reason goes to a person."""


# ----- inputs -----


def books(d: Dossier, months: list[str]) -> tuple[Witness, dict[str, str]]:
    """The books for these months: per month, the latest export that covers it."""
    exports = d.exports()
    docs, lines, register, covered, balances = [], [], {}, [], {}
    for m in sorted(set(months)):
        latest = next((e for e in reversed(exports) if m in e["months"]), None)
        if latest is None:
            continue
        body = d.export(latest["export_id"])
        w = Witness.model_validate({k: v for k, v in body.items() if k != "balances"})
        covered.append(m)
        docs += [x for x in w.docs if x.date[:7] == m]
        lines += [x for x in w.lines if x.date[:7] == m]
        for r in w.spv_register:
            register[(r.number, r.date, r.partner_cui)] = r
        if m == max(months):
            balances = dict(body.get("balances") or {})
    return Witness(
        covered=covered, docs=docs, lines=lines, spv_register=list(register.values())
    ), balances


def axes_for(cat: Catalog, d: Dossier, period: str) -> dict[str, str]:
    axes = d.codit(period)
    if axes is None:
        raise StepError(f"no CO.DiT for {period}: set it first (kit dossier set-codit)")
    for axis, value in axes.items():
        row = cat.get("Axis", axis)
        if value not in row.values:
            raise StepError(f"CO.DiT {period}: {value!r} is not a value of {axis}")
    return axes


def _read(data: bytes) -> tuple[bytes, list[str]]:
    """The XML of a document and its kinds: an SPV zip's invoice, or the XML itself."""
    if data[:4] == b"PK\x03\x04":
        return read_spv_zip(data).invoice, ["ubl_spv"]
    return data, ["xml"]


def _job_issue(job_id: str) -> str:
    return f"job:{job_id}"


def _month_issue(kind: str, d: Dossier, period: str) -> str:
    return f"{kind}:{d.client_cui}:{period}"


# ----- Sorting: a file in, a batch issue -----


def intake(cat: Catalog, d: Dossier, period: str, name: str, data: bytes) -> tuple[str, dict]:
    """Store the file and write its batch issue's facts: the pack and the gates' decision.

    An invoice the client is not on alone (neither its seller nor its buyer, or both) is not
    the client's document: it is refused before anything is stored, as the core's upload refuses
    it before any pack. No source, no pack, no Job; the batch issue holds only the reason, and
    the route ends it (P13). An invoice is from abroad as the core reads it: its counterparty
    has no RO CUI and a country other than RO, an absent country meaning RO. Its kind is then
    its XML, whatever it came in (``foreign_invoice_xml``'s primary kind)."""
    try:
        xml, kinds = _read(data)
        ubl = parse_ubl(xml)
    except UblError:
        ubl = None
    if ubl is not None:
        try:
            view = for_client(ubl, d.client_cui)
        except UblError as exc:
            return _refuse(d, data, f"{exc}: not the client's invoice, refused before a pack (P13)")
    source_hash = d.put_source(period, name, data)
    issue = f"batch:{source_hash[:16]}"
    if ubl is None:
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else "file"
        pack = Pack(
            client_cui=d.client_cui,
            period=period,
            source_hash=source_hash,
            source_doc_id="unknown",
            kinds=[ext],
        )
    else:
        other = ubl.buyer if view.our_role == "outbound" else ubl.seller
        abroad = other.cui is None and (other.country or "RO").upper() != "RO"
        pack = Pack(
            client_cui=d.client_cui,
            period=period,
            source_hash=source_hash,
            source_doc_id="foreign_invoice_xml" if abroad else "ro_efactura_ubl",
            kinds=["xml"] if abroad else kinds,
            our_role=view.our_role,
            counterparty_cui=view.counterparty_cui,
            identity_ok=True,
            is_storno=view.is_storno,
        )
    facts = {"_pack": pack.model_dump(), "_name": name, **_decision(cat, pack)}
    d.add_facts(issue, f"intake:{source_hash}", "kit", facts)
    return issue, facts


def _refuse(d: Dossier, data: bytes, reason: str) -> tuple[str, dict]:
    """A file refused at intake: its batch issue gets the reason and nothing else."""
    source_hash = hashlib.sha256(data).hexdigest()
    issue = f"batch:{source_hash[:16]}"
    facts = {"refused": reason, "emit": False, "failed": []}
    d.add_facts(issue, f"refused:{source_hash}", "refusal", facts)
    return issue, facts


def _decision(cat: Catalog, pack: Pack) -> dict:
    dec = decide(cat, pack)
    return {
        "emit": dec.emit,
        "failed": dec.failed,
        "question": dec.question,
        "split": dec.split,
        "_job_kind": dec.job_kind,
    }


def _emit(cat, d: Dossier, issue, facts, detail) -> dict:
    pack = Pack.model_validate(facts["_pack"])
    job, _ = d.insert_job(
        pack.client_cui, pack.source_hash, facts["_job_kind"], pack.source_doc_id, pack.period
    )
    child = _job_issue(job.job_id)
    try:
        d.source(pack.source_hash)
        has_xml = "ubl_spv" in pack.kinds or "xml" in pack.kinds
    except StoreError:
        has_xml = False
    d.add_facts(
        child,
        "emitted",
        "kit",
        {
            "job_id": job.job_id,
            "status": job.status,
            "has_xml": has_xml,
            "book_is_saga": True,
            "_source_hash": pack.source_hash,
            "_period": pack.period,
            "_source_doc_id": pack.source_doc_id,
            "_batch": issue,
        },
    )
    return {
        "job_emitted": True,
        "_job": child,
        "_spawn": [[child, _month_issue("close", d, pack.period)]],
    }


def _emit_children(cat, d: Dossier, issue, facts, detail) -> dict:
    pack = Pack.model_validate(facts["_pack"])
    children = split(cat, pack, {"parts": facts.get("_parts") or []})
    spawned = []
    for child in children:
        key = f"batch:{child.source_hash[:16]}"
        d.add_facts(
            key,
            f"part-of:{issue}",
            "kit",
            {"_pack": child.model_dump(), "_parent": issue, **_decision(cat, child)},
        )
        spawned.append([key, None])
    return {"children_emitted": True, "_spawn": spawned}


# ----- the document path -----


def _extract_xml(cat, d: Dossier, issue, facts, detail) -> dict:
    data, _ = d.source(facts["_source_hash"])
    try:
        xml, _ = _read(data)
        ubl = parse_ubl(xml)
        view = for_client(ubl, d.client_cui)
    except UblError as exc:
        raise StepError(f"the XML does not read: {exc}") from exc
    period = facts["_period"]
    fiscal_class = cat.get("SourceDoc", facts["_source_doc_id"]).fiscal_class
    base = "intrare" if view.our_role == "inbound" else "iesire"
    doc_class = f"storn_{base}" if view.is_storno else base
    doc = Doc(
        doc_class=doc_class,
        number=ubl.number,
        date=ubl.issue_date,
        partner_cui=view.counterparty_cui,
        gross=ubl.totals.gross,
        vat=ubl.totals.vat,
        period=period,
    )
    found = candidates(
        cat,
        fiscal_class,
        view.our_role,
        view.is_storno,
        axes_for(cat, d, period),
        ubl.issue_date,
        allow_draft=d.is_test_firm,
    )
    return {
        "extracted": True,
        "candidates": found,
        "_doc": doc.model_dump(),
        "_doc_class": doc_class,
        "_fiscal_class": fiscal_class,
    }


def _bind(cat, d: Dossier, issue, facts, detail) -> dict:
    art = cat.get("Articol", detail["articol"])
    doc_class = facts.get("_doc_class")
    if not doc_class:
        raise StepError("bind needs the document's class, written when it was read")
    mouths = [m for m in art.mouths if cat.get("Mouth", m).doc_class == doc_class]
    d.set_status(facts["job_id"], "bound")
    return {
        "bound_articol": art.id,
        "status": "bound",
        "policy": art.gate.policy,
        "first_n": art.gate.first_n,
        "mouths_for_class": len(mouths),
        "packaged_count": _packaged(d, art.id),
    }


def _packaged(d: Dossier, articol: str) -> int:
    """Jobs of this articol and client already past the package (the first_n gate)."""
    done = ("packaged", "wait_validare", "acked")
    rows = d.db.execute("SELECT job_id, status FROM jobs").fetchall()
    return sum(
        1
        for jid, st in rows
        if st in done and d.facts(_job_issue(jid)).get("bound_articol") == articol
    )


def _months_of(doc: Doc) -> list[str]:
    first, last = sorted([doc.date[:7], doc.period])
    out, (y, m) = [], map(int, first.split("-"))
    while f"{y:04d}-{m:02d}" <= last:
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _pre_check(cat, d: Dossier, issue, facts, detail) -> dict:
    doc = Doc.model_validate(facts["_doc"])
    w, _ = books(d, _months_of(doc))
    r = pre_check(pick_profile(cat, "pre", facts["_fiscal_class"]), doc, w)
    d.put_verdict(facts["job_id"], "pre", r.snapshot_id, r.verdict, r.model_dump())
    d.set_status(facts["job_id"], "reconcile_pre")
    out = {"pre_verdict": r.verdict, "status": "reconcile_pre", "_pre": r.model_dump()}
    if r.verdict in UNDECIDED_PRE:
        recon = _month_issue("recon", d, doc.period)
        d.add_facts(recon, f"pre:{facts['job_id']}:{r.snapshot_id}", "kit", {"checked": False})
        out["_spawn"] = [[recon, None]]
    return out


def _package(cat, d, issue, facts, detail) -> dict:
    raise StepError("the package is WP-10's: the SAGA XML renderer waits on R4")


def _reopen(cat, d: Dossier, issue, facts, detail) -> dict:
    d.set_status(facts["job_id"], "reopened")
    return {
        "status": "reopened",
        "packaged": False,
        "imported": False,
        "validare": None,
        "intent_ok": None,
    }


def _intent_check(cat, d: Dossier, issue, facts, detail) -> dict:
    """SAGA's posted document against the document as read: side, gross, partner."""
    key, doc = facts.get("_saga_doc_key"), Doc.model_validate(facts["_doc"])
    w, _ = books(d, [doc.date[:7]])
    posted = next((s for s in w.docs if s.saga_key == key), None)
    if posted is None:
        raise StepError(f"no books export shows {key} yet: upload SAGA's export of {doc.date[:7]}")
    same = (posted.doc_class, posted.gross, posted.partner_cui) == (
        doc.doc_class,
        doc.gross,
        doc.partner_cui,
    )
    if same:
        d.set_status(facts["job_id"], "acked")
    return {"intent_ok": same, "_saga_key": key, "status": "acked" if same else facts["status"]}


# ----- Reconcile -----


def _jobs_of(d: Dossier, period: str) -> list[tuple[str, dict]]:
    return [(j.job_id, d.facts(_job_issue(j.job_id))) for j in d.jobs(period)]


def _post_default(cat: Catalog, d: Dossier, period: str) -> str:
    """The POST profile of the period's close kind (its ``recon_profile`` in the catalog): the
    default for a fiscal class without a POST profile of its own. No close kind refuses (P10)."""
    kind = close_kind(cat, axes_for(cat, d, period))
    if kind is None:
        raise StepError(f"no close kind fits the CO.DiT of {period} (tva / exig): no POST profile")
    return cat.get("CloseKind", kind).recon_profile


def _recheck_window(cat, d: Dossier, issue, facts, detail) -> dict:
    """Every Job stopped at PRE, against the books as they are now; acked Jobs through POST."""
    period = issue.split(":")[2]
    to_review, ambiguous, missing, how = [], [], set(), []
    post_default: str | None = None
    for job_id, jf in _jobs_of(d, period):
        if "_doc" not in jf:
            continue
        doc = Doc.model_validate(jf["_doc"])
        if jf.get("pre_verdict") in UNDECIDED_PRE:
            w, _ = books(d, _months_of(doc))
            r = pre_check(pick_profile(cat, "pre", jf["_fiscal_class"]), doc, w)
            d.put_verdict(job_id, "pre", r.snapshot_id, r.verdict, r.model_dump())
            d.add_facts(
                _job_issue(job_id), f"recheck:{r.snapshot_id}", "kit", {"_rechecked": r.verdict}
            )
            if r.verdict in ("already_posted", "absent"):
                to_review.append(job_id)
            elif r.verdict == "ambiguous":
                ambiguous.append(job_id)
            else:
                missing |= set(r.missing)
        elif jf.get("status") == "acked" and jf.get("bound_articol"):
            art = cat.get("Articol", jf["bound_articol"])
            w, _ = books(d, [doc.date[:7]])
            post_default = post_default or _post_default(cat, d, period)
            p = post_check(
                pick_profile(cat, "post", jf["_fiscal_class"], post_default),
                art.reconcile.expect_accounts,
                doc,
                w,
            )
            if p.verdict == "how_mismatch":
                how.append(job_id)
            elif p.verdict == "need_export":
                missing |= set(p.missing)
    return {
        "checked": True,
        "to_review": to_review,
        "ambiguous": ambiguous,
        "missing_months": sorted(missing),
        "how_mismatch": how,
        "contested": [],
        "_ask:recon_ambiguous": {},
        "_ask:need_rj_export": _exports_question(d, missing),
    }


def _exports_question(d: Dossier, missing: set) -> dict:
    return {
        "months": sorted(missing),
        "exports": {e["export_id"]: e["months"] for e in d.exports()},
    }


def _pre_answer(verdict: str, d: Dossier, job_id: str, key: str) -> None:
    """A person's PRE verdict back to its Job (stored once per answer)."""
    status = "already_in_sink" if verdict == "already_posted" else "reconcile_pre"
    if verdict == "already_posted":
        d.set_status(job_id, "already_in_sink")
    d.add_facts(_job_issue(job_id), key, "answer", {"pre_verdict": verdict, "status": status})


# ----- Month close -----


def recon_open(d: Dossier, period: str) -> bool:
    """The month's Reconcile still has a question or an unchecked window."""
    f = d.facts(_month_issue("recon", d, period))
    if not f:
        return False
    fields = {k: v for k, v in f.items() if k in ReconFacts.model_fields}
    return route_recon(ReconFacts.model_validate(fields)).kind != "done"


def _items(cat: Catalog, d: Dossier, period: str) -> list[ExpectedItem]:
    axes = axes_for(cat, d, period)
    unread = [jid for jid, jf in _jobs_of(d, period) if "_doc" not in jf]
    if unread:
        raise StepError(f"{len(unread)} Job(s) of {period} are not read yet: {unread[:3]}")
    items = []
    for job_id, jf in _jobs_of(d, period):
        doc = Doc.model_validate(jf["_doc"])
        vat_open = None
        if axes.get("exig") == "tva_la_incasare" and doc.vat and Decimal(doc.vat):
            vat = Decimal(doc.vat)
            vat_open = f"{(-vat if doc.doc_class.endswith('intrare') else vat):.2f}"
        items.append(
            ExpectedItem(
                job_id=job_id,
                status=d.job(job_id).status,
                doc_class=doc.doc_class,
                number=doc.number,
                date=doc.date,
                partner_cui=doc.partner_cui,
                gross=doc.gross,
                vat=doc.vat,
                saga_key=jf.get("_saga_key"),
                vat_open=vat_open,
            )
        )
    return items


def _lock(cat, d: Dossier, issue, facts, detail) -> dict:
    period = issue.split(":")[2]
    items = _items(cat, d, period)
    ok = d.lock_close(period, expected_set_hash(items))
    return {"locked": True, "_lock_mismatch": not ok, "_items": [i.model_dump() for i in items]}


def _period_diff(cat, d: Dossier, issue, facts, detail) -> dict:
    period = issue.split(":")[2]
    axes = axes_for(cat, d, period)
    items = [ExpectedItem.model_validate(i) for i in facts.get("_items", [])]
    w, balances = books(d, [period])
    rules = [ExplainedRule.model_validate(r) for r in facts.get("_rules", [])]
    open_pre = [jid for jid, jf in _jobs_of(d, period) if jf.get("pre_verdict") in UNDECIDED_PRE]
    diff = period_diff(
        cat,
        period,
        items,
        w,
        axes=axes,
        rules=rules,
        balances=balances or None,
        open_pre=open_pre,
        lock_mismatch=bool(facts.get("_lock_mismatch")),
    )
    unexplained = [b.saga_key for b in diff.buckets if b.bucket == "unexplained"]
    return {
        "diffed": True,
        "_diff": {
            "material": diff.material,
            "blockers": diff.blockers,
            "outbound_holes": diff.outbound_holes,
            "unexplained": unexplained,
            "snapshot_id": diff.snapshot_id,
        },
        "_ask:v2_close": {
            "material": diff.material,
            "blockers": diff.blockers,
            "rules": [r.rule_id for r in rules],
        },
    }


def _release_lock(cat, d: Dossier, issue, facts, detail) -> dict:
    """reopen: the month is unlocked and the close runs again as its next round (``_round``).

    The round makes each round's facts, and so its steps' keys and its questions (``round`` in
    the question, ``kit.dispatch._question``), its own: a round that reaches the same state as
    the one before is never a replay of it (P9)."""
    d.release_close(issue.split(":")[2])
    return {
        "locked": False,
        "diffed": False,
        "suggested": False,
        "v2": None,
        "_round": facts.get("_round", 0) + 1,
    }


# ----- The calendar (WP-21) -----


def _obligations(cat, d: Dossier, issue, facts, detail) -> dict:
    """The core's calendar for the client-month, on the period's CO.DiT as stored.

    The CO.DiT is not translated: an axis or value outside the core catalog's vocabulary refuses
    (``calendar.check_axes``), so no filing is dropped silently (P10).
    """
    period = issue.split(":")[2]
    axes = d.codit(period)
    if axes is None:
        raise StepError(f"no CO.DiT for {period}: set it first (kit dossier set-codit)")
    return calendar.month_calendar(calendar.core_catalog(), axes, period, calendar.today())


EXECUTORS: dict[tuple[str, str], Executor] = {
    ("batch", "emit"): _emit,
    ("batch", "emit_children"): _emit_children,
    ("job", "extract_xml"): _extract_xml,
    ("job", "bind"): _bind,
    ("job", "pre_check"): _pre_check,
    ("job", "package"): _package,
    ("job", "reopen"): _reopen,
    ("job", "intent_check"): _intent_check,
    ("recon", "recheck_window"): _recheck_window,
    ("close", "lock"): _lock,
    ("close", "period_diff"): _period_diff,
    ("close", "release_lock"): _release_lock,
    ("calendar", "obligations"): _obligations,
}


def derive(d: Dossier, issue: str, facts: dict) -> dict:
    """Facts that follow from other issues, recomputed on every wake (never stored)."""
    if issue.startswith("close:"):
        return {**facts, "recon_open": recon_open(d, issue.split(":")[2])}
    if issue.startswith("calendar:"):
        return {**facts, "today": calendar.today().isoformat()}
    return facts


# ----- an accepted answer's effect -----

Apply = Callable[[Catalog, Dossier, str, dict, dict, dict], dict]


def _drop(name: str):
    def apply(cat, d, issue, f, q, a):
        return {name: [x for x in f.get(name, []) if x != q.get("job_id")]}

    return apply


def _recon_verdict(name: str):
    def apply(cat, d, issue, f, q, a):
        verdict = "already_posted" if a["action"] == "already_posted" else "absent"
        _pre_answer(verdict, d, q["job_id"], f"answer:{name}:{question_hash(q)}")
        return {
            name: [x for x in f.get(name, []) if x != q.get("job_id")],
            "_wake": [_job_issue(q["job_id"])],
        }

    return apply


def _approve(cat, d: Dossier, issue, f, q, a) -> dict:
    if a["decision"] == "reject":
        return {"approval": "reject"}
    d.set_status(f["job_id"], "approved")
    return {"approval": a["decision"], "status": "approved", "_edit": a.get("edit")}


def _redecide(cat, d, issue, f, q, a) -> dict:
    pack = Pack.model_validate(f["_pack"])
    if "source_doc_id" in a:
        pack = pack.model_copy(update={"source_doc_id": a["source_doc_id"]})
    if "cu_cui" in a:
        pack = pack.model_copy(update={"bon_our_cui_on_doc": bool(a["cu_cui"])})
    return {"_pack": pack.model_dump(), **_decision(cat, pack)}


ALLOWED_EDIT, ALLOWED_SEED = {"exig"}, {"impozit", "tva"}


def _next(period: str) -> str:
    y, m = map(int, period.split("-"))
    return f"{y + (m == 12):04d}-{1 if m == 12 else m + 1:02d}"


def _v4(cat, d: Dossier, issue, f, q, a) -> dict:
    period = issue.split(":")[2]
    axes = axes_for(cat, d, period)
    if a.get("accept"):
        edit, seed = a.get("edit") or {}, a.get("seed_next") or {}
        if set(edit) - ALLOWED_EDIT or set(seed) - ALLOWED_SEED:
            raise StepError(
                f"v4_codit may edit {sorted(ALLOWED_EDIT)} and seed {sorted(ALLOWED_SEED)} only"
            )
        nxt = _next(period)
        if d.codit(nxt) is None:  # never overwrite an existing next CO.DiT
            d.set_codit(nxt, {**axes, **edit, **seed})
    filings = [fid for fid in cat.ids("Filing") if _fits(axes, cat.get("Filing", fid))]
    for fid in filings:
        d.open_filing(period, fid)
    return {"v4_done": True, "filings_open": filings}


def _fits(axes: dict, row) -> bool:
    if any(axes.get(k) not in vs for k, vs in row.require.items()):
        return False
    return not any(axes.get(k) in vs for k, vs in row.forbid.items())


def _receipt(cat, d: Dossier, issue, f, q, a) -> dict:
    d.file_filing(issue.split(":")[2], a["filing_id"], a["receipt_key"], a["submitted_by"])
    return {"filings_open": [x for x in f.get("filings_open", []) if x != a["filing_id"]]}


APPLY: dict[str, Apply] = {
    "define_class": _redecide,
    "bon_cui_unclear": _redecide,
    "decont_split": lambda c, d, i, f, q, a: {
        "split_answered": True,
        "question": None,
        "_parts": a["parts"],
    },
    "define_articol": lambda c, d, i, f, q, a: {"candidates": [a["articol_id"]]},
    "v3_approve": _approve,
    "wait_validare": lambda c, d, i, f, q, a: {
        "validare": "validated" if a["validated"] else "not_validated",
        "_saga_doc_key": a.get("saga_doc_key"),
    },
    "need_rj_export": lambda c, d, i, f, q, a: {"checked": False, "missing_months": []},
    "recon_review_contest": _recon_verdict("contested"),
    "recon_ambiguous": _recon_verdict("ambiguous"),
    "recon_how_mismatch": _drop("how_mismatch"),
    "v2_close": lambda c, d, i, f, q, a: {"v2": a["action"]},
    "v4_codit": _v4,
    "filing_receipt": _receipt,
}


# ----- what a question's check needs to know, read from the dossier when it is asked -----


def _period_of(issue: str, facts: dict) -> str:
    return facts.get("_period") or issue.split(":")[2]


# Context read again when the answer is checked: the books may have arrived since it was asked.
LIVE_CONTEXT = ("wait_validare", "need_rj_export")

CONTEXT: dict[str, Callable[[Dossier, str, dict], dict]] = {
    "wait_validare": lambda d, issue, f: {
        "validated_keys": sorted(
            x.saga_key for x in books(d, [_period_of(issue, f)])[0].docs if x.validated
        )
    },
    "need_rj_export": lambda d, issue, f: _exports_question(d, set(f.get("missing_months", []))),
    "filing_receipt": lambda d, issue, f: {"period": _period_of(issue, f)},
    "define_articol": lambda d, issue, f: {"candidates": list(f.get("candidates", []))},
    "decont_split": lambda d, issue, f: {"pack": f.get("_pack"), "proposed": f.get("_proposed")},
}
