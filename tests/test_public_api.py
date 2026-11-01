"""Smoke tests for the public library API (no network or LLM access needed)."""

import privacy_policy_analyzer as ppa
from privacy_policy_analyzer import (
    AnalysisResult,
    AnalyzerError,
    FetchError,
)

FAKE_AGG = {
    "overall_score": 72.5,
    "confidence": 0.9,
    "category_scores": {"user_rights_and_redress": {"score": 8.0, "weight": 14, "rationale": "r"}},
    "top_strengths": [["user_rights_and_redress", 8.0]],
    "top_risks": [["cross_border_transfers", 3.0]],
    "red_flags": ["indefinite retention"],
    "recommendations": ["note"],
}


def _result() -> AnalysisResult:
    return AnalysisResult(
        url="https://example.com",
        resolved_url="https://example.com/privacy",
        model="gpt-4o",
        num_chunks=3,
        valid_chunks=3,
        aggregate=dict(FAKE_AGG),
        chunk_results=[{"index": 1}, {"index": 2}, {"index": 3}],
        timings={"discovery": 0.1, "fetch": 0.2, "analysis": 0.3, "total": 0.6},
    )


def test_public_exports_exist():
    for name in ppa.__all__:
        assert getattr(ppa, name, None) is not None, name
    assert callable(ppa.analyze)
    assert callable(ppa.resolve_privacy_url)
    assert callable(ppa.fetch_policy_text)


def test_analysis_result_properties():
    r = _result()
    assert r.status == "ok"
    assert r.overall_score == 72.5
    assert r.confidence == 0.9
    assert r.red_flags == ["indefinite retention"]
    assert r.recommendations == ["note"]


def test_to_dict_summary_shape():
    out = _result().to_dict(report="summary")
    assert out["status"] == "ok"
    assert out["chunks"] == 3
    assert out["valid_chunks"] == 3
    assert out["overall_score"] == 72.5
    assert out["red_flags_count"] == 1
    assert "category_scores" not in out


def test_to_dict_detailed_shape():
    out = _result().to_dict(report="detailed")
    assert out["chunks"] == 3
    assert out["category_scores"] == FAKE_AGG["category_scores"]
    assert out["red_flags"] == ["indefinite retention"]


def test_to_dict_full_includes_chunk_results():
    out = _result().to_dict(report="full")
    # Historical shape: "chunks" carries the per-chunk results in full mode.
    assert out["chunks"] == [{"index": 1}, {"index": 2}, {"index": 3}]


def test_analyzer_error_payload():
    exc = FetchError("fetch_failed", "https://example.com", "https://example.com/privacy")
    assert isinstance(exc, AnalyzerError)
    assert exc.to_dict() == {
        "status": "error",
        "reason": "fetch_failed",
        "url": "https://example.com",
        "resolved_url": "https://example.com/privacy",
    }


def test_analyze_pipeline_with_stubbed_io(monkeypatch):
    """End-to-end analyze() without any network or LLM calls."""
    from privacy_policy_analyzer import analysis

    monkeypatch.setattr(
        analysis, "resolve_privacy_url", lambda url: (url + "/privacy", url)
    )
    monkeypatch.setattr(
        analysis, "fetch_policy_text", lambda url, prefer="auto": "policy text " * 100
    )
    scores = {k: 7 for k in ppa.SCORING_WEIGHTS}
    rationales = {k: "ok" for k in ppa.SCORING_WEIGHTS}
    monkeypatch.setattr(
        analysis,
        "analyze_chunk_json",
        lambda chunk, model: {"scores": dict(scores), "rationales": dict(rationales), "red_flags": [], "notes": []},
    )

    events: list[str] = []
    result = analysis.analyze(
        "https://example.com",
        model="fake-model",
        on_progress=lambda event, payload: events.append(event),
    )
    assert result.resolved_url == "https://example.com/privacy"
    assert result.model == "fake-model"
    assert result.valid_chunks == result.num_chunks >= 1
    assert result.overall_score == 70.0
    assert events[0] == "resolve_start"
    assert "analyzed" in events
    assert set(result.timings) == {"discovery", "fetch", "analysis", "total"}


def test_analyze_fetch_failure_raises(monkeypatch):
    from privacy_policy_analyzer import analysis

    monkeypatch.setattr(analysis, "resolve_privacy_url", lambda url: (url, None))
    monkeypatch.setattr(analysis, "fetch_policy_text", lambda url, prefer="auto": None)

    try:
        analysis.analyze("https://example.com")
    except FetchError as exc:
        assert exc.reason == "fetch_failed"
        assert exc.to_dict()["status"] == "error"
    else:
        raise AssertionError("expected FetchError")
