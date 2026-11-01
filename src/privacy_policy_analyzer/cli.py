"""Click CLI for the privacy policy analyzer (thin wrapper over the library).

Installed as the ``ppa`` console script::

    ppa https://example.com --report detailed
"""

import json
import os
from typing import Any

import click

from privacy_policy_analyzer.analysis import analyze
from privacy_policy_analyzer.models import AnalyzerError


@click.command()
@click.argument("url", required=False)
@click.option("--url", "url_option", default=None, hidden=True, help="Site or policy URL to analyze (legacy spelling; prefer the positional argument).")
@click.option("--model", default=lambda: os.getenv("OPENAI_MODEL", "gpt-4o"), help="LLM model name.")
@click.option("--chunk-size", default=10000, type=int, help="Character-based chunk size.")
@click.option("--chunk-overlap", default=350, type=int, help="Overlap between chunks.")
@click.option("--max-chunks", default=30, type=int, help="Hard cap for analyzed chunks.")
@click.option("--report", type=click.Choice(["summary", "detailed", "full"]), default="summary", help="Report detail level.")
@click.option("--fetch", "fetch_method", type=click.Choice(["auto", "http", "selenium"]), default="auto", help="Fetch method preference.")
@click.option("--no-discover", is_flag=True, help="Skip auto-discovery; analyze the given URL as-is.")
@click.option("--json", "json_output", is_flag=True, help="Print only the JSON report (no progress or performance output).")
def main(
    url: str | None,
    url_option: str | None,
    model: str,
    chunk_size: int,
    chunk_overlap: int,
    max_chunks: int,
    report: str,
    fetch_method: str,
    no_discover: bool,
    json_output: bool,
) -> None:
    """Privacy Policy Analyzer – auto-discovery + JSON scoring.

    URL is the site homepage or a direct privacy policy URL.
    """
    url = url or url_option
    if not url:
        url = click.prompt("Enter a site (or privacy policy) URL")

    def on_progress(event: str, payload: dict[str, Any]) -> None:
        if json_output:
            return
        if event == "resolve_start":
            click.secho("\n[1/3] Resolving Privacy URL...", fg="cyan")
        elif event == "resolved":
            click.echo(
                f"      Resolved to: {click.style(payload['resolved_url'], fg='green')}"
                f" ({payload['seconds']:.2f}s)"
            )
        elif event == "fetch_start":
            click.secho("[2/3] Fetching Policy Content...", fg="cyan")
        elif event == "fetched":
            click.echo(
                f"      Content length: {payload['chars']} chars"
                f" ({payload['seconds']:.2f}s)"
            )
        elif event == "analyze_start":
            click.secho(
                f"[3/3] Analyzing {payload['num_chunks']} chunk(s) in parallel...",
                fg="cyan",
            )

    error_messages = {
        "fetch_failed": "Error: Failed to fetch policy content.",
        "no_chunks": "Error: No text chunks produced.",
        "no_valid_scores": "Error: No valid scores returned by model.",
    }

    try:
        result = analyze(
            url,
            model=model,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            max_chunks=max_chunks,
            fetch_method=fetch_method,
            discover=not no_discover,
            on_progress=on_progress,
        )
    except AnalyzerError as exc:
        click.secho(error_messages.get(exc.reason, f"Error: {exc.reason}."), fg="red", err=True)
        click.echo(json.dumps(exc.to_dict()))
        raise SystemExit(1)

    click.echo(json.dumps(result.to_dict(report=report), ensure_ascii=False, indent=2))

    if json_output:
        return

    # --- Performance summary (stderr, won't pollute JSON stdout) ---
    t = result.timings
    click.secho("\n" + "=" * 40, fg="yellow", err=True)
    click.secho("Performance Summary", bold=True, err=True)
    click.secho("-" * 40, fg="yellow", err=True)
    click.echo(f"  Discovery:    {t['discovery']:>6.2f}s", err=True)
    click.echo(f"  Fetching:     {t['fetch']:>6.2f}s", err=True)
    click.echo(f"  LLM Analysis: {t['analysis']:>6.2f}s", err=True)
    click.echo(f"  Total:        {t['total']:>6.2f}s", err=True)
    if result.num_chunks:
        click.echo(f"  Per chunk:    {(t['analysis'] / result.num_chunks):>6.2f}s", err=True)
    click.secho("=" * 40 + "\n", fg="yellow", err=True)


if __name__ == "__main__":
    main()
