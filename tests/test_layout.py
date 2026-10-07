"""The repository keeps the layout ARCHITECTURE.md and AGENTS.md point to."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DOCS = ["README.md", "LAW.md", "AGENTS.md", "ARCHITECTURE.md", "BUILD.md", "RESEARCH_LOG.md"]
FOLDERS = ["catalog", "kit", "hanks", "paperclip", "saga-agent", "fixtures", "tests", "loops"]
CATALOG = ["10_law_firm", "20_document", "30_path", "40_sink", "50_control", "60_practice"]


def test_top_level_documents_exist():
    assert [d for d in DOCS if not (ROOT / d).is_file()] == []


def test_folders_exist_with_a_readme():
    missing = [
        f for f in FOLDERS if f not in ("kit", "tests") and not (ROOT / f / "README.md").is_file()
    ]
    assert missing == []


def test_catalog_sections():
    assert [c for c in CATALOG if not (ROOT / "catalog" / c).is_dir()] == []


def test_every_principle_has_a_permanent_id():
    law = (ROOT / "LAW.md").read_text(encoding="utf-8")
    ids = [f"P{n}" for n in range(1, 17)]
    assert [i for i in ids if f"**{i} ·" not in law] == []
