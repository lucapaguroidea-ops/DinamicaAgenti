"""WP-20, the ``catalog.py`` step: the kit's catalog loader (``kit/catalog.py``) and its rows
(``catalog/``) against the core's (``core.catalog``: ``load_catalog``, ``Catalog``,
``CatalogError``, read on the pinned checkout's ``catalog/``), before any replacement.

**What each side has.** The kit: eleven catalogs, each a file of ``rows`` keyed by ``id``; every
row a closed model (``CATALOGS``); every scalar read as text; every problem of a load reported at
once (``CatalogError.problems``); rows looked up by ``Catalog.get(kind, id)`` and ``ids(kind)``.
The core: twenty-one catalogs, each with its own list keys and id fields (``_ROWS``); rows kept as
the YAML's dicts, only ``WriteModule`` and ``ModelRole`` validated as models; YAML's own types;
the first problem raised; rows by attribute (``source_docs``, ``jobs``, ...) with two named
lookups (``articol``, ``hitl_kind``). The kit's eleven catalogs are ten of the core's and its
``ArticoleCoDitAxes`` (``CORE_OF``); ten core catalogs have no kit namesake. Neither loader reads
the other's files (``file_format``), so the loaders are compared on the same fact written in each
side's own format, and the rows through an explicit field map (``FIELDS``).

**The loader.** 115 invented-row cases (``CASES``): for each of the ten catalogs both carry with
rows, an unknown field, a missing id, a duplicate id and five statuses (unknown, active without
approval, deprecated, yanked, none); seven references to a row that does not exist; two unknown
axes; three P2 shapes; five scalars; four model pins; twelve file faults; two problems at once; a
split container marked posting_eligible. Each case is applied to a copy of each side's own
catalog (the pinned checkout is only read) and loaded. Compared: accepted or refused, and whether
the reason names the row; the wording is prose and is not compared, and the number of problems
reported is its own gap. Also compared: how each loader takes its root, a lookup of an unknown id
or catalog, the row types, the status vocabulary, an unquoted money value's type, and what the
kit's modules import from ``kit/catalog.py``.

**The rows.** For each catalog both carry: the ids on one side only; on the shared ids each mapped
field (lists as sets; no value, an empty list and false alike); the fields only one side's rows
have. Model roles share no id and are compared by count, system, pin and slot (no model id is
written here); the CO.DiT vocabulary axis by axis. Differences the earlier steps declared are
cited from their ``PARITY_GAPS``, not declared again: the sorting step's gaps 5, 6 and 14, the
recon step's gap 17, the questions step's gaps 1 to 3 and 6, the period step's gap 6, and the
WP-20 row's open gap for this step (the CO.DiT vocabulary), of which ``axis_vocabulary`` is the
whole.

**What agrees.** The loader: 55 of 115 cases, 11 accepted and 44 refused on both (a missing or
duplicate id in every catalog, every reference to a row that does not exist, an articol with no
path, an alias pin, YAML that does not parse or is not a mapping, an unknown catalog, two base
files, an additive file with no base, the other side's catalog, a deprecated row but a model
role). The rows: 570 of 706 field positions of the shared rows; two of six shared axes.

**Live paths.** Every kit caller loads ``catalog/`` with ``load_catalog`` and reads rows through
``Catalog.get`` and ``ids``; both sides load their own catalog, so no refusal case is on a live
path: each is a guard on a file the owner edits. Every one of the eleven catalogs is read by some
kit module; ``LIVE`` names the fields read, bracketed by what the five invented firms' months and
every hank's check read through the rows and by every field a reading module names. On those
fields 427 of 515 positions agree; the 88 that differ are in the source documents (29), articole
(14), mouths (4, doc_class), profiles (7), close kinds (1), controls (27), filings (4) and question
kinds (2). Off the live paths: a Job kind's articole, a profile's review and sink_source, a
filing's form, books gate, closer and certainty, a mouth's fields but doc_class, and the status of
any row but an articol.

**Vacuity.** No row on either side is active or deprecated (the kit's 105 rows are all draft; the
core's are draft but for its 8 filings and 27 question kinds, which carry no status, and its model
roles, wired or shadow), so the rows never exercise the status lifecycle (P14): the invented rows
do, each side accepting and refusing a status. 194 of the 570 agreeing positions (185 of the 427
live) agree only empty against empty; a mutation that sets a kit field the core leaves empty is
caught (BUILD WP-20).

**What it does not prove**, because neither catalog nor the invented rows exercise it: the core's
checks with no kit counterpart (a graph's allowed articole and questions, an articol in both Flux
and Reconcile, a write module's used_by_flux both ways, a model role's family, pack, route and
card, the Jev annex) and its catalogs the kit has not (``core_only_catalogs``); the kit's rule that
only a document path names a mouth (no other articol exists to carry one), its additive files (it
has none), a Job kind naming an articol off the document path; nor which side's rows are right,
which the owner decides (P14, P15).

While any gap stands the kit keeps ``kit/catalog.py``; the owner frames the decision (BUILD
WP-20)."""

from __future__ import annotations

import copy
import typing
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import pytest
import yaml
from poarta_contabila import core
from test_calendar import _pinned_checkout
from test_period_parity import PARITY_GAPS as PERIOD_GAPS
from test_questions_parity import PARITY_GAPS as QUESTIONS_GAPS
from test_recon_parity import PARITY_GAPS as RECON_GAPS
from test_sorting_parity import PARITY_GAPS as SORTING_GAPS
from test_sorting_parity import ROW_FIELDS as SOURCE_DOC_FIELDS

from kit import catalog as kc
from kit.catalog import load_catalog

ROOT = Path(__file__).resolve().parents[1]

# ----- the two loaders' files -----

# Each kit catalog → the core catalog that carries the same rows: its catalog name, the list key
# of its rows and their id field (``poarta_contabila.catalog._ROWS``). The kit's files all hold
# ``rows`` keyed by ``id``.
CORE_OF = {
    "SourceDoc": ("ArticoleSourceDoc", "rows", "source_doc_id"),
    "JobKind": ("ArticoleJobs", "jobs", "job_kind"),
    "Articol": ("ArticoleFlux", "flux", "articol_id"),
    "Mouth": ("ArticoleWriteModule", "modules", "module_id"),
    "ReconcileProfile": ("ArticoleReconcile", "profiles", "profile_id"),
    "CloseKind": ("ArticoleClose", "kinds", "close_kind"),
    "Control": ("ArticoleControls", "controls", "control_id"),
    "Filing": ("ArticoleFiling", "filings", "filing_id"),
    "QuestionKind": ("ArticoleHITL", "kinds", "kind"),
    "ModelRole": ("ArticoleModelRoles", "roles", "role_id"),
}
# The kit's Axis rows are the core's ArticoleCoDitAxes, which has no rows (``existing_axes`` and
# ``new_axes`` mappings) and no id field; its loader checks nothing in it.
AXES_DOC = "ArticoleCoDitAxes"

# One row per catalog that both sides carry, by the same fact: the same id, or (job kinds,
# controls) the same row under the core's spelling of its id, or (model roles, no id shared)
# the role that judges a document on both sides.
TARGET = {
    "SourceDoc": ("decont_cheltuieli", "decont_cheltuieli"),
    "JobKind": ("ro_efactura", "job_ro_efactura"),
    "Articol": ("ro_efactura_inbound", "ro_efactura_inbound"),
    "Mouth": ("intrare_factura_xml", "intrare_factura_xml"),
    "ReconcileProfile": ("pre_doc_nr_date", "pre_doc_nr_date"),
    "CloseKind": ("close_standard", "close_standard"),
    "Control": ("c0_synthetic_parity", "C0_synthetic_parity"),
    "Filing": ("d300_platitor", "d300_platitor"),
    "QuestionKind": ("v3_approve", "v3_approve"),
    "ModelRole": ("judge_document", "jev_v3_judge"),
}


@cache
def _kcat() -> kc.Catalog:
    return load_catalog(ROOT / "catalog")


@cache
def _core_dir() -> Path:
    return _pinned_checkout()


@cache
def _ccat() -> core.Catalog:
    return core.load_catalog(_core_dir())


class Tree:
    """One side's catalog files, parsed, to mutate and write out; ``raw`` holds files written as
    text (a YAML mistake the parser cannot hold), ``gone`` the files removed."""

    def __init__(self, root: Path, side: str) -> None:
        self.side = side
        self.docs: dict[str, dict] = {}
        for path in sorted(root.rglob("*.yaml")):
            self.docs[str(path.relative_to(root))] = yaml.safe_load(path.read_text("utf-8"))
        self.raw: dict[str, str] = {}

    def file_of(self, kind: str) -> str:
        """The base file of the kit catalog ``kind`` (on the core's side, its namesake's)."""
        name = kind if self.side == "kit" else CORE_OF[kind][0]
        return next(
            rel
            for rel, d in self.docs.items()
            if isinstance(d, dict) and d.get("catalog") == name and d.get("mode") != "additive"
        )

    def _where(self, kind: str) -> tuple[str, str]:
        return ("rows", "id") if self.side == "kit" else CORE_OF[kind][1:]

    def rows(self, kind: str) -> list[dict]:
        """Every row of ``kind``, base and additive files alike, in place."""
        name = kind if self.side == "kit" else CORE_OF[kind][0]
        key = self._where(kind)[0]
        return [
            r
            for d in self.docs.values()
            if isinstance(d, dict) and d.get("catalog") == name
            for r in d.get(key) or []
        ]

    def row(self, kind: str, rid: str | None = None) -> dict:
        rid = rid or TARGET[kind][0 if self.side == "kit" else 1]
        id_field = self._where(kind)[1]
        return next(r for r in self.rows(kind) if r.get(id_field) == rid)

    def id_field(self, kind: str) -> str:
        return self._where(kind)[1]

    def append(self, kind: str, row: dict) -> None:
        self.docs[self.file_of(kind)][self._where(kind)[0]].append(row)

    def write(self, dest: Path) -> Path:
        for rel, doc in self.docs.items():
            path = dest / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(_dump(rel, doc), "utf-8")
        for rel, text in self.raw.items():
            path = dest / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, "utf-8")
        return dest


_DUMPED: dict[str, tuple[dict, str]] = {}


def _dump(rel: str, doc: dict) -> str:
    """The file's text; an unchanged file is dumped once (a speed-up only)."""
    seen = _DUMPED.get(rel)
    if seen is not None and seen[0] == doc:
        return seen[1]
    text = yaml.safe_dump(doc, sort_keys=False, allow_unicode=True)
    if seen is None:
        _DUMPED[rel] = (copy.deepcopy(doc), text)
    return text


@cache
def _trees() -> tuple[Tree, Tree]:
    return Tree(ROOT / "catalog", "kit"), Tree(_core_dir(), "core")


