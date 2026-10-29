"""Offline checks. Expected labels are assertion data, never inputs to OCR."""
import hashlib
import json
import subprocess
from pathlib import Path

here = Path(__file__).resolve().parent
base = here.parent / "preview5"
evidence = base / "attempt-05/evidence"
cropped = [320, 250, 320, 320]
cases = [
    ("g", evidence / "pixel-1857233f96723708.png", cropped),
    ("v", evidence / "pixel-0ab24edf988e0a6a.png", cropped),
    ("t", evidence / "fixture-letter-t.png", cropped),
    ("", evidence / "fixture-blank.png", cropped),
    ("+", evidence / "fixture-fixation.png", cropped),
    ("B", evidence / "pixel-37a69906a6888ae8.png", cropped),
    ("G", evidence / "pixel-a91aee5b26f5d21c.png", cropped),
    ("V", evidence / "pixel-b3ba805a0728c10e.png", cropped),
    ("D", evidence / "pixel-ed9885c8140086af.png", cropped),
    ("b", evidence / "pixel-fc96e965416a4309.png", cropped),
    ("", evidence / "pixel-f1ad1490970b19af.png", cropped),
    ("t", base / "attempt-04/evidence/009-current.png", [600, 413, 80, 80]),
    ("", base / "attempt-04/evidence/009-current.png", [280, 413, 80, 80]),
    ("+", base / "attempt-04/evidence/007-practice-start.png", [600, 413, 80, 80]),
]
results = []
for expected, path, crop in cases:
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    cmd = [str(here / "ocr-fast"), str(path), "--crop", *map(str, crop)]
    response = subprocess.run(cmd, capture_output=True, text=True, check=False)
    after = hashlib.sha256(path.read_bytes()).hexdigest()
    output = json.loads(response.stdout) if response.returncode == 0 else None
    results.append({"expected": expected, "path": str(path), "crop": crop,
                    "source_sha256": before, "source_unchanged": before == after,
                    "command": cmd, "output": output, "stderr": response.stderr,
                    "exit_code": response.returncode,
                    "passed": output is not None and output["text"] == expected and before == after})
summary = {"results": results, "passed": sum(r["passed"] for r in results), "total": len(results),
           "ocr_source_sha256": hashlib.sha256((here / "ocr-fast.swift").read_bytes()).hexdigest(),
           "source_fixture_limitation": "attempt-05 PNGs were saved by another adapter after 4x Pillow resize. g/v raw cropped screenshot bytes are unavailable. Tests preserve the provided files exactly; crops select pixels without resampling. Full attempt-04 frames are unscaled source captures."}
(here / "fast-validation.json").write_text(json.dumps(summary, indent=2) + "\n")
for r in results:
    print(json.dumps({"path": Path(r["path"]).name, "crop": r["crop"], "expected": r["expected"],
                      "observed": r["output"]["text"] if r["output"] else None, "passed": r["passed"]}))
print(f"Passed {summary['passed']}/{summary['total']}")
