"""Discovery of a site's privacy policy URL (links, sitemaps, common paths)."""

import gzip
import io
import re
import xml.etree.ElementTree as ET
from urllib.parse import urljoin, urlparse

import click
from bs4 import BeautifulSoup

from privacy_policy_analyzer.fetching import _fetch_text, _head_ok, _http_get

# ---------------------------------------------------------------------------
# Priority-based regex patterns for privacy URL discovery.
# Lower index = higher priority. The resolver picks the URL matching the
# lowest-index pattern, so "privacy-policy" (idx 0) always beats a generic
# "privacy" (idx 6) hub page.
# ---------------------------------------------------------------------------
_PRIVACY_REGEX_PATTERNS = [
    re.compile(r"privacy-policy\b", re.IGNORECASE),          # 1. Target: Full legal text
    re.compile(r"\bprivacy/policy\b", re.IGNORECASE),        # 2
    re.compile(r"privacy-policy-[a-z]+", re.IGNORECASE),    # 3
    re.compile(r"\bdata-protection\b", re.IGNORECASE),       # 4
    re.compile(r"\bsecurity-policy\b", re.IGNORECASE),       # 5
    re.compile(r"\blegal-notice\b", re.IGNORECASE),          # 6
    re.compile(r"\bprivacy\b", re.IGNORECASE),               # 7. Target: Menu/Hub page
    re.compile(r"\blegal\b", re.IGNORECASE),                 # 8
    re.compile(r"\bterms\b", re.IGNORECASE),                 # 9
]

_PRIVACY_CUES = (
    "privacy",
    "privacy-policy",
    "privacy_notice",
    "privacy-notice",
    "gizlilik",
    "gizlilik-politik",
    "veri koruma",
    "privacidad",
    "politica de privacidad",
    "privacidade",
    "politica de privacidade",
    "datenschutz",
    "confidentialité",
    "politique de confidentialité",
    "informativa privacy",
    "informativa sulla privacy",
    "個人情報",
    "プライバシー",
    "隐私",
    "隱私",
    "개인정보",
    "privatsphäre",
)

_PRIVACY_KEYWORDS = [
    "privacy policy",
    "privacy-policy",
]

_COMMON_PATHS = [
    "/privacy",
    "/privacy-policy",
    "/privacy_policy",
    "/legal/privacy",
    "/legal/privacy-policy",
    "/policies/privacy",
    "/en/privacy",
    "/en/privacy-policy",
    "/tr/gizlilik",
    "/tr/gizlilik-politikasi",
]

# Priority/discovery configurations
_NO_MATCH_PRIORITY = 999


def _is_privacy_like(s: str) -> bool:
    """Heuristic check for privacy-related terms in a string.

    Args:
        s: The string to check for privacy cues.

    Returns:
        True if any privacy cue is found in the string, False otherwise.
    """
    s = (s or "").lower()
    return any(k in s for k in _PRIVACY_CUES)


def _light_verify(url: str) -> bool:
    """Low-cost check that a URL likely points to a privacy policy page.

    Args:
        url: The candidate URL to verify.

    Returns:
        True if the URL passes the lightweight HEAD existence probe, False otherwise.
    """
    return _head_ok(url, timeout=3)  # only check for existence


def _get_sitemaps_from_robots(base_url: str) -> list[str]:
    """Extract sitemap URLs from robots.txt; also try the default /sitemap.xml."""
    parsed = urlparse(base_url)
    robots = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    out: list[str] = []
    txt = _fetch_text(robots)
    if txt:
        for line in txt.splitlines():
            line = line.strip()
            if line.lower().startswith("sitemap:"):
                sm = line.split(":", 1)[1].strip()
                if sm:
                    out.append(sm)
    default_sm = f"{parsed.scheme}://{parsed.netloc}/sitemap.xml"
    if default_sm not in out:
        out.append(default_sm)
    seen, uniq = set(), []
    for u in out:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    return uniq


def _fetch_sitemap_urls(url: str, max_urls: int = 50) -> list[str]:
    """Return privacy-like URLs found in the sitemap (gz and index supported)."""
    r = _http_get(url)
    if not r:
        return []
    data = r.content
    if url.endswith(".gz"):
        try:
            data = gzip.GzipFile(fileobj=io.BytesIO(data)).read()
        except Exception:
            return []
    try:
        root = ET.fromstring(data)
    except Exception:
        return []
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls: list[str] = []
    if root.tag.endswith("sitemapindex"):
        for i, loc in enumerate(root.findall(".//sm:loc", ns)):
            if i >= 5:
                break
            child = (loc.text or "").strip()
            urls.extend(_fetch_sitemap_urls(child, max_urls=max_urls))
            if len(urls) >= max_urls:
                break
    else:
        for loc in root.findall(".//sm:loc", ns):
            u = (loc.text or "").strip()
            if u and _is_privacy_like(u):
                urls.append(u)
                if len(urls) >= max_urls:
                    break
    seen, uniq = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    return uniq


def _get_url_priority(url: str) -> int:
    """Return the priority index of a URL based on regex patterns. Lower is better.

    Args:
        url: The URL to evaluate.

    Returns:
        The priority index (0-based) based on the matching regex pattern,
        or _NO_MATCH_PRIORITY if no pattern matches.
    """
    for idx, pattern in enumerate(_PRIVACY_REGEX_PATTERNS):
        if pattern.search(url):
            return idx
    return _NO_MATCH_PRIORITY


