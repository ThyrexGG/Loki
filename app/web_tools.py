"""Web search and page reading for Loki chat (ADR-011).

- Search: DuckDuckGo's plain HTML results page (no API key, no account). When DuckDuckGo is busy (it answers
  HTTP 202 to rate-limit automated searches) or returns nothing, Yahoo's results page is used instead
  (Bing was tried and returned unrelated results to automated searches).
- Read: fetches a public http(s) page and extracts readable text.

Safety boundaries:
- Only public internet hosts: loopback, private, link-local, reserved and multicast addresses are
  refused (also after every redirect), so a page or prompt can never make Loki read this PC or the
  home network (e.g. http://127.0.0.1:8420/... or a router admin page).
- Ports 80/443 only, http/https only, GET only, generic User-Agent (nothing identifying). No cookies are kept:
  a search engine's cookie lives only for that one search.
- Size cap (1.5 MB download, ~2,500 chars kept per page) and short timeouts.
- Returned text is always treated as UNTRUSTED data by the caller (wrapped in <untrusted_data>).
"""

from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from typing import Any
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
SEARCH_URL = "https://html.duckduckgo.com/html/"
YAHOO_URL = "https://search.yahoo.com/search"
MAX_DOWNLOAD_BYTES = 1_500_000
PAGE_CHARS = 2500
TIMEOUT = httpx.Timeout(10.0, connect=5.0)
MAX_REDIRECTS = 4


class WebError(Exception):
    pass


