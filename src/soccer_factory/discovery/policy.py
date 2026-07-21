"""
Discovery policy: robots.txt handling, restricted paths, same-domain allowlist,
URL-scheme filtering.

Design notes
------------
* robots_unavailable_blocks=True (default): when robots.txt cannot be fetched
  or parsed, crawling is blocked.  This is the safe default.
* Restricted-path checks operate on the *parsed* URL path, not the raw string.
* Same-domain accepts both www and non-www but no other subdomains.
* Scheme filtering blocks mailto:, javascript:, tel:, data: before any other check.

IMPORTANT: ``robots_allowed() == True`` means the crawler's robots.txt rule
permits the request.  It is NOT a statement that scraping is permitted or
that the site consents to any use of the data.
"""
from __future__ import annotations

import urllib.parse
import urllib.robotparser
from typing import Dict, Optional

# ---------------------------------------------------------------------------
# Same-domain allowlist
# ---------------------------------------------------------------------------

# Canonical domain for each source (without www).
# Both www.{domain} and {domain} are accepted.
ALLOWED_BASE_DOMAINS: Dict[str, str] = {
    "soccerstats": "soccerstats.com",
    "forebet": "forebet.com",
}

# ---------------------------------------------------------------------------
# Hard-blocked URL schemes — must be checked before any path work
# ---------------------------------------------------------------------------

BLOCKED_SCHEMES = {"mailto", "javascript", "tel", "data"}

# ---------------------------------------------------------------------------
# Hard-blocked path prefixes (applied to parsed URL path, lower-cased)
# ---------------------------------------------------------------------------

BLOCKED_PATH_PREFIXES = (
    "/cdn-cgi/",
    "/js/",
    "/css/",
    "/images/",
    "/img/",
    "/flags/",
    "/logos/",
    "/ads/",
    "/advert/",
)

# ---------------------------------------------------------------------------
# Hard-blocked path basenames (lower-cased, no extension ambiguity)
# ---------------------------------------------------------------------------

BLOCKED_PATH_NAMES: frozenset[str] = frozenset({
    "members.asp",
    "register.asp",
    "login.asp",
    "signup.asp",
    "payment.asp",
    "subscription.asp",
    "error.htm",
    "error.html",
    "error.asp",
})

# ---------------------------------------------------------------------------
# Hard-blocked extensions (applied to parsed path, lower-cased)
# ---------------------------------------------------------------------------

BLOCKED_EXTENSIONS: frozenset[str] = frozenset({
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp",
    ".ico", ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".css", ".js", ".json", ".xml", ".pdf", ".zip",
    ".mp4", ".mp3", ".avi", ".mov",
})

# ---------------------------------------------------------------------------
# Robots policy (per base-URL, lazily fetched and cached)
# ---------------------------------------------------------------------------

_robots_cache: Dict[str, Optional[urllib.robotparser.RobotFileParser]] = {}


def _build_robots_parser(robots_url: str, timeout: float = 10.0) -> Optional[urllib.robotparser.RobotFileParser]:
    """Fetch and parse robots.txt.  Return None on any error."""
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(robots_url)
    try:
        rp.read()
        return rp
    except Exception:
        return None


def _robots_parser(base_url: str) -> Optional[urllib.robotparser.RobotFileParser]:
    """Return a cached RobotFileParser (or None when unavailable)."""
    if base_url not in _robots_cache:
        robots_url = base_url.rstrip("/") + "/robots.txt"
        _robots_cache[base_url] = _build_robots_parser(robots_url)
    return _robots_cache[base_url]


def clear_robots_cache() -> None:
    """Clear the module-level robots cache.  Call in tests between cases."""
    _robots_cache.clear()


