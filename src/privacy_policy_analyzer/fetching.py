"""HTTP and browser-based fetching of policy page content."""

import requests
from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
import chromedriver_autoinstaller

try:
    import trafilatura

    _HAS_TRAFILATURA = True
except Exception:
    trafilatura = None  # type: ignore[assignment]
    _HAS_TRAFILATURA = False

# Selenium timeouts (seconds)
_SELENIUM_PAGE_LOAD_TIMEOUT = 10
_SELENIUM_WAIT_TIMEOUT = 5

# Minimum character thresholds for extracted text
_MIN_TEXT_LENGTH_MAIN = 100    # <main> tag must exceed this to be considered valid
_MIN_TEXT_LENGTH_POLICY = 400  # extracted policy text must exceed this to be kept

_DEFAULT_HEADERS = {
    "User-Agent": "PrivacyPolicyAnalyzer/0.2 (+https://example.org)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def _http_get(url: str, timeout: int = 5) -> requests.Response | None:
    """HTTP GET with basic headers and redirects allowed.

    Args:
        url: The target URL to send the GET request to.
        timeout: Timeout in seconds for the request. Defaults to 5.

    Returns:
        The requests.Response object if status is OK (< 400) and contains text,
        otherwise None.
    """
    try:
        r = requests.get(
            url,
            timeout=timeout,
            allow_redirects=True,
            headers=_DEFAULT_HEADERS,
        )
        return r if (r.status_code < 400 and r.text) else None
    except Exception:
        return None


def _fetch_text(url: str, timeout: int = 5) -> str | None:
    """Fetch raw text content via GET.

    Args:
        url: The target URL to fetch text from.
        timeout: Timeout in seconds for the request. Defaults to 5.

    Returns:
        The response text content as a string, or None if the request failed.
    """
    r = _http_get(url, timeout=timeout)
    return r.text if r else None


def _head_ok(url: str, timeout: int = 3) -> bool:
    """Lightweight existence probe using HEAD; redirects considered OK.

    Args:
        url: The target URL to probe.
        timeout: Timeout in seconds for the request. Defaults to 3.

    Returns:
        True if the URL exists and returns a successful status code (2xx) or
        a redirect status code (3xx), False otherwise.
    """
    try:
        r = requests.head(
            url,
            timeout=timeout,
            allow_redirects=True,
            headers=_DEFAULT_HEADERS,
        )
        if 200 <= r.status_code < 300:
            return True
        if r.status_code in (301, 302, 303, 307, 308):
            return True
        return False
    except Exception:
        return False


def _extract_text_http(url: str) -> str | None:
    """Fetch text from <main> tag, fallback to <body>.

    Args:
        url: The target URL to extract text from.

    Returns:
        The extracted policy text if its length is greater than or equal to
        _MIN_TEXT_LENGTH_POLICY, otherwise None.
    """
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
    opts.add_argument("--blink-settings=imagesEnabled=false")  # do not load images
    opts.page_load_strategy = "eager"  # do not wait for full load
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
