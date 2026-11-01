"""Chunking, LLM scoring backends, and the high-level analyze() orchestrator."""

import json
import os
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from dotenv import load_dotenv
from langchain_text_splitters import RecursiveCharacterTextSplitter
from google import genai
from google.genai import types as genai_types
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_random_exponential

from privacy_policy_analyzer.discovery import resolve_privacy_url
from privacy_policy_analyzer.fetching import fetch_policy_text
from privacy_policy_analyzer.models import AnalysisError, AnalysisResult, FetchError
from privacy_policy_analyzer.prompts import SYSTEM_SCORER, build_user_prompt
from privacy_policy_analyzer.scoring import aggregate_chunk_results

load_dotenv()

# Progress callback: receives an event name and a payload dict.
ProgressCallback = Callable[[str, dict[str, Any]], None]


def split_text_into_chunks(
    text: str, chunk_size: int = 3500, chunk_overlap: int = 350
) -> list[str]:
    """Split text into chunks using paragraph-first recursive boundaries.

    Args:
        text: The text to split.
        chunk_size: Target size of each chunk in characters. Defaults to 3500.
        chunk_overlap: Overlap between adjacent chunks in characters. Defaults to 350.

    Returns:
        A list of split text chunks.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    return splitter.split_text(text or "")


@retry(
    stop=stop_after_attempt(5),
    wait=wait_random_exponential(min=2, max=30),
    reraise=True
)
def _analyze_chunk_gemini(text_chunk: str, model: str) -> dict[str, Any] | None:
    """Analyze a text chunk using the Google Gemini API.

    Args:
        text_chunk: The text content chunk to analyze.
        model: The Gemini model name to use.

    Returns:
        The scored and analyzed dictionary if successful, None otherwise.

    Raises:
        RuntimeError: If GEMINI_API_KEY environment variable is not configured.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set. Configure your .env file.")

    client = genai.Client(api_key=api_key)
    resp = client.models.generate_content(
        model=model,
        contents=build_user_prompt(text_chunk),
        config=genai_types.GenerateContentConfig(
            system_instruction=SYSTEM_SCORER,
            response_mime_type="application/json",
            temperature=0.0,
            max_output_tokens=8192,
        ),
    )
    content = (resp.text or "").strip()
    try:
        return json.loads(content)  # type: ignore[no-any-return]
    except Exception:
        return None


