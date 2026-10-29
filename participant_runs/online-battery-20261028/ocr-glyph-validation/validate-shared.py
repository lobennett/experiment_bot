"""Compare generic --fast helper with offline labels; retain raw OCR output."""
import hashlib
import json
import subprocess
from pathlib import Path

here = Path(__file__).resolve().parent
baseline = json.loads((here / "fast-validation.json").read_text())
cases = [(r["expected"], Path(r["path"]), ["--crop", *map(str, r["crop"]), "--fast"])
         for r in baseline["results"]]
root = here.parent
cases.extend([
    ("Mary", root / "self-paced-reading/attempt-01/evidence/05_word.png", []),
    ("", root / "tower-hanoi/attempt-02/evidence/001_click_text.png", []),
    ("is", root / "self-paced-reading/attempt-04/evidence/053_frame.png", ["--crop", "20", "70", "760", "110"]),
])
results = []
for expected, path, flags in cases:
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    cmd = ["/private/tmp/experiment-bot-ocr", str(path), *flags]
    response = subprocess.run(cmd, capture_output=True, text=True, check=False)
    after = hashlib.sha256(path.read_bytes()).hexdigest()
    output = json.loads(response.stdout) if response.returncode == 0 else None
    exact = output is not None and output["text"] == expected and before == after
    case_insensitive = output is not None and output["text"].casefold() == expected.casefold() and before == after
    results.append({"expected": expected, "source_sha256": before, "source_unchanged": before == after,
                    "command": cmd, "output": output, "stderr": response.stderr,
                    "exact_match": exact, "case_insensitive_match": case_insensitive})
    print(json.dumps({"path": path.name, "expected": expected, "observed": output["text"] if output else None,
                      "exact_match": exact, "case_insensitive_match": case_insensitive}))
helper = Path("skills/behavioral-participant/scripts/ocr.swift")
summary = {"helper_sha256": hashlib.sha256(helper.read_bytes()).hexdigest(), "results": results,
           "fast_exact_passed": sum(r["exact_match"] for r in results[:14]), "fast_total": 14,
           "fast_case_insensitive_passed": sum(r["case_insensitive_match"] for r in results[:14]),
           "default_compatibility_passed": sum(r["exact_match"] for r in results[14:]), "default_total": 3}
(here / "shared-helper-validation.json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps({k:v for k,v in summary.items() if k != "results"}))
