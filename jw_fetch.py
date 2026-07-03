"""
jw_fetch.py

Optional PicoReader plugin: download JW.org EPUB publications directly
onto the device, using the same public media API JW.org's own official
apps use (b.jw-cdn.org/apis/pub-media/GETPUBMEDIALINKS) plus the
jw.org "What's New" RSS feed to auto-detect the newest Watchtower Study
Edition and Meeting Workbook issue without needing to know or guess a date.

PRIVATE PLUGIN -- per the person's explicit instruction, this file is
NOT to be published to a public GitHub repo alongside gutenberg_fetch.py.
Keep it local-only. See AI NOTES in main.py for the full legal reasoning
(jw.org Terms of Use, checked in-conversation, not guessed).

All pub codes below were verified LIVE against the real API before being
added here (not guessed) -- see main.py's AI NOTES for the verification
method if any of these ever need re-checking after a JW.org catalog change.

HOW THIS PLUGIN DIFFERS FROM gutenberg_fetch.py:
  gutenberg_fetch.py queries a real search API (Gutendex) with free-text
  queries and gets back paginated results. This plugin works differently:
  - The catalog is small and fixed (a curated list of publications we know
    exist), so there's no search or pagination -- everything fits one page.
  - Downloads are a TWO-STEP process: first we call GETPUBMEDIALINKS to
    resolve the current download URL for a publication (URLs can change),
    then we fetch that URL. gutenberg_fetch.py only needs one step because
    Gutendex already gives us a direct EPUB URL in the catalog response.
  - Periodical issues (Watchtower, Workbook) need an YYYYMM issue code.
    We use the RSS feed to detect the actual latest issue, with a
    same-month fallback guess if the feed can't be reached.

PLUGIN CONTRACT -- same as gutenberg_fetch.py. See that file's docstring
for the full interface. list_items() here ignores `query`/`page` (the
catalog is small and fixed, no pagination needed) and always returns
has_next=False.

No pip dependencies -- stdlib urllib only. See gutenberg_fetch.py's
docstring for why this matters on muOS hardware.
"""

import json
import os
import re
import time
import urllib.request
import urllib.error
import urllib.parse

# ---------------------------------------------------------------------------
# Plugin identity and capability flags
# ---------------------------------------------------------------------------

PLUGIN_NAME = "JW.org"

# SUPPORTS_MANUAL_CODE tells main.py to show a Y-button code-entry screen.
# This is distinct from SUPPORTS_SEARCH (gutenberg_fetch.py): we're not
# filtering a catalog, we're doing a direct live lookup of one specific
# exact code the person already knows -- for publications not in the
# curated STATIC_PUBLICATIONS list below. The on-validate path checks the
# code against the live API BEFORE leaving the entry screen, so a typo
# shows a clear error and lets the person fix it immediately rather than
# bouncing to the results list with nothing in it.
SUPPORTS_MANUAL_CODE = True

# Shown on-screen under the manual-code input box. main.py reads this via
# getattr() so it's optional/plugin-owned -- main.py's text-entry code has
# no JW-specific knowledge, keeping concerns cleanly separated.
# Codes here are all verified LIVE against the real API (same standard as
# STATIC_PUBLICATIONS -- nothing is guessed or assumed).
#
# Awake! GOTCHA worth remembering: its "issue" is a real YYYYMM release
# month, but the on-site "No. N YYYY" label does NOT map to that year/month
# directly. Confirmed live: "Awake! No. 1 2025" is actually issue=202511
# (November 2025), not 202501. Since Awake! only publishes ~1x/year now
# (irregular timing), there's no reliable way to guess its current issue.
# Manual code entry with a known issue is the practical approach for now.
# To find the right issue= value, check jw.org/en/library/magazines/ and
# look at the download links for the specific issue you want.
MANUAL_CODE_HINT = "w=Watchtower  g=Awake!  mwb=Workbook  es=Daily Text"

# ---------------------------------------------------------------------------
# API configuration
# ---------------------------------------------------------------------------

# JW.org's own public media API -- the same endpoint their official apps
# use. No authentication required, but this is not a documented public API;
# use it respectfully (reasonable timeouts, no hammering).
# Reference: confirmed via network inspection of official JW apps.
API_BASE = "https://b.jw-cdn.org/apis/pub-media/GETPUBMEDIALINKS"

# RSS feed used to detect the actual latest Watchtower/Workbook issue.
# This is a publicly available feed linked from jw.org itself. We parse
# the title strings to extract month/year and convert to YYYYMM issue codes.
WHATS_NEW_RSS = "https://www.jw.org/en/whats-new/rss/WhatsNewArticles/feed.xml"

REQUEST_TIMEOUT = 15
USER_AGENT = "PicoReader/1.0 (muOS EPUB reader; personal, non-commercial)"

