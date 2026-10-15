"""``kit hank-run``: a model step from the dossier and back (WP-18, ARCHITECTURE §6, P8).

The Dispatcher hands a hank step to its role agent as a child issue ``hank:{name}:{issue}``,
which blocks the work issue. The role agent's process adapter runs ``kit hank-run``:

1. **prepare** the run's input from the work issue's facts (``input.json``, and the document for
   a read), written for one client into ``runs/`` of its dossier (P13);
2. if every role of the hank already has a verified answer for this input and card (the cache
   key: role, input hash, card hash), reuse it and run nothing (P9);
3. else **render** the hank with the catalog's pins (refused while a role is unpinned, D3) and
   **run** the runtime's one command line (``kit.hanks.command``), with its cost and time limits;
4. **verify** every role's output file (``kit verify``); a passing answer is stored;
5. write the **facts** the work issue's route reads: what passed, or the fail-closed reading of
   what did not (a doubtful verdict, a contest, a read not confirmed, no suggestion).

Nothing a model wrote reaches a fact without ``verify``; the run never touches the dossier store
except through the kit (P7).
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from kit.bind import candidates
from kit.catalog import Catalog
from kit.hanks import (
    DOUBTFUL,
    Verified,
    card_hash,
    command,
    input_hash,
    load_hank,
    render,
    roles_for,
    verify,
)
from kit.recon import Doc
from kit.steps import StepError, _pre_answer, axes_for, books
from kit.store import Dossier
from kit.types import normalize_cui

Runner = Callable[[list[str], Path], int]
AGENT_OF_SYSTEM = {"reader": "agent:reader", "one": "agent:classifier", "two": "agent:classifier"}


@dataclass
class HankRun:
    hank: str
    issue: str
    ran: bool
    verified: dict[str, Verified] = field(default_factory=dict)
    fields: dict = field(default_factory=dict)


def agent_for(cat: Catalog, hank: str) -> str:
    """The Paperclip agent that runs a hank: the Reader's, or the Classifier's (One and Two)."""
    systems = {r.system for r in roles_for(cat, hank).values()}
    agents = {AGENT_OF_SYSTEM[s] for s in systems}
    if len(agents) != 1:
        raise StepError(f"{hank} has roles of two agents: {sorted(agents)}")
    return agents.pop()


def subprocess_runner(argv: list[str], cwd: Path) -> int:
    """The runtime, as the process it is (its own limits bound it; this is the outer stop)."""
    return subprocess.run(argv, cwd=cwd, timeout=3600, check=False).returncode


# ----- inputs -----


def _doc_facts(f: dict) -> dict:
    doc = f.get("_doc") or {}
    return {f"document.{k}": v for k, v in doc.items() if v is not None}


def prepare(cat: Catalog, d: Dossier, hank: str, issue: str, f: dict) -> tuple[dict, dict]:
    """The run's ``input.json`` and the files that go next to it (name -> bytes)."""
    if hank == "judge-document":
        art = cat.get("Articol", f["bound_articol"])
        period = f["_period"]
        return {
            "job_id": f["job_id"],
            "articol": art.id,
            "document": f["_doc"],
            "expected_accounts": list(art.reconcile.expect_accounts),
            "client": {"cui": d.client_cui, "axes": axes_for(cat, d, period)},
            "facts": {**_doc_facts(f), "articol": art.id, "pre_verdict": f.get("pre_verdict")},
        }, {}
    if hank == "read-document":
        data, meta = d.source(f["_source_hash"])
        fiscal = cat.get("SourceDoc", f["_source_doc_id"]).fiscal_class
        name = Path(meta["name"]).name or "document"
        return {
            "client_cui": d.client_cui,
            "expected": "statement" if fiscal == "extras" else "invoice",
            "files": [name],
        }, {name: data}
    if hank == "review-match":
        job_id = (f.get("to_review") or [None])[0]
        if job_id is None:
            raise StepError("nothing to review")
        jf = d.facts(f"job:{job_id}")
        doc = Doc.model_validate(jf["_doc"])
        w, _ = books(d, [doc.date[:7]])
        return {
            "job_id": job_id,
            "pre": {"verdict": jf.get("_rechecked"), "first": (jf.get("_pre") or {}).get("reason")},
            "document": jf["_doc"],
            "books": [x.model_dump() for x in w.docs],
        }, {}
    if hank == "close-suggest":
        period = issue.split(":")[2]
        diff = f.get("_diff") or {}
        w, _ = books(d, [period])
        unexplained = []
        for x in w.docs:
            if x.saga_key in diff.get("unexplained", []):
                accounts = sorted({ln.account for ln in w.lines if ln.saga_key == x.saga_key})
                unexplained.append({**x.model_dump(), "accounts": accounts})
        return {
            "period": period,
            "material": bool(diff.get("material", True)),
            "blockers": list(diff.get("blockers", [])),
            "controls": [],
            "unexplained": unexplained,
            "facts": {
                "material": bool(diff.get("material", True)),
                "blockers.count": len(diff.get("blockers", [])),
                "unexplained.count": len(unexplained),
            },
        }, {}
    raise StepError(f"{hank}: no input is prepared for it on this path")


