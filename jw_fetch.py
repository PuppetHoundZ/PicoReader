"""
jw_fetch.py

Optional PicoReader plugin: download JW.org EPUB publications directly
onto the device, using the same public media API JW.org's own official
apps use (b.jw-cdn.org/apis/pub-media/GETPUBMEDIALINKS) plus the
jw.org "What's New" RSS feed to auto-detect the newest Watchtower Study
Edition and Meeting Workbook issue without needing to know or guess a
date.

PRIVATE PLUGIN -- per the person's explicit instruction, this file is
NOT to be published to a public GitHub repo alongside gutenberg_fetch.py.
Keep it local-only. See AI NOTES in main.py for the full legal reasoning
this was based on (jw.org Terms of Use, checked in-conversation, not
guessed).

All pub codes below were verified LIVE against the real API before being
added here (not guessed) -- see main.py's AI NOTES for the verification
method if any of these ever need re-checking after a JW.org catalog
change.

PLUGIN CONTRACT -- same as gutenberg_fetch.py, see that file's docstring
for the full interface. list_items() here ignores `query`/`page` (the
catalog is small and fixed, no pagination needed) and always returns
has_next=False.
"""

import json
import os
import re
import time
import urllib.request
import urllib.error
import urllib.parse

PLUGIN_NAME = "JW.org"
SUPPORTS_MANUAL_CODE = True  # main.py offers a "type a pub code" screen
                              # for plugins that declare this -- distinct
                              # from SUPPORTS_SEARCH (gutenberg_fetch.py):
                              # this isn't filtering a catalog, it's a
                              # direct live lookup of one specific,
                              # exact code the person already knows,
                              # for publications not in the curated
                              # STATIC_PUBLICATIONS list below.

API_BASE = "https://b.jw-cdn.org/apis/pub-media/GETPUBMEDIALINKS"
WHATS_NEW_RSS = "https://www.jw.org/en/whats-new/rss/WhatsNewWebArticles/feed.xml"
REQUEST_TIMEOUT = 15
USER_AGENT = "PicoReader/1.0 (muOS EPUB reader; personal, non-commercial)"
LANG = "E"

# Fixed-code publications (verified live, no `issue` param needed).
# (pub_code, display title, extra query params dict or None)
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

# Periodicals need an `issue=YYYYMM`. current_issue_guess() below picks a
# reasonable default (this month); check_new_issues() (RSS-based) is the
# more reliable way to get the ACTUAL latest published issue.
PERIODICALS = [
    ("w",   "Watchtower -- Study Edition"),
    ("mwb", "Meeting Workbook"),
    ("es",  "Examining the Scriptures Daily (current year)"),
]


def _get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def _extract_epub(data):
    try:
        epubs = data["files"][LANG]["EPUB"]
    except (KeyError, TypeError):
        return None
    if not epubs:
        return None
    return epubs[0]


def current_issue_guess():
    """This month as YYYYMM, for periodicals -- a fallback when the RSS
    feed can't be reached. The actual current issue may differ (JW.org
    typically publishes a month or so ahead of the calendar), so
    check_new_issues() is preferred when network access allows it."""
    return time.strftime("%Y%m")


def current_year_es_code():
    """es + 2-digit year, e.g. es26 for 2026, matching the pub code
    pattern confirmed live for the daily-text booklet."""
    return "es" + time.strftime("%y")


