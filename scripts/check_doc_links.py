#!/usr/bin/env python3
"""Fail on dead intra-repo references in the high-traffic docs.

Scans README.md, CLAUDE.md, and docs/*.md (top level) for references to repo
files — docs/*.md, taskcards/<hash>.json, scripts/*.py — and reports any that
do not resolve on disk. Illustrative/example paths (uppercase placeholders like
DATE/NN/YYYY, or <…>/* ) are skipped. Exit 1 if any dangling reference is found.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REF_RE = re.compile(r"(docs/[\w./-]+\.md|taskcards/[\w./-]+\.json|scripts/[\w./-]+\.py)")
# Illustrative refs use uppercase placeholders (DATE, NN, YYYY) or <…>/*; real
# doc/taskcard/script paths are lowercase + digits.
PLACEHOLDER_RE = re.compile(r"[A-Z<>*]")


def find_dangling(sources: list[Path], repo: Path) -> list[tuple[str, str]]:
    bad: list[tuple[str, str]] = []
    for src in sources:
        if not src.exists():
            continue
        for m in REF_RE.finditer(src.read_text()):
            ref = m.group(1)
            if PLACEHOLDER_RE.search(ref):
                continue  # illustrative example, not a real reference
            if not (repo / ref).exists():
                bad.append((str(src.relative_to(repo)), ref))
    return bad


# Frozen pre-registered docs are never edited post-hoc; they reference
# expert-arm assets that live on the `main` branch, so they are exempt.
FROZEN = {"preregistration-naive.md"}


def _default_sources(repo: Path) -> list[Path]:
    docs = [p for p in sorted((repo / "docs").glob("*.md")) if p.name not in FROZEN]
    return [repo / "README.md", repo / "CLAUDE.md", *docs]


def main() -> int:
    bad = find_dangling(_default_sources(REPO), REPO)
    if bad:
        print("Dangling intra-repo references found:")
        for src, ref in bad:
            print(f"  {src}: {ref}")
        return 1
    print("check_doc_links: OK — all references resolve.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
