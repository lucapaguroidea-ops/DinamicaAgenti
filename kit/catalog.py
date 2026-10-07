"""The catalog loader: YAML rows in ``catalog/``, checked against closed row schemas.

A catalog file::

    catalog: Articol          # one of CATALOGS
    file_schema: 1
    mode: base | additive     # optional, default base
    rows: [...]

Fail closed (P10): an unknown catalog, top-level key, field, axis, axis value or referenced id
is an error, and so is a repeated YAML key, a repeated id or a ``.yml`` file. Every problem of
a load is reported at once. Scalars are read as strings (YAML's own typing is off), so money,
dates and account codes stay strings; integers and booleans are converted where a field says so.

An articol names its path and its gate (P2): a row with no ``procedure`` is a comment, one with
no ``gate`` a silent post; a document path ends in a SAGA mouth and no other path names one.

Rows enter as ``draft``; ``active`` needs the owner's dated approval on the row (P14).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)

FILE_SCHEMA = "1"


class CatalogError(Exception):
    """One or more problems in the catalog; ``problems`` lists them all."""

    def __init__(self, problems: Iterable[str]):
        self.problems = list(problems)
        super().__init__("\n".join(self.problems))


# ----- value types -----

Slug = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$")]
Account = Annotated[str, StringConstraints(pattern=r"^[1-9]\d{2,3}$")]
Money = Annotated[str, StringConstraints(pattern=r"^-?\d+\.\d{2}$")]
Approval = Annotated[str, StringConstraints(pattern=r"^owner, \d{4}-\d{2}-\d{2}$")]
Procedure = Literal["sorting", "document", "reconcile", "close"]
Axes = dict[Slug, list[Slug]]


def _date(v: str | None) -> str | None:
    if v is not None:
        dt.date.fromisoformat(v)  # YYYY-MM-DD and a real day
        if len(v) != 10:
            raise ValueError("a date is YYYY-MM-DD")
    return v


class Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Row(Closed):
    id: Slug
    status: Literal["draft", "active", "deprecated"]
    schema_version: int = 1
    approved: Approval | None = None
    note: str | None = None

    @model_validator(mode="after")
    def _active_needs_approval(self):
        if self.status == "active" and self.approved is None:
            raise ValueError(
                "status active only with the owner's approval: approved: 'owner, YYYY-MM-DD' (P14)"
            )
        return self


class Gate(Closed):
    policy: Literal["always", "first_n", "never_if_risk_low"]
    first_n: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _n(self):
        if (self.policy == "first_n") != (self.first_n is not None):
            raise ValueError("gate first_n is set exactly when policy is first_n")
        return self


# ----- row models, one per catalog -----


class AxisRow(Row):
    values: list[Slug] = Field(min_length=1)


class Split(Closed):
    question: Slug
    children: list[Slug] = Field(min_length=1)


class SourceDocRow(Row):
    posting_eligible: bool
    primary_kinds: list[
        Literal[
            "ubl_spv",
            "xml",
            "pdf",
            "jpeg",
            "png",
            "mt940",
            "sta",
            "csv",
            "xlsx",
            "xls",
            "eml",
            "msg",
        ]
    ] = []
    emit_on_incomplete: bool = False
    needs_client_on_doc: bool = False
    needs_counterparty_cui: bool = False
    bon_cui_fork: bool = False
    fiscal_class: Slug | None = None
    our_role_default: Literal["inbound", "outbound", "n_a"] | None = None
    split: Split | None = None


class JobKindRow(Row):
    source_docs: list[Slug] = Field(min_length=1)
    articole: list[Slug] = Field(min_length=1)
    storno: bool = False


class Filters(Closed):
    fiscal_class: Slug | None = None
    our_role: Literal["inbound", "outbound"] | None = None
    is_storno: bool | None = None
    our_cui_on_doc: bool | None = None  # a fiscal receipt: is the client's CUI on it


class ArticolReconcile(Closed):
    match_keys: list[Literal["number", "date", "gross"]] = Field(min_length=1)
    expect_accounts: list[Account] = []
    tolerance: Money


class ArticolRow(Row):
    procedure: Procedure
    gate: Gate
    filters: Filters = Filters()
    require: Axes = {}
    forbid: Axes = {}
    mouths: list[Slug] = []
    reconcile: ArticolReconcile | None = None
    valid_from: str | None = None
    valid_to: str | None = None

    _check_dates = field_validator("valid_from", "valid_to")(_date)

    @model_validator(mode="before")
    @classmethod
    def _path_and_gate(cls, data: Any):
        if isinstance(data, dict):
            missing = []
            if not data.get("procedure"):
                missing.append("names no path: an articol without a procedure is a comment (P2)")
            if not data.get("gate"):
                missing.append("has no gate: a path without a gate is a silent post (P2)")
            if missing:
                raise ValueError("; ".join(missing))
        return data

    @model_validator(mode="after")
    def _mouths(self):
        if self.procedure == "document" and not self.mouths:
            raise ValueError("a document path names no mouth: it must end in SAGA (P2)")
        if self.procedure != "document" and self.mouths:
            raise ValueError("only a document path names a mouth")
        return self


class MouthRow(Row):
    saga_path: Literal["import_xml", "import_dbf"]
    doc_class: Slug | None = None
    validare: Literal["person", "n_a"]  # never an agent (P5)
    backup: Literal["none", "before_batch", "before_each"]
    gate: Gate
    fixture: str | None = None


class ReconcileProfileRow(Row):
    stage: Literal["pre", "post"]
    match_keys: list[Literal["number", "date", "gross"]] = Field(min_length=1)
    number_levels: list[Literal["exact", "alnum", "digits_core"]] = []
    tolerance: Money
    sink_source: Literal["registru_jurnal"] = "registru_jurnal"
    require_all_accounts: bool = False
    fallback_accounts: list[Account] = []
    review: bool = False


class CloseKindRow(Row):
    require: Axes = {}
    forbid: Axes = {}
    recon_profile: Slug
    watched_extra: list[Account] = []
    v4: bool = True


class ControlRow(Row):
    layer: Literal["prefile", "close"]
    severity: Literal["blocking", "advisory"]
    rule: str = Field(min_length=1)
    watched: list[Account] = []
    epsilon: Money | None = None
    require: Axes = {}


class FilingRow(Row):
    form: Literal[
        "D300", "D301", "D390", "D394", "D100", "D101", "D106", "D112", "D205", "D406", "SF", "OSS"
    ]
    require: Axes = {}
    forbid: Axes = {}
    books_gate: list[Slug] = []
    closer: Literal["receipt"] = "receipt"
    certainty: Literal["confirmed", "de_confirmat"] = "de_confirmat"


class QuestionKindRow(Row):
    actor: Literal["accountant", "saga_agent"]
    procedure: Procedure
    answer: dict[Slug, str] = Field(min_length=1)


class ModelRoleRow(Row):
    system: Literal["one", "two", "reader"]
    hank: str = Field(min_length=1)
    codon: Slug
    model: str | None = None  # unset: the role refuses and a person is asked (P8)
    card: str | None = None


CATALOGS: dict[str, type[Row]] = {
    "Axis": AxisRow,
    "SourceDoc": SourceDocRow,
    "JobKind": JobKindRow,
    "Articol": ArticolRow,
    "Mouth": MouthRow,
    "ReconcileProfile": ReconcileProfileRow,
    "CloseKind": CloseKindRow,
    "Control": ControlRow,
    "Filing": FilingRow,
    "QuestionKind": QuestionKindRow,
    "ModelRole": ModelRoleRow,
}

# (catalog, field) → the catalog its ids must exist in
_REFS: dict[tuple[str, str], str] = {
    ("Articol", "mouths"): "Mouth",
    ("JobKind", "source_docs"): "SourceDoc",
    ("JobKind", "articole"): "Articol",
    ("SourceDoc", "split.question"): "QuestionKind",
    ("SourceDoc", "split.children"): "SourceDoc",
    ("CloseKind", "recon_profile"): "ReconcileProfile",
    ("Filing", "books_gate"): "Control",
}
_AXES_FIELDS = ("require", "forbid")


# ----- the catalog -----


@dataclass(frozen=True)
class Catalog:
    rows: dict[str, dict[str, Row]]

    def _kind(self, kind: str) -> dict[str, Row]:
        if kind not in self.rows:
            raise CatalogError([f"unknown catalog {kind!r}"])
        return self.rows[kind]

    def ids(self, kind: str) -> list[str]:
        return list(self._kind(kind))

    def get(self, kind: str, row_id: str) -> Any:
        rows = self._kind(kind)
        if row_id not in rows:
            raise CatalogError([f"unknown {kind} id {row_id!r}"])
        return rows[row_id]


class _Loader(yaml.BaseLoader):
    """Every scalar a string; a repeated key in a mapping is an error."""


def _mapping(loader: _Loader, node: yaml.MappingNode, deep: bool = False) -> dict:
    out: dict = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in out:
            mark = key_node.start_mark
            raise yaml.constructor.ConstructorError(
                None, None, f"repeated key {key!r} (line {mark.line + 1})", mark
            )
        out[key] = loader.construct_object(value_node, deep=deep)
    return out


_Loader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def _values(row: Row, dotted: str) -> list[str]:
    value: Any = row
    for part in dotted.split("."):
        value = getattr(value, part, None)
        if value is None:
            return []
    return [value] if isinstance(value, str) else list(value)


def load_catalog(root: Path) -> Catalog:
    """Load and check every catalog file under ``root``; raise CatalogError with all problems."""
    problems: list[str] = []
    base: dict[str, Path] = {}
    files: list[tuple[Path, str, str, list]] = []

    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root)
        if path.suffix == ".yml":
            problems.append(f"{rel}: catalog files end in .yaml")
            continue
        if path.suffix != ".yaml":
            continue
        try:
            doc = yaml.load(path.read_text(encoding="utf-8"), Loader=_Loader)
        except yaml.YAMLError as exc:
            problems.append(f"{rel}: {exc}")
            continue
        if not isinstance(doc, dict):
            problems.append(f"{rel}: a catalog file is a mapping")
            continue
        extra = set(doc) - {"catalog", "file_schema", "mode", "rows"}
        if extra:
            problems.append(f"{rel}: unknown top-level keys {sorted(extra)}")
        kind, mode = doc.get("catalog"), doc.get("mode", "base")
        if kind not in CATALOGS:
            problems.append(f"{rel}: unknown catalog {kind!r}")
            continue
        if doc.get("file_schema") != FILE_SCHEMA:
            problems.append(f"{rel}: file_schema must be {FILE_SCHEMA}")
        if mode not in ("base", "additive"):
            problems.append(f"{rel}: mode is base or additive")
            continue
        rows = doc.get("rows")
        if not isinstance(rows, list):
            problems.append(f"{rel}: rows is a list")
            continue
        if mode == "base":
            if kind in base:
                problems.append(f"{kind}: two base files, {base[kind]} and {rel}")
            base[kind] = rel
        files.append((rel, kind, mode, rows))

    catalog: dict[str, dict[str, Row]] = {kind: {} for kind in CATALOGS}
    for rel, kind, mode, rows in sorted(files, key=lambda f: (f[2] != "base", str(f[0]))):
        if mode == "additive" and kind not in base:
            problems.append(f"{rel}: additive rows for {kind}, which has no base file")
            continue
        for i, raw in enumerate(rows):
            label = raw.get("id", f"row {i + 1}") if isinstance(raw, dict) else f"row {i + 1}"
            try:
                row = CATALOGS[kind].model_validate(raw)
            except ValidationError as exc:
                for err in exc.errors():
                    where = ".".join(str(p) for p in err["loc"]) or "row"
                    problems.append(f"{rel}: {kind} {label!r}: {where}: {err['msg']}")
                continue
            if row.id in catalog[kind]:
                problems.append(f"{rel}: {kind} id {row.id!r} appears twice")
                continue
            catalog[kind][row.id] = row

    for job in catalog["JobKind"].values():
        for aid in job.articole:
            art = catalog["Articol"].get(aid)
            if art is not None and art.procedure != "document":
                problems.append(f"JobKind {job.id!r}: articol {aid!r} is not on the document path")

    axes = {a.id: set(a.values) for a in catalog["Axis"].values()}
    for kind, rows in catalog.items():
        for row in rows.values():
            for (ref_kind, field), target in _REFS.items():
                if ref_kind == kind:
                    for ref in _values(row, field):
                        if ref not in catalog[target]:
                            problems.append(
                                f"{kind} {row.id!r}: {field}: unknown {target} id {ref!r}"
                            )
            for field in _AXES_FIELDS:
                for axis, values in (getattr(row, field, None) or {}).items():
                    if axis not in axes:
                        problems.append(f"{kind} {row.id!r}: {field}: unknown axis {axis!r}")
                        continue
                    for v in values:
                        if v not in axes[axis]:
                            problems.append(
                                f"{kind} {row.id!r}: {field}: unknown value {v!r} of axis {axis!r}"
                            )

    if problems:
        raise CatalogError(problems)
    return Catalog(rows=catalog)