# ----- results -----


def _body(v: Verified | None) -> dict | None:
    return v.body if v is not None and v.ok else None


def _read_result(cat: Catalog, d: Dossier, f: dict, vs: dict[str, Verified]) -> dict:
    out = {"read_runs": f.get("read_runs", 0) + 1}
    body = _body(next(iter(vs.values()), None))
    if body is None:
        return {**out, "read_confirmed": False}
    if body["doc_type"] == "statement":  # the statement-line path is not built yet
        return {
            **out,
            "read_confirmed": True,
            "extracted": True,
            "candidates": [],
            "_statement": body["statement"],
        }
    inv = body["invoice"]
    client = d.client_cui
    inbound = normalize_cui(inv["buyer_cui"]) == client
    role = "inbound" if inbound else "outbound"
    doc_class = "intrare" if inbound else "iesire"
    partner = normalize_cui(inv["seller_cui"] if inbound else inv["buyer_cui"])
    doc = Doc(
        doc_class=doc_class,
        number=inv["number"],
        date=inv["date"],
        partner_cui=partner,
        gross=inv["gross"],
        vat=inv["vat"],
        period=f["_period"],
    )
    fiscal = cat.get("SourceDoc", f["_source_doc_id"]).fiscal_class
    found = candidates(
        cat,
        fiscal,
        role,
        False,
        axes_for(cat, d, f["_period"]),
        inv["date"],
        allow_draft=d.is_test_firm,
    )
    return {
        **out,
        "read_confirmed": True,
        "extracted": True,
        "candidates": found,
        "_doc": doc.model_dump(),
        "_doc_class": doc_class,
        "_fiscal_class": fiscal,
    }


def results(
    cat: Catalog, d: Dossier, hank: str, issue: str, f: dict, inp: dict, vs: dict[str, Verified]
) -> dict:
    """The work issue's facts from the verified files; what failed reads the cautious way."""
    if hank == "judge-document":
        verdict = _body(vs.get("judge")) or dict(DOUBTFUL)
        out = {"judged": True, "verdict": verdict}
        explain = _body(vs.get("explain"))
        if explain:
            out["_ask:v3_approve"] = {**f.get("_ask:v3_approve", {}), "explanation": explain}
        return out
    if hank == "read-document":
        return _read_result(cat, d, f, vs)
    if hank == "review-match":
        job_id, review = inp["job_id"], _body(vs.get("review"))
        rest = [j for j in f.get("to_review", []) if j != job_id]
        if review and review["decision"] == "confirm":
            jf = d.facts(f"job:{job_id}")
            _pre_answer(jf["_rechecked"], d, job_id, f"review:{input_hash(inp)}")
            return {"to_review": rest, "_wake": [f"job:{job_id}"]}
        return {"to_review": rest, "contested": [*f.get("contested", []), job_id]}
    if hank == "close-suggest":
        ask = dict(f.get("_ask:v2_close", {}))
        suggestion = _body(vs.get("suggest"))
        if suggestion:
            ask["suggestion"] = suggestion
        explain = _body(vs.get("explain"))
        if explain:
            ask["explanation"] = explain
        out = {"suggested": True, "_ask:v2_close": ask}
        rules = _body(vs.get("draft_rule"))
        if rules:
            out["_drafted_rules"] = rules["rules"]
        return out
    raise StepError(f"{hank}: no result is read on this path")


# ----- the run -----


def run_hank(
    cat: Catalog,
    repo: Path,
    d: Dossier,
    hank: str,
    issue: str,
    runner: Runner = subprocess_runner,
    tier: str = "everyday",
) -> HankRun:
    f = d.facts(issue)
    inp, files = prepare(cat, d, hank, issue, f)
    ihash = input_hash(inp)
    roles = roles_for(cat, hank, tier)
    doc = load_hank(repo, hank)
    keys = {c: (r.id, ihash, card_hash(repo, r, doc)) for c, r in roles.items()}
    cached = {c: d.model_answer(*k) for c, k in keys.items()}
    run = HankRun(hank, issue, ran=False)
    if all(v is not None for v in cached.values()):
        run.verified = {c: Verified(roles[c].id, True, cached[c]) for c in roles}
    else:
        base = d.folder / "runs" / issue.replace(":", "_") / f"{hank}-{ihash[:12]}"
        rendered = render(cat, repo, hank, base / "hank", tier)  # HankRefused while unpinned
        data, out = base / "input", base / "out"
        data.mkdir(parents=True)
        out.mkdir()
        (data / "input.json").write_text(json.dumps(inp, ensure_ascii=False, indent=2))
        for name, blob in files.items():
            (data / name).write_bytes(blob)
        code = runner(command(rendered, data, out), base)
        run.ran = True
        for c, role in roles.items():
            found = sorted(out.rglob(role.output)) if code == 0 else []
            body = found[0].read_bytes() if len(found) == 1 else None
            v = verify(cat, role.id, inp, body)
            if code != 0:
                v.problems.insert(0, f"the runtime exited {code}")
            if v.ok:
                d.put_model_answer(*keys[c], v.body)
            run.verified[c] = v
    run.fields = results(cat, d, hank, issue, f, inp, run.verified)
    return run
