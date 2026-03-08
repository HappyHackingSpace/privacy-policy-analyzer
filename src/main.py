import time
import argparse
import gzip
import io
import json
import os
import pathlib
import re
import sys
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import urljoin, urlparse
from analyzer.prompts import SYSTEM_SCORER, build_user_prompt
from analyzer.scoring import aggregate_chunk_results
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from langchain_text_splitters import RecursiveCharacterTextSplitter
from openai import OpenAI

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
import chromedriver_autoinstaller

ROOT = pathlib.Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

try:
    import trafilatura

    _HAS_TRAFILATURA = True
except Exception:
    trafilatura = None  # type: ignore[assignment]
    _HAS_TRAFILATURA = False


load_dotenv()
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

# Selenium timeouts (seconds)
_SELENIUM_PAGE_LOAD_TIMEOUT = 10
_SELENIUM_WAIT_TIMEOUT = 5

# Minimum character thresholds for extracted text
_MIN_TEXT_LENGTH_MAIN = 100    # <main> tag must exceed this to be considered valid
_MIN_TEXT_LENGTH_POLICY = 400  # extracted policy text must exceed this to be kept

def _is_privacy_like(s: str) -> bool:
    """Heuristic check for privacy-related terms in a string."""
    s = (s or "").lower()
    return any(k in s for k in _PRIVACY_CUES)


