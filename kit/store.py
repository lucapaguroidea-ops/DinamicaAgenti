"""The dossier store: one client's facts in ``dossiers/{cui}/store.db`` (SQLite, D1).

Written only by the gate kit (ARCHITECTURE §7). The client boundary is the folder: the only way
in is ``open_dossier``, which checks the CUI and opens that client's file, and the file itself
refuses a row that carries another client's CUI (P13). Every side effect sits behind a unique
key, so a second attempt is a no-op that returns the first result (P9). Event and answer logs
are append-only (P12). Nothing here is a book: no journal, no accounts, no balances (P4).
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kit.types import cui_is_valid, is_period, normalize_cui

SUBDIRS = ("sources", "extracts", "outbox", "eye", "runs")
STATUSES = (
    "ingested",
    "extracted",
    "bound",
    "reconcile_pre",
    "approved",
    "packaged",
    "wait_validare",
    "acked",
    "already_in_sink",
    "needs_human",
    "reopened",
    "rejected",
    "failed",
)
_FORWARD = {
    "ingested": {"extracted", "bound"},
    "extracted": {"bound"},
    "bound": {"reconcile_pre"},
    "reconcile_pre": {"approved", "already_in_sink"},
    "approved": {"packaged"},
    "packaged": {"wait_validare"},
    "wait_validare": {"acked", "reopened"},
    "acked": {"reopened"},
    "reopened": {"packaged"},
    # a person settles what was held: the Job goes back to the step it stopped before
    "needs_human": {"bound", "reconcile_pre", "approved", "already_in_sink", "acked", "reopened"},
}
_TERMINAL = {"already_in_sink", "rejected", "failed"}
_ANY = {"rejected", "failed", "needs_human"}

_TABLES = {
    "jobs": """job_id TEXT PRIMARY KEY, client_cui TEXT NOT NULL, source_hash TEXT NOT NULL,
        job_kind TEXT NOT NULL, source_doc_id TEXT NOT NULL, period TEXT NOT NULL,
        status TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE (client_cui, source_hash)""",
    "job_events": """seq INTEGER PRIMARY KEY AUTOINCREMENT, client_cui TEXT NOT NULL,
        job_id TEXT NOT NULL REFERENCES jobs(job_id), status TEXT NOT NULL, at TEXT NOT NULL""",
    "packages": """export_key TEXT PRIMARY KEY, client_cui TEXT NOT NULL,
        job_id TEXT NOT NULL REFERENCES jobs(job_id), module_id TEXT NOT NULL,
        schema_version TEXT NOT NULL, period TEXT NOT NULL, path TEXT NOT NULL,
        sha256 TEXT NOT NULL, at TEXT NOT NULL""",
    "verdicts": """client_cui TEXT NOT NULL, job_id TEXT NOT NULL REFERENCES jobs(job_id),
        stage TEXT NOT NULL CHECK (stage IN ('pre', 'post')), snapshot_id TEXT NOT NULL,
        verdict TEXT NOT NULL, body TEXT NOT NULL, at TEXT NOT NULL,
        PRIMARY KEY (job_id, stage, snapshot_id)""",
    "model_answers": """client_cui TEXT NOT NULL, role_id TEXT NOT NULL, input_hash TEXT NOT NULL,
        card_hash TEXT NOT NULL, body TEXT NOT NULL, at TEXT NOT NULL,
        PRIMARY KEY (role_id, input_hash, card_hash)""",
    "answers": """seq INTEGER PRIMARY KEY AUTOINCREMENT, client_cui TEXT NOT NULL,
        issue TEXT NOT NULL, kind TEXT NOT NULL, question_hash TEXT NOT NULL,
        answer TEXT NOT NULL, proposed TEXT, operator TEXT NOT NULL, at TEXT NOT NULL,
        outcome TEXT NOT NULL CHECK (outcome IN ('accepted', 'asked_again', 'no_question'))""",
    "close_locks": """period TEXT PRIMARY KEY, client_cui TEXT NOT NULL,
        expected_set_hash TEXT NOT NULL, at TEXT NOT NULL""",
    "control_runs": """client_cui TEXT NOT NULL, period TEXT NOT NULL, control_id TEXT NOT NULL,
        snapshot_id TEXT NOT NULL, status TEXT NOT NULL CHECK (status IN ('PASS', 'FAIL', 'INFO')),
        body TEXT NOT NULL, at TEXT NOT NULL, PRIMARY KEY (period, control_id, snapshot_id)""",
    "filing_items": """client_cui TEXT NOT NULL, period TEXT NOT NULL, filing_id TEXT NOT NULL,
        state TEXT NOT NULL CHECK (state IN ('open', 'filed')), receipt_key TEXT,
        submitted_by TEXT, at TEXT NOT NULL, PRIMARY KEY (period, filing_id),
        CHECK (state = 'open' OR (receipt_key IS NOT NULL AND receipt_key != ''))""",
    "backup_labels": """label TEXT PRIMARY KEY, client_cui TEXT NOT NULL, at TEXT NOT NULL""",
}
_APPEND_ONLY = ("job_events", "answers")


class StoreError(ValueError):
    """The write or read is refused; nothing was changed."""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def _schema() -> str:
    parts = ["CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);"]
    for name, cols in _TABLES.items():
        parts.append(f"CREATE TABLE IF NOT EXISTS {name} ({cols});")
        parts.append(
            f"CREATE TRIGGER IF NOT EXISTS {name}_one_client BEFORE INSERT ON {name} "
            "WHEN NEW.client_cui IS NOT (SELECT value FROM meta WHERE key = 'client_cui') "
            "BEGIN SELECT RAISE(ABORT, 'a row of another client (P13)'); END;"
        )
    for name in _APPEND_ONLY:
        for op in ("UPDATE", "DELETE"):
            parts.append(
                f"CREATE TRIGGER IF NOT EXISTS {name}_no_{op.lower()} BEFORE {op} ON {name} "
                f"BEGIN SELECT RAISE(ABORT, '{name} is append-only'); END;"
            )
    parts.append(
        "CREATE UNIQUE INDEX IF NOT EXISTS answers_once ON answers (issue, question_hash) "
        "WHERE outcome = 'accepted';"
    )
    return "\n".join(parts)


@dataclass(frozen=True)
class Job:
    job_id: str
    client_cui: str
    source_hash: str
    job_kind: str
    source_doc_id: str
    period: str
    status: str


@dataclass(frozen=True)
class Package:
    export_key: str
    job_id: str
    module_id: str
    path: str  # relative to the dossier folder
    sha256: str


@dataclass(frozen=True)
class Verdict:
    job_id: str
    stage: str
    snapshot_id: str
    verdict: str
    body: dict


def job_id_for(client_cui: str, source_hash: str) -> str:
    """The Job's id follows from its unique key, so a retry names the same Job."""
    return "j_" + hashlib.sha256(f"{client_cui}:{source_hash}".encode()).hexdigest()[:20]