@dataclass(frozen=True)
class Outcome:
    """A load: accepted or refused; the problems it reports (each side's own count) and whether
    its reason names the row the case is about (``None``: the case is about no one row)."""

    status: str
    problems: int = 0
    names_row: bool | None = None
    error: str = ""

    def view(self) -> tuple:
        return (self.status, self.problems, self.names_row)


def _kit_load(root: Path) -> kc.Catalog:
    return load_catalog(root)


_PARSED: dict[str, object] = {}


def _safe_load(text: str):
    """``yaml.safe_load``, remembering what an unchanged file parses to (a speed-up only: a text
    seen before gives a copy of what it gave; a new one, a refusal included, is parsed)."""
    if text not in _PARSED:
        _PARSED[text] = yaml.safe_load(text)
    return copy.deepcopy(_PARSED[text])


def _core_load(root: Path) -> core.Catalog:
    import types
    from unittest import mock

    from poarta_contabila import catalog as core_catalog

    fast = types.SimpleNamespace(safe_load=_safe_load, YAMLError=yaml.YAMLError)
    with mock.patch.object(core_catalog, "yaml", fast):
        return core.load_catalog(root)


def _outcome(load: Callable, root: Path, row: str | None) -> Outcome:
    try:
        load(root)
    except kc.CatalogError as exc:
        names = None if row is None else any(row in p for p in exc.problems)
        return Outcome("refused", len(exc.problems), names, "kit.catalog.CatalogError")
    except core.CatalogError as exc:
        text = str(exc)
        problems = text.count("\n  ") if text.startswith("catalog references") else 1
        names = None if row is None else row in text
        return Outcome("refused", problems, names, type(exc).__name__)
    return Outcome("accepted")


# ----- the invented rows: one mutation per side, the same fact -----


@dataclass(frozen=True)
class Case:
    kit: Callable[[Tree], None]
    core: Callable[[Tree], None]
    rows: tuple[str | None, str | None] = (None, None)  # the row each reason should name
    note: str = ""


def _set(kind: str, kit_field: str, kit_value, core_field: str | None = None, core_value=None):
    """A case setting one field of the kind's target row on both sides (``None`` field: drop)."""

    def kit(t: Tree) -> None:
        t.row(kind)[kit_field] = kit_value

    def core_(t: Tree) -> None:
        t.row(kind)[core_field or kit_field] = kit_value if core_value is None else core_value

    return Case(kit, core_, TARGET[kind])


def _drop(kind: str, kit_field: str, core_field: str | None = None, rows: bool = True) -> Case:
    def kit(t: Tree) -> None:
        t.row(kind).pop(kit_field, None)

    def core_(t: Tree) -> None:
        t.row(kind).pop(core_field or kit_field, None)

    return Case(kit, core_, TARGET[kind] if rows else (None, None))


def _missing_id(kind: str) -> Case:
    def mut(t: Tree) -> None:
        t.row(kind).pop(t.id_field(kind))

    return Case(mut, mut)


def _duplicate(kind: str) -> Case:
    def mut(t: Tree) -> None:
        t.append(kind, copy.deepcopy(t.row(kind)))

    return Case(mut, mut, TARGET[kind])


def _extend(kind: str, kit_field: str, core_field: str, value: str = "zzz_unknown") -> Case:
    def kit(t: Tree) -> None:
        t.row(kind)[kit_field] = [*t.row(kind).get(kit_field, []), value]

    def core_(t: Tree) -> None:
        t.row(kind)[core_field] = [*t.row(kind).get(core_field, []), value]

    return Case(kit, core_, TARGET[kind])


def _split(kit_field: str, core_field: str, value) -> Case:
    def kit(t: Tree) -> None:
        t.row("SourceDoc")["split"][kit_field] = value

    def core_(t: Tree) -> None:
        t.row("SourceDoc")["split"][core_field] = value

    return Case(kit, core_, TARGET["SourceDoc"])


def _file(kit: Callable[[Tree], None], core_: Callable[[Tree], None] | None = None) -> Case:
    return Case(kit, core_ or kit)


def _add_file(doc: dict | str, rel: str = "60_practice/zzz.yaml") -> Callable[[Tree], None]:
    def mut(t: Tree) -> None:
        t.raw[rel] = doc if isinstance(doc, str) else yaml.safe_dump(doc)

    return mut


def _filings(mut: Callable[[dict], None]) -> Callable[[Tree], None]:
    return lambda t: mut(t.docs[t.file_of("Filing")])


def _yml(t: Tree) -> None:
    rel = t.file_of("Filing")
    t.raw[rel[: -len(".yaml")] + ".yml"] = yaml.safe_dump(t.docs[rel])


def _two_bases(t: Tree) -> None:
    t.raw["60_practice/zzz_second_base.yaml"] = yaml.safe_dump(t.docs[t.file_of("Filing")])


def _no_base(t: Tree) -> None:
    t.docs[t.file_of("Filing")]["mode"] = "additive"


def _no_filings(t: Tree) -> None:
    del t.docs[t.file_of("Filing")]


def _repeated_key(t: Tree) -> None:
    rel = t.file_of("Filing")
    text = yaml.safe_dump(t.docs[rel], sort_keys=False)
    t.raw[rel] = text.replace("  form: D300\n", "  form: D300\n  form: D300\n", 1)
    assert t.raw[rel] != text
    del t.docs[rel]


def _no_gate(t: Tree) -> None:
    row = t.row("Articol")
    for f in ("gate", "hitl", "first_n"):
        row.pop(f, None)


def _no_path(t: Tree) -> None:
    t.row("Articol").pop("procedure" if t.side == "kit" else "graph_id")


def _no_mouth(t: Tree) -> None:
    row = t.row("Articol")
    if t.side == "kit":
        row["mouths"] = []
        return
    row["write_modules"] = []
    for m in t.rows("Mouth"):  # the core keeps both ends of a module's use; drop both
        m["used_by_flux"] = [a for a in m.get("used_by_flux") or [] if a != row["articol_id"]]


def _close_profile(t: Tree) -> None:
    t.row("CloseKind")["recon_profile" if t.side == "kit" else "recon_flux"] = "zzz_unknown"


def _axis(axis: str, value: str) -> Callable[[Tree], None]:
    def mut(t: Tree) -> None:
        t.row("Articol").setdefault("require", {})[axis] = [value]

    return mut


def _slot_clash(t: Tree) -> None:
    row = copy.deepcopy(t.row("ModelRole"))
    row[t.id_field("ModelRole")] = "zzz_second_judge"
    t.append("ModelRole", row)


def _two_problems(t: Tree) -> None:
    _duplicate("Filing").kit(t)
    _missing_id("JobKind").kit(t)


def _other_format(side: str) -> Callable[[Tree], None]:
    """Replace the side's files with the other side's: each loader on the other's catalog."""

    def mut(t: Tree) -> None:
        other = _trees()[1 if side == "kit" else 0]
        t.docs = copy.deepcopy(other.docs)

    return mut


KINDS = tuple(CORE_OF)

CASES: dict[str, Case] = {
    # A row field neither side's schema names.
    **{f"unknown_field.{k}": _set(k, "zzz_unknown", "x") for k in KINDS},
    # A row without its id.
    **{f"missing_id.{k}": _missing_id(k) for k in KINDS},
    # The same id twice in one catalog.
    **{f"duplicate_id.{k}": _duplicate(k) for k in KINDS},
    # The status lifecycle.
    **{f"status_unknown.{k}": _set(k, "status", "zzz_unknown") for k in KINDS},
    **{f"status_active_unapproved.{k}": _set(k, "status", "active") for k in KINDS},
    **{f"status_deprecated.{k}": _set(k, "status", "deprecated") for k in KINDS},
    **{f"status_yanked.{k}": _set(k, "status", "yanked") for k in KINDS},
    **{f"status_absent.{k}": _drop(k, "status") for k in KINDS},
    # A reference to a row that does not exist.
    "ref.job_source_doc": _extend("JobKind", "source_docs", "source_doc_ids"),
    "ref.job_articol": _extend("JobKind", "articole", "allowed_flux"),
    "ref.articol_mouth": _extend("Articol", "mouths", "write_modules"),
    "ref.filing_control": _extend("Filing", "books_gate", "books_gate"),
    "ref.split_child": _split("children", "children", ["workings", "zzz_unknown"]),
    "ref.split_question": _split("question", "hitl", "zzz_unknown"),
    "ref.close_profile": Case(_close_profile, _close_profile, TARGET["CloseKind"]),
    "ref.axis_unknown": Case(
        _axis("zzz_unknown", "x"), _axis("zzz_unknown", "x"), TARGET["Articol"]
    ),
    "ref.axis_value_unknown": Case(
        _axis("tva", "zzz_unknown"), _axis("tva", "zzz_unknown"), TARGET["Articol"]
    ),
    # An articol names its path and its gate, and a document path its mouth (P2).
    "articol.no_gate": Case(_no_gate, _no_gate, TARGET["Articol"]),
    "articol.no_path": Case(_no_path, _no_path, TARGET["Articol"]),
    "articol.document_without_mouth": Case(_no_mouth, _no_mouth, TARGET["Articol"]),
    # Scalars: money, accounts and a gate's count.
    "scalar.money_unquoted": _set("ReconcileProfile", "tolerance", 0.05),
    "scalar.money_three_decimals": _set("ReconcileProfile", "tolerance", "0.055"),
    "scalar.money_not_a_number": _set("ReconcileProfile", "tolerance", "five"),
    "scalar.account_not_an_account": _set(
        "ReconcileProfile", "fallback_accounts", ["4x"], "fallback_accounts"
    ),
    "scalar.first_n_without_its_policy": _set(
        "Mouth", "gate", {"policy": "always", "first_n": 3}, "first_n", 3
    ),
    # Model roles: the pin.
    "model.alias_auto": _set("ModelRole", "model", "auto"),
    "model.not_an_exact_id": _set("ModelRole", "model", "best"),
    "model.unpinned": Case(
        lambda t: t.row("ModelRole").pop("model", None),  # the kit's unset pin is no key
        lambda t: t.row("ModelRole").__setitem__("model", None),
    ),
    "model.one_role_per_slot": Case(_slot_clash, _slot_clash),
    # Files.
    "file.unknown_catalog": _file(_add_file({"catalog": "Zzz", "file_schema": "1", "rows": []})),
    "file.not_yaml": _file(_add_file("catalog: [\n")),
    "file.not_a_mapping": _file(_add_file("- a\n- b\n")),
    "file.repeated_key": _file(_repeated_key),
    "file.yml_suffix": _file(_yml),
    "file.unknown_top_level_key": _file(_filings(lambda d: d.__setitem__("zzz_unknown", 1))),
    "file.schema_version": _file(_filings(lambda d: d.__setitem__("file_schema", "2"))),
    "file.unknown_mode": _file(_filings(lambda d: d.__setitem__("mode", "zzz_unknown"))),
    "file.two_bases": _file(_two_bases),
    "file.additive_without_base": _file(_no_base),
    "file.catalog_missing": _file(_no_filings),
    "file.the_other_sides_catalog": Case(_other_format("kit"), _other_format("core")),
    # Every problem at once, or the first.
    "report.two_problems": _file(_two_problems),
}