def _collect_link_candidates(html_content: str, base_url: str, limit: int = 100) -> list[tuple[str, str]]:
    """Collect all privacy-related link candidates from HTML.

    Args:
        html_content: The HTML page content to extract links from.
        base_url: The base URL of the page to resolve relative URLs.
        limit: Maximum number of candidate links to collect. Defaults to 100.

    Returns:
        List of (full_url, anchor_text) tuples, de-duplicated.
    """
    if not html_content:
        return []

    soup = BeautifulSoup(html_content, "html.parser")
    candidates: dict[str, str] = {}  # url -> best_anchor_text

    for a in soup.find_all("a", href=True):
        href = a["href"]
        try:
            full_url = urljoin(base_url, href)
        except Exception as e:
            click.secho(f"      DEBUG: URL join error for '{href}': {e}", fg="yellow", dim=True, err=True)
            continue

        if not full_url.startswith("http"):
            continue

        # Get anchor text
        anchor_text = (a.get_text(strip=True) or "").lower()

        # select candidates based on privacy-likeness or priority instead of just any link
        url_priority = _get_url_priority(full_url)
        anchor_priority = _get_url_priority(anchor_text)
        if (
            _is_privacy_like(full_url)
            or _is_privacy_like(anchor_text)
            or url_priority < _NO_MATCH_PRIORITY
            or anchor_priority < _NO_MATCH_PRIORITY
        ):
            existing = candidates.get(full_url, "")
            if (
                not existing
                or (any(kw in anchor_text for kw in _PRIVACY_KEYWORDS) and not any(kw in existing for kw in _PRIVACY_KEYWORDS))
            ):
                candidates[full_url] = anchor_text
        if len(candidates) >= limit:
            break

    return [(url, text) for url, text in candidates.items()]


def _score_candidate(url: str, anchor_text: str = "") -> tuple[int, int]:
    """Score a candidate URL and anchor text.

    Args:
        url: The candidate URL to score.
        anchor_text: The anchor text associated with the candidate URL. Defaults to "".

    Returns:
        A tuple of (priority_index, anchor_bonus) where lower values are better.
        anchor_bonus is -1 if anchor explicitly matches privacy keywords, otherwise 0.
    """
    url_priority = _get_url_priority(url)
    anchor_bonus = 0

    # Give extra credit if anchor text explicitly mentions "privacy policy"
    anchor_lower = (anchor_text or "").lower()
    if any(kw in anchor_lower for kw in _PRIVACY_KEYWORDS):
        anchor_bonus = -1  # Lower is better, so -1 boosts the score

    return (url_priority, anchor_bonus)


def _pick_best_verified_candidate(candidates: list[tuple[str, str]], max_verify: int = 5) -> str | None:
    """Score candidates, verify top ones, and return the best verified candidate URL.

    Args:
        candidates: A list of (url, anchor_text) candidates.
        max_verify: Maximum number of candidates to verify. Defaults to 5.

    Returns:
        The best verified privacy policy URL, or None if no candidate is verified.
    """
    if not candidates:
        return None

    # Score all candidates
    scored = [(url, text, _score_candidate(url, text)) for url, text in candidates]
    # Sort by (priority, anchor_bonus), ascending
    scored.sort(key=lambda x: (x[2][0], x[2][1]))

    # Verify top candidates (up to max_verify)
    for i, (url, text, score) in enumerate(scored[:max_verify]):
        # if the score is already very good, skip verification
        if score[0] <= 1:
            return url
        if _light_verify(url):
            click.secho(f"      DEBUG: Selected URL '{url}' from {len(candidates)} candidates (score: {score})", fg="yellow", dim=True, err=True)
            return url

    return None


def resolve_privacy_url(input_url: str) -> tuple[str, str | None]:
    """Resolve a likely privacy policy URL using link-based discovery, sitemaps, or common paths.

    Args:
        input_url: The initial URL provided to find a privacy policy for.

    Returns:
        A tuple of (resolved_url, original_input_url).
    """
    # If input looks like privacy policy already
    if _is_privacy_like(input_url):
        return input_url, None

    parsed = urlparse(input_url)
    base = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")

    # === PHASE 1: Link-based discovery ===
    # Collect links from input page and homepage
    candidates_set: dict[str, str] = {}  # url -> anchor_text

    for page_url in (input_url, base):
        if not (resp := _http_get(page_url)):
            continue

        for url, text in _collect_link_candidates(resp.text, resp.url, limit=100):
            candidates_set.setdefault(url, text)

    if candidates_set:
        candidates_list = [(url, text) for url, text in candidates_set.items()]
        best_url = _pick_best_verified_candidate(candidates_list, max_verify=5)
        if best_url:
            return best_url, input_url

    # === PHASE 2: Sitemap-based discovery ===
    for sm in _get_sitemaps_from_robots(base):
        for cand in _fetch_sitemap_urls(sm, max_urls=50):
            if _light_verify(cand):
                click.secho(f"      DEBUG: Found via sitemap: {cand}", fg="yellow", dim=True, err=True)
                return cand, input_url

    # === PHASE 3: Common paths (last resort) ===
    for candidate_url in (base + path for path in _COMMON_PATHS):
        if _light_verify(candidate_url):
            click.secho(f"      DEBUG: Found via common path: {candidate_url}", fg="yellow", dim=True, err=True)
            return candidate_url, input_url

    return input_url, None
