"""The company in Paperclip: ``paperclip/company.yaml`` as API requests, and the HTTP client.

``plan_company`` turns the company file into the requests that create it (company, goal, labels,
agents and their hard-stop budgets, the Build project), in order; ``plan_client`` adds one
client (its project, budget and routines). A request names the ids it needs as ``{ref}`` and
records the id it gets back under its own ``ref``; ``apply`` resolves them and keeps a state
file, so a second run creates nothing it already created (P9). ``${VAR}`` values come from the
environment and a missing one refuses the whole plan before any request is sent (P10).

The client speaks Paperclip's REST API (``/api``, ``Authorization: Bearer``; R2). It is the only
code here that talks to the network; everything else is a pure function of files and facts.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import yaml

from kit.types import cui_is_valid, normalize_cui

_VAR = re.compile(r"\$\{([A-Z][A-Z0-9_]*)\}")
_REF = re.compile(r"\{([a-z][a-z0-9_:]*)\}")
RUNTIME = "paperclipai@2026.1012.0"


class SetupError(ValueError):
    """The company file or its environment is refused; nothing was sent."""


class PaperclipError(RuntimeError):
    def __init__(self, status: int, method: str, path: str, body: str):
        self.status = status
        super().__init__(f"{method} {path}: HTTP {status}: {body[:500]}")


# ----- the client -----


class Client(Protocol):
    def request(self, method: str, path: str, body: dict | None = None) -> Any: ...


class HttpClient:
    """Paperclip's REST API. 409 (another owns the task) and 422 (a refused transition) are
    errors, never retried here (R2)."""

    def __init__(self, base_url: str, api_key: str, timeout: float = 30):
        if not base_url or not api_key:
            raise SetupError("a Paperclip URL and API key are needed")
        self.base, self.key, self.timeout = base_url.rstrip("/"), api_key, timeout

    @classmethod
    def from_env(cls) -> HttpClient:
        return cls(os.environ.get("PAPERCLIP_API_URL", ""), os.environ.get("PAPERCLIP_API_KEY", ""))

    def request(self, method: str, path: str, body: dict | None = None) -> Any:
        if not path.startswith("/api/"):
            raise SetupError(f"{path}: every endpoint is under /api")
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self.key}")
        req.add_header("Accept", "application/json")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            raise PaperclipError(exc.code, method, path, body) from exc
        return json.loads(raw) if raw else None


# ----- the plan -----


@dataclass
class Request:
    ref: str | None  # the id this request creates is recorded under this name
    method: str
    path: str
    body: dict | None = None
    note: str = ""


@dataclass
class Plan:
    requests: list[Request] = field(default_factory=list)

    def add(self, ref, method, path, body=None, note=""):
        self.requests.append(Request(ref, method, path, body, note))


def load_company(path: Path, env: dict[str, str] | None = None) -> dict:
    """The company file with every ``${VAR}`` filled from ``env``; any missing one refuses."""
    env = dict(os.environ if env is None else env)
    raw = path.read_text(encoding="utf-8")
    missing = sorted({m for m in _VAR.findall(raw) if not env.get(m)})
    if missing:
        raise SetupError(f"set these first: {', '.join(missing)}")
    conf = yaml.safe_load(_VAR.sub(lambda m: env[m.group(1)], raw))
    extra = set(conf) - {"runtime", "company", "labels", "agents", "projects", "routines", "people"}
    if extra:
        raise SetupError(f"unknown keys in the company file: {sorted(extra)}")
    if conf.get("runtime") != RUNTIME:
        raise SetupError(f"the company file is written for {RUNTIME}, not {conf.get('runtime')}")
    for key, agent in conf["agents"].items():
        if agent["adapterType"] not in ("process", "http"):
            raise SetupError(f"agent {key}: the cabinet's agents are process or http adapters")
        if "model" in agent.get("adapterConfig", {}):
            raise SetupError(f"agent {key}: a model is pinned per role in the catalog, not here")
    return conf


def _budget(scope_type: str, scope_ref: str, cents: int) -> dict:
    return {
        "scopeType": scope_type,
        "scopeId": "{" + scope_ref + "}",
        "amount": int(cents),
        "windowKind": "calendar_month_utc",
        "hardStopEnabled": True,
    }


def plan_company(conf: dict) -> Plan:
    p = Plan()
    c = conf["company"]
    p.add("company", "POST", "/api/companies", {"name": c["name"], "description": c["description"]})
    p.add("goal", "POST", "/api/companies/{company}/goals", {"title": c["goal"]})
    for name, color in conf["labels"].items():
        p.add(
            f"label:{name}",
            "POST",
            "/api/companies/{company}/labels",
            {"name": name, "color": color},
        )
    for key, a in conf["agents"].items():
        body = {
            "name": a["name"],
            "title": a.get("title"),
            "role": a["role"],
            "capabilities": a.get("capabilities"),
            "adapterType": a["adapterType"],
            "adapterConfig": a["adapterConfig"],
            "runtimeConfig": {"heartbeat": {"enabled": False, "wakeOnDemand": True}},
            "budgetMonthlyCents": int(a["monthly_cents"]),
            "metadata": {"kit_agent": key},
        }
        p.add(f"agent:{key}", "POST", "/api/companies/{company}/agents", body)
        p.add(
            None,
            "POST",
            "/api/companies/{company}/budgets/policies",
            _budget("agent", f"agent:{key}", a["monthly_cents"]),
            f"hard stop for {key}",
        )
        if a.get("paused"):
            p.add(
                None,
                "POST",
                "/api/agents/{agent:" + key + "}/pause",
                None,
                f"{key} is a person until built",
            )
    p.add(
        None,
        "POST",
        "/api/companies/{company}/budgets/policies",
        _budget("company", "company", c["monthly_cents"]),
        "the company's hard stop",
    )
    b = conf["projects"]["build"]
    p.add(
        "project:build",
        "POST",
        "/api/companies/{company}/projects",
        {"name": b["name"], "description": b["description"], "idempotencyKey": "project:build"},
    )
    return p


def plan_client(conf: dict, cui: str, monthly_cents: int = 0) -> Plan:
    if not cui_is_valid(cui):
        raise SetupError(f"{cui!r} fails the CUI check digit")
    cui = normalize_cui(cui)
    p = Plan()
    t = conf["projects"]["client"]
    ref = f"project:{cui}"
    p.add(
        ref,
        "POST",
        "/api/companies/{company}/projects",
        {
            "name": t["name"].format(cui=cui),
            "description": t["description"].format(cui=cui),
            "idempotencyKey": ref,
        },
    )
    p.add(
        None,
        "POST",
        "/api/companies/{company}/budgets/policies",
        _budget("project", ref, monthly_cents),
        f"hard stop for client {cui}",
    )
    for key, r in conf["routines"].items():
        rref = f"routine:{cui}:{key}"
        p.add(
            rref,
            "POST",
            "/api/companies/{company}/routines",
            {
                "title": r["title"].format(cui=cui),
                "projectId": "{" + ref + "}",
                "assigneeAgentId": "{agent:" + r["assignee"] + "}",
                "concurrencyPolicy": "coalesce_if_active",
                "catchUpPolicy": "skip_missed",
            },
        )
        p.add(
            f"trigger:{cui}:{key}",
            "POST",
            "/api/routines/{" + rref + "}/triggers",
            dict(r["trigger"]),
        )
    return p


def _resolve(value: Any, ids: dict[str, str]) -> Any:
    if isinstance(value, str):
        whole = _REF.fullmatch(value)
        if whole:
            if whole.group(1) not in ids:
                raise SetupError(f"no id yet for {whole.group(1)!r}")
            return ids[whole.group(1)]
        return _REF.sub(lambda m: _resolve("{" + m.group(1) + "}", ids), value)
    if isinstance(value, dict):
        return {k: _resolve(v, ids) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve(v, ids) for v in value]
    return value


def _created_id(r: Request, out: Any) -> str:
    """The id of what a request created: at the top, or under the one object it returns
    (``{"agent": …}``, ``{"trigger": …, "secretMaterial": …}``; R2, seen on a live server)."""
    if isinstance(out, dict):
        if isinstance(out.get("id"), str):
            return out["id"]
        for key in ("agent", "trigger", "routine", "project", "company"):
            inner = out.get(key)
            if isinstance(inner, dict) and isinstance(inner.get("id"), str):
                return inner["id"]
    raise PaperclipError(0, r.method, r.path, "no id in the answer")


def _keep_secret(state_path: Path, ref: str, secret: dict) -> None:
    """A webhook's signing secret is shown once: kept in a file only its owner reads, next to
    the state file, never printed or written to the state (D4 says where it goes next)."""
    path = state_path.with_name(state_path.stem + ".secrets.json")
    kept = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    kept[ref] = secret
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(kept, f, indent=2, sort_keys=True)
    os.chmod(path, 0o600)


def load_state(state_path: Path) -> dict[str, str]:
    """The ids the set-up recorded: ``{ref: Paperclip id}``."""
    if not state_path.exists():
        return {}
    return dict(json.loads(state_path.read_text(encoding="utf-8")).get("ids", {}))


def _write_state(state_path: Path, ids: dict, sent: set, inflight: str | None) -> None:
    body = {"ids": ids, "sent": sorted(sent)}
    if inflight:
        body["inflight"] = inflight
    state_path.write_text(json.dumps(body, indent=2, sort_keys=True), encoding="utf-8")


def apply(plan: Plan, client: Client, state_path: Path) -> dict[str, str]:
    """Send the plan's requests in order. A request whose ref is already in the state file is
    skipped, and so is a request with no ref that was already sent: a second run sends nothing
    twice. Each request is marked in flight before it is sent; a run that stopped during one
    (the server may have acted) refuses to resend it until a person has looked (P9)."""
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    if state.get("inflight"):
        raise SetupError(
            f"the last run stopped during {state['inflight']}: check Paperclip for it, record its"
            f" id in {state_path} (or drop 'inflight' if it is not there), then run again"
        )
    ids: dict[str, str] = dict(state.get("ids", {}))
    sent: set[str] = set(state.get("sent", []))
    for r in plan.requests:
        key = hashlib.sha256(
            json.dumps([r.method, r.path, r.body], sort_keys=True).encode()
        ).hexdigest()[:24]
        if (r.ref and r.ref in ids) or (not r.ref and key in sent):
            continue
        label = r.ref or f"{r.method} {r.path} ({r.note or key})"
        _write_state(state_path, ids, sent, label)
        try:
            out = client.request(r.method, _resolve(r.path, ids), _resolve(r.body, ids))
        except PaperclipError as exc:
            if 400 <= exc.status < 500:  # refused: the server did nothing
                _write_state(state_path, ids, sent, None)
            raise
        if r.ref:
            ids[r.ref] = _created_id(r, out)
            secret = ((out or {}).get("secretMaterial") or {}) if isinstance(out, dict) else {}
            if secret:
                _keep_secret(state_path, r.ref, secret)
                ids[f"{r.ref}:url"] = secret.get("webhookUrl", "")
        else:
            sent.add(key)
        _write_state(state_path, ids, sent, None)
    return ids
