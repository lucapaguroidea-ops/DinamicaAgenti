"""Sorting (``batch:{id}``): what a file is, whether it is primary, whether it may become a Job.

``decide`` runs the emit gates of ARCHITECTURE §4.1 on a ``Pack`` (one file of one client) and
lists every gate that fails; the file emits only when none does. It never writes: the Job's
unique key is returned for the store (WP-08) to insert once.

Gates, in order: ``class`` (the source document is posting-eligible), ``primary`` (one of its
primary kinds is present, unless it may emit incomplete), ``identity`` (the client is on the
document where it must be; a required counterparty CUI is present and passes its check digit),
``bon_fork`` (a receipt's CUI question is answered), ``job_kind`` (exactly one Job kind lists
the document; a credit note only the storno kind). An unknown file asks ``define_class``; an
open receipt fork asks ``bon_cui_unclear``; a container whose identity and primary gates pass
asks ``decont_split`` and never emits itself. ``split`` checks that answer and returns the
child packs, each to go through ``decide`` on its own.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, StringConstraints, ValidationError

from kit.catalog import Catalog, Slug
from kit.types import cui_is_valid, is_period, normalize_cui

GATES = ("class", "primary", "identity", "bon_fork", "job_kind")


def _cui(v: str) -> str:
    if not cui_is_valid(v):
        raise ValueError(f"{v!r} is not a valid CUI")
    return normalize_cui(v)


def _period(v: str) -> str:
    if not is_period(v):
        raise ValueError(f"{v!r} is not a period YYYY-MM")
    return v


Cui = Annotated[str, AfterValidator(_cui)]
Period = Annotated[str, AfterValidator(_period)]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Pack(Closed):
    """One file of one client, as Sorting sees it."""

    client_cui: Cui
    period: Period
    source_hash: Sha256
    source_doc_id: Slug
    kinds: list[Slug] = []
    our_role: Literal["inbound", "outbound", "n_a"] | None = None
    counterparty_cui: str | None = None  # checked by the identity gate, not refused here
    identity_ok: bool = False  # the client is on the document
    is_storno: bool = False
    bon_our_cui_on_doc: bool | None = None


class Decision(Closed):
    emit: bool
    job_kind: str | None
    failed: list[str]
    question: str | None
    split: bool
    job_key: dict[str, str] | None


def decide(cat: Catalog, pack: Pack) -> Decision:
    row = cat.get("SourceDoc", pack.source_doc_id)  # unknown id: CatalogError (P10)
    failed: list[str] = []

    if not row.posting_eligible:
        failed.append("class")
    if not set(row.primary_kinds) & set(pack.kinds) and not row.emit_on_incomplete:
        failed.append("primary")
    cp = pack.counterparty_cui
    if (row.needs_client_on_doc and not pack.identity_ok) or (
        row.needs_counterparty_cui and not (cp and cui_is_valid(cp))
    ):
        failed.append("identity")
    if row.bon_cui_fork and pack.bon_our_cui_on_doc is None:
        failed.append("bon_fork")

    job_kind = None
    if row.posting_eligible:
        kinds = [
            j.id
            for j in (cat.get("JobKind", i) for i in cat.ids("JobKind"))
            if pack.source_doc_id in j.source_docs and j.storno == pack.is_storno
        ]
        if len(kinds) == 1:
            job_kind = kinds[0]
        else:
            failed.append("job_kind")

    split_now = row.split is not None and not {"identity", "primary"} & set(failed)
    if pack.source_doc_id == "unknown":
        question = "define_class"
    elif "bon_fork" in failed:
        question = "bon_cui_unclear"
    elif split_now:
        question = row.split.question
    else:
        question = None

    emit = not failed
    return Decision(
        emit=emit,
        job_kind=job_kind if emit else None,
        failed=failed,
        question=question,
        split=split_now,
        job_key={"client_cui": pack.client_cui, "source_hash": pack.source_hash} if emit else None,
    )


class SplitError(ValueError):
    """The decont_split answer is refused; the question is asked again with this reason."""


class Part(Closed):
    part_hash: Sha256
    source_doc_id: Slug
    kinds: list[Slug] = []
    bon_our_cui_on_doc: bool | None = None
    counterparty_cui: str | None = None


class SplitAnswer(Closed):
    parts: list[Part]


def split(cat: Catalog, container: Pack, answer: Any) -> list[Pack]:
    """Check a ``decont_split`` answer for ``container``; return one child pack per part."""
    row = cat.get("SourceDoc", container.source_doc_id)
    if row.split is None:
        raise SplitError(f"{container.source_doc_id} is not a container")
    try:
        parts = SplitAnswer.model_validate(answer).parts
    except ValidationError as exc:
        raise SplitError(
            "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
        ) from exc
    if not parts:
        raise SplitError("name at least one part")
    hashes = [p.part_hash for p in parts]
    if len(set(hashes)) != len(hashes):
        raise SplitError("part hashes must be unique")
    if container.source_hash in hashes:
        raise SplitError("a part cannot carry the container's own hash")

    children = []
    for p in parts:
        if p.source_doc_id not in row.split.children:
            raise SplitError(f"{p.source_doc_id} is not a part of {container.source_doc_id}")
        if p.source_doc_id == "ro_efactura_pdf" and {"ubl_spv", "xml"} & set(p.kinds):
            raise SplitError("a part with its XML: ro_efactura_ubl, not ro_efactura_pdf (P6)")
        child_row = cat.get("SourceDoc", p.source_doc_id)
        if child_row.bon_cui_fork and p.bon_our_cui_on_doc is None:
            raise SplitError(f"part {p.part_hash[:12]}: is the client's CUI on the receipt?")
        children.append(
            Pack(
                client_cui=container.client_cui,
                period=container.period,
                source_hash=p.part_hash,
                source_doc_id=p.source_doc_id,
                kinds=p.kinds,
                our_role=child_row.our_role_default or container.our_role or row.our_role_default,
                counterparty_cui=p.counterparty_cui,
                identity_ok=container.identity_ok,
                bon_our_cui_on_doc=p.bon_our_cui_on_doc,
            )
        )
    return children
