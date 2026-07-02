"""
gutenberg_fetch.py

Optional PicoReader plugin: browse and download public-domain EPUBs from
Project Gutenberg via Gutendex (a community-run, read-only JSON API over
Project Gutenberg's catalog -- Project Gutenberg itself has no official
JSON API, only nightly XML/RDF archives; Gutendex exists specifically to
make that catalog easy to query). https://gutendex.com -- source/schema
docs: https://github.com/garethbjohnson/gutendex

LEGAL: Project Gutenberg content is not restricted by U.S. copyright law
(the vast majority of the catalog). Per Project Gutenberg's own policy
(gutenberg.org/policy/permission.html): "No permission is needed for
non-commercial use... you can freely redistribute any eBook, anywhere,
any time, with or without the 'Project Gutenberg' trademark included."
Safe to publish this file publicly.

PLUGIN CONTRACT (see main.py's plugin-loading code for how this is used):
    PLUGIN_NAME: str -- shown in the UI when more than one plugin is present
    list_items(query=None, page=1) -> (items, has_next)
        items: list of dicts, each with at minimum:
            "title": str            -- shown in the browse list
            "subtitle": str         -- shown as a dimmer second line (author)
            "filename": str         -- suggested local filename, no path
            "_download_url": str    -- resolved EPUB URL for download()
        has_next: bool -- whether page+1 has more results
    download(item, dest_dir) -> (ok: bool, message: str, dest_path: str|None)
        Fetches item["_download_url"] and writes it to dest_dir. Returns
        a short human-readable message either way (used as the on-screen
        status toast) and the final path on success.

No pip dependencies -- stdlib urllib only, matching the rest of PicoReader.
"""

import json
import os
import re
import urllib.request
import urllib.error
import urllib.parse

PLUGIN_NAME = "Project Gutenberg"
SUPPORTS_SEARCH = True  # main.py only offers the on-screen search/letter-
                         # grid for plugins that declare this -- jw_fetch's
                         # catalog is small and fixed, so it doesn't

API_BASE = "https://gutendex.com/books/"
REQUEST_TIMEOUT = 15
USER_AGENT = "PicoReader/1.0 (muOS EPUB reader; personal, non-commercial)"


def _get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def _safe_filename(title, book_id):
    # Gutendex titles can contain characters that are awkward as filenames
    # (slashes, colons from subtitles) -- strip anything that isn't
    # alnum/space/hyphen, collapse whitespace, cap length so it stays
    # readable in the Library list and safe on any filesystem.
    cleaned = re.sub(r"[^\w\s-]", "", title, flags=re.UNICODE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        cleaned = f"gutenberg-{book_id}"
    return f"{cleaned[:80]}.epub"


def _book_to_item(book):
    title = book.get("title") or "(untitled)"
    authors = book.get("authors") or []
    author_names = ", ".join(a.get("name", "") for a in authors if a.get("name"))
    formats = book.get("formats") or {}
    # NOTE: Gutendex sometimes lists more than one EPUB variant (e.g. with
    # and without embedded cover images) under different MIME-type keys.
    # An earlier version of this tried to prefer a "noimages" variant for
    # faster downloads on this hardware, but that logic was never
    # verified against a real Gutendex response (this sandbox can't reach
    # gutendex.com) and turned out to be checking the wrong string
    # entirely -- removed rather than ship unverified guessing. This just
    # takes the first application/epub* entry, in whatever order Gutendex
    # returns. Revisit with a real device/response if download size ever
    # turns out to matter in practice.
    epub_url = None
    for mime, url in formats.items():
        if mime.startswith("application/epub"):
            epub_url = url
            break
    if not epub_url:
        return None
    book_id = book.get("id")
    return {
        "title": title,
        "subtitle": author_names or "Unknown author",
        "filename": _safe_filename(title, book_id),
        "_download_url": epub_url,
        "_id": book_id,
    }


def list_items(query=None, page=1):
    """Browse popular books (default, no typing required -- this device
    has no on-screen keyboard yet) or search by title/author words if a
    query string is supplied by a future UI. Returns (items, has_next)."""
    params = {"page": str(page)}
    if query:
        params["search"] = query
    url = API_BASE + "?" + urllib.parse.urlencode(params)
    try:
        data = _get_json(url)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as e:
        return [], False, str(e)

    items = []
    for book in data.get("results", []):
        item = _book_to_item(book)
        if item:
            items.append(item)
    has_next = bool(data.get("next"))
    return items, has_next, None


def download(item, dest_dir):
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
