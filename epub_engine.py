"""
epub_engine.py

Standalone EPUB parsing/navigation engine -- no UI code.
Handles: manifest/spine parsing, table of contents (NCX + nav.xhtml),
internal hyperlink resolution (same-file anchors, cross-file anchors,
footnote/noteref pairs), inline images, and back-stack navigation.

STDLIB ONLY -- no BeautifulSoup/lxml dependency, so this runs on a bare
muOS python3 with zero pip installs. Uses xml.etree.ElementTree, which
handles the well-formed XHTML that real-world EPUB3 files (including JW
publications) produce.

Designed to be UI-agnostic so it can be driven from a terminal or an
SDL2 render loop.
"""

from __future__ import annotations
import zipfile
import posixpath
import bisect
import os
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

NS = {
    "container": "urn:oasis:names:tc:opendocument:xmlns:container",
    "opf": "http://www.idpf.org/2007/opf",
    "dc": "http://purl.org/dc/elements/1.1/",
    "ncx": "http://www.daisy.org/z3986/2005/ncx/",
    "xhtml": "http://www.w3.org/1999/xhtml",
    "epub": "http://www.idpf.org/2007/ops",
}

# v0.1.151: populated by main.py at startup (set_active_glyph_subs()),
# after it checks the ACTIVE bundled font's real cmap via
# TTF_GlyphIsProvided32 -- see the call site in main.py right after
# FONT_PATH is resolved for the full reasoning. Starts as an empty dict
# (not a hardcoded per-font table) so that if this module is ever used
# standalone/without main.py calling the setter, text passes through
# unmodified rather than guessing at substitutions for a font state it
# can't actually see.
_ACTIVE_GLYPH_SUBS = {}


def set_active_glyph_subs(subs: dict) -> None:
    """Replace the active glyph-substitution table. Called once by
    main.py at startup with only the entries the active font actually
    needs (i.e. codepoints TTF_GlyphIsProvided32 reported as missing)."""
    global _ACTIVE_GLYPH_SUBS
    _ACTIVE_GLYPH_SUBS = dict(subs)


