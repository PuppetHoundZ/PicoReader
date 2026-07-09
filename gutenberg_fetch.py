"""
gutenberg_fetch.py

Optional PicoReader plugin: browse and download public-domain EPUBs from
Project Gutenberg via Project Gutenberg's OWN official OPDS catalog feed
(www.gutenberg.org/ebooks/search.opds/) -- switched (v0.1.141) from the
earlier Gutendex-based version. See v0.1.141 changelog in main.py for why.

WHY OPDS INSTEAD OF GUTENDEX:
  Gutendex (gutendex.com) is a solid community project, but it's a THIRD
  PARTY host separate from gutenberg.org -- meaning book search depended on
  a completely different service than the one we actually download EPUBs
  from. OPDS (Open Publication Distribution System) is Project Gutenberg's
  own official catalog feed format, served directly from gutenberg.org --
  the same host every EPUB download already comes from. One trusted host
  instead of two. Confirmed live (2026-07-08): search, pagination, and
  per-book acquisition links (with exact byte sizes and multiple EPUB
  variants -- .epub.images, .epub3.images, .epub.noimages) all work.

  TRADE-OFF, worth knowing: OPDS has no subject/topic FILTER param (unlike
  Gutendex's `topic=`). It only offers three sort orders (downloads/
  release_date/random) plus free-text `query=` (matches title, author, AND
  subject/bookshelf text -- confirmed live: query="Mystery" surfaces real
  mystery novels like Dracula and Sherlock Holmes, not just books with the
  literal word "mystery" in the title). So CATEGORY_TOPIC keywords below
  are now fed through the free-text query param instead of a real filter --
  same category list, slightly fuzzier matching, but genuinely tested
  (unlike the old Gutendex topic= list, which was never live-verified).

  ALSO WORTH KNOWING: gutenberg.org throttles/503s on bursts of rapid
  requests from the same client (confirmed live -- several requests inside
  a couple seconds triggered temporary 403/503s that cleared 15-20s later,
  even with a plain browser User-Agent). This isn't a permanent block and
  isn't User-Agent-specific (our honest, descriptive USER_AGENT below
  works fine once request pacing is reasonable) -- just don't hammer it in
  a tight loop. Normal single-request UI interactions on-device are nowhere
  near this threshold.

  OPDS book-listing entries do NOT include direct download links -- only a
  "subsection" link to that book's own .opds detail page, which DOES have
  the real acquisition links. So download() does one extra request (fetch
  the book's own .opds page, then download the EPUB) -- same two-step
  shape as jw_fetch.py's resolve-then-download pattern elsewhere in this
  project.

THIRD-PARTY API -- NOT OUR CODE, but now the OFFICIAL one:
  This calls Project Gutenberg's own public OPDS feed directly. No
  separate third-party service in the loop for search.

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
            "_gb_id": int           -- Gutenberg book ID, resolved to a real
                                        download URL by download() itself
        has_next: bool -- True if page+1 has more results
        error: str or None -- human-readable error, or None on success
    download(item, dest_dir) -> (ok: bool, message: str, dest_path: str|None)
        Resolves item["_gb_id"] to a real EPUB URL (one extra request to
        that book's own .opds detail page), then fetches and writes it to
        dest_dir/filename. Returns a short human-readable status message
        either way (shown as an on-screen toast) and the saved path on
        success.

  Optional flags (declare at module level):
    SUPPORTS_SEARCH = True
        Tells main.py to show a Y-button search entry screen. Implement
        list_items(query=...) to handle the typed search string.
    SUPPORTS_CATEGORIES = True
        Tells main.py to show the category-picker screen before browse.

No pip dependencies -- stdlib urllib + xml.etree.ElementTree only, matching
the rest of PicoReader. The target device (Anbernic RG CubeXX-H, muOS) has
no pip available. Every plugin must be self-contained pure Python stdlib.
xml.etree.ElementTree is already a real dependency elsewhere in this
project (epub_engine.py parses XHTML with it), so this isn't new surface
area.
"""

import os
import re
import urllib.request
import urllib.error
import urllib.parse
import xml.etree.ElementTree as ET

# ---------------------------------------------------------------------------
# Plugin identity and capability flags
# ---------------------------------------------------------------------------

PLUGIN_NAME = "Project Gutenberg"

SUPPORTS_SEARCH = True
SUPPORTS_CATEGORIES = True

# ---------------------------------------------------------------------------
# API configuration
# ---------------------------------------------------------------------------

SEARCH_BASE = "https://www.gutenberg.org/ebooks/search.opds/"
PAGE_SIZE = 25

BOOK_DETAIL_URL = "https://www.gutenberg.org/ebooks/{id}.opds"

REQUEST_TIMEOUT = 15

USER_AGENT = "PicoReader/1.0 (muOS EPUB reader; personal, non-commercial)"

NS = {
    "a":    "http://www.w3.org/2005/Atom",
    "opds": "http://opds-spec.org/2010/catalog",
}

_BOOK_HREF_RE = re.compile(r"/ebooks/(\d+)\.opds$")

_EPUB_VARIANT_PREFERENCE = ["EPUB (older E-readers)", "EPUB3 (E-readers incl. Send-to-Kindle)"]

# ---------------------------------------------------------------------------
# Category catalog
# ---------------------------------------------------------------------------