@cache
def _loads() -> dict[str, tuple[Outcome, Outcome]]:
    """Every case, through both loaders, each on a copy of its own side's catalog."""
    import tempfile

    out = {}
    with tempfile.TemporaryDirectory() as tmp:
        for name, case in CASES.items():
            got = []
            for side, (load, mutate) in enumerate(((_kit_load, case.kit), (_core_load, case.core))):
                tree = copy.deepcopy(_trees()[side])
                mutate(tree)
                dest = tree.write(Path(tmp) / name / ("kit" if side == 0 else "core"))
                got.append(_outcome(load, dest, case.rows[side]))
            out[name] = (got[0], got[1])
    return out


# ----- the loaders' other edges: the root, lookups, scalars, the status lifecycle -----


def _call(f: Callable) -> str:
    try:
        f()
    except Exception as exc:  # the type is the observation
        return type(exc).__name__
    return "ok"


def _with_env(f: Callable):
    from unittest import mock

    with mock.patch.dict("os.environ", {"POARTA_CATALOG_DIR": str(_core_dir())}):
        return f()


@cache
def _root_view() -> dict[str, tuple[str, str]]:
    """How each loader takes its root: a str, a directory that does not exist, none."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        nowhere = Path(tmp) / "nowhere"

        def kit_empty() -> str:
            return f"accepted, {sum(len(r) for r in load_catalog(nowhere).rows.values())} rows"

        return {
            "str": (
                _call(lambda: load_catalog(str(ROOT / "catalog"))),
                _call(lambda: core.load_catalog(str(_core_dir()))),
            ),
            "missing directory": (kit_empty(), _call(lambda: core.load_catalog(nowhere))),
            "none, POARTA_CATALOG_DIR set": (
                _call(lambda: load_catalog(None)),
                _call(lambda: _with_env(lambda: core.load_catalog(None))),
            ),
        }


def _lookup_view() -> dict[str, tuple[object, object]]:
    """A lookup of an id the catalog has not, and of a catalog it has not."""
    k, c = _kcat(), _ccat()
    return {
        "unknown id": (
            _call(lambda: k.get("Articol", "zzz_unknown")),
            {
                "articol": _call(lambda: c.articol("zzz_unknown")),
                "hitl_kind": _call(lambda: c.hitl_kind("zzz_unknown")),
                "rows by attribute": _call(lambda: c.source_docs["zzz_unknown"]),
            },
        ),
        "unknown catalog": (_call(lambda: k.get("Zzz", "x")), _call(lambda: c.docs["Zzz"])),
        "error base": (kc.CatalogError.__mro__[1].__name__, core.CatalogError.__mro__[1].__name__),
        "row type": (
            sorted(
                {type(r).__mro__[1].__name__ for rows in k.rows.values() for r in rows.values()}
            ),
            sorted(
                {
                    type(r).__name__
                    for n in ("articole", "source_docs", "write_modules", "model_roles")
                    for r in getattr(c, n).values()
                }
            ),
        ),
    }


def _status_vocabulary() -> tuple[dict, dict]:
    """The status values each loader takes, per catalog (``unchecked``: any value or none)."""
    from poarta_contabila.model_roles import ModelRole

    kit_values = list(typing.get_args(kc.Row.model_fields["status"].annotation))
    mine = {"every catalog": kit_values, "active needs": "approved: 'owner, YYYY-MM-DD'"}
    theirs = {
        "Mouth": list(typing.get_args(core.WriteModule.model_fields["status"].annotation)),
        "ModelRole": list(typing.get_args(ModelRole.model_fields["status"].annotation)),
        "every other catalog": "unchecked",
        "active needs": "nothing",
    }
    return mine, theirs


def _statuses_in_use() -> tuple[dict, dict]:
    """The status of every row the two catalogs carry, counted per catalog."""
    k, c = _kcat(), _ccat()
    mine = {kind: dict(Counter(r.status for r in rows.values())) for kind, rows in k.rows.items()}
    attr = {
        "SourceDoc": "source_docs",
        "JobKind": "jobs",
        "Articol": "articole",
        "Mouth": "write_modules",
        "ReconcileProfile": "recon_profiles",
        "CloseKind": "close_kinds",
        "Control": "controls",
        "Filing": "filings",
        "QuestionKind": "hitl",
        "ModelRole": "model_roles",
    }

    def status(r) -> str:
        s = r.get("status") if isinstance(r, dict) else r.status
        return s or "none"

    theirs = {
        kind: dict(Counter(status(r) for r in getattr(c, a).values())) for kind, a in attr.items()
    }
    return mine, theirs


def _scalar_view() -> dict[str, tuple[str, str]]:
    """What an unquoted money value is once loaded: the kit reads every scalar as a string."""
    import tempfile

    case = CASES["scalar.money_unquoted"]
    with tempfile.TemporaryDirectory() as tmp:
        got = []
        for side, (load, mutate) in enumerate(((_kit_load, case.kit), (_core_load, case.core))):
            tree = copy.deepcopy(_trees()[side])
            mutate(tree)
            cat = load(tree.write(Path(tmp) / str(side)))
            row = (
                cat.get("ReconcileProfile", "pre_doc_nr_date")
                if side == 0
                else cat.recon_profiles["pre_doc_nr_date"]
            )
            value = row.tolerance if side == 0 else row["tolerance"]
            got.append(f"{type(value).__name__} {value!r}")
    return {"tolerance: 0.05": (got[0], got[1])}


# ----- the rows: every catalog both sides carry, id by id and field by field -----

# The kit's procedure → the core's graph (the questions step's GRAPH).
GRAPH = {
    "sorting": "folder_triage",
    "document": "ingest_source_doc",
    "reconcile": "reconcile_sink",
    "close": "monthly_close",
}


def _dig(row, path: str):
    cur = row
    for part in path.split("."):
        if cur is None:
            return None
        cur = cur.get(part) if isinstance(cur, dict) else getattr(cur, part, None)
    return cur


def _norm(v):
    """One spelling for both sides: no value, an empty list and false alike; lists as sorted
    sets; mappings of lists with their lists sorted; numbers as the text YAML wrote."""
    if v in (None, [], (), {}, False):
        return None
    if isinstance(v, (list, tuple)):
        return sorted(str(x) for x in v)
    if isinstance(v, dict):
        return {str(k): _norm(x) for k, x in sorted(v.items())} or None
    if hasattr(v, "model_dump"):
        return _norm(v.model_dump())
    return v if isinstance(v, (bool, str)) else str(v)


def _core_id(kind: str, kid: str) -> str:
    if kind == "JobKind":
        return f"job_{kid}"
    if kind == "Control":
        return kid[0].upper() + kid[1:]
    return kid


def _profile_of(c: core.Catalog, articol_id: str | None):
    return (c.articole.get(articol_id) or {}).get("profile_id")


def _recon_articole(c: core.Catalog, profile_id: str) -> list[dict]:
    return [a for a in c.articole.values() if a.get("profile_id") == profile_id]


# Per catalog: (the kit's field, the core's field or a function of the core's row and catalog).
FIELDS: dict[str, tuple[tuple[str, object], ...]] = {
    "SourceDoc": (*SOURCE_DOC_FIELDS, ("status", "status")),
    "JobKind": (
        ("source_docs", "source_doc_ids"),
        ("articole", "allowed_flux"),
        ("status", "status"),
    ),
    "Articol": (
        ("procedure", lambda r, c: next((p for p, g in GRAPH.items() if g == r["graph_id"]), None)),
        ("gate.policy", "hitl"),
        ("gate.first_n", "first_n"),
        ("filters.fiscal_class", "filters.fiscal_class"),
        ("filters.our_role", "filters.our_role"),
        ("filters.is_storno", "extra_filters.is_storno"),
        ("filters.our_cui_on_doc", "extra_filters.our_cui_on_doc"),
        ("require", "require"),
        ("forbid", "forbid"),
        ("mouths", "write_modules"),
        ("reconcile.match_keys", "reconcile.match_keys"),
        ("reconcile.expect_accounts", "reconcile.expect_accounts"),
        ("reconcile.tolerance", "reconcile.tolerance"),
        ("valid_from", lambda r, c: r.get("valid_from") or c.docs["ArticoleFlux"]["valid_from"]),
        ("valid_to", "valid_to"),
        ("status", "status"),
    ),
    "Mouth": (
        ("saga_path", "saga_path"),
        ("doc_class", lambda r, c: core.mouth_doc_class(r.module_id)),
        ("validare", "validare"),
        ("backup", "backup"),
        ("gate.policy", "hitl"),
        ("gate.first_n", "first_n"),
        ("fixture", "fixture"),
        ("status", "status"),
    ),
    "ReconcileProfile": (
        ("stage", lambda r, c: sorted({a["stage"] for a in _recon_articole(c, r["profile_id"])})),
        ("match_keys", "match_keys"),
        ("number_levels", "number_match"),
        ("tolerance", "tolerance"),
        ("sink_source", "sink_source"),
        ("require_all_accounts", "require_all_accounts"),
        ("fallback_accounts", "fallback_accounts"),
        ("review", "llm_review"),
        (
            "fiscal_classes",
            lambda r, c: [
                a["filters"]["fiscal_class"]
                for a in _recon_articole(c, r["profile_id"])
                if (a.get("filters") or {}).get("fiscal_class")
            ],
        ),
        ("status", "status"),
    ),
    "CloseKind": (
        ("require", "require"),
        ("forbid", "forbid"),
        ("recon_profile", lambda r, c: _profile_of(c, r.get("recon_flux"))),
        ("watched_extra", "watched_extra"),
        ("v4", "v4"),
        ("status", "status"),
    ),
    "Control": (
        ("layer", "layer"),
        ("severity", "severity"),
        ("watched", "watched"),
        ("epsilon", "epsilon"),
        ("require", "require"),
        ("status", "status"),
    ),
    "Filing": (
        ("form", "form"),
        ("require", "require"),
        ("forbid", "forbid"),
        ("books_gate", lambda r, c: [g[0].lower() + g[1:] for g in r.get("books_gate") or []]),
        ("closer", "closer"),
        ("certainty", "certainty"),
        ("status", "status"),
    ),
    "QuestionKind": (
        ("actor", "actor"),
        (
            "procedure",
            lambda r, c: [p for p, g in GRAPH.items() if g in (r.get("graph_ids") or [])],
        ),
        ("answer", lambda r, c: list(r.get("resume_schema") or {})),
        ("status", "status"),
    ),
}
# The kit's fields compared through another view: the answer's field names (its grammar is the
# questions step's), a procedure as the list of the core's graphs it maps to, a profile's stage
# as the stages of the core's articole that name it.
VIEW = {
    ("QuestionKind", "answer"): lambda v: list(v),
    ("QuestionKind", "procedure"): lambda v: [v],
    ("ReconcileProfile", "stage"): lambda v: [v],
}
# Fields a row carries that are prose or the row's own key, compared on neither side.
NOT_COMPARED = {"id", "note", "schema_version", "approved", "rule", "check"}


def _core_rows(kind: str) -> dict:
    c = _ccat()
    attr = {
        "SourceDoc": c.source_docs,
        "JobKind": c.jobs,
        "Articol": c.articole,
        "Mouth": c.write_modules,
        "ReconcileProfile": c.recon_profiles,
        "CloseKind": c.close_kinds,
        "Control": c.controls,
        "Filing": c.filings,
        "QuestionKind": c.hitl,
        "ModelRole": c.model_roles,
    }
    return attr[kind]


def _core_value(kind: str, row, spec) -> object:
    if callable(spec):
        return spec(row, _ccat())
    return _dig(row, spec)


@cache
def _ids() -> dict[str, tuple[list[str], list[str], list[str]]]:
    """Per catalog: the ids both carry (the kit's spelling), the kit's only, the core's only."""
    out = {}
    for kind in CORE_OF:
        mine = set(_kcat().ids(kind))
        theirs = set(_core_rows(kind))
        shared = sorted(k for k in mine if _core_id(kind, k) in theirs)
        out[kind] = (
            shared,
            sorted(mine - set(shared)),
            sorted(theirs - {_core_id(kind, k) for k in shared}),
        )
    return out


@cache
def _field_diffs() -> dict[str, dict[str, tuple]]:
    """Per catalog, ``<id>.<field>`` → (the kit's value, the core's) where shared rows differ."""
    out: dict[str, dict[str, tuple]] = {}
    for kind, specs in FIELDS.items():
        diffs = {}
        for kid in _ids()[kind][0]:
            krow, crow = _kcat().get(kind, kid), _core_rows(kind)[_core_id(kind, kid)]
            for kf, cf in specs:
                k = _dig(krow, kf)
                k = VIEW.get((kind, kf), lambda v: v)(k) if k is not None else None
                if kind == "SourceDoc" and kf == "our_role_default" and _dig(crow, cf) == "either":
                    c = None  # the core's child_pack reads "either" as none (the sorting step)
                else:
                    c = _core_value(kind, crow, cf)
                if _norm(k) != _norm(c):
                    diffs[f"{kid}.{kf}"] = (_norm(k), _norm(c))
        out[kind] = diffs
    return out


def _core_keys(kind: str) -> set[str]:
    keys: set[str] = set()
    for r in _core_rows(kind).values():
        keys |= set(r.model_dump() if hasattr(r, "model_dump") else r)
    return keys


@cache
def _one_side_fields() -> dict[str, tuple[list[str], list[str]]]:
    """Per catalog: the row fields only the kit's rows have, and only the core's (top level)."""
    out = {}
    for kind, specs in FIELDS.items():
        kit_fields = set(kc.CATALOGS[kind].model_fields) - NOT_COMPARED
        mapped_kit = {kf.split(".")[0] for kf, _ in specs}
        mapped_core = {cf.split(".")[0] for _, cf in specs if isinstance(cf, str)}
        mapped_core |= DERIVED_FROM.get(kind, set())
        theirs = _core_keys(kind) - NOT_COMPARED - mapped_core - {CORE_OF[kind][2]}
        out[kind] = (sorted(kit_fields - mapped_kit), sorted(theirs))
    return out


# The core's fields a derived comparison reads.
DERIVED_FROM = {
    "Articol": {"graph_id", "valid_from"},
    "Mouth": set(),
    "CloseKind": {"recon_flux"},
    "Filing": {"books_gate"},
    "QuestionKind": {"graph_ids", "resume_schema"},
}
SPLIT_CASE = "split.container_posting_eligible"


def _container_posting(t: Tree) -> None:
    t.row("SourceDoc")["posting_eligible"] = True


CASES[SPLIT_CASE] = Case(_container_posting, _container_posting, TARGET["SourceDoc"])


def _axes_view() -> tuple[dict, dict]:
    """The CO.DiT vocabulary: the kit's Axis rows, the core's ArticoleCoDitAxes (its existing and
    new axes); per shared axis, the values on one side only (``null`` the core's unset value)."""
    mine = {a: list(_kcat().get("Axis", a).values) for a in _kcat().ids("Axis")}
    doc = _ccat().docs[AXES_DOC]
    theirs = {k: list(v) for k, v in (doc.get("existing_axes") or {}).items()}
    theirs.update({k: list(v["values"]) for k, v in (doc.get("new_axes") or {}).items()})
    kit, core_ = {}, {}
    for axis in sorted(set(mine) | set(theirs)):
        if axis not in theirs:
            kit[axis] = "axis"
        elif axis not in mine:
            core_[axis] = "axis"
        else:
            spell = lambda vs: ["null" if v is None else str(v) for v in vs]  # noqa: E731
            only_k = sorted(set(spell(mine[axis])) - set(spell(theirs[axis])))
            only_c = sorted(set(spell(theirs[axis])) - set(spell(mine[axis])))
            if only_k:
                kit[axis] = only_k
            if only_c:
                core_[axis] = only_c
    return kit, core_


SYSTEMS = {"one": "system_one", "two": "system_two", "reader": "document_reading"}


def _model_roles_view() -> tuple[dict, dict]:
    """Model roles share no id; what each side has: how many, by system, pinned or not (no model
    id is written here), and the slot a role fills."""
    k = [_kcat().get("ModelRole", r) for r in _kcat().ids("ModelRole")]
    c = list(_ccat().model_roles.values())
    return (
        {
            "rows": len(k),
            "by system": dict(sorted(Counter(SYSTEMS[r.system] for r in k).items())),
            "pinned": sum(r.model is not None for r in k),
            "slot": "hank, codon, tier",
        },
        {
            "rows": len(c),
            "by system": dict(sorted(Counter(r.system for r in c).items())),
            "pinned": sum(r.model is not None for r in c),
            "slot": "graph_id, node",
        },
    )


# ----- tagging: every difference to the gap that explains it -----

LOADER_TAGS = (
    ("unknown_field.", "unknown_row_field"),
    ("status_unknown.", "status_vocabulary"),
    ("status_yanked.", "status_vocabulary"),
    ("status_deprecated.", "status_vocabulary"),
    ("status_active_unapproved.", "active_without_approval"),
    ("status_absent.", "status_required"),
    ("ref.axis_", "axes_unchecked"),
    ("articol.", "path_and_gate"),
    ("scalar.", "scalar_shapes"),
    ("model.", "model_pin_rules"),
    ("file.catalog_missing", "missing_catalog"),
    ("file.", "file_rules"),
    (SPLIT_CASE, "split_container_posting"),
)


def _loader_tag(case: str) -> str:
    return next((g for prefix, g in LOADER_TAGS if case.startswith(prefix)), "unexplained")


def _group(case: str) -> str:
    """A case's name without the catalog it ran on: the counts are per kind of case."""
    head, _, tail = case.rpartition(".")
    return head if tail in CORE_OF else case


@cache
def _loader_tally() -> dict:
    """Per gap, the cases' outcomes on each side, counted; and the agreement."""
    gaps: dict[str, tuple[Counter, Counter]] = {}
    agree: Counter = Counter()
    for case, (k, c) in _loads().items():
        if k.status != c.status:
            g = _loader_tag(case)
            mine, theirs = gaps.setdefault(g, (Counter(), Counter()))
            mine[f"{_group(case)}: {k.status}"] += 1
            theirs[f"{_group(case)}: {c.status}"] += 1
            continue
        if None not in (k.names_row, c.names_row) and k.names_row != c.names_row:
            mine, theirs = gaps.setdefault("reason_names_no_row", (Counter(), Counter()))
            mine[f"{case}: names it"] += 1
            theirs[f"{case}: names it not"] += 1
        agree[k.status] += 1
        if k.status == "refused" and k.problems != c.problems:
            mine, theirs = gaps.setdefault("problems_reported", (Counter(), Counter()))
            mine[f"{case}: {k.problems}"] += 1
            theirs[f"{case}: {c.problems}"] += 1
    out = {g: (dict(sorted(a.items())), dict(sorted(b.items()))) for g, (a, b) in gaps.items()}
    return {"gaps": out, "agree": dict(agree)}


ROW_TAGS = {
    "SourceDoc": "source_doc_rows",
    "JobKind": "job_kind_rows",
    "Articol": "articol_rows",
    "Mouth": "mouth_rows",
    "ReconcileProfile": "reconcile_profile_rows",
    "CloseKind": "close_kind_rows",
    "Control": "control_rows",
    "Filing": "filing_rows",
    "QuestionKind": "question_kind_rows",
}


def _row_tag(kind: str, key: str) -> str:
    if key.endswith(".status"):
        return "status_by_row"
    if kind == "ReconcileProfile" and key.endswith(".review"):
        return "reconcile_profile_review"
    return ROW_TAGS[kind]


@cache
def _row_tally() -> dict[str, tuple[dict, dict]]:
    out: dict[str, tuple[dict, dict]] = {}
    for kind, diffs in _field_diffs().items():
        for key, (k, c) in diffs.items():
            mine, theirs = out.setdefault(_row_tag(kind, key), ({}, {}))
            mine[f"{kind}.{key}" if _row_tag(kind, key) == "status_by_row" else key] = k
            theirs[f"{kind}.{key}" if _row_tag(kind, key) == "status_by_row" else key] = c
    return out


# ----- what the kit's other modules take from kit/catalog.py -----


def _caller_names() -> list[str]:
    import ast

    names = set()
    for path in sorted((ROOT / "kit").glob("*.py")):
        if path.name == "catalog.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module == "kit.catalog":
                names |= {a.name for a in node.names}
    return sorted(names)


def _caller_shapes() -> tuple[dict, dict[str, str]]:
    names = _caller_names()
    theirs = {n: "present" if hasattr(core, n) else "absent" for n in names}
    for method in ("get", "ids", "rows"):  # what the kit's callers call on a Catalog
        theirs[f"Catalog.{method}"] = "present" if hasattr(core.Catalog, method) else "absent"
    theirs["Slug pattern"] = core.Slug.__metadata__[0].pattern
    return {"names": names, "Slug pattern": kc.Slug.__metadata__[0].pattern}, theirs


def _file_format() -> tuple[dict, dict]:
    """Each kit catalog's file key and id field; the core's namesake's."""
    from poarta_contabila.catalog import _ROWS

    mine = {kind: "rows / id" for kind in kc.CATALOGS}
    theirs = {}
    for kind in kc.CATALOGS:
        name = AXES_DOC if kind == "Axis" else CORE_OF[kind][0]
        spec = _ROWS[name]
        theirs[kind] = (
            f"{name}: " + ", ".join(f"{k} / {i}" for k, i in spec) if spec else f"{name}: no rows"
        )
    theirs["Articol"] += "; ArticoleReconcile: flux / articol_id"  # both lists are articole
    return mine, theirs


def _core_only_catalogs() -> list[str]:
    from poarta_contabila.catalog import _ROWS

    used = {AXES_DOC} | {CORE_OF[k][0] for k in CORE_OF}
    return sorted(set(_ROWS) - used)


# ----- the declared gaps, (the kit's, the core's) -----


PARITY_GAPS: dict[str, tuple[object, object]] = {
    # ----- the loader -----
    # status active with no owner's approval on the row: the kit refuses it (P14), the core takes it
    # (its ModelRole refuses active as outside its vocabulary, which agrees).
    "active_without_approval": (
        {"status_active_unapproved: refused": 9},
        {"status_active_unapproved: accepted": 9},
    ),
    # require / forbid naming an axis or value the CO.DiT vocabulary has not: the kit refuses, the
    # core's loader checks no axis.
    "axes_unchecked": (
        {"ref.axis_unknown: refused": 1, "ref.axis_value_unknown: refused": 1},
        {"ref.axis_unknown: accepted": 1, "ref.axis_value_unknown: accepted": 1},
    ),
    # A repeated YAML key, a .yml file, an unknown top-level key, a file_schema other than 1, a mode
    # other than base / additive: the kit refuses; the core keeps the last key, reads only *.yaml,
    # reads neither file_schema nor an unknown mode (any mode but additive is a base).
    "file_rules": (
        {
            "file.repeated_key: refused": 1,
            "file.schema_version: refused": 1,
            "file.unknown_mode: refused": 1,
            "file.unknown_top_level_key: refused": 1,
            "file.yml_suffix: refused": 1,
        },
        {
            "file.repeated_key: accepted": 1,
            "file.schema_version: accepted": 1,
            "file.unknown_mode: accepted": 1,
            "file.unknown_top_level_key: accepted": 1,
            "file.yml_suffix: accepted": 1,
        },
    ),
    # A catalog with no file at all: the kit loads it empty, the core refuses (every catalog but
    # ArticoleCoDitAxes and ArticoleExtrasGrain must be there).
    "missing_catalog": (
        {"file.catalog_missing: accepted": 1},
        {"file.catalog_missing: refused": 1},
    ),
    # A pin that is a word with no digit, two roles on one slot: the kit refuses (P8), the core
    # takes them (it refuses only its own alias pattern, which 'auto' meets on both sides).
    "model_pin_rules": (
        {"model.not_an_exact_id: refused": 1, "model.one_role_per_slot: refused": 1},
        {"model.not_an_exact_id: accepted": 1, "model.one_role_per_slot: accepted": 1},
    ),
    # P2: an articol with no gate, a document articol with no mouth: the kit refuses, the core takes
    # them (an articol with no path is refused on both: the core for its unknown graph).
    "path_and_gate": (
        {"articol.document_without_mouth: refused": 1, "articol.no_gate: refused": 1},
        {"articol.document_without_mouth: accepted": 1, "articol.no_gate: accepted": 1},
    ),
    # Both refuse; the kit reports every problem of the load (a refused row also leaves the rows
    # that name it dangling), the core stops at the first.
    "problems_reported": (
        {
            "articol.no_path: 2": 1,
            "file.the_other_sides_catalog: 50": 1,
            "file.two_bases: 9": 1,
            "missing_id.Articol: 2": 1,
            "missing_id.Control: 3": 1,
            "missing_id.Mouth: 3": 1,
            "report.two_problems: 2": 1,
            "status_absent.Mouth: 3": 1,
            "status_unknown.Mouth: 3": 1,
            "unknown_field.Mouth: 3": 1,
        },
        {
            "articol.no_path: 1": 1,
            "file.the_other_sides_catalog: 1": 1,
            "file.two_bases: 1": 1,
            "missing_id.Articol: 1": 1,
            "missing_id.Control: 1": 1,
            "missing_id.Mouth: 1": 1,
            "report.two_problems: 1": 1,
            "status_absent.Mouth: 1": 1,
            "status_unknown.Mouth: 1": 1,
            "unknown_field.Mouth: 1": 1,
        },
    ),
    # Both refuse a bad model role; the kit's reason names the row, the core's (a pydantic error on
    # the merged role) does not.
    "reason_names_no_row": (
        {
            "model.alias_auto: names it": 1,
            "status_absent.ModelRole: names it": 1,
            "status_active_unapproved.ModelRole: names it": 1,
            "status_unknown.ModelRole: names it": 1,
            "status_yanked.ModelRole: names it": 1,
            "unknown_field.ModelRole: names it": 1,
        },
        {
            "model.alias_auto: names it not": 1,
            "status_absent.ModelRole: names it not": 1,
            "status_active_unapproved.ModelRole: names it not": 1,
            "status_unknown.ModelRole: names it not": 1,
            "status_yanked.ModelRole: names it not": 1,
            "unknown_field.ModelRole: names it not": 1,
        },
    ),
    # Money with three decimals or not a number, an account that is not one, a first_n beside a
    # policy that is not first_n: the kit's value types refuse them, the core reads no type.
    "scalar_shapes": (
        {
            "scalar.account_not_an_account: refused": 1,
            "scalar.first_n_without_its_policy: refused": 1,
            "scalar.money_not_a_number: refused": 1,
            "scalar.money_three_decimals: refused": 1,
        },
        {
            "scalar.account_not_an_account: accepted": 1,
            "scalar.first_n_without_its_policy: accepted": 1,
            "scalar.money_not_a_number: accepted": 1,
            "scalar.money_three_decimals: accepted": 1,
        },
    ),
    # A split container marked posting_eligible: the kit takes it, the core refuses it.
    "split_container_posting": (
        {"split.container_posting_eligible: accepted": 1},
        {"split.container_posting_eligible: refused": 1},
    ),
    # A row with no status: the kit requires one; the core only on WriteModule and ModelRole.
    "status_required": (
        {"status_absent: refused": 8},
        {"status_absent: accepted": 8},
    ),
    # A status outside a side's lifecycle: the kit's is draft / active / deprecated in every
    # catalog; the core checks none outside WriteModule (draft / active / deprecated / yanked)
    # and ModelRole (wired / shadow / not_wired), so it takes any value elsewhere, yanked on a
    # mouth too, and refuses deprecated on a model role.
    "status_vocabulary": (
        {
            "status_deprecated: accepted": 1,
            "status_unknown: refused": 8,
            "status_yanked: refused": 9,
        },
        {
            "status_deprecated: refused": 1,
            "status_unknown: accepted": 8,
            "status_yanked: accepted": 9,
        },
    ),
    # A row field neither schema names: the kit's closed row models refuse it in every catalog; the
    # core's rows are dicts, so only its two validated rows (WriteModule, ModelRole) refuse it.
    "unknown_row_field": (
        {"unknown_field: refused": 8},
        {"unknown_field: accepted": 8},
    ),
    # ----- the rows -----
    # The ten shared articole, field by field (the core's filters split into filters and
    # extra_filters; its valid_from is its file's).
    "articol_rows": (
        {
            "bon_cu_cui.filters.our_role": "inbound",
            "bon_fara_cui.filters.our_role": "inbound",
            "bon_fara_cui.reconcile.expect_accounts": None,
            "extras_statement.reconcile.expect_accounts": ["5121"],
            "foreign_invoice_inbound.mouths": ["intrare_factura_xml", "parteneri_xml"],
            "foreign_invoice_inbound.require": {"tva": ["tva_platitor"]},
            "foreign_invoice_outbound.mouths": ["iesire_factura_xml", "parteneri_xml"],
            "foreign_rc_neplatitor.forbid": None,
            "foreign_rc_neplatitor.mouths": ["nota_nc_dbf"],
            "foreign_rc_neplatitor.require": {"tva": ["tva_neplatitor", "tva_scutire_mici"]},
            "ro_efactura_inbound.forbid": None,
            "ro_efactura_outbound.forbid": None,
            "storno_iesire.reconcile.expect_accounts": ["4111", "4427"],
            "storno_intrare.reconcile.expect_accounts": ["401", "4426"],
        },
        {
            "bon_cu_cui.filters.our_role": None,
            "bon_fara_cui.filters.our_role": None,
            "bon_fara_cui.reconcile.expect_accounts": ["6"],
            "extras_statement.reconcile.expect_accounts": ["5121", "5311"],
            "foreign_invoice_inbound.mouths": [
                "articole_xml",
                "intrare_factura_xml",
                "parteneri_xml",
            ],
            "foreign_invoice_inbound.require": None,
            "foreign_invoice_outbound.mouths": [
                "articole_xml",
                "iesire_factura_xml",
                "parteneri_xml",
            ],
            "foreign_rc_neplatitor.forbid": {"tva": ["tva_platitor"]},
            "foreign_rc_neplatitor.mouths": ["nota_nc_dbf", "parteneri_xml"],
            "foreign_rc_neplatitor.require": {
                "cross_border": ["inbound_eu_services", "mixed"],
                "tva": ["tva_neplatitor", "tva_scutire_mici"],
            },
            "ro_efactura_inbound.forbid": {"rol": ["mandat_contabil"]},
            "ro_efactura_outbound.forbid": {"rol": ["mandat_contabil"]},
            "storno_iesire.reconcile.expect_accounts": ["4111"],
            "storno_intrare.reconcile.expect_accounts": ["401"],
        },
    ),
    # close_standard requires tva_091 too in the core, a value the kit's vocabulary has not
    # (axis_vocabulary).
    "close_kind_rows": (
        {"close_standard.require": {"tva": ["tva_neplatitor", "tva_platitor", "tva_scutire_mici"]}},
        {
            "close_standard.require": {
                "tva": ["tva_091", "tva_neplatitor", "tva_platitor", "tva_scutire_mici"]
            }
        },
    ),
    # The fourteen controls: layer close vs v2, the epsilon the kit leaves unset, and the two regime
    # controls' require, which is the period step's gap 6 (regime_controls_on_a_payer).
    "control_rows": (
        {
            "c0_synthetic_parity.layer": "close",
            "c1_outbound_complete.epsilon": None,
            "c1_outbound_complete.layer": "close",
            "c2_unexplained_empty.epsilon": None,
            "c2_unexplained_empty.layer": "close",
            "c2_waiting_for_xml.epsilon": None,
            "c2_waiting_for_xml.layer": "close",
            "m1_1_payables_tie.epsilon": None,
            "m1_1_payables_tie.layer": "close",
            "m1_1_trade_ext.epsilon": None,
            "m1_1_trade_ext.layer": "close",
            "m1_2_receivables_tie.epsilon": None,
            "m1_2_receivables_tie.layer": "close",
            "m1_2_trade_ext.epsilon": None,
            "m1_2_trade_ext.layer": "close",
            "m1_8_4428_open.epsilon": None,
            "m1_8_4428_open.layer": "close",
            "m1_9_4424_watched.epsilon": None,
            "m1_9_4424_watched.layer": "close",
            "p_prefile_duplicate.epsilon": None,
            "p_prefile_hard_failures.epsilon": None,
            "t_regime_4428.epsilon": None,
            "t_regime_4428.layer": "close",
            "t_regime_4428.require": {"tva": ["tva_neplatitor", "tva_scutire_mici"]},
            "t_regime_442x.epsilon": None,
            "t_regime_442x.layer": "close",
            "t_regime_442x.require": {"tva": ["tva_neplatitor", "tva_scutire_mici"]},
        },
        {
            "c0_synthetic_parity.layer": "v2",
            "c1_outbound_complete.epsilon": "0.00",
            "c1_outbound_complete.layer": "v2",
            "c2_unexplained_empty.epsilon": "0.00",
            "c2_unexplained_empty.layer": "v2",
            "c2_waiting_for_xml.epsilon": "0.00",
            "c2_waiting_for_xml.layer": "v2",
            "m1_1_payables_tie.epsilon": "0.01",
            "m1_1_payables_tie.layer": "v2",
            "m1_1_trade_ext.epsilon": "0.01",
            "m1_1_trade_ext.layer": "v2",
            "m1_2_receivables_tie.epsilon": "0.01",
            "m1_2_receivables_tie.layer": "v2",
            "m1_2_trade_ext.epsilon": "0.01",
            "m1_2_trade_ext.layer": "v2",
            "m1_8_4428_open.epsilon": "0.01",
            "m1_8_4428_open.layer": "v2",
            "m1_9_4424_watched.epsilon": "0.01",
            "m1_9_4424_watched.layer": "v2",
            "p_prefile_duplicate.epsilon": "0.00",
            "p_prefile_hard_failures.epsilon": "0.00",
            "t_regime_4428.epsilon": "0.01",
            "t_regime_4428.layer": "v2",
            "t_regime_4428.require": None,
            "t_regime_442x.epsilon": "0.01",
            "t_regime_442x.layer": "v2",
            "t_regime_442x.require": None,
        },
    ),
    # The eight filings: requires and forbids that differ, and d300's books gate.
    "filing_rows": (
        {
            "d100_micro.require": {"impozit": ["micro_1", "micro_3"]},
            "d100_profit.forbid": {"forma": ["ii", "pfa"]},
            "d112_payroll.forbid": None,
            "d300_platitor.books_gate": [
                "c0_synthetic_parity",
                "c1_outbound_complete",
                "c2_unexplained_empty",
            ],
            "d390_rc.forbid": None,
        },
        {
            "d100_micro.require": {"impozit": ["micro_1"]},
            "d100_profit.forbid": {"forma": ["pfa"]},
            "d112_payroll.forbid": {"employees": ["none"]},
            "d300_platitor.books_gate": [
                "c0_synthetic_parity",
                "c1_outbound_complete",
                "c2_unexplained_empty",
                "t_regime_442x",
            ],
            "d390_rc.forbid": {"cross_border": ["none"]},
        },
    ),
    # ro_efactura's articole: the core's job also allows the storno articole (the kit has a storno
    # job of its own, sorting step gap 14).
    "job_kind_rows": (
        {"ro_efactura.articole": ["ro_efactura_inbound", "ro_efactura_outbound"]},
        {
            "ro_efactura.articole": [
                "ro_efactura_inbound",
                "ro_efactura_outbound",
                "storno_iesire",
                "storno_intrare",
            ]
        },
    ),
    # The ten mouths: validare person vs human, the fixtures the kit has not, incasare / plata's
    # first_n, and doc_class against the core's mouth_doc_class (None: a mouth it does not render).
    "mouth_rows": (
        {
            "articole_xml.fixture": None,
            "bon_via_nota.doc_class": "nota_interna",
            "bon_via_nota.fixture": None,
            "bon_via_nota.validare": "person",
            "iesire_factura_xml.fixture": None,
            "iesire_factura_xml.validare": "person",
            "incasare_xml.fixture": None,
            "incasare_xml.gate.first_n": "3",
            "incasare_xml.validare": "person",
            "intrare_factura_xml.fixture": None,
            "intrare_factura_xml.validare": "person",
            "nota_nc_dbf.doc_class": "nota_interna",
            "nota_nc_dbf.fixture": None,
            "nota_nc_dbf.validare": "person",
            "parteneri_xml.fixture": None,
            "plata_xml.fixture": None,
            "plata_xml.gate.first_n": "3",
            "plata_xml.validare": "person",
            "storno_iesire_xml.doc_class": "storn_iesire",
            "storno_iesire_xml.fixture": None,
            "storno_iesire_xml.validare": "person",
            "storno_intrare_xml.doc_class": "storn_intrare",
            "storno_intrare_xml.fixture": None,
            "storno_intrare_xml.validare": "person",
        },
        {
            "articole_xml.fixture": "fixtures/saga/articole.xml",
            "bon_via_nota.doc_class": None,
            "bon_via_nota.fixture": "fixtures/saga/bon_nota.dbf",
            "bon_via_nota.validare": "human",
            "iesire_factura_xml.fixture": "fixtures/saga/iesire.xml",
            "iesire_factura_xml.validare": "human",
            "incasare_xml.fixture": "fixtures/saga/incasare.xml",
            "incasare_xml.gate.first_n": "5",
            "incasare_xml.validare": "human",
            "intrare_factura_xml.fixture": "fixtures/saga/intrare.xml",
            "intrare_factura_xml.validare": "human",
            "nota_nc_dbf.doc_class": None,
            "nota_nc_dbf.fixture": "fixtures/saga/NC_sample.dbf",
            "nota_nc_dbf.validare": "human",
            "parteneri_xml.fixture": "fixtures/saga/parteneri.xml",
            "plata_xml.fixture": "fixtures/saga/plata.xml",
            "plata_xml.gate.first_n": "5",
            "plata_xml.validare": "human",
            "storno_iesire_xml.doc_class": None,
            "storno_iesire_xml.fixture": "fixtures/saga/storno_iesire.xml",
            "storno_iesire_xml.validare": "human",
            "storno_intrare_xml.doc_class": None,
            "storno_intrare_xml.fixture": "fixtures/saga/storno_intrare.xml",
            "storno_intrare_xml.validare": "human",
        },
    ),
    # need_rj_export's procedure is the questions step's gap 2 (asked_where); filing_receipt's
    # receipt_key is its gap 3 (answer_shapes).
    "question_kind_rows": (
        {
            "filing_receipt.answer": ["filing_id", "period", "receipt_key", "submitted_by"],
            "need_rj_export.procedure": ["reconcile"],
        },
        {
            "filing_receipt.answer": ["filing_id", "period", "receipt_bucket_key", "submitted_by"],
            "need_rj_export.procedure": ["reconcile", "sorting"],
        },
    ),
    # post_* profiles: review false vs llm_review true (not read by the kit).
    "reconcile_profile_review": (
        {"post_bon_how.review": None, "post_doc_how.review": None, "post_how_4428.review": None},
        {"post_bon_how.review": True, "post_doc_how.review": True, "post_how_4428.review": True},
    ),
    # The status of the rows the core writes none on: every filing and question kind.
    "status_by_row": (
        {
            "Filing.d100_micro.status": "draft",
            "Filing.d100_profit.status": "draft",
            "Filing.d112_payroll.status": "draft",
            "Filing.d300_platitor.status": "draft",
            "Filing.d301_neplatitor_rc.status": "draft",
            "Filing.d390_rc.status": "draft",
            "Filing.d394_platitor.status": "draft",
            "Filing.d406_saft.status": "draft",
            "QuestionKind.bon_cui_unclear.status": "draft",
            "QuestionKind.control_disposition.status": "draft",
            "QuestionKind.decont_split.status": "draft",
            "QuestionKind.define_articol.status": "draft",
            "QuestionKind.define_class.status": "draft",
            "QuestionKind.explained_rule.status": "draft",
            "QuestionKind.filing_receipt.status": "draft",
            "QuestionKind.need_rj_export.status": "draft",
            "QuestionKind.recon_ambiguous.status": "draft",
            "QuestionKind.recon_how_mismatch.status": "draft",
            "QuestionKind.recon_review_contest.status": "draft",
            "QuestionKind.v2_close.status": "draft",
            "QuestionKind.v3_approve.status": "draft",
            "QuestionKind.v4_codit.status": "draft",
            "QuestionKind.wait_validare.status": "draft",
        },
        {
            "Filing.d100_micro.status": None,
            "Filing.d100_profit.status": None,
            "Filing.d112_payroll.status": None,
            "Filing.d300_platitor.status": None,
            "Filing.d301_neplatitor_rc.status": None,
            "Filing.d390_rc.status": None,
            "Filing.d394_platitor.status": None,
            "Filing.d406_saft.status": None,
            "QuestionKind.bon_cui_unclear.status": None,
            "QuestionKind.control_disposition.status": None,
            "QuestionKind.decont_split.status": None,
            "QuestionKind.define_articol.status": None,
            "QuestionKind.define_class.status": None,
            "QuestionKind.explained_rule.status": None,
            "QuestionKind.filing_receipt.status": None,
            "QuestionKind.need_rj_export.status": None,
            "QuestionKind.recon_ambiguous.status": None,
            "QuestionKind.recon_how_mismatch.status": None,
            "QuestionKind.recon_review_contest.status": None,
            "QuestionKind.v2_close.status": None,
            "QuestionKind.v3_approve.status": None,
            "QuestionKind.v4_codit.status": None,
            "QuestionKind.wait_validare.status": None,
        },
    ),
}


def _normed(pair: tuple[dict, dict]) -> tuple[dict, dict]:
    return tuple({k: _norm(v) for k, v in side.items()} for side in pair)  # type: ignore[return-value]


def _recon_cited() -> tuple[dict, dict]:
    """The recon step's gap 17 (``profile_rows``) as ``<profile>.<field>``; its
    ``account_amounts`` is a field only the core's rows have here (``one_side_fields``)."""

    def flat(side: dict) -> dict:
        return {
            f"{pid}.{f}": _norm(v)
            for pid, fs in side.items()
            for f, v in fs.items()
            if f != "account_amounts"
        }

    kit, core_ = RECON_GAPS["profile_rows"]
    return flat(kit), flat(core_)


PARITY_GAPS.update(
    {
        # ----- the rows, cited from the earlier steps, not declared again -----
        # The source documents only one side has: the sorting step's gap 5 (source_doc_ids).
        "source_doc_ids": SORTING_GAPS["source_doc_ids"],
        # The shared source documents' fields: the sorting step's gap 6 (source_doc_rows), 29.
        "source_doc_rows": _normed(SORTING_GAPS["source_doc_rows"]),
        # The Job kinds' names: the sorting step's gap 14 (job_kind_ids).
        "job_kind_ids": SORTING_GAPS["job_kind_ids"],
        # The question kinds only the core has: the questions step's gap 1 (core_only_kinds).
        "question_kind_ids": ([], QUESTIONS_GAPS["core_only_kinds"][1]),
        # The six reconcile profiles' fields: the recon step's gap 17 (profile_rows).
        "reconcile_profile_rows": _recon_cited(),
        # ----- the rows, new here -----
        # The CO.DiT vocabulary: the kit's Axis rows against the core's ArticoleCoDitAxes. The
        # WP-20 row's open gap for this step named the kit's side and three core axes; this is
        # all of it: the axes and values on one side only ("null" is the core's unset value).
        "axis_vocabulary": (
            {"exig": ["tva_la_livrare"], "forma": ["ii"], "impozit": ["micro_3", "norma_venit"]},
            {
                "book_of_record": "axis",
                "d100_period": "axis",
                "d112_period": "axis",
                "engagement": "axis",
                "exig": ["null", "tva_exig_livrare"],
                "forma": ["ong", "prof", "sucursala"],
                "fx_currencies": "axis",
                "impozit": ["ong_scutit", "pfa_norma", "pfa_real"],
                "marketplace": "axis",
                "oss": "axis",
                "tva": ["tva_091"],
                "tva_period": "axis",
            },
        ),
        # The core's articole of its other three graphs (folder_triage, reconcile_sink,
        # monthly_close): the kit's articole are document paths only, its close kinds and
        # reconcile profiles their own catalogs.
        "articol_ids": (
            [],
            [
                "close_standard",
                "close_tva_incasare",
                "recon_post_bon",
                "recon_post_standard",
                "recon_post_tva_incasare",
                "recon_pre_bon",
                "recon_pre_extras",
                "recon_pre_standard",
                "recon_pre_storno",
                "triage_bon_fork",
                "triage_extras",
                "triage_pair_efactura",
                "triage_place",
            ],
        ),
        # The controls' ids: the same fourteen, lower case vs upper case first letter.
        "control_ids": (
            [
                "c0_synthetic_parity",
                "c1_outbound_complete",
                "c2_unexplained_empty",
                "c2_waiting_for_xml",
                "m1_1_payables_tie",
                "m1_1_trade_ext",
                "m1_2_receivables_tie",
                "m1_2_trade_ext",
                "m1_8_4428_open",
                "m1_9_4424_watched",
                "p_prefile_duplicate",
                "p_prefile_hard_failures",
                "t_regime_4428",
                "t_regime_442x",
            ],
            [
                "C0_synthetic_parity",
                "C1_outbound_complete",
                "C2_unexplained_empty",
                "C2_waiting_for_xml",
                "M1_1_payables_tie",
                "M1_1_trade_ext",
                "M1_2_receivables_tie",
                "M1_2_trade_ext",
                "M1_8_4428_open",
                "M1_9_4424_watched",
                "P_prefile_duplicate",
                "P_prefile_hard_failures",
                "T_regime_4428",
                "T_regime_442x",
            ],
        ),
        # Model roles share no id: nine roles by hank, codon and tier, none pinned (D3), vs
        # thirteen by graph and node, every one pinned. No model id is written here.
        "model_role_rows": (
            {
                "by system": {"document_reading": 3, "system_one": 3, "system_two": 3},
                "pinned": 0,
                "rows": 9,
                "slot": "hank, codon, tier",
            },
            {
                "by system": {"document_reading": 2, "system_one": 7, "system_two": 4},
                "pinned": 13,
                "rows": 13,
                "slot": "graph_id, node",
            },
        ),
        # Row fields only one side's rows carry (top level; prose and ids aside).
        "one_side_fields": (
            {"JobKind": ["storno"]},
            {
                "Articol": ["maps_profile", "profile_id", "route_key", "stage"],
                "CloseKind": ["articol_id", "graph_id", "hitl"],
                "Control": ["on_fail"],
                "Filing": ["due_from"],
                "JobKind": [
                    "graph_id",
                    "hitl_kinds",
                    "matrix",
                    "optional_fields",
                    "reconcile",
                    "required_fields",
                    "thread_prefix",
                    "unique_key",
                ],
                "Mouth": ["approved_at", "max_docs_per_run", "used_by_flux"],
                "QuestionKind": ["cannot", "effects", "server_stamps"],
                "ReconcileProfile": [
                    "account_amounts",
                    "expect_accounts_from",
                    "how",
                    "number_match_note",
                ],
                "SourceDoc": ["aisle", "extract", "flux_candidates", "pairing"],
            },
        ),
        # The core's catalogs the kit has no namesake for.
        "core_only_catalogs": (
            [],
            [
                "ArticolBon",
                "ArticoleCoDitPairs",
                "ArticoleCoDitT",
                "ArticoleExtrasGrain",
                "ArticoleGraph",
                "ArticoleNonWorking",
                "ArticolePins",
                "ArticoleTerms",
                "JevAnnex",
                "JevValidateV",
            ],
        ),
        # ----- the loader, beyond the invented rows -----
        # The files: every kit catalog is `rows` keyed by `id`; the core's names, list keys and
        # id fields are its own, so neither loader reads the other's catalog (both refuse it).
        "file_format": (
            {kind: "rows / id" for kind in kc.CATALOGS},
            {
                "Articol": "ArticoleFlux: flux / articol_id; ArticoleReconcile: flux / articol_id",
                "Axis": "ArticoleCoDitAxes: no rows",
                "CloseKind": "ArticoleClose: kinds / close_kind",
                "Control": "ArticoleControls: controls / control_id",
                "Filing": "ArticoleFiling: filings / filing_id",
                "JobKind": "ArticoleJobs: jobs / job_kind",
                "ModelRole": "ArticoleModelRoles: roles / role_id",
                "Mouth": "ArticoleWriteModule: modules / module_id",
                "QuestionKind": "ArticoleHITL: kinds / kind",
                "ReconcileProfile": "ArticoleReconcile: flux / articol_id, profiles / profile_id",
                "SourceDoc": "ArticoleSourceDoc: rows / source_doc_id",
            },
        ),
        # An unquoted money value: the kit reads every scalar as text, the core as YAML types it.
        "scalar_typing": ({"tolerance: 0.05": "str '0.05'"}, {"tolerance: 0.05": "float 0.05"}),
        # The root: the kit takes a Path only and loads a directory that does not exist as an
        # empty catalog; the core takes a str, refuses a missing directory and reads
        # POARTA_CATALOG_DIR when given none.
        "root_argument": (
            {
                "missing directory": "accepted, 0 rows",
                "none, POARTA_CATALOG_DIR set": "AttributeError",
                "str": "AttributeError",
            },
            {
                "missing directory": "CatalogError",
                "none, POARTA_CATALOG_DIR set": "ok",
                "str": "ok",
            },
        ),
        # Lookups: the kit's Catalog.get raises its CatalogError (an Exception) for an unknown id
        # or catalog; the core's rows are dicts by attribute (KeyError), with two named lookups
        # whose errors are its CatalogError (a ValueError); its rows are dicts but for mouths and
        # model roles, the kit's every row a closed model.
        "lookups": (
            {
                "error base": "Exception",
                "row type": ["Row"],
                "unknown catalog": "CatalogError",
                "unknown id": "CatalogError",
            },
            {
                "error base": "ValueError",
                "row type": ["ModelRole", "WriteModule", "dict"],
                "unknown catalog": "KeyError",
                "unknown id": {
                    "articol": "UnknownArticol",
                    "hitl_kind": "UnknownHitlKind",
                    "rows by attribute": "KeyError",
                },
            },
        ),
        # What the kit's modules import from kit/catalog.py: the core has Catalog, CatalogError,
        # load_catalog and Slug, but not the two row models, and its Catalog has none of the
        # methods the callers use; its Slug is the questions step's gap 6 (slug_pattern).
        "caller_shapes": (
            {
                "names": [
                    "Catalog",
                    "CatalogError",
                    "ModelRoleRow",
                    "ReconcileProfileRow",
                    "Slug",
                    "load_catalog",
                ],
                "Slug pattern": "^[a-z][a-z0-9_]*$",
            },
            {
                "Catalog": "present",
                "Catalog.get": "absent",
                "Catalog.ids": "absent",
                "Catalog.rows": "absent",
                "CatalogError": "present",
                "ModelRoleRow": "absent",
                "ReconcileProfileRow": "absent",
                "Slug": "present",
                "Slug pattern": "^[a-z0-9][a-z0-9_.-]*$",
                "load_catalog": "present",
            },
        ),
    }
)

LOADER_GAPS = {
    "unknown_row_field",
    "status_vocabulary",
    "active_without_approval",
    "status_required",
    "axes_unchecked",
    "path_and_gate",
    "scalar_shapes",
    "model_pin_rules",
    "file_rules",
    "missing_catalog",
    "split_container_posting",
    "reason_names_no_row",
    "problems_reported",
}


def _observed(gap: str) -> tuple[object, object]:
    if gap in LOADER_GAPS:
        return _loader_tally()["gaps"].get(gap, ({}, {}))
    rows = _row_tally()
    if gap in rows:
        return rows[gap]
    ids = _ids()
    if gap == "source_doc_ids":
        return ids["SourceDoc"][1], ids["SourceDoc"][2]
    if gap == "job_kind_ids":
        return sorted(_kcat().ids("JobKind")), sorted(_ccat().jobs)
    if gap == "question_kind_ids":
        return ids["QuestionKind"][1], ids["QuestionKind"][2]
    if gap == "articol_ids":
        return ids["Articol"][1], ids["Articol"][2]
    if gap == "control_ids":
        return sorted(_kcat().ids("Control")), sorted(_ccat().controls)
    if gap == "axis_vocabulary":
        return _axes_view()
    if gap == "model_role_rows":
        return _model_roles_view()
    if gap == "one_side_fields":
        f = _one_side_fields()
        return ({k: v[0] for k, v in f.items() if v[0]}, {k: v[1] for k, v in f.items() if v[1]})
    if gap == "core_only_catalogs":
        return [], _core_only_catalogs()
    if gap == "file_format":
        return _file_format()
    if gap in ("scalar_typing", "root_argument", "lookups"):
        view = {"scalar_typing": _scalar_view, "root_argument": _root_view}.get(gap, _lookup_view)()
        return {k: v[0] for k, v in view.items()}, {k: v[1] for k, v in view.items()}
    if gap == "caller_shapes":
        return _caller_shapes()
    raise KeyError(gap)


@pytest.mark.parametrize("gap", sorted(PARITY_GAPS))
def test_each_declared_gap_still_holds_exactly(gap: str) -> None:
    assert _observed(gap) == PARITY_GAPS[gap]


# ----- live paths: the catalogs and fields the kit's modules read -----

# Per catalog, the row fields some kit module other than catalog.py reads (bind, sorting, steps,
# recon, period, questions, cards, dispatch, hanks, hankrun, scenario, cli). Bracketed by two
# observations below: what the five invented firms' months and every hank's check read through
# the rows, and every field a module that reads the catalog names as an attribute.
LIVE: dict[str, set[str]] = {
    "Axis": {"values"},
    "SourceDoc": {
        "bon_cui_fork",
        "emit_on_incomplete",
        "fiscal_class",
        "needs_client_on_doc",
        "needs_counterparty_cui",
        "our_role_default",
        "posting_eligible",
        "primary_kinds",
        "split",
    },
    "JobKind": {"source_docs", "storno"},
    "Articol": {
        "filters",
        "forbid",
        "gate",
        "mouths",
        "procedure",
        "reconcile",
        "require",
        "status",
        "valid_from",
        "valid_to",
    },
    "Mouth": {"doc_class"},
    "ReconcileProfile": {
        "fallback_accounts",
        "fiscal_classes",
        "match_keys",
        "number_levels",
        "require_all_accounts",
        "stage",
        "tolerance",
    },
    "CloseKind": {"forbid", "recon_profile", "require"},
    "Control": {"epsilon", "layer", "require", "severity", "watched"},
    "Filing": {"forbid", "require"},
    "QuestionKind": {"actor", "answer", "procedure"},
    "ModelRole": {"answer", "card", "codon", "hank", "model", "output", "tier"},
}


def _static_reads() -> dict[str, set[str]]:
    """Every row field a kit module that reads a catalog names as an attribute (a superset: the
    name may be another object's attribute)."""
    import ast

    out: dict[str, set[str]] = {k: set() for k in kc.CATALOGS}
    for path in sorted((ROOT / "kit").glob("*.py")):
        if path.name == "catalog.py":
            continue
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src)
        kinds = {
            n.args[0].value
            for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr in ("get", "ids")
            and n.args
            and isinstance(n.args[0], ast.Constant)
            and n.args[0].value in kc.CATALOGS
        } | {k for k, m in kc.CATALOGS.items() if m.__name__ in src}
        attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        for k in kinds:
            out[k] |= set(kc.CATALOGS[k].model_fields) & attrs
    return out