def _local(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


def _find_all_local(elem, tagname):
    return [e for e in elem.iter() if _local(e.tag) == tagname]


def _find_local(elem, tagname):
    for e in elem.iter():
        if _local(e.tag) == tagname:
            return e
    return None


def _children_local(elem, tagname):
    return [e for e in elem if _local(e.tag) == tagname]


@dataclass
class TocEntry:
    title: str
    href: str
    level: int
    children: list = field(default_factory=list)


@dataclass
class LinkSpan:
    start: int
    end: int
    target_file: str
    target_anchor: str | None
    kind: str
    href: str = ""  # v0.1.98: raw href, only populated for kind="external"
                    # (internal links already navigate via target_file/
                    # target_anchor and don't need it).


@dataclass
class ImageSpan:
    start: int
    end: int
    src: str
    alt: str


@dataclass
class StyleSpan:
    """A character range that should render bold and/or italic -- from
    <strong>/<b> and <em>/<i> in the source HTML (v0.1.35). Overlapping
    spans (e.g. <strong><em>...) are represented as separate StyleSpan
    entries covering the same range rather than one span with both flags,
    which keeps get_page()'s return shape simple; the renderer merges
    them per character range when building styled runs."""
    start: int
    end: int
    bold: bool
    italic: bool


@dataclass
class ParaSpan:
    """Paragraph-level formatting hint (v0.1.42). Covers an absolute text
    range (start..end) and carries a 'kind' that the renderer uses to
    pick font, colour, and indent. Unlike StyleSpan (character-level
    bold/italic), these are whole-paragraph traits applied once per line
    during draw_reader().

    Kinds:
      superscript  -- <sup> inline marker (v0.1.42)
      caption      -- <figcaption> text below an image (v0.1.42)
      box_rule     -- synthetic rule line emitted around boxSupplement (v0.1.42)
    Note: JW paragraph classes sm/sh/si/sb/sj removed in v0.1.47 --
    they caused unwanted italic, indent, small font and greying.
    """
    start: int
    end: int
    kind: str
    extra: str = ""   # reserved (box rule text)


def collapse_blank_line_runs(text, images, links, styles, para_spans, anchor_offsets):
    """v0.1.118: nested block-tag transitions (a </header> closing while
    <div class="bodyTxt"><div class="section"><div class="pGroup"> all
    open right before the first real <p>, for example) each independently
    call maybe_newline(), and incidental XML pretty-printing whitespace
    between sibling tags gets emitted as its own blank " " line by
    emit_text() -- neither dedupes against the OTHER mechanism, so a
    transition crossing several nested containers with no real content in
    between can stack up 2-4 blank lines where exactly one was intended.
    Confirmed on a real Awake! cover article (Kaleb's report + photos):
    the </header>-to-first-<p> transition alone produced 4 blank lines,
    and every <ul><li> boundary (the Anja/Delina/Gregory bullet list)
    doubled up to 2 blank lines instead of 1, because the <li>'s own
    block-boundary blank line stacked with its child <p>'s.

    This collapses any run of 2+ consecutive whitespace-only lines down to
    exactly 1, and remaps every recorded image/link/style/para/anchor
    offset to match -- safe because no span or anchor is ever placed
    inside pure whitespace, so nothing meaningful can fall inside a
    deleted range."""
    lines = text.split("\n")
    line_spans = []  # (start, end) in the ORIGINAL text; end excludes the "\n"
    pos = 0
    for line in lines:
        start = pos
        end = pos + len(line)
        line_spans.append((start, end))
        pos = end + 1

    is_blank = [line.strip() == "" for line in lines]

    delete_ranges = []
    for i in range(1, len(lines)):
        if is_blank[i] and is_blank[i - 1]:
            # drop this line's own leading "\n" + content: [end of line
            # i-1, end of line i) -- the following "\n" then correctly
            # becomes the sole separator before whatever comes next.
            delete_ranges.append((line_spans[i - 1][1], line_spans[i][1]))

    if not delete_ranges:
        return text, images, links, styles, para_spans, anchor_offsets

    # v26.07.09.16 BUG FIX: same underlying pattern as main.py's
    # style_at()/_compute_line_style_runs() fixes (v26.07.09.15/.16) --
    # remap() used to do a scan over delete_ranges (early-break once past
    # the query offset, but still O(ranges before offset) per call) for
    # EVERY offset being remapped. On Enjoy Life Forever's largest page
    # (4.5M chars, many collapsed-blank-line ranges), this was called
    # 134,097 times (once per image/link/style/anchor offset) and was the
    # single largest remaining cost after the style_at() fix -- confirmed
    # via profiling, ~7 of ~16s total. Fixed with a precomputed cumulative-
    # shift array (delete_ranges is already naturally sorted and non-
    # overlapping, built from sequential line indices) and bisect, giving
    # O(log ranges) per call instead.
    _ends = [de for _ds, de in delete_ranges]
    _cum_shift = []
    _running = 0
    for _ds, _de in delete_ranges:
        _running += (_de - _ds)
        _cum_shift.append(_running)

    def remap(offset):
        idx = bisect.bisect_right(_ends, offset) - 1
        if idx < 0:
            return offset
        shift = _cum_shift[idx]
        # defensive clamp (matches original's "shouldn't occur" case):
        # offset falls INSIDE the next range rather than before/after it
        if idx + 1 < len(delete_ranges):
            nds, nde = delete_ranges[idx + 1]
            if nds < offset < nde:
                shift += (offset - nds)
        return offset - shift

    out = []
    cursor = 0
    for ds, de in delete_ranges:
        out.append(text[cursor:ds])
        cursor = de
    out.append(text[cursor:])
    new_text = "".join(out)

    for im in images:
        im.start, im.end = remap(im.start), remap(im.end)
    for ln in links:
        ln.start, ln.end = remap(ln.start), remap(ln.end)
    for sp in styles:
        sp.start, sp.end = remap(sp.start), remap(sp.end)
    for ps in para_spans:
        ps.start, ps.end = remap(ps.start), remap(ps.end)
    for k in list(anchor_offsets.keys()):
        anchor_offsets[k] = remap(anchor_offsets[k])

    return new_text, images, links, styles, para_spans, anchor_offsets


class EpubDocument:
    def __init__(self, path: str, anchor_cache_path: str | None = None):
        self.path = path
        self.zip = zipfile.ZipFile(path, "r")
        self.opf_path, self.opf_dir = self._find_opf()
        self.manifest, self.spine, self.ncx_path, self.nav_path = self._parse_opf()
        self.toc: list[TocEntry] = self._parse_toc()
        self._anchor_index: dict[str, set[str]] | None = None
        self.anchor_cache_path = anchor_cache_path

    def _read(self, path: str) -> str:
        with self.zip.open(path) as f:
            return f.read().decode("utf-8", errors="replace")

    def _parse_xml(self, text: str):
        return ET.fromstring(text.encode("utf-8"))

    def _resolve(self, base_dir: str, href: str) -> str:
        href = href.split("#")[0]
        if not href:
            return ""
        return posixpath.normpath(posixpath.join(base_dir, href))

    def _find_opf(self):
        container = self._read("META-INF/container.xml")
        root = self._parse_xml(container)
        rootfile = _find_local(root, "rootfile")
        opf_path = rootfile.get("full-path")
        opf_dir = posixpath.dirname(opf_path)
        return opf_path, opf_dir

    def _parse_opf(self):
        opf_text = self._read(self.opf_path)
        root = self._parse_xml(opf_text)

        manifest = {}
        for item in _find_all_local(root, "item"):
            item_id = item.get("id")
            href = item.get("href")
            manifest[item_id] = posixpath.normpath(posixpath.join(self.opf_dir, href))

        spine = []
        spine_tag = _find_local(root, "spine")
        if spine_tag is not None:
            for itemref in _children_local(spine_tag, "itemref"):
                idref = itemref.get("idref")
                if idref in manifest:
                    spine.append(manifest[idref])

        ncx_path = None
        nav_path = None
        if spine_tag is not None:
            toc_attr = spine_tag.get("toc")
            if toc_attr and toc_attr in manifest:
                ncx_path = manifest[toc_attr]
        for item in _find_all_local(root, "item"):
            props = item.get("properties") or ""
            if "nav" in props.split():
                nav_path = manifest[item.get("id")]

        return manifest, spine, ncx_path, nav_path

    def _get_text(self, elem, tagname):
        found = _find_local(elem, tagname)
        return "".join(found.itertext()).strip() if found is not None else ""

    def _parse_toc(self) -> list[TocEntry]:
        if self.ncx_path:
            return self._parse_ncx(self.ncx_path)
        if self.nav_path:
            return self._parse_nav(self.nav_path)
        return [TocEntry(title=posixpath.basename(f), href=f, level=0) for f in self.spine]

    def _parse_ncx(self, ncx_path: str) -> list[TocEntry]:
        ncx_text = self._read(ncx_path)
        root = self._parse_xml(ncx_text)
        ncx_dir = posixpath.dirname(ncx_path)

        def walk(nav_point_container, level):
            entries = []
            for np in _children_local(nav_point_container, "navPoint"):
                title = self._get_text(np, "text")
                content_tag = _find_local(np, "content")
                src = content_tag.get("src") if content_tag is not None else ""
                href = self._resolve(ncx_dir, src)
                anchor = src.split("#", 1)[1] if "#" in src else None
                full_href = href + (f"#{anchor}" if anchor else "")
                entry = TocEntry(title=title or "(untitled)", href=full_href, level=level)
                entry.children = walk(np, level + 1)
                entries.append(entry)
            return entries

        nav_map = _find_local(root, "navMap")
        return walk(nav_map, 0) if nav_map is not None else []

    def _parse_nav(self, nav_path: str) -> list[TocEntry]:
        nav_text = self._read(nav_path)
        root = self._parse_xml(nav_text)
        nav_dir = posixpath.dirname(nav_path)

        toc_nav = None
        for nav_el in _find_all_local(root, "nav"):
            attrs = {k.split("}")[-1]: v for k, v in nav_el.attrib.items()}
            if attrs.get("type") == "toc":
                toc_nav = nav_el
                break
        if toc_nav is None:
            toc_nav = _find_local(root, "nav")
        if toc_nav is None:
            return []

        def walk(ol, level):
            entries = []
            if ol is None:
                return entries
            for li in _children_local(ol, "li"):
                a = None
                for child in li:
                    if _local(child.tag) == "a":
                        a = child
                        break
                if a is None:
                    continue
                title = "".join(a.itertext()).strip()
                href_raw = a.get("href", "")
                path = self._resolve(nav_dir, href_raw)
                anchor = href_raw.split("#", 1)[1] if "#" in href_raw else None
                full_href = path + (f"#{anchor}" if anchor else "")
                entry = TocEntry(title=title, href=full_href, level=level)
                sub_ol = None
                for child in li:
                    if _local(child.tag) == "ol":
                        sub_ol = child
                        break
                entry.children = walk(sub_ol, level + 1)
                entries.append(entry)
            return entries

        top_ol = None
        for child in toc_nav:
            if _local(child.tag) == "ol":
                top_ol = child
                break
        return walk(top_ol, 0)

    def _build_anchor_index(self):
        if self._anchor_index is not None:
            return

        mtime = None
        try:
            mtime = os.path.getmtime(self.path)
        except OSError:
            pass

        if self.anchor_cache_path and os.path.exists(self.anchor_cache_path):
            try:
                with open(self.anchor_cache_path) as f:
                    cached = json.load(f)
                if cached.get("mtime") == mtime:
                    self._anchor_index = {k: set(v) for k, v in cached["index"].items()}
                    return
            except Exception:
                pass  # corrupt/stale cache -- fall through and rebuild

        self._anchor_index = {}
        for name in self.zip.namelist():
            if name.lower().endswith((".xhtml", ".html", ".htm")):
                try:
                    root = self._parse_xml(self._read(name))
                except ET.ParseError:
                    continue
                ids = {e.get("id") for e in root.iter() if e.get("id")}
                self._anchor_index[name] = ids

        if self.anchor_cache_path:
            try:
                os.makedirs(os.path.dirname(self.anchor_cache_path), exist_ok=True)
                with open(self.anchor_cache_path, "w") as f:
                    json.dump({
                        "mtime": mtime,
                        "index": {k: list(v) for k, v in self._anchor_index.items()},
                    }, f)
            except Exception:
                pass  # caching is an optimization, not a correctness requirement

    def find_file_for_anchor(self, anchor: str, hint_file: str | None = None) -> str | None:
        self._build_anchor_index()
        if hint_file and anchor in self._anchor_index.get(hint_file, set()):
            return hint_file
        for fname, ids in self._anchor_index.items():
            if anchor in ids:
                return fname
        return None

    def resolve_href(self, href: str, current_file: str) -> tuple[str | None, str | None]:
        if href.startswith("http://") or href.startswith("https://"):
            return None, None

        if href.startswith("#"):
            anchor = href[1:]
            found = self.find_file_for_anchor(anchor, hint_file=current_file)
            return (found or current_file), anchor

        if "#" in href:
            file_part, anchor = href.split("#", 1)
        else:
            file_part, anchor = href, None

        base_dir = posixpath.dirname(current_file)
        target = posixpath.normpath(posixpath.join(base_dir, file_part))
        return target, anchor

    def get_page(self, file_path: str):
        raw = self._read(file_path)
        try:
            root = self._parse_xml(raw)
        except ET.ParseError as e:
            raise ValueError(f"could not parse {file_path}: {e}")

        body = _find_local(root, "body")
        if body is None:
            body = root

        text_parts = []
        links: list[LinkSpan] = []
        images: list[ImageSpan] = []
        styles: list[StyleSpan] = []
        para_spans: list[ParaSpan] = []
        anchor_offsets: dict[str, int] = {}
        cursor = [0]
        last_image_end = [None, 0]  # v0.1.93: [text_parts index, cursor pos]
                                     # right after the most recent image's
                                     # own trailing "\n" -- see the img
                                     # handler in walk() for why

        STYLE_TAGS = {"strong": "bold", "b": "bold", "em": "italic", "i": "italic"}
        # h2/ol added v0.1.42: h2 for be_E subheadings; ol so ordered-list
        # items get proper newlines (noMarker lists inside boxSupplement).
        BLOCK_TAGS = {"p", "div", "li", "h1", "h2", "h3", "h4", "aside", "br", "ol"}

        # JW paragraph-style classes (sm/sh/si/sb/sj) are intentionally
        # not mapped -- they caused italic, indent, small font and grey
        # colour that conflicted with plain readable body text rendering
        # (v0.1.47 removal). Bold still comes through naturally from
        # <strong> tags in the source HTML.

        # Collapses runs of whitespace -- including the "\r\n" + indentation
        # that XML pretty-printing leaves between tags like </tr> and <tr> --
        # down to a single space, matching normal HTML whitespace handling.
        # Without this, that incidental source formatting was being emitted
        # as literal hard line breaks, so a table like the Psalms chapter
        # grid (5 links per <tr>) rendered as one forced line per row no
        # matter how much screen width was actually available.
        _WS_RE = re.compile(r"[ \t\r\n]+")

        # v0.1.151: substitution table is now DYNAMIC, computed once by
        # main.py at startup via a real TTF_GlyphIsProvided32 check
        # against whichever font is actually bundled (see
        # set_active_glyph_subs() below and the call site in main.py,
        # right after FONT_PATH is resolved). This function no longer
        # hardcodes an assumption about which font is active -- it just
        # applies whatever _ACTIVE_GLYPH_SUBS currently holds, which may
        # be empty (e.g. DejaVu Sans, as of v0.1.151, has every one of
        # these natively, so nothing gets substituted and the real
        # glyphs render untouched).
        def _sub_missing_glyphs(s: str) -> str:
            for bad, good in _ACTIVE_GLYPH_SUBS.items():
                if bad in s:
                    s = s.replace(bad, good)
            return s

        def emit(s: str):
            if not s:
                return
            text_parts.append(s)
            cursor[0] += len(s)

        def emit_text(s: str):
            """For elem.text / child.tail specifically -- collapses internal
            whitespace runs to a single space before emitting. Explicit
            structural newlines (from maybe_newline()/BLOCK_TAGS/[IMG]) are
            added separately and are never passed through this.

            Also collapses ACROSS fragment boundaries, not just within a
            single fragment: without this, one element's trailing
            whitespace-only tail followed by the next element's leading
            whitespace each independently collapse to one space, but
            concatenated they form a double-space in the final text. That
            double-space later gets silently re-collapsed to a single
            space when main.py word-wraps the line (joining words with
            " ".join, which drops the empty string a double-space
            produces on split) -- permanently desyncing character offsets,
            and therefore link/image span positions, from that point
            forward in the paragraph. Confirmed via a real Bible chapter-
            grid page: this caused chapter-number links to lose their
            highlight (or highlight the wrong character) starting right
            after each <tr> row boundary, worsening with each subsequent
            row as the drift compounded."""
            if not s:
                return
            s = _sub_missing_glyphs(s)
            collapsed = _WS_RE.sub(" ", s)
            if collapsed.startswith(" ") and text_parts and text_parts[-1].endswith(" "):
                collapsed = collapsed[1:]
            emit(collapsed)

        def maybe_newline():
            if text_parts and not text_parts[-1].endswith("\n"):
                emit("\n")

        def walk(elem):
            tag = _local(elem.tag)

            node_id = elem.get("id")
            if node_id:
                anchor_offsets.setdefault(node_id, cursor[0])

            # v0.1.120 added a skip here for screen-reader-only text
            # (class="dc-screenReaderText", aria-hidden="true") after
            # finding "Your answer" fill-in-the-blank labels cluttering
            # meeting workbooks. v0.1.121: Kaleb decided he wants that
            # text visible at all times instead (not conditional on the
            # images toggle, just always shown) -- reverted. No render-
            # time filtering needed either since there's nothing to filter.

            if tag == "img":
                src = elem.get("src")
                if src:
                    alt = (elem.get("alt") or "").strip()
                    base_dir = posixpath.dirname(file_path)
                    resolved = posixpath.normpath(posixpath.join(base_dir, src))
                    # v0.1.93 fix: two images back-to-back (each commonly
                    # wrapped in its own <div><figure>, e.g. a thin chapter-
                    # header banner immediately followed by a full photo --
                    # Courage/Enjoy Life Forever) picked up a full BLANK
                    # LINE of gap from the block-tag-boundary/whitespace
                    # machinery below (maybe_newline() + emit_text()'s
                    # tail-whitespace collapsing) even though the source
                    # XHTML has nothing but incidental indentation between
                    # them -- no caption, no real text. That wasted 2 rows
                    # of page budget with zero visual content, which only
                    # became visible as the second image getting pushed to
                    # the next page once larger Font Sizes shrank the
                    # per-page row budget (Kaleb, 28pt/32pt on Courage).
                    # Matches JW Library's own rendering (Kaleb's reference
                    # screenshot) of no gap between back-to-back images.
                    # Deliberately narrow: only triggers when EVERYTHING
                    # since the immediately preceding image was pure
                    # whitespace (no real text/caption in between) -- any
                    # actual content between two images is left completely
                    # untouched, and this has zero effect on ordinary
                    # paragraph-to-paragraph spacing elsewhere.
                    if last_image_end[0] is not None:
                        since = "".join(text_parts[last_image_end[0]:])
                        if since.strip() == "":
                            del text_parts[last_image_end[0]:]
                            cursor[0] = last_image_end[1]
                    img_start = cursor[0]
                    emit("[IMG]")
                    images.append(ImageSpan(start=img_start, end=cursor[0], src=resolved, alt=alt))
                    emit("\n")
                    last_image_end[0] = len(text_parts)
                    last_image_end[1] = cursor[0]
                return

            # SVG <image> (v0.1.56): newer Project Gutenberg "ebookmaker"
            # covers wrap the cover picture as <svg><image xlink:href="..."/>
            # </svg> instead of a plain <img>, so the img-only check above
            # silently produced a blank page for the whole cover spine
            # entry. xlink:href is the correct SVG1.1 attribute name; some
            # tools drop the xlink: prefix per SVG2, so fall back to a bare
            # "href" too. Confirmed against a real Gutenberg epub (The
            # Adventures of Sherlock Holmes, gutenberg.org/1661) -- see
            # wrap0000.xhtml in that file for the exact markup.
            if tag == "image":
                href = elem.get("{http://www.w3.org/1999/xlink}href") or elem.get("href")
                if href:
                    base_dir = posixpath.dirname(file_path)
                    resolved = posixpath.normpath(posixpath.join(base_dir, href))
                    img_start = cursor[0]
                    emit("[IMG]")
                    images.append(ImageSpan(start=img_start, end=cursor[0], src=resolved, alt=""))
                    emit("\n")
                return

            if tag in ("script", "style"):
                return

            # <sup> inline superscript (v0.1.42): smaller font, COL_DIM in renderer.
            if tag == "sup":
                sup_start = cursor[0]
                if elem.text:
                    emit_text(elem.text)
                for child in elem:
                    walk(child)
                    if child.tail:
                        emit_text(child.tail)
                if cursor[0] > sup_start:
                    para_spans.append(ParaSpan(start=sup_start, end=cursor[0],
                                               kind="superscript"))
                return

            # <figcaption> caption text below an image (v0.1.42).
            if tag == "figcaption":
                maybe_newline()
                cap_start = cursor[0]
                if elem.text:
                    emit_text(elem.text)
                for child in elem:
                    walk(child)
                    if child.tail:
                        emit_text(child.tail)
                if cursor[0] > cap_start:
                    para_spans.append(ParaSpan(start=cap_start, end=cursor[0],
                                               kind="caption"))
                maybe_newline()
                return

            # <span class="pageNum"> print-page markers are silently skipped --
            # they're invisible in the digital reading context and injecting
            # them mid-sentence caused surrounding text to render in small/dim
            # font (v0.1.46 fix).
            elem_classes = set((elem.get("class") or "").split())
            if tag == "span" and "pageNum" in elem_classes:
                return

            # boxSupplement: emit rule lines around the box (v0.1.42).
            # The box title (boxTtl) gets bold via StyleSpan naturally since
            # it's usually wrapped in <strong>. We add blank-line + rule
            # before and after the entire div.
            is_box = tag == "div" and "boxSupplement" in elem_classes
            if is_box:
                maybe_newline()
                rule_start = cursor[0]
                emit("─" * 32)
                para_spans.append(ParaSpan(start=rule_start, end=cursor[0],
                                           kind="box_rule"))
                emit("\n")

            if tag in BLOCK_TAGS:
                maybe_newline()



            # h2 bold: emit StyleSpan for the whole h2 content (v0.1.42).
            is_h2 = (tag == "h2")
            h2_start = cursor[0] if is_h2 else None

            # A <tr> that reads like a list of distinct records -- one
            # chapter title per row, whether that's ONE cell (a Project
            # Gutenberg TOC: <tr><td><a>Chapter title</a></td></tr>) or TWO
            # (another common Gutenberg TOC pattern: a chapter-number link
            # cell plus a separate title cell) -- should get its own line,
            # same as any other block element. A <tr> that's really a
            # compact GRID of short items (the JW Bible's book-navigation
            # table: 5 short book-abbreviation links per row, meant to flow
            # and wrap together, not one-per-line -- see the whitespace-
            # collapse comment above BLOCK_TAGS for why that exact case was
            # deliberately fixed to flow naturally) must NOT be forced onto
            # separate lines. Cell COUNT alone isn't a reliable enough
            # signal (both known Gutenberg TOC patterns and the JW grid can
            # all have "a few" cells) -- average TEXT LENGTH per cell is:
            # short abbreviations average ~4 chars/cell in the JW grid,
            # versus ~18-35 chars/cell for real chapter titles. Threshold
            # picked from those real, measured numbers, not a guess.
            is_row_of_records = False
            if tag == "tr":
                cells = [ch for ch in elem if _local(ch.tag) in ("td", "th")]
                if cells:
                    total_len = sum(len("".join(ch.itertext())) for ch in cells)
                    avg_len = total_len / len(cells)
                    is_row_of_records = avg_len > 10
                if is_row_of_records:
                    maybe_newline()

            is_link = tag == "a" and elem.get("href")
            link_start = cursor[0] if is_link else None

            # <strong>/<b> -> bold, <em>/<i> -> italic (v0.1.35). Nested/
            # overlapping combinations (e.g. <strong><em>...) naturally
            # produce two separate StyleSpans covering overlapping ranges
            # -- one bold, one italic -- rather than trying to merge them
            # here; see StyleSpan's docstring for why that's deliberate.
            style_kind = STYLE_TAGS.get(tag)
            style_start = cursor[0] if style_kind else None

            if elem.text:
                emit_text(elem.text)

            for child in elem:
                walk(child)
                if child.tail:
                    emit_text(child.tail)

            if style_kind and cursor[0] > style_start:
                styles.append(StyleSpan(
                    start=style_start, end=cursor[0],
                    bold=(style_kind == "bold"), italic=(style_kind == "italic"),
                ))

            # h2 bold: wrap entire h2 text in a bold StyleSpan (v0.1.42).
            if is_h2 and cursor[0] > h2_start:
                styles.append(StyleSpan(start=h2_start, end=cursor[0],
                                        bold=True, italic=False))

            if is_link:
                href = elem.get("href")
                target_file, target_anchor = self.resolve_href(href, file_path)
                epub_type = (elem.get("{http://www.idpf.org/2007/ops}type")
                             or elem.get("epub:type"))
                # v0.1.98: external http(s) links (e.g. a "Watch the video"
                # link to jw.org from inside a publication) used to
                # resolve_href() to (None, None) and get lumped in as
                # "internal" -- selectable/highlighted like any other link,
                # but follow_selected() only acts when target_file is set,
                # so pressing A on one silently did nothing. Give them their
                # own kind and keep the raw href so the reader can actually
                # do something with it.
                if href and (href.startswith("http://") or href.startswith("https://")):
                    kind = "external"
                else:
                    kind = "noteref" if epub_type == "noteref" else "internal"
                links.append(LinkSpan(
                    start=link_start, end=cursor[0],
                    target_file=target_file, target_anchor=target_anchor,
                    kind=kind, href=(href if kind == "external" else ""),
                ))

            if is_row_of_records:
                maybe_newline()

            if tag in BLOCK_TAGS:
                maybe_newline()

            # boxSupplement closing rule (v0.1.42).
            if is_box:
                rule_start = cursor[0]
                emit("─" * 32)
                para_spans.append(ParaSpan(start=rule_start, end=cursor[0],
                                           kind="box_rule"))
                emit("\n")

        node_id = body.get("id")
        if node_id:
            anchor_offsets.setdefault(node_id, cursor[0])
        if body.text:
            emit_text(body.text)
        for child in body:
            walk(child)
            if child.tail:
                emit_text(child.tail)

        text = "".join(text_parts)
        text, images, links, styles, para_spans, anchor_offsets = collapse_blank_line_runs(
            text, images, links, styles, para_spans, anchor_offsets)
        return text, links, images, anchor_offsets, styles, para_spans

    def get_image_bytes(self, image_path: str) -> bytes:
        return self.zip.read(image_path)

    def spine_index(self, file_path: str) -> int:
        try:
            return self.spine.index(file_path)
        except ValueError:
            return -1

    def next_in_spine(self, file_path: str) -> str | None:
        i = self.spine_index(file_path)
        if i == -1 or i + 1 >= len(self.spine):
            return None
        return self.spine[i + 1]

    def prev_in_spine(self, file_path: str) -> str | None:
        i = self.spine_index(file_path)
        if i <= 0:
            return None
        return self.spine[i - 1]


class ReaderState:
    def __init__(self, doc: EpubDocument, start_file: str):
        self.doc = doc
        self.current_file = start_file
        self.current_anchor: str | None = None
        # v0.1.39: exact character offset into the page's plain text,
        # used instead of current_anchor when restoring a bookmark or
        # resume-reading position. current_anchor only ever holds a value
        # briefly (cleared to None once a page finishes loading -- see
        # App._ensure_page_built()), so a bookmark saved after scrolling
        # past that point had nothing to restore to and always reopened
        # at the top of the chapter. char_off is captured fresh every
        # time (see App._current_char_offset()), so it survives exactly
        # where the user actually was, mid-paragraph included.
        self.current_char_off: int | None = None
        self.back_stack: list[tuple[str, str | None]] = []

    def goto(self, file_path: str, anchor: str | None = None, push_history=True,
             char_off: int | None = None):
        if push_history:
            self.back_stack.append((self.current_file, self.current_anchor))
        self.current_file = file_path
        self.current_anchor = anchor
        self.current_char_off = char_off

    def follow_link(self, link: LinkSpan):
        if link.target_file:
            self.goto(link.target_file, link.target_anchor)

    def go_back(self) -> bool:
        if not self.back_stack:
            return False
        self.current_file, self.current_anchor = self.back_stack.pop()
        return True