def check_new_issues():
    """Parses the What's New RSS feed for dated Watchtower Study Edition
    and Meeting Workbook titles (e.g. "THE WATCHTOWER-STUDY EDITION |
    September 2026") and converts the month/year into an issue=YYYYMM
    code -- this is how a newly-released issue can be found without
    guessing or hardcoding a date. Returns a list of (pub_code, title,
    issue) tuples, most recent first, deduplicated. Best-effort: returns
    an empty list (never raises) if the feed can't be reached."""
    req = urllib.request.Request(WHATS_NEW_RSS, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            text = resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError):
        return []

    months = {m: i + 1 for i, m in enumerate([
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"])}
    month_re = "|".join(months.keys())

    found = {}
    for m in re.finditer(r"<title>(.*?)</title>", text, re.S):
        title = m.group(1).strip()
        # Bi-monthly titles like "November-December 2026" (the Workbook)
        # must resolve to the FIRST month -- that's the actual issue
        # code (mwb_E_202611, not 202612) -- so the second optional
        # month is matched but deliberately not captured/used.
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


def list_items(query=None, page=1):
    """Returns the static publication list plus, if the RSS feed is
    reachable, the actual latest Watchtower/Workbook issue (falls back
    to a same-month guess if the feed can't be reached). Always
    has_next=False -- everything fits on one page."""
    items = []
    for pub, title, extra in STATIC_PUBLICATIONS:
        items.append({
            "title": title,
            "subtitle": f"pub: {pub}",
            "filename": f"{pub}_{LANG}.epub",
            "_pub": pub,
            "_extra": extra,
        })

    new_issues = check_new_issues()
    covered = {(pub, issue) for pub, _t, issue in new_issues}
    for pub, title, issue in new_issues:
        items.append({
            "title": f"{title} (new)",
            "subtitle": f"pub: {pub}  issue: {issue}",
            "filename": f"{pub}_{LANG}_{issue}.epub",
            "_pub": pub,
            "_extra": {"issue": issue},
        })

    for pub, title in PERIODICALS:
        if pub == "es":
            code = current_year_es_code()
            items.append({
                "title": title,
                "subtitle": f"pub: {code}",
                "filename": f"{code}_{LANG}.epub",
                "_pub": code,
                "_extra": None,
            })
            continue
        issue = current_issue_guess()
        if (pub, issue) in covered:
            continue  # already added via the RSS "(new)" entry above
        items.append({
            "title": f"{title} (this month, guess)",
            "subtitle": f"pub: {pub}  issue: {issue}",
            "filename": f"{pub}_{LANG}_{issue}.epub",
            "_pub": pub,
            "_extra": {"issue": issue},
        })

    return items, False, None


def lookup_pub_code(code, issue=None):
    """Manually-entered pub code lookup (v0.1.31) -- for publications NOT
    in STATIC_PUBLICATIONS, tried directly against the live API. Returns
    (item_dict_or_None, error_message). Mirrors the same
    fileformat=EPUB retry _resolve_download_url() uses internally for
    multi-format publications (the plain NWT needs it -- see that
    function's comment). This performs the FULL round-trip up front
    (not just building a URL) specifically so a typo or nonexistent code
    can be reported clearly, rather than only failing later at actual
    download time."""
    code = (code or "").strip().lower()
    if not code:
        return None, "Enter a publication code"
    if len(code) > 40:
        return None, "That doesn't look like a publication code"

    params = {"pub": code, "langwritten": LANG, "output": "json"}
    if issue:
        params["issue"] = issue.strip()

    def _try(p):
        try:
            return _get_json(API_BASE + "?" + urllib.parse.urlencode(p)), None
        except urllib.error.HTTPError as e:
            if e.code == 400:
                # The API's actual behavior for an unrecognized pub code
                # (confirmed live) -- distinct from a real connectivity
                # failure, so the person isn't told "network error" for
                # what's actually just an invalid code.
                return None, "INVALID_CODE"
            return None, f"Server error ({e.code})"
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            return None, f"Network error: {e}"
        except ValueError as e:
            return None, f"Bad response from server: {e}"

    data, err = _try(params)
    epub = _extract_epub(data) if isinstance(data, dict) else None

    if not epub:
        # Some pubs (like the plain NWT) actually return an HTTP 400 --
        # not just a "no epub" response -- unless fileformat is explicit,
        # so the first attempt above may have failed via exception
        # (err set, data None) rather than just missing an epub. Either
        # way, retry once with fileformat=EPUB before giving up.
        retry_params = dict(params, fileformat="EPUB")
        data2, err2 = _try(retry_params)
        epub2 = _extract_epub(data2) if isinstance(data2, dict) else None
        if epub2:
            data, epub, err = data2, epub2, None
        elif err2 is None:
            # retry got a real response but still no epub -- prefer that
            # (more specific) error/data over the first attempt's
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
        "title": title,
        "subtitle": f"pub: {code}" + (f"  issue: {issue.strip()}" if issue else ""),
        "filename": f"{code}_{LANG}{fname_suffix}.epub",
        "_pub": code,
        "_extra": ({"issue": issue.strip()} if issue else None),
    }, None


def _resolve_download_url(item):
    params = {"pub": item["_pub"], "langwritten": LANG, "output": "json"}
    if item.get("_extra"):
        params.update(item["_extra"])
    url = API_BASE + "?" + "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
    try:
        data = _get_json(url)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as e:
        return None, str(e)
    epub = _extract_epub(data)
    if not epub:
        return None, f'"{data.get("pubName", item["title"])}" has no EPUB available'
    return epub["file"]["url"], None


def download(item, dest_dir):
    dest_path = os.path.join(dest_dir, item["filename"])
    if os.path.exists(dest_path):
        return False, f'"{item["filename"]}" already in Library', dest_path

    epub_url, err = _resolve_download_url(item)
    if err:
        return False, err, None
    if not epub_url:
        return False, "Could not resolve a download link", None

    tmp_path = dest_path + ".part"
    req = urllib.request.Request(epub_url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            with open(tmp_path, "wb") as f:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
        os.replace(tmp_path, dest_path)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
        return False, f"Download failed: {e}", None
    return True, f'Downloaded "{item["title"]}"', dest_path
