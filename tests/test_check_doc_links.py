from pathlib import Path
from scripts.check_doc_links import find_dangling


def _repo(tmp_path: Path) -> Path:
    (tmp_path / "docs").mkdir()
    (tmp_path / "taskcards" / "x").mkdir(parents=True)
    (tmp_path / "taskcards" / "x" / "abc12345.json").write_text("{}")
    (tmp_path / "docs" / "real.md").write_text("ok")
    return tmp_path


def test_resolvable_refs_pass(tmp_path):
    repo = _repo(tmp_path)
    src = repo / "README.md"
    src.write_text("See `docs/real.md` and `taskcards/x/abc12345.json`.")
    assert find_dangling([src], repo) == []


def test_dangling_ref_is_caught(tmp_path):
    repo = _repo(tmp_path)
    src = repo / "CLAUDE.md"
    src.write_text("Tracked in `docs/sp6-results.md` (deleted).")
    bad = find_dangling([src], repo)
    assert ("CLAUDE.md", "docs/sp6-results.md") in [(s, r) for s, r in bad]


def test_illustrative_placeholders_are_skipped(tmp_path):
    repo = _repo(tmp_path)
    src = repo / "CLAUDE.md"
    src.write_text("Never create docs/clean-run-DATE.md or docs/spNN-results.md or docs/<paradigm>-test.md")
    assert find_dangling([src], repo) == []
