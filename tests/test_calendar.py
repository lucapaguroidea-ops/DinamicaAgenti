"""WP-21: the calendar in the firm. A routine opens each client's ``calendar:{cui}:{period}``
issue; the Dispatcher asks the pinned core's calendar and records every owed filing as dated,
refused or later, with its reason; a refusal or a register that is not fresh holds the client's
calendar for a person, with the reasons (P10).

No legal value is written here. The real core catalog is read at the pinned commit from the
checkout ``uv sync`` made of it; it pins no non-working year and leaves the freshness window
unset, so every owed filing is refused and the calendar is held. The dated path runs on that
catalog with an **invented** window and **invented** non-working years (labelled synthetic,
tests only), as PoartaContabila's own calendar tests do. Firms are the core's synthetic ones.
"""

from __future__ import annotations

import copy
import json
import subprocess
from datetime import date, timedelta
from pathlib import Path

import pytest
from fake_paperclip import Fake
from poarta_contabila import core

import kit.calendar as kcal
from kit.catalog import load_catalog
from kit.dispatch import Company, dispatch
from kit.paperclip import load_company, plan_client, plan_company
from kit.route import CalendarFacts, route_calendar
from kit.store import open_dossier
from kit.types import cui_is_valid

ROOT = Path(__file__).resolve().parents[1]
FIRM = core.synthetic.FIRMS["platitor"]
CUI = FIRM.cui
PERIOD = "2026-06"
ISSUE = f"calendar:{CUI}:{PERIOD}"
ENV = {
    "KIT_HOME": "/srv/kit",
    "DOSSIERS": "/srv/dossiers",
    "SAGA_AGENT_URL": "https://saga.example.invalid/hook",
    "ACCOUNTANT_USER_ID": "user-acc",
}
# Invented for the tests (synthetic): the owner sets the real window; no year is pinned.
WINDOW = 90
FREQ = {"tva_period": "lunar", "d100_period": "trimestrial", "d112_period": "lunar"}


def _pinned_checkout() -> Path:
    """The core's catalog at the pinned commit: the git checkout ``uv sync`` made of the pin."""
    commit = kcal.pinned_commit()
    cache = subprocess.run(["uv", "cache", "dir"], capture_output=True, text=True, check=True)
    for path in sorted(Path(cache.stdout.strip()).glob(f"git-v0/checkouts/*/{commit[:7]}")):
        if kcal._head(path) == commit and (path / "catalog").is_dir():
            return path / "catalog"
    pytest.fail(f"no checkout of the pinned core {commit[:7]} in uv's cache: run uv sync")


@pytest.fixture(scope="module")
def real_dir() -> Path:
    return _pinned_checkout()


@pytest.fixture(scope="module")
def real(real_dir):
    return kcal.core_catalog({kcal.CATALOG_ENV: str(real_dir)})


@pytest.fixture(scope="module")
def cat():
    return load_catalog(ROOT / "catalog")


def invented(real, window: int | None = WINDOW, years=(2026, 2027)):
    """The real catalog with an invented freshness window and invented non-working years."""
    other = copy.deepcopy(real)
    other.docs["ArticoleTerms"]["register"]["max_age_days"] = window
    other.docs["ArticoleNonWorking"]["years"] = [
        {
            "year_id": f"synthetic_{y}",
            "year": y,
            "weekly_rest": ["saturday", "sunday"],
            "days": [],
            "provenance": {"source": "synthetic test year (invented)", "certainty": "de_confirmat"},
        }
        for y in years
    ]
    return other


def verified(real) -> date:
    return date.fromisoformat(real.docs["ArticoleTerms"]["register"]["verified_at"])


def company() -> Company:
    ids = {
        "company": "co-1",
        f"project:{CUI}": "prj-1",
        "agent:dispatcher": "agt-d",
        "label:calendar": "lbl-calendar",
    }
    return Company(ids, "user-acc")


@pytest.fixture
def firm(tmp_path):
    d = open_dossier(tmp_path, CUI)
    d.set_codit(PERIOD, {**FIRM.axes, **FREQ})
    return d


def on(monkeypatch, day: date, catalog=None) -> None:
    monkeypatch.setattr(kcal, "today", lambda: day)
    if catalog is not None:
        monkeypatch.setattr(kcal, "core_catalog", lambda: catalog)


def owed(real) -> list[str]:
    return sorted(r["filing_id"] for r in core.due_filings(real, {**FIRM.axes, **FREQ}))


def test_the_firms_are_synthetic_and_their_cuis_pass_the_check_digit():
    assert all(cui_is_valid(f.cui) for f in core.synthetic.FIRMS.values())


# ----- the routine -----