def _recorded_reads(tmp: Path) -> dict[str, set[str]]:
    """The row fields read while the five invented firms' months run (with and without the
    scenario's defects) and every hank is checked."""
    from kit.hanks import check_hank
    from kit.scenario import DEFECTS, run_month
    from kit.synthetic import FIRMS

    seen: dict[str, set[str]] = {k: set() for k in kc.CATALOGS}
    kinds = {m: k for k, m in kc.CATALOGS.items()}
    original = kc.Row.__getattribute__

    def recording(self, name):
        kind = kinds.get(type(self))
        if kind and name in type(self).model_fields:
            seen[kind].add(name)
        return original(self, name)

    cat = _kcat()
    kc.Row.__getattribute__ = recording  # type: ignore[method-assign]
    try:
        for firm in FIRMS:
            for defects in ((), DEFECTS):
                run_month(cat, tmp / f"{firm}-{len(defects)}", firm, "2026-09", defects=defects)
        for hank in sorted({cat.get("ModelRole", r).hank for r in cat.ids("ModelRole")}):
            check_hank(cat, ROOT, hank)
    finally:
        kc.Row.__getattribute__ = original  # type: ignore[method-assign]
    return seen


def _live(kind: str, key: str) -> bool:
    return key.split(".", 1)[1].split(".")[0] in LIVE[kind]