@retry(
    stop=stop_after_attempt(5),
    wait=wait_random_exponential(min=2, max=30),
    reraise=True
)
def _analyze_chunk_openai(text_chunk: str, model: str) -> dict[str, Any] | None:
    """Analyze a text chunk with the OpenAI API and return one JSON object.

    Args:
        text_chunk: The text content chunk to analyze.
        model: The OpenAI-compatible model name to use.

    Returns:
        The scored and analyzed dictionary if successful, None otherwise.

    Raises:
        RuntimeError: If OPENAI_API_KEY environment variable is not configured.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set. Configure your .env file.")
    client = OpenAI(api_key=api_key, base_url=os.getenv("OPENAI_BASE_URL"))
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_SCORER},
            {"role": "user", "content": build_user_prompt(text_chunk)},
        ],
        temperature=0,
        max_tokens=2000,
        response_format={"type": "json_object"},
    )
    content = (resp.choices[0].message.content or "").strip()
    try:
        return json.loads(content)  # type: ignore[no-any-return]
    except Exception:
        return None


def analyze_chunk_json(text_chunk: str, model: str) -> dict[str, Any] | None:
    """Analyze a text chunk with the LLM and return one JSON object.

    Automatically selects the backend based on the model name:
    - Models starting with ``gemini`` → Google Gemini API (GEMINI_API_KEY)
    - All other models → OpenAI-compatible API (OPENAI_API_KEY + OPENAI_BASE_URL)

    Args:
        text_chunk: The text content chunk to analyze.
        model: The LLM model name to use.

    Returns:
        The scored and analyzed dictionary if successful, None otherwise.
    """
    if model.lower().startswith("gemini"):
        return _analyze_chunk_gemini(text_chunk, model)
    return _analyze_chunk_openai(text_chunk, model)


def analyze(
    url: str,
    *,
    model: str | None = None,
    chunk_size: int = 10000,
    chunk_overlap: int = 350,
    max_chunks: int = 30,
    fetch_method: str = "auto",
    discover: bool = True,
    max_workers: int = 5,
    on_progress: ProgressCallback | None = None,
) -> AnalysisResult:
    """Analyze a site's privacy policy end to end.

    Resolves the policy URL (unless ``discover`` is False), fetches the policy
    text, chunks it, scores every chunk with the LLM in parallel, and
    aggregates the scores into one report.

    Args:
        url: Site homepage or direct privacy policy URL.
        model: LLM model name; defaults to env ``OPENAI_MODEL`` or ``gpt-4o``.
        chunk_size: Character-based chunk size.
        chunk_overlap: Overlap between adjacent chunks in characters.
        max_chunks: Hard cap for analyzed chunks (overflow merges into the last).
        fetch_method: ``"auto"``, ``"http"``, or ``"selenium"``.
        discover: If False, analyze ``url`` as-is without auto-discovery.
        max_workers: Parallel LLM requests.
        on_progress: Optional callback receiving (event, payload) pairs:
            ``resolve_start``, ``resolved``, ``fetch_start``, ``fetched``,
            ``analyze_start``, ``analyzed``.

    Returns:
        An AnalysisResult with the aggregated report, per-chunk results,
        and per-phase timings.

    Raises:
        FetchError: If the policy content could not be fetched (``fetch_failed``).
        AnalysisError: If no chunks were produced (``no_chunks``) or the model
            returned no valid scores (``no_valid_scores``).
    """
    def _emit(event: str, payload: dict[str, Any]) -> None:
        if on_progress is not None:
            on_progress(event, payload)

    if model is None:
        model = os.getenv("OPENAI_MODEL", "gpt-4o")

    start_total = time.time()

    # --- Phase 1: Resolve URL ---
    _emit("resolve_start", {"url": url})
    start_discovery = time.time()
    resolved_url, _ = resolve_privacy_url(url) if discover else (url, None)
    discovery_time = time.time() - start_discovery
    _emit("resolved", {"resolved_url": resolved_url, "seconds": discovery_time})

    # --- Phase 2: Fetch content ---
    _emit("fetch_start", {"resolved_url": resolved_url})
    start_fetch = time.time()
    content = fetch_policy_text(resolved_url, prefer=fetch_method)
    fetch_time = time.time() - start_fetch
    _emit("fetched", {"chars": len(content) if content else 0, "seconds": fetch_time})

    if not content:
        raise FetchError("fetch_failed", url, resolved_url)

    chunks = split_text_into_chunks(
        content, chunk_size=chunk_size, chunk_overlap=chunk_overlap
    )
    if not chunks:
        raise AnalysisError("no_chunks", url, resolved_url)

    # Merge overflow chunks into the last allowed slot
    if len(chunks) > max_chunks:
        head = chunks[: max_chunks - 1]
        tail = " ".join(chunks[max_chunks - 1 :])
        chunks = head + [tail]

    # --- Phase 3: LLM analysis ---
    _emit("analyze_start", {"num_chunks": len(chunks)})
    start_analysis = time.time()
    results: list[dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(analyze_chunk_json, chunk, model): i
            for i, chunk in enumerate(chunks, 1)
        }
        for future in futures:
            idx = futures[future]
            res = future.result()
            if res:
                res["index"] = idx
                results.append(res)

    analysis_time = time.time() - start_analysis
    total_time = time.time() - start_total
    _emit("analyzed", {"seconds": analysis_time, "valid_chunks": len(results)})

    if not results:
        raise AnalysisError("no_valid_scores", url, resolved_url)

    agg = aggregate_chunk_results(results)
    return AnalysisResult(
        url=url,
        resolved_url=resolved_url,
        model=model,
        num_chunks=len(chunks),
        valid_chunks=len(results),
        aggregate=agg,
        chunk_results=results,
        timings={
            "discovery": discovery_time,
            "fetch": fetch_time,
            "analysis": analysis_time,
            "total": total_time,
        },
    )
