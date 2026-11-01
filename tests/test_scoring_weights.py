import math
from privacy_policy_analyzer.scoring import SCORING_WEIGHTS, aggregate_chunk_results

ALL_CATEGORIES = [
    "lawful_basis_and_purpose",
    "collection_and_minimization",
    "secondary_use_and_limits",
    "retention_and_deletion",
    "third_parties_and_processors",
    "cross_border_transfers",
    "user_rights_and_redress",
    "security_and_breach",
    "transparency_and_notice",
    "sensitive_children_ads_profiling",
]

def _expected_overall(scores_0to10: dict[str, float]) -> float:
    total_w = sum(SCORING_WEIGHTS.values())
    weighted = 0.0
    for k, w in SCORING_WEIGHTS.items():
        s10 = float(scores_0to10[k])
        weighted += (s10 / 10.0) * w
    return round((weighted / total_w) * 100.0, 2)

def test_weights_sum_and_keys():
    assert set(ALL_CATEGORIES) == set(SCORING_WEIGHTS.keys())
    assert len(SCORING_WEIGHTS) == 10
    assert sum(SCORING_WEIGHTS.values()) == 100

def test_aggregate_basic_two_chunks_expected_overall_and_fields():
    scores1 = {k: 6 for k in ALL_CATEGORIES}
    scores2 = {k: 8 for k in ALL_CATEGORIES}
    rats1 = {k: "r1" for k in ALL_CATEGORIES}
    rats2 = {k: "r2" for k in ALL_CATEGORIES}

    payload = [
        {"scores": scores1, "rationales": rats1, "red_flags": ["rf1"], "notes": ["n1"]},
        {"scores": scores2, "rationales": rats2, "red_flags": ["rf1", "rf2"], "notes": ["n2"]},
    ]

    agg = aggregate_chunk_results(payload)

    assert "overall_score" in agg and isinstance(agg["overall_score"], float)
    assert "category_scores" in agg and isinstance(agg["category_scores"], dict)
    assert "confidence" in agg and 0 <= agg["confidence"] <= 1
    assert "top_strengths" in agg and isinstance(agg["top_strengths"], list)
    assert "top_risks" in agg and isinstance(agg["top_risks"], list)
    assert "red_flags" in agg and set(agg["red_flags"]) == {"rf1", "rf2"}
    assert "recommendations" in agg and agg["recommendations"] == ["n1", "n2"]

    expected = _expected_overall({k: 7 for k in ALL_CATEGORIES})
    assert math.isclose(agg["overall_score"], expected, abs_tol=1e-9)

    for k, entry in agg["category_scores"].items():
        assert entry["rationale"] == "r1"

def test_confidence_partial_coverage_and_recommendations_capped():
    missing_key = "cross_border_transfers"
    scores = {k: 7 for k in ALL_CATEGORIES if k != missing_key}
    rats = {k: "ok" for k in ALL_CATEGORIES if k != missing_key}

    notes = [f"n{i}" for i in range(12)]

    payload = [{"scores": scores, "rationales": rats, "red_flags": ["a", "a", "b"], "notes": notes}]
    agg = aggregate_chunk_results(payload)

    assert agg["confidence"] == 0.9
    assert set(agg["red_flags"]) == {"a", "b"}
    assert len(agg["recommendations"]) == 10