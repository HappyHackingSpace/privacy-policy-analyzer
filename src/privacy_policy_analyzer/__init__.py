"""Privacy Policy Analyzer — importable core library.

Typical usage:

    from privacy_policy_analyzer import analyze

    result = analyze("https://example.com")
    print(result.overall_score, result.top_risks)
    print(result.to_dict(report="detailed"))
"""

from privacy_policy_analyzer.analysis import (
    analyze,
    analyze_chunk_json,
    split_text_into_chunks,
)
from privacy_policy_analyzer.discovery import resolve_privacy_url
from privacy_policy_analyzer.fetching import fetch_content_with_selenium, fetch_policy_text
from privacy_policy_analyzer.models import (
    AnalysisError,
    AnalysisResult,
    AnalyzerError,
    FetchError,
)
from privacy_policy_analyzer.prompts import SYSTEM_SCORER, build_user_prompt
from privacy_policy_analyzer.scoring import SCORING_WEIGHTS, aggregate_chunk_results

__version__ = "0.1.0"

__all__ = [
    "analyze",
    "AnalysisResult",
    "AnalyzerError",
    "FetchError",
    "AnalysisError",
    "resolve_privacy_url",
    "fetch_policy_text",
    "fetch_content_with_selenium",
    "split_text_into_chunks",
    "analyze_chunk_json",
    "aggregate_chunk_results",
    "SCORING_WEIGHTS",
    "SYSTEM_SCORER",
    "build_user_prompt",
    "__version__",
]
