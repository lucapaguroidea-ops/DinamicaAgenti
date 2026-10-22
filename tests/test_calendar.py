"""WP-21: the calendar in the firm. A routine opens each client's ``calendar:{cui}:{period}``
issue; the Dispatcher asks the pinned core's calendar and records every owed filing as dated,
refused or later, with its reason; a refusal or a register that is not fresh holds the client's
calendar for a person, with the reasons (P10).

No legal value is written here. The real core catalog is read at the pinned commit from
``POARTA_CATALOG_DIR``, the same variable the kit reads in deployment (CI fetches PoartaContabila
at the pinned commit and sets it); its checkout must be at exactly the pin, or the tests fail.
Only when the variable is unset do the tests look, for local convenience, for a checkout
``uv sync`` left in uv's cache. The catalog pins no non-working year and leaves the freshness
window unset, so every owed filing is refused and the calendar is held. The dated path runs on that
catalog with an **invented** window and **invented** non-working years (labelled synthetic,
tests only), as PoartaContabila's own calendar tests do. Firms are the core's synthetic ones.
"""

from __future__ import annotations

import copy
import json
import os
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
    """The core's catalog at the pinned commit: ``POARTA_CATALOG_DIR``, else a uv-cache checkout.

    A set variable is the only source: it must be a clean ``catalog/`` of a checkout at the pin
    (the kit's own ``checkout_refusal``, as CI checks), or the tests fail.
    """
    commit = kcal.pinned_commit()
    where = os.environ.get(kcal.CATALOG_ENV)
    if where:
        path = Path(where)
        if not path.is_dir():
            pytest.fail(f"{kcal.CATALOG_ENV}={where} is not a directory")
        refusal = kcal.checkout_refusal(path, commit)
        if refusal:
            pytest.fail(refusal)
        return path
    try:
        cache = subprocess.run(["uv", "cache", "dir"], capture_output=True, text=True, check=True)
        found = sorted(Path(cache.stdout.strip()).glob(f"git-v0/checkouts/*/{commit[:7]}"))
    except (OSError, subprocess.SubprocessError):
        found = []
    for path in found:
        if (path / "catalog").is_dir() and kcal.checkout_refusal(path / "catalog", commit) is None:
            return path / "catalog"
    pytest.fail(
        f"no clean catalog of the pinned core {commit[:7]}: set {kcal.CATALOG_ENV} to the catalog/"
        f" of a PoartaContabila checkout at {commit} (git fetch --depth 1 origin {commit};"
        " git checkout FETCH_HEAD)"
    )


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
def test_a_directory_outside_git_is_refused(tmp_path):
    with pytest.raises(kcal.CalendarUnavailable, match="checkout is at no git commit"):
        kcal.core_catalog({kcal.CATALOG_ENV: str(tmp_path)})


def _git(repo: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    )
    return out.stdout.strip()


@pytest.fixture
def clone(real_dir, tmp_path, monkeypatch) -> Path:
    """A throwaway git repo holding a copy of the pinned catalog, its commit faked as the pin."""
    import shutil

    repo = tmp_path / "core"
    shutil.copytree(real_dir, repo / "catalog")
    _git(repo.parent, "init", "-q", str(repo))
    for key, value in (("user.email", "t@example.invalid"), ("user.name", "t")):
        _git(repo, "config", key, value)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "catalog")
    head = _git(repo, "rev-parse", "HEAD")
    monkeypatch.setattr(kcal, "pinned_commit", lambda: head)
    return repo


def _terms(repo: Path) -> Path:
    return repo / "catalog" / "60_practice" / "ARTICOLE_TERMS_v1.yaml"


def test_the_clean_pinned_checkout_is_accepted(clone):
    cat = kcal.core_catalog({kcal.CATALOG_ENV: str(clone / "catalog")})
    assert cat.docs["ArticoleTerms"]["register"]["max_age_days"] is None


@pytest.mark.law("P10")
def test_an_edited_catalog_at_the_pin_is_refused(clone):
    terms = _terms(clone)
    text = terms.read_text(encoding="utf-8")
    assert "max_age_days: null" in text
    terms.write_text(text.replace("max_age_days: null", "max_age_days: 99999"), encoding="utf-8")
    with pytest.raises(kcal.CalendarUnavailable, match="is modified: .*ARTICOLE_TERMS_v1.yaml"):
        kcal.core_catalog({kcal.CATALOG_ENV: str(clone / "catalog")})


@pytest.mark.law("P10")
def test_an_untracked_file_in_the_catalog_is_refused(clone):
    (clone / "catalog" / "60_practice" / "EXTRA_v1.yaml").write_text("x: 1\n", encoding="utf-8")
    with pytest.raises(kcal.CalendarUnavailable, match="is modified: .*EXTRA_v1.yaml"):
        kcal.core_catalog({kcal.CATALOG_ENV: str(clone / "catalog")})


@pytest.mark.law("P10")
def test_a_directory_other_than_the_checkouts_catalog_is_refused(clone):
    for where, named in ((clone, "the checkout root"), (clone / "catalog" / "60_practice", "")):
        with pytest.raises(kcal.CalendarUnavailable, match=f"is {named}.*not catalog/"):
            kcal.core_catalog({kcal.CATALOG_ENV: str(where)})


@pytest.mark.law("P10")
def test_a_catalog_at_another_commit_is_refused(clone):
    pin = _git(clone, "rev-parse", "HEAD")
    _terms(clone).write_text(_terms(clone).read_text(encoding="utf-8") + "\n", encoding="utf-8")
    _git(clone, "commit", "-q", "-am", "another commit")
    with pytest.raises(kcal.CalendarUnavailable, match=f"the pin is {pin[:7]}"):
        kcal.core_catalog({kcal.CATALOG_ENV: str(clone / "catalog")})


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
    # A deliberate tripwire: these fail when the owner sets the freshness window or pins a year
    # and the core pin moves to that commit; the test is then rewritten for the new state.
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
    assert f["catalog_commit"] == kcal.pinned_commit()  # which core catalog was read


# ----- the CO.DiT vocabulary: the core's, not translated -----


@pytest.mark.law("P10")
@pytest.mark.parametrize(
    ("axis", "value"),
    [("impozit", "micro_3"), ("exig", "tva_la_livrare"), ("forma", "ii")],
)
def test_a_codit_value_the_core_does_not_know_holds_the_calendar(
    cat, tmp_path, real, monkeypatch, axis, value
):
    d = open_dossier(tmp_path, CUI)
    d.set_codit(PERIOD, {**FIRM.axes, **FREQ, axis: value})
    on(monkeypatch, verified(real) + timedelta(days=10), invented(real))
    pc = Fake()
    tick = dispatch(cat, ROOT, d, ISSUE, pc, company())
    assert tick.ended.startswith("hold: kit step obligations: the CO.DiT is outside the core's")
    assert f"{axis}: {value!r} is not one of the core's" in tick.ended
    assert d.facts(ISSUE).get("items") is None  # nothing recorded as dated
    assert value in pc.comments[d.paperclip_id(ISSUE)][-1]


@pytest.mark.law("P10")
def test_a_codit_axis_the_core_does_not_know_is_refused(real):
    with pytest.raises(kcal.CalendarUnavailable, match="axis 'regime'"):
        kcal.check_axes(real, {**FIRM.axes, **FREQ, "regime": "x"})


def test_the_core_firms_axes_are_inside_the_core_vocabulary(real):
    for firm in core.synthetic.FIRMS.values():
        kcal.check_axes(real, {**firm.axes, **FREQ})
