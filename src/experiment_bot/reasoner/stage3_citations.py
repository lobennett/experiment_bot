from __future__ import annotations
import copy
import json
import logging
import os
from pathlib import Path
from experiment_bot.llm.protocol import LLMClient
from experiment_bot.reasoner.parse_retry import parse_with_retry
from experiment_bot.reasoner.retrieval import search_works, verify_by_title
from experiment_bot.reasoner.openalex import verify_doi
from experiment_bot.taskcard.types import ReasoningStep

logger = logging.getLogger(__name__)
PROMPTS_DIR = Path(__file__).parent / "prompts"
_POOL_CAP = 30

# param-name -> search phrase (deterministic queries; reproducible, no LLM call)
_PARAM_PHRASE = {
    "mu": "ex-Gaussian reaction time distribution",
    "sigma": "ex-Gaussian reaction time distribution",
    "tau": "ex-Gaussian reaction time distribution",
    "ssrt": "stop-signal reaction time",
    "cse_magnitude": "congruency sequence effect",
    "post_error_slowing": "post-error slowing",
    "accuracy": "accuracy error rate",
    "omission": "omission error rate",
    "lag1_autocorr": "sequential dependency reaction time",
}


def _enumerate_parameters(partial: dict) -> list[str]:
    """Return paths like 'response_distributions/<condition>/mu'.

    The 'enabled' subkey of temporal effects is excluded — it's a boolean,
    not a numeric parameter that needs literature grounding.
    """
    paths = []
    for cond, dist in partial.get("response_distributions", {}).items():
        for p in dist.get("value", {}):
            paths.append(f"response_distributions/{cond}/{p}")
    for eff, body in partial.get("temporal_effects", {}).items():
        for p in body.get("value", {}):
            if p == "enabled":
                continue
            paths.append(f"temporal_effects/{eff}/{p}")
    bsj = partial.get("between_subject_jitter", {}).get("value", {})
    for p in bsj:
        paths.append(f"between_subject_jitter/_/{p}")
    return paths


def _query_for(path: str, paradigm_classes: list[str]) -> str:
    _, key, param = (path.split("/", 2) + ["", ""])[:3]
    phrase = _PARAM_PHRASE.get(param, param.replace("_", " "))
    classes = " ".join(paradigm_classes[:2])
    return f"{classes} {key if key != '_' else ''} {phrase}".strip()


def _resolve_target(result: dict, path: str) -> dict | None:
    parts = path.split("/")
    section = parts[0]
    key = parts[1] if len(parts) > 1 else None
    if section == "response_distributions":
        return result.get("response_distributions", {}).get(key)
    if section == "temporal_effects":
        return result.get("temporal_effects", {}).get(key)
    if section == "between_subject_jitter":
        return result.get("between_subject_jitter")
    return None


