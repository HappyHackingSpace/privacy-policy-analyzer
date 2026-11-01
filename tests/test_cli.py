"""Smoke tests for the ppa click CLI (no network or LLM access needed)."""

import json

from click.testing import CliRunner

from privacy_policy_analyzer import AnalysisResult, FetchError
from privacy_policy_analyzer.cli import main


def test_help_exits_zero():
    result = CliRunner().invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "URL" in result.output
    assert "--report" in result.output
    assert "--json" in result.output


def test_bad_report_choice_is_usage_error():
    result = CliRunner().invoke(main, ["https://example.com", "--report", "nope"])
    assert result.exit_code == 2
    assert "Invalid value" in result.output


def test_unknown_option_is_usage_error():
    result = CliRunner().invoke(main, ["https://example.com", "--no-such-flag"])
    assert result.exit_code == 2


def _fake_result() -> AnalysisResult:
    return AnalysisResult(
        url="https://example.com",
        resolved_url="https://example.com/privacy",
        model="fake-model",
        num_chunks=1,
        valid_chunks=1,
        aggregate={
            "overall_score": 70.0,
            "confidence": 1.0,
            "category_scores": {},
            "top_strengths": [],
            "top_risks": [],
            "red_flags": [],
            "recommendations": [],
        },
        chunk_results=[{"index": 1}],
        timings={"discovery": 0.0, "fetch": 0.0, "analysis": 0.0, "total": 0.0},
    )


def test_json_flag_prints_only_json(monkeypatch):
    import privacy_policy_analyzer.cli as cli_mod

    monkeypatch.setattr(cli_mod, "analyze", lambda url, **kwargs: _fake_result())
    result = CliRunner().invoke(main, ["https://example.com", "--json"])
    assert result.exit_code == 0
    out = json.loads(result.output)
    assert out["status"] == "ok"
    assert out["overall_score"] == 70.0
    assert out["resolved_url"] == "https://example.com/privacy"


def test_positional_and_legacy_url_option_agree(monkeypatch):
    import privacy_policy_analyzer.cli as cli_mod

    seen: list[str] = []

    def fake_analyze(url, **kwargs):
        seen.append(url)
        return _fake_result()

    monkeypatch.setattr(cli_mod, "analyze", fake_analyze)
    runner = CliRunner()
    assert runner.invoke(main, ["https://a.example", "--json"]).exit_code == 0
    assert runner.invoke(main, ["--url", "https://b.example", "--json"]).exit_code == 0
    assert seen == ["https://a.example", "https://b.example"]


def test_fetch_error_prints_error_json_and_exits_1(monkeypatch):
    import privacy_policy_analyzer.cli as cli_mod

    def fake_analyze(url, **kwargs):
        raise FetchError("fetch_failed", url, url + "/privacy")

    monkeypatch.setattr(cli_mod, "analyze", fake_analyze)
    result = CliRunner().invoke(main, ["https://example.com", "--json"])
    assert result.exit_code == 1
    payload = json.loads(result.output.strip().splitlines()[-1])
    assert payload == {
        "status": "error",
        "reason": "fetch_failed",
        "url": "https://example.com",
        "resolved_url": "https://example.com/privacy",
    }