# ---------------------------------------------------------------------------
# URL safety
# ---------------------------------------------------------------------------
def _is_public_ip(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    return not (addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved
                or addr.is_multicast or addr.is_unspecified)


async def check_public_url(url: str) -> str:
    """Return the URL if it is a public http(s) URL on port 80/443, else raise WebError."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise WebError("Only http(s) links can be read.")
    if parsed.username or parsed.password:
        raise WebError("Links with embedded credentials are not allowed.")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if port not in (80, 443):
        raise WebError("Only standard web ports (80/443) are allowed.")
    host = parsed.hostname
    if host.lower() in ("localhost",) or host.lower().endswith((".local", ".localhost", ".internal", ".lan", ".home")):
        raise WebError("Local network addresses are blocked.")
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise WebError(f"Could not resolve {host}.")
    ips = {info[4][0] for info in infos}
    if not ips or not all(_is_public_ip(ip) for ip in ips):
        raise WebError("This address points to this PC or a private network, so Loki will not read it.")
    return url


async def _safe_get(client: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
    """GET with manual redirects so every hop is re-checked, and a hard size cap."""
    for _ in range(MAX_REDIRECTS + 1):
        await check_public_url(url)
        async with client.stream("GET", url, **kwargs) as resp:
            if resp.is_redirect:
                url = urljoin(url, resp.headers.get("location", ""))
                kwargs.pop("params", None)
                continue
            body = bytearray()
            async for chunk in resp.aiter_bytes():
                body.extend(chunk)
                if len(body) > MAX_DOWNLOAD_BYTES:
                    break
            resp._content = bytes(body)  # noqa: SLF001 - capped body for .text
            return resp
    raise WebError("Too many redirects.")


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False,
                             headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.8"})


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------
def _clean_result_url(href: str) -> str | None:
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        href = unquote(target)
    if not href.startswith(("http://", "https://")):
        return None
    if urlparse(href).netloc.endswith("duckduckgo.com"):  # ads / internal links
        return None
    return href


def parse_search_results(html: str, limit: int) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "lxml")
    results: list[dict[str, str]] = []
    for block in soup.select("div.result"):
        if "result--ad" in (block.get("class") or []):
            continue
        a = block.select_one("a.result__a")
        if not a or not a.get("href"):
            continue
        url = _clean_result_url(a["href"])
        if not url or any(r["url"] == url for r in results):
            continue
        snippet_el = block.select_one(".result__snippet")
        results.append({
            "title": " ".join(a.get_text(" ").split())[:160],
            "url": url,
            "snippet": " ".join(snippet_el.get_text(" ").split())[:400] if snippet_el else "",
        })
        if len(results) >= limit:
            break
    return results


def _yahoo_target(href: str) -> str | None:
    """Yahoo wraps results in r.search.yahoo.com/.../RU=<url-encoded real URL>/RK=..."""
    m = re.search(r"/RU=([^/]+)/R[KS]=", href)
    if m:
        href = unquote(m.group(1))
    if not href.startswith(("http://", "https://")):
        return None
    host = urlparse(href).netloc
    if host.endswith(("yahoo.com", "bing.com", "yimg.com")):
        return None
    return href


def parse_yahoo_results(html: str, limit: int) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "lxml")
    results: list[dict[str, str]] = []
    # Organic results only: ads live in the searchCenterTop / searchCenterBottom lists.
    for block in soup.select("ol.searchCenterMiddle div.algo"):
        title_el = block.select_one("h3.title") or block.select_one("h3")
        a = title_el.find_parent("a") if title_el else None
        a = a or block.select_one("h3 a")
        if not title_el or not a or not a.get("href"):
            continue
        url = _yahoo_target(a["href"])
        if not url or any(r["url"] == url for r in results):
            continue
        snippet_el = block.select_one(".compText p") or block.select_one(".compText")
        results.append({"title": " ".join(title_el.get_text(" ").split())[:160], "url": url,
                        "snippet": " ".join(snippet_el.get_text(" ").split())[:400] if snippet_el else ""})
        if len(results) >= limit:
            break
    return results


async def _search_duckduckgo(query: str, limit: int) -> list[dict[str, str]]:
    async with _client() as client:
        resp = await client.post(SEARCH_URL, data={"q": query, "kl": "wt-wt"})
    if resp.status_code != 200:
        raise WebError(f"DuckDuckGo returned HTTP {resp.status_code}")
    return parse_search_results(resp.text, limit)


async def _search_yahoo(query: str, limit: int) -> list[dict[str, str]]:
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True,
                                 headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.8"}) as client:
        resp = await client.get(YAHOO_URL, params={"p": query})
    if resp.status_code != 200:
        raise WebError(f"Yahoo returned HTTP {resp.status_code}")
    return parse_yahoo_results(resp.text, limit)


async def search(query: str, limit: int = 5) -> list[dict[str, str]]:
    """DuckDuckGo first; Yahoo when DuckDuckGo is busy or finds nothing."""
    query = " ".join(query.split())[:200]
    if not query:
        return []
    problems: list[str] = []
    for engine in (_search_duckduckgo, _search_yahoo):
        try:
            results = await engine(query, limit)
        except httpx.HTTPError as exc:
            problems.append(f"{engine.__name__[8:]}: {exc.__class__.__name__}")
            continue
        except WebError as exc:
            problems.append(str(exc))
            continue
        if results:
            return results
        problems.append(f"{engine.__name__[8:]}: no results")
    raise WebError("Search engines are not answering right now (" + "; ".join(problems) + ")")


# ---------------------------------------------------------------------------
# Page reading
# ---------------------------------------------------------------------------
_DROP_TAGS = ["script", "style", "noscript", "svg", "nav", "header", "footer", "aside", "form",
              "iframe", "button", "template"]


_CHROME = re.compile(
    r"^(sorry, something went wrong|uh oh!?|there was an error while loading|no results found|"
    r"choose a tag to compare|accept (all )?cookies|we use cookies|sign in|log in|subscribe|share this|"
    r"skip to (main )?content|advertisement)\b",
    re.I,
)


def extract_text(html: str, max_chars: int = PAGE_CHARS) -> tuple[str, str]:
    """Return (title, readable text) from HTML, preferring <article>/<main>."""
    soup = BeautifulSoup(html, "lxml")
    title = " ".join((soup.title.get_text() if soup.title else "").split())[:200]
    for tag in soup(_DROP_TAGS):
        tag.decompose()
    root = soup.find("article") or soup.find("main") or soup.body or soup
    parts = []
    for el in root.find_all(["h1", "h2", "h3", "p", "li", "td", "pre", "blockquote"]):
        text = " ".join(el.get_text(" ").split())
        if len(text) >= 25 or el.name in ("h1", "h2", "h3"):
            parts.append(text)
    parts = [p for p in parts if not _CHROME.search(p)]
    text = "\n".join(dict.fromkeys(parts))  # de-duplicate, keep order
    if len(text) < 200:  # fall back to all visible text
        text = " ".join(root.get_text(" ").split())
    return title, text[:max_chars]


async def read_page(url: str, max_chars: int = PAGE_CHARS) -> dict[str, str]:
    async with _client() as client:
        try:
            resp = await _safe_get(client, url)
        except httpx.HTTPError as exc:
            raise WebError(f"Could not load the page ({exc.__class__.__name__}).") from exc
    if resp.status_code >= 400:
        raise WebError(f"The page returned HTTP {resp.status_code}.")
    ctype = resp.headers.get("content-type", "").lower()
    if "html" in ctype or not ctype:
        title, text = extract_text(resp.text, max_chars)
    elif ctype.startswith("text/") or "json" in ctype:
        title, text = "", resp.text[:max_chars]
    else:
        raise WebError(f"Unsupported content type ({ctype.split(';')[0]}).")
    return {"url": str(resp.url), "title": title or urlparse(url).netloc, "text": text}


async def research(query: str, max_pages: int = 3) -> list[dict[str, str]]:
    """Search, then read the top pages concurrently. Pages that fail fall back to their snippet."""
    results = await search(query, limit=max_pages + 2)
    picked = results[:max_pages]

    async def load(r: dict[str, str]) -> dict[str, str]:
        try:
            page = await read_page(r["url"])
            text = page["text"] if len(page["text"]) > len(r["snippet"]) else r["snippet"]
        except WebError:
            text = r["snippet"]
        return {"title": r["title"], "url": r["url"], "text": text}

    return list(await asyncio.gather(*(load(r) for r in picked)))


URL_RE = re.compile(r"https?://[^\s<>()\"']+[^\s<>()\"'.,;:!?]")


def find_urls(text: str) -> list[str]:
    return list(dict.fromkeys(URL_RE.findall(text or "")))[:2]
