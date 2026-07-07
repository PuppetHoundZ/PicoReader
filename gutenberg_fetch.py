"""
gutenberg_fetch.py

Optional PicoReader plugin: browse and download public-domain EPUBs from
Project Gutenberg via Gutendex (a community-run, read-only JSON API over
Project Gutenberg's catalog -- Project Gutenberg itself has no official
JSON API, only nightly XML/RDF archives; Gutendex exists specifically to
make that catalog easy to query). https://gutendex.com -- source/schema
docs: https://github.com/garethbjohnson/gutendex

THIRD-PARTY API -- NOT OUR CODE:
  Gutendex is an open-source project by Gareth Johnson, MIT licensed.
  We don't bundle any Gutendex code -- we only call its public REST API
  over HTTP. Project Gutenberg itself is a separate organisation; Gutendex
  is an unofficial community tool that wraps PG's catalog.

LEGAL: Project Gutenberg content is not restricted by U.S. copyright law
(the vast majority of the catalog). Per Project Gutenberg's own policy
(gutenberg.org/policy/permission.html): "No permission is needed for
non-commercial use... you can freely redistribute any eBook, anywhere,
any time, with or without the 'Project Gutenberg' trademark included."
Safe to publish this file publicly.

HOW PLUGIN LOADING WORKS (so you understand the bigger picture):
  main.py scans a fixed list of known plugin filenames at startup using
  a defensive try/except __import__ loop. If this file is present in the
  PicoReader/ app folder, it gets loaded into DOWNLOAD_PLUGINS and the
  "Download Books" option appears in the Library menu automatically.
  If the file is missing or crashes on import, the app silently skips it
  -- no crash, no broken menu. Drop the file back in and restart to
  restore it. No other files need to be changed.

PLUGIN CONTRACT (see main.py's plugin-loading code for how this is used):
  Every downloader plugin must implement:
    PLUGIN_NAME: str
        Shown in the source-picker UI when more than one plugin is present.
    list_items(query=None, page=1) -> (items, has_next, error)
        items: list of dicts, each with at minimum:
            "title": str            -- shown in the browse list
            "subtitle": str         -- shown as a dimmer second line (e.g. author)
            "filename": str         -- suggested local filename, no path
            "_download_url": str    -- resolved EPUB URL passed to download()
        has_next: bool -- True if page+1 has more results
        error: str or None -- human-readable error, or None on success
    download(item, dest_dir) -> (ok: bool, message: str, dest_path: str|None)
        Fetches item["_download_url"] and writes it to dest_dir/filename.
        Returns a short human-readable status message either way (shown as
        an on-screen toast) and the saved path on success.

  Optional flags (declare at module level):
    SUPPORTS_SEARCH = True
        Tells main.py to show a Y-button search entry screen. Implement
        list_items(query=...) to handle the typed search string.
    SUPPORTS_MANUAL_CODE = True
        Tells main.py to show a Y-button code-entry screen instead (for
        sources accessed by a specific code, not free-text search).
        Implement lookup_pub_code() too.
    MANUAL_CODE_HINT = "..."
        One-line hint shown on the code-entry screen.

No pip dependencies -- stdlib urllib only, matching the rest of PicoReader.
This is important: the target device (Anbernic RG CubeXX-H, muOS) has no
pip available. Every plugin must be self-contained pure Python stdlib.

CATEGORIES (v2): Adds a JW-library-style category picker (SUPPORTS_CATEGORIES,
same main.py mechanism as jw_fetch.py) sourced from Project Gutenberg's own
"Main Categories" page, plus a literal "Top 100" category equivalent to PG's
"Frequently Downloaded" list. See the "Category catalog" section below for
the full mapping and an important caveat about live verification.
"""

import json
import os
import re
import urllib.request
import urllib.error
import urllib.parse

# ---------------------------------------------------------------------------
# Plugin identity and capability flags
# ---------------------------------------------------------------------------

PLUGIN_NAME = "Project Gutenberg"

# SUPPORTS_SEARCH tells main.py to offer the Y-button on-screen letter-grid
# search for this plugin. Gutendex has a real `search` query param (confirmed
# in its docs: case-insensitive, matches both title and author fields), so
# search is genuinely useful here and we declare it.
# Contrast with jw_fetch.py, which has a small fixed catalog -- search would
# be pointless there, so it doesn't declare SUPPORTS_SEARCH.
SUPPORTS_SEARCH = True