def test_each_client_gets_the_calendar_routine_and_the_company_its_label():
    conf = load_company(ROOT / "paperclip" / "company.yaml", env=ENV)
    labels = [r.body["name"] for r in plan_company(conf).requests if r.path.endswith("/labels")]
    assert "calendar" in labels
    plan = plan_client(conf, CUI)
    routine = next(r for r in plan.requests if r.ref == f"routine:{CUI}:month_calendar")
    assert routine.body["title"].startswith(f"calendar:{CUI}:")
    assert routine.body["assigneeAgentId"] == "{agent:dispatcher}"
    trigger = next(r for r in plan.requests if r.ref == f"trigger:{CUI}:month_calendar")
    assert trigger.body["kind"] == "schedule"


# ----- the core's catalog, read at the pin only -----


@pytest.mark.law("P10")
def test_no_core_catalog_holds_the_client_with_the_reason(cat, firm, monkeypatch):
    monkeypatch.delenv(kcal.CATALOG_ENV, raising=False)
    on(monkeypatch, date(2026, 7, 1))
    pc = Fake()
    tick = dispatch(cat, ROOT, firm, ISSUE, pc, company())
    assert tick.steps == ["kit:obligations"]
    assert tick.ended.startswith("hold: kit step obligations: the pinned core ships no catalog")
    pid = firm.paperclip_id(ISSUE)
    assert pc.issues[pid]["assigneeUserId"] == "user-acc"
    assert pc.issues[pid]["title"] == f"{ISSUE} [{CUI}]"
    assert kcal.CATALOG_ENV in pc.comments[pid][-1]


@pytest.mark.law("P10")
def test_a_catalog_at_another_commit_is_refused(tmp_path):
    with pytest.raises(kcal.CalendarUnavailable, match="not the pinned core's catalog"):
        kcal.core_catalog({kcal.CATALOG_ENV: str(tmp_path)})


def test_the_catalog_read_is_the_pinned_commits(real):
    assert real.docs["ArticoleTerms"]["register"]["commit"]  # the register pin it dates under
    assert core.lock_set(real).core == core.CORE_VERSION == "0.4.0"


# ----- the real state: no window, no year: every item refused, the client held -----


@pytest.mark.law("P10")
def test_the_real_catalog_refuses_every_owed_filing_and_the_client_is_held(
    cat, firm, real_dir, monkeypatch
):
    monkeypatch.setenv(kcal.CATALOG_ENV, str(real_dir))
    on(monkeypatch, date(2026, 7, 1))
    pc = Fake()
    tick = dispatch(cat, ROOT, firm, ISSUE, pc, company())
    real = kcal.core_catalog()
    assert real.docs["ArticoleTerms"]["register"]["max_age_days"] is None
    assert real.docs["ArticoleNonWorking"]["years"] == []

    f = firm.facts(ISSUE)
    unset = core.register_freshness(real, date(2026, 7, 1))
    assert unset and "max_age_days" in unset
    assert f["freshness"] == unset and f["items"] == [] and f["later"] == []
    assert sorted(r["filing_id"] for r in f["refused"]) == owed(real)  # none dropped
    assert all(r["reason"] == unset for r in f["refused"])

    assert tick.steps == ["kit:obligations", "hold:calendar_refuses"]
    assert tick.ended.startswith("hold: the calendar refuses: register: ")
    comment = pc.comments[firm.paperclip_id(ISSUE)][-1]
    assert "max_age_days" in comment and "D300 (d300_platitor)" in comment


# ----- the dated path, on invented pins -----


def test_every_owed_filing_is_dated_with_its_lock_set_and_the_calendar_is_done(
    cat, firm, real, monkeypatch
):
    on(monkeypatch, verified(real) + timedelta(days=10), invented(real))
    pc = Fake()
    tick = dispatch(cat, ROOT, firm, ISSUE, pc, company())
    f = firm.facts(ISSUE)
    assert f["freshness"] is None and f["refused"] == []
    assert sorted(i["filing_id"] for i in f["items"] + f["later"]) == owed(real)
    for item in f["items"]:
        assert date.fromisoformat(item["due"]) >= date.fromisoformat(item["unshifted"])
        assert date.fromisoformat(item["due"]).weekday() < 5  # the invented weekly rest
        assert item["lock"]["core"] == "0.4.0"
        assert item["lock"]["library"] == real.docs["ArticoleTerms"]["register"]["commit"]
        assert item["lock_key"].startswith("core-v0.4.0|library@")
    assert tick.ended.startswith("done:dated")
    assert pc.issues[firm.paperclip_id(ISSUE)]["status"] == "done"


