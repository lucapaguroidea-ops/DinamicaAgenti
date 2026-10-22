"""The calendar in the firm (WP-21): a client's month items with their due dates, from the
pinned core (PoartaContabila's ``core.obligations``, ``core.register_freshness``).

A ``calendar:{cui}:{period}`` issue is opened per client and month (the ``month_calendar``
routine of ``paperclip/company.yaml``); the Dispatcher routes it like any other issue
(``kit/route.py``, ``route_calendar``). Its one kit step, ``obligations``, asks the core for every
filing the period's CO.DiT owes and records the answer as the issue's facts:

- **items**: each dated filing with its due date, the register's day before any move, its
  certainty, its source and the lock set it was computed under (``lock``, ``lock_key``);
- **refused**: each filing the core could not date, with the core's reason;
- **later**: each quarterly filing whose quarter does not end in the month, with its reason;
- **freshness**: why the register pin may not date anything on the day asked, or ``None``.

Nothing is dropped and nothing is guessed: no term, date, non-working day or freshness window
is written here; every one is the core catalog's. A refused item, or a register that is not
fresh, holds the issue for a person with the reasons (P10).

**The core's catalog.** The pinned package ships the core's code, not its catalog, so the
catalog directory is configured with the core's own variable, ``POARTA_CATALOG_DIR`` (a
PoartaContabila checkout's ``catalog/``, D4). It must be a git checkout at exactly the commit
``pyproject.toml`` pins; anything else refuses, so a calendar is never read from another
commit's terms.

**The day.** The core reads no clock. ``today()`` is the UTC date; the step records the day it
asked on (``computed_on``), and a held calendar is asked again on a later day, so a refusal
clears once the owner's pins allow a date. A fully dated calendar is never recomputed: its
dates stay with the lock set they were computed under.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, date, datetime
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path

from poarta_contabila import core

CATALOG_ENV = "POARTA_CATALOG_DIR"


class CalendarUnavailable(ValueError):
    """The core's calendar cannot be asked; the reason goes to a person."""


def today() -> date:
    return datetime.now(UTC).date()


def pinned_commit() -> str:
    """The commit of PoartaContabila that ``pyproject.toml`` pins, as installed."""
    try:
        raw = distribution("poarta-contabila").read_text("direct_url.json")
    except PackageNotFoundError as exc:
        raise CalendarUnavailable("the shared core is not installed") from exc
    commit = ((json.loads(raw or "{}").get("vcs_info") or {}).get("commit_id")) or ""
    if len(commit) != 40:
        raise CalendarUnavailable("the installed core names no pinned commit")
    return commit


def _head(path: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def core_catalog(env: dict[str, str] | None = None) -> core.Catalog:
    """The core's catalog at the pinned commit, from ``POARTA_CATALOG_DIR``; else refused."""
    env = dict(os.environ if env is None else env)
    commit = pinned_commit()
    where = env.get(CATALOG_ENV)
    if not where:
        raise CalendarUnavailable(
            f"the pinned core ships no catalog: set {CATALOG_ENV} to a PoartaContabila"
            f" checkout's catalog/ at {commit[:7]} (D4)"
        )
    path = Path(where)
    head = _head(path)
    if head != commit:
        raise CalendarUnavailable(
            f"{CATALOG_ENV} is not the pinned core's catalog: its checkout is at"
            f" {(head or 'no git commit')[:7]}, the pin is {commit[:7]}"
        )
    try:
        return core.load_catalog(path)
    except core.CatalogError as exc:
        raise CalendarUnavailable(f"the core's catalog does not load: {exc}") from exc


def month_calendar(cat: core.Catalog, axes: dict[str, str], period: str, as_of: date) -> dict:
    """The facts of one client-month's calendar: the core's answer, every filing kept."""
    result = core.obligations(cat, axes, period, None, as_of=as_of)
    items = [
        {
            "filing_id": o.filing_id,
            "form": o.form,
            "filing_period": o.filing_period,
            "due": o.due,
            "unshifted": o.unshifted,
            "conditional": o.conditional,
            "certainty": o.certainty,
            "term_id": o.term_id,
            "source": o.source,
            "lock": o.lock.as_dict(),
            "lock_key": o.lock.key,
        }
        for o in result.items
    ]
    return {
        "computed_on": as_of.isoformat(),
        "freshness": core.register_freshness(cat, as_of),
        "items": items,
        "refused": [dict(r) for r in result.refused],
        "later": [dict(r) for r in result.later],
    }