# SUPPORTS_CATEGORIES tells main.py to show the same category-picker screen
# it already built for jw_fetch.py (see that file's SUPPORTS_CATEGORIES
# comment) before the browse list. main.py's category-picker code is fully
# generic -- it just reads plugin.CATEGORIES and calls
# list_items(query=..., page=..., category=...) -- so this plugin needed NO
# main.py changes, only the additions in this file.
# Search (Y) still works as normal, scoped to whichever category is open,
# exactly like jw_fetch.py.
SUPPORTS_CATEGORIES = True

# ---------------------------------------------------------------------------
# API configuration
# ---------------------------------------------------------------------------

# Gutendex public REST API base URL. No API key required.
# Full schema docs: https://github.com/garethbjohnson/gutendex
# The /books/ endpoint returns paginated JSON with a "results" array,
# "next" URL (or null), and "count" total. Default sort is by download
# popularity, which gives the most well-known books first -- good default
# for a browse screen.
API_BASE = "https://gutendex.com/books/"

# 15 seconds is generous for a slow device/connection but not so long that
# the UI feels frozen. Downloads use the same timeout per read() chunk --
# not per total download -- so a large file will still complete.
REQUEST_TIMEOUT = 15

# A descriptive User-Agent is polite to API operators and helps them
# understand traffic patterns. "personal, non-commercial" is accurate and
# relevant to Gutenberg's usage policy.
USER_AGENT = "PicoReader/1.0 (muOS EPUB reader; personal, non-commercial)"

# ---------------------------------------------------------------------------
# Category catalog
# ---------------------------------------------------------------------------
#
# Source: Project Gutenberg's own "Main Categories" page
# (https://www.gutenberg.org/ebooks/categories), fetched live 2026-07-04 --
# these are PG's real bookshelf groupings, not invented. "Frequently
# Downloaded" (https://www.gutenberg.org/browse/scores/top) is PG's own name
# for its top-100-by-downloads list; Gutendex's default sort order (no
# filters applied) IS download-count-descending per Gutendex's own docs, so
# CATEGORY_TOP100 below needs no `topic` filter at all -- it's a direct
# equivalent, not an approximation.
#
# For every other category, Gutendex has one real filter that fits:
# `topic=` -- "a case-insensitive key-phrase search in books' bookshelves or
# subjects" (Gutendex docs). It's a substring match, not an exact-name
# lookup, so CATEGORY_TOPIC below uses short plain keywords rather than
# PG's full punctuated display labels (e.g. "Mystery" rather than "Crime,
# Thrillers & Mystery") -- full labels with commas/ampersands are less
# likely to substring-match real subject/bookshelf text.
#
# IMPORTANT -- NOT YET LIVE-VERIFIED: unlike every pub code in jw_fetch.py,
# these topic keywords could NOT be tested against the real Gutendex API
# from this session (gutendex.com is blocked by this sandbox's egress
# allowlist, and web_fetch is blocked by gutendex.com's robots.txt). If any
# category comes back empty on-device, tell Claude which one so the keyword
# can be adjusted -- don't assume the category is genuinely empty.
CATEGORY_TOP100 = "Top 100 (Most Downloaded)"
CATEGORY_ADVENTURE = "Adventure"
CATEGORY_CLASSICS = "Classics"
CATEGORY_SCIFI_FANTASY = "Science Fiction & Fantasy"
CATEGORY_MYSTERY = "Crime, Thrillers & Mystery"
CATEGORY_ROMANCE = "Romance"
CATEGORY_HUMOR = "Humour"
CATEGORY_MYTHOLOGY = "Mythology, Legends & Folklore"
CATEGORY_POETRY = "Poetry"
CATEGORY_PLAYS = "Plays & Drama"
CATEGORY_SHORT_STORIES = "Short Stories"
CATEGORY_CHILDRENS = "Children & Young Adult"
CATEGORY_HISTORY = "History"
CATEGORY_BIOGRAPHIES = "Biographies"
CATEGORY_PHILOSOPHY_RELIGION = "Philosophy & Religion"
CATEGORY_SCIENCE = "Science & Technology"
CATEGORY_TRAVEL = "Travel Writing"

