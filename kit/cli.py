"""``kit``: the gate kit's command line, run by the Dispatcher and by hank rigs.

Built so far: ``kit cui``. The other commands are named in ``ARCHITECTURE.md`` and refuse until
their work package is done (``BUILD.md``): a command that is not built never pretends to work.
"""

from __future__ import annotations

import argparse
import sys

from kit import __version__
from kit.types import cui_is_valid, normalize_cui

PLANNED = {
    "route": "WP-13: the next step of an issue, from the dossier's facts",
    "answer": "WP-12: validate and record an answer to a question issue",
    "verify": "WP-14: check a hank's output file before it becomes a fact",
    "emit": "WP-06: the emit gates and the Job of a source document",
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="kit", description=__doc__.split("\n")[0])
    ap.add_argument("--version", action="version", version=f"kit {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("cui", help="check a CUI's check digit")
    c.add_argument("value")
    for name, why in PLANNED.items():
        sub.add_parser(name, help=f"not built yet ({why})")
    args = ap.parse_args(argv)

    if args.cmd == "cui":
        ok = cui_is_valid(args.value)
        print(f"{normalize_cui(args.value)} {'valid' if ok else 'invalid'}")
        return 0 if ok else 1
    print(f"kit {args.cmd}: not built yet ({PLANNED[args.cmd]})", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