@cache
def _row_agreement() -> dict[str, int]:
    """Field positions compared on the shared rows (each shared row × each compared field), how
    many agree, and how many of those agree only empty against empty; the same on live fields."""
    out: Counter = Counter()
    for kind, specs in FIELDS.items():
        diffs = _field_diffs()[kind]
        for kid in _ids()[kind][0]:
            krow = _kcat().get(kind, kid)
            for kf, _ in specs:
                key = f"{kid}.{kf}"
                live = _live(kind, key)
                for scope in ("all", "live") if live else ("all",):
                    out[f"{scope} positions"] += 1
                    if key not in diffs:
                        out[f"{scope} agree"] += 1
                        if _norm(_dig(krow, kf)) is None:
                            out[f"{scope} agree empty on both"] += 1
    return dict(out)


# ----- the tests -----


def test_the_core_catalog_is_core_catalog() -> None:
    """The core's loader is ``core.catalog``'s; the kit's is ``kit/catalog.py``."""
    assert core.CORE_MODULES["core.catalog"] == (
        "poarta_contabila.catalog",
        "poarta_contabila.flux",
    )
    assert core.load_catalog.__module__ == "poarta_contabila.catalog"
    assert core.CatalogError.__module__ == "poarta_contabila.catalog"


def test_each_loader_takes_its_own_catalog_and_refuses_the_others() -> None:
    """Live: every kit caller loads ``catalog/``; both sides load their own, and neither reads the
    other's files (``file_format``)."""
    assert sum(len(r) for r in _kcat().rows.values()) == 105
    assert len(_ccat().articole) == 23
    k, c = _loads()["file.the_other_sides_catalog"]
    assert (k.status, c.status) == ("refused", "refused")