CATEGORY_POPULAR = "Popular"
CATEGORY_LATEST = "Latest"
CATEGORY_RANDOM = "Random"
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
    CATEGORY_POPULAR, CATEGORY_LATEST, CATEGORY_RANDOM,
    CATEGORY_ADVENTURE, CATEGORY_CLASSICS,
    CATEGORY_SCIFI_FANTASY, CATEGORY_MYSTERY, CATEGORY_ROMANCE,
    CATEGORY_HUMOR, CATEGORY_MYTHOLOGY, CATEGORY_POETRY, CATEGORY_PLAYS,
    CATEGORY_SHORT_STORIES, CATEGORY_CHILDRENS, CATEGORY_HISTORY,
    CATEGORY_BIOGRAPHIES, CATEGORY_PHILOSOPHY_RELIGION, CATEGORY_SCIENCE,
    CATEGORY_TRAVEL,
]

# v0.1.143: Kaleb asked to drop the redundant CATEGORY_TOP100 (our own
# invented label) since it was functionally identical to CATEGORY_POPULAR
# (both sort_order=downloads) -- CATEGORY_POPULAR kept as the sole entry,
# using Project Gutenberg's OWN official label. Confirmed live: the
# top-level OPDS root catalog (www.gutenberg.org/ebooks.opds/) itself
# titles these exact three entries "Popular", "Latest", "Random" --
# these aren't names we made up, they're Project Gutenberg's own naming
# for these three sort orders.
CATEGORY_SORT_ORDER = {
    CATEGORY_POPULAR: "downloads",
    CATEGORY_LATEST:  "release_date",
    CATEGORY_RANDOM:  "random",
}

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
# Internal helpers
# ---------------------------------------------------------------------------

def _get_xml(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/atom+xml",
    })
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        body = resp.read()
    return ET.fromstring(body)


def _safe_filename(title, book_id):
    cleaned = re.sub(r"[^\w\s-]", "", title or "", flags=re.UNICODE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        cleaned = f"gutenberg-{book_id}"
    return f"{cleaned[:80]}.epub"


def _entry_to_item(entry):
    sub = entry.find("a:link[@rel='subsection']", NS)
    href = sub.get("href") if sub is not None else None
    m = _BOOK_HREF_RE.search(href or "")
    if not m:
        return None
    book_id = int(m.group(1))

    title_el = entry.find("a:title", NS)
    title = (title_el.text if title_el is not None else None) or "(untitled)"
    content_el = entry.find("a:content", NS)
    author = (content_el.text if content_el is not None else None) or "Unknown author"

    return {
        "title":    title,
        "subtitle": author,
        "filename": _safe_filename(title, book_id),
        "_gb_id":   book_id,
    }


def _resolve_download_url(book_id):
    url = BOOK_DETAIL_URL.format(id=book_id)
    try:
        root = _get_xml(url)
    except (urllib.error.URLError, TimeoutError, ET.ParseError, OSError) as e:
        return None, str(e)

    candidates = {}
    for entry in root.findall("a:entry", NS):
        for link in entry.findall("a:link", NS):
            if (link.get("type") == "application/epub+zip"
                    and link.get("rel") == "http://opds-spec.org/acquisition"):
                candidates[link.get("title", "")] = link.get("href")
    if not candidates:
        for link in root.findall("a:link", NS):
            if (link.get("type") == "application/epub+zip"
                    and link.get("rel") == "http://opds-spec.org/acquisition"):
                candidates[link.get("title", "")] = link.get("href")
    if not candidates:
        return None, "No EPUB available for this book"

    for preferred in _EPUB_VARIANT_PREFERENCE:
        if preferred in candidates:
            return candidates[preferred], None
    return next(iter(candidates.values())), None


# ---------------------------------------------------------------------------
# Required plugin functions
# ---------------------------------------------------------------------------

def list_items(query=None, page=1, category=None):
    parts = []
    if query:
        parts.append(query)
    topic = CATEGORY_TOPIC.get(category) if category else None
    if topic:
        parts.append(topic)
    combined_query = " ".join(parts) if parts else None

    params = {}
    if combined_query:
        params["query"] = combined_query
    sort_order = CATEGORY_SORT_ORDER.get(category, "downloads" if category is None else None)
    if sort_order:
        params["sort_order"] = sort_order
    start_index = (page - 1) * PAGE_SIZE + 1
    if start_index > 1:
        params["start_index"] = str(start_index)

    url = SEARCH_BASE + "?" + urllib.parse.urlencode(params)
    try:
        root = _get_xml(url)
    except (urllib.error.URLError, TimeoutError, ET.ParseError, OSError) as e:
        return [], False, str(e)

    items = []
    for entry in root.findall("a:entry", NS):
        item = _entry_to_item(entry)
        if item:
            items.append(item)
    has_next = root.find("a:link[@rel='next']", NS) is not None
    return items, has_next, None


def download(item, dest_dir):
    book_id = item.get("_gb_id")
    if not book_id:
        return False, "No book ID for this item", None

    dest_path = os.path.join(dest_dir, item["filename"])
    if os.path.exists(dest_path):
        return False, f'"{item["filename"]}" already in Library', dest_path

    url, err = _resolve_download_url(book_id)
    if not url:
        return False, err or "Could not resolve a download link", None

    tmp_path = dest_path + ".part"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
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
