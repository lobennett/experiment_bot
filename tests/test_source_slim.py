"""Mechanical source slimming for generation prompts.

The slimmer is PURELY mechanical — blob elision by size, file ranking by
size/minification/entry-point reference — never semantic (no keyword-based
dropping, which could bias the behavioral content the model sees).
"""
from experiment_bot.core.config import SourceBundle
from experiment_bot.behavior.source_slim import (
    BLOB_THRESHOLD,
    DEFAULT_SOURCE_BUDGET,
    elide_blobs,
    slim_bundle,
)


# ---------------------------------------------------------------------------
# blob elision
# ---------------------------------------------------------------------------

def test_large_data_uri_elided_with_byte_count():
    payload = "A" * (BLOB_THRESHOLD + 100)
    text = f'<img src="data:image/png;base64,{payload}">'
    slimmed, elisions = elide_blobs(text)
    assert payload not in slimmed
    assert "elided" in slimmed
    assert str(len(payload)) in slimmed  # marker notes the byte count
    assert elisions == [{"kind": "data-uri", "bytes": len(payload)}]


def test_small_data_uri_kept_verbatim():
    payload = "A" * 64
    text = f'<img src="data:image/png;base64,{payload}">'
    slimmed, elisions = elide_blobs(text)
    assert slimmed == text
    assert elisions == []


def test_large_inline_svg_path_elided():
    d = "M0,0 " + "L1,1 " * ((BLOB_THRESHOLD // 5) + 100)
    text = f'<svg><path d="{d}"/></svg>'
    slimmed, elisions = elide_blobs(text)
    assert d not in slimmed
    assert len(elisions) == 1
    assert elisions[0]["kind"] == "svg-path"
    assert elisions[0]["bytes"] == len(d)


def test_small_svg_path_kept_verbatim():
    text = '<svg><path d="M0,0 L1,1 Z"/></svg>'
    slimmed, elisions = elide_blobs(text)
    assert slimmed == text
    assert elisions == []


# ---------------------------------------------------------------------------
# bundle slimming: pass-through, ranking, budget, entry point
# ---------------------------------------------------------------------------

def _bundle(entry: str, files: dict[str, str]) -> SourceBundle:
    return SourceBundle(url="http://x", source_files=files,
                        description_text=entry)


def test_small_bundle_passes_through_byte_identical():
    entry = "<html><script src='task.js'></script></html>"
    task = "var x = 1;\nfunction go() { return x; }\n"
    result = slim_bundle(_bundle(entry, {"task.js": task}))
    assert result.text == f"## Page HTML\n{entry}\n\n## File: task.js\n{task}"
    manifest = result.manifest
    assert manifest["budget"] == DEFAULT_SOURCE_BUDGET
    assert manifest["entry"]["truncated"] is False
    assert manifest["entry"]["elisions"] == []
    assert [f["included"] for f in manifest["files"]] == [True]
    assert manifest["files"][0]["elisions"] == []


def test_minified_vendor_ranked_below_task_file_and_excluded():
    """A minified vendor file loses the budget race to a plain task file even
    when the vendor file is SMALLER — ranking is by mechanical minification
    signal first, not just size."""
    entry = ('<html><script src="vendor.min.js"></script>'
             '<script src="task.js"></script></html>')
    vendor = "var a=1;" * 250  # 2000 chars, one long line -> minified
    task = "\n".join(f"var line{i} = {i};" for i in range(150))  # ~2.6k, short lines
    files = {"vendor.min.js": vendor, "task.js": task}
    # Budget: entry + task fit; vendor does not (after task is taken).
    budget = len("## Page HTML\n" + entry) + len("\n\n## File: task.js\n" + task) + 10
    result = slim_bundle(_bundle(entry, files), budget=budget)
    assert task in result.text
    assert vendor not in result.text
    by_name = {f["name"]: f for f in result.manifest["files"]}
    assert by_name["task.js"]["included"] is True
    assert by_name["vendor.min.js"]["included"] is False
    assert by_name["vendor.min.js"]["original_bytes"] == len(vendor)
    # The prompt notes the exclusion mechanically (name + byte count only).
    assert "vendor.min.js" in result.text


def test_oversized_file_excluded_when_budget_exhausted():
    entry = "<html></html>"
    huge = "x" * 10_000
    small = "var ok = true;\n"
    result = slim_bundle(_bundle(entry, {"huge.js": huge, "small.js": small}),
                         budget=1_000)
    assert small in result.text
    assert huge not in result.text
    by_name = {f["name"]: f for f in result.manifest["files"]}
    assert by_name["small.js"]["included"] is True
    assert by_name["huge.js"]["included"] is False


def test_entry_point_always_included_even_over_budget():
    entry = "<html>" + "e" * 5_000 + "</html>"
    result = slim_bundle(_bundle(entry, {"task.js": "var x;"}), budget=500)
    assert result.text.startswith("## Page HTML\n<html>")
    assert len(result.text) <= 500 + 200  # entry truncated to ~budget (+ elision note)
    assert result.manifest["entry"]["truncated"] is True
    assert all(not f["included"] for f in result.manifest["files"])


def test_included_files_keep_original_bundle_order():
    """Ranking decides WHICH files fit; the rendered text preserves the
    bundle's original file order so the model reads sources naturally."""
    entry = "<html></html>"
    files = {"z_second.js": "var b = 2;\n", "a_first.js": "var a = 1;\n"}
    result = slim_bundle(_bundle(entry, files))
    assert result.text.index("z_second.js") < result.text.index("a_first.js")


def test_entry_html_reference_boosts_rank():
    """With identical size/minification, a file referenced by the HTML entry
    point wins the budget race over an unreferenced one."""
    entry = '<html><script src="linked.js"></script></html>'
    body = "\n".join(f"var v{i} = {i};" for i in range(100))
    files = {"orphan.js": body, "linked.js": body}
    budget = (len("## Page HTML\n" + entry)
              + len("\n\n## File: linked.js\n" + body) + 10)
    result = slim_bundle(_bundle(entry, files), budget=budget)
    by_name = {f["name"]: f for f in result.manifest["files"]}
    assert by_name["linked.js"]["included"] is True
    assert by_name["orphan.js"]["included"] is False


def test_blob_elision_happens_before_budget_accounting():
    """A file dominated by a data-URI blob fits the budget after elision."""
    entry = "<html></html>"
    blob = "B" * 50_000
    fname_content = f'var img = "data:image/png;base64,{blob}";\nvar x = 1;\n'
    result = slim_bundle(_bundle(entry, {"task.js": fname_content}),
                         budget=2_000)
    by_name = {f["name"]: f for f in result.manifest["files"]}
    assert by_name["task.js"]["included"] is True
    assert "var x = 1;" in result.text
    assert blob not in result.text
    assert by_name["task.js"]["elisions"] == [{"kind": "data-uri", "bytes": 50_000}]