def open_dossier(root: Path, cui: str) -> Dossier:
    """Open (or create) the dossier of ``cui`` under ``root``; the only way into a store."""
    if not cui_is_valid(cui):
        raise StoreError(f"{cui!r} is not a valid CUI")
    cui = normalize_cui(cui)
    folder = Path(root) / cui
    for sub in SUBDIRS:
        (folder / sub).mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(folder / "store.db", isolation_level=None)
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript(_schema())
    db.execute("INSERT OR IGNORE INTO meta (key, value) VALUES ('client_cui', ?)", (cui,))
    owner = db.execute("SELECT value FROM meta WHERE key = 'client_cui'").fetchone()[0]
    if owner != cui:
        db.close()
        raise StoreError(f"this store.db belongs to {owner}, not {cui} (P13)")
    return Dossier(folder=folder, client_cui=cui, db=db)


@dataclass
class Dossier:
    folder: Path
    client_cui: str
    db: sqlite3.Connection

    def _own(self, cui: str) -> None:
        if normalize_cui(cui) != self.client_cui:
            raise StoreError(f"a record of {cui} in the dossier of {self.client_cui} (P13)")

    # ----- jobs -----

    def insert_job(
        self, client_cui: str, source_hash: str, job_kind: str, source_doc_id: str, period: str
    ) -> tuple[Job, bool]:
        """One Job per (client, source hash): a second insert returns the first, created=False."""
        self._own(client_cui)
        if not is_period(period):
            raise StoreError(f"{period!r} is not a period YYYY-MM")
        jid, at = job_id_for(self.client_cui, source_hash), _now()
        with self.db:
            cur = self.db.execute(
                "INSERT INTO jobs (job_id, client_cui, source_hash, job_kind, source_doc_id,"
                " period, status, created_at) VALUES (?, ?, ?, ?, ?, ?, 'ingested', ?)"
                " ON CONFLICT (client_cui, source_hash) DO NOTHING",
                (jid, self.client_cui, source_hash, job_kind, source_doc_id, period, at),
            )
            created = cur.rowcount == 1
            if created:
                self._event(jid, "ingested")
        return self.job(jid), created

    def job(self, job_id: str) -> Job:
        row = self.db.execute(
            "SELECT job_id, client_cui, source_hash, job_kind, source_doc_id, period, status"
            " FROM jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        if row is None:
            raise StoreError(f"unknown job {job_id!r}")
        return Job(*row)

    def jobs(self, period: str) -> list[Job]:
        rows = self.db.execute(
            "SELECT job_id, client_cui, source_hash, job_kind, source_doc_id, period, status"
            " FROM jobs WHERE period = ? ORDER BY created_at, job_id",
            (period,),
        )
        return [Job(*r) for r in rows]

    def set_status(self, job_id: str, status: str) -> Job:
        """Move a Job forward (ARCHITECTURE §4.2); the same status again is a no-op."""
        if status not in STATUSES:
            raise StoreError(f"unknown status {status!r}")
        old = self.job(job_id).status
        if status == old:
            return self.job(job_id)
        allowed = set() if old in _TERMINAL else _FORWARD.get(old, set()) | _ANY
        if status not in allowed:
            raise StoreError(f"{old} → {status} is not a forward step")
        with self.db:
            self.db.execute("UPDATE jobs SET status = ? WHERE job_id = ?", (status, job_id))
            self._event(job_id, status)
        return self.job(job_id)

    def _event(self, job_id: str, status: str) -> None:
        self.db.execute(
            "INSERT INTO job_events (client_cui, job_id, status, at) VALUES (?, ?, ?, ?)",
            (self.client_cui, job_id, status, _now()),
        )

    def events(self, job_id: str) -> list[dict]:
        rows = self.db.execute(
            "SELECT status, at FROM job_events WHERE job_id = ? ORDER BY seq", (job_id,)
        )
        return [{"status": s, "at": at} for s, at in rows]

    # ----- packages -----

    def write_package(
        self,
        export_key: str,
        job_id: str,
        module_id: str,
        schema_version: str,
        period: str,
        filename: str,
        data: bytes,
    ) -> Package:
        """Write a package to the outbox once; the same content again is a no-op."""
        digest = hashlib.sha256(data).hexdigest()
        row = self.db.execute(
            "SELECT export_key, job_id, module_id, path, sha256 FROM packages WHERE export_key = ?",
            (export_key,),
        ).fetchone()
        if row is not None:
            if row[4] != digest:
                raise StoreError(f"{export_key} already written with other content")
            return Package(*row)
        if "/" in filename or "\\" in filename or filename in ("", ".", ".."):
            raise StoreError(f"unsafe file name {filename!r}")
        self.job(job_id)
        rel = Path("outbox") / period / job_id / filename
        target = self.folder / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, target)
        with self.db:
            self.db.execute(
                "INSERT INTO packages (export_key, client_cui, job_id, module_id, schema_version,"
                " period, path, sha256, at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    export_key,
                    self.client_cui,
                    job_id,
                    module_id,
                    schema_version,
                    period,
                    rel.as_posix(),
                    digest,
                    _now(),
                ),
            )
        return Package(export_key, job_id, module_id, rel.as_posix(), digest)

    # ----- verdicts and model answers -----

    def put_verdict(
        self, job_id: str, stage: str, snapshot_id: str, verdict: str, body: dict
    ) -> Verdict:
        """Stored once per (job, stage, books snapshot); a replay returns the first verdict."""
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO verdicts (client_cui, job_id, stage, snapshot_id, verdict,"
                " body, at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (self.client_cui, job_id, stage, snapshot_id, verdict, json.dumps(body), _now()),
            )
        v, b = self.db.execute(
            "SELECT verdict, body FROM verdicts WHERE job_id = ? AND stage = ? AND snapshot_id = ?",
            (job_id, stage, snapshot_id),
        ).fetchone()
        return Verdict(job_id, stage, snapshot_id, v, json.loads(b))

    def put_model_answer(self, role_id: str, input_hash: str, card_hash: str, body: dict) -> None:
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO model_answers (client_cui, role_id, input_hash, card_hash,"
                " body, at) VALUES (?, ?, ?, ?, ?, ?)",
                (self.client_cui, role_id, input_hash, card_hash, json.dumps(body), _now()),
            )

    def model_answer(self, role_id: str, input_hash: str, card_hash: str) -> dict | None:
        row = self.db.execute(
            "SELECT body FROM model_answers WHERE role_id = ? AND input_hash = ? AND card_hash = ?",
            (role_id, input_hash, card_hash),
        ).fetchone()
        return json.loads(row[0]) if row else None

    # ----- answers -----

    def record_answer(
        self,
        issue: str,
        kind: str,
        question_hash: str,
        answer: Any,
        proposed: Any,
        outcome: str,
        operator: str,
    ) -> None:
        """Append to the answer log (P12). One accepted answer per (issue, question): the same
        answer again is a no-op; a different one is refused."""
        body = json.dumps(answer, sort_keys=True)
        if outcome == "accepted":
            row = self.db.execute(
                "SELECT answer FROM answers WHERE issue = ? AND question_hash = ?"
                " AND outcome = 'accepted'",
                (issue, question_hash),
            ).fetchone()
            if row is not None:
                if row[0] == body:
                    return
                raise StoreError(f"{issue}: this question is already answered")
        with self.db:
            self.db.execute(
                "INSERT INTO answers (client_cui, issue, kind, question_hash, answer, proposed,"
                " outcome, operator, at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    self.client_cui,
                    issue,
                    kind,
                    question_hash,
                    body,
                    None if proposed is None else json.dumps(proposed, sort_keys=True),
                    outcome,
                    operator,
                    _now(),
                ),
            )

    def answers(self, issue: str) -> list[dict]:
        rows = self.db.execute(
            "SELECT kind, question_hash, answer, proposed, outcome, operator, at FROM answers"
            " WHERE issue = ? ORDER BY seq",
            (issue,),
        )
        keys = ("kind", "question_hash", "answer", "proposed", "outcome", "operator", "at")
        out = []
        for r in rows:
            d = dict(zip(keys, r, strict=True))
            d["answer"] = json.loads(d["answer"])
            d["proposed"] = None if d["proposed"] is None else json.loads(d["proposed"])
            out.append(d)
        return out

    # ----- the month -----

    def lock_close(self, period: str, expected_set_hash: str) -> bool:
        """Lock the month's expected set once. False = a different set: a lock mismatch."""
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO close_locks (period, client_cui, expected_set_hash, at)"
                " VALUES (?, ?, ?, ?)",
                (period, self.client_cui, expected_set_hash, _now()),
            )
        held = self.db.execute(
            "SELECT expected_set_hash FROM close_locks WHERE period = ?", (period,)
        ).fetchone()[0]
        return held == expected_set_hash

    def release_close(self, period: str) -> None:
        """reopen: the next close run locks the month afresh."""
        with self.db:
            self.db.execute("DELETE FROM close_locks WHERE period = ?", (period,))

    def open_filing(self, period: str, filing_id: str) -> None:
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO filing_items (client_cui, period, filing_id, state, at)"
                " VALUES (?, ?, ?, 'open', ?)",
                (self.client_cui, period, filing_id, _now()),
            )

    def file_filing(self, period: str, filing_id: str, receipt_key: str, submitted_by: str) -> None:
        """A filing closes only on its receipt, never by date."""
        if not receipt_key or not submitted_by:
            raise StoreError("a filing closes only on its receipt, with who submitted it")
        if self.filing(period, filing_id) is None:
            raise StoreError(f"no open filing {filing_id} for {period}")
        with self.db:
            self.db.execute(
                "UPDATE filing_items SET state = 'filed', receipt_key = ?, submitted_by = ?, at = ?"
                " WHERE period = ? AND filing_id = ?",
                (receipt_key, submitted_by, _now(), period, filing_id),
            )

    def filing(self, period: str, filing_id: str) -> dict | None:
        row = self.db.execute(
            "SELECT state, receipt_key, submitted_by FROM filing_items"
            " WHERE period = ? AND filing_id = ?",
            (period, filing_id),
        ).fetchone()
        return (
            None
            if row is None
            else dict(zip(("state", "receipt_key", "submitted_by"), row, strict=True))
        )

    def period_filed(self, period: str) -> bool:
        """A period with a filing receipt gets no new package."""
        return (
            self.db.execute(
                "SELECT 1 FROM filing_items WHERE period = ? AND state = 'filed' LIMIT 1", (period,)
            ).fetchone()
            is not None
        )

    def record_backup(self, label: str) -> None:
        """A backup label ``{cui}:{folder}:{utc}`` of this client only."""
        parts = label.split(":", 2)
        if len(parts) != 3 or not all(parts):
            raise StoreError(f"{label!r} is not a label {{cui}}:{{folder}}:{{utc}}")
        if normalize_cui(parts[0]) != self.client_cui:
            raise StoreError(f"a backup label of another client: {label!r} (P13)")
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO backup_labels (label, client_cui, at) VALUES (?, ?, ?)",
                (label, self.client_cui, _now()),
            )