def _http_get(url: str, timeout: int = 5) -> requests.Response | None:
    """HTTP GET with basic headers and redirects allowed."""
    try:
        r = requests.get(
            url,
            timeout=timeout,
            allow_redirects=True,
            headers={
                "User-Agent": "PrivacyPolicyAnalyzer/0.2 (+https://example.org)",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        return r if (r.status_code < 400 and r.text) else None
    except Exception:
        return None


def _fetch_text(url: str, timeout: int = 5) -> str | None:
    """Fetch raw text content via GET."""
    r = _http_get(url, timeout=timeout)
    return r.text if r else None


def _head_ok(url: str, timeout: int = 3) -> bool:
    """Lightweight existence probe using HEAD; redirects considered OK."""
    try:
        r = requests.head(
            url,
            timeout=timeout,
            allow_redirects=True,
            headers={
                "User-Agent": "PrivacyPolicyAnalyzer/0.2 (+https://example.org)",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        if 200 <= r.status_code < 300:
            return True
        if r.status_code in (301, 302, 303, 307, 308):
            return True
        return False
    except Exception:
        return False


def _extract_text_http(url: str) -> str | None:
    """Fetch text from <main> tag, fallback to <body>."""
    if _HAS_TRAFILATURA:
        try:
            downloaded = trafilatura.fetch_url(url)
            if downloaded:
                text = trafilatura.extract(downloaded, include_formatting=False) or ""
                t = text.strip()
                return t if len(t) >= _MIN_TEXT_LENGTH_POLICY else None
        except Exception:
            pass
    r = _http_get(url)
    if not r:
        return None
    
    soup = BeautifulSoup(r.text, "html.parser")
    
    # Extraction Logic: Prefer <main>, fallback to <body>
    content_element = soup.find("main")
    if not content_element or not content_element.get_text(strip=True):
        content_element = soup.find("body")
        
    t = content_element.get_text("\n").strip() if content_element else ""
    return t if len(t) >= _MIN_TEXT_LENGTH_POLICY else None


def fetch_content_with_selenium(url: str) -> str | None:
    """Return visible text using headless Chrome; robust for dynamic pages."""
    chromedriver_autoinstaller.install()
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-extensions")
    opts.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
    )
    opts.add_argument("--blink-settings=imagesEnabled=false") # do not load images
    opts.page_load_strategy = 'eager'  # do not wait for full load
    driver = webdriver.Chrome(options=opts)
    try:
        driver.set_page_load_timeout(_SELENIUM_PAGE_LOAD_TIMEOUT)
        driver.get(url)
        WebDriverWait(driver, _SELENIUM_WAIT_TIMEOUT).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        
        # Selenium Extraction: Prefer <main>, fallback to <body>
        try:
            content_element = driver.find_element(By.TAG_NAME, "main")
            text = content_element.get_attribute("innerText")
            if text and len(text.strip()) > _MIN_TEXT_LENGTH_MAIN:
                return text
        except Exception:
            pass
            
        return driver.find_element(By.TAG_NAME, "body").get_attribute("innerText")
    except Exception:
        return None
    finally:
        driver.quit()


def fetch_policy_text(url: str, prefer: str = "auto") -> str | None:
    """Fetch policy text using HTTP first; fallback to Selenium if needed."""
    if prefer in ("auto", "http"):
        t = _extract_text_http(url)
        if t:
            return t
        if prefer == "http":
            return None
    return fetch_content_with_selenium(url)


def _light_verify(url: str) -> bool:
    """Low-cost check that a URL likely points to a privacy policy page."""
    return _head_ok(url, timeout=3) #only check for existence


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
    """Return the priority index of a URL based on regex patterns. Lower is better."""
    for idx, pattern in enumerate(_PRIVACY_REGEX_PATTERNS):
        if pattern.search(url):
            return idx
    return 999


def find_best_policy_url(html_content: str, base_url: str) -> tuple[str, int] | None:
    """
    Finds the single best-matching URL for a privacy-related link on the page.
    Returns (url, priority_index).
    Lower = better.  Returns _NO_MATCH_PRIORITY (999) when nothing matches.
    """
    if not html_content:
        return None
        
    soup = BeautifulSoup(html_content, "html.parser")
    
    # Store tuples of (priority_index, full_url)
    matches: list[tuple[int, str]] = []
    seen_urls = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]
        try:
            full_url = urljoin(base_url, href)
        except Exception:
            continue

        if not full_url.startswith("http"):
            continue
            
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)

        # Check regex priority
        p = _get_url_priority(full_url)
        if p < 999:
            matches.append((p, full_url))

    if not matches:
        return None

    # Sort by priority index (ascending), get the best match
    matches.sort(key=lambda x: x[0])
    return (matches[0][1], matches[0][0])


def _improve_candidate(candidate_url: str) -> str:
    """
    If the found candidate is a generic 'hub' page (e.g. /privacy),
    fetch it and check if it links to a more specific policy (e.g. /privacy-policy).
    """
    # 0=privacy-policy, 1=privacy/policy, 2=privacy-policy-x
    # Generally, if we found something better than generic 'privacy' (index 6), we stick with it.
    # But let's say anything > 2 is worth checking deeper.
    priority = _get_url_priority(candidate_url)
    if priority <= 2:
        return candidate_url

    print(f"DEBUG: Candidate '{candidate_url}' is generic (Priority {priority}). Checking for deep links...")
    r = _http_get(candidate_url)
    if not r:
        return candidate_url

    match_info = find_best_policy_url(r.text, r.url)
    if match_info:
        deep_url, deep_priority = match_info
        if deep_priority < priority:
            print(f"DEBUG: Upgraded to deep link '{deep_url}' (Priority {deep_priority})")
            return deep_url
    
    return candidate_url


def _collect_link_candidates(html_content: str, base_url: str, limit: int = 100) -> list[tuple[str, str]]:
    """
    Collect all privacy-related link candidates from HTML.
    Returns list of (full_url, anchor_text) tuples, de-duplicated.
    """
    if not html_content:
        return []
    
    soup = BeautifulSoup(html_content, "html.parser")
    candidates: dict[str, str] = {}  # url -> best_anchor_text
    
    for a in soup.find_all("a", href=True):
        href = a["href"]
        try:
            full_url = urljoin(base_url, href)
        except Exception:
            continue
        
        if not full_url.startswith("http"):
            continue
        
        # Get anchor text
        anchor_text = (a.get_text(strip=True) or "").lower()
        
        #select candidates based on privacy-likeness or priority instead of just any link
        url_priority = _get_url_priority(full_url)
        anchor_priority = _get_url_priority(anchor_text)
        if (
            _is_privacy_like(full_url)
            or _is_privacy_like(anchor_text)
            or url_priority < 999
            or anchor_priority < 999
        ):
            existing = candidates.get(full_url, "")
            if (
                not existing
                or ("privacy policy" in anchor_text and "privacy policy" not in existing)
            ):
                candidates[full_url] = anchor_text
        if len(candidates) >= limit:
            break
    
    return [(url, text) for url, text in candidates.items()]


def _score_candidate(url: str, anchor_text: str = "") -> tuple[int, int]:
    """
    Score a candidate URL and anchor text.
    Returns (priority_index, anchor_bonus) where lower values are better.
    anchor_bonus: -1 if anchor explicitly says "privacy policy", 0 otherwise.
    """
    url_priority = _get_url_priority(url)
    anchor_bonus = 0
    
    # Give extra credit if anchor text explicitly mentions "privacy policy"
    anchor_lower = (anchor_text or "").lower()
    if "privacy policy" in anchor_lower or "privacy-policy" in anchor_lower:
        anchor_bonus = -1  # Lower is better, so -1 boosts the score
    
    return (url_priority, anchor_bonus)


def _pick_best_verified_candidate(candidates: list[tuple[str, str]], max_verify: int = 5) -> str | None:
    """
    Score candidates, verify top ones, return the best verified candidate.
    """
    if not candidates:
        return None
    
    # Score all candidates
    scored = [(url, text, _score_candidate(url, text)) for url, text in candidates]
    # Sort by (priority, anchor_bonus), ascending
    scored.sort(key=lambda x: (x[2][0], x[2][1]))
    
    # Verify top candidates (up to max_verify)
    for i, (url, text, score) in enumerate(scored[:max_verify]):
        #if the score is already very good, skip verification
        if score[0] <= 1: 
            return url
        if _light_verify(url):
            print(f"DEBUG: Selected URL '{url}' from {len(candidates)} candidates (score: {score})")
            return url
    
    return None


def resolve_privacy_url(input_url: str) -> tuple[str, str | None]:
    """
    Resolve a likely privacy policy URL using link-based discovery (primary),
    then sitemap discovery, then common paths (fallback).
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
                print(f"DEBUG: Found via sitemap: {cand}")
                return cand, input_url
    
    # === PHASE 3: Common paths (last resort) ===
    for candidate_url in (base + path for path in _COMMON_PATHS):
        if _light_verify(candidate_url):
            print(f"DEBUG: Found via common path: {candidate_url}")
            return candidate_url, input_url

    return input_url, None


def split_text_into_chunks(
    text: str, chunk_size: int = 3500, chunk_overlap: int = 350
) -> list[str]:
    """Split text into chunks using paragraph-first recursive boundaries."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    return splitter.split_text(text or "")


def analyze_chunk_json(text_chunk: str, model: str) -> dict[str, Any] | None:
    """Analyze a text chunk with the LLM and return one JSON object."""
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")

    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set. Configure your .env file.")
    #client = OpenAI(api_key=api_key)
    client = OpenAI(api_key=api_key, base_url=base_url)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_SCORER},
            {"role": "user", "content": build_user_prompt(text_chunk)},
        ],
        temperature=0,
        max_tokens=2000, #changed from 300 to 2000
        response_format={"type": "json_object"},
    )
    content = (resp.choices[0].message.content or "").strip()
    try:
        return json.loads(content)  # type: ignore[no-any-return]
    except Exception:
        return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Privacy Policy Analyzer (auto-discovery + JSON scoring)"
    )
    parser.add_argument("--url", type=str, help="Site or policy URL to analyze")
    parser.add_argument(
        "--model",
        type=str,
        default=os.getenv("OPENAI_MODEL", "gpt-4o"),
        help="OpenAI chat model, e.g., gpt-4o",
    )
    parser.add_argument(
        "--chunk-size", type=int, default=10000, help="Character-based chunk size"
    )
    parser.add_argument(
        "--chunk-overlap", type=int, default=350, help="Overlap between chunks"
    )
    parser.add_argument(
        "--max-chunks",
        type=int,
        default=30,
        help="Hard cap for analyzed chunks (tail chunks are merged).",
    )
    parser.add_argument(
        "--report",
        type=str,
        choices=["summary", "detailed", "full"],
        default="summary",
        help="Report detail level",
    )
    parser.add_argument(
        "--fetch",
        type=str,
        choices=["auto", "http", "selenium"],
        default="auto",
        help="Fetch method preference",
    )
    parser.add_argument(
        "--no-discover",
        action="store_true",
        help="Skip auto-discovery and analyze the given URL as-is",
    )

    args = parser.parse_args()
    input_url = args.url or input("Enter a site (or privacy policy) URL: ").strip()

    start_total = time.time()
    
    print(f"\n[1/3] Resolving Privacy URL...")
    start_discovery = time.time()
    
    resolved_url, _ = (
        (input_url, None) if args.no_discover else resolve_privacy_url(input_url)
    )
    discovery_time = time.time() - start_discovery
    print(f"DEBUG: Discovery took {discovery_time:.2f}s. Resolved to: {resolved_url}")
    
    print(f"[2/3] Fetching Policy Content...")
    start_fetch = time.time()
    content = fetch_policy_text(resolved_url, prefer=args.fetch)
    fetch_time = time.time() - start_fetch
    print(f"DEBUG: Fetching took {fetch_time:.2f}s. Content length: {len(content) if content else 0} chars.")
    
    if not content:
        print(
            json.dumps(
                {
                    "status": "error",
                    "reason": "fetch_failed",
                    "url": input_url,
                    "resolved_url": resolved_url,
                }
            )
        )
        return

    chunks = split_text_into_chunks(
        content, chunk_size=args.chunk_size, chunk_overlap=args.chunk_overlap
    )
    if not chunks:
        print(
            json.dumps(
                {
                    "status": "error",
                    "reason": "no_chunks",
                    "url": input_url,
                    "resolved_url": resolved_url,
                }
            )
        )
        return

    if len(chunks) > args.max_chunks:
        head = chunks[: args.max_chunks - 1]
        tail = " ".join(chunks[args.max_chunks - 1 :])
        chunks = head + [tail]

    start_analysis = time.time()
    results: list[dict[str, Any]] = []
    print(f"[3/3]Analyzing {len(chunks)} chunks in parallel...")
    
    # Parallel analysis of chunks
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(analyze_chunk_json, chunk, args.model): i for i, chunk in enumerate(chunks, 1)}
        for future in futures:
            idx = futures[future]
            res = future.result()
            if res:
                res["index"] = idx
                results.append(res)

    analysis_time = time.time() - start_analysis
    total_time = time.time() - start_total
    
    if not results:
        print(
            json.dumps(
                {
                    "status": "error",
                    "reason": "no_valid_scores",
                    "url": input_url,
                    "resolved_url": resolved_url,
                }
            )
        )
        return

    agg = aggregate_chunk_results(results)
    base = {
        "status": "ok",
        "url": input_url,
        "resolved_url": resolved_url,
        "model": args.model,
        "chunks": len(chunks),
        "valid_chunks": len(results),
    }

    if args.report == "summary":
        out = {
            **base,
            "overall_score": agg["overall_score"],
            "confidence": agg["confidence"],
            "top_strengths": agg["top_strengths"],
            "top_risks": agg["top_risks"],
            "red_flags_count": len(agg["red_flags"]),
        }
    elif args.report == "detailed":
        out = {**base, **agg}
    else:
        out = {**base, **agg, "chunks": results}

    print(json.dumps(out, ensure_ascii=False, indent=2))
    print("\n" + "="*40)
    print(f"Performance Summary for model:")
    print("-" * 40)
    print(f"Discovery time:    {discovery_time:>6.2f}s")
    print(f"Fetching time:   {fetch_time:>6.2f}s")
    print(f"LLM Analysis time:          {analysis_time:>6.2f}s")
    print(f"Total time :          {total_time:>6.2f}s")
    if chunks:
        print(f"Average time needed per chunk:    {(analysis_time/len(chunks)):>6.2f}s")
    print("="*40 + "\n")

if __name__ == "__main__":
    main()
