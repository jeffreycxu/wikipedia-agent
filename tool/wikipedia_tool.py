import threading
import time
import requests
from rank_bm25 import BM25Okapi
from config import MAX_FETCHED_PAGES, MAX_CONTENT_CHARS, TOP_K_CHUNKS, WIKI_MAX_RETRIES, WIKI_BACKOFF_BASE, WIKI_RATE_LIMIT_WAIT, WIKI_RATE_LIMIT_INTERVAL

WIKI_API = "https://en.wikipedia.org/w/api.php"
HEADERS = {"User-Agent": "wiki-agent (local development; Jeffrey Xu)"}


class WikipediaRateLimitError(Exception):
    """Raised after a 429 backoff so run_case can restart the case with clean latency."""


class _WikiRateLimiter:
    """Thread-safe rate limiter: enforces a minimum interval between Wikipedia API requests."""
    def __init__(self, interval: float):
        self._lock = threading.Lock()
        self._last_request = 0.0
        self._interval = interval

    def wait(self):
        with self._lock:
            now = time.monotonic()
            wait_time = self._interval - (now - self._last_request)
            if wait_time > 0:
                time.sleep(wait_time)
            self._last_request = time.monotonic()

_rate_limiter = _WikiRateLimiter(WIKI_RATE_LIMIT_INTERVAL)

# ── Global 429 backoff gate ───────────────────────────────────────────────────
# Cleared for WIKI_RATE_LIMIT_WAIT seconds on any 429.
# All request functions block on it so no new HTTP calls go out during backoff.
_request_gate = threading.Event()
_request_gate.set()
_gate_setup_lock = threading.Lock()


def _enter_backoff():
    """Block all Wikipedia threads for WIKI_RATE_LIMIT_WAIT seconds.
    Only the first thread starts the timer; the rest just wait on the gate."""
    with _gate_setup_lock:
        if _request_gate.is_set():
            _request_gate.clear()
            def _reopen():
                time.sleep(WIKI_RATE_LIMIT_WAIT)
                _request_gate.set()
                print("Wikipedia rate limit cooldown complete — resuming requests.")
            threading.Thread(target=_reopen, daemon=True).start()
            print("Wikipedia 429 — pausing all requests for {s}s...".format(s=WIKI_RATE_LIMIT_WAIT))
    _request_gate.wait()


def get_wikipedia_tool_definition():
    return {
        "name": "search_wikipedia",
        "description": "Searches Wikipedia and returns relevant information",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search term to look up on Wikipedia"
                },
            },
            "required": ["query"]
        }
    }


def _search_titles(query: str) -> list:
    _request_gate.wait()
    _rate_limiter.wait()
    resp = requests.get(WIKI_API, params={
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srlimit": MAX_FETCHED_PAGES,
        "format": "json",
    }, headers=HEADERS, timeout=10)
    resp.raise_for_status()
    return [item["title"] for item in resp.json().get("query", {}).get("search", [])]


def _fetch_page_content(title: str):
    _request_gate.wait()
    _rate_limiter.wait()
    resp = requests.get(WIKI_API, params={
        "action": "query",
        "prop": "extracts",
        "explaintext": True,
        "titles": title,
        "format": "json",
        "redirects": 1,
    }, headers=HEADERS, timeout=10)
    resp.raise_for_status()
    pages = resp.json().get("query", {}).get("pages", {})
    page = next(iter(pages.values()))

    if page.get("ns") != 0 or "missing" in page:
        return None

    extract = page.get("extract", "")
    if not extract:
        return None

    if "may refer to:" in extract[:200].lower():
        return None

    return extract


def _do_search(query: str) -> str:
    titles = _search_titles(query)
    if not titles:
        return "No Wikipedia results found for the given query."

    chunks = []
    total_chars = 0
    for title in titles:
        try:
            content = _fetch_page_content(title)
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 429:
                raise
            continue
        except requests.exceptions.RequestException:
            continue
        if content is None:
            continue

        remaining = MAX_CONTENT_CHARS - total_chars
        content = content[:remaining]
        total_chars += len(content)

        for para in content.split("\n\n"):
            para = para.strip()
            if para:
                chunks.append(f"[{title}] {para}")

        if total_chars >= MAX_CONTENT_CHARS:
            break

    if not chunks:
        return "Could not retrieve content for any Wikipedia pages."

    tokenized = [c.lower().split() for c in chunks]
    bm25 = BM25Okapi(tokenized)
    scores = bm25.get_scores(query.lower().split())
    top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:TOP_K_CHUNKS]

    return "\n\n".join(chunks[i] for i in top_indices)


def execute_wikipedia_search(query: str) -> str:
    last_error = None
    for attempt in range(WIKI_MAX_RETRIES):
        try:
            return _do_search(query)
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 429:
                _enter_backoff()
                raise WikipediaRateLimitError("Wikipedia 429") from e
            last_error = e
        except requests.exceptions.RequestException as e:
            last_error = e

        if attempt < WIKI_MAX_RETRIES - 1:
            sleep_s = WIKI_BACKOFF_BASE * (2 ** attempt)
            print("Wikipedia API error (attempt {a}/{n}), retrying in {s}s...".format(
                a=attempt + 1, n=WIKI_MAX_RETRIES, s=sleep_s
            ))
            time.sleep(sleep_s)

    print("wikipedia error: max retries")
    return "Search Error: Wikipedia API unavailable after {n} attempts. ({e})".format(
        n=WIKI_MAX_RETRIES, e=last_error
    )
