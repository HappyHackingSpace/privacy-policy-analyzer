"""Result and error types for the public API."""

from dataclasses import dataclass, field
from typing import Any

__all__ = ["AnalysisResult", "AnalyzerError", "FetchError", "AnalysisError"]


class AnalyzerError(RuntimeError):
    """Base error for the analysis pipeline.

    Carries the machine-readable ``reason`` plus the input and resolved URLs so
    callers (e.g. the CLI) can emit the same structured error payload the tool
    has always printed.
    """

    def __init__(self, reason: str, url: str, resolved_url: str | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.url = url
        self.resolved_url = resolved_url

    def to_dict(self) -> dict[str, Any]:
        """Structured error payload (same shape the CLI prints on failure)."""
        return {
            "status": "error",
            "reason": self.reason,
            "url": self.url,
            "resolved_url": self.resolved_url,
        }


class FetchError(AnalyzerError):
    """Raised when the policy content could not be fetched."""


class AnalysisError(AnalyzerError):
    """Raised when chunking or LLM scoring produced no usable results."""


@dataclass
class AnalysisResult:
    """Aggregated result of analyzing one privacy policy.

    Attributes:
        url: The URL the user asked to analyze.
        resolved_url: The privacy policy URL that was actually analyzed.
        model: The LLM model name used for scoring.
        num_chunks: Number of text chunks sent to the LLM.
        valid_chunks: Number of chunks that returned a valid score.
        aggregate: Aggregated report from ``aggregate_chunk_results`` (overall
            score, confidence, category scores, strengths, risks, red flags,
            recommendations).
        chunk_results: Raw per-chunk JSON results from the LLM.
        timings: Wall-clock seconds per phase (discovery, fetch, analysis, total).
        status: Always ``"ok"`` for a returned result; failures raise instead.
    """

    url: str
    resolved_url: str
    model: str
    num_chunks: int
    valid_chunks: int
    aggregate: dict[str, Any]
    chunk_results: list[dict[str, Any]] = field(default_factory=list)
    timings: dict[str, float] = field(default_factory=dict)
    status: str = "ok"

    @property
    def overall_score(self) -> float:
        """Weighted overall score, 0-100."""
        return float(self.aggregate.get("overall_score", 0.0))

    @property
    def confidence(self) -> float:
        """Category coverage confidence, 0-1."""
        return float(self.aggregate.get("confidence", 0.0))

    @property
    def category_scores(self) -> dict[str, Any]:
        """Per-category score/weight/rationale entries."""
        return dict(self.aggregate.get("category_scores", {}))

    @property
    def top_strengths(self) -> list[Any]:
        """Top three highest-scoring categories."""
        return list(self.aggregate.get("top_strengths", []))

    @property
    def top_risks(self) -> list[Any]:
        """Top three lowest-scoring categories."""
        return list(self.aggregate.get("top_risks", []))

    @property
    def red_flags(self) -> list[str]:
        """Deduplicated red flags across all chunks."""
        return list(self.aggregate.get("red_flags", []))

    @property
    def recommendations(self) -> list[str]:
        """Collected notes/recommendations (capped by the aggregator)."""
        return list(self.aggregate.get("recommendations", []))

    def to_dict(self, report: str = "summary") -> dict[str, Any]:
        """Serialize to the JSON document shape the CLI prints.

        Args:
            report: One of ``"summary"``, ``"detailed"``, or ``"full"``.

        Returns:
            A JSON-serializable dict matching the historical CLI output for
            the given report level.
        """
        base_info = {
            "status": self.status,
            "url": self.url,
            "resolved_url": self.resolved_url,
            "model": self.model,
            "chunks": self.num_chunks,
            "valid_chunks": self.valid_chunks,
        }
        if report == "summary":
            return {
                **base_info,
                "overall_score": self.aggregate["overall_score"],
                "confidence": self.aggregate["confidence"],
                "top_strengths": self.aggregate["top_strengths"],
                "top_risks": self.aggregate["top_risks"],
                "red_flags_count": len(self.aggregate["red_flags"]),
            }
        if report == "detailed":
            return {**base_info, **self.aggregate}
        # "full": per-chunk results replace the chunk count (historical shape)
        return {**base_info, **self.aggregate, "chunks": self.chunk_results}