# Language code used in all API calls. "E" = English.
# The API accepts standard two-letter codes for other languages.
LANG = "E"

# ---------------------------------------------------------------------------
# Publication catalog
# ---------------------------------------------------------------------------

# Fixed-code publications that don't need an issue parameter.
# Format: (pub_code, display_title, extra_params_dict_or_None)
# extra_params: passed directly to GETPUBMEDIALINKS alongside pub= and
# langwritten=. Some publications (e.g. the plain NWT) need fileformat=EPUB
# explicitly or the API returns a 400 error -- see _resolve_download_url()
# and lookup_pub_code() for the retry logic that handles this.
# ALL codes here were verified LIVE before being added.
STATIC_PUBLICATIONS = [
    ("nwt",   "New World Translation (2013 Revision)", {"fileformat": "EPUB"}),
    ("bi12",  "New World Translation (1984 Edition)", None),
    ("lffi",  "Enjoy Life Forever! -- Introductory Bible Lessons", None),
    ("lff",   "Enjoy Life Forever! -- An Interactive Bible Course", None),
    ("sjjls", '"Sing Out Joyfully" to Jehovah', None),
    ("od",    "Organized to Do Jehovah's Will", None),
    ("wcg",   "Walk Courageously With God", None),
    ("lfb",   "Lessons You Can Learn From the Bible", None),
    ("jy",    "Jesus -- The Way, the Truth, the Life", None),
    ("cl",    "Draw Close to Jehovah", None),
    ("rr",    "Pure Worship of Jehovah -- Restored At Last!", None),
]

# Periodicals that need an `issue=YYYYMM` parameter.
# For these, we try the RSS feed first (most accurate), then fall back to
# a same-month guess via current_issue_guess(). The daily text (es) is a
# special case: its code is year-specific (es26 for 2026, es27 for 2027)
# rather than using an issue parameter, so it's handled separately below.
PERIODICALS = [
    ("w",   "Watchtower -- Study Edition"),
    ("mwb", "Meeting Workbook"),
    ("es",  "Examining the Scriptures Daily (current year)"),
]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_json(url):
    """Fetch a URL and parse the response as JSON.
    Raises urllib.error.URLError, TimeoutError, ValueError, or OSError --
    callers handle these. Same pattern as gutenberg_fetch.py."""
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def _extract_epub(data):
    """Pull the first EPUB entry out of a GETPUBMEDIALINKS response.

    The API response structure is:
      data["files"][LANG]["EPUB"] -> list of file objects
    Each file object has a ["file"]["url"] we can download.
    Returns None if the path doesn't exist or the list is empty -- the
    caller decides what to do (usually retry with fileformat=EPUB)."""
    try:
        epubs = data["files"][LANG]["EPUB"]
    except (KeyError, TypeError):
        return None
    if not epubs:
        return None
    return epubs[0]


def current_issue_guess():
    """This month as YYYYMM -- a fallback issue code for periodicals when
    the RSS feed can't be reached. JW.org typically publishes a month or
    two ahead of the calendar, so this guess may be one issue behind the
    actual latest. check_new_issues() via RSS is preferred when available."""
    return time.strftime("%Y%m")


def current_year_es_code():
    """Returns the pub code for this year's daily text booklet.
    The pattern (confirmed live) is "es" + 2-digit year: es26 for 2026,
    es27 for 2027, etc. Unlike other periodicals, this doesn't use an
    issue= parameter -- the year is baked into the pub code itself."""
    return "es" + time.strftime("%y")


