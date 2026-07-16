"""Mechanical source slimming for naive program generation (Wave C2).

Heavy platforms (bundled SPAs, vendored jsPsych) can blow the generation
prompt's context or bury the task logic under vendor code. This module
shrinks a SourceBundle using ONLY mechanical signals:

- base64 data-URIs and inline SVG path data over a size threshold are
  replaced with a short marker noting the byte count;
- for multi-file bundles, files are ranked by likely task relevance using
  file size, minification (fraction of very long lines), and whether the
  file name appears in the HTML entry point, then included best-first under
  a total character budget;
- the HTML entry point is always included (truncated only if it alone
  exceeds the budget).

NO semantic filtering: no keyword-based dropping, which could bias the
behavioral content the generation model sees. Everything elided is recorded
in a manifest archived with the generation transcript.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath

# Blob payloads (base64 data-URI, SVG path data) longer than this many
# characters are elided. Mechanical size threshold, not content-based.
BLOB_THRESHOLD = 1024

# A line longer than this is counted as "minified"; a file whose non-empty
# lines exceed MINIFIED_FRACTION_THRESHOLD of such lines ranks below plain
# source files in the budget race.
MINIFIED_LINE_CHARS = 500
MINIFIED_FRACTION_THRESHOLD = 0.25

# Total character budget for the assembled {PAGE_SOURCE} text. Generous by
# default; overridable via gen_cli's --source-budget.
DEFAULT_SOURCE_BUDGET = 300_000

# Marker templates. These strings reach the live generation prompt, so they
# are scanned by the neutrality invariants (tests/test_naive_prompt_invariants.py)
# exactly like the prompt template itself.
BLOB_MARKER = "[elided {kind}: {n} bytes]"
EXCLUDED_SECTION_HEADER = (
    "## Files elided by mechanical slimmer (character budget)\n"
)
EXCLUDED_LINE = "- {name}: {n} bytes"

_ENTRY_HEADER = "## Page HTML\n"
_FILE_HEADER = "## File: {name}\n"
_SEP = "\n\n"

_DATA_URI_RE = re.compile(r"(data:[A-Za-z0-9.+/-]+;base64,)([A-Za-z0-9+/=]+)")
_SVG_PATH_RE = re.compile(r"(\bd=)(\"[^\"]+\"|'[^']+')")


@dataclass
class SlimResult:
    text: str
    manifest: dict


def elide_blobs(text: str, *, threshold: int = BLOB_THRESHOLD) -> tuple[str, list[dict]]:
    """Replace oversized base64 data-URI payloads and inline SVG path data
    with byte-count markers. Returns (slimmed_text, elision_records)."""
    elisions: list[dict] = []

    def _data_uri(m: re.Match) -> str:
        payload = m.group(2)
        if len(payload) <= threshold:
            return m.group(0)
        elisions.append({"kind": "data-uri", "bytes": len(payload)})
        return m.group(1) + BLOB_MARKER.format(kind="data-uri", n=len(payload))

    out = _DATA_URI_RE.sub(_data_uri, text)

    def _svg_path(m: re.Match) -> str:
        quoted = m.group(2)
        inner = quoted[1:-1]
        if len(inner) <= threshold:
            return m.group(0)
        elisions.append({"kind": "svg-path", "bytes": len(inner)})
        quote = quoted[0]
        return (m.group(1) + quote
                + BLOB_MARKER.format(kind="svg-path", n=len(inner)) + quote)

    out = _SVG_PATH_RE.sub(_svg_path, out)
    return out, elisions


def _minified_fraction(text: str) -> float:
    """Fraction of non-empty lines longer than MINIFIED_LINE_CHARS."""
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return 0.0
    return sum(1 for line in lines if len(line) > MINIFIED_LINE_CHARS) / len(lines)


def slim_bundle(bundle, budget: int = DEFAULT_SOURCE_BUDGET) -> SlimResult:
    """Assemble a SourceBundle into one prompt-ready text under ``budget``
    characters, with a manifest of everything elided.

    Selection is best-first by mechanical rank (non-minified before
    minified, entry-referenced before orphaned, small before large); the
    rendered text preserves the bundle's original file order among the
    files that made the cut.
    """
    entry_raw = bundle.description_text or ""
    entry_text, entry_elisions = elide_blobs(entry_raw)
    entry_seg = _ENTRY_HEADER + entry_text
    entry_truncated = False
    if len(entry_seg) > budget:
        entry_seg = entry_seg[:budget]
        entry_truncated = True
    remaining = budget - len(entry_seg)

    infos: list[dict] = []
    for name, raw in (bundle.source_files or {}).items():
        raw = raw or ""
        slimmed, elisions = elide_blobs(raw)
        infos.append({
            "name": name,
            "original_bytes": len(raw),
            "slimmed_bytes": len(slimmed),
            "minified_fraction": round(_minified_fraction(slimmed), 3),
            "referenced_in_entry": bool(
                name and (name in entry_raw or PurePosixPath(name).name in entry_raw)
            ),
            "elisions": elisions,
            "included": False,
            "_content": slimmed,
        })

    # Best-first greedy inclusion under the remaining budget.
    ranked = sorted(infos, key=lambda f: (
        f["minified_fraction"] > MINIFIED_FRACTION_THRESHOLD,  # plain source first
        not f["referenced_in_entry"],                          # entry-linked first
        f["slimmed_bytes"],                                    # small first
        f["name"],                                             # stable tiebreak
    ))
    for f in ranked:
        seg_len = len(_SEP) + len(_FILE_HEADER.format(name=f["name"])) + len(f["_content"])
        if seg_len <= remaining:
            f["included"] = True
            remaining -= seg_len

    parts = [entry_seg]
    for f in infos:  # original bundle order among included files
        if f["included"]:
            parts.append(_FILE_HEADER.format(name=f["name"]) + f["_content"])
    excluded = [f for f in infos if not f["included"]]
    if excluded:
        parts.append(EXCLUDED_SECTION_HEADER + "\n".join(
            EXCLUDED_LINE.format(name=f["name"], n=f["original_bytes"])
            for f in excluded))
    text = _SEP.join(parts)

    manifest = {
        "budget": budget,
        "total_chars": len(text),
        "entry": {
            "chars": len(entry_seg),
            "truncated": entry_truncated,
            "elisions": entry_elisions,
        },
        "files": [
            {k: v for k, v in f.items() if not k.startswith("_")}
            for f in infos
        ],
    }
    return SlimResult(text=text, manifest=manifest)