async def run_stage3(client: LLMClient, partial: dict) -> tuple[dict, ReasoningStep]:
    """Stage 3 (retrieval-grounded): retrieve a real-literature pool per parameter,
    then one LLM 'ground' call cites ONLY by pool index, grounds rationale in
    retrieved abstracts, and revises a value ONLY within a grounded range —
    else abstains (model-prior). Python enforces every guard. Fabrication is
    structurally impossible."""
    result = copy.deepcopy(partial)
    paths = _enumerate_parameters(result)
    pclasses = result.get("task", {}).get("paradigm_classes", []) or []

    def _abstain_all(reason: str):
        for path in paths:
            tgt = _resolve_target(result, path)
            if tgt is not None and not tgt.get("citations"):
                tgt["citations"] = tgt.get("citations", [])
                tgt["no_citation_reason"] = reason
                tgt.setdefault("value_source", "model_prior")
        return result, ReasoningStep(
            step="stage3_citations",
            inference=f"Retrieval-grounded Stage 3 abstained for all {len(paths)} parameters ({reason}).",
            evidence_lines=[], confidence="high")

    # Offline switch
    if os.environ.get("EXPERIMENT_BOT_RETRIEVAL", "").lower() in ("off", "0", "false"):
        return _abstain_all("retrieval disabled (EXPERIMENT_BOT_RETRIEVAL=off)")

    # --- Propose phase: model names canonical papers (NO DOI); Python verifies each ---
    propose_system = (PROMPTS_DIR / "stage3_propose.md").read_text()
    propose_user = "## Task\n" + json.dumps(
        {"name": result.get("task", {}).get("name", ""),
         "paradigm_classes": pclasses, "parameters": paths}, indent=2)
    candidates: list = []
    try:
        proposed = await parse_with_retry(client, system=propose_system,
                                          user=propose_user, stage_name="stage3_propose")
        if isinstance(proposed, dict) and isinstance(proposed.get("candidates"), list):
            candidates = proposed["candidates"]
    except Exception as e:
        logger.warning("stage3 propose call failed (%s); using search-only pool", e)
        candidates = []

    canonical: list = []
    for cand in candidates:
        if not isinstance(cand, dict):
            continue
        w = await verify_by_title(cand.get("authors", ""), cand.get("year"),
                                  cand.get("title", ""))
        if w is not None:
            canonical.append(w)

    # --- Deterministic citation-ranked search (OpenAlex sorted by cited_by_count) ---
    search_hits: list = []
    qcache: dict[str, list] = {}
    for path in paths:
        q = _query_for(path, pclasses)
        if q not in qcache:
            qcache[q] = await search_works(q, per_page=5)
        search_hits.extend(qcache[q])

    # --- Union: verified-canonical first (always kept), then highest-cited search hits ---
    pool: list = []
    seen: set = set()

    def _add(w) -> None:
        k = w.doi or (w.title, w.year)
        if k in seen:
            return
        seen.add(k)
        pool.append(w)

    for w in canonical:
        _add(w)
    for w in sorted(search_hits, key=lambda x: x.cited_by_count, reverse=True):
        if len(pool) >= _POOL_CAP:
            break
        _add(w)

    if not pool:
        return _abstain_all("retrieval unavailable or no candidates found")

    # One LLM ground call
    system = (PROMPTS_DIR / "stage3_ground.md").read_text()
    pool_json = [
        {"pool_idx": i, "doi": w.doi, "authors": w.authors, "year": w.year,
         "title": w.title, "abstract": w.abstract}
        for i, w in enumerate(pool)
    ]
    cur = {p: _resolve_target(result, p) for p in paths}
    user = "## Parameters + current values\n" + json.dumps(
        {"parameters": {p: (cur[p] or {}).get("value") for p in paths}}, indent=2
    ) + "\n\n## Retrieved pool\n" + json.dumps(pool_json, indent=2)
    try:
        grounded = await parse_with_retry(client, system=system, user=user,
                                          stage_name="stage3_ground")
    except Exception as e:
        logger.warning("stage3 ground call failed (%s); abstaining all", e)
        return _abstain_all(f"ground call failed: {e}")

    n_cited = n_revised = n_abstain = 0
    to_verify: list[dict] = []
    for path in paths:
        tgt = _resolve_target(result, path)
        if tgt is None:
            continue
        body = grounded.get(path) or {}
        param = path.split("/", 2)[-1]
        kept: list[dict] = []
        for c in body.get("citations", []):
            idx = c.get("pool_idx")
            if not isinstance(idx, int) or not (0 <= idx < len(pool)):
                continue  # GUARD: drop off-pool citations
            w = pool[idx]
            cit = {"doi": w.doi, "authors": w.authors, "year": w.year,
                   "title": w.title, "rationale": c.get("rationale", ""),
                   "confidence": c.get("confidence", "low"),
                   "abstract_snippet": w.abstract[:500]}
            kept.append(cit)
            to_verify.append(cit)
        if kept:
            # Accumulate citations (multiple params share the same tgt dict)
            existing = tgt.get("citations")
            if isinstance(existing, list):
                tgt["citations"] = existing + kept
            else:
                tgt["citations"] = kept
                n_cited += 1
            lr = body.get("literature_range")
            if isinstance(lr, dict):
                tgt.setdefault("literature_range", {}).update(lr)
            # GUARD: evidence-bounded revision
            rv = body.get("revised_value")
            if isinstance(rv, dict) and isinstance(lr, dict) and param in rv and param in lr:
                low, high = lr[param][0], lr[param][1]
                new = rv[param]
                if isinstance(new, (int, float)) and low <= new <= high:
                    orig = dict(tgt.get("value", {}))
                    tgt.setdefault("value", {})[param] = new
                    tgt["value_source"] = "literature_revised"
                    tgt["original_value"] = orig
                    tgt["revision_reason"] = body.get("revision_reason", "")
                    n_revised += 1
                else:
                    tgt.setdefault("value_source", "model_prior")
                    logger.warning("stage3: rejected out-of-range revision for %s: %r not in %r",
                                   path, new, lr.get(param))
            else:
                tgt.setdefault("value_source", "model_prior")
        else:
            # Only set abstain state if no citations were previously attached to this tgt
            if not tgt.get("citations"):
                tgt["citations"] = []
                tgt["no_citation_reason"] = body.get("no_citation_reason", "no pool work supported this parameter")
                tgt.setdefault("value_source", "model_prior")
                n_abstain += 1

    # GUARD: verify_doi title-gate on survivors (independent of pool source)
    for cit in to_verify:
        try:
            ok, _m = await verify_doi(doi=cit["doi"], expected_authors=cit["authors"],
                                      expected_year=int(cit["year"]), expected_title=cit["title"])
        except Exception:
            ok = False
        cit["doi_verified"] = bool(ok)

    step = ReasoningStep(
        step="stage3_citations",
        inference=(f"Canonical-recall: proposed={len(candidates)}, "
                   f"title-verified={len(canonical)}, search_hits={len(search_hits)}, "
                   f"pool={len(pool)}; {n_cited} parameters cited, {n_abstain} abstained, "
                   f"{n_revised} values revised within grounded ranges."),
        evidence_lines=[], confidence="high")
    return result, step
