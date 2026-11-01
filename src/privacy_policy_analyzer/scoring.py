from typing import Any

__all__ = ["SCORING_WEIGHTS", "aggregate_chunk_results"]

SCORING_WEIGHTS: dict[str, int] = {
    "lawful_basis_and_purpose": 12,
    "collection_and_minimization": 10,
    "secondary_use_and_limits": 8,
    "retention_and_deletion": 8,
    "third_parties_and_processors": 12,
    "cross_border_transfers": 8,
    "user_rights_and_redress": 14,
    "security_and_breach": 12,
    "transparency_and_notice": 8,
    "sensitive_children_ads_profiling": 8,
}

_REQUIRED_KEYS = set(SCORING_WEIGHTS.keys())


def _avg(nums: list[float]) -> float:
    """Calculate the average of a list of floats.

    Args:
        nums: A list of float numbers.

    Returns:
        The average value as a float, or 0.0 if the list is empty.
    """
    return sum(nums) / len(nums) if nums else 0.0


def _get_score_descending(kv: tuple[str, float]) -> float:
    """Helper key function to sort categories by score in descending order."""
    return -kv[1]


def _get_score_ascending(kv: tuple[str, float]) -> float:
    """Helper key function to sort categories by score in ascending order."""
    return kv[1]


def aggregate_chunk_results(chunk_json_list: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregates per-chunk JSON results into a weighted overall report.

    Args:
        chunk_json_list: A list of chunk evaluation results from LLM. Each item must contain
            "scores" (dict mapping category keys to int 0..10), "rationales" (dict mapping
            category keys to string explanations), optional "red_flags" (list of strings),
            and optional "notes" (list of strings).

    Returns:
        A aggregated report dictionary with overall score, confidence, category scores,
        top strengths, top risks, red flags, and recommendations.
    """
    per_cat: dict[str, list[float]] = {k: [] for k in _REQUIRED_KEYS}
    rationales: dict[str, list[str]] = {k: [] for k in _REQUIRED_KEYS}
    all_red_flags: list[str] = []
    all_notes: list[str] = []

    for item in chunk_json_list:
        scores = item.get("scores", {})
        rats = item.get("rationales", {})
        for k in _REQUIRED_KEYS:
            v = scores.get(k)
            if isinstance(v, int) and 0 <= v <= 10:
                per_cat[k].append(float(v))
            r = rats.get(k)
            if isinstance(r, str) and r:
                rationales[k].append(r)
        if isinstance(item.get("red_flags"), list):
            all_red_flags.extend(x for x in item["red_flags"] if isinstance(x, str))
        if isinstance(item.get("notes"), list):
            all_notes.extend(x for x in item["notes"] if isinstance(x, str))

    category_scores: dict[str, dict[str, Any]] = {}
    weighted_sum = 0.0
    total_weight = 0

    for cat, weight in SCORING_WEIGHTS.items():
        s10 = round(_avg(per_cat[cat]), 2)
        category_scores[cat] = {
            "score": s10,
            "weight": weight,
            "rationale": rationales[cat][0] if rationales[cat] else "",
        }
        weighted_sum += (s10 / 10.0) * weight
        total_weight += weight

    overall_score = (
        round((weighted_sum / total_weight) * 100.0, 2) if total_weight else 0.0
    )
    coverage = sum(1 for v in per_cat.values() if v) / len(_REQUIRED_KEYS)
    confidence = round(coverage, 2)

    strengths: list[tuple[str, float]] = sorted(
        ((k, v["score"]) for k, v in category_scores.items()),
        key=_get_score_descending,
    )[:3]
    risks: list[tuple[str, float]] = sorted(
        ((k, v["score"]) for k, v in category_scores.items()),
        key=_get_score_ascending,
    )[:3]

    return {
        "overall_score": overall_score,
        "confidence": confidence,
        "category_scores": category_scores,
        "top_strengths": strengths,
        "top_risks": risks,
        "red_flags": sorted(set(all_red_flags)),
        "recommendations": all_notes[:10],
    }
