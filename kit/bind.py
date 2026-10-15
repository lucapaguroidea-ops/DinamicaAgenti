"""Bind: which articol de cale a document is on (ARCHITECTURE §4.2, step 2). Deterministic.

An articol of the document path matches when every filter it sets equals the document's (fiscal
class, our role, storno, the client's CUI on a receipt), the day is within its validity, every
``require`` axis of the client's CO.DiT is among the listed values and no ``forbid`` axis is.
Ties go to the row with more filters, then the narrower ``require``, then the latest
``valid_from``. One candidate binds; none or several is a question (``define_articol``).

Only ``active`` rows bind in production; ``allow_draft`` admits draft rows for invented firms
and test firms (P14).
"""

from __future__ import annotations

from kit.catalog import Catalog


def candidates(
    cat: Catalog,
    fiscal_class: str | None,
    our_role: str | None,
    is_storno: bool,
    axes: dict[str, str],
    day: str,
    our_cui_on_doc: bool | None = None,
    allow_draft: bool = False,
) -> list[str]:
    facts = {
        "fiscal_class": fiscal_class,
        "our_role": our_role,
        "is_storno": is_storno,
        "our_cui_on_doc": our_cui_on_doc,
    }
    ranked = []
    for aid in cat.ids("Articol"):
        a = cat.get("Articol", aid)
        if a.procedure != "document" or a.status == "deprecated":
            continue
        if a.status == "draft" and not allow_draft:
            continue
        filters = {k: v for k, v in a.filters.model_dump().items() if v is not None}
        if any(facts[k] != v for k, v in filters.items()):
            continue
        if (a.valid_from and day < a.valid_from) or (a.valid_to and day > a.valid_to):
            continue
        if any(axes.get(ax) not in vs for ax, vs in a.require.items()):
            continue
        if any(axes.get(ax) in vs for ax, vs in a.forbid.items()):
            continue
        narrow = -sum(len(vs) for vs in a.require.values()) if a.require else -1_000_000
        ranked.append(((len(filters), narrow, a.valid_from or ""), aid))
    if not ranked:
        return []
    best = max(rank for rank, _ in ranked)
    return sorted(aid for rank, aid in ranked if rank == best)