def check_new_issues():
    """Parse the jw.org What's New RSS feed to find the actual latest
    Watchtower Study Edition and Meeting Workbook issue codes.

    Why RSS instead of just guessing? JW.org publishes issues ahead of
    the calendar month, so same-month guessing is unreliable. The RSS
    feed titles contain the month and year ("THE WATCHTOWER-STUDY EDITION
    | September 2026"), which we convert to YYYYMM issue codes.

    Key gotcha: bi-monthly Workbook titles like "November-December 2026"
    must resolve to the FIRST month (mwb_E_202611, not 202612) -- that's
    the actual issue code confirmed live. The regex matches but discards
    the second month.

    Returns a list of (pub_code, title, issue_YYYYMM) tuples, deduplicated.
    Best-effort only: returns [] if the feed can't be reached -- never
    raises, so the calling code can always fall back to current_issue_guess()
    without extra error handling."""
    req = urllib.request.Request(WHATS_NEW_RSS, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            text = resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError):
        return []  # network failure -- caller falls back to guess

    # Build a month-name -> month-number lookup for all 12 months
    months = {m: i + 1 for i, m in enumerate([
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"])}
    month_re = "|".join(months.keys())

    found = {}
    for m in re.finditer(r"<title>(.*?)</title>", text, re.S):
        title = m.group(1).strip()
        # Match "Month YYYY" or "Month-Month YYYY" (bi-monthly), capture
        # only the first month. Unicode dashes (\u2013 en-dash, \u2014
        # em-dash) are included because RSS feeds sometimes use them.
        date_m = re.search(
            rf"({month_re})(?:[\s\u2013\u2014-]+(?:{month_re}))?\s+(\d{{4}})",
            title)
        if not date_m:
            continue
        mon, year = date_m.group(1), date_m.group(2)
        issue = f"{year}{months[mon]:02d}"
        if "WATCHTOWER" in title.upper() and "STUDY" in title.upper():
            key = ("w", issue)
            found[key] = title
        elif "WORKBOOK" in title.upper():
            key = ("mwb", issue)
            found[key] = title

    return [(pub, title, issue) for (pub, issue), title in found.items()]


# ---------------------------------------------------------------------------
# Required plugin functions
# ---------------------------------------------------------------------------

def list_items(query=None, page=1):
    """Build and return the full catalog of available JW.org publications.

    Unlike gutenberg_fetch.py, this doesn't call an API here -- the catalog
    is assembled locally from STATIC_PUBLICATIONS and PERIODICALS, with the
    RSS feed used only to determine the current periodical issue codes.
    The actual download URL is resolved lazily in download() via
    _resolve_download_url() -- we don't need it for the browse list.

    query and page are ignored: the catalog is small and fixed, so there's
    no search or pagination. has_next is always False.

    Catalog assembly order:
    1. Static publications (books, courses -- no issue needed)
    2. New issues found via RSS (labeled "(new)")
    3. Periodicals not already covered by RSS (labeled "(this month, guess)")
    4. Daily text (special case: year-specific pub code, no issue param)"""
    items = []

    # Step 1: static publications
    # These are books/courses that don't change issue-to-issue. The item
    # dict doesn't include a _download_url because we resolve it at download
    # time -- the URL can change and we want the freshest link each time.
    for pub, title, extra in STATIC_PUBLICATIONS:
        items.append({
            "title":    title,
            "subtitle": f"pub: {pub}",
            "filename": f"{pub}_{LANG}.epub",
            "_pub":     pub,
            "_extra":   extra,   # passed to GETPUBMEDIALINKS at download time
        })

    # Step 2: RSS-detected new issues
    # If the feed is reachable, these are the actual currently-published
    # issues -- more accurate than guessing from the calendar.
    new_issues = check_new_issues()
    covered = {(pub, issue) for pub, _t, issue in new_issues}
    for pub, title, issue in new_issues:
        items.append({
            "title":    f"{title} (new)",
            "subtitle": f"pub: {pub}  issue: {issue}",
            "filename": f"{pub}_{LANG}_{issue}.epub",
            "_pub":     pub,
            "_extra":   {"issue": issue},
        })

    # Step 3 & 4: periodicals not yet covered + daily text
    for pub, title in PERIODICALS:
        if pub == "es":
            # Daily text: year-baked-into-code pattern (es26, es27, ...)
            code = current_year_es_code()
            items.append({
                "title":    title,
                "subtitle": f"pub: {code}",
                "filename": f"{code}_{LANG}.epub",
                "_pub":     code,
                "_extra":   None,
            })
            continue
        issue = current_issue_guess()
        if (pub, issue) in covered:
            continue  # already listed via RSS above -- don't duplicate
        items.append({
            "title":    f"{title} (this month, guess)",
            "subtitle": f"pub: {pub}  issue: {issue}",
            "filename": f"{pub}_{LANG}_{issue}.epub",
            "_pub":     pub,
            "_extra":   {"issue": issue},
        })

    return items, False, None


def lookup_pub_code(code, issue=None):
    """Manual pub-code lookup for publications NOT in STATIC_PUBLICATIONS.

    Called by main.py when the user confirms a code on the Y-button manual-
    entry screen. Unlike list_items(), this performs a LIVE API round-trip
    immediately -- the point is to catch typos on the entry screen with a
    clear error ("not found") rather than only failing later at download time.

    Two-attempt strategy (why it's needed):
      Some publications (confirmed: the plain NWT "nwt") return HTTP 400
      from GETPUBMEDIALINKS unless fileformat=EPUB is explicit. A single
      attempt without fileformat would always fail for these. So:
        Attempt 1: without fileformat (works for most pubs)
        Attempt 2: with fileformat=EPUB (fallback for pubs that need it)
      If attempt 1 raises HTTPError 400, we fall through to attempt 2
      rather than giving up. This was a real bug before being fixed: the
      original code returned on the first error and never reached the retry.

    Returns (item_dict, None) on success, (None, error_string) on failure."""
    code = (code or "").strip().lower()
    if not code:
        return None, "Enter a publication code"
    if len(code) > 40:
        return None, "That doesn't look like a publication code"

    params = {"pub": code, "langwritten": LANG, "output": "json"}
    if issue:
        params["issue"] = issue.strip()

    def _try(p):
        """One attempt at the API. Returns (data_dict, None) on success or
        (None, error_string) on failure. error_string "INVALID_CODE" is a
        sentinel meaning the API returned 400 (unknown pub code) -- distinct
        from a real network error so we can give a better message."""
        try:
            return _get_json(API_BASE + "?" + urllib.parse.urlencode(p)), None
        except urllib.error.HTTPError as e:
            if e.code == 400:
                # 400 means the pub code isn't recognized by the API
                # (confirmed live) -- NOT a network problem. We use
                # "INVALID_CODE" so the outer function can distinguish
                # "needs retry with fileformat=EPUB" from "bad code".
                return None, "INVALID_CODE"
            return None, f"Server error ({e.code})"
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            return None, f"Network error: {e}"
        except ValueError as e:
            return None, f"Bad response from server: {e}"

    # Attempt 1: no fileformat param
    data, err = _try(params)
    epub = _extract_epub(data) if isinstance(data, dict) else None

    if not epub:
        # Attempt 2: explicit fileformat=EPUB (fallback for pubs like NWT)
        retry_params = dict(params, fileformat="EPUB")
        data2, err2 = _try(retry_params)
        epub2 = _extract_epub(data2) if isinstance(data2, dict) else None
        if epub2:
            data, epub, err = data2, epub2, None
        elif err2 is None:
            # Retry got a real response but still no epub -- use its data
            # (more specific / informative) over the first attempt's result
            err, data = None, data2

    if not epub:
        if isinstance(data, dict) and data.get("pubName"):
            return None, f'"{data["pubName"]}" has no EPUB available'
        if err and err != "INVALID_CODE":
            return None, err
        return None, f'"{code}" not found (check the code and try again)'

    title = data.get("pubName", code)
    fname_suffix = f"_{issue.strip()}" if issue else ""
    return {
        "title":    title,
        "subtitle": f"pub: {code}" + (f"  issue: {issue.strip()}" if issue else ""),
        "filename": f"{code}_{LANG}{fname_suffix}.epub",
        "_pub":     code,
        "_extra":   ({"issue": issue.strip()} if issue else None),
    }, None


def _resolve_download_url(item):
    """Resolve the current EPUB download URL for an item at download time.

    WHY resolve at download time instead of storing the URL in list_items()?
    JW.org's CDN URLs are time-limited and can change between catalog builds
    and actual download. Calling GETPUBMEDIALINKS fresh at download time
    always gives us a valid, current URL.

    Constructs the API request from item["_pub"] and item["_extra"] (which
    carries the issue= param for periodicals, or fileformat=EPUB for pubs
    that need it). Returns (url_string, None) on success or (None, error)."""
    params = {"pub": item["_pub"], "langwritten": LANG, "output": "json"}
    if item.get("_extra"):
        params.update(item["_extra"])
    url = API_BASE + "?" + "&".join(
        f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
    try:
        data = _get_json(url)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as e:
        return None, str(e)
    epub = _extract_epub(data)
    if not epub:
        return None, f'"{data.get("pubName", item["title"])}" has no EPUB available'
    return epub["file"]["url"], None


def download(item, dest_dir):
    """Download the EPUB for `item` into `dest_dir`.

    Two-step process (different from gutenberg_fetch.py's single-step):
      Step 1: call _resolve_download_url() to get a fresh CDN URL from
              GETPUBMEDIALINKS (URLs are time-limited and can change).
      Step 2: stream the EPUB from that URL in 64 KB chunks.

    The streaming + .part temp file pattern is the same as gutenberg_fetch:
    - .part file prevents a corrupt/partial epub appearing in the library
    - 64 KB chunks keep RAM use flat regardless of file size
    - atomic os.replace() is safe even if the process is interrupted

    Called on a background thread by main.py -- never block the UI thread
    with network I/O.

    Returns (ok, message, dest_path) -- same contract as gutenberg_fetch."""
    dest_path = os.path.join(dest_dir, item["filename"])
    if os.path.exists(dest_path):
        return False, f'"{item["filename"]}" already in Library', dest_path

    # Step 1: resolve current CDN URL
    epub_url, err = _resolve_download_url(item)
    if err:
        return False, err, None
    if not epub_url:
        return False, "Could not resolve a download link", None

    # Step 2: stream download
    tmp_path = dest_path + ".part"
    req = urllib.request.Request(epub_url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            with open(tmp_path, "wb") as f:
                while True:
                    chunk = resp.read(65536)  # 64 KB chunks -- flat RAM use
                    if not chunk:
                        break
                    f.write(chunk)
        os.replace(tmp_path, dest_path)  # atomic rename
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
        return False, f"Download failed: {e}", None

    return True, f'Downloaded "{item["title"]}"', dest_path
