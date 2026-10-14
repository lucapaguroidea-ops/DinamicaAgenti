"""``kit``: the gate kit's command line, run by the Dispatcher and by hank rigs.

Built so far: ``kit cui``, ``kit catalog``, ``kit emit``, ``kit read``, ``kit answer``,
``kit route``, ``kit scenario``, ``kit hank``, ``kit verify``. A command named in
``ARCHITECTURE.md`` and not built yet refuses until its work package is done (``BUILD.md``): a
command that is not built never pretends to work.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from kit import __version__
from kit.catalog import CatalogError, load_catalog
from kit.hanks import HankError, HankRefused, card_hash, check_hank, input_hash, render, verify
from kit.hanks import command as hank_command
from kit.questions import AnswerError, answer_question
from kit.route import route
from kit.scenario import DEFECTS, ScenarioError, run_month
from kit.sorting import Pack, SplitError, decide, split
from kit.store import StoreError, open_dossier
from kit.synthetic import FIRMS
from kit.types import cui_is_valid, normalize_cui
from kit.ubl import UblError, for_client, parse_ubl, read_spv_zip

PLANNED = {
    "prepare": "WP-15: write a hank run's input.json from the dossier, for the Dispatcher",
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="kit", description=__doc__.split("\n")[0])
    ap.add_argument("--version", action="version", version=f"kit {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("cui", help="check a CUI's check digit")
    c.add_argument("value")
    k = sub.add_parser("catalog", help="load and check the catalog; print rows per catalog")
    k.add_argument("root", nargs="?", type=Path, default=Path("catalog"))
    e = sub.add_parser("emit", help="Sorting: the emit gates of one file (a pack as JSON)")
    e.add_argument("pack", type=Path, help="the pack, a JSON file")
    e.add_argument("--split", type=Path, help="a decont_split answer (JSON): print the children")
    e.add_argument("--catalog", type=Path, default=Path("catalog"))
    e.add_argument("--dossiers", type=Path, help="insert the Job into the client's dossier here")
    r = sub.add_parser("read", help="read an e-invoice: UBL XML or the SPV zip (XML first)")
    r.add_argument("file", type=Path)
    r.add_argument("--client", help="the client's CUI: says inbound or outbound")
    a = sub.add_parser("answer", help="validate and record an answer to a question issue")
    a.add_argument("--dossiers", type=Path, required=True)
    a.add_argument("--cui", required=True, help="the client's CUI")
    a.add_argument("--issue", required=True, help="the work issue, e.g. job:j_…")
    a.add_argument("--kind", required=True, help="the question kind")
    a.add_argument("--question", type=Path, required=True, help="the question asked (JSON)")
    a.add_argument("--answer", type=Path, required=True, help="the answer given (JSON)")
    a.add_argument("--operator", required=True, help="who answered")
    a.add_argument("--actor", choices=["person", "saga_agent"], default="person")
    a.add_argument("--catalog", type=Path, default=Path("catalog"))
    ro = sub.add_parser("route", help="the next step of an issue, from its facts (JSON)")
    ro.add_argument("--procedure", required=True, choices=["batch", "job", "recon", "close"])
    ro.add_argument("--facts", type=Path, required=True, help="the issue's facts (JSON)")
    sc = sub.add_parser("scenario", help="an invented firm's month, end to end (synthetic)")
    sc.add_argument("firm", help="one of: " + ", ".join(FIRMS))
    sc.add_argument("--period", required=True, help="YYYY-MM")
    sc.add_argument("--dossiers", type=Path, required=True)
    sc.add_argument("--defect", action="append", default=[], choices=DEFECTS)
    sc.add_argument("--eu-service", action="store_true", help="add a service bought from the EU")
    sc.add_argument("--seed", type=int, default=7)
    sc.add_argument("--catalog", type=Path, default=Path("catalog"))
    h = sub.add_parser("hank", help="check the hanks, or render a run with the catalog's pins")
    h.add_argument("action", choices=["check", "render"])
    h.add_argument("name", nargs="?", help="the hank (render)")
    h.add_argument("--run", type=Path, help="the run directory to write (render)")
    h.add_argument("--tier", choices=["everyday", "strong"], default="everyday")
    h.add_argument("--data", type=Path, help="with --out: print the runtime's command line")
    h.add_argument("--out", type=Path)
    h.add_argument("--root", type=Path, default=Path("."), help="the repository (hanks/)")
    h.add_argument("--catalog", type=Path, default=Path("catalog"))
    v = sub.add_parser("verify", help="check a codon's output file before it becomes a fact")
    v.add_argument("--role", required=True, help="the model role (catalog row)")
    v.add_argument("--input", type=Path, required=True, help="the run's input.json")
    v.add_argument("--output", type=Path, required=True, help="the file the codon wrote")
    v.add_argument("--dossiers", type=Path, help="store a passing answer in the client's dossier")
    v.add_argument("--cui", help="the client's CUI (with --dossiers)")
    v.add_argument("--root", type=Path, default=Path("."), help="the repository (hanks/)")
    v.add_argument("--catalog", type=Path, default=Path("catalog"))
    for name, why in PLANNED.items():
        sub.add_parser(name, help=f"not built yet ({why})")
    args = ap.parse_args(argv)

    if args.cmd == "cui":
        ok = cui_is_valid(args.value)
        print(f"{normalize_cui(args.value)} {'valid' if ok else 'invalid'}")
        return 0 if ok else 1
    if args.cmd == "catalog":
        try:
            cat = load_catalog(args.root)
        except CatalogError as err:
            print("\n".join(err.problems), file=sys.stderr)
            return 1
        for kind, rows in cat.rows.items():
            print(f"{kind:<18} {len(rows)}")
        return 0
    if args.cmd == "emit":
        return _emit(args)
    if args.cmd == "read":
        return _read(args)
    if args.cmd == "answer":
        return _answer(args)
    if args.cmd == "hank":
        return _hank(args)
    if args.cmd == "verify":
        return _verify(args)
    if args.cmd == "scenario":
        return _scenario(args)
    if args.cmd == "route":
        try:
            step = route(args.procedure, json.loads(args.facts.read_text(encoding="utf-8")))
        except (ValueError, OSError) as err:
            print(f"kit route: {err}", file=sys.stderr)
            return 1
        print(step.model_dump_json())
        return 0
    print(f"kit {args.cmd}: not built yet ({PLANNED[args.cmd]})", file=sys.stderr)
    return 2


def _emit(args: argparse.Namespace) -> int:
    """Print the decision for a pack, or with --split the children and their decisions.
    Exit 0 when it ran; 1 when the input or the catalog is refused (the reason on stderr)."""
    try:
        cat = load_catalog(args.catalog)
        pack = Pack.model_validate(json.loads(args.pack.read_text(encoding="utf-8")))
        if args.split is None:
            decision = decide(cat, pack)
            out: object = decision.model_dump()
            if args.dossiers is not None and decision.emit:
                dossier = open_dossier(args.dossiers, pack.client_cui)
                job, created = dossier.insert_job(
                    pack.client_cui,
                    pack.source_hash,
                    decision.job_kind,
                    pack.source_doc_id,
                    pack.period,
                )
                out = {**decision.model_dump(), "job_id": job.job_id, "created": created}
        else:
            answer = json.loads(args.split.read_text(encoding="utf-8"))
            out = [
                {"pack": c.model_dump(), "decision": decide(cat, c).model_dump()}
                for c in split(cat, pack, answer)
            ]
    except (CatalogError, SplitError, StoreError, ValueError, OSError) as err:
        print(f"kit emit: {err}", file=sys.stderr)
        return 1
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


def _hank(args: argparse.Namespace) -> int:
    """check: exit 0 when every hank fits its role rows. render: exit 0 with the run written;
    3 when a role has no pinned model (the hank refuses, a person is asked); 1 on an error."""
    try:
        cat = load_catalog(args.catalog)
        if args.action == "check":
            hanks = sorted({cat.get("ModelRole", r).hank for r in cat.ids("ModelRole")})
            bad = {n: p for n in hanks if (p := check_hank(cat, args.root, n))}
            for n, problems in bad.items():
                print(f"{n}: " + "; ".join(problems), file=sys.stderr)
            if not bad:
                print("\n".join(f"{n} ok" for n in hanks))
            return 1 if bad else 0
        if not args.name or not args.run:
            print("kit hank render: name and --run are required", file=sys.stderr)
            return 1
        r = render(cat, args.root, args.name, args.run, args.tier)
        out: dict = {
            "hank": r.hank,
            "run_dir": str(r.run_dir),
            "models": r.models,
            "roles": r.roles,
            "card_hashes": r.card_hashes,
        }
        if args.data and args.out:
            out["command"] = hank_command(r, args.data, args.out)
    except HankRefused as refused:
        print(f"kit hank: refused: {refused}", file=sys.stderr)
        return 3
    except (CatalogError, HankError, KeyError, OSError) as err:
        print(f"kit hank: {err}", file=sys.stderr)
        return 1
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


def _verify(args: argparse.Namespace) -> int:
    """Print the check of a codon's file; exit 0 when it passes (and is stored with
    --dossiers), 1 when it is refused: the body printed is then the fallback fact, if any."""
    try:
        cat = load_catalog(args.catalog)
        inp = json.loads(args.input.read_text(encoding="utf-8"))
        output = args.output.read_bytes() if args.output.exists() else None
        result = verify(cat, args.role, inp, output)
        stored = False
        if result.ok and args.dossiers is not None:
            if not args.cui:
                raise ValueError("--dossiers needs --cui")
            role = cat.get("ModelRole", args.role)
            dossier = open_dossier(args.dossiers, args.cui)
            dossier.put_model_answer(
                role.id, input_hash(inp), card_hash(args.root, role), result.body
            )
            stored = True
    except (CatalogError, StoreError, KeyError, ValueError, OSError) as err:
        print(f"kit verify: {err}", file=sys.stderr)
        return 1
    out = {
        "role": result.role_id,
        "ok": result.ok,
        "body": result.body,
        "problems": result.problems,
        "stored": stored,
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0 if result.ok else 1


def _scenario(args: argparse.Namespace) -> int:
    """Print each document's walk and the month's close. Exit 0 when the walk went as designed
    (a material month held is as designed); 1 when it did not or the input is refused."""
    if args.firm not in FIRMS:
        print(f"kit scenario: unknown firm {args.firm!r}: one of {list(FIRMS)}", file=sys.stderr)
        return 1
    try:
        r = run_month(
            load_catalog(args.catalog),
            args.dossiers,
            args.firm,
            args.period,
            tuple(args.defect),
            args.seed,
            args.eu_service,
        )
    except (CatalogError, ScenarioError, StoreError, ValueError, OSError) as err:
        print(f"kit scenario: {err}", file=sys.stderr)
        return 1
    out = {
        "firm": r.firm,
        "period": r.period,
        "documents": [
            {"name": t.name, "job_id": t.job_id, "articol": t.articol, "steps": t.steps}
            for t in r.trails
        ],
        "close": {
            "material": r.diff.material,
            "blockers": r.diff.blockers,
            "v2": r.v2,
            "steps": r.close_steps,
        },
        "answers": r.answers,
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


def _read(args: argparse.Namespace) -> int:
    """Print the document read from a UBL XML or an SPV zip, and its side for --client."""
    try:
        data = args.file.read_bytes()
        name = args.file.name
        if data[:4] == b"PK\x03\x04":
            spv = read_spv_zip(data)
            data, name = spv.invoice, spv.invoice_name
        doc = parse_ubl(data)
        out: dict = {"file": name, "document": doc.model_dump()}
        if args.client:
            out["client"] = for_client(doc, args.client).model_dump()
    except (UblError, OSError) as err:
        print(f"kit read: {err}", file=sys.stderr)
        return 1
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


def _answer(args: argparse.Namespace) -> int:
    """Exit 0 accepted, 3 asked again (the reason on stdout), 1 refused."""
    try:
        cat = load_catalog(args.catalog)
        dossier = open_dossier(args.dossiers, args.cui)
        out = answer_question(
            cat,
            dossier,
            args.issue,
            args.kind,
            json.loads(args.question.read_text(encoding="utf-8")),
            json.loads(args.answer.read_text(encoding="utf-8")),
            operator=args.operator,
            actor=args.actor,
        )
    except (CatalogError, AnswerError, StoreError, ValueError, OSError) as err:
        print(f"kit answer: {err}", file=sys.stderr)
        return 1
    print(
        json.dumps({"status": out.status, "error": out.error, "question_hash": out.question_hash})
    )
    return 0 if out.status == "accepted" else 3


if __name__ == "__main__":
    raise SystemExit(main())