def test_the_loaders_agree_outside_the_declared_gaps() -> None:
    """Every invented-row case agrees (outcome, and whether the reason names the row) or is a
    declared gap: 55 of 115 agree, 11 accepted and 44 refused on both."""
    tally = _loader_tally()
    assert len(CASES) == 115
    assert "unexplained" not in tally["gaps"]
    assert tally["agree"] == {"accepted": 11, "refused": 44}
    differ = sum(
        n
        for g, (mine, _) in tally["gaps"].items()
        if g not in ("reason_names_no_row", "problems_reported")
        for n in mine.values()
    )
    assert differ == 115 - 55


def test_the_rows_agree_outside_the_declared_gaps_overall_and_live() -> None:
    """Field positions on the shared rows: 570 of 706 agree, 427 of 515 on the fields the kit
    reads; every difference is a declared gap (tagged by catalog)."""
    assert _row_agreement() == {
        "all positions": 706,
        "all agree": 570,
        "all agree empty on both": 194,
        "live positions": 515,
        "live agree": 427,
        "live agree empty on both": 185,
    }
    live = {kind: sum(_live(kind, k) for k in d) for kind, d in _field_diffs().items()}
    assert live == {
        "SourceDoc": 29,
        "JobKind": 0,
        "Articol": 14,
        "Mouth": 4,
        "ReconcileProfile": 7,
        "CloseKind": 1,
        "Control": 27,
        "Filing": 4,
        "QuestionKind": 2,
    }
    shared_axes = set(_kcat().ids("Axis")) & (
        set(_ccat().docs[AXES_DOC]["existing_axes"]) | set(_ccat().docs[AXES_DOC]["new_axes"])
    )
    kit_only, core_only = PARITY_GAPS["axis_vocabulary"]
    assert sorted(shared_axes - set(kit_only) - set(core_only)) == ["cross_border", "employees"]