def robots_allowed(
    url: str,
    user_agent: str = "*",
    unavailable_blocks: bool = True,
) -> bool:
    """Return True only if robots.txt explicitly permits the URL.

    Parameters
    ----------
    url:
        The URL to check.
    user_agent:
        The crawler user-agent string to check against.
    unavailable_blocks:
        When True (default), an unavailable or malformed robots.txt causes
        the function to return False (safe-block).  Set to False only for
        test scenarios where a live robots fetch is intentionally skipped.
    """
    parsed = urllib.parse.urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    rp = _robots_parser(base)
    if rp is None:
        # robots.txt unavailable or malformed
        return not unavailable_blocks
    return rp.can_fetch(user_agent, url)


# ---------------------------------------------------------------------------
# Scheme check
# ---------------------------------------------------------------------------

def is_valid_scheme(url: str) -> bool:
    """Return False for non-HTTP/HTTPS schemes and protocol-relative URLs.

    Blocked: mailto:, javascript:, tel:, data:, // (protocol-relative).
    """
    if url.startswith("//"):
        return False
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme in BLOCKED_SCHEMES:
        return False
    if parsed.scheme not in ("http", "https", ""):
        return False
    return True


# ---------------------------------------------------------------------------
# Domain check
# ---------------------------------------------------------------------------

def _normalise_host(netloc: str) -> str:
    """Strip port and leading 'www.' for comparison."""
    host = netloc.lower().split(":")[0]   # remove port
    if host.startswith("www."):
        host = host[4:]
    return host


def is_same_domain(url: str, source: str) -> bool:
    """Return True when *url* belongs to the allowed domain for *source*.

    Accepts both ``www.soccerstats.com`` and ``soccerstats.com``.
    Rejects all other subdomains (``data.soccerstats.com`` → False).
    """
    canonical = ALLOWED_BASE_DOMAINS.get(source, "")
    if not canonical:
        return False
    parsed = urllib.parse.urlparse(url)
    host = _normalise_host(parsed.netloc)
    return host == canonical


# ---------------------------------------------------------------------------
# Path / extension checks
# ---------------------------------------------------------------------------

def _path_from_url(url: str) -> str:
    """Return the lowercase parsed path component."""
    return urllib.parse.urlparse(url).path.lower()


def _is_blocked_extension(path: str) -> bool:
    """Check file extension of the path (not query string)."""
    dot_pos = path.rfind(".")
    if dot_pos == -1:
        return False
    ext = path[dot_pos:]
    return ext in BLOCKED_EXTENSIONS


def _is_blocked_prefix(path: str) -> bool:
    return any(path.startswith(pfx) for pfx in BLOCKED_PATH_PREFIXES)


def _is_blocked_name(path: str) -> bool:
    """Check the basename of the parsed path."""
    basename = path.split("/")[-1]
    # strip query if still present (shouldn't be, but be safe)
    basename = basename.split("?")[0]
    return basename in BLOCKED_PATH_NAMES


def is_restricted(url: str) -> bool:
    """Return True if the URL must never be fetched.

    Checks are applied to the *parsed* URL path (lower-cased),
    not the raw URL string, so query parameters cannot trigger a false block.
    """
    if not is_valid_scheme(url):
        return True
    path = _path_from_url(url)
    return (
        _is_blocked_extension(path)
        or _is_blocked_prefix(path)
        or _is_blocked_name(path)
    )


# ---------------------------------------------------------------------------
# Combined gate
# ---------------------------------------------------------------------------

def is_allowed(
    url: str,
    source: str,
    check_robots: bool = False,
    robots_unavailable_blocks: bool = True,
) -> bool:
    """Full allowance gate: valid scheme AND same-domain AND not restricted
    AND (optionally) robots-permitted.

    Parameters
    ----------
    url:
        URL to evaluate.
    source:
        "soccerstats" or "forebet".
    check_robots:
        When True, also consult the cached robots.txt.
        Set False in fixture mode to avoid network calls.
    robots_unavailable_blocks:
        Passed through to ``robots_allowed()``.
    """
    if not is_valid_scheme(url):
        return False
    if not is_same_domain(url, source):
        return False
    if is_restricted(url):
        return False
    if check_robots and not robots_allowed(url, unavailable_blocks=robots_unavailable_blocks):
        return False
    return True