def test_a_filing_owed_later_is_kept_with_its_reason_and_holds_nothing(
    cat, tmp_path, real, monkeypatch
):
    d = open_dossier(tmp_path, CUI)
    d.set_codit("2026-07", {**FIRM.axes, **FREQ})
    on(monkeypatch, verified(real) + timedelta(days=10), invented(real))
    pc = Fake()
    tick = dispatch(cat, ROOT, d, f"calendar:{CUI}:2026-07", pc, company())
    later = d.facts(f"calendar:{CUI}:2026-07")["later"]
    assert [x["form"] for x in later] == ["D100"]
    assert later[0]["reason"] == "its quarter does not end in 2026-07"
    assert tick.ended == "done:dated"
    assert "1 later" in pc.comments[d.paperclip_id(f"calendar:{CUI}:2026-07")][-1]


@pytest.mark.law("P10")
def test_a_stale_register_refuses_every_item_and_holds(cat, firm, real, monkeypatch):
    day = verified(real) + timedelta(days=WINDOW + 1)
    on(monkeypatch, day, invented(real))
    tick = dispatch(cat, ROOT, firm, ISSUE, Fake(), company())
    f = firm.facts(ISSUE)
    assert "stale" in f["freshness"] and f["items"] == []
    assert sorted(r["filing_id"] for r in f["refused"]) == owed(real)
    assert all(r["reason"] == f["freshness"] for r in f["refused"])
    assert tick.ended.startswith("hold: the calendar refuses: register: the register pin is stale")


@pytest.mark.law("P10")
def test_a_register_not_fresh_holds_even_with_nothing_refused():
    f = CalendarFacts(today="2026-07-01", computed_on="2026-07-01", freshness="not set")
    step = route_calendar(f)
    assert step.kind == "hold" and step.reason == "the calendar refuses: register: not set"
    assert route_calendar(f.model_copy(update={"freshness": None})).kind == "done"


@pytest.mark.law("P10")
def test_an_unpinned_year_refuses_its_items_with_the_reason(cat, firm, real, monkeypatch):
    on(monkeypatch, verified(real) + timedelta(days=10), invented(real, years=()))
    tick = dispatch(cat, ROOT, firm, ISSUE, Fake(), company())
    refused = firm.facts(ISSUE)["refused"]
    assert refused and all("no non-working days pinned" in r["reason"] for r in refused)
    assert "no non-working days pinned for 2026" in tick.ended


@pytest.mark.law("P10")
def test_no_codit_holds_the_calendar(cat, tmp_path, real, monkeypatch):
    d = open_dossier(tmp_path, CUI)
    on(monkeypatch, verified(real) + timedelta(days=10), invented(real))
    tick = dispatch(cat, ROOT, d, ISSUE, Fake(), company())
    assert tick.ended == f"hold: kit step obligations: no CO.DiT for {PERIOD}: set it first" + (
        " (kit dossier set-codit)"
    )


# ----- replay and a later day -----


@pytest.mark.law("P9")
def test_a_replayed_wake_adds_nothing_and_a_later_day_asks_again(cat, firm, real, monkeypatch):
    day = verified(real) + timedelta(days=10)
    on(monkeypatch, day, invented(real, window=None))  # the window still unset: held
    pc, co = Fake(), company()
    dispatch(cat, ROOT, firm, ISSUE, pc, co)
    rows = firm.db.execute("SELECT COUNT(*) FROM issue_facts WHERE issue = ?", (ISSUE,)).fetchone()
    again = dispatch(cat, ROOT, firm, ISSUE, pc, co)
    assert again.steps == ["hold:calendar_refuses"]
    assert (
        firm.db.execute("SELECT COUNT(*) FROM issue_facts WHERE issue = ?", (ISSUE,)).fetchone()
        == rows
    )
    on(monkeypatch, day + timedelta(days=1), invented(real))  # the owner set the window
    later = dispatch(cat, ROOT, firm, ISSUE, pc, co)
    assert later.steps == ["kit:obligations", "done:dated"]
    dated = firm.facts(ISSUE)
    assert dated["computed_on"] == (day + timedelta(days=1)).isoformat() and dated["items"]
    on(monkeypatch, day + timedelta(days=2), invented(real, window=None))
    assert dispatch(cat, ROOT, firm, ISSUE, pc, co).ended.startswith("done:dated")
    assert firm.facts(ISSUE)["items"] == dated["items"]  # a dated calendar is never recomputed


def test_the_recorded_facts_are_plain_json(cat, firm, real, monkeypatch):
    on(monkeypatch, verified(real) + timedelta(days=10), invented(real))
    dispatch(cat, ROOT, firm, ISSUE, Fake(), company())
    f = firm.facts(ISSUE)
    assert json.loads(json.dumps(f)) == f