def test_the_live_fields_are_what_the_kit_reads(tmp_path) -> None:
    """``LIVE`` lies between what the invented months and the hank checks read and every field a
    catalog-reading module names."""
    recorded, static = _recorded_reads(tmp_path), _static_reads()
    for kind in kc.CATALOGS:
        assert recorded[kind] - NOT_COMPARED <= LIVE[kind] <= static[kind], kind
    # read by no module: the profile's review and sink_source, a filing's form, books gate,
    # closer and certainty, a Job kind's articole, a mouth's every field but doc_class
    unread = {k: sorted(set(_fields_of(k)) - LIVE[k]) for k in FIELDS}
    assert unread["ReconcileProfile"] == ["review", "sink_source", "status"]
    assert unread["JobKind"] == ["articole", "status"]


def _fields_of(kind: str) -> list[str]:
    return [kf.split(".")[0] for kf, _ in FIELDS[kind]]


def test_vacuity_is_pinned_and_probed() -> None:
    """No row is active or deprecated on either side, so the rows never exercise the status
    lifecycle (P14): the invented rows do, each side accepting and refusing a status. 194 of the
    570 agreeing positions are empty on both (185 of 427 live): a probe sets each kit field the
    core writes and is caught (mutations, reported in BUILD)."""
    mine, theirs = _statuses_in_use()
    assert {s for c in mine.values() for s in c} == {"draft"}
    assert theirs["Filing"] == {"none": 8} and theirs["QuestionKind"] == {"none": 27}
    assert theirs["ModelRole"] == {"wired": 7, "shadow": 6}
    assert all(
        set(c) <= {"draft"}
        for k, c in theirs.items()
        if k not in ("Filing", "QuestionKind", "ModelRole")
    )
    status = [v for case, v in _loads().items() if case.startswith("status_")]
    for side in (0, 1):
        assert {o[side].status for o in status} == {"accepted", "refused"}
    assert _status_vocabulary() == (
        {
            "every catalog": ["draft", "active", "deprecated"],
            "active needs": "approved: 'owner, YYYY-MM-DD'",
        },
        {
            "Mouth": ["draft", "active", "deprecated", "yanked"],
            "ModelRole": ["wired", "shadow", "not_wired"],
            "every other catalog": "unchecked",
            "active needs": "nothing",
        },
    )