CATEGORIES = [
    CATEGORY_TOP100, CATEGORY_ADVENTURE, CATEGORY_CLASSICS,
    CATEGORY_SCIFI_FANTASY, CATEGORY_MYSTERY, CATEGORY_ROMANCE,
    CATEGORY_HUMOR, CATEGORY_MYTHOLOGY, CATEGORY_POETRY, CATEGORY_PLAYS,
    CATEGORY_SHORT_STORIES, CATEGORY_CHILDRENS, CATEGORY_HISTORY,
    CATEGORY_BIOGRAPHIES, CATEGORY_PHILOSOPHY_RELIGION, CATEGORY_SCIENCE,
    CATEGORY_TRAVEL,
]

# Maps each category (except CATEGORY_TOP100, which uses no filter) to the
# short keyword passed as Gutendex's `topic=` param.
CATEGORY_TOPIC = {
    CATEGORY_ADVENTURE:            "Adventure",
    CATEGORY_CLASSICS:             "Classic",
    CATEGORY_SCIFI_FANTASY:        "Science Fiction",
    CATEGORY_MYSTERY:              "Mystery",
    CATEGORY_ROMANCE:              "Romance",
    CATEGORY_HUMOR:                "Humor",
    CATEGORY_MYTHOLOGY:            "Mythology",
    CATEGORY_POETRY:               "Poetry",
    CATEGORY_PLAYS:                "Drama",
    CATEGORY_SHORT_STORIES:        "Short Stories",
    CATEGORY_CHILDRENS:            "Children",
    CATEGORY_HISTORY:              "History",
    CATEGORY_BIOGRAPHIES:          "Biography",
    CATEGORY_PHILOSOPHY_RELIGION:  "Philosophy",
    CATEGORY_SCIENCE:              "Science",
    CATEGORY_TRAVEL:               "Travel",
}


# ---------------------------------------------------------------------------
# Internal helpers (prefixed _ to signal they're not part of the plugin
# contract -- main.py never calls these directly)
# ---------------------------------------------------------------------------

