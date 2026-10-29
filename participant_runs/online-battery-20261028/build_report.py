"""Build the local evaluation index without editing any individual attempt."""
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
REPO = BASE.parents[1]
CHECKER = REPO / "skills/behavioral-participant/scripts/check_run.py"


def make_report():
    selection = json.loads((BASE / "selection.json").read_text())
    attempts = []
    for path in sorted(BASE.glob("*/attempt-*/run.json")):
        manifest = json.loads(path.read_text())
        relative = path.parent.relative_to(BASE).as_posix()
        row = {"directory": relative, **{key: manifest.get(key) for key in (
            "input_url", "status", "status_reason", "mode", "counts", "data_export",
            "policy_sha256", "skill_sha256", "limitations", "started_at", "ended_at")}}
        row["manifest_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        if manifest["status"] != "running" and manifest.get("artifacts_sha256"):
            result = subprocess.run([sys.executable, str(CHECKER), str(path.parent)],
                                    text=True, capture_output=True)
            row["artifact_integrity"] = "verified" if result.returncode == 0 else "failed"
            row["verification"] = result.stdout.strip() if result.returncode == 0 else result.stderr.strip()
        else:
            row["artifact_integrity"] = "pending"
        attempts.append(row)
    tasks = []
    for task in selection["tasks"]:
        prefix = "self-paced-reading" if task["id"] == "paced-reading" else task["id"]
        matching = [r for r in attempts if r["directory"].startswith(prefix + "/")]
        tasks.append({**task, "attempts": [r["directory"] for r in matching],
                      "completed_attempts": [r["directory"] for r in matching if r["status"] == "completed"],
                      "latest_completed": next((r for r in reversed(matching) if r["status"] == "completed"), None),
                      "latest": matching[-1] if matching else None})
    report = {"updated_at": datetime.now(timezone.utc).isoformat(),
              "purpose": selection["purpose"], "tasks": tasks, "attempts": attempts}
    (BASE / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    lines = ["# Online behavioral skill evaluation", "", report["purpose"], "",
             "Every attempt is retained. Completion, perceptual coverage, native data availability, "
             "and human behavioral validity are separate claims.", "",
             "The table distinguishes the latest terminal run from the latest attempt. "
             "These are developmental attempts, not a selected scientific cohort. "
             "See [findings.md](findings.md) for phase-specific outcomes and limitations.", "",
             "| Task | Latest terminal run | Latest attempt | Mode of latest attempt | Artifact integrity | Native export |",
             "|---|---|---|---|---|---|"]
    for task in tasks:
        latest = task["latest"]
        if latest:
            directory = latest["directory"]
            export = (latest["data_export"] or {}).get("status", "unknown")
            terminal = task["latest_completed"]
            completed_link = (f"[{terminal['directory'].split('/')[-1]}]({terminal['directory']}/summary.md)"
                              if terminal else "none")
            lines.append(f"| [{task['id']}]({task['url']}) | {completed_link} | [{latest['status']}]({directory}/summary.md) "
                         f"| {latest['mode']} | {latest['artifact_integrity']} | {export} |")
        else:
            lines.append(f"| [{task['id']}]({task['url']}) | none | pending | — | — | — |")
    lines += ["", "## All attempts", ""]
    for row in attempts:
        reason = row["status_reason"] or "Run in progress."
        lines += [f"- [{row['directory']}]({row['directory']}/run.json): "
                  f"**{row['status']}**, {row['mode']}; {reason}"]
    lines += ["", "## Design changes grounded in these runs", "",
              "- Direct model/tool round trips missed brief stimuli; the skill now explicitly distinguishes "
              "direct participation from a frozen, model-authored visible-state policy.",
              "- Canvas planning required coordinate drag input; the skill now checks input capabilities "
              "and permits an isolated browser transport with the needed capability.",
              "- Installed CLI scripting and session failures require a real adapter preflight, page-identity "
              "checks, and observation before retrying uncertain delivery.",
              "- Participant memory and random state persist across tool segments; continuous blocks do "
              "not pause for agent narration.",
              "- Reading exposed missed observations despite a self-paced label; direct participation "
              "now emphasizes persistent transport and compact stimulus screenshots.",
              "- A portable artifact checker validates evidence links, frozen policy pins, protocol "
              "snapshots, and all finalized artifact hashes.", "",
              "See [selection.json](selection.json) for the task selection and completion criteria, "
              "[results.json](results.json) for full counts and limitations, and each attempt's summary "
              "for evidence. This battery does not compare outputs with human reference data.", ""]
    (BASE / "summary.md").write_text("\n".join(lines))
    print(json.dumps({"tasks": len(tasks), "attempts": len(attempts),
                      "finalized": sum(r["status"] != "running" for r in attempts),
                      "verification_failures": [r["directory"] for r in attempts
                                                if r["artifact_integrity"] == "failed"]}))


if __name__ == "__main__":
    make_report()
