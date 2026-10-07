"""``kit``: the gate kit's command line, run by the Dispatcher and by hank rigs.

Built so far: ``kit cui``, ``kit catalog``, ``kit emit``, ``kit read``. The other commands are
named in ``ARCHITECTURE.md`` and refuse until their work package is done (``BUILD.md``): a
command that is not built never pretends to work.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from kit import __version__
from kit.catalog import CatalogError, load_catalog
from kit.sorting import Pack, SplitError, decide, split
from kit.store import StoreError, open_dossier
from kit.types import cui_is_valid, normalize_cui
from kit.ubl import UblError, for_client, parse_ubl, read_spv_zip

PLANNED = {
    "route": "WP-13: the next step of an issue, from the dossier's facts",
    "answer": "WP-12: validate and record an answer to a question issue",
    "verify": "WP-14: check a hank's output file before it becomes a fact",
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


if __name__ == "__main__":
    raise SystemExit(main())