def _get_json(url):
    """Fetch a URL and parse the response body as JSON.
    Raises urllib.error.URLError, TimeoutError, ValueError, or OSError on
    failure -- callers catch these and convert to user-facing error strings.
    We set both User-Agent and Accept headers: User-Agent for politeness,
    Accept to signal we want JSON (some servers use this to pick a format)."""
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def _safe_filename(title, book_id):
    """Convert a Gutendex title into a safe local filename.

    Gutendex titles can contain characters that are awkward as filenames --
    slashes, colons from subtitles, curly quotes, etc. We strip everything
    that isn't alphanumeric, whitespace, or a hyphen; collapse whitespace;
    cap the length at 80 chars so filenames stay readable in the Library
    list and safe on any filesystem muOS might use. If the title strips
    down to nothing (e.g. a title made entirely of special characters),
    fall back to a numeric ID so the file is still distinguishable."""
    cleaned = re.sub(r"[^\w\s-]", "", title, flags=re.UNICODE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        cleaned = f"gutenberg-{book_id}"
    return f"{cleaned[:80]}.epub"


def _book_to_item(book):
    """Convert one Gutendex book object (a dict from the JSON response)
    into a plugin item dict that main.py's browse/download UI can display.

    Returns None if the book has no EPUB format available -- those books
    are silently skipped rather than showing a broken entry in the list.

    Key decisions:
    - Authors: Gutendex returns a list of {"name": ..., "birth_year": ...}
      objects. We join all names with ", " for a natural display string.
    - EPUB URL: Gutendex's "formats" dict maps MIME types to URLs. We look
      for any key starting with "application/epub" (there can be more than
      one variant, e.g. with/without embedded cover images). We take the
      first match in whatever order Gutendex returns -- no preference logic,
      because earlier attempts to prefer a "noimages" variant were never
      verified against a real response and checked the wrong string entirely.
      If download size ever matters on this hardware, revisit with a real
      device response first.
    - _id: stored for traceability (not used by main.py directly)."""
    title = book.get("title") or "(untitled)"
    authors = book.get("authors") or []
    author_names = ", ".join(a.get("name", "") for a in authors if a.get("name"))
    formats = book.get("formats") or {}

    epub_url = None
    for mime, url in formats.items():
        if mime.startswith("application/epub"):
            epub_url = url
            break
    if not epub_url:
        return None  # no EPUB available -- skip this book silently

    book_id = book.get("id")
    return {
        "title":         title,
        "subtitle":      author_names or "Unknown author",
        "filename":      _safe_filename(title, book_id),
        "_download_url": epub_url,
        "_id":           book_id,
    }


# ---------------------------------------------------------------------------
# Required plugin functions
# ---------------------------------------------------------------------------

def list_items(query=None, page=1, category=None):
    """Browse popular books, optionally scoped to a category, and/or
    search by title/author.

    Called by main.py whenever the download browse screen needs data:
    - On first open with no category (query=None, page=1, category=None):
      returns the most-downloaded books on Gutenberg -- a good default
      browse experience, no typing needed.
    - After picking a category (see CATEGORIES/CATEGORY_TOPIC above):
      CATEGORY_TOP100 applies no extra filter (Gutendex's default sort IS
      download-count order, so it's already PG's own "Frequently
      Downloaded" list). Every other category adds Gutendex's `topic=`
      filter using the matching keyword from CATEGORY_TOPIC.
    - After a Y-button search (query="some words"): passes the search string
      to Gutendex's `search` param, which matches both title and author
      fields, case-insensitively. This still combines with an open category,
      same as jw_fetch.py's per-category search.
    - On L/R page turn (page > 1): fetches the next/previous page.

    Returns (items, has_next, error):
      items     list of item dicts (may be empty)
      has_next  bool -- True if there's a next page (Gutendex provides a
                "next" URL when there is)
      error     str or None -- network/parse error message, or None on success

    Why catch so many exception types? urllib can raise URLError (network),
    TimeoutError (timeout), ValueError (bad JSON), or OSError (low-level
    socket error) -- we want all of them to surface as readable strings
    rather than crashing the background thread."""
    params = {"page": str(page)}
    if query:
        params["search"] = query  # Gutendex search: case-insensitive, title+author
    topic = CATEGORY_TOPIC.get(category) if category else None
    if topic:
        params["topic"] = topic  # case-insensitive substring match on bookshelf/subject
    url = API_BASE + "?" + urllib.parse.urlencode(params)
    try:
        data = _get_json(url)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as e:
        return [], False, str(e)

    items = []
    for book in data.get("results", []):
        item = _book_to_item(book)
        if item:           # None means no EPUB available -- skip
            items.append(item)
    has_next = bool(data.get("next"))  # Gutendex sets "next" to null on last page
    return items, has_next, None


def download(item, dest_dir):
    """Download the EPUB for `item` into `dest_dir`.

    Called by main.py on a background thread (never on the main/UI thread)
    so the interface stays responsive during the download. This is important
    on slower hardware/connections -- never do network I/O on the main thread.

    Strategy:
    - Write to a .part temp file first, then atomically rename on success.
      This means an interrupted download never leaves a corrupt .epub in the
      library -- the partial file is cleaned up on failure.
    - Stream in 64 KB chunks to keep memory use flat regardless of file size.
      Loading the whole EPUB into memory first would be wasteful on a 1GB
      device and could cause issues with large files.
    - Check for an existing file BEFORE downloading to avoid re-downloading
      something already in the library (and to give a clear message why).

    Returns (ok, message, dest_path):
      ok         True on success, False on failure
      message    Short human-readable string shown as an on-screen toast
      dest_path  Full path of saved file on success, None on failure"""
    url = item.get("_download_url")
    if not url:
        return False, "No download URL for this item", None

    dest_path = os.path.join(dest_dir, item["filename"])
    if os.path.exists(dest_path):
        return False, f'"{item["filename"]}" already in Library', dest_path

    tmp_path = dest_path + ".part"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            with open(tmp_path, "wb") as f:
                while True:
                    chunk = resp.read(65536)  # 64 KB chunks -- keeps RAM use flat
                    if not chunk:
                        break
                    f.write(chunk)
        os.replace(tmp_path, dest_path)  # atomic rename -- safe even if interrupted
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        # Clean up the partial file so a retry starts fresh
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
        return False, f"Download failed: {e}", None

    return True, f'Downloaded "{item["title"]}"', dest_path
