from privacy_policy_analyzer.scoring import aggregate_chunk_results

ALL = [
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

def test_top_strengths_and_risks_ordering_with_ties():
    s = {k: 5 for k in ALL}
    s.update({
        "user_rights_and_redress": 9,
        "security_and_breach": 9,
        "transparency_and_notice": 9,
        "cross_border_transfers": 3,
        "retention_and_deletion": 4,
        "secondary_use_and_limits": 4,
    })
    rats = {k: "r" for k in ALL}
    payload = [{"scores": s, "rationales": rats, "red_flags": [], "notes": []}]
    agg = aggregate_chunk_results(payload)

    strengths = [name for name, _ in agg["top_strengths"]]
    risks = [name for name, _ in agg["top_risks"]]

    assert set(strengths) == {"user_rights_and_redress", "security_and_breach", "transparency_and_notice"}
    assert set(risks) == {"cross_border_transfers", "retention_and_deletion", "secondary_use_and_limits"}
