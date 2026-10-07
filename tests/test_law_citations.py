"""The citation test: every ``[test]`` principle of LAW.md has a test naming it.

A test names a principle with ``@pytest.mark.law("P<n>")`` (or a module's ``pytestmark``).
Until the code a principle constrains exists, the principle waits in ``PENDING`` with the work
package that must bring its test. The ledger is checked as strictly as the citations:

- every ``[test]`` principle is cited by a test or pending;
- a pending principle names an open (not done) work package of BUILD.md;
- a cited principle is no longer pending: its line leaves ``PENDING`` in the same commit;
- every pending or cited id is a principle of LAW.md.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# principle id → the work package whose tests will name it. Shrinks to empty.
PENDING: dict[str, str] = {
    "P3": "WP-10",  # renderer: the only output toward SAGA is an import file of a mouth row
    "P5": "WP-13",  # routes: Validare comes only from a person; a closed month gets nothing
    "P7": "WP-13",  # router: the next step is a function of stored facts only
    "P8": "WP-14",  # hanks: a codon's model is the role row's pin; output checked before use
}

_PRINCIPLE = re.compile(r"^- \*\*(P\d+) · ")
_WP_ROW = re.compile(r"^\| (WP-\d+) \| ([a-z-]+) \|")


def parse_law(text: str) -> dict[str, bool]:
    """Principle id → whether it is marked ``[test]``. A principle's block is its bullet line
    and the indented lines that follow it."""
    found: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in text.splitlines():
        m = _PRINCIPLE.match(line)
        if m:
            if m.group(1) in found:
                raise ValueError(f"principle {m.group(1)} appears twice")
            current = found[m.group(1)] = [line]
        elif current is not None and line.startswith("  "):
            current.append(line)
        else:
            current = None
    return {pid: "[test]" in " ".join(block) for pid, block in found.items()}


def parse_build(text: str) -> dict[str, str]:
    """Work package id → status, from BUILD.md's status table."""
    return {m.group(1): m.group(2) for m in map(_WP_ROW.match, text.splitlines()) if m}


def parse_citations(source: str, name: str = "<test>") -> set[str]:
    """Principle ids named by ``pytest.mark.law(...)`` in a test module's source.
    An argument that is not a string literal is an error: a citation must be readable."""
    ids: set[str] = set()
    for node in ast.walk(ast.parse(source, filename=name)):
        f = node.func if isinstance(node, ast.Call) else None
        if (
            isinstance(f, ast.Attribute)
            and f.attr == "law"
            and isinstance(f.value, ast.Attribute)
            and f.value.attr == "mark"
        ):
            for arg in node.args:
                if not (isinstance(arg, ast.Constant) and isinstance(arg.value, str)):
                    raise ValueError(f"{name}:{node.lineno}: law() takes literal ids")
                ids.add(arg.value)
    return ids


def _law() -> dict[str, bool]:
    return parse_law((ROOT / "LAW.md").read_text(encoding="utf-8"))


def _cited() -> set[str]:
    ids: set[str] = set()
    for path in sorted((ROOT / "tests").rglob("*.py")):
        ids |= parse_citations(path.read_text(encoding="utf-8"), str(path.relative_to(ROOT)))
    return ids


def test_every_test_principle_is_cited_or_pending():
    tested = {pid for pid, t in _law().items() if t}
    assert sorted(tested - _cited() - PENDING.keys(), key=lambda p: int(p[1:])) == []


def test_pending_principles_wait_on_open_work():
    law, build = _law(), parse_build((ROOT / "BUILD.md").read_text(encoding="utf-8"))
    wrong = {
        pid: wp
        for pid, wp in PENDING.items()
        if not law.get(pid) or build.get(wp) in (None, "done")
    }
    assert wrong == {}


def test_a_cited_principle_leaves_the_ledger():
    assert sorted(_cited() & PENDING.keys()) == []


def test_citations_name_principles_of_the_law():
    assert sorted(_cited() - _law().keys()) == []


# ----- the parsers themselves -----

_SAMPLE_LAW = """\
Intro mentions [test] outside any principle.

- **P1 · Plain.** Not enforced by a test.
- **P2 · Tested.** Enforced, and the tag sits on
  the next line. [test]
- **P3 · Also plain.**

  An unindented paragraph after a blank line is not part of P3. [test]
"""


def test_parse_law_reads_ids_and_tags():
    assert parse_law(_SAMPLE_LAW) == {"P1": False, "P2": True, "P3": False}


def test_parse_law_refuses_a_repeated_id():
    with pytest.raises(ValueError, match="P1 appears twice"):
        parse_law("- **P1 · A.**\n- **P1 · B.**\n")


def test_parse_build_reads_the_status_table():
    table = "| id | status |\n|---|---|\n| WP-01 | done | x |\n| WP-07 | in-progress | y |\n"
    assert parse_build(table) == {"WP-01": "done", "WP-07": "in-progress"}


def test_parse_citations_finds_decorators_and_pytestmark():
    source = (
        "import pytest\n"
        'pytestmark = [pytest.mark.law("P4")]\n'
        '@pytest.mark.law("P2", "P3")\n'
        "def test_x():\n"
        "    pass\n"
        '# pytest.mark.law("P9") in a comment does not count\n'
    )
    assert parse_citations(source) == {"P2", "P3", "P4"}


def test_parse_citations_refuses_a_computed_id():
    with pytest.raises(ValueError, match="literal ids"):
        parse_citations('import pytest\nPID = "P2"\n@pytest.mark.law(PID)\ndef test_x(): pass\n')
