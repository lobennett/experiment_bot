#!/usr/bin/env python3
"""Verify run evidence and hashes; --seal records hashes after structural checks.

Python standard library only. This checks artifact integrity, not task performance.
"""
import argparse
import hashlib
import json
from pathlib import Path


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def file_in(root, name):
    candidate = root / name
    require(not Path(name).is_absolute() and candidate.resolve().is_relative_to(root),
            f"artifact must stay inside the run directory: {name}")
    require(candidate.is_file(), f"missing artifact: {name}")
    return candidate


def unique_ids(items, label):
    ids = [item["id"] for item in items]
    require(len(ids) == len(set(ids)), f"duplicate {label} ID")
    return set(ids)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(directory, seal=False):
    root = Path(directory).resolve()
    manifest = read_json(root / "run.json")
    ontology = read_json(root / "ontology.json")
    file_in(root, "summary.md")
    events = [json.loads(line) for line in (root / "events.jsonl").read_text().splitlines()]
    require(manifest["status"] in {"completed", "partial", "blocked"},
            "finalize the run status before checking or sealing")
    require(manifest.get("ended_at"), "finalized run needs ended_at")
    version = manifest.get("schema_version", "1.0")
    require(version in {"1.0", "1.1"}, "unsupported run contract version")
    if version == "1.1":
        require(manifest.get("mode") in {"direct_browser", "generated_visible_policy"},
                "new contract needs an explicit execution mode")
        require((root / "protocol").is_dir() and bool(manifest.get("skill_sha256")),
                "new contract requires pinned protocol snapshots")
        if manifest["mode"] == "generated_visible_policy" and manifest["status"] == "completed":
            require(bool(manifest.get("policy_sha256")), "completed generated run needs policy hash")
            for field in ("policy_path", "authoring_prompt_path", "gate_report_path"):
                require(bool(manifest.get(field)), f"completed generated run needs {field}")
                file_in(root, manifest[field])
            require(manifest.get("authoring_context") in {
                "inherited_agent_context", "isolated_model_call"},
                "completed generated run needs authoring_context")
    node_ids = unique_ids(ontology["nodes"], "node")
    evidence_ids = unique_ids(ontology["evidence"], "evidence")

    def references(item, label, nonempty=False):
        refs = item["evidence_refs"]
        require(not nonempty or bool(refs), f"{label} needs evidence")
        require(set(refs) <= evidence_ids, f"unresolved evidence reference in {label}")

    for evidence in ontology["evidence"]:
        file_in(root, evidence["path"])
    for node in ontology["nodes"]:
        references(node, f"node {node['id']}", nonempty=True)
    for relation in ontology["relations"]:
        require(relation["subject"] in node_ids and relation["object"] in node_ids,
                "unresolved relation endpoint")
        references(relation, "relation", nonempty=True)
    indices = [event["index"] for event in events]
    require(all(isinstance(index, int) for index in indices) and
            indices == sorted(set(indices)), "event indices must strictly increase")
    for event in events:
        references(event, f"event {event['index']}")
    completion = manifest["completion_evidence_refs"]
    require(set(completion) <= evidence_ids, "unresolved completion evidence")
    if manifest["status"] == "completed":
        require(bool(completion), "completed run needs completion evidence")

    export = manifest["data_export"]
    require(export["status"] in {"available", "unavailable", "not_attempted"},
            "invalid data_export status")
    if export["status"] == "available":
        require(bool(export["paths"]), "available export needs a file")
    for name in export["paths"]:
        path = file_in(root, name)
        require(path.stat().st_size > 0, f"empty export: {name}")
        if path.suffix == ".json":
            read_json(path)

    if manifest.get("policy_sha256") is not None:
        require(bool(manifest.get("policy_path")), "pinned policy needs policy_path")
        require(digest(file_in(root, manifest["policy_path"])) == manifest["policy_sha256"],
                "frozen policy hash mismatch")
    if (root / "protocol").is_dir():
        for name, expected in manifest.get("skill_sha256", {}).items():
            require(digest(file_in(root, "protocol/" + name)) == expected,
                    f"skill snapshot hash mismatch: {name}")

    artifacts = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and path != root / "run.json":
            relative = path.relative_to(root).as_posix()
            artifacts[relative] = digest(file_in(root, relative))
    if seal:
        manifest["artifacts_sha256"] = artifacts
        # Validate first, then replace atomically; never leave a half-written manifest.
        temporary = root / ".run.json.tmp"
        require(not temporary.exists(), "temporary manifest already exists")
        temporary.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        temporary.replace(root / "run.json")
    else:
        require(manifest["artifacts_sha256"] == artifacts,
                "artifact hash mismatch or unrecorded/missing file")
    return {"status": manifest["status"], "nodes": len(node_ids),
            "relations": len(ontology["relations"]), "events": len(events),
            "verified_artifacts": len(artifacts), "legacy_contract": version == "1.0"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_directory", type=Path)
    parser.add_argument("--seal", action="store_true", help="write hashes after validating structure")
    args = parser.parse_args()
    try:
        print(json.dumps(check(args.run_directory, args.seal)))
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(1, f"Invalid run: {error}\n")


if __name__ == "__main__":
    main()
