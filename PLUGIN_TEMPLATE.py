"""
PLUGIN_TEMPLATE.py

Template for writing a custom PicoReader downloader plugin.
Copy this file, rename it (e.g. my_source_fetch.py), fill in the
sections marked TODO, and drop it in the PicoReader/ app folder.
PicoReader will detect and load it automatically on next launch --
no other files need to be changed.

HOW LOADING WORKS:
  main.py scans a fixed list of known plugin filenames at startup via a
  defensive try/except __import__ loop. To have your plugin loaded, its
  filename must be added to that list in main.py. If the file is missing
  or fails to import, the app silently skips it -- no crash, no broken
  menu items. Dropping the file back in and restarting restores it.

REQUIREMENTS:
  - Pure Python stdlib only (no pip/external packages).
    PicoReader runs on muOS (MustardOS) on ARM hardware with no pip.
  - Your plugin must deliver EPUB files. Other formats are not supported.
  - Keep memory use bounded -- the target device has 1GB RAM total.
    Stream downloads in chunks (see the example below); don't load
    entire responses into memory at once.
  - Respect the terms of service of any API or website you query.

PLUGIN CONTRACT -- implement all three required items below:
  PLUGIN_NAME       str
  list_items()      function
  download()        function

OPTIONAL FLAGS (declare these at module level if you want them):
  SUPPORTS_SEARCH = True
      Tells main.py to show a Y-button search option in the browse
      screen. Implement list_items(query=...) to handle the typed query.

  SUPPORTS_MANUAL_CODE = True
      Tells main.py to show a Y-button code-entry screen instead of
      search (used for sources that need a specific publication code
      rather than a free-text search). Implement lookup_pub_code() too.

  MANUAL_CODE_HINT = "short hint string"
      One-line hint shown on the code-entry screen, e.g. which codes
      are valid. Only used when SUPPORTS_MANUAL_CODE = True.
"""

import json
import os
import urllib.request
import urllib.error
import urllib.parse

# ---------------------------------------------------------------------------
# REQUIRED: Plugin display name -- shown in the source-picker UI when more
# than one plugin is installed.
# ---------------------------------------------------------------------------
PLUGIN_NAME = "My Source"  # TODO: replace with your source's name

# ---------------------------------------------------------------------------
# OPTIONAL FLAGS -- uncomment whichever apply to your plugin.
# ---------------------------------------------------------------------------
# SUPPORTS_SEARCH = True
# SUPPORTS_MANUAL_CODE = True
# MANUAL_CODE_HINT = "Enter a code, e.g. ABC123"

# ---------------------------------------------------------------------------
# Internal constants -- adjust to suit your source.
# ---------------------------------------------------------------------------
API_BASE = "https://example.com/api/"         # TODO: your API base URL
REQUEST_TIMEOUT = 15                           # seconds
USER_AGENT = "PicoReader/1.0 (muOS EPUB reader; personal, non-commercial)"


# ---------------------------------------------------------------------------
# REQUIRED: list_items(query=None, page=1)
#
# Called by main.py to populate the browse/search results list.
#
# Parameters:
#   query   str or None -- typed search string, or None for default browse
#   page    int         -- 1-based page number for pagination
#
# Returns:
#   (items, has_next, error)
#   items     list of dicts  -- see item dict format below
#   has_next  bool           -- True if page+1 has more results
#   error     str or None    -- human-readable error string, or None on success
#
# Item dict format (all keys required):
#   "title"          str  -- main line shown in the browse list
#   "subtitle"       str  -- dimmer second line (e.g. author name)
#   "filename"       str  -- suggested local filename, no path, e.g. "book.epub"
#   "_download_url"  str  -- direct URL passed to download() below
#
# Extra keys are fine and ignored by main.py.
# ---------------------------------------------------------------------------
def list_items(query=None, page=1):
    params = {"page": str(page)}
    if query:
        params["search"] = query  # TODO: adjust param name to match your API

    url = API_BASE + "books/?" + urllib.parse.urlencode(params)  # TODO: adjust path

    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return [], False, str(e)

    items = []
    for result in data.get("results", []):   # TODO: adjust to your API's shape
        epub_url = result.get("epub_url")    # TODO: adjust field name
        if not epub_url:
            continue
        items.append({
            "title":         result.get("title", "(untitled)"),
            "subtitle":      result.get("author", "Unknown author"),
            "filename":      _safe_filename(result.get("title", ""), result.get("id")),
            "_download_url": epub_url,
        })

    has_next = bool(data.get("next"))        # TODO: adjust to your API's shape
    return items, has_next, None


# ---------------------------------------------------------------------------
# REQUIRED: download(item, dest_dir)
#
# Called by main.py (on a background thread) when the user confirms a
# download. Fetch the EPUB and write it to dest_dir.
#
# Parameters:
#   item      dict  -- one of the dicts returned by list_items()
#   dest_dir  str   -- absolute path to the PicoReader library folder
#
# Returns:
#   (ok, message, dest_path)
#   ok         bool      -- True on success, False on failure
#   message    str       -- short human-readable status (shown as a toast)
#   dest_path  str|None  -- full path of the saved file on success, else None
# ---------------------------------------------------------------------------
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
                    chunk = resp.read(65536)  # 64 KB chunks -- keeps RAM use flat
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


# ---------------------------------------------------------------------------
# OPTIONAL: lookup_pub_code(code, issue=None)
#
# Only needed if you set SUPPORTS_MANUAL_CODE = True above.
# Called when the user types a code on the manual-entry screen.
#
# Parameters:
#   code   str       -- the typed publication code
#   issue  str|None  -- optional issue identifier (e.g. "202604")
#
# Returns:
#   (item, error)
#   item   dict|None  -- a single item dict (same format as list_items),
#                        or None on failure
#   error  str|None   -- human-readable error, or None on success
# ---------------------------------------------------------------------------
# def lookup_pub_code(code, issue=None):
#     # TODO: look up the code against your API and return one item dict
#     return None, "Not implemented"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _safe_filename(title, book_id):
    """Strips characters that are unsafe in filenames, caps length."""
    import re
    cleaned = re.sub(r"[^\w\s-]", "", title, flags=re.UNICODE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        cleaned = f"book-{book_id}"
    return f"{cleaned[:80]}.epub"