def test_the_earlier_steps_catalog_gaps_are_the_ones_observed_here() -> None:
    """Consolidated, not declared again: sorting gaps 5, 6 and 14, recon gap 17, questions gaps
    1 to 3 and 6, period gap 6 and the WP-20 row's CO.DiT clause name what this step observes."""
    assert "source_doc_rows" in SORTING_GAPS and "job_kind_ids" in SORTING_GAPS
    assert len(PARITY_GAPS["source_doc_rows"][0]) == 29
    review = PARITY_GAPS["reconcile_profile_review"][0]
    assert sorted(_field_diffs()["ReconcileProfile"]) == sorted(
        [*PARITY_GAPS["reconcile_profile_rows"][0], *review]
    )
    assert "need_rj_export" in QUESTIONS_GAPS["asked_where"][0]
    assert "filing_receipt.receipt_key" in QUESTIONS_GAPS["answer_shapes"][0]
    assert sorted(PARITY_GAPS["question_kind_rows"][0]) == [
        "filing_receipt.answer",
        "need_rj_export.procedure",
    ]
    assert "slug_pattern" in QUESTIONS_GAPS
    assert "regime_controls_on_a_payer" in PERIOD_GAPS
    regime = [k for k in PARITY_GAPS["control_rows"][0] if k.endswith(".require")]
    assert regime == ["t_regime_4428.require", "t_regime_442x.require"]
    kit_only, core_only = PARITY_GAPS["axis_vocabulary"]
    assert {"tva_period", "d100_period", "d112_period"} <= set(core_only)
    assert kit_only["exig"] == ["tva_la_livrare"] and "tva_exig_livrare" in core_only["exig"]
    assert kit_only["impozit"] == ["micro_3", "norma_venit"] and kit_only["forma"] == ["ii"]
