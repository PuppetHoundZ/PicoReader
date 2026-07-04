#!/usr/bin/env python3
"""
PicoReader for muOS (Anbernic RG CubeXX-H, 720x720)

*** THIS IS THE PERSONAL BUILD -- INCLUDES jw_fetch.py ***
jw_fetch.py is a PRIVATE downloader plugin (JW.org publications) and
must NEVER be published to the public GitHub repo. This build is for
Kaleb's own device only. For the public/GitHub-safe build (identical
otherwise, jw_fetch.py simply not included), see the separate release
build's main.py header.

Companion app to Pico8FavsSorter -- same conventions: raw ctypes SDL2,
no external deps, hint bar, controller-first navigation.

Screens:
  LIBRARY  - lists .epub files found in the library folder, titles pulled
             from each book's OPF metadata
  READER   - main reading view: scrolling text, inline image placeholders,
             link selection via D-pad, page turn via L/R triggers
  MENU     - opened with X or Y: Chapters (TOC) / Bookmarks / Library / Font Size

Controls:
  D-PAD UP/DOWN     scroll / move link selection
  D-PAD LEFT/RIGHT  cycle link selection left/right on same line
  A                 follow selected link / confirm menu selection
  B                 go back (link history) / close menu / back to library;
                    (Library) quit the app -- moved here from SELECT in
                    v0.1.29, see SELECT below for why
  L / R             previous / next page  (Chapters/Bookmarks lists: jump -10/+10)
  L2 / R2           previous / next chapter (reader); previous / next
                    book/article (Chapters screen); (Library, if a
                    downloader plugin is present) open the downloader
  Y                 (Reader) toggle fast-scroll: D-pad moves x10 while on
                    (Chapters/Bookmarks lists) jump +10
                    (Library) cycle sort mode: Title A-Z / Author A-Z /
                    Last Read / Recently Added
  X                 open menu (reader); delete bookmark, press twice to
                    confirm (Bookmarks screen); pin/unpin (Library)
  START             (Reader) set a bookmark at current position
                    (Library) open the Library menu -- sort shortcuts,
                    Download Books, Storage (v0.1.29)
  SELECT            (Library) delete book, press twice to confirm --
                    moved here from B in v0.1.29: B sits right next to
                    the D-pad and means "go back" everywhere else in the
                    app, so it was too easy to hit by muscle memory and
                    delete a book even with the two-press confirm.
                    B now quits from Library instead (was SELECT's job
                    since v0.1.27).

Menu also includes a Storage screen (cache size, per-book cache size,
orphaned-bookmark cleanup, manual "Clear Image Cache", whole-book
background "Pre-render Book Images", and a live RAM-only toggle that
disables the on-disk image cache entirely) -- reachable from the Reader
menu OR from the new Library menu (START); Storage's own Back/B always
returns to whichever one opened it.

List screens (Menu, Library, Library Menu, Chapters, Bookmarks, Storage)
wrap around top-to-bottom/bottom-to-top on UP/DOWN. Chapters opens
scrolled to your current reading position, not always the top of the list.

===========================================================================
AI NOTES -- read this first if you're a future Claude session picking this
project back up. Kept deliberately short; the versioned changelog below
has full detail on any specific fix.

CURRENT STATE (v0.1.75): Rounded-corner polish from Kaleb's on-device
testing: row bottom padding increased (_row_h() default pad 16->20,
Chapters 10->14) since the gap between a glyph's descender and a
selection highlight's bottom edge was a tight 4px at every Font Size
before, now 8px. The hint bar's top-left/top-right corners are also
"rounded" (_round_top_corners_to_bg(), draw_hint()) by painting a
COL_BG quarter-circle over each -- makes the reading area above it
read as having a curved bottom edge. Bottom corners untouched (flush
with the screen's physical edge, rounding wouldn't show).
Library empty-state message ("No .epub files found in <LIBRARY_DIR>")
no longer overflows at large Font Size -- _wrap_path_message() wraps a
filesystem path (no spaces to word-wrap on) by also splitting on '/',
with a character-level fallback if a segment is somehow still too
wide alone.
Selector highlights and popup windows have slightly rounded corners
(fill_rect_rounded(), CORNER_RADIUS = 6px scaled, 3px for the
text-entry keyboard cells specifically, which had less natural
clearance). No SDL2_gfx is linked, so this is a cheap approximation: a
center cross of 3 plain rects + one 1px-tall SDL_RenderFillRect per
row per corner (quarter-circle mask via math.sqrt). Applied to every
list-row selection highlight, the Menu/Library Menu popup panels, the
text-entry keyboard cells and value box, and the image-loading
placeholder box. NOT applied to the full-width hint/status bars
(edge-to-edge, only 2 of 4 corners would show).
Text color is fully theme-driven system-wide (every render_text() call
and full-screen background fill across all 12 screens resolves to
COL_TEXT/COL_ACCENT/COL_DIM/COL_WARNING/COL_BG) -- confirmed via audit,
no hardcoded colors anywhere.
Color Themes -- "Theme +"/"Theme -" (Reader menu or Library menu)
cycle THEMES (Default / Dim Warm / Deep Amber / Red Shift / Adventure),
saved as settings.json "theme_index". apply_theme(index) is the ONLY
place a theme touches: it rebinds the module-level COL_* globals that
every draw_* function already reads by name, so adding a future theme
is just one new dict in THEMES -- no per-screen draw code changes
needed. Dim Warm/Deep Amber/Red Shift are bedtime-reading palettes
(progressively less blue, more amber/red) based on blue-light/
melatonin-suppression research; Default uses a muted teal accent
(95,168,156) and Deep Teal link (61,125,118); Adventure is the
BMO-inspired palette (link=Deeper Mint, accent=Pale Mint, selected
link=Button Yellow, warning=Button Red/Pink, dark bg kept per Kaleb's
request, text=Muted Mint-Grey (180,200,190) -- picked after reviewing
4 swatch options, softer than the original near-white).
Global Font Size setting scales ALL UI text (reading + hint bar +
menus + Library/Chapters/Storage), with dynamic row heights/wrapping
so nothing overflows at max size -- see v0.1.50-57 below if anything
still clips/overlaps at large Font Size, that's the most likely place
to look first.
JW.org plugin: category picker (Bibles/Books & Brochures/Tracts/
Watchtower/Awake!/Meeting Workbooks), search scoped per-category, and
manual pub-code entry -- all pub codes in jw_fetch.py are individually
verified live against the real API, not guessed (see v0.1.58-61).
Gutenberg plugin: handles both plain <img> covers and newer SVG-wrapped
covers (<svg><image xlink:href>), Loading/Checking screens show a
spinner + elapsed seconds, and any spine page that renders fully blank
(no text, no images) is logged to data/render_issues.log and shown as
a visible on-screen note rather than silently looking broken (v0.1.62-63).
This header was itself found stale during the v0.1.64 audit (stuck at
v0.1.55 while the changelog below had already reached v0.1.61) -- if
this ever happens again, trust the highest version number IN the
changelog over this line, and fix this line to match.

Architecture, three files:
  main.py         SDL2/ctypes UI, App class (all mutable reader state),
                   ImageLoader (background decode, priority queue),
                   ReaderState (current file/anchor/history)
  epub_engine.py  EpubDocument: manifest/spine/TOC (NCX+nav) parsing,
                   get_page() (HTML->wrapped text+links+images+anchors),
                   pure stdlib only
  mini_jpeg.py    from-scratch JPEG decoder (no PIL/Pillow available)

Recurring bug shape to watch for: UNIT MISMATCHES between "_lines[] index"
(li) and "visual screen rows" (row). An image is ONE _lines[] entry but
costs IMG_BOX_ROWS (14) visual rows to draw. Any code that scrolls/pages
MUST walk li and row as separate counters (see App._rows_for_li(),
draw_reader(), visible_span_indices() for the canonical pattern) --
mixing them (e.g. `scroll += body_rows` where scroll is li-indexed) is
exactly what caused the v0.1.23 image-skip/cutoff bug. If a report sounds
like "images skip/cut off/reappear when paging," check this first.

Chapter/day navigation (L2/R2, and the "Chapters" TOC screen) are TWO
SEPARATE systems, easy to conflate when debugging:
  - Chapters screen = doc.toc, straight from the EPUB's NCX/nav (coarse --
    e.g. one "January" entry for a whole month in a daily-text book).
  - L2/R2 = App._chapter_nav_points, a heuristic (chapterN anchors, else
    TOC, else weekday-prefix detection for daily-text books, else raw
    spine) built once per book open. _jump_chapter()'s bisect math must
    handle sitting BEFORE the first nav point (front matter) correctly --
    see the v0.1.22 fix for the exact off-by-one this produces if wrong.

Image cache keys are ALWAYS "{book_id}__{internal epub path}" (see
App._img_key), book_id = sha1(book_path)[:16], flat directory
(IMG_CACHE_DIR), no per-book subfolders. Per-book size/delete is a
filename-prefix match (book_cache_size_bytes/delete_book_cache) -- do
NOT introduce a second scoping scheme.

Font: bundled assets/font.ttf is Liberation Sans (proportional), checked
FIRST in FONT_PATHS. This was deliberate and confirmed by device
evidence (DejaVu is not actually present on this hardware) -- don't
"fix" it back to DejaVu without new evidence.

Decode-target box (ImageLoader.TARGET_BOX_W/H, currently 480x272) only
affects which scale_n mini_jpeg decodes at -- NOT the on-screen display
size (that's SW-40 wide x IMG_BOX_ROWS tall, computed in draw_reader()).
Shrinking it trades sharpness for decode speed; don't confuse the two.

get_page() returns SIX values (v0.1.42, was five): text, links, images,
anchor_offsets, styles, para_spans. Every call site must unpack all 6
or it throws on every page load. Para_spans are ParaSpan dataclasses
(epub_engine.py) -- active kinds: superscript, caption, box_rule only.
pagenum removed v0.1.46 (JW print-page markers silently skipped).
JW paragraph classes sm/sh/si/sb/sj removed v0.1.47 (caused italic,
indent, small font, grey on Bible text). draw_reader() resolves active
ParaSpan per line via _line_abs_offsets[] (precomputed once in
_ensure_page_built, v0.1.46). Only box_rule gets special rendering;
all other kinds render as plain body text, uniform size and colour.
_page_text_cache (v0.1.48, raised to 200 in v0.1.68): RAM-only LRU,
eliminates XML parse lag on distant chapter/scripture jumps, not just
adjacent ones. _wrapped_cache (v0.1.69), separate cache keyed by (href,
font_size_index), skips the SDL_ttf word-wrap pass on revisits to a page
already built at the current size -- see v0.1.69 changelog for measured
before/after on a real large chapter. Both cleared on open_book().

Bold/italic (v0.1.35): StyleSpans from walk() -> _compute_line_style_runs()
-> _line_segments() -> per-segment render with body_styled(bold, italic).
Font files: assets/font-bold.ttf, font-italic.ttf, font-bolditalic.ttf
(Liberation Sans 2.1.5, SIL OFL -- third-party open-source fonts).
Dummy SDL video driver can't create textures (known sandbox limitation);
verify logic-level + zero-exception real-SDL walks rather than visual.

epub_engine.py's walk() treats <tr> specially (v0.1.34): a row is forced
onto its own line ONLY if its cells' average text length exceeds ~10
chars (real chapter titles) -- short compact grids like the JW Bible's
book-navigation table (5-char book abbreviations) are deliberately left
to flow/wrap naturally instead, matching how they render everywhere
else. This was chosen (over simpler options like cell count) specifically
because two REAL Gutenberg books use two different table shapes for
their TOC (one cell per row vs. two), and cell count alone couldn't
distinguish either from the JW grid. If a future table renders wrong,
check average-cell-length against this threshold before assuming the
threshold itself needs adjusting -- get real numbers from the actual
book first, the way this fix was derived, rather than guessing a new one.

Every fix ships with an AST-parse check and, wherever feasible, a
standalone simulation (a types.SimpleNamespace/plain-function harness
reproducing the exact bug scenario) run BEFORE delivery, not just after.
Crash log for boot/runtime failures: /tmp/picoreader_crash.log.

===========================================================================
PROJECT-LEVEL NOTES (added for future reference/troubleshooting)
===========================================================================
TARGET HARDWARE: Anbernic RG CubeXX-H, 720x720 display, running MustardOS
(muOS) Funky Jacaranda. The device has 1GB of RAM total. This is a hard
constraint on everything: avoid unbounded caches (see the 24-entry GPU
texture cache / disk-cached decoded images pattern already in use), avoid
loading whole large assets into memory when a streaming/chunked approach
is possible, and be skeptical of any change that meaningfully grows
steady-state memory use. When in doubt, ask before adding a cache,
buffer, or preload step that isn't obviously small and bounded.

OPEN SOURCE ATTRIBUTION -- ALWAYS FLAG IT: Any time a change ships,
touches, or references code/assets that did not originate in this
project, say so explicitly and plainly, e.g.: "This uses Liberation
Sans, SIL Open Font License, third-party -- not code we wrote." Applies
to the bundled fonts (Liberation Sans family, SIL OFL), MustardOS/muOS
source referenced for launcher/controller behavior, and any future
library or snippet pulled in from elsewhere. Never let an open-source
dependency pass by silently as if it were original work.

MUSTARDOS SOURCE ACCESS: The MustardOS GitHub org (github.com/MustardOS)
and its "internal" repo (board configs, sdl_map, func.sh, etc.) ARE
reachable via web_fetch/the GitHub Contents API from this environment --
try that first. Only ask the user to open a GitHub page and paste its
contents back if a direct fetch genuinely fails (blocked path, private
repo, rate limit, etc.) -- don't ask preemptively when a fetch would work.

DELIVERY FORMAT -- ALWAYS BOTH: Every delivery that changes app files
must include (1) the individual changed file(s) and (2) a full .muxapp
zip bundle containing everything needed to run (main.py + epub_engine.py
+ mini_jpeg.py + assets/ + mux_launch.sh, etc.), so the person can test
on-device quickly AND push individual file diffs to GitHub. Never ship
only one of the two.

NEVER ASSUME -- ALWAYS ASK: Standing instruction from the project owner.
Get clarification before making changes whenever the request, root cause,
or intended behavior is not fully clear from evidence already gathered
(crash logs, screenshots, real code, or explicit confirmation). Don't
present theories as confirmed fixes. Don't start editing code on an
ambiguous request -- ask first, then act once confirmed.

v0.1.75 -- Adventure theme's reading text color changed to Muted
  Mint-Grey (180,200,190), Kaleb's pick from the 4-swatch review in
  v0.1.74 -- softer than the original near-white (220,228,222), which
  read too bright on-device.

v0.1.74 -- Two fixes reported by Kaleb testing the rounded-corner work
  (v0.1.70/71) on-device: (1) _row_h()'s default pad bumped 16->20
  (Chapters' custom pad 10->14) -- measured a consistent 4px gap
  between a glyph's descender and the selection highlight's bottom
  edge at every Font Size; read as cramped once that edge became a
  visible curve. Now 8px. (2) Added _round_top_corners_to_bg(), called
  from draw_hint(), which paints a COL_BG quarter-circle over the hint
  bar's top-left/top-right corners -- makes the reading area above the
  hint bar read as having a curved bottom edge (Kaleb's request).
  Bottom corners left alone since they're flush with the screen's own
  edge. Verified with a full regression pass: all 7 Font Size steps x
  all 5 themes x every screen, no crashes.
  Adventure theme's reading text color (220,228,222) flagged by Kaleb
  as too bright/white on-device -- showed 4 softer teal options
  (soft sage teal, muted mint-grey, deeper soft teal, kept current as
  baseline), awaiting his pick before changing THEMES.

v0.1.73 -- Bug fix: Library's empty-state message ("No .epub files
  found in <LIBRARY_DIR>") could run off the right edge of the screen
  at large Font Size, reported by Kaleb. Root cause: it was a single
  un-wrapped render_text() call, and unlike other Library rows it
  didn't even use _fit_text() truncation. Added _wrap_path_message()
  since the existing hint-bar word-wrap can't help with an unbroken
  filesystem path (no spaces) -- new helper also splits on '/' and
  falls back to character-level breaking as a last resort. Also moved
  the message's y-position from a hardcoded _sy(100) to the same
  dynamic `top` value the book list already uses, so it can't overlap
  the heading/sort line at large Font Size either. Verified against
  the real on-device path and a pathological single-token path at all
  7 Font Size steps, plus a regression check that a normal
  library-with-books draw is unaffected.

v0.1.72 -- Feature: 5th theme "Adventure", requested by Kaleb (BMO/
  Adventure Time inspired, background kept dark/black per his explicit
  ask). Colors he picked from a swatch review: link = Deeper Mint
  (68,176,151), accent = Pale Mint (175,245,191), selected link =
  Button Yellow (255,236,71), warning = Button Red/Pink (242,5,83).
  Remaining fields (bg/panel/text/dim/hint_bg/hint_text/menu_sel_bg)
  filled in to match -- dark neutral background (14,14,16), off-white
  text with a faint mint tint (220,228,222) for readability. No
  official BMO/Adventure Time brand color palette exists (Cartoon
  Network/WBD haven't published one), so these hex values are based on
  fan-made palette references (Lospec "Beemo", ColorsWall "bmo
  design") -- close approximations, not exact. Just a 5th dict added
  to THEMES; apply_theme()/menu wiring needed no changes.

v0.1.71 -- Kaleb asked for verification that the new rounded corners
  don't overlap or clip any text. Audited clearance (rect-edge to
  text-position distance) at every fill_rect_rounded() call site
  against the 6px CORNER_RADIUS: found the text-entry keyboard cells
  had only ~5px clearance, tighter than the radius -- fixed by using
  radius=3 for that specific call site. Everything else already had
  10-20px clearance. Re-ran the headless smoke test across all 4
  themes x all 7 font-size steps x all 11 screens to confirm.

v0.1.70 -- Feature: slightly rounded corners on selector highlights
  and popup windows, requested by Kaleb. Added fill_rect_rounded()
  (center cross + per-row quarter-circle corner mask, no SDL2_gfx
  needed) and CORNER_RADIUS = 6px scaled. Swapped in at every list-row
  selection highlight, the Menu/Library Menu popup panels, the
  text-entry keyboard cells, the text-entry value box, and the
  image-loading placeholder box. Left the full-width hint/status bars
  square since they run edge-to-edge (only 2 of 4 corners would show).
  Verified with a headless smoke test across all 4 themes and all 12
  screens (no crashes) plus an ASCII render of the corner math to
  confirm a smooth quarter-circle taper rather than a jagged
  staircase at radius 6-8px.

v0.1.69 -- Theme +/- added to LIBRARY_MENU_ITEMS (the START popup menu
  on the Library screen), so themes can be changed without opening a
  book first. Same handler logic as the Reader menu's Theme +/-
  (apply_theme/save_settings), just added to a second screen's button
  handler. Also audited every draw_* function's selection-highlight
  color per Kaleb's question -- confirmed COL_MENU_SEL_BG is already
  one shared global applied identically on every list screen in the
  app (Library, Reader Menu, Chapters, Bookmarks, Storage, Library
  Menu, Download screens); no code change was needed for that part.

v0.1.66/68 -- Added Color Themes (THEMES list + apply_theme(index),
  see CURRENT STATE above for how it works) with 4 palettes: Default,
  Dim Warm, Deep Amber, Red Shift -- the latter three are bedtime
  palettes based on blue-light/melatonin-suppression research. Reader
  menu gained "Theme +"/"Theme -", saved to settings.json as
  "theme_index". Default theme's link color changed to Deep Teal
  (61,125,118) and accent to a soft muted teal (95,168,156) -- both
  picked by Kaleb after reviewing swatch comparisons, replacing the
  original green/blue.

v0.1.64 -- Full-project audit per Kaleb's request (all .py/.sh files, not
  just recent changes): ran pyflakes across every Python file (only
  pre-existing, harmless dead-variable warnings, e.g. para_extra unused
  since v0.1.47 removed per-kind styling -- nothing acted on), bash -n
  on mux_launch.sh, and a full regression of get_page() against all 20
  real epub files collected across this session (5 Kaleb-provided +
  15 freshly downloaded from gutenberg.org, spanning English/French/
  German/Spanish and one Arabic title) -- zero blank/error pages.
  Found and fixed ONE real bug, not in the app itself but in this
  changelog: v0.1.62/63 below were originally written as v0.1.56/57,
  colliding with real entries already at those numbers (v0.1.57-61,
  JW categories/magazine-scan/pub-code work) because the CURRENT STATE
  header above was itself stale at "v0.1.55" despite the changelog
  already reaching v0.1.61 underneath it -- i.e. the header hadn't been
  updated across some earlier session(s). Renumbered to the true next
  version and fixed the header. Lesson for future sessions: check the
  highest version number IN THE CHANGELOG, not just the CURRENT STATE
  line, before assigning a new version number.

v0.1.63 -- Per Kaleb's request: added both a persistent log AND a visible
  on-screen note for the "page rendered completely blank" failure mode
  (the class of bug v0.1.62's Gutenberg svg-cover fix addressed one
  instance of). New RENDER_LOG_PATH ("data/render_issues.log", inside
  the app folder so it survives reboots and can be pulled off the SD
  card -- unlike CRASH_LOG in /tmp, which is wiped on reboot). Logged
  once per fresh page parse (not on RAM-cache hits) when a spine page
  produces zero text AND zero images; the reading screen also swaps in
  "(This page appears empty -- it may use formatting PicoReader doesn't
  support yet.)" instead of a silent blank screen. Logging is
  best-effort/swallow-all-errors, matching _boot_log()'s pattern -- a
  logging failure must never interrupt reading.
  Note: a small number of real epubs may have an intentionally blank
  page by design (rare) -- this would show the note as a false
  positive in that case. Acceptable trade-off per Kaleb's request for
  visibility; can be revisited if it turns out to be noisy in practice.

v0.1.62 -- Two fixes reported by Kaleb after testing real Gutenberg epubs:
  (1) Cover pages skipped/blank on some Gutenberg books (confirmed on
  "The Adventures of Sherlock Holmes", gutenberg.org/1661). Root cause:
  newer Gutenberg "ebookmaker" output wraps the cover as
  <svg><image xlink:href="cover.jpg"/></svg> instead of a plain <img>,
  and epub_engine.py's walk() only had an <img> branch -- the whole
  cover spine page rendered as empty text. Added an <image> branch
  (checks xlink:href, falls back to bare href for SVG2-style markup
  some tools produce) that emits it as a normal [IMG] span, same as
  <img>. Verified against the real cover markup in that epub's
  wrap0000.xhtml before writing the fix, not guessed.
  (2) Download-browse "Loading..." was static text -- indistinguishable
  from a frozen screen on a slow connection, which read as "stuck until
  I press the D-pad" even though the v0.1.32 dirty-flag fix (see that
  entry) was confirmed still working correctly on both the plain-browse
  and Y-button-search paths. Changed to a spinner + elapsed seconds
  ("Loading |  (3s)") so a slow real network call is visibly still
  alive instead of looking hung. Same pattern applied to the JW manual
  pub-code "Checking..." status (same static-text problem, same fix).
  Regression-tested the cover fix against all 5 real Gutenberg epubs
  Kaleb provided (Study in Scarlet, Adventures/Return/Case-Book of
  Sherlock Holmes, Illustrated Adventures) -- all 5 use the same
  svg-wrapped cover pattern and all 5 now produce a real [IMG] span.
  Also re-checked a normal body chapter page from the same file to
  confirm the new <image> branch didn't affect ordinary <img> parsing.

v0.1.61 -- Verified a batch of historical/edge-case pub codes live against
  the real GETPUBMEDIALINKS API (Kaleb's request, not just guessed):
  w/mwb confirmed to work for issue=YYYYMM back to January 2016, and
  confirmed to 404 for 2015 and earlier -- EPUB doesn't appear to exist
  before 2016 for either. g/wp issue dates can't be reliably guessed
  (irregular real publish months); use manual code entry with a known
  issue instead. Walked back "mwbr" from v0.1.60 -- tried 8+ plausible
  issue codes live and none resolved, so it's commented out until
  actually confirmed rather than left looking verified when it wasn't.

v0.1.60 -- Scanned jw.org's Magazines and Meeting Workbooks library pages
  per Kaleb's request. Finding: both pages only surface recent issues
  (Study Watchtower to Jan 2026, Workbook to May 2025, public
  Watchtower/Awake! to ~2022) -- not a deep historical archive. A true
  historical scan (the year filter goes back to 1981) would need
  fetching each year separately; deferred pending Kaleb's confirmation
  it's still worth doing, since any past issue is already reachable via
  the existing manual pub-code entry (Y Enter Code, e.g. "w 202001").
  Did find one genuinely new, useful pub code: "mwbr" (References for
  Life and Ministry Meeting Workbook, a companion to mwb) -- added to
  the Meeting Workbooks category.

v0.1.59 -- Fixed reading-percentage indicator overlapping the last line
  of body text (confirmed via Kaleb's photo: "loyal," and "26%" drawn on
  top of each other). Root cause: the percentage label was positioned at
  a fixed offset above the hint bar, with no relationship to body_rows
  -- whenever body_h didn't divide evenly by the current line_h (which
  varies with Font Size), the leftover remainder could be smaller than
  the label, so the last text row and the percentage shared the same
  vertical space. Fixed by reserving dedicated footer_h space BELOW the
  text area up front (subtracted from body_h before body_rows is
  computed), so text can never lay out into where the percentage is
  drawn. Verified by simulation across 15 font-size/hint-height
  combinations: the old logic overlapped in 12 of them, the new one in
  none.

v0.1.58 -- Feature: JW.org plugin now has categories (Kaleb's request):
  Bibles, Books & Brochures, Tracts, Watchtower (Public & Study), Awake!,
  Meeting Workbooks. Selecting the plugin now opens a category picker
  first; selecting a category opens the browse list scoped to just that
  category, with search (Y) still available and scoped to the same
  category. New generic plugin capability (SUPPORTS_CATEGORIES +
  CATEGORIES list + list_items(category=...)) -- gutenberg_fetch.py is
  unaffected, it simply doesn't declare it. Along the way: added the
  "wp" (public Watchtower) and "g" (Awake!) periodical codes, which
  weren't in the catalog before at all -- both confirmed live on
  jw.org's own magazines page. Verified end-to-end with the real
  jw_fetch.py code (not simulated): all 6 categories return the
  expected items, and search-within-category filters correctly.

v0.1.57 -- More font-scaling overflow fixes at max Font Size, found by
  Kaleb: (1) Library header ("LIBRARY"/"Sort:"/first row) used fixed Y
  offsets, causing the sort label to overlap the first row's selection
  highlight. (2) Download-from selector and Gutenberg/JW download
  browse lists used fixed row heights/gaps, causing title/author lines
  to overlap. (3) Text-entry keyboard (search, pub-code entry) used a
  fixed cell height (SPACE/DEL/OK/CANCEL spilled outside their boxes)
  and didn't wrap the heading/hint text (got clipped instead). All now
  scale/wrap with font size, same pattern as v0.1.50-56.
  jw_fetch.py: added be/cf/jd/ia/jr/bt/mbs/yb11-17/tracts (t-ftr, t-fam,
  t-god, t-pry, t-jss, t-kng, t-sfr, t-dth, t-rlg) per Kaleb's request,
  titles verified against wol.jw.org's official Abbreviations page and
  jw.org's Tracts library page (not guessed).

v0.1.55 -- Feature: L/R on the Library screen are now a Font Size -/+
  hotkey (Kaleb's request -- L/R were unmapped there). Same logic and
  status message as the existing "Font Size -/+" menu items, so it's
  reachable without opening the Library menu. Hint bar updated to
  advertise it.

v0.1.54 -- Two more font-scaling bugs at max Font Size, found by Kaleb:
  (1) Transient status-message bar (e.g. "Font size: 32pt (largest)")
      used a fixed-height panel sized for the old fixed-size UI font --
      at max size the text no longer fit and visually overlapped the
      hint bar directly below it. New _status_bar_h() scales it like
      _row_h() does. Fixed in draw_library, draw_reader,
      draw_download_browse (all 3 places this panel is drawn).
  (2) MENU popup, Library MENU popup, and the Storage action list drew
      every item unconditionally with no bounds check -- fine at the
      old fixed font size where everything always fit, but at max Font
      Size (taller rows) items ran past the bottom of the screen with
      no way to reach them (e.g. "Pre-render Book Images" and "Back"
      on Storage). All three now use the same windowed-scroll pattern
      Library/Chapters already used, centered on the selected item.

v0.1.53 -- Two more font-scaling overflow bugs, found by Kaleb at max
  Font Size after v0.1.52:
  (1) Storage screen info lines (cache size, disk cache state, etc.)
      used a fixed 22px line-height increment that didn't grow with
      ui_small -- at max size lines started overlapping. Now uses
      _row_h(fonts.ui_small) like the action rows below it.
  (2) Reader's fast-scroll "%  [FAST]" indicator used a fixed guessed
      x-offset from the right edge, sized for the old fixed-size UI
      font -- at max Font Size the wider label ran off-screen. Now
      right-aligned using the label's actual measured width.

v0.1.52 -- Fixed hint bar text overlap at large Font Size (confirmed via
  Kaleb's on-device screenshots: popup MENU's hint bar visibly overlapped
  with leftover reader hint text above it). Root cause: hint_height()
  cached whatever text last called draw_hint() in the same frame --
  draw_menu() draws draw_reader() first (long hint, wraps to 2 lines),
  THEN its own short hint (1 line). The menu's overlay panel was sized
  using the reader's stale 2-line height, but the final draw_hint() call
  only cleared/redrew a 1-line area, leaving part of the reader's old
  hint text uncleared underneath. Fix: hint_height(fonts) is now a pure
  function of font size only (always reserves the HINT_H_MAX_LINES
  worst case), so every screen's layout math and its own hint draw
  always agree, regardless of what any other screen drew first. All
  hint_height() call sites now take app.fonts.

v0.1.51 -- Cache size increases (confirmed by Kaleb, 32GB SD card):
  MAX_CACHE_BYTES: 200MB → 500MB (on-disk image cache cap)
  MAX_INMEMORY_IMAGES: 60 → 80 (decoded images held in RAM)
  Storage screen "cap" label updated to match.

v0.1.50 -- Two fixes:
  (1) Global text size: "Font Size +/-" now scales ALL UI text (hint bar,
      popup menus, Library, Chapters, Bookmarks, Storage, text entry),
      not just reading text -- previously these were pinned to a fixed
      18pt (UI_STEP) specifically to avoid overflow at large sizes. That
      protection is now handled at each draw site instead of by capping
      the font: hint bar wraps to up to 2 lines and grows vertically
      (hint_height()/draw_hint()); list rows use dynamic height
      (_row_h(), via TTF_FontHeight) instead of fixed pixel constants;
      popup menu/list text truncates with an ellipsis if it would run
      past its container (_fit_text()) instead of clipping/overflowing.
      Touches: FontManager.ui_body/ui_small/ui_heading, draw_hint,
      draw_menu, draw_library_menu, draw_storage, draw_library, draw_toc.
  (2) Bible chapter-navigation cursor bug: selecting a chapter (e.g.
      Genesis 1) from the in-book "CHAPTERS:" grid scrolled to roughly
      the right spot but left the highlighted link on an unrelated
      chapter number, confirmed via real on-device screenshots. Root
      cause: _ensure_page_built() always reset selected_span to 0
      (first span in document order) after ANY page rebuild, including
      same-file anchor jumps -- so for a huge single-page Bible nav file
      the cursor landed nowhere near the actual target, and the
      renderer's "snap to first visible span" fallback then grabbed
      whatever was nearest on screen instead. Fixed: selected_span is
      now set to the span at/after the anchor's/resume's char offset.
      Verified against the real bi12_E.epub structure (BIBLE_01.xhtml)
      -- link targets themselves were always correct; this was purely
      an app-side cursor bug, not a bad EPUB link.

Earlier versions (condensed -- see AI NOTES above for anything still
architecturally relevant):
v0.1.42  ParaSpan formatting support added (superscript/caption/box_rule/
         JW paragraph classes); JW classes later removed v0.1.47.
v0.1.41  Search hint added to Gutenberg text-entry screen.
v0.1.40  JW pub-code entry hint added; noted Awake! issue-number mapping
         quirk (jw_fetch.py).
v0.1.39  Bookmarks/resume-reading now save exact paragraph (char offset),
         not just chapter.
v0.1.38  Fixed progressive-JPEG band-skip desync on one real image;
         fixed L2/R2 chapter nav skipping all front matter on Bible books.
v0.1.37  Progressive JPEG decoding added (mini_jpeg.py v0.2.0).
v0.1.36  Fixed bold/italic word-wrap overflow (bold text ~11% wider than
         regular wasn't accounted for).

START is deliberately unbound outside the Reader screen (v0.1.27) --
reserved for the downloader plugin trigger, which ended up bound to
Library-screen L2 instead (v0.1.28) once actually built. START remains
free; don't repurpose it without checking with the person first.

DOWNLOADER PLUGINS (v0.1.28): gutenberg_fetch.py (public/GitHub-safe)
and jw_fetch.py (PRIVATE -- never publish this one) are optional,
self-contained modules main.py loads defensively at import time into
DOWNLOAD_PLUGINS (empty list if neither file is present -- the app must
work identically either way). Contract: PLUGIN_NAME, list_items(query,
page)->(items,has_next,err), download(item,dest_dir)->(ok,msg,path).
See gutenberg_fetch.py's docstring for the full contract, and each
file's own docstring for its specific API details/legal basis (both
were checked in-conversation against real ToS/policy pages, not
assumed). JW pub codes in jw_fetch.py were all verified LIVE against
GETPUBMEDIALINKS before being hardcoded -- b.jw-cdn.org and jw.org ARE
reachable from this sandbox (allowed network domains), gutendex.com is
NOT (verify gutenberg_fetch.py's parsing against a real response the
first time it runs on real hardware, if anything looks off).

HARD LESSON from building this feature, worth repeating: a str_replace
that inserted a new elif block accidentally deleted the following
"elif app.screen == SCREEN_READER:" line, silently merging all
Reader-screen input handling into the wrong block and breaking normal
reading completely -- and AST-parse alone did NOT catch it (still
syntactically valid Python). This sandbox has real SDL2 installed
(check: `ctypes.util.find_library` fails but the .so exists at
/usr/lib/x86_64-linux-gnu/libSDL2-2.0.so.0 and libsdl2-ttf-2.0-0 can be
apt-installed) -- meaning main.py, App, and every draw_*/handle_button
function can actually be imported and driven for real with
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy, no physical device needed.
After ANY edit that touches handle_button()'s screen dispatch chain (the
long if/elif app.screen==... ladder), re-verify by actually constructing
App(renderer) and calling handle_button() with real button strings,
checking app.screen/app.scroll/etc. after each press -- not just
AST-parsing. This is now the required verification bar for edits to
that function, not merely a nice-to-have.
===========================================================================

Version: 0.1.70

Changelog:
  v0.1.70 -- Two unrelated additions, both documented here for one clean
    build reference:
    (1) jw_fetch.py: added AWAKE_BACK_ISSUES, a hard-coded list of every
      real Awake! issue from 2016-2025 (28 issues), shown when browsing
      the Awake! category. Previously Awake! had no back-issue browse
      list at all -- only manual code entry (Y button) worked, unlike
      Watchtower/Workbook which already had full generated back-issue
      lists. Not a generator like w/mwb because Awake!'s frequency
      changed twice (6/yr Feb-Dec even months 2016-17, 3/yr Mar/Jul/Nov
      2018-21, 1/yr 2022+) -- a per-year count alone can't derive the
      right issue=YYYYMM codes, so each of the 28 entries was
      individually confirmed live against GETPUBMEDIALINKS (HTTP 200 +
      real EPUB file present) before being added, same bar as every
      other pub code in that file. Frequency history independently
      corroborated via Wikipedia's Awake! article, which matches the
      live results exactly. Titles sourced from jw.org's own magazine
      library pages. Wired into list_items() the same way w/mwb
      back-issues are: only shown when browsing that specific category,
      deduplicated against the RSS "(new)"/"(this month, guess)"
      entries. No main.py logic changed for this -- browse/download/UI
      code is pub-agnostic.
    (2) assets/ fonts (font.ttf, font-bold.ttf, font-italic.ttf,
      font-bolditalic.ttf): re-sourced and rebuilt to fix a provenance
      gap in FONT_LICENSE.txt, which previously cited "the
      fonts-liberation Debian/Ubuntu package" as the source -- less
      precise than it should be. Rebuilt directly from the official
      https://github.com/liberationfonts/liberation-fonts repo at tag
      2.1.5 (commit 4b0192046158094654e865245832c66d2104219e), using
      that project's own documented build process (fontforge -script
      scripts/fontexport.pe against the .sfd sources via `make`) --
      not a third-party mirror. Verified by inspecting each output
      file's embedded name-table version field: all four report
      "Version 2.1.5", matching FONT_LICENSE.txt's existing version
      claim exactly. FONT_LICENSE.txt's source note updated to reflect
      this. No glyph/rendering changes expected -- same official 2.1.5
      source as before, just a corrected and independently-verified
      provenance trail.
  v0.1.69 -- Two loading-speed fixes, both verified against real nwt_E.epub
    content (not just AST-parsed -- actually built with real SDL2_ttf,
    SDL_VIDEODRIVER=dummy, timed before/after):
    (1) NEW wrapped-lines cache (_wrapped_cache), separate from
        _page_text_cache. Investigated first whether "cache the parsed
        book structure" (spine/TOC/chapter-nav) was worth doing -- it
        wasn't: _build_anchor_index() (the expensive full-book scan,
        used by both anchor lookups and chapter-nav-point building) was
        ALREADY disk-cached via anchor_cache_path/mtime since earlier
        work, so there was no real second win there. The actual gap:
        _ensure_page_built() was re-running self._wrap() (SDL_ttf word-
        width measurement) on EVERY build, even on a full
        _page_text_cache hit. Measured on the largest real chapter in
        nwt_E.epub (OEBPS/1001061175.xhtml, 2880 lines): cold wrap
        1.94s, warm (cache hit) 0.0008s. Keyed by (href, font_size_index)
        -- confirmed correct via real test: changing font size produces
        a genuinely different line count (2880 -> 3288 lines) and a
        separate cache entry, not stale reuse. NOT populated from the
        background prefetch thread -- self._wrap() calls SDL_ttf
        (TTF_SizeUTF8), and this project's own rule is real-device
        verification before trusting anything novel; calling SDL_ttf off
        the main thread hasn't been verified safe on this hardware. So
        this is a same-thread memoization win (revisits, L2/R2 back-and
        -forth, returning to a recent scripture) rather than a
        preemptive background-wrap -- flagged as a possible v2 if Kaleb
        wants to verify background SDL_ttf calls on real hardware first.
        Capped at 200 entries, same bound as _page_text_cache, cleared
        on open_book().
    (2) Widened _prefetch_adjacent_chapters() from 1 chapter each
        direction to 2 (delta -2,-1,+1,+2). Kaleb reads ahead across more
        than just the immediate next chapter in a sitting; RAM impact is
        zero beyond the existing 200-entry _page_text_cache cap since
        candidates already skip anything already cached.
  v0.1.68 -- Raised _page_text_cache from 4 to 200 entries. Prompted by
    Kaleb's actual usage pattern: NWT scripture lookups during meetings
    jump non-sequentially across the Bible (e.g. Genesis to Matthew --
    confirmed by direct inspection of nwt_E.epub: 1189 real chapterN
    anchors, matching the standard 929 OT + 260 NT count, spread across
    2749 actual spine files once chapter-splitting is accounted for).
    A 4-entry cache is fine for straight sequential reading (L2/R2) but
    thrashes hard under "jump to book, jump to another book" access,
    forcing a fresh XML parse on every visit even to a recently-viewed
    passage.
    RAM cost: ~28KB/entry x 200 = ~5.6MB worst case (up from ~112KB at 4
    entries) -- trivial against 1GB total, and this is the only thing
    using that memory (doesn't compete with the separately-bounded image
    caches). CPU cost: none from the cache itself (dict insert is O(1)
    regardless of size); the only size-sensitive part is
    _page_text_cache_put()'s eviction list (.remove()/.pop(0), O(n)),
    which at n=200 is still sub-millisecond -- not worth the complexity
    of an OrderedDict swap at this size, left as plain list on purpose.
    200 was chosen over other sizes considered (300, 500) as adequate
    headroom (~10x a typical meeting's actual page-touch count) without
    committing RAM the real usage pattern doesn't need.
  v0.1.67 -- Crash-safe image disk cache, prompted by Kaleb asking
    whether switching chapters/closing the book mid-decode could
    corrupt cached images. Confirmed: chapter/page switching was
    already async and non-blocking (resets _page_cache_key only, never
    joins the image worker thread) -- that part was fine. The real gap
    was _load_or_decode()'s disk-cache write, which wrote straight to
    the final .rgb/.meta filenames. An interruption mid-write (app
    killed, power loss, SD card hiccup -- exactly what a fast chapter
    switch could trigger while a background image was still being
    cached) could leave a truncated .rgb paired with a .meta still
    claiming the original dimensions, producing a garbled texture (or
    worse, SDL reading past a too-short buffer) on next load.
    Fix, two parts:
    (1) Read-side validation: before trusting a cached entry, checks
        that the .rgb file size exactly matches w*h*3 from its .meta.
        Mismatch -> logs it, deletes both files, falls through to a
        fresh decode instead of handing back garbage pixel data.
    (2) Write-side atomicity: decode result is written to temp files,
        then os.rename()'d into place (atomic on the same filesystem on
        Linux). rgb is renamed into place before meta, so a reader can
        never see a meta file whose matching rgb isn't fully written.
        An interrupted write now just leaves the OLD cache entry (or
        nothing) instead of a corrupted one.
    Net effect: chapters can be switched or the book closed at any time
    without any risk of poisoning the on-disk image cache.
  v0.1.66 -- CPU throttle for background image decode, addressing Kaleb's
    report that page/chapter loads could stutter behind image work.
    Root cause: the single ImageLoader worker thread is correct in
    design (image decode is GIL-serialized Python work, so more threads
    would only add contention -- see v0.1.9 notes), but once a
    PRIORITY_PRERENDER image started decoding it could NOT be
    interrupted, so a page turn or chapter change (PRIORITY_VISIBLE)
    landing mid-decode had to wait for that background image to finish
    -- worse for large/progressive JPEGs.
    Fix: added _pending_counts, a per-priority counter of not-yet-started
    queued tasks (kept in sync under _lock in request()/_worker_loop()
    since PriorityQueue has no safe peek). Before starting a PRERENDER
    task, the worker now checks whether VISIBLE or PREFETCH work is
    already waiting; if so, it requeues the PRERENDER task behind it
    instead of starting it, avoiding the block. Also added
    PRERENDER_THROTTLE_SECONDS=0.03 -- a small sleep between PRERENDER
    decodes only (never applied to VISIBLE/PREFETCH), so a long
    whole-book pre-render run generates noticeably less sustained
    CPU/heat without slowing down real reading.
    NOTE: _results was previously flagged in old notes as "unbounded" --
    that was stale. MAX_INMEMORY_IMAGES=80 with LRU eviction in
    _evict_if_needed() has handled this since v0.1.48/v0.1.51; no change
    needed there.
  v0.1.65 -- Fixed prerender progress falsely looking like it "restarts
    from the beginning" after a crash (Kaleb reported). Root cause:
    prerender_progress()'s done-count only checked is_full_res(), which
    tests the in-memory ImageLoader._results dict -- empty on every fresh
    process. The on-disk image cache (IMG_CACHE_DIR) already survives
    crashes/reboots, and _walk_and_enqueue() was already correctly
    skipping the expensive raw-JPEG-decode for disk-cached images -- but
    the progress bar had no way to know that until each one was
    individually re-touched through the single-worker queue (a real,
    serialized disk read per image), which for "lots of images" was slow
    enough to be visually indistinguishable from a genuine full restart.
    Fix: done-count now also counts has_full_disk_cache(key) as done,
    without waiting for the worker to reload it into RAM (cheap --
    os.path.exists, no decode, no RAM cost). Verified directly: simulated
    a post-crash state (fresh ImageLoader, empty _results, real file
    already in the disk cache) and confirmed the old calc reported it
    "not done" while the new one correctly reports "done" instantly.
    Also fixed this file's own stale version headers while here --
    CURRENT STATE above and this line were still at v0.1.61/64 despite
    the changelog having already reached v0.1.64 underneath -- same class
    of mistake the v0.1.64 audit entry below already flagged once.

  v0.1.61 -- Hint bar clipping fully fixed (supersedes v0.1.60, which
    only papered over the symptom). ROOT CAUSE found via direct
    word-count testing: _wrap_hint_text's line-cap logic, on reaching the
    last allowed line, kept only the ONE word that had just overflowed
    and then broke out of the loop -- silently discarding every word
    after it. This is what produced the orphaned "X"/"Y" alone on a
    clipped line in Kaleb's on-device screenshots; it was never a
    rendering overflow. Fixed: the last allowed line now packs ALL
    remaining words (may exceed the bar's width and get renderer-clipped
    as a last resort, but never drops content).
    Also: the hint bar no longer always reserves a fixed worst-case
    height. hint_height()/draw_hint() now use _hint_lines_needed() --
    1-3 lines, calibrated per current global Font Size against the two
    longest hint strings in the app (_HINT_CALIBRATION_TEXTS) -- so the
    bar stays 1 line thick at 14-18pt and only grows to 2 at 21pt+
    (verified: nothing needs 3 once _hint_pt()'s font-shrink fallback is
    applied). _hint_pt() shrinks just the hint font (floor 11pt,
    independent of the rest of the UI) if a hint string is ever too long
    to fit in HINT_H_MAX_LINES=3 even at that scale.
    Verified end-to-end by measuring real SDL_ttf-rendered word counts
    and line widths at all 7 Font Size steps (14-32pt): 24/24 words drawn
    at every step, zero width overflow on any line.
  v0.1.49 -- Single-lock image status check (main.py only). Added
    ImageLoader.get_status_snapshot(key) -- returns result/is_full/
    is_upgrading/seconds in ONE lock acquisition, replacing the old
    pattern of calling get(), is_upgrading(), get_with_full_flag(),
    and seconds_loading() separately (each took its own lock).
    has_pending_image_updates() and get_image_texture() both switched
    to the single snapshot call -- was up to 3 lock acquisitions per
    image per frame while any image on the page was still decoding
    (has_pending_image_updates() polls every loop iteration by design).
    Verified behaviorally equivalent across all 8 possible entry states
    (None/empty/loading/upgrading/full-landed/error) before switching --
    identical results to the old separate calls. Check frequency is
    UNCHANGED (still every frame) so images cannot get stuck waiting for
    a button press; this only reduces redundant lock overhead per check,
    not how often the check runs. Root cause: person reported 3-8s lag
    resuming a book to an exact paragraph -- images on that page still
    decoding meant has_pending_image_updates()+draw_reader() were doing
    3 lock acquisitions per image per frame competing with real
    rendering work on the ARM device's more limited CPU.
  v0.1.48 -- Background chapter pre-parse (main.py only). Added
    _page_text_cache (RAM-only LRU dict, 4 entries, ~112KB) and
    _page_text_cache_put() LRU helper. _prefetch_adjacent_chapters()
    fires a daemon thread after every page build -- pre-parses the
    prev and next chapter nav-point files into cache so L2/R2 jumps
    find the XML already parsed. _ensure_page_built() checks cache
    before calling doc.get_page(), stores result on cold miss.
    Cache cleared on open_book(). Eliminates main-thread XML parse
    lag (~0.7s+ on ARM) for chapter navigation.
  v0.1.47 -- Removed all JW paragraph class rendering (sm/sh/si/sb/sj).
    epub_engine.py: JW_PARA_CLASSES dict and detection/emit block
    removed from walk(). These caused italic, indent, small font and
    grey colour on Bible verse text (sb class on every NWT verse),
    outline labels, copyright lines etc. Bold still comes through
    naturally from <strong> in source HTML. main.py: draw_reader
    simplified -- all para kinds now render as plain body text, same
    size and colour. superscript/caption also no longer get small font
    or COL_DIM (uniform rendering throughout). box_rule unchanged.
  v0.1.46 -- Two fixes (epub_engine.py + main.py):
    (1) Removed pagenum ([p.N]) tokens entirely. JW print-page markers
        (<span class="pageNum">) are now silently skipped in walk().
        Previously they were emitted as "[p.N]" text tokens with a
        pagenum ParaSpan, which caused the whole wrapped line containing
        the marker to render in small/dim font (the para_span overlap
        check painted the entire line, not just the token). All pagenum
        references removed from ParaSpan docstring, draw_reader
        use_small check, and segment color logic.
    (2) Fixed O(n^2) line_abs_start in draw_reader. Previously computed
        as sum(len(_lines[i])+1 for i in range(li)) on every line every
        frame -- ~32M iterations/frame on large NWT chapters (8000+
        lines). Now precomputed once in _ensure_page_built() into
        _line_abs_offsets[] list; draw_reader does a single index lookup.
  v0.1.45 -- Pre-render counter fix: previously showed 0/0 during the
    entire spine-walk phase (up to 3941 files for NWT) because
    _prerender_total was only set after the walk completed. Added
    _prerender_scanning flag; _prerender_keys and _prerender_total now
    update live per spine file so the Storage screen shows
    "Scanning book... (N images found so far)" during the walk, then
    switches to "done/total images decoded" once decoding begins.
    Button label also updates live. prerender_progress() now returns
    (done, total, scanning) -- all three callers updated.
  v0.1.44 -- Two image rendering bug fixes:
    (1) Race in get_image_texture(): get() + is_full_res() were separate
        lock acquisitions; worker could land full decode between them,
        tagging a blurry thumb texture as full-res permanently ("improving..."
        stuck, pixelated image). Fixed with new atomic get_with_full_flag().
    (2) Duplicate scale= in draw_reader(): zero-guard line silently
        overwritten by second line without guard (div-by-zero if iw/ih=0).
        Collapsed to: min(box_w/iw, box_h/ih) if iw and ih else 1.0


  v0.1.35 -- Two things:
    (1) Fixed the Library pin icon: it used a star (U+2605), which is
        NOT present in Liberation Sans -- confirmed via both fontTools
        cmap inspection and a live SDL_ttf glyph lookup (returned glyph
        index 0, i.e. "not provided") -- meaning it was always rendering
        as a blank/tofu box, not a design choice. Switched to a heart
        (U+2665), confirmed present in the font both ways too. Audited
        every other Unicode escape used in the UI while at it: em dash
        is present and fine; the one other escape found is a sort-key
        sentinel value that's never actually rendered as text, so no
        other glyph issues exist right now.
    (2) Completed the full bold/italic styling system (font loading and
        HTML-side extraction already existed from earlier in this
        session; the actual rendering pipeline connecting them did not
        -- get_page()'s signature had already changed to return a 5th
        value (styles) but main.py's callers hadn't been updated yet,
        which meant every single page load was crashing outright before
        this fix). Real Liberation Sans Bold/Italic/BoldItalic (matching
        version 2.1.5, byte-identical to the already-bundled Regular,
        confirmed via checksum) now ship in assets/. FontManager already
        had per-style font-handle caching with graceful fallback to
        regular if a style file is missing. epub_engine.py already
        tracked <strong>/<b> -> bold and <em>/<i> -> italic as
        StyleSpans with absolute text offsets. What was missing and is
        now built: _wrap() computes per-line style runs from those
        offsets (new _compute_line_style_runs()), and draw_reader()
        renders each line as a merged sequence of link/image-range AND
        style-run segments (new _line_segments()) rather than one
        whole-line draw call -- so a character that's e.g. both a link
        and bold gets the link's color WITH the bold font, neither
        dimension silently overriding the other.
    Verification for this size of change: re-parsed every page of all 9
    real books (5,199 pages, 0 errors, 77,178 real style spans
    extracted); confirmed a real bold span in actual JW content (a Bible
    citation reference); confirmed FontManager returns genuinely
    different font handles per style; confirmed at the FreeType surface
    level (bypassing this sandbox's known broken dummy-driver texture
    step) that the bold font actually renders wider glyphs for identical
    text (108px vs 97px), not just a different pointer; then drove a
    full real-SDL render walk through 3,254 actual screens across all 10
    library books with zero exceptions. One bug caught and fixed during
    this pass: the new per-line style-run helper was originally named
    the same as the instance attribute meant to store its output
    (self._line_style_runs), which silently shadowed the method after
    the first assignment -- renamed to _compute_line_style_runs().
  v0.1.34 -- Fixed HTML <table>-based content (common in Project
    Gutenberg books, essentially never seen in JW publications until
    now) rendering as one giant run-on wall of text with no line breaks
    between table rows -- reported as "renders weird" on A Study in
    Scarlet's and The Hound of the Baskervilles' in-book Contents pages.
    Root cause: epub_engine.py's BLOCK_TAGS set (which decides which
    HTML tags force a line break) has never included <tr> -- and for
    good reason, confirmed by an EXISTING comment in the code from an
    earlier fix: the JW Bible's book-navigation grid (biblebooknav.xhtml,
    5 short book-abbreviation links per row, e.g. "Gen. Ex. Lev. Num.
    Deut.") deliberately relies on natural width-based word-wrap instead
    of a forced per-row break, or it wastes most of the screen wrapping
    one row per line no matter how much width is available. A blanket
    "tr = newline" would have fixed the reported bug while regressing
    that one. Investigated two REAL Gutenberg TOC patterns (both
    genuinely different table structures) before landing on a fix:
      - A Study in Scarlet: <tr><td><a>Chapter title</a></td></tr> --
        exactly one cell per row.
      - The Hound of the Baskervilles: <tr><td><a>Chapter N</a></td>
        <td>Title</td></tr> -- two cells per row (a plain cell-COUNT
        check alone, tried first, correctly handled the first case but
        missed this one).
    Fixed with a per-row heuristic based on average TEXT LENGTH per
    cell, not cell count: the JW grid's cells average ~4 characters
    each (short abbreviations); both real Gutenberg TOC patterns
    average ~18-35 characters per cell (actual chapter titles).
    Threshold (>10 chars/cell average) picked from these real, measured
    numbers across all three known cases, not guessed. A <tr> that
    trips this average gets treated as a block element (its own line);
    one that doesn't is left exactly as before, completely unchanged.
    Verified thoroughly given this touches the core HTML walker used by
    literally every page of every book: re-confirmed the JW book-nav
    grid still flows identically to before (byte-compared the actual
    output text); confirmed both Gutenberg TOC patterns now render one
    chapter per line; then re-parsed EVERY page of all 9 real books in
    the library (5,199 pages total: 2 Gutenberg novels + 7 JW
    publications, including the 3,941-page NWT) with zero exceptions;
    finally drove a real SDL render pass (open + page through + draw)
    across all 10 library books to catch anything a text-only diff
    could have missed.
  v0.1.33 -- Performance: mini_jpeg.py's scale_n=1 decode path (the
    instant DC-only thumbnail pass every image goes through first,
    before the full-res upgrade -- the single most-executed decode case
    in the app) now uses a closed-form calculation instead of running
    the general truncated-IDCT machinery. Mathematically, a 1x1 IDCT
    output is exactly dc_coeff * qtable[0] / 8 (the textbook "DC-only
    IDCT" identity -- basis[0][0]^2 = 1/8 exactly, not an approximation)
    -- so this skips building the unused 8x8 dequant block, the 64-entry
    zigzag walk, and both matrix-multiply passes entirely for this case.
    Verified before shipping: diffed the new fast path against the OLD
    general-path code across a DC/quantizer sweep (max difference
    3.6e-12, pure float-ordering noise); ran a full real-image decode
    with both old and new paths and diffed every output byte (max diff
    1/255, a single rounding-boundary artifact from that same float
    noise, not a systematic error); re-ran the PIL ground-truth
    comparison from the original decoder audit to confirm nothing else
    regressed. Benchmarked on 60 real images from an actual JW
    publication epub: 409.6ms/image -> 232.9ms/image, a 1.76x speedup
    for this pass specifically (real measured numbers, not estimated --
    proportional gain on the actual ARM handheld should be similar even
    if absolute timings differ from this dev machine).
    Also reviewed main.py's render side (get_image_texture/draw_reader)
    per request -- no equivalent change made there: the LRU texture
    cache already skips rebuilding when nothing's changed, and on-screen
    scaling is already delegated to SDL_RenderCopy's destination rect
    (a GPU-side blit), not Python-level arithmetic, so there isn't a
    comparable "restructure the math" opportunity on that side.
  v0.1.32 -- Fixed download browse screens getting stuck showing
    "Loading..." (or a blank screen) after the load actually finished,
    until an unrelated button press forced a redraw. Root cause, once
    traced: the render loop's redraw-polling conditions (e.g. "redraw
    while dl_loading is True") can only ever trigger a redraw WHILE
    their condition holds -- but the background thread flips that flag
    to done on a completely different thread, at an arbitrary moment the
    render loop isn't watching for. The very next redraw check after
    that happens sees "nothing pending anymore" and skips rendering
    entirely, leaving the stale last-drawn frame on screen indefinitely.
    This is a general bug CLASS, not a one-off -- found and fixed FOUR
    occurrences of it once traced, all now explicitly set self.dirty =
    True at the exact moment they finish rather than relying on the main
    loop to notice indirectly:
      (1) the reported case -- _load_dl_page()'s background list_items()
          call (download browse screens)
      (2) start_download()'s background download() call (download
          completion status/library refresh)
      (3) the JW manual pub-code entry's on_validate background lookup
          (v0.1.31's own new feature -- same bug, same session it
          shipped in)
      (4) whole-book pre-render (v0.1.24) finishing
    Also fixed the SAME bug class in image decoding on the Reader screen
    itself, found while tracing the others even though it wasn't
    reported: ImageLoader gained an on_update callback, invoked from its
    worker thread every time a decode finishes (thumb or full stage,
    success or error), wired to mark the app dirty immediately --
    instead of only via has_pending_image_updates()'s WHILE-pending
    polling, which had the exact same class of gap and could in theory
    leave a just-finished image's upgrade to full resolution unpainted
    until the next button press.
    Verified for real, not just by reasoning about it: for each of the
    four cases, kicked off the operation, explicitly reset app.dirty to
    False (simulating "already rendered once"), then polled app.dirty in
    a tight loop with NO button presses at all -- confirming it flips
    back to True on its own once the background thread completes, for
    every case. Also ran a full regression pass (page-turn, chapter
    jump, draw_reader) to confirm nothing else broke.
  v0.1.31 -- Feature: manual JW.org publication-code entry, per request
    -- for typing in a code the person already knows/found themselves,
    not limited to the curated STATIC_PUBLICATIONS list in jw_fetch.py.
    Reuses the same D-pad text-entry screen v0.1.30 built for Gutenberg
    search, but through a new on_validate path (App.open_text_entry()
    gained this as a second, mutually-exclusive option alongside the
    existing on_confirm): the typed code is actually looked up against
    the live API on a background thread BEFORE leaving the entry screen,
    so an invalid code shows a clear inline error and lets the person
    fix a typo and retry immediately, rather than bouncing to the
    results list with nothing in it (per explicit confirmation on both
    of these points). Periodicals are supported by typing the code and
    issue together, space-separated (e.g. "w 202609"). New
    jw_fetch.lookup_pub_code(code, issue) does the actual round-trip.
    Gated behind a new SUPPORTS_MANUAL_CODE flag (jw_fetch.py sets it;
    gutenberg_fetch.py doesn't -- Gutendex has actual search, a raw code
    lookup wouldn't make sense there) -- same opt-in pattern
    SUPPORTS_SEARCH already established, so Y does the right thing for
    whichever plugin is active without main.py needing to know which
    plugin it's talking to.
    TWO real bugs caught and fixed during verification (again, by
    actually driving real button input against the real API, not just
    reading the code):
      (1) lookup_pub_code()'s retry logic (for pubs like the plain NWT
          that need an explicit fileformat=EPUB param) never actually
          ran -- urllib.request.urlopen() raises HTTPError for the
          server's 400 response to the FIRST attempt (confirmed live;
          curl doesn't surface this the same way, which is why it wasn't
          obvious from earlier curl-based testing), and the old code
          returned on that first error before ever reaching the retry.
          Fixed the control flow so a failed first attempt falls through
          to the retry instead of giving up immediately; also improved
          the error message for a genuinely nonexistent code to say so
          plainly instead of "Network error: HTTP Error 400" (technically
          accurate, but reads like a connectivity problem when it isn't).
      (2) MUCH more basic: the letter grid built for v0.1.30 had NO
          DIGITS at all -- typing a periodical issue number like 202609
          was flatly impossible with the shipped grid, silently
          defeating the periodical-support requirement for this very
          feature. Caught immediately when the first real test tried to
          type "w 202609". Rebuilt the grid with letters, then digits,
          then actions as separate (ragged-length, ordinary) rows;
          confirmed the existing navigation code already handled ragged
          rows correctly without needing changes there.
    Verified end to end with real button input: typed "bhs" (a code NOT
    in the static list) and confirmed it resolves via the live API;
    typed a deliberately bogus code and confirmed the screen stays put
    with a clear error, then backspaced and retried successfully without
    losing the session; typed "w 202609" and confirmed the correct
    periodical issue resolves; confirmed Gutenberg's search (v0.1.30)
    still works unaffected on the rebuilt grid.
  v0.1.30 -- Feature: on-screen search for the Gutenberg downloader, per
    request (the earlier "browse popular only" limitation was flagged as
    a known gap when the downloader shipped, not a bug -- this fills it
    in). Built as a GENERIC D-pad letter-grid text-entry screen
    (SCREEN_TEXT_ENTRY, App.open_text_entry()) rather than something
    Gutenberg-specific, so any future feature needing typed input can
    reuse it. 6x5 grid (26 letters + space/backspace/confirm/cancel,
    exact fit, no wasted cells); D-pad moves the cursor, A selects a
    cell, X is a quick-backspace shortcut, B cancels outright (the
    on_confirm callback is simply never called -- whatever triggered the
    search stays exactly as it was).
    Gated behind a new SUPPORTS_SEARCH flag plugins can declare --
    gutenberg_fetch.py sets it (Gutendex actually supports a `search`
    param); jw_fetch.py does not (its catalog is small/fixed, a search
    box would be pointless there) and the Y-Search hint simply doesn't
    appear for it. Search results reuse the exact same
    list_items()/pagination path as browsing -- a query is just another
    parameter alongside page, with a matching stale-response guard
    (dl_query included, not just dl_page) so a slow in-flight request
    can't clobber a newer search.
    Verified with real button-driven input end to end: opened search,
    typed "DUNE" letter by letter through actual grid navigation
    (confirmed via a monkeypatched list_items() that the exact query and
    page reached the plugin call), confirmed and watched dl_query and
    the on-screen title update; separately verified B correctly cancels
    without invoking the callback or touching the existing search, X
    backspaces correctly including on a prefilled value, and Y is
    correctly a no-op on jw_fetch (SUPPORTS_SEARCH absent).
  v0.1.29 -- Button remap on the Library screen, per request (accidental
    deletions were happening even with the two-press confirm, because B
    sits right next to the D-pad and means "go back" everywhere else in
    the app -- too easy to hit by muscle memory):
      - SELECT now triggers delete (still press-twice-to-confirm, same
        armed-row behavior as before) -- was B.
      - B now quits the app from Library -- was SELECT's job since
        v0.1.27.
      - START opens a new Library-specific popup menu (SCREEN_LIBRARY_MENU):
        direct sort-mode shortcuts (Title A-Z / Author A-Z / Last Read /
        Recently Added -- picks the mode directly instead of cycling
        blind through Y), "Download Books" (same as L2, just discoverable
        without needing to already know the shortcut), and "Storage" --
        which was previously ONLY reachable by opening a book first; the
        Library now has its own path to it. Reader-screen START is
        UNCHANGED (still sets a bookmark), per explicit confirmation.
      Storage's own Back/B previously always returned to the Reader
      screen unconditionally -- harmless when only reachable from there,
      but would have shown a broken/bookless Reader screen now that
      Storage is also reachable from the Library menu with no book open.
      Fixed with a small return-screen tracker (_storage_return_screen)
      set at the point Storage is opened, so Back always goes back to
      wherever you actually came from.
    Verified with real button-driven input through handle_button() again
    (not just AST-parse) after last version's lesson -- specifically
    re-confirmed the Reader screen's own input handling still works
    untouched (the exact regression class from v0.1.28), plus every new
    transition (Library SELECT arm+delete, B quit, START menu, sort
    shortcuts, Storage opened from both the Reader menu and the new
    Library menu returning to the correct place from each).
  v0.1.28 -- Feature: optional downloader plugin system, per request.
    Two new self-contained, OPTIONAL module files:
      gutenberg_fetch.py -- browses/downloads public-domain EPUBs from
        Project Gutenberg via Gutendex (gutendex.com), a community JSON
        API over PG's catalog. Legal to publish publicly per Project
        Gutenberg's own policy (gutenberg.org/policy/permission.html):
        "No permission is needed for non-commercial use... you can
        freely redistribute any eBook, anywhere, any time." Schema
        verified against Gutendex's own GitHub README (this sandbox
        can't reach gutendex.com directly to pull a live sample -- if a
        real response ever looks different from the documented schema,
        re-verify list_items()/_book_to_item() against it).
      jw_fetch.py -- downloads JW.org EPUB publications via the same
        public API (b.jw-cdn.org/apis/pub-media/GETPUBMEDIALINKS) their
        own official apps use, plus parses the jw.org "What's New" RSS
        feed to auto-detect the latest Watchtower Study Edition and
        Meeting Workbook issue (no hardcoded/guessed date). All pub
        codes were verified LIVE against the real API, not guessed --
        see this file's own docstring. PRIVATE per explicit instruction
        -- do not publish this file to a public repo alongside
        gutenberg_fetch.py; keep it local-only. Legal basis (checked
        in-conversation against jw.org's actual Terms of Use, not
        assumed): personal/non-commercial download of public EPUB files
        via a free, non-commercial application is explicitly exempted
        from their anti-scraping clause.
    Both plugins share one contract (PLUGIN_NAME, list_items(), 
    download()) documented in gutenberg_fetch.py's docstring. main.py
    loads whichever files are actually present via a defensive
    try/except __import__ loop (DOWNLOAD_PLUGINS list) -- deleting a
    plugin file removes the feature cleanly with no dead menu items or
    crashes; dropping it back in restores it, nothing else to wire up.
    Library screen: L2 opens the downloader (only shown/bound if
    DOWNLOAD_PLUGINS is non-empty) -- goes straight to the one plugin's
    browse list if only one is present, or a source-picker screen if
    both are. Downloads run on a background thread (same reasoning as
    every other network/decode call in this app: never block input).
    Two real bugs caught and fixed during verification, BEFORE
    shipping, by actually importing and running main.py against real
    SDL2 (this sandbox has libSDL2 installed) rather than relying on
    AST-parse alone:
      (1) jw_fetch.py's RSS date parser resolved bi-monthly titles like
          "November-December 2026" (the Workbook) to December instead
          of November -- wrong issue code entirely (202612 vs the
          correct, live-confirmed 202611). Fixed to always anchor on
          the FIRST month in a range.
      (2) CRITICAL, self-inflicted: an earlier edit in this same session
          that added the SCREEN_DOWNLOAD_BROWSE input-handling block
          accidentally deleted the following "elif app.screen ==
          SCREEN_READER:" line during a str_replace, silently merging
          ALL Reader-screen input handling (scroll, page-turn, chapter
          jump, menu, everything) into the download-browse screen's
          block and leaving the Reader screen with NO input handling at
          all -- normal reading would have been completely broken.
          AST-parse alone did not catch this (still syntactically
          valid). Caught by actually driving real button input through
          handle_button() against a live App instance and checking
          app.screen transitions and app.scroll after each press.
          Fixed by restoring the missing elif header. Both fixes
          re-verified the same way before shipping -- see this
          session's tool-call history for the actual test output.
    Also confirmed via a full real download: gutenberg/jw_fetch's
    download() correctly writes a valid EPUB (verified with zipfile)
    into the actual Library folder, App.start_download()'s background
    thread correctly updates status/refreshes the library list, and
    duplicate-download detection works (won't re-download an existing
    file).
  v0.1.27 -- Button remap, per request: SELECT (JOY_BACK -- was mapped
    to a constant but never actually dispatched to a button name, so it
    did nothing at all) now quits the app from the Library screen,
    replacing START in that role. START keeps its existing "set a
    bookmark" behavior in the Reader screen (left untouched per
    confirmation) and is otherwise unbound, deliberately reserved for a
    planned JW.org publication downloader trigger. Updated the controls
    docstring and Library hint bar to match.
  v0.1.26 -- Feature: "Toggle Images (text-only mode)" on the Storage
    screen. When off, image lines render as a single compact placeholder
    ("[Image hidden -- text-only mode]") instead of the full IMG_BOX_ROWS
    box, and the decoder is never touched at all -- no request(), no
    prefetch, no pending-image polling -- for faster reading when images
    aren't wanted. Refactored visible_span_indices() to call the same
    _rows_for_li() helper page_down()/page_up()/draw_reader() already
    use (previously it duplicated the image-line classification inline),
    so text-only mode's row-cost change (image lines now cost 1 row, not
    14) is automatically consistent everywhere instead of needing the
    same edit made in four places -- exactly the kind of duplicated
    accounting that caused the v0.1.23 skip/cutoff bug in the first
    place. Persisted via settings.json like the existing disk-cache
    toggle; live-updates immediately, no restart needed.
  v0.1.25 -- Feature: delete a book from the Library screen. B, twice to
    confirm (same "press again on the same row" pattern the Bookmarks
    screen already uses for deletes -- armed row highlights, any other
    input cancels it). Only removes the .epub file itself; the image
    cache, anchor cache, and pin entry are deliberately NOT touched
    directly -- scan_library() already detects and purges cache/pin
    entries for any book file no longer present on disk (that cleanup
    already existed, originally written for the case of a book being
    removed by hand outside the app), so refresh_library() right after
    the delete reuses that exact path instead of duplicating the
    cleanup logic. Bookmarks are left alone on purpose, consistent with
    that same existing cleanup's philosophy -- they're the person's own
    data; Storage > Clean Up Orphaned Bookmarks remains the deliberate,
    separate way to clear those. If the book being deleted is also the
    one currently mid-pre-render (v0.1.24), that pre-render is cancelled
    first.
  v0.1.24 -- Three additions, all from direct feedback:
    (1) Shrunk ImageLoader.TARGET_BOX_H from 360 to 480x272 (was
        480x360) -- per follow-up request, aimed specifically at slow-
        loading Bible story book cover images (large/high-res source
        photos). Same tradeoff as the original 680x560->480x360 change:
        a smaller decode-resolution TARGET picks a smaller scale_n,
        trading a bit of sharpness for real decode time, with no visible
        difference since the result is upscaled to fill the same
        on-screen box either way.
    (2) Book-scoped cache accounting: book_cache_size_bytes() and
        delete_book_cache() (prefix-match against the existing
        "{book_id}__..." cache filenames -- no directory restructuring
        needed, the namespacing was already there from the book_id work
        that prevented cross-book image collisions). Storage screen now
        shows the currently-open book's own cache size alongside the
        total. Foundation for an upcoming "delete book" feature that
        will reuse delete_book_cache() to clean up after itself.
    (3) Feature: "Pre-render Book Images" on the Storage screen --
        walks every spine file, collects every unique image, and
        enqueues them all at a new PRIORITY_PRERENDER level (lower
        priority than both PRIORITY_VISIBLE and PRIORITY_PREFETCH).
        Deliberately reuses the existing single-worker priority queue
        instead of a separate thread pool: real reading needs (the page
        you're actually looking at, or about to turn to) always jump the
        queue ahead of pre-render work, so this can run for a long time
        in the background -- a full year of a daily-text book, hundreds
        of images -- without making scrolling or menu input feel
        unresponsive. Progress (X/Y actually decoded, not just
        enqueued -- checked against real decode results) shows live on
        the action row and in the info panel; pressing A again cancels
        it. Automatically cancelled if you switch to a different book
        mid-run, guarded by a book-id check so a stale progress bar or
        late-arriving decode can never bleed into the wrong book.
    Also added a permanent "AI NOTES" block at the top of this file
    (architecture summary + recurring bug shapes) per request, so a
    future session can orient quickly instead of re-deriving context
    from the full changelog every time.
  v0.1.23 -- Fixed images getting cut off ("shows half the image") and
    then skipped entirely on the next page-turn, reported while reading
    the second study article of a real Watchtower epub with L/R page
    turns (and, less predictably, after D-pad scrolling too). CONFIRMED
    via direct simulation (a 30-line page with an image sitting right
    where a page boundary would fall at body_rows=20): two compounding
    bugs, both now fixed together --
    (1) page_down()/page_up() did `scroll +/- body_rows` directly.
        body_rows is a VISUAL row count (screen height / line height),
        but self.scroll is an index into self._lines[], where one image
        is a SINGLE entry that costs IMG_BOX_ROWS (14) visual rows to
        draw -- draw_reader() and visible_span_indices() already knew
        this and walked row/li separately, but page_down/page_up never
        did, so a flat body_rows added straight to scroll could jump
        clean over an image's li (skipping it) or land short of a full
        page (re-showing lines already seen). Fixed by giving both
        methods the same row-cost-aware li walk draw_reader() uses (new
        shared helper _rows_for_li()), so paging always advances/
        retreats by exactly what was actually shown on screen.
    (2) draw_reader()'s render loop drew an image unconditionally once
        it started iterating that line, even when the remaining space
        on screen (body_rows - row) was less than IMG_BOX_ROWS -- so an
        image near the bottom of a page rendered cropped instead of
        being deferred to the next page. Fixed: the loop now checks
        whether the image would fully fit in what's left of the current
        screen and, if not, stops the page there (unless it's the very
        first thing being drawn, to avoid an infinite stall on an
        oversized image) -- the image becomes the first thing shown on
        the next page instead of being torn in half.
    Verified: simulated page_down() from just before the image stops
    exactly at the image's line (not mid-image, not past it); the next
    page_down() shows the full image plus a full following screenful;
    page_up() from there returns to exactly the same starting line.
  v0.1.22 -- Fixed L2/R2 "next chapter" skipping day/chapter 1 of any
    book that has cover/front-matter pages before its first real
    chapter (reported: opening a daily-text epub and pressing R2 from
    the cover landed on "Friday, January 2", never "Thursday, January
    1"). CONFIRMED root cause via direct simulation against the
    person's own es26_E.epub: _build_chapter_nav_points() correctly
    detects Jan 1 as the first daily entry (365 weekday-prefixed pages
    found, in order, Jan 1 first) -- the bug was purely in
    _jump_chapter()'s position math. When the reader is currently
    positioned BEFORE the first nav point (spine index less than the
    first chapter's), bisect gives pos = -1, meaning "not yet at any
    chapter". The old code clamped this to pos = 0 (treating the
    front-matter page as if it were already sitting AT chapter 0), so
    "next" (pos + 1) jumped straight to chapter 1, permanently skipping
    chapter/day 0. Fix: when pos < 0, "next" now explicitly targets
    chapter 0 instead of chapter 1; "previous" from that same position
    correctly still reports no previous chapter. This affects any book
    with front matter, not just daily-text publications -- general fix.
  v0.1.21 -- Fixed the menu/hint bar font-size scaling bug (reported
    multiple times -- confirmed via screenshots showing the hint bar
    text running past the right edge of the screen). Root cause: every
    UI element (hint bar, menu popup, Library/Chapters/Bookmarks/Storage
    screens, all headings) shared the SAME size-index-driven font
    properties as the actual reader body text, so "Font Size +/-" (meant
    to control the book text only) also inflated the chrome around it,
    and none of that chrome's layout code accounted for suddenly-larger
    text needing more room. FontManager now has a separate fixed
    UI_STEP=18pt reference, with ui_body/ui_small/ui_heading properties
    that never move regardless of size_index. Reader body text (the
    _wrap() layout pass and the actual line/link/image rendering in
    draw_reader) is the ONLY thing still tied to the scalable
    body/small/heading properties -- correctly, since that's the whole
    point of the font-size control. Every other draw_* function (hint
    bar, library, menu, TOC, bookmarks, storage, and the image
    loading/upgrading placeholder text) switched to the fixed ui_*
    variants. Verified directly: hint bar rendered width is now
    identical (595px, well under the 720px screen) at the smallest,
    default, and largest reading sizes -- previously this would have
    grown proportionally with each step up. Also re-rendered menu/TOC
    at max reading size with no errors.
  v0.1.20 -- Image loading indicator now shows elapsed time
    ("Loading image... (3s)") instead of a static placeholder that looks
    identical whether decode has been running for 1 second or 30.
    Investigated first (not assumed): simulated the exact real sequence
    (button press -> open_book() -> first draw_reader() call) and the
    exact idle-loop logic main() actually runs, with real decode timing.
    Both the image-request trigger and the periodic while-loading
    redraw worked correctly in that simulation -- the image resolved on
    its own within the idle wait, no scroll/input needed. Given the
    report was specifically that the first image looked "stuck" until
    scrolling, and other images resolved fine without needing anything
    beyond time passing, the mechanism itself wasn't broken; the person
    just had no visible confirmation that a fixed placeholder was still
    doing something. Chose the transparent fix over guessing at
    speeding up decode without evidence that decode speed was the
    problem. ImageLoader.request() now stamps a requested_at timestamp;
    new ImageLoader.seconds_loading(key) exposes elapsed time to the UI.
  v0.1.19 -- Font: reverted priority order back to checking system paths
    FIRST (matching the original v0.1.0 behavior), now safe to do since
    v0.1.17 added unconditional logging -- a failure here is diagnosable
    now instead of silent. Also switched the searched typeface to DejaVu
    Sans Mono, matching Pico8FavsSorter's exact font list and look
    (confirmed directly from Favs Sorter's actual source, not guessed):
      DejaVuSansMono.ttf -> DejaVuSans.ttf -> TTF/DejaVuSansMono.ttf ->
      FreeMono.ttf -> LiberationMono-Regular.ttf (two path variants) ->
      bundled assets/font.ttf (now also DejaVu Sans Mono, swapped from
      the previous bundled DejaVu Sans) as the final fallback.
    Bundled font kept as the LAST resort (not removed) -- this is the
    one thing standing between "text renders" and the exact blank-UI
    bug this device already hit once. Verified both paths: system-path
    resolution (this dev sandbox has DejaVuSansMono.ttf) and the bundled
    fallback (forced FONT_PATH to the bundled file directly) both render
    correctly with no crash.
    Still open: the menu popup / hint bar scaling with reading font size
    and overflowing off-screen at larger sizes (diagnosed, not yet
    fixed -- holding per explicit request until other items are
    gathered), and the image-loading-only-on-scroll report (not yet
    investigated).
  v0.1.18 -- Two items, both grounded in evidence the person actually
    provided (crash log + screenshots), not assumptions:
    (1) CONFIRMED (not theorized) by picoreader_crash.log: FONT_PATH
        resolved to the bundled assets/font.ttf and text now renders
        correctly on-device. v0.1.17's diagnostic logging did its job.
        Why the original v0.1.0 (identical font-path code, no bundled
        font) apparently worked before remains unexplained and is being
        left alone rather than guessed at further -- not worth chasing
        now that this build works, but noted here so it isn't silently
        forgotten.
    (2) Fix: inconsistent Bible chapter-link highlighting, diagnosed
        directly from a real screenshot (Exodus chapter grid: 10, 13, 14
        highlighted; 28, 29, 30, 31 in the same row plain white) rather
        than guessed at. Root cause: v0.1.5's whitespace-collapse fix
        (epub_engine.py's emit_text()) collapsed whitespace WITHIN each
        text/tail fragment independently, but not ACROSS fragment
        boundaries -- so a table row's trailing whitespace-only tail
        followed by the next row's leading whitespace each collapsed to
        one space separately, concatenating into a double-space in the
        final page text (confirmed: exactly one double-space per <tr>
        boundary, matching the table's 5-links-per-row structure).
        main.py's line-wrapper then silently re-collapsed each of those
        double-spaces back to one when reconstructing the visual line
        (word-join with " ".join(), which drops the empty string a
        double-space produces on split) -- permanently desyncing
        character offsets, and therefore link span positions, from that
        point forward in the paragraph. Worse with each subsequent row
        as the drift compounded, matching the reported pattern exactly.
        Fixed emit_text() to also collapse across fragment boundaries
        (skip a leading space if the previously-emitted text already
        ended in one). Verified: 0 double-spaces and 0 uncovered link
        characters remain across all 61 chapter-nav pages in the whole
        Bible (was checking one page's worth of manual evidence before;
        now checked exhaustively). Regular prose paragraphs (Psalm 91,
        Genesis) reconfirmed unaffected.
    Still pending clarification from the person: what specifically
    looked "nicer" about Pico8FavsSorter's font rendering, for
    comparison -- not acted on without more detail, per explicit
    instruction to ask rather than assume.
  v0.1.17 -- DIAGNOSTIC BUILD, not a confirmed fix. Correction to
    v0.1.16 below: that entry stated the missing-bundled-font theory as
    a confirmed root cause. It wasn't confirmed -- it was a plausible
    theory built from reading the code, presented with more certainty
    than the evidence supported. The person directly disproved it:
    the ORIGINAL v0.1.0 (still sitting in project knowledge, byte-for-
    byte identical FONT_PATHS/FontManager/render_text to what shipped
    in v0.1.16) reportedly showed text working, and /tmp/picoreader_
    crash.log doesn't exist on the device at all -- meaning no
    exception has ever been logged, this specific failure mode included.
    Reported symptom (still unexplained): background/highlights/images
    all render correctly, app runs and responds normally (book opens,
    chapters scroll, menu opens), but literally zero text renders
    anywhere -- and the gaps between images are short, suggesting line
    layout/height IS being computed from real font metrics, just
    nothing visible gets drawn.
    This build adds real diagnostics instead of another guess:
    - TTF_Init result logged unconditionally (OK, or the SDL error).
    - FONT_PATH resolution logged unconditionally, not just on failure.
    - render_text() now logs (once per failure type, to avoid flooding)
      if TTF_RenderUTF8_Blended returns NULL, if
      SDL_CreateTextureFromSurface returns NULL, or if SDL_RenderCopy
      returns a nonzero (error) code -- covering every step between
      "font handle exists" and "pixels actually copied to the screen."
    - COL_TEXT/COL_BG values logged once at startup, to rule out a
      color/alpha mixup without more speculation.
    Bundled font and reordered FONT_PATHS from v0.1.16 are kept in (they
    can only help, not hurt), but this build should be treated as a
    request for real evidence, not a claim that the blank-text issue is
    resolved. Next step: run this on-device, reproduce the blank text,
    and share whatever /tmp/picoreader_crash.log contains -- that
    determines what actually needs fixing.
  v0.1.16 -- [SEE CORRECTION ABOVE] Attempted fix for a blank-UI report (background
    colors, highlights, and images rendered fine, but zero text
    anywhere -- no menu labels, no book content, nothing). Root cause:
    FONT_PATHS only listed standard desktop-Linux font locations
    (/usr/share/fonts/truetype/dejavu/...), none of which exist on
    muOS's minimal embedded Linux. The intended fallback
    (assets/font.ttf) was never actually bundled into any package this
    whole project -- every dev-machine test happened to have DejaVu Sans
    already installed system-wide, so this was never caught locally.
    render_text() silently no-ops when font is None (`if not font: return
    0`), with zero logging -- exactly matching "images and highlights
    work, but no text at all."
    Fixed:
    - Actually bundled DejaVu Sans (assets/font.ttf, ~760KB) into the
      package this time, plus its license file (permissive, explicitly
      allows redistribution/embedding in software -- verified before
      including it).
    - Reordered FONT_PATHS to check the bundled font FIRST, falling back
      to system paths only if that's somehow missing -- so this can't
      depend on the device's font layout at all going forward.
    - Added crash-log diagnostics for BOTH failure modes that were
      previously silent: no font found at all, and TTF_OpenFont failing
      even with a valid path (corrupt file, bad format, etc.) -- the
      latter needed SDL_GetError(), not TTF_GetError(), since SDL2_ttf
      doesn't export its own error function and reports through the
      shared SDL error string. Confirmed this the hard way: my first
      attempt called a nonexistent TTF_GetError symbol, which would have
      crashed on exactly the failure path it was meant to diagnose --
      caught via direct ctypes testing before shipping, not after.
    Verified: forced a font-open failure with an invalid file and
    confirmed a real, readable message now lands in the crash log
    instead of silence; confirmed the bundled font resolves first and
    renders correctly end-to-end.
  v0.1.15 -- Feature: bookmark backup/restore via Menu > Storage.
    - "Backup Bookmarks Now" writes a timestamped snapshot of every
      book's bookmarks to a new backups/ folder -- deliberately a
      sibling of library/ and data/ (not buried inside data/) so it's
      easy to find and copy off the device with a file manager. Non-
      destructive/instant (only ever adds a file), so no confirm needed.
      Keeps only the 10 most recent backups so this can't grow
      unboundedly like everything else this session has been careful
      about.
    - "Restore Latest Backup" merges (does NOT blindly overwrite) the
      newest backup into live data -- per book, per (file, anchor, label)
      entry: if both a live and backed-up version exist, keep whichever
      has the later timestamp; otherwise add it. Still respects
      MAX_BOOKMARKS_PER_BOOK=20 by keeping the most recent entries per
      book after merging. Confirm-armed (press A twice) since it does
      modify live data, unlike the backup action.
    - Storage screen now also shows backup count and the most recent
      backup's timestamp.
    Verified end-to-end: backed up 2 real bookmarks, simulated data loss
    by deleting bookmarks.json entirely, restored -- both came back
    correctly. Then added a third bookmark AFTER that backup and
    restored the (now-older) backup again to confirm the merge doesn't
    clobber newer local changes -- all three bookmarks survived.
  v0.1.14 -- UI/stability review across every screen, requested
    specifically to find missing usability features and edge cases (not
    tied to a single bug report). Found and fixed:
    (1) Feature: Chapters screen always opened at the very top of the
        list, regardless of where you were actually reading -- for a
        66-book Bible or 741-day daily text, that meant re-navigating
        from scratch every time. Added
        App._toc_index_for_current_position(), which finds the TOC entry
        nearest-at-or-before the current spine position (same pattern
        already used for bookmark labels), so Chapters now opens
        scrolled to "you are here." Verified: opened from Psalm 91,
        Chapters now lands on index 63 ("Psalms") instead of index 0.
    (2) Feature: UP/DOWN on every list screen (Menu, Library, Chapters,
        Bookmarks, Storage) now wraps around top<->bottom instead of
        just clamping at the ends. Also fixed a latent bug this touched:
        the old clamp pattern (min(n-1, ...)) would have produced index
        -1 for an empty list (0 bookmarks/chapters), which Python
        silently accepts as "last element" on list indexing rather than
        erroring -- not currently reachable with any real book tested,
        but a real landmine for a future edge case. Now guarded to 0 for
        n=0 instead.
    (3) Feature: "Font Size +/-" gave zero feedback -- no indication of
        the current size or that you'd hit the min/max. Now shows a
        status toast ("Font size: 24pt", or "... (largest)"/"(smallest)"
        at the bounds). Confirmed it displays correctly through the Menu
        overlay, which draws the reader (where toast rendering already
        lived) as its background.
    (4) Fix: only the Chapters screen truncated long text; Library and
        Bookmarks didn't, so an unusually long title/label could run off
        -screen (SDL clips it safely -- not a crash -- but looks broken,
        and on Bookmarks could push the timestamp off-screen entirely).
        Added the same truncation pattern to both.
    Reviewed but found no issues: flatten_toc()'s recursion is bounded by
    TOC nesting depth (real books never exceed ~10 levels vs Python's
    1000-frame default limit) -- not a practical stack-overflow risk.
  v0.1.13 -- Real-world test pass against 5 newly-provided sample epubs
    (lffi, od, rr, lfb, es26 -- a brochure, a small book, two larger
    illustrated books, and the previously-fixed daily-text booklet) plus
    one non-epub upload (a .jwpub file), covering library scan/sort,
    chapter navigation, linking, and images. Found and fixed:
    (1) Real bug: silently opening an incompatible file (tested with a
        .jwpub renamed to .epub -- confirmed via inspection that .jwpub
        is a fundamentally different container format, manifest.json +
        contents, no OPF/META-INF at all, not just a malformed epub) did
        nothing visible -- open_book() already failed safely internally,
        but gave the person zero feedback, so pressing A just looked
        like the button didn't work. Added status-toast feedback (and
        toast rendering support to the Library screen, which didn't have
        any before) for both known open_book failure paths.
    (2) Real bug found via testing, NOT hypothetical: JPEGs using restart
        intervals (DRI marker) failed to decode -- confirmed via a real
        sample book (lffi_E.epub) where this hit 37 of 49 images (75%).
        The decoder had a previous defensive NotImplementedError for
        this rather than risk producing corrupted pixels, with a correct
        implementation already partially started downstream (_decode_scan
        already threaded restart_interval through and called
        reset_byte_align() at each boundary) -- but reset_byte_align()
        cleared the bit-buffer state without ever advancing pos past the
        2-byte restart marker itself, meaning if the early fail hadn't
        been there, decoding would have silently corrupted every image
        that actually used restart intervals. Fixed reset_byte_align()
        to correctly consume the marker's second byte (the leading 0xFF
        is already consumed when the marker is first detected during
        bulk-fill, but the marker-type byte itself was only peeked, not
        consumed) and removed the now-safe-to-remove NotImplementedError.
        Verified by actually decoding and visually inspecting several of
        the previously-failing images at full resolution (not just
        checking for "no crash") -- clean, correct output, no artifacts
        at restart boundaries. Re-verified all 49/49 images in lffi now
        succeed (up from 12/49), sampled 109+65 images across lfb_E.epub
        and rr_E.epub with zero further failures, and reconfirmed non-
        restart-interval images (everything in NWT/Watchtower/es26) are
        completely unaffected -- reset_byte_align() is only ever called
        from the restart-interval branch, so books without DRI markers
        never touch this code path at all.
    (3) Fix: a permanently-failed image (like the DRI ones before the
        fix above, or any future genuine decode failure) showed "Loading
        image..." forever, indistinguishable from one that's just slow.
        get_image_texture() now returns a distinct "error" sentinel when
        a decode has permanently failed with nothing cached to fall back
        on, and the reader shows "Image unavailable (unsupported JPEG
        features)" instead. Confirmed has_pending_image_updates() already
        correctly excluded the "error" state, so this was never a
        battery-drain risk, just a misleading message.
    Chapter navigation (L2/R2), library sort, and TOC/link-following all
    checked out correctly on lffi/od/rr/lfb with no further issues found
    -- od_E.epub's unusually high link count (2884 links in a 54-file
    book) was inspected and confirmed legitimate (a dense scripture/
    subject index), not a parsing bug.
  v0.1.12 -- Fix: L2/R2 chapter navigation jumped by full months instead
    of by day in daily-text publications (reported against a real
    "Examining the Scriptures--2026" epub). Root cause: this book has no
    chapterN-style structural anchors (that's Bible-specific), so
    _build_chapter_nav_points() fell through to its TOC fallback -- but
    this book's TOC only lists the 12 months (17 entries total incl.
    front matter), even though every single day is genuinely its own
    spine file (741 spine files total; "-split" suffixes here mean a new
    day, NOT pagination-within-a-chapter like they do in the Bible epub
    -- confirmed by actually reading the page content, not just
    filenames: "...-split2.xhtml" opens with "Friday, January 2").
    Added a third detection strategy: JW daily-text publications reliably
    open each entry with a weekday name ("Thursday, January 1", "Friday,
    January 2", ...) -- a distinctive signal essentially never seen at
    the start of a Bible chapter or magazine article. Deliberately gated
    to only run this extra per-spine-file scan when the TOC already
    looks suspiciously coarse relative to the spine (fewer than 10% as
    many TOC points as spine files, on a book with >50 spine files) --
    so it can never fire for, and can't risk affecting, books that
    already resolve correctly via the first two strategies. First
    version of the regex was anchored at position 0 and missed all 12
    first-of-month days (each has a "January" heading before the weekday
    line); caught via testing (352/365 matches instead of ~365) and
    fixed by searching a wider window instead of matching at the start.
    Verified end-to-end with real button presses on the real file: 365
    daily nav points found (one full year, correct), R2 now steps
    Jan 2 -> Jan 3 -> Jan 4 -> Jan 5 -> Jan 6 one day at a time, L2
    correctly reverses. Reverified the Bible (1,190 points, still via
    chapterN anchors, completely unaffected) and a Watchtower issue
    (9 points/19 spine files -- well above the 10% gating threshold, so
    the new scan never even runs for it) to confirm no regression.
  v0.1.11 -- Storage screen: manual cache management, none of which had
    a UI before (the backend functions -- image_cache_size_bytes(),
    orphaned_bookmark_book_paths(), clean_orphaned_bookmarks(),
    clear_image_cache(), and ImageLoader's disk_cache_enabled flag --
    already existed from the previous session but were never wired to
    anything reachable in the app). Added via Menu > Storage:
    - Live stats: current image cache size on disk, count of orphaned
      bookmark sets (from deleted books), disk cache on/off state.
    - "Clear Image Cache" -- deletes every on-disk cache file and clears
      both in-memory caches (ImageLoader._results and the App's SDL
      texture cache), so nothing stale lingers in RAM either. Confirm-
      armed (press A twice) using the same pattern already established
      for bookmark deletion, so a stray press can't wipe it.
    - "Clean Up Orphaned Bookmarks" -- removes bookmark entries for
      books no longer in the library. Also confirm-armed, since this
      touches the person's own data, not disposable cache.
    - "Toggle Disk Cache (RAM-only mode)" -- flips ImageLoader's
      disk_cache_enabled LIVE (no restart needed) and persists the
      choice to settings.json for next launch. With it off, decoded
      images are never written to disk at all -- pure RAM operation,
      still bounded by MAX_INMEMORY_IMAGES.
    Verified all four against real data: cleared a real 3.4MB cache
    (12 files -> 0, in-memory caches confirmed empty after); created a
    genuine orphaned bookmark by deleting a book, confirmed cleanup
    removed exactly that entry; toggled RAM-only mode and confirmed
    zero disk writes while viewing images that still loaded correctly
    into memory.
  v0.1.10 -- Bounded image memory, plus a real correctness bug found
    while implementing it (not a hypothetical -- caught by testing):
    (1) Fix: the shared ImageLoader keyed cached images purely by their
        INTERNAL epub path (e.g. "OEBPS/images/cover.jpg") with no book
        identifier at all. Since ImageLoader is shared across every book
        opened in a session, two different books that happened to reuse
        the same internal image path (common in EPUB packaging) would
        have silently collided -- one book showing another's cached
        image, both in memory and on disk. Added book_id() (same
        derivation the anchor cache already used) and namespace every
        image-cache key by it via a new App._img_key() helper, covering
        ImageLoader.get/request/has_full_disk_cache/is_upgrading/
        is_full_res, the prefetch path, and the App's own SDL-texture
        cache. Verified: the same internal path in two different books
        now produces two different cache keys.
    (2) Feature: deleting a book's epub file used to leave its image
        cache, anchor cache, and pin entry sitting on disk forever with
        nothing that could ever reference them again. scan_library()'s
        existing stale-entry cleanup (which already handled the title/
        metadata cache) now also globs and removes {book_id}__* files
        from the image cache and the book's anchor_cache/{book_id}.json,
        and drops its pinned.json entry. Caught and fixed a real bug
        during testing: the on-disk pinned.json purge wasn't being
        reflected back into the already-loaded in-memory App.pinned set,
        so a deleted-but-still-pinned book would silently un-pin on disk
        but still show as pinned in the running app until restart --
        refresh_library() now reloads pinned state from disk after
        scanning. Verified end-to-end: copied a book in, viewed/cached
        its images, pinned it, deleted the file, rescanned -- all 12
        cache files and the pin entry were gone, in memory and on disk.
    (3) Feature: ImageLoader._results (the in-memory decoded-image cache)
        grew unboundedly for the entire life of the app before this --
        unlike the App's own SDL-texture cache, which already had a
        24-entry LRU cap. Added MAX_INMEMORY_IMAGES=60 with the same
        OrderedDict-based LRU pattern (~15-25MB of RAM at typical real
        image sizes). Eviction only runs on fully-resolved entries, never
        one still "loading" mid-decode. Verified: pushing 90 entries in
        correctly trims to 60, oldest evicted first.
  v0.1.9 -- Two more image-loading optimizations, both verified against
    real epub content:
    (1) Fix: get_image_texture() and the next-page prefetch were both
        unconditionally reading the raw JPEG bytes out of the epub zip
        (potentially decompressing a DEFLATE-stored entry) EVERY time an
        image was first requested in a session -- even when the decoded
        result was already sitting in the on-disk .rgb cache from a
        previous session, about to make that zip read pointless.
        ImageLoader.has_full_disk_cache() lets both call sites skip the
        zip read entirely and pass jpeg_bytes=None through the normal
        async request() queue (kept on the background worker thread, not
        blocking the render loop) when a disk-cache hit is already known.
        Verified against a real Watchtower article: reopening it in a
        fresh App instance with a warm disk cache dropped total image
        load time from 3.76s to 0.02s.
    (2) mini_jpeg.py's IDCT basis matrix (trig-heavy, but only depends on
        scale_n, of which there are just 8 possible values) was being
        rebuilt from scratch on every single decode_jpeg() call, even
        when several images on the same page share the same scale_n.
        Added @functools.lru_cache(maxsize=8) -- pure function, safe to
        cache (verified _idct_scaled() only reads from it, never
        mutates), confirmed identical decode output before/after.
    Also discussed but NOT implemented (bigger scope, flagged for a
    future session if wanted): switching the single-threaded ImageLoader
    worker to a multiprocessing pool for true parallel decode across
    CPU cores (the current single-worker-thread design is correct for
    threads specifically, since CPU-bound Python work is GIL-serialized
    anyway -- processes could actually help but need muOS/fork
    verification first), and bounding ImageLoader._results in memory
    (currently grows unboundedly for the life of the app, unlike the
    already-bounded _image_textures LRU).
  v0.1.8 -- Feature: Library sorting and pinning, none of which existed
    before (books were always plain filename order). Verified against
    the real library directory with a mix of authors and mtimes:
    - Y on the Library screen cycles four sort modes: Title A-Z,
      Author A-Z (no-author books sort last, not first), Last Read
      (pulled from the same bookmarks.json __lastpos__ timestamp already
      used for "resume reading" -- never-read books sort last), and
      Recently Added (a NEW first_seen timestamp added to
      library_cache.json, deliberately kept stable across rescans/edits
      so it doesn't reorder every time a file's mtime changes for an
      unrelated reason).
    - X pins/unpins the selected book. Pinned books float to the top
      under every sort mode, still sorted among themselves by whichever
      mode is active, and are marked with a "star" prefix. Persisted to
      a new pinned.json, independent of the sort mode itself.
    - Author extraction (dc:creator, same regex approach as the existing
      dc:title extraction) added to the library scan/cache.
    - Verified: pinning a book keeps it first across all four sort
      modes; unpinning drops it back into normal sorted position;
      selection follows the pinned book rather than jumping elsewhere
      when the list re-sorts under it.
  v0.1.7 -- Bookmark management: duplicate handling, a 20-per-book cap,
    and deletion, none of which existed before. Verified end-to-end:
    - Bookmarking the same file+anchor twice now UPDATES the existing
      entry's label/timestamp instead of creating a duplicate.
    - Capped at MAX_BOOKMARKS_PER_BOOK=20 real bookmarks per book (the
      internal __lastpos__ "resume reading" marker doesn't count against
      this). Attempting to add past the cap is refused with a status
      message telling the person to delete one first, rather than
      silently failing or silently growing forever.
    - X on the Bookmarks screen now deletes: first press arms the
      selected row (shown in red with "Press X again to delete, or B to
      cancel"), second press on the same row actually deletes it. Any
      navigation (UP/DOWN/L/R/Y) or B cancels the pending delete instead
      of accidentally deleting the wrong row.
    - Added a lightweight status-toast system (App.status_msg /
      set_status()) since none existed -- used here for "Bookmarked...",
      "Bookmark updated...", "Bookmark limit reached...", and "Bookmark
      deleted" feedback, so none of this happens silently. The main loop
      now also keeps redrawing while a toast is showing so it disappears
      on schedule instead of lingering until the next button press.
    - Bookmarks screen header now shows "BOOKMARKS (n/20)".
    Tested with a real add/duplicate/cap-to-20/delete/cancel sequence
    against the actual bookmarks.json flow.
  v0.1.6 -- Feature: L2/R2 on the Chapters screen now jump to the
    previous/next "real" section (Bible book or magazine article)
    instead of a fixed row count -- a simpler alternative to a numeric
    keyboard-entry screen for long lists like the Bible's 66 books.
    First attempt used TocEntry.level to detect section boundaries, but
    this epub's TOC turned out to have NO nesting at all (every entry is
    level 0), so that approach silently did nothing useful -- caught via
    testing against the real file before shipping. Fixed by using a
    title-pattern heuristic instead: each Bible book appears as two
    consecutive entries ("Genesis Outline" then "Genesis"), so L2/R2 skip
    the "<Name> Outline" summary pages and land only on the real
    book/article entry. Verified against the real NWT TOC: R2 from
    Genesis correctly steps Exodus -> Leviticus -> Numbers -> Deuteronomy
    -> Joshua -> Judges, one full book per press.
  v0.1.5 -- Four fixes from real-device feedback, all verified against the
    real NWT and Watchtower epubs:
    (0) CRITICAL SELF-FIX: an earlier edit this session had accidentally
        merged draw_toc() and draw_bookmarks() into one function, deleting
        the "def draw_bookmarks(...)" header entirely -- opening the
        Bookmarks screen would have crashed with NameError. Caught and
        fixed before shipping; verified both screens render standalone.
    (1) Fix: chapter-link pages like the Psalms "1 2 3 4 5 / 6 7 8 9 10..."
        grid only used a small strip of screen width. Root cause: that
        page's source HTML is a real <table> (5 links per <tr>), and the
        raw XML's pretty-printed "\r\n" between tags was being emitted as
        literal hard line breaks instead of being collapsed to a space
        like normal HTML whitespace handling -- so every table row was
        forced onto its own screen line no matter how much width was
        free. Added whitespace-run collapsing (epub_engine.py) matching
        standard HTML rendering. Verified: the Psalms grid went from 33
        wrapped lines to 8, now using the full screen width.
    (2) Fix: a real, pre-existing bug (not something from this session)
        in draw_reader()'s image handling -- the loop used ONE variable
        for both "how many visual rows drawn so far" (row, which jumps by
        IMG_BOX_ROWS=14 for an image) and "which _lines[] entry to render
        next" (also called row, via app.scroll+row). Since an image is
        only ONE entry in _lines but consumes 14 visual rows, every image
        was silently skipping up to 13 lines of real text right after it.
        Verified on a real Watchtower article: an image at the top of the
        page was hiding the article's title, byline, and opening lines
        entirely. Fixed by tracking row (visual) and li (_lines index) as
        separate counters; same fix applied to visible_span_indices() so
        link-selection scope matches what's actually drawn. This is very
        likely the cause of the reported "text moving around" symptom.
    (3) Feature: image decode is faster. Added peek_jpeg_size() to
        mini_jpeg.py (reads just the SOF0 width/height, no entropy
        decode -- ~0.01ms vs 300ms+ for a real decode) so ImageLoader can
        pick a decode resolution sized to the actual on-screen box
        instead of always using a fixed scale. Also lowered the target
        box used for that resolution pick (680x560 -> 480x360), trading
        some sharpness for real speed per direct feedback, and skips the
        separate "instant thumb, then upgrade" pass entirely for images
        that land at scale_n<=4 (most real photos) since paying for a
        second full entropy-decode pass just to show a placeholder for a
        fraction of a second wasn't worth it. Measured against every real
        image in a full Watchtower issue: 39% less total decode time
        (up to 61% for an oversized cover image that was previously
        always decoded at a fixed resolution regardless of its actual
        size).
    (4) Feature: LEFT/RIGHT now do fine (always 1-step) link navigation,
        as the docstring always claimed but was never actually wired up.
        Complements Y's coarse 10x jump and UP/DOWN's toggleable speed.
  v0.1.4 -- Three fixes/improvements from real-device feedback, verified
    against the actual NWT epub:
    (1) Fix: B (go back) after following a footnote/cross-reference link
        always snapped to the top of the chapter instead of returning to
        where you actually were. Root cause: ReaderState.back_stack only
        ever stored (file, anchor) -- never the in-chapter scroll offset
        -- so there was nothing to restore. Added a parallel
        App._scroll_stack pushed everywhere a history-tracked goto()
        happens (follow_selected, Chapters-screen jump, Bookmarks-screen
        jump) and popped in go_back(); reset alongside back_stack when a
        new book is opened. Verified: scroll=3 preserved across a real
        footnote round-trip on Psalm 91.
    (2) Fix: bookmarks were labeled with the raw internal spine filename
        (e.g. "1001061123-split20.xhtml"), which is meaningless -- the
        save-date shown next to it was the only readable part, making
        bookmarks look like they were "labeled by date." Added
        App._current_location_label(), which finds the nearest top-level
        TOC entry at-or-before the current position (book/section title)
        and, where available, the nearest structural chapterN anchor (the
        same index L2/R2 chapter-nav already uses) to produce labels like
        "Psalms 91" for Bible content, or the article title for
        magazines. Verified against the real file.
    (3) Feature: wired up D-PAD LEFT/RIGHT to actually do fine (always
        1-step) link navigation, matching what the top-of-file docstring
        already claimed but was never implemented (LEFT/RIGHT previously
        just duplicated line-scrolling). Gives a natural way to step
        across a link grid like the Psalms chapter-number list without
        the coarser UP/DOWN (row-order) or Y-toggled 10x jump.
  v0.1.3 -- Feature: Y now doubles as a fast-scroll TOGGLE inside the
    reader itself (not just the Chapters/Bookmarks screens). Pressing Y
    turns on 10x D-pad movement -- both for stepping through inline
    links (e.g. a page full of Psalms chapter links) and for plain line
    scrolling -- and pressing Y again turns it back off. State is shown
    next to the page-progress %% as "[FAST]" so it's never a silent
    toggle. No held-button/repeat infrastructure exists in the event
    loop (SDL_JOYHATMOTION only fires on directional change, not on
    hold), so a toggle was used instead of a hold-modifier -- simpler
    and more reliable given the current single-shot event dispatch.
  v0.1.2 -- Feature: fast-scroll for long Chapters/Bookmarks lists (e.g.
    the NWT Bible epub's ~1,190 chapter anchors). Y now jumps +10 in the
    TOC/Bookmarks screens; L/R jump -10/+10 there too (previously unused
    on those screens). X is now the sole menu-open button in the reader
    (Y freed up so it isn't double-booked with the new jump-10 action).
  v0.1.1 -- Fix: crash-log/excepthook install was happening AFTER the
    `from epub_engine import ...` / `from mini_jpeg import decode_jpeg`
    imports, so any import-time failure in those modules (syntax error,
    missing symbol, stdlib behaving differently on the device's Python
    build) died silently to stderr with nothing written to
    /tmp/picoreader_crash.log -- muOS has no way to show/save that.
    Same class of bug as Pico8FavsSorter Fix 11/13. Fixed by moving
    _boot_log/_excepthook installation to the top of the file, before
    those imports, and wrapping the imports (plus the DATA_DIR/
    LIBRARY_DIR os.makedirs calls) in their own try/except that logs
    and exits cleanly instead of crashing bare. Also added
    threading.excepthook (a separate hook from sys.excepthook on
    Python 3.8+) so a crash inside ImageLoader's background worker
    thread reaches the crash log too, and wrapped App(renderer)
    construction in main() with explicit crash logging for a clear,
    labelled log entry if init itself fails.
"""

import ctypes
import ctypes.util
import math
import os
import sys
import json
import time
import threading
import bisect
import hashlib
import glob
import queue
import itertools
from collections import OrderedDict

# ============================================================
# Crash logging -- MUST be installed before anything that can fail
# (module imports, path setup, etc.) or a boot-time failure dies
# silently to stderr with nothing for muOS to show/save. This bit
# muOS Favs Sorter (Fix 11/13) and cost real debugging time -- see
# note below on why the epub_engine/mini_jpeg imports were moved
# below this block instead of staying up with the stdlib imports.
# ============================================================
CRASH_LOG = "/tmp/picoreader_crash.log"


def _boot_log(msg):
    try:
        with open(CRASH_LOG, "a") as f:
            f.write(msg)
    except Exception:
        pass


def _excepthook(exc_type, exc_value, tb):
    import traceback
    _boot_log("\n--- UNCAUGHT EXCEPTION ---\n")
    _boot_log("".join(traceback.format_exception(exc_type, exc_value, tb)))
    _boot_log("--- END ---\n")


sys.excepthook = _excepthook

# Also catch exceptions raised on background threads (ImageLoader's worker
# thread etc.) -- threading.excepthook is a SEPARATE hook from sys.excepthook
# on Python 3.8+, so without this, a thread-level crash would never reach
# picoreader_crash.log even though sys.excepthook is installed above.
def _thread_excepthook(args):
    import traceback
    _boot_log("\n--- UNCAUGHT THREAD EXCEPTION ---\n")
    _boot_log(f"thread: {args.thread.name}\n")
    _boot_log("".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)))
    _boot_log("--- END ---\n")


threading.excepthook = _thread_excepthook

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from epub_engine import EpubDocument, ReaderState, TocEntry
    from mini_jpeg import decode_jpeg, peek_jpeg_size
except Exception:
    import traceback
    _boot_log("\n--- IMPORT FAILURE (epub_engine / mini_jpeg) ---\n")
    _boot_log(traceback.format_exc())
    _boot_log("--- END ---\n")
    sys.exit(1)

# ============================================================
# Optional downloader plugins -- unlike epub_engine/mini_jpeg above,
# these are genuinely OPTIONAL: the app must work identically whether
# zero, one, or both files are present. Each is a self-contained module
# (see gutenberg_fetch.py's docstring for the plugin contract every
# downloader module must implement: PLUGIN_NAME, list_items(), download()).
# A plugin failing to import (missing file, or a bug inside it) is
# swallowed and logged, never fatal -- the Library/Storage screens check
# DOWNLOAD_PLUGINS and simply don't show a "Download Books" option if
# it's empty, rather than crashing or showing a broken menu item.
DOWNLOAD_PLUGINS = []
for _plugin_mod_name in ("gutenberg_fetch", "jw_fetch"):
    try:
        _mod = __import__(_plugin_mod_name)
        DOWNLOAD_PLUGINS.append(_mod)
    except Exception:
        _boot_log(f"optional plugin '{_plugin_mod_name}' not loaded (this is fine if the "
                   f"file isn't present): {sys.exc_info()[1]}\n")

# ============================================================
# Paths
# ============================================================
APP_DIR = os.path.dirname(os.path.abspath(__file__))
LIBRARY_DIR = os.environ.get("EPUB_LIBRARY_DIR", os.path.join(APP_DIR, "library"))
DATA_DIR = os.path.join(APP_DIR, "data")
BOOKMARKS_PATH = os.path.join(DATA_DIR, "bookmarks.json")
SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")
LIBRARY_CACHE_PATH = os.path.join(DATA_DIR, "library_cache.json")
PINNED_PATH = os.path.join(DATA_DIR, "pinned.json")
ANCHOR_CACHE_DIR = os.path.join(DATA_DIR, "anchor_cache")
IMG_CACHE_DIR = os.path.join(DATA_DIR, "img_cache")
# Deliberately a sibling of library/ and data/, not buried inside data/ --
# the whole point of a backup is being easy to find and copy off the
# device (SD card swap, USB, another file manager) without having to know
# it's hiding inside the app's internal data folder.
BACKUP_DIR = os.path.join(APP_DIR, "backups")
# v0.1.63: unlike CRASH_LOG (/tmp -- wiped on reboot, only useful over SSH
# same session), this lives in DATA_DIR so it survives reboots and can be
# pulled off the SD card later. Records non-fatal render oddities (e.g. a
# spine page that parsed to zero text/images -- see log_render_issue()) --
# things that aren't crashes but are worth knowing about after the fact.
RENDER_LOG_PATH = os.path.join(DATA_DIR, "render_issues.log")


def book_id(book_path):
    """Stable per-book identifier, deterministic from the path alone (so
    it can be recomputed even for a book that's since been deleted, e.g.
    to find and purge its orphaned cache files). Same derivation the
    anchor cache already used, now also reused to namespace image-cache
    keys -- without this, two different books that happen to share an
    internal image path (common in EPUB packaging, e.g. both using
    "OEBPS/images/cover.jpg") would silently collide in the shared
    ImageLoader and show each other's cached image."""
    return hashlib.sha1(book_path.encode()).hexdigest()[:16]

try:
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(LIBRARY_DIR, exist_ok=True)
except Exception:
    import traceback
    _boot_log("\n--- FAILED TO CREATE DATA/LIBRARY DIRS ---\n")
    _boot_log(traceback.format_exc())
    _boot_log("--- END ---\n")
    sys.exit(1)

# ============================================================
# SDL2 ctypes bindings (minimal, matches Pico8FavsSorter conventions)
# ============================================================
SDL_INIT_VIDEO = 0x00000020
SDL_INIT_JOYSTICK = 0x00000200
SDL_WINDOWPOS_CENTERED = 0x2FFF0000

SDL_QUIT_EV = 0x100
SDL_KEYDOWN_EV = 0x300
SDL_JOYHATMOTION_EV = 0x602
SDL_JOYBUTTONDOWN_EV = 0x603

SDL_HAT_UP = 1; SDL_HAT_RIGHT = 2; SDL_HAT_DOWN = 4; SDL_HAT_LEFT = 8; SDL_HAT_CENTERED = 0

SDLK_UP = 1073741906; SDLK_DOWN = 1073741905
SDLK_LEFT = 1073741904; SDLK_RIGHT = 1073741903
SDLK_RETURN = 13; SDLK_ESCAPE = 27; SDLK_BACKSPACE = 8
SDLK_TAB = 9; SDLK_EQUALS = 61; SDLK_MINUS = 45

def _load_lib(names, explicit_paths):
    for n in names:
        try:
            found = ctypes.util.find_library(n)
            if found:
                return ctypes.CDLL(found)
        except OSError:
            pass
    for p in explicit_paths:
        if os.path.exists(p):
            try:
                return ctypes.CDLL(p)
            except OSError:
                pass
    return None


SDL = _load_lib(
    ["SDL2"],
    ["/usr/lib/x86_64-linux-gnu/libSDL2-2.0.so.0", "/usr/lib/libSDL2-2.0.so.0",
     "libSDL2.so", "libSDL2-2.0.so.0"],
)
if SDL is None:
    _boot_log("FATAL: could not load libSDL2\n")
    sys.exit(1)

TTF = _load_lib(
    ["SDL2_ttf"],
    ["/usr/lib/x86_64-linux-gnu/libSDL2_ttf-2.0.so.0", "/usr/lib/libSDL2_ttf-2.0.so.0",
     "libSDL2_ttf.so", "libSDL2_ttf-2.0.so.0"],
)
if TTF is None:
    _boot_log("FATAL: could not load libSDL2_ttf\n")
    sys.exit(1)


class Color(ctypes.Structure):
    _fields_ = [("r", ctypes.c_ubyte), ("g", ctypes.c_ubyte),
                ("b", ctypes.c_ubyte), ("a", ctypes.c_ubyte)]


class Rect(ctypes.Structure):
    _fields_ = [("x", ctypes.c_int), ("y", ctypes.c_int),
                ("w", ctypes.c_int), ("h", ctypes.c_int)]


SDL.SDL_CreateWindow.restype = ctypes.c_void_p
SDL.SDL_CreateRenderer.restype = ctypes.c_void_p
SDL.SDL_GetError.restype = ctypes.c_char_p
TTF.TTF_Init.restype = ctypes.c_int
TTF.TTF_OpenFont.restype = ctypes.c_void_p
TTF.TTF_OpenFont.argtypes = [ctypes.c_char_p, ctypes.c_int]
TTF.TTF_RenderUTF8_Blended.restype = ctypes.c_void_p
TTF.TTF_RenderUTF8_Blended.argtypes = [ctypes.c_void_p, ctypes.c_char_p, Color]
TTF.TTF_SizeUTF8.argtypes = [ctypes.c_void_p, ctypes.c_char_p,
                              ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)]
TTF.TTF_SizeUTF8.restype = ctypes.c_int
TTF.TTF_CloseFont.argtypes = [ctypes.c_void_p]
TTF.TTF_FontHeight.restype = ctypes.c_int
TTF.TTF_FontHeight.argtypes = [ctypes.c_void_p]
SDL.SDL_CreateRGBSurfaceFrom.restype = ctypes.c_void_p
SDL.SDL_CreateRGBSurfaceFrom.argtypes = [
    ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32,
]
SDL.SDL_CreateTextureFromSurface.restype = ctypes.c_void_p
HAS_TTF = TTF.TTF_Init() == 0
_boot_log(f"TTF_Init: {'OK' if HAS_TTF else 'FAILED -- ' + SDL.SDL_GetError().decode('utf-8', errors='replace')}\n")

FONT_PATHS = [
    # Bundled first now -- per explicit request to bundle rather than
    # depend on system paths "to prevent issues". Justified by real
    # device evidence (not assumption): a file-manager screenshot of this
    # exact device showed /usr/share/fonts/truetype/dejavu/ completely
    # empty (just .uuid) -- DejaVu was NEVER actually present on this
    # hardware in either Sans or Mono form, meaning every earlier
    # DejaVu-first FONT_PATHS ordering was silently falling through to
    # later entries the whole time. Liberation Sans (proportional, not
    # Mono) confirmed present on-device and is the actual look the person
    # asked for, matching the original v0.1.0-era screenshots they liked.
    os.path.join(APP_DIR, "assets", "font.ttf"),
    "/usr/share/fonts/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/liberation/LiberationMono-Regular.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/freefont/FreeMono.ttf",
]
FONT_PATH = next((p for p in FONT_PATHS if os.path.exists(p)), None)

# Bold/Italic/BoldItalic style variants (v0.1.35) -- same bundled-first,
# system-fallback pattern as FONT_PATHS above, each ending in None so
# FontManager can fall back to the plain regular font (FONT_PATH) rather
# than fail outright if a style file is ever missing (matches the
# optional-plugin philosophy elsewhere in this app: degrade gracefully,
# never crash, over a missing-but-non-essential asset).
FONT_PATHS_BOLD = [
    os.path.join(APP_DIR, "assets", "font-bold.ttf"),
    "/usr/share/fonts/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]
FONT_PATHS_ITALIC = [
    os.path.join(APP_DIR, "assets", "font-italic.ttf"),
    "/usr/share/fonts/liberation/LiberationSans-Italic.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Italic.ttf",
]
FONT_PATHS_BOLDITALIC = [
    os.path.join(APP_DIR, "assets", "font-bolditalic.ttf"),
    "/usr/share/fonts/liberation/LiberationSans-BoldItalic.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-BoldItalic.ttf",
]
FONT_PATH_BOLD = next((p for p in FONT_PATHS_BOLD if os.path.exists(p)), None)
FONT_PATH_ITALIC = next((p for p in FONT_PATHS_ITALIC if os.path.exists(p)), None)
FONT_PATH_BOLDITALIC = next((p for p in FONT_PATHS_BOLDITALIC if os.path.exists(p)), None)
_boot_log(f"FONT_PATH_BOLD resolved to: {FONT_PATH_BOLD!r}\n")
_boot_log(f"FONT_PATH_ITALIC resolved to: {FONT_PATH_ITALIC!r}\n")
_boot_log(f"FONT_PATH_BOLDITALIC resolved to: {FONT_PATH_BOLDITALIC!r}\n")

# Logged unconditionally (not just on failure) -- a prior version of this
# code only logged the failure case, which meant a report of "blank text,
# but no crash log entry at all" gave no way to tell whether FONT_PATH had
# resolved to something that LOOKED valid but still failed downstream, vs.
# some other cause entirely. This line exists specifically so the next
# report includes real evidence instead of another guess.
_boot_log(f"FONT_PATH resolved to: {FONT_PATH!r} (checked {FONT_PATHS})\n")
if FONT_PATH is None:
    _boot_log(
        "\n--- NO FONT FOUND ---\n"
        "None of the checked paths exist. Text rendering will silently "
        "fail (render_text() returns early when font is None) -- but this "
        "is only ONE possible cause of blank text; a font that opens "
        "successfully can still fail to render visibly for other reasons "
        "(see the TTF_OpenFont / render_text diagnostics below/elsewhere "
        "in this log for what actually happened on this run).\n"
        "--- END ---\n"
    )

# ============================================================
# Screen size / scaling (matches sorter's 720x720 reference-scale pattern)
# ============================================================
SW, SH = 720, 720
_SX = SW / 720.0
_SY = SH / 720.0


def _sx(n): return max(1, int(n * _SX))
def _sy(n): return max(1, int(n * _SY))


# ============================================================
# Colors / Themes (v0.1.66)
# ============================================================
# THEMES holds full palettes; the COL_* names below stay module-level
# globals exactly as before (every draw call in this file reads them
# by name), so apply_theme() just reassigns those globals in place --
# no call site anywhere else in the file needs to change.
#
# Dim Warm / Deep Amber / Red Shift are for bedtime reading: each
# pushes the palette progressively further from blue-enriched light
# toward warm/amber/red tones. Short-wavelength (blue) light in the
# evening is the specific mechanism that suppresses melatonin and
# delays the circadian clock; amber/red-shifted light reduces that
# suppression. Red Shift has essentially no blue channel, matching
# "red light at night" approaches used to preserve night vision/melatonin.
THEMES = [
    {
        "name": "Default",
        "bg": (18, 18, 22), "panel": (28, 28, 34), "text": (225, 225, 230),
        "dim": (140, 140, 150), "link": (61, 125, 118), "link_sel": (255, 210, 90),
        "hint_bg": (10, 10, 13), "hint_text": (180, 180, 190),
        "accent": (95, 168, 156), "menu_sel_bg": (45, 45, 55), "warning": (230, 90, 90),
    },
    {
        # ~2700K-ish warm gray/amber -- gentle general night reading,
        # not as aggressive as the two below.
        "name": "Dim Warm",
        "bg": (26, 20, 16), "panel": (36, 29, 23), "text": (201, 184, 150),
        "dim": (140, 120, 95), "link": (217, 148, 74), "link_sel": (240, 190, 120),
        "hint_bg": (16, 12, 9), "hint_text": (170, 148, 115),
        "accent": (201, 140, 80), "menu_sel_bg": (55, 43, 32), "warning": (216, 110, 80),
    },
    {
        # Strong blue-light reduction, sepia/candlelight feel.
        "name": "Deep Amber",
        "bg": (20, 16, 12), "panel": (30, 23, 16), "text": (184, 122, 61),
        "dim": (130, 92, 55), "link": (201, 120, 46), "link_sel": (230, 165, 80),
        "hint_bg": (12, 9, 6), "hint_text": (150, 105, 60),
        "accent": (201, 120, 46), "menu_sel_bg": (48, 36, 24), "warning": (200, 100, 70),
    },
    {
        # Near-zero blue channel -- the most aggressive option, meant
        # for right before sleep.
        "name": "Red Shift",
        "bg": (16, 8, 8), "panel": (24, 12, 12), "text": (176, 90, 74),
        "dim": (120, 60, 50), "link": (196, 90, 70), "link_sel": (214, 120, 90),
        "hint_bg": (10, 5, 5), "hint_text": (140, 70, 58),
        "accent": (140, 58, 46), "menu_sel_bg": (40, 18, 18), "warning": (200, 80, 60),
    },
    {
        # Kaleb's requested palette: dark background kept (his explicit
        # ask), accent colors drawn from fan-made BMO/Adventure Time
        # palette references (Lospec "Beemo", ColorsWall "bmo design") --
        # no official studio palette exists, so treat as close
        # approximations, not exact brand colors.
        "name": "Adventure",
        "bg": (14, 14, 16), "panel": (26, 26, 30), "text": (180, 200, 190),
        "dim": (140, 145, 142), "link": (68, 176, 151), "link_sel": (255, 236, 71),
        "hint_bg": (8, 9, 9), "hint_text": (170, 178, 172),
        "accent": (175, 245, 191), "menu_sel_bg": (40, 44, 42), "warning": (242, 5, 83),
    },
]

COL_BG = COL_PANEL = COL_TEXT = COL_DIM = None
COL_LINK = COL_LINK_SEL = COL_HINT_BG = COL_HINT_TEXT = None
COL_ACCENT = COL_MENU_SEL_BG = COL_WARNING = None

THEME_INDEX = 0


def apply_theme(index):
    """Rebinds the module-level COL_* globals to the given THEMES[index]
    palette. Every draw_* function reads COL_BG/COL_TEXT/etc. as plain
    module globals, so this is the ONLY place a theme change needs to
    touch -- no per-screen draw code changes when adding a new theme,
    just add an entry to THEMES above."""
    global THEME_INDEX, COL_BG, COL_PANEL, COL_TEXT, COL_DIM, COL_LINK
    global COL_LINK_SEL, COL_HINT_BG, COL_HINT_TEXT, COL_ACCENT
    global COL_MENU_SEL_BG, COL_WARNING
    index = max(0, min(len(THEMES) - 1, index))
    t = THEMES[index]
    THEME_INDEX = index
    COL_BG = Color(*t["bg"], 255)
    COL_PANEL = Color(*t["panel"], 255)
    COL_TEXT = Color(*t["text"], 255)
    COL_DIM = Color(*t["dim"], 255)
    COL_LINK = Color(*t["link"], 255)
    COL_LINK_SEL = Color(*t["link_sel"], 255)
    COL_HINT_BG = Color(*t["hint_bg"], 255)
    COL_HINT_TEXT = Color(*t["hint_text"], 255)
    COL_ACCENT = Color(*t["accent"], 255)
    COL_MENU_SEL_BG = Color(*t["menu_sel_bg"], 255)
    COL_WARNING = Color(*t["warning"], 255)


apply_theme(0)  # Default at import time; App.__init__ re-applies the
                 # saved choice from settings.json once load_settings()
                 # is defined below.
_boot_log(f"COL_TEXT=({COL_TEXT.r},{COL_TEXT.g},{COL_TEXT.b},{COL_TEXT.a}) "
          f"COL_BG=({COL_BG.r},{COL_BG.g},{COL_BG.b},{COL_BG.a})\n")

# ============================================================
# Joystick button map -- loaded from muOS sdl_map same as sorter
# ============================================================
def _load_sdl_map():
    paths = [
        "/opt/muos/device/current/config/board/sdl_map",
        "/usr/lib/muos/device/current/config/board/sdl_map",
    ]
    result = {}
    for p in paths:
        if os.path.exists(p):
            try:
                with open(p) as f:
                    content = f.read()
                for entry in content.split(","):
                    if ":" in entry:
                        k, v = entry.split(":", 1)
                        k = k.strip().lower()
                        v = v.strip()
                        if v.startswith("b"):
                            try:
                                result[k] = int(v[1:])
                            except ValueError:
                                pass
            except Exception:
                pass
            break
    return result


_sdl_map = _load_sdl_map()
JOY_A = _sdl_map.get("a", 3)
JOY_B = _sdl_map.get("b", 4)
JOY_Y = _sdl_map.get("y", 5)
JOY_X = _sdl_map.get("x", 6)
JOY_L = _sdl_map.get("leftshoulder", 7)
JOY_R = _sdl_map.get("rightshoulder", 8)
JOY_BACK = _sdl_map.get("back", 9)
JOY_START = _sdl_map.get("start", 10)
JOY_L2 = _sdl_map.get("lefttrigger", 13)
JOY_R2 = _sdl_map.get("righttrigger", 14)


# ============================================================
# Font manager -- supports adjustable size (feature request)
# ============================================================
class FontManager:
    SIZE_STEPS = [14, 16, 18, 21, 24, 28, 32]
    # v0.1.50: UI chrome (menus, hint bar, library/TOC/bookmarks/storage
    # screens, headings) now scales with the SAME "Font Size +/-" setting
    # as reading text -- Kaleb wants one global text-size control, not a
    # separate reading-only one. This REVERSES the earlier UI_STEP=18pt-
    # fixed approach (which existed specifically to stop the hint bar and
    # popup menu overflowing at large reading sizes). Overflow is now
    # handled at the draw site instead of by capping the font:
    #   - hint bar (draw_hint/hint_height()) wraps to up to 2 lines and
    #     grows vertically to fit, rather than clipping off-screen.
    #   - popup MENU/CHAPTERS/etc. lists were already width-safe at 32pt
    #     (largest SIZE_STEPS entry) in testing; revisit if a longer
    #     label is ever added.
    UI_STEP = 18  # no longer used for ui_* fonts; kept as fallback constant
                  # for any future fixed-size need

    def __init__(self):
        self._cache = {}
        settings = load_settings()
        self.size_index = settings.get("font_size_index", 2)  # default 18pt

    # style is one of "regular", "bold", "italic", "bolditalic" -- picks
    # which FONT_PATH_* to open. Falls back to the plain regular font
    # (FONT_PATH) if that style's file wasn't found at startup, rather
    # than failing -- a missing bold/italic file should degrade to
    # regular-looking text, never crash the app or blank out reading text.
    _STYLE_PATHS = None  # set lazily below to avoid referencing FONT_PATH_*
                          # globals before they're guaranteed to exist

    def _style_path(self, style):
        if FontManager._STYLE_PATHS is None:
            FontManager._STYLE_PATHS = {
                "regular": FONT_PATH,
                "bold": FONT_PATH_BOLD or FONT_PATH,
                "italic": FONT_PATH_ITALIC or FONT_PATH,
                "bolditalic": FONT_PATH_BOLDITALIC or FONT_PATH,
            }
        return FontManager._STYLE_PATHS.get(style, FONT_PATH)

    def _get(self, pt, style="regular"):
        pt = _sy(pt)
        key = (pt, style)
        if key not in self._cache:
            path = self._style_path(style)
            if path:
                f = TTF.TTF_OpenFont(path.encode(), pt)
                if not f:
                    _boot_log(f"TTF_OpenFont failed for {path} ({style}) at {pt}pt: "
                              f"{SDL.SDL_GetError().decode('utf-8', errors='replace')}\n")
                    # fall back to regular at this size rather than caching
                    # a hard failure for this style forever
                    if style != "regular":
                        f = self._get(pt, "regular")
                self._cache[key] = f
            else:
                self._cache[key] = None
        return self._cache[key]

    @property
    def body(self):
        return self._get(self.SIZE_STEPS[self.size_index])

    @property
    def body_bold(self):
        return self._get(self.SIZE_STEPS[self.size_index], "bold")

    @property
    def body_italic(self):
        return self._get(self.SIZE_STEPS[self.size_index], "italic")

    @property
    def body_bolditalic(self):
        return self._get(self.SIZE_STEPS[self.size_index], "bolditalic")

    def body_styled(self, bold, italic):
        """Convenience: pick the right body-size font handle for a given
        (bold, italic) combination -- what the styled-run renderer
        actually calls per run rather than checking flags itself."""
        if bold and italic:
            return self.body_bolditalic
        if bold:
            return self.body_bold
        if italic:
            return self.body_italic
        return self.body

    @property
    def small(self):
        return self._get(max(11, self.SIZE_STEPS[self.size_index] - 4))

    @property
    def heading(self):
        return self._get(self.SIZE_STEPS[self.size_index] + 6)

    # -------- UI chrome fonts (v0.1.50: now scale with global size_index,
    # same as body/small/heading above -- kept as separate properties
    # rather than aliasing body/small/heading so call sites and any
    # future re-split stay simple) --------
    @property
    def ui_body(self):
        return self.body

    @property
    def ui_small(self):
        return self.small

    @property
    def ui_heading(self):
        return self.heading

    def bigger(self):
        self.size_index = min(len(self.SIZE_STEPS) - 1, self.size_index + 1)
        save_settings({"font_size_index": self.size_index})

    def smaller(self):
        self.size_index = max(0, self.size_index - 1)
        save_settings({"font_size_index": self.size_index})


def load_settings():
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH) as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def log_render_issue(book_path, file_path, detail):
    """Appends one line to RENDER_LOG_PATH for a non-fatal render oddity
    (currently: a spine page that parsed to zero text AND zero images --
    see the blank-cover bug this was added for, v0.1.62/63). Best-effort:
    a logging failure must never interrupt reading, so every error is
    swallowed silently, matching _boot_log()'s pattern above."""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        book_name = os.path.basename(book_path) if book_path else "?"
        with open(RENDER_LOG_PATH, "a") as f:
            f.write(f"[{ts}] {book_name} :: {file_path} -- {detail}\n")
    except Exception:
        pass


def save_settings(patch):
    s = load_settings()
    s.update(patch)
    try:
        with open(SETTINGS_PATH, "w") as f:
            json.dump(s, f)
    except Exception:
        pass


# ============================================================
# Bookmarks -- per-book list, stored in one JSON file
# ============================================================
MAX_BOOKMARKS_PER_BOOK = 20  # not counting the internal __lastpos__ marker


def load_bookmarks():
    if os.path.exists(BOOKMARKS_PATH):
        try:
            with open(BOOKMARKS_PATH) as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_bookmarks(data):
    try:
        with open(BOOKMARKS_PATH, "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def backup_bookmarks():
    """Writes a timestamped snapshot of the full bookmarks.json (every
    book) to BACKUP_DIR. Returns the backup's filename, or None if there
    was nothing to back up or the write failed. Keeps only the most
    recent 10 backups -- otherwise this would be one more thing that
    grows on the SD card forever with nothing to bound it."""
    data = load_bookmarks()
    if not data:
        return None
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        fname = f"bookmarks_backup_{time.strftime('%Y%m%d_%H%M%S')}.json"
        path = os.path.join(BACKUP_DIR, fname)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        _boot_log(f"bookmark backup failed: {e}\n")
        return None

    # trim to the 10 most recent
    try:
        backups = sorted(
            (f for f in os.listdir(BACKUP_DIR) if f.startswith("bookmarks_backup_")),
            reverse=True)
        for old in backups[10:]:
            try:
                os.remove(os.path.join(BACKUP_DIR, old))
            except OSError:
                pass
    except OSError:
        pass
    return fname


def list_bookmark_backups():
    """Newest-first list of backup filenames."""
    if not os.path.isdir(BACKUP_DIR):
        return []
    return sorted(
        (f for f in os.listdir(BACKUP_DIR) if f.startswith("bookmarks_backup_")),
        reverse=True)


def restore_latest_backup():
    """Merges the most recent backup into the live bookmarks.json -- does
    NOT simply overwrite, since a stale backup blindly replacing live
    data could lose bookmarks made since that backup was taken. Per book,
    per (file, anchor) entry: if both a live and backed-up version exist,
    keep whichever has the later timestamp; otherwise add it. Still
    respects MAX_BOOKMARKS_PER_BOOK by keeping only the most recent
    entries per book after merging (__lastpos__ markers are excluded
    from that cap, same as everywhere else).
    Returns (backup_filename, books_touched, entries_added) or
    (None, 0, 0) if there's no backup to restore."""
    backups = list_bookmark_backups()
    if not backups:
        return None, 0, 0
    latest = backups[0]
    try:
        with open(os.path.join(BACKUP_DIR, latest)) as f:
            backup_data = json.load(f)
    except Exception as e:
        _boot_log(f"bookmark restore failed to read {latest}: {e}\n")
        return None, 0, 0

    live_data = load_bookmarks()
    books_touched = 0
    entries_added = 0

    for book_path, backup_entries in backup_data.items():
        live_entries = live_data.setdefault(book_path, [])
        touched_this_book = False

        for be in backup_entries:
            match = None
            for le in live_entries:
                if le.get("file") == be.get("file") and le.get("anchor") == be.get("anchor") \
                        and le.get("label") == be.get("label"):
                    match = le
                    break
            if match is None:
                live_entries.append(dict(be))
                entries_added += 1
                touched_this_book = True
            elif be.get("ts", 0) > match.get("ts", 0):
                match.update(be)
                touched_this_book = True

        # re-cap at MAX_BOOKMARKS_PER_BOOK real entries, keeping the most
        # recent -- the __lastpos__ marker doesn't count toward this
        real = [e for e in live_entries if e.get("label") != "__lastpos__"]
        lastpos = [e for e in live_entries if e.get("label") == "__lastpos__"]
        if len(real) > MAX_BOOKMARKS_PER_BOOK:
            real.sort(key=lambda e: e.get("ts", 0), reverse=True)
            real = real[:MAX_BOOKMARKS_PER_BOOK]
        live_entries[:] = lastpos + real

        if touched_this_book:
            books_touched += 1

    save_bookmarks(live_data)
    return latest, books_touched, entries_added


def add_bookmark(book_path, file_path, anchor, label, char_off=None):
    """Returns 'added', 'updated' (an existing bookmark at the same
    file+anchor+char_off was refreshed instead of creating a duplicate),
    or 'limit' (already at MAX_BOOKMARKS_PER_BOOK real bookmarks and this
    would have been a new one, not a duplicate update).

    v0.1.39: duplicate matching now includes char_off, not just anchor.
    Before precise-position bookmarks, anchor was almost always None for
    anything bookmarked after scrolling (see ReaderState.current_char_off
    docstring) -- so two bookmarks in the same chapter at different
    paragraphs both matched on (file, anchor=None) and the second one
    silently overwrote the first instead of adding a new entry. Matching
    on char_off too restores the "one bookmark per distinct spot" this
    feature actually needs; two bookmarks placed extremely close together
    (within CHAR_OFF_DUP_TOLERANCE) still collapse to one, so START'd
    twice at nearly the same spot doesn't clutter the list."""
    data = load_bookmarks()
    entries = data.setdefault(book_path, [])

    CHAR_OFF_DUP_TOLERANCE = 40  # ~ half a line; avoids near-duplicate clutter
    for e in entries:
        if e.get("label") == "__lastpos__":
            continue
        if e.get("file") != file_path:
            continue
        same_anchor = e.get("anchor") == anchor
        e_off = e.get("char_off")
        same_off = (
            (e_off is None and char_off is None) or
            (e_off is not None and char_off is not None
             and abs(e_off - char_off) <= CHAR_OFF_DUP_TOLERANCE)
        )
        if same_anchor and same_off:
            e["label"] = label
            e["ts"] = time.time()
            e["char_off"] = char_off
            save_bookmarks(data)
            return "updated"

    real_count = sum(1 for e in entries if e.get("label") != "__lastpos__")
    if real_count >= MAX_BOOKMARKS_PER_BOOK:
        return "limit"

    entries.append({
        "file": file_path, "anchor": anchor, "label": label,
        "ts": time.time(), "char_off": char_off,
    })
    save_bookmarks(data)
    return "added"


def delete_bookmark(book_path, file_path, anchor, ts):
    """Removes one specific bookmark, matched by (file, anchor, ts) --
    ts makes this unambiguous even if two bookmarks happen to share a
    label. Returns True if something was actually removed."""
    data = load_bookmarks()
    entries = data.get(book_path, [])
    before = len(entries)
    entries[:] = [
        e for e in entries
        if not (e.get("file") == file_path and e.get("anchor") == anchor and e.get("ts") == ts)
    ]
    if len(entries) != before:
        save_bookmarks(data)
        return True
    return False


def get_bookmarks(book_path):
    return load_bookmarks().get(book_path, [])


def get_last_position(book_path):
    data = load_bookmarks()
    entries = data.get(book_path, [])
    for e in reversed(entries):
        if e.get("label") == "__lastpos__":
            return e
    return None


def save_last_position(book_path, file_path, anchor, char_off=None):
    data = load_bookmarks()
    entries = data.setdefault(book_path, [])
    entries[:] = [e for e in entries if e.get("label") != "__lastpos__"]
    entries.append({"file": file_path, "anchor": anchor, "char_off": char_off,
                     "label": "__lastpos__", "ts": time.time()})
    save_bookmarks(data)


# ============================================================
# Storage management -- cache size, orphaned-bookmark cleanup, manual clear
# ============================================================
def image_cache_size_bytes():
    total = 0
    if os.path.isdir(IMG_CACHE_DIR):
        for fname in os.listdir(IMG_CACHE_DIR):
            try:
                total += os.path.getsize(os.path.join(IMG_CACHE_DIR, fname))
            except OSError:
                pass
    return total


def book_cache_size_bytes(book_id_value):
    """Bytes used in the on-disk image cache by ONE book. Cache filenames
    are already namespaced "{book_id}__{...}" (see App._img_key), so this
    is a simple prefix match over the same flat IMG_CACHE_DIR -- no
    separate per-book folder needed. Used for the Storage screen's
    per-book breakdown and (feeding into book deletion) to report how
    much space a book's cache will free."""
    total = 0
    prefix = f"{book_id_value}__"
    if os.path.isdir(IMG_CACHE_DIR):
        for fname in os.listdir(IMG_CACHE_DIR):
            if fname.startswith(prefix):
                try:
                    total += os.path.getsize(os.path.join(IMG_CACHE_DIR, fname))
                except OSError:
                    pass
    return total


def delete_book_cache(book_id_value):
    """Deletes every on-disk cache file belonging to ONE book (same
    prefix-match approach as book_cache_size_bytes). Returns bytes freed.
    Does not touch the anchor cache or bookmarks -- callers that are
    actually deleting a book should also remove ANCHOR_CACHE_DIR's
    {book_id}.json alongside this."""
    freed = 0
    prefix = f"{book_id_value}__"
    if os.path.isdir(IMG_CACHE_DIR):
        for fname in os.listdir(IMG_CACHE_DIR):
            if fname.startswith(prefix):
                path = os.path.join(IMG_CACHE_DIR, fname)
                try:
                    freed += os.path.getsize(path)
                    os.remove(path)
                except OSError:
                    pass
    return freed


def format_bytes(n):
    if n < 1024 * 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


def orphaned_bookmark_book_paths():
    """Book paths in bookmarks.json that no longer correspond to a file
    actually present in the library -- left behind after deleting a book
    (deliberately NOT auto-purged alongside the image/anchor caches,
    since bookmarks are the person's own data, not disposable cache)."""
    data = load_bookmarks()
    current_paths = {b["path"] for b in scan_library()}
    return [p for p in data.keys() if p not in current_paths]


def clean_orphaned_bookmarks():
    """Removes all bookmark entries for books no longer in the library.
    Returns the number of books' worth of entries removed."""
    orphans = orphaned_bookmark_book_paths()
    if not orphans:
        return 0
    data = load_bookmarks()
    for p in orphans:
        del data[p]
    save_bookmarks(data)
    return len(orphans)


def clear_image_cache():
    """Deletes every file in the on-disk image cache. Safe at any time --
    anything still needed gets redecoded and re-cached on next view.
    Returns the number of bytes freed."""
    freed = 0
    if os.path.isdir(IMG_CACHE_DIR):
        for fname in os.listdir(IMG_CACHE_DIR):
            path = os.path.join(IMG_CACHE_DIR, fname)
            try:
                freed += os.path.getsize(path)
                os.remove(path)
            except OSError:
                pass
    return freed


# ============================================================
# Image decode worker -- background thread + disk cache, keeps UI responsive
# ============================================================
class ImageLoader:
    THUMB_N = 1   # DC-only, near-instant, ~1/8 resolution
    FULL_N = 4    # fallback full-res scale when the header can't be peeked
                  # (corrupt/truncated data) -- otherwise _pick_scale_n()
                  # below chooses per-image based on its actual dimensions.
    MAX_CACHE_BYTES = 500 * 1024 * 1024  # 500MB cap on the on-disk image cache
                                          # (raised from 200MB v0.1.51 -- 32GB SD)
    MAX_INMEMORY_IMAGES = 80  # ~80 decoded images kept in RAM at once (at
                               # typical real sizes from _pick_scale_n, that's
                               # roughly 20-32MB) -- raised from 60 v0.1.51.
                               # Unbounded before v0.1.48.

    # Target size used only to PICK a decode resolution -- deliberately
    # smaller than the actual on-screen image box (SW-40 wide, up to
    # IMG_BOX_ROWS tall) in draw_reader(). This trades some sharpness
    # (the decoded image gets modestly upscaled to fill the box) for real
    # decode speed, per direct feedback that large photos were taking too
    # long. Real numbers from a representative Watchtower issue (1200-
    # 1800px wide source photos): at the old fixed default (scale_n=4,
    # ~627ms per image on this dev machine -- correspondingly slower on
    # the actual ARM handheld) every photo also paid for a separate
    # thumb-stage decode first (~280ms) even though the full stage
    # followed immediately after in the same worker pass. With the
    # 480x360 target that followed, real magazine photos landed at
    # scale_n 2-4 and skipped the thumb stage entirely (see the <= 4
    # check in _process()), cutting per-image decode time roughly in
    # half. Shrunk further to 480x272 per follow-up feedback that Bible
    # story book cover images (large, often portrait/high-res source
    # photos) were still slow -- a smaller target box pushes those covers
    # down to a smaller scale_n too, without a visible quality hit given
    # they're upscaled to fit the same on-screen box either way.
    TARGET_BOX_W = 480
    TARGET_BOX_H = 272

    @staticmethod
    def _pick_scale_n(orig_w, orig_h, target_w=TARGET_BOX_W, target_h=TARGET_BOX_H):
        """Smallest scale_n (1-8) that still decodes to at least the
        on-screen display size -- so an image that only needs to be shown
        at, say, 340x200 doesn't pay for a 1200x675 decode just because
        that's what a fixed default would have used. The decoder supports
        any integer 1-8, not just powers of 2, so this picks the tightest
        fit rather than jumping straight to the next power of 2 (which
        was overshooting to full-res for images that only needed a little
        more than half)."""
        if not orig_w or not orig_h:
            return 4
        fit_scale = min(target_w / orig_w, target_h / orig_h, 1.0)  # never upscale past 1:1 source
        needed = fit_scale * 8
        for n in range(1, 9):
            if n >= needed:
                return n
        return 8

    # priority levels: lower number = processed first
    PRIORITY_VISIBLE = 0    # image on the page currently being read
    PRIORITY_PREFETCH = 1   # background prefetch for the next page/chapter
    PRIORITY_PRERENDER = 2  # opportunistic whole-book background decode --
                             # always loses the queue to real reading needs,
                             # so it can run for a long time without ever
                             # making the UI feel slow

    def __init__(self, cache_dir, is_relevant=None, disk_cache_enabled=True, on_update=None):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        # Called (with no args) from the worker thread every time a decode
        # actually finishes (thumb or full stage, success or error) --
        # v0.1.32 fix for the same "background thread flips a flag but
        # nothing tells the render loop to actually redraw" bug class
        # reported for the downloader screens. Reader-screen polling via
        # has_pending_image_updates() only redraws WHILE something is
        # still pending; the exact frame where the LAST image finishes
        # could otherwise be missed entirely, leaving a stale low-res
        # thumbnail on screen until an unrelated button press.
        self.on_update = on_update
        # When False, decode results never touch disk at all -- pure
        # RAM-only operation (still bounded by MAX_INMEMORY_IMAGES).
        # Useful for a wearing/slow SD card, or anyone who'd rather not
        # accumulate cache files at all and is fine re-decoding on every
        # fresh view.
        self.disk_cache_enabled = disk_cache_enabled
        # key -> {"thumb": (rgb,w,h)|"loading"|"error"|None,
        #         "full":  (rgb,w,h)|"loading"|"error"|None}
        self._results = OrderedDict()
        self._lock = threading.Lock()
        self._cache_lock = threading.Lock()

        # is_relevant(key) -> bool: lets the app tell the loader whether a
        # PRIORITY_VISIBLE request is still for a page the user is actually
        # looking at. Checked before starting AND before the (expensive)
        # full-res stage, so scrolling past an image cancels wasted work
        # instead of burning CPU decoding something nobody will see.
        # Not applied to PRIORITY_PREFETCH tasks -- those are opportunistic
        # background work and always allowed to finish.
        self.is_relevant = is_relevant

        # Single dedicated worker: image decode is pure CPU work under the
        # GIL, so multiple threads don't add real parallelism -- what they
        # WOULD add is contention and unpredictable interleaving. A single
        # priority-ordered worker guarantees a visible-page image always
        # jumps the queue ahead of any pending prefetch work.
        self._queue = queue.PriorityQueue()
        self._seq_counter = itertools.count()

        # v0.1.66 -- Tracks how many not-yet-started tasks are sitting in
        # the queue at each priority level. The queue itself can't be
        # cheaply peeked (PriorityQueue has no safe "is there a VISIBLE
        # item waiting?" check), so this counter is kept in step with
        # every put/get under _lock. Lets a PRERENDER task about to start
        # decoding check "is something more urgent waiting right now?"
        # and step aside if so -- see _worker_loop(). Without this, once
        # a PRERENDER image starts decoding it can't be interrupted, so a
        # page turn or chapter change can end up stuck behind it even
        # though PRERENDER is nominally the lowest priority.
        self._pending_counts = {self.PRIORITY_VISIBLE: 0,
                                 self.PRIORITY_PREFETCH: 0,
                                 self.PRIORITY_PRERENDER: 0}

        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker.start()

    def _cache_path(self, key, stage):
        safe = key.replace("/", "_").replace("\\", "_")
        return os.path.join(self.cache_dir, f"{safe}.{stage}.rgb")

    def get(self, key):
        """Returns the best available result: full-res if ready, else
        thumb if ready, else 'loading', else None if not yet requested."""
        with self._lock:
            entry = self._results.get(key)
            if entry is not None:
                self._results.move_to_end(key)  # mark as recently used
        if not entry:
            return None
        if isinstance(entry.get("full"), tuple):
            return entry["full"]
        if isinstance(entry.get("thumb"), tuple):
            return entry["thumb"]
        if entry.get("full") == "loading" or entry.get("thumb") == "loading":
            return "loading"
        return "error"

    def get_with_full_flag(self, key):
        """Atomic version of get() + is_full_res() under one lock.
        Returns (result, is_full) where result matches get() and is_full
        is True only when the full-res decode has actually landed.
        Prevents the race in get_image_texture() where two separate lock
        acquisitions (get() then is_full_res()) let the worker land the
        full result in between -- causing get() to return the thumb while
        is_full_res() returns True, permanently tagging a blurry thumb
        texture as full-res and showing "improving..." forever."""
        with self._lock:
            entry = self._results.get(key)
            if entry is not None:
                self._results.move_to_end(key)
        if not entry:
            return None, False
        full_ready = isinstance(entry.get("full"), tuple)
        if full_ready:
            return entry["full"], True
        if isinstance(entry.get("thumb"), tuple):
            return entry["thumb"], False
        if entry.get("full") == "loading" or entry.get("thumb") == "loading":
            return "loading", False
        return "error", False

    def is_upgrading(self, key):
        """True if a thumb is showing but the full-res version is still
        decoding in the background -- lets the UI show a subtle indicator."""
        with self._lock:
            entry = self._results.get(key)
        if not entry:
            return False
        return isinstance(entry.get("thumb"), tuple) and entry.get("full") == "loading"

    def is_full_res(self, key):
        """True if the full-resolution decode has landed for this key."""
        with self._lock:
            entry = self._results.get(key)
        if not entry:
            return False
        return isinstance(entry.get("full"), tuple)

    def seconds_loading(self, key):
        """Elapsed seconds since this key was first requested, or None if
        never requested. Only meaningful to call while the result is still
        pending (loading/None) -- lets the UI show active progress
        ('Loading image... (3s)') instead of a static placeholder that
        looks identical whether it's been 1 second or 30, which was the
        actual cause of it looking 'stuck' until the person scrolled."""
        with self._lock:
            entry = self._results.get(key)
        if not entry or "requested_at" not in entry:
            return None
        return time.time() - entry["requested_at"]

    def get_status_snapshot(self, key):
        """Everything a caller needs about one image in a SINGLE lock
        acquisition (v0.1.49). Replaces the old pattern of calling get(),
        is_upgrading(), get_with_full_flag(), and seconds_loading()
        separately -- each took its own lock. On the reader screen this
        combo ran every frame for every image on the page while any of
        them were still decoding (has_pending_image_updates() polls
        every loop iteration by design, so images can't get stuck until
        a button press), so 3 separate lock acquisitions per image per
        frame was pure redundant overhead on top of already-cheap work.
        Same check frequency as before -- this only makes each check
        cheaper, not less frequent, so nothing about "does it notice
        completion" changes.
        Returns a dict: {result, is_full, is_upgrading, seconds}
          result       -- matches get(): rgb tuple, 'loading', 'error', or None
          is_full      -- True only when the full-res decode has landed
          is_upgrading -- True if showing a thumb while full-res still decodes
          seconds      -- elapsed since first requested, or None if never requested
        """
        with self._lock:
            entry = self._results.get(key)
            if entry is not None:
                self._results.move_to_end(key)
        if not entry:
            return {"result": None, "is_full": False, "is_upgrading": False, "seconds": None}
        full_val = entry.get("full")
        thumb_val = entry.get("thumb")
        full_ready = isinstance(full_val, tuple)
        thumb_ready = isinstance(thumb_val, tuple)
        if full_ready:
            result = full_val
        elif thumb_ready:
            result = thumb_val
        elif full_val == "loading" or thumb_val == "loading":
            result = "loading"
        else:
            result = "error"
        seconds = (time.time() - entry["requested_at"]) if "requested_at" in entry else None
        return {
            "result": result,
            "is_full": full_ready,
            "is_upgrading": thumb_ready and full_val == "loading",
            "seconds": seconds,
        }

    def has_full_disk_cache(self, key):
        """True if the full-res decode for this key is already sitting on
        disk from a previous session. Lets the caller pass jpeg_bytes=None
        to request() below, skipping the raw JPEG read (and potential
        zip decompression) out of the epub entirely for a returning
        reader -- that read was previously happening unconditionally on
        every launch even when the decode itself was about to be skipped
        via the disk cache anyway."""
        if not self.disk_cache_enabled:
            return False
        cache_file = self._cache_path(key, "full")
        return os.path.exists(cache_file) and os.path.exists(cache_file + ".meta")

    def request(self, key, jpeg_bytes, priority=PRIORITY_VISIBLE):
        with self._lock:
            existing = self._results.get(key)
            if existing is not None:
                # already requested -- if this new request is more urgent
                # than whatever priority it was originally queued at (e.g.
                # a prefetched image the user has now scrolled to), bump it
                # by re-enqueueing at the better priority. Any resulting
                # duplicate decode work is cheap: _process() below checks
                # for an already-complete result before doing real work,
                # and the on-disk cache makes a redundant decode near-free.
                if priority < existing.get("priority", self.PRIORITY_PREFETCH):
                    existing["priority"] = priority
                    self._pending_counts[priority] += 1
                    self._queue.put((priority, next(self._seq_counter), key, jpeg_bytes))
                return
            self._results[key] = {"thumb": "loading", "full": None, "priority": priority,
                                   "requested_at": time.time()}
            self._pending_counts[priority] += 1
        self._queue.put((priority, next(self._seq_counter), key, jpeg_bytes))

    # v0.1.66 -- Small sleep inserted between PRERENDER decodes only.
    # Doesn't slow down real reading (VISIBLE/PREFETCH are never delayed),
    # but caps sustained CPU/heat during a long whole-book background
    # pre-render pass. 30ms is small enough that pre-render of a full
    # book still finishes in a reasonable time, but large enough to give
    # the render loop and any newly-arriving reading request a real gap.
    PRERENDER_THROTTLE_SECONDS = 0.03

    def _worker_loop(self):
        while True:
            priority, _seq, key, jpeg_bytes = self._queue.get()
            with self._lock:
                self._pending_counts[priority] -= 1

            # Step-aside check (v0.1.66): a PRERENDER task can't be
            # interrupted once decoding starts, so if VISIBLE or PREFETCH
            # work is waiting RIGHT NOW, requeue this one behind it
            # instead of blocking a page turn/chapter load behind
            # low-priority background work. Bounded to a few retries so a
            # steady trickle of prefetch requests can't starve pre-render
            # forever.
            if priority == self.PRIORITY_PRERENDER:
                with self._lock:
                    urgent_waiting = (self._pending_counts[self.PRIORITY_VISIBLE] > 0
                                       or self._pending_counts[self.PRIORITY_PREFETCH] > 0)
                if urgent_waiting:
                    with self._lock:
                        self._pending_counts[priority] += 1
                    self._queue.put((priority, next(self._seq_counter), key, jpeg_bytes))
                    self._queue.task_done()
                    time.sleep(0.01)  # brief yield, avoid a busy spin
                    continue

            try:
                self._process(key, jpeg_bytes, priority)
                self._evict_if_needed()
            except Exception as e:
                _boot_log(f"image worker error for {key}: {e}\n")
            finally:
                self._queue.task_done()
                if self.on_update:
                    try:
                        self.on_update()
                    except Exception:
                        pass  # never let a UI-signaling callback crash the decode worker
                if priority == self.PRIORITY_PRERENDER:
                    time.sleep(self.PRERENDER_THROTTLE_SECONDS)

    def _evict_if_needed(self):
        """LRU-evict fully-resolved entries from the in-memory results
        cache once it exceeds MAX_INMEMORY_IMAGES. Never evicts an entry
        still "loading" -- the worker may still be writing into it, and
        popping it out from under that write would KeyError."""
        with self._lock:
            if len(self._results) <= self.MAX_INMEMORY_IMAGES:
                return
            for k in list(self._results.keys()):
                if len(self._results) <= self.MAX_INMEMORY_IMAGES:
                    break
                entry = self._results[k]
                if entry.get("full") == "loading" or entry.get("thumb") == "loading":
                    continue  # still in flight, don't evict
                del self._results[k]

    def _process(self, key, jpeg_bytes, priority):
        with self._lock:
            entry = self._results.get(key)
            if entry is not None and isinstance(entry.get("full"), tuple):
                return  # already fully resolved by an earlier queue entry for this key

        if priority == self.PRIORITY_VISIBLE and self.is_relevant is not None \
                and not self.is_relevant(key):
            # user has already navigated away from this page -- drop the
            # placeholder so a fresh request can be made if it becomes
            # visible again later, and skip decoding entirely
            with self._lock:
                self._results.pop(key, None)
            return

        if jpeg_bytes is None:
            # Caller already confirmed has_full_disk_cache(key) is True and
            # deliberately skipped reading the raw JPEG out of the epub zip
            # -- just load the cached RGB straight off disk.
            try:
                result = self._load_or_decode(key, None, "full", None)
                with self._lock:
                    self._results[key]["thumb"] = result
                    self._results[key]["full"] = result
            except Exception as e:
                _boot_log(f"disk-cache image load failed for {key}: {e}\n")
                with self._lock:
                    self._results[key]["thumb"] = "error"
                    self._results[key]["full"] = "error"
            return

        peeked = peek_jpeg_size(jpeg_bytes)
        full_n = self._pick_scale_n(*peeked) if peeked else self.FULL_N

        if full_n <= 4:
            # Small enough on-screen that the "instant DC-only thumb, then
            # upgrade" two-pass dance isn't worth it -- it was costing a
            # full extra entropy-decode pass (re-parsing the same JPEG
            # bitstream from scratch) just to show a placeholder for a
            # fraction of a second before immediately replacing it. Decode
            # once, directly at the resolution that's actually needed.
            try:
                result = self._load_or_decode(key, jpeg_bytes, "full", full_n)
                with self._lock:
                    self._results[key]["thumb"] = result
                    self._results[key]["full"] = result
            except Exception as e:
                _boot_log(f"single-pass decode failed for {key}: {e}\n")
                with self._lock:
                    self._results[key]["thumb"] = "error"
                    self._results[key]["full"] = "error"
            return

        try:
            result = self._load_or_decode(key, jpeg_bytes, "thumb", self.THUMB_N)
            with self._lock:
                self._results[key]["thumb"] = result
                self._results[key]["full"] = "loading"
        except Exception as e:
            _boot_log(f"thumb decode failed for {key}: {e}\n")
            with self._lock:
                self._results[key]["thumb"] = "error"
                self._results[key]["full"] = "error"
            return

        # re-check relevance before the expensive full-res stage -- the
        # thumb decode takes a fraction of a second, but if the user has
        # already scrolled past by the time it's done, don't burn the
        # remaining ~1-2s on the upgrade
        if priority == self.PRIORITY_VISIBLE and self.is_relevant is not None \
                and not self.is_relevant(key):
            with self._lock:
                self._results[key]["full"] = "error"  # thumb stays visible, just won't upgrade
            return

        try:
            result = self._load_or_decode(key, jpeg_bytes, "full", full_n)
            with self._lock:
                self._results[key]["full"] = result
        except Exception as e:
            _boot_log(f"full decode failed for {key}: {e}\n")
            with self._lock:
                self._results[key]["full"] = "error"

    def _load_or_decode(self, key, jpeg_bytes, stage, n):
        if not self.disk_cache_enabled:
            # RAM-only mode: never touch disk at all, just decode fresh.
            # (jpeg_bytes is guaranteed non-None here -- the disk-cache-hit
            # fast path that passes None can only trigger when
            # has_full_disk_cache() is True, which is always False while
            # disk cache is disabled.)
            return decode_jpeg(jpeg_bytes, scale_n=n)
        cache_file = self._cache_path(key, stage)
        meta_file = cache_file + ".meta"
        if os.path.exists(cache_file) and os.path.exists(meta_file):
            try:
                with open(meta_file) as f:
                    w, h = map(int, f.read().split(","))
                expected_size = w * h * 3
                actual_size = os.path.getsize(cache_file)
                if actual_size != expected_size:
                    raise ValueError(
                        f"cache size mismatch: expected {expected_size}, got {actual_size}")
                with open(cache_file, "rb") as f:
                    rgb = f.read()
                try:
                    os.utime(cache_file, None)  # touch for LRU recency
                except OSError:
                    pass
                return rgb, w, h
            except Exception as e:
                # v0.1.67 -- Corrupt/truncated cache entry: most likely an
                # interrupted write (chapter switch, book close, power
                # loss, or SD card hiccup while this exact file was being
                # written). Discard and fall through to a fresh decode
                # instead of handing SDL a buffer shorter than its
                # claimed dimensions, which produced garbled textures or
                # risked an out-of-bounds read.
                _boot_log(f"discarding corrupt image cache for {key} ({stage}): {e}\n")
                for stale in (cache_file, meta_file):
                    try:
                        os.remove(stale)
                    except OSError:
                        pass
        rgb, w, h = decode_jpeg(jpeg_bytes, scale_n=n)

        # v0.1.67 -- Atomic write: decode to a temp file, then os.rename()
        # into place. rename() on the same filesystem is atomic on Linux,
        # so a reader can only ever see the old cache file or the fully
        # written new one -- never a partial write. rgb is renamed into
        # place BEFORE meta, so a reader can never observe a meta file
        # whose matching .rgb isn't already complete (the read path above
        # only trusts a pair where both files exist). This is what makes
        # switching chapters or closing the book safe to do immediately,
        # without waiting for in-flight background image decodes to
        # finish first -- an interrupted write just leaves the old cache
        # entry (or nothing) rather than a corrupted one.
        tmp_rgb = f"{cache_file}.tmp{os.getpid()}"
        tmp_meta = f"{meta_file}.tmp{os.getpid()}"
        try:
            with open(tmp_rgb, "wb") as f:
                f.write(rgb)
            os.rename(tmp_rgb, cache_file)
            with open(tmp_meta, "w") as f:
                f.write(f"{w},{h}")
            os.rename(tmp_meta, meta_file)
        finally:
            for tmp in (tmp_rgb, tmp_meta):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
        self._enforce_cache_limit()
        return rgb, w, h

    def _enforce_cache_limit(self):
        """LRU eviction: if the on-disk image cache exceeds MAX_CACHE_BYTES,
        delete the least-recently-used .rgb/.meta pairs until under the cap.
        Runs cheaply -- only triggered right after a write, and skipped
        entirely most of the time via a size check first."""
        with self._cache_lock:
            try:
                entries = []
                total = 0
                for fname in os.listdir(self.cache_dir):
                    if not fname.endswith(".rgb"):
                        continue
                    fpath = os.path.join(self.cache_dir, fname)
                    size = os.path.getsize(fpath)
                    meta_path = fpath + ".meta"
                    meta_size = os.path.getsize(meta_path) if os.path.exists(meta_path) else 0
                    mtime = os.path.getmtime(fpath)
                    entries.append((mtime, fpath, meta_path, size + meta_size))
                    total += size + meta_size

                if total <= self.MAX_CACHE_BYTES:
                    return

                entries.sort(key=lambda e: e[0])  # oldest first
                for mtime, fpath, meta_path, size in entries:
                    if total <= self.MAX_CACHE_BYTES:
                        break
                    try:
                        os.remove(fpath)
                    except OSError:
                        pass
                    try:
                        if os.path.exists(meta_path):
                            os.remove(meta_path)
                    except OSError:
                        pass
                    total -= size
            except Exception as e:
                _boot_log(f"cache eviction failed: {e}\n")


# ============================================================
# Text rendering helpers
# ============================================================
_render_text_failure_logged = set()  # which failure types we've already logged once


def render_text(renderer, font, text, color, x, y):
    if not font or not text:
        return 0
    surf = TTF.TTF_RenderUTF8_Blended(font, text.encode("utf-8"), color)
    if not surf:
        if "surf" not in _render_text_failure_logged:
            _render_text_failure_logged.add("surf")
            _boot_log(f"render_text: TTF_RenderUTF8_Blended returned NULL for "
                       f"{text!r}: {SDL.SDL_GetError().decode('utf-8', errors='replace')}\n")
        return 0
    tex = SDL.SDL_CreateTextureFromSurface(renderer, surf)
    if not tex:
        if "tex" not in _render_text_failure_logged:
            _render_text_failure_logged.add("tex")
            _boot_log(f"render_text: SDL_CreateTextureFromSurface returned NULL "
                       f"for {text!r}: {SDL.SDL_GetError().decode('utf-8', errors='replace')}\n")
        SDL.SDL_FreeSurface(surf)
        return 0
    w = ctypes.c_int(); h = ctypes.c_int()
    TTF.TTF_SizeUTF8(font, text.encode("utf-8"), ctypes.byref(w), ctypes.byref(h))
    dst = Rect(x, y, w.value, h.value)
    ret = SDL.SDL_RenderCopy(renderer, tex, None, ctypes.byref(dst))
    if ret != 0 and "copy" not in _render_text_failure_logged:
        _render_text_failure_logged.add("copy")
        _boot_log(f"render_text: SDL_RenderCopy returned {ret} (error) for "
                   f"{text!r}: {SDL.SDL_GetError().decode('utf-8', errors='replace')}\n")
    SDL.SDL_DestroyTexture(tex)
    SDL.SDL_FreeSurface(surf)
    return w.value


def render_text_cached(app, renderer, font, text, color, x, y):
    """Same as render_text, but reuses SDL textures across frames instead
    of rasterizing + uploading + destroying on every single draw call.
    Cache is scoped to the current page and cleared whenever the page (or
    font size) changes -- see App._clear_text_texture_cache()."""
    if not font or not text:
        return 0
    key = (id(font), text, color.r, color.g, color.b)
    cached = app._text_texture_cache.get(key)
    if cached:
        tex, w, h = cached
    else:
        surf = TTF.TTF_RenderUTF8_Blended(font, text.encode("utf-8"), color)
        if not surf:
            return 0
        tex = SDL.SDL_CreateTextureFromSurface(renderer, surf)
        wbuf = ctypes.c_int(); hbuf = ctypes.c_int()
        TTF.TTF_SizeUTF8(font, text.encode("utf-8"), ctypes.byref(wbuf), ctypes.byref(hbuf))
        w, h = wbuf.value, hbuf.value
        SDL.SDL_FreeSurface(surf)
        if not tex:
            return 0
        app._text_texture_cache[key] = (tex, w, h)
    dst = Rect(x, y, w, h)
    SDL.SDL_RenderCopy(renderer, tex, None, ctypes.byref(dst))
    return w


def _row_h(font, pad=20):
    """Row height in real pixels: current font's rendered height plus
    padding (scaled). v0.1.50 -- list/menu rows used to be fixed _sy(NN)
    constants tuned for the old fixed 18pt UI font; now that UI text
    scales with Font Size +/-, rows need to grow with it or text clips/
    overlaps between rows at larger sizes.
    v0.1.74: default pad bumped 16->20 -- with only 16, the gap between
    a glyph's lowest descender pixel and the row's bottom edge measured
    a consistent 4px at every Font Size, which read as cramped once
    that edge became a visible curve (rounded-corner highlights, Kaleb's
    report) rather than a plain straight line. 20 gives ~8px of
    breathing room instead, comfortably more than CORNER_RADIUS."""
    if not font:
        return _sy(44)
    return TTF.TTF_FontHeight(font) + _sy(pad)


def _fit_text(font, text, max_w):
    """Truncate text with a trailing ellipsis if it's wider than max_w --
    v0.1.50 safety net for popup menus/overlays with a fixed pixel width
    (e.g. the MENU panel), now that UI text can be scaled up via Font
    Size +/- and could otherwise run past the panel edge."""
    if not font or not text or text_width(font, text) <= max_w:
        return text
    ell = "..."
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if text_width(font, text[:mid] + ell) <= max_w:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo] + ell if lo > 0 else ell


def text_width(font, text):
    if not font or not text:
        return 0
    w = ctypes.c_int(); h = ctypes.c_int()
    TTF.TTF_SizeUTF8(font, text.encode("utf-8"), ctypes.byref(w), ctypes.byref(h))
    return w.value


def fill_rect(renderer, x, y, w, h, color):
    SDL.SDL_SetRenderDrawColor(renderer, color.r, color.g, color.b, color.a)
    r = Rect(x, y, w, h)
    SDL.SDL_RenderFillRect(renderer, ctypes.byref(r))


CORNER_RADIUS = _sx(6)  # "slight curved edges" per Kaleb's request -- small on
                         # purpose, meant to soften corners without looking
                         # like a bubbly/rounded design language change.


def fill_rect_rounded(renderer, x, y, w, h, color, radius=None):
    """Same as fill_rect() but with softly rounded corners. No SDL2_gfx is
    linked (raw ctypes SDL2 core only, per this project's no-external-deps
    rule), so true anti-aliased circles aren't available -- this
    approximates each corner with one 1px-tall SDL_RenderFillRect per row
    (a quarter-circle staircase), which is visually smooth enough at
    small radii and costs only ~4*radius extra fill calls, done once per
    popup/selector draw (not per frame of scrolling body text), so it's
    negligible on the 1GB-RAM ARM target."""
    if radius is None:
        radius = CORNER_RADIUS
    radius = max(0, min(radius, w // 2, h // 2))
    if radius == 0:
        fill_rect(renderer, x, y, w, h, color)
        return
    SDL.SDL_SetRenderDrawColor(renderer, color.r, color.g, color.b, color.a)
    # center cross: full-height middle strip + left/right strips (minus
    # the corner squares, which are filled separately below)
    mid = Rect(x + radius, y, w - 2 * radius, h)
    SDL.SDL_RenderFillRect(renderer, ctypes.byref(mid))
    left = Rect(x, y + radius, radius, h - 2 * radius)
    SDL.SDL_RenderFillRect(renderer, ctypes.byref(left))
    right = Rect(x + w - radius, y + radius, radius, h - 2 * radius)
    SDL.SDL_RenderFillRect(renderer, ctypes.byref(right))
    # 4 corners, one row at a time, quarter-circle mask
    for row in range(radius):
        dy = radius - row
        dx = int(math.sqrt(max(0, radius * radius - dy * dy)))
        inset = radius - dx
        if inset >= radius:
            continue
        rw = radius - inset
        tl = Rect(x + inset, y + row, rw, 1)
        SDL.SDL_RenderFillRect(renderer, ctypes.byref(tl))
        tr = Rect(x + w - radius, y + row, rw, 1)
        SDL.SDL_RenderFillRect(renderer, ctypes.byref(tr))
        bl = Rect(x + inset, y + h - 1 - row, rw, 1)
        SDL.SDL_RenderFillRect(renderer, ctypes.byref(bl))
        br = Rect(x + w - radius, y + h - 1 - row, rw, 1)
        SDL.SDL_RenderFillRect(renderer, ctypes.byref(br))


# ============================================================
# Library scanning
# ============================================================
def _load_library_cache():
    if os.path.exists(LIBRARY_CACHE_PATH):
        try:
            with open(LIBRARY_CACHE_PATH) as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_library_cache(cache):
    try:
        with open(LIBRARY_CACHE_PATH, "w") as f:
            json.dump(cache, f)
    except Exception:
        pass


def scan_library():
    books = []
    if not os.path.isdir(LIBRARY_DIR):
        return books
    cache = _load_library_cache()
    cache_dirty = False

    for fname in sorted(os.listdir(LIBRARY_DIR)):
        if not fname.lower().endswith(".epub"):
            continue
        path = os.path.join(LIBRARY_DIR, fname)
        try:
            stat = os.stat(path)
            fingerprint = f"{stat.st_size}:{stat.st_mtime}"
        except OSError:
            fingerprint = None
            stat = None

        cached_entry = cache.get(fname)
        # first_seen is deliberately kept stable across re-scans/edits (it's
        # "when this book first appeared in the library", not tied to the
        # fingerprint) -- otherwise "recently added" would reorder every
        # time a file's mtime changed for an unrelated reason.
        first_seen = (cached_entry or {}).get("first_seen") or (stat.st_mtime if stat else time.time())

        if cached_entry and cached_entry.get("fingerprint") == fingerprint:
            title = cached_entry["title"]
            author = cached_entry.get("author") or ""
        else:
            title = fname[:-5]
            author = ""
            try:
                doc = EpubDocument(path)
                opf = doc._read(doc.opf_path)
                import re
                m = re.search(r"<dc:title[^>]*>(.*?)</dc:title>", opf, re.DOTALL | re.IGNORECASE)
                if m:
                    title = re.sub(r"<[^>]+>", "", m.group(1)).strip() or title
                m2 = re.search(r"<dc:creator[^>]*>(.*?)</dc:creator>", opf, re.DOTALL | re.IGNORECASE)
                if m2:
                    author = re.sub(r"<[^>]+>", "", m2.group(1)).strip()
            except Exception as e:
                _boot_log(f"library scan failed for {fname}: {e}\n")
            cache[fname] = {
                "fingerprint": fingerprint, "title": title, "author": author,
                "first_seen": first_seen,
            }
            cache_dirty = True

        books.append({
            "path": path, "title": title, "filename": fname,
            "author": author, "first_seen": first_seen,
        })

    # drop stale entries for files that no longer exist -- and purge their
    # orphaned caches too. Without this, deleting an epub left its image
    # cache, anchor cache, and pin entry sitting around forever with
    # nothing that could ever reference them again.
    current_files = {b["filename"] for b in books}
    stale = [k for k in cache if k not in current_files]
    for fname in stale:
        del cache[fname]
        cache_dirty = True
        stale_id = book_id(os.path.join(LIBRARY_DIR, fname))
        for pattern in (
            os.path.join(IMG_CACHE_DIR, f"{stale_id}__*"),
            os.path.join(ANCHOR_CACHE_DIR, f"{stale_id}.json"),
        ):
            for path in glob.glob(pattern):
                try:
                    os.remove(path)
                except OSError:
                    pass
        pinned = load_pinned()
        if fname in pinned:
            pinned.discard(fname)
            save_pinned(pinned)

    if cache_dirty:
        _save_library_cache(cache)

    return books


# ---- Pinned books ----
def load_pinned():
    if os.path.exists(PINNED_PATH):
        try:
            with open(PINNED_PATH) as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()


def save_pinned(pinned_set):
    try:
        with open(PINNED_PATH, "w") as f:
            json.dump(sorted(pinned_set), f)
    except Exception:
        pass


LIBRARY_SORT_MODES = ["title", "author", "last_read", "recent"]
LIBRARY_SORT_LABELS = {
    "title": "Title A-Z", "author": "Author A-Z",
    "last_read": "Last Read", "recent": "Recently Added",
}


def _book_last_read_ts(book):
    last = get_last_position(book["path"])
    return last.get("ts", 0) if last else 0


def sort_library(books, mode, pinned):
    """Pinned books always float to the top, sorted among themselves by
    the same active mode; unpinned books follow, sorted the same way."""
    def sort_key(b):
        if mode == "author":
            return (b.get("author") or "").lower() or "\uffff"  # no-author books sort last
        if mode == "title":
            return (b.get("title") or "").lower()
        if mode == "last_read":
            return -_book_last_read_ts(b)  # most recent first; never-read (0) sorts last
        if mode == "recent":
            return -(b.get("first_seen") or 0)  # newest first
        return (b.get("title") or "").lower()

    pinned_books = sorted([b for b in books if b["filename"] in pinned], key=sort_key)
    other_books = sorted([b for b in books if b["filename"] not in pinned], key=sort_key)
    return pinned_books + other_books


# ============================================================
# App state / screens
# ============================================================
SCREEN_LIBRARY = "library"
SCREEN_READER = "reader"
SCREEN_MENU = "menu"
SCREEN_TOC = "toc"
SCREEN_BOOKMARKS = "bookmarks"
SCREEN_STORAGE = "storage"
SCREEN_DOWNLOAD_SOURCES = "download_sources"  # pick a plugin (only shown
                                               # if more than one is loaded)
SCREEN_DOWNLOAD_CATEGORIES = "download_categories"  # pick a category, for
                                               # plugins with SUPPORTS_CATEGORIES
SCREEN_DOWNLOAD_BROWSE = "download_browse"    # browse/download from the
                                               # selected plugin
SCREEN_LIBRARY_MENU = "library_menu"          # START on Library -- sort
                                               # shortcuts + Download +
                                               # Storage (v0.1.29)
SCREEN_TEXT_ENTRY = "text_entry"              # generic D-pad letter-grid
                                               # text input (v0.1.30) --
                                               # not tied to any one
                                               # feature; anything needing
                                               # typed input can reuse it

LIBRARY_MENU_ITEMS = ["Sort: Title A-Z", "Sort: Author A-Z", "Sort: Last Read",
                       "Sort: Recently Added", "Theme +", "Theme -",
                       "Download Books", "Storage", "Back"]

# Ragged rows are fine -- UP/DOWN/LEFT/RIGHT navigation clamps to each
# row's own length dynamically, no fixed grid width assumed. Letters,
# then digits (needed for periodical issue numbers like 202609 -- an
# earlier version of this grid omitted digits entirely, which silently
# made typing any issue number impossible; caught via real button-input
# testing, not just AST-parse, same lesson as v0.1.28/29), then actions.
TEXT_ENTRY_GRID = [
    [("A", "char"), ("B", "char"), ("C", "char"), ("D", "char"), ("E", "char"), ("F", "char"), ("G", "char")],
    [("H", "char"), ("I", "char"), ("J", "char"), ("K", "char"), ("L", "char"), ("M", "char"), ("N", "char")],
    [("O", "char"), ("P", "char"), ("Q", "char"), ("R", "char"), ("S", "char"), ("T", "char"), ("U", "char")],
    [("V", "char"), ("W", "char"), ("X", "char"), ("Y", "char"), ("Z", "char")],
    [("0", "char"), ("1", "char"), ("2", "char"), ("3", "char"), ("4", "char"),
     ("5", "char"), ("6", "char"), ("7", "char"), ("8", "char"), ("9", "char")],
    [("SPACE", "space"), ("DEL", "backspace"), ("OK", "confirm"), ("CANCEL", "cancel")],
]

MENU_ITEMS = ["Chapters", "Bookmarks", "Add Bookmark", "Font Size +", "Font Size -",
              "Theme +", "Theme -", "Library", "Storage", "Resume"]

STORAGE_ACTIONS = ["Clear Image Cache", "Clean Up Orphaned Bookmarks",
                    "Backup Bookmarks Now", "Restore Latest Backup",
                    "Toggle Disk Cache (RAM-only mode)", "Toggle Images (text-only mode)",
                    "Pre-render Book Images", "Back"]


def flatten_toc(entries, out=None):
    if out is None:
        out = []
    for e in entries:
        out.append(e)
        flatten_toc(e.children, out)
    return out


class App:
    def __init__(self, renderer):
        self.renderer = renderer
        self.fonts = FontManager()
        apply_theme(load_settings().get("theme_index", 0))
        self.screen = SCREEN_LIBRARY
        self.pinned = load_pinned()
        self.lib_sort_mode = "title"
        self.books = []
        self.lib_index = 0
        self.refresh_library()

        self.doc = None
        self.state = None
        self.current_book_path = None
        self._book_id = None  # set in open_book(); namespaces ImageLoader keys

        self.scroll = 0
        self.selected_span = 0
        self.fast_scroll = False   # toggled by Y in the reader: 10x jump for D-pad
        # Parallel to ReaderState.back_stack (which only remembers file+anchor).
        # Without this, "B" after following a footnote always snapped back to
        # the top of the chapter instead of wherever the reader actually was,
        # since there was nowhere the exact scroll offset was being kept.
        self._scroll_stack = []
        self.menu_index = 0
        self.toc_flat = []
        self.toc_index = 0
        self.bookmarks_index = 0
        self._bookmark_delete_confirm_idx = None  # armed-for-delete row, or None
        self._lib_delete_confirm_idx = None  # armed-for-delete row on Library screen, or None
        self.storage_index = 0
        self._storage_confirm_idx = None  # armed-for-confirm row on Storage screen, or None
        self._storage_return_screen = SCREEN_READER  # where Storage's Back
                                                       # goes -- Reader menu
                                                       # or Library menu,
                                                       # whichever opened it
        self.lib_menu_index = 0  # selection on SCREEN_LIBRARY_MENU

        # Generic text-entry state (v0.1.30) -- see open_text_entry().
        self.te_value = ""
        self.te_row = 0
        self.te_col = 0
        self.te_prompt = ""
        self.te_hint = ""  # optional one-line helper text (e.g. common
                            # abbreviations) shown below the input box;
                            # generic on App, not JW-specific -- any
                            # future text-entry use case can set it
        self.te_return_screen = SCREEN_LIBRARY
        self.te_on_confirm = None  # callable(app, value) -- set by whoever opens this screen
        self.te_on_validate = None  # (v0.1.31) callable(app, value) run on a
                                     # background thread BEFORE leaving this
                                     # screen -- must itself either switch
                                     # app.screen away on success or set
                                     # app.te_error and leave te_checking
                                     # False to stay put. Takes priority
                                     # over te_on_confirm when set.
        self.te_checking = False
        self.te_checking_start = None  # time.time() when validation began,
                                        # for the "Checking... (Ns)" spinner
        self.te_error = None

        # Downloader plugin UI state.
        self.dl_source_index = 0     # selection on SCREEN_DOWNLOAD_SOURCES
        self.dl_cat_index = 0        # selection on SCREEN_DOWNLOAD_CATEGORIES
        self.dl_category = None      # active category (plugin-defined string),
                                      # or None = no category scoping
        self.dl_plugin = None        # the module currently being browsed
        self.dl_items = []
        self.dl_index = 0
        self.dl_page = 1
        self.dl_query = None         # active search text, or None = browse popular
        self.dl_has_next = False
        self.dl_loading = False
        self.dl_loading_start = None  # time.time() a load began, for the
                                       # "Loading... (Ns)" spinner (v0.1.62)
        self.dl_load_error = None
        self._dl_downloading_idx = None  # index currently mid-download, or None

        self.status_msg = None   # brief on-screen feedback (bookmark saved/
        self.status_until = 0    # updated/limit-reached, delete confirmed, etc.

        self._visible_image_keys = set()  # images on the currently-built page
        self.disk_cache_enabled = load_settings().get("disk_cache_enabled", True)
        self.images_enabled = load_settings().get("images_enabled", True)
        self.image_loader = ImageLoader(
            IMG_CACHE_DIR,
            is_relevant=lambda key: key in self._visible_image_keys,
            disk_cache_enabled=self.disk_cache_enabled,
            on_update=lambda: setattr(self, "dirty", True),
        )
        self._image_textures = OrderedDict()   # key -> (texture, w, h, is_full_res)
        self.MAX_IMAGE_TEXTURES = 24            # bounded LRU: caps GPU texture memory
        self.storage_index = 0
        self.quit_requested = False

        # Whole-book background pre-render state (Storage screen action).
        # _prerender_book_id guards against a stale progress bar surviving
        # a book switch -- checked before every progress update.
        self._prerender_active = False
        self._prerender_scanning = False   # True while spine walk is in progress
        self._prerender_cancel = False
        self._prerender_total = 0
        self._prerender_keys = []
        self._prerender_book_id = None
        self._prerender_thread = None

        self._page_cache_key = None
        self._lines = []
        self._line_abs_offsets = []   # cumulative abs char offsets per line (v0.1.46)
        self._line_span_map = []
        self._line_style_runs = []
        self._combined_spans = []
        self._links = []
        self._images = []
        self._anchors = {}
        self._styles = []
        self._para_spans = []
        self._chapter_nav_points = []
        self._text_texture_cache = {}
        # RAM-only LRU cache of raw get_page() results (v0.1.48, raised
        # to 200 entries in v0.1.68 -- see changelog).
        # Keyed by href; capped at _PAGE_TEXT_CACHE_MAX entries.
        # Cleared on book open/close. ~28KB per entry x 200 = ~5.6MB RAM
        # worst case (measured entries are usually smaller; heavy
        # cross-reference/footnote pages could run higher, doubling the
        # estimate to ~11MB is still a safe upper bound on 1GB total RAM).
        # Background thread pre-parses adjacent chapter files so
        # _ensure_page_built() skips the cold XML parse on L2/R2 jumps.
        self._page_text_cache = {}         # href -> get_page() result tuple
        self._page_text_cache_order = []   # insertion order for LRU eviction
        self._PAGE_TEXT_CACHE_MAX = 200

        # v0.1.69 -- Separate cache for the WRAPPED/reflowed result
        # (lines, line_span_map, line_style_runs), keyed by (href,
        # font_size_index). This is distinct from _page_text_cache above:
        # that one skips the XML parse on a repeat visit, but
        # _ensure_page_built() was still re-running self._wrap() (which
        # measures every word's pixel width via SDL_ttf) EVERY time,
        # even on a full cache hit -- on a big NWT chapter (8000+ lines)
        # that's real, repeated cost for something that produces an
        # IDENTICAL result until the font size changes. Keyed by size
        # index (not just href) because wrap results genuinely change
        # with font size; NOT keyed by avail_w since that's fixed by the
        # display resolution for the life of a session.
        # Deliberately NOT populated by the background prefetch thread:
        # self._wrap() calls into SDL_ttf (TTF_SizeUTF8), and this
        # project's own testing rule is real-device verification before
        # trusting anything novel -- calling SDL_ttf off the main thread
        # hasn't been verified safe on this hardware, so wrap results are
        # only ever computed and cached from the main thread, on actual
        # page builds. This still gives a real win for revisits (L2/R2
        # back-and-forth, or jumping back to a recently-viewed scripture)
        # without introducing an unverified threading risk.
        self._wrapped_cache = {}           # (href, size_index) -> (lines, line_span_map, line_style_runs)
        self._wrapped_cache_order = []
        self._WRAPPED_CACHE_MAX = 200       # same bound as _page_text_cache; see v0.1.69 changelog for the combined RAM estimate
        self.dirty = True

    # -------- library --------
    def _img_key(self, src):
        """Namespaces an image's internal epub path with the current book's
        id, so the shared ImageLoader can never confuse two different
        books' images even if they happen to use the same internal path."""
        return f"{self._book_id}__{src}"

    def delete_book(self, book):
        """Deletes the .epub file itself. Deliberately does NOT touch the
        image cache, anchor cache, or pin entry directly -- scan_library()
        (called via refresh_library() right after) already detects any
        cache/pin entry whose file no longer exists on disk and purges it
        automatically (see scan_library()'s stale-entry cleanup). This
        reuses that existing path instead of duplicating it. Bookmarks
        are deliberately left alone, same as that existing cleanup does --
        they're the person's own reading data, not disposable cache; use
        Storage > Clean Up Orphaned Bookmarks if they should go too.
        Returns True on success."""
        if self._prerender_active and self._book_id == book_id(book["path"]):
            self.cancel_prerender()
        try:
            os.remove(book["path"])
        except OSError as e:
            _boot_log(f"failed to delete book {book['path']}: {e}\n")
            return False
        return True

    def refresh_library(self):
        books = scan_library()  # may purge stale pin entries for deleted books on disk
        self.pinned = load_pinned()
        self.books = sort_library(books, self.lib_sort_mode, self.pinned)

    # -------- generic text entry (v0.1.30) --------
    def open_text_entry(self, prompt, initial_value, on_confirm, return_screen, on_validate=None, hint=""):
        """Opens the D-pad letter-grid text-entry screen. Two ways to
        finish, mutually exclusive:
          - on_confirm(app, value): fires immediately when OK is
            selected, screen switches to return_screen right away
            (v0.1.30 behavior -- used for plain search/filter, which
            can't meaningfully "fail").
          - on_validate(app, value): (v0.1.31) fires on a background
            thread instead -- for anything that needs a network
            round-trip to know whether the input was even valid before
            leaving this screen. Must itself set app.screen on success,
            or set app.te_error (and leave te_checking False) to stay
            here and let the person fix a typo. Cancelling (B, or the
            CANCEL cell) always just returns to return_screen without
            calling either one.

        hint: (v0.1.40) optional one-line helper text shown under the
        input box when there's no error/checking status to show instead
        -- e.g. common abbreviations for a code-entry screen. Blank by
        default; purely additive, no effect on existing callers."""
        self.te_value = initial_value or ""
        self.te_row = 0
        self.te_col = 0
        self.te_prompt = prompt
        self.te_hint = hint
        self.te_on_confirm = on_confirm
        self.te_on_validate = on_validate
        self.te_checking = False
        self.te_error = None
        self.te_return_screen = return_screen
        self.screen = SCREEN_TEXT_ENTRY


    def open_downloader(self, plugin):
        """Switches to the browse screen for one plugin (or, if the plugin
        declares SUPPORTS_CATEGORIES, to a category picker first -- see
        open_category()) and kicks off its (network-bound) list_items()
        call on a background thread so the UI never blocks/freezes while
        waiting on a slow or absent connection -- same reasoning as every
        other network/decode call in this app."""
        self.dl_plugin = plugin
        self.dl_category = None
        if getattr(plugin, "SUPPORTS_CATEGORIES", False) and getattr(plugin, "CATEGORIES", None):
            self.dl_cat_index = 0
            self.screen = SCREEN_DOWNLOAD_CATEGORIES
            return
        self.dl_items = []
        self.dl_index = 0
        self.dl_page = 1
        self.dl_query = None
        self.dl_has_next = False
        self.dl_load_error = None
        self.screen = SCREEN_DOWNLOAD_BROWSE
        self._load_dl_page()

    def open_category(self, category):
        """Opens the browse screen scoped to one category (see
        jw_fetch.CATEGORIES) -- same loading pattern as open_downloader()."""
        self.dl_category = category
        self.dl_items = []
        self.dl_index = 0
        self.dl_page = 1
        self.dl_query = None
        self.dl_has_next = False
        self.dl_load_error = None
        self.screen = SCREEN_DOWNLOAD_BROWSE
        self._load_dl_page()

    def _load_dl_page(self):
        # NOTE (v0.1.32 bugfix, applies to every background thread in this
        # class): a redraw-polling condition like "while X is still
        # loading" in the main render loop can only ever redraw WHILE the
        # condition holds. The exact frame where a background thread
        # flips that flag to done happens on a DIFFERENT thread, at an
        # arbitrary time the render loop isn't watching for -- so the
        # very next redraw check after completion sees "not loading
        # anymore" and does nothing, leaving the last-drawn frame (still
        # showing "Loading...") stuck on screen until some UNRELATED
        # event (a button press) forces app.dirty=True. Reported
        # symptom: download browse screens stuck on "Loading..." until
        # the D-pad was pressed. Fix: every background thread below sets
        # self.dirty = True itself at the exact point it finishes, rather
        # than relying on the main loop to notice indirectly.
        plugin = self.dl_plugin
        page = self.dl_page
        query = self.dl_query
        category = self.dl_category
        self.dl_loading = True
        self.dl_loading_start = time.time()
        self.dl_load_error = None

        def _do_load():
            try:
                if category is not None:
                    items, has_next, err = plugin.list_items(query=query, page=page, category=category)
                else:
                    items, has_next, err = plugin.list_items(query=query, page=page)
            except Exception as e:
                items, has_next, err = [], False, str(e)
            # Guard against a stale response landing after the person
            # already backed out, switched plugins/pages/categories, or
            # started a different search while this one was still in
            # flight.
            if (self.dl_plugin is plugin and self.dl_page == page
                    and self.dl_query == query and self.dl_category == category):
                self.dl_items = items
                self.dl_has_next = has_next
                self.dl_load_error = err
                self.dl_index = 0
                self.dl_loading = False
                self.dirty = True  # see class-wide note above _load_dl_page

        threading.Thread(target=_do_load, daemon=True).start()

    def start_search(self, query):
        """Applies a new search query (or clears it back to plain
        browsing if query is empty) and reloads page 1."""
        self.dl_query = query if query else None
        self.dl_page = 1
        self._load_dl_page()

    def dl_next_page(self):
        if not self.dl_has_next or self.dl_loading:
            return
        self.dl_page += 1
        self._load_dl_page()

    def dl_prev_page(self):
        if self.dl_page <= 1 or self.dl_loading:
            return
        self.dl_page -= 1
        self._load_dl_page()

    def start_download(self, idx):
        if self._dl_downloading_idx is not None:
            return  # one at a time -- avoid overlapping writes/status races
        if idx < 0 or idx >= len(self.dl_items):
            return
        item = self.dl_items[idx]
        plugin = self.dl_plugin
        self._dl_downloading_idx = idx
        self.set_status(f'Downloading "{item["title"]}"...', duration=60)

        def _do_download():
            try:
                ok, msg, _path = plugin.download(item, LIBRARY_DIR)
            except Exception as e:
                ok, msg = False, f"Download failed: {e}"
            self._dl_downloading_idx = None
            self.set_status(msg, duration=4.0)
            if ok:
                self.refresh_library()
            self.dirty = True

        threading.Thread(target=_do_download, daemon=True).start()

    def cycle_sort_mode(self):
        idx = LIBRARY_SORT_MODES.index(self.lib_sort_mode)
        self.lib_sort_mode = LIBRARY_SORT_MODES[(idx + 1) % len(LIBRARY_SORT_MODES)]
        self.books = sort_library(self.books, self.lib_sort_mode, self.pinned)
        self.lib_index = 0

    def toggle_pin(self, book):
        fname = book["filename"]
        if fname in self.pinned:
            self.pinned.discard(fname)
        else:
            self.pinned.add(fname)
        save_pinned(self.pinned)
        selected_path = book["path"]
        self.books = sort_library(self.books, self.lib_sort_mode, self.pinned)
        # keep the selection on the same book after the re-sort moves it
        for i, b in enumerate(self.books):
            if b["path"] == selected_path:
                self.lib_index = i
                break

    def open_book(self, book):
        if self._prerender_active:
            self.cancel_prerender()
        cache_key = book_id(book["path"])
        self._book_id = cache_key  # reused to namespace ImageLoader cache keys
        anchor_cache_path = os.path.join(ANCHOR_CACHE_DIR, f"{cache_key}.json")
        try:
            self.doc = EpubDocument(book["path"], anchor_cache_path=anchor_cache_path)
        except Exception as e:
            _boot_log(f"failed to open {book['path']}: {e}\n")
            self.set_status(f'Couldn\'t open "{book["title"]}" -- not a readable EPUB', duration=3.5)
            return
        self.current_book_path = book["path"]

        if not self.doc.spine:
            _boot_log(f"book has an empty spine, cannot open: {book['path']}\n")
            self.current_book_path = None
            self.doc = None
            self.set_status(f'Couldn\'t open "{book["title"]}" -- no readable content found', duration=3.5)
            return

        last = get_last_position(book["path"])
        if last:
            start_file, start_anchor = last["file"], last.get("anchor")
            start_char_off = last.get("char_off")
        else:
            start_file = self.doc.spine[2] if len(self.doc.spine) > 2 else self.doc.spine[0]
            start_anchor = None
            start_char_off = None
        self.state = ReaderState(self.doc, start_file)
        self.state.current_anchor = start_anchor
        self.state.current_char_off = start_char_off
        self.scroll = 0
        self.selected_span = 0
        self._scroll_stack = []
        self.screen = SCREEN_READER
        self._page_cache_key = None
        self._page_text_cache.clear()        # v0.1.48: stale on new book
        self._page_text_cache_order.clear()
        self._wrapped_cache.clear()          # v0.1.69: stale on new book
        self._wrapped_cache_order.clear()
        self._chapter_nav_points = self._build_chapter_nav_points()

    def _build_chapter_nav_points(self):
        """Build an ordered list of (spine_index, file, anchor) representing
        real 'chapters' for L2/R2 navigation. Prefers structural chapterN
        anchors (e.g. Bible books: Exodus 1, Exodus 2, ...) so navigation
        lands on actual chapters rather than internal split/nav fragments.
        Falls back to TOC entries, then (if the TOC turns out to be much
        coarser than the book's real content -- e.g. a daily-text booklet
        whose TOC only lists 12 months even though every day is its own
        spine file) to per-day weekday-prefixed entries, then finally to
        raw spine order for books that don't match any of that."""
        import re
        self.doc._build_anchor_index()

        chapter_re = re.compile(r"^chapter\d+$")
        points = []
        for fname, ids in self.doc._anchor_index.items():
            matches = [i for i in ids if i and chapter_re.match(i)]
            # v0.1.38 fix: a real per-chapter spine file has exactly ONE
            # chapterN anchor (its own opening point). Confirmed against
            # nwt_E.epub's real structure: all 1189 genuine Bible-chapter
            # files have exactly 1 match each, while toc.xhtml alone has
            # 196 -- an internal index page listing in-page jump links to
            # every book/chapter, not a real chapter itself. Without this
            # guard, toc.xhtml (spine index 1, earlier than ALL real front
            # matter -- cover, Bible Navigation, title page, the 22
            # "Question N" articles) was being sorted in as nav point 0,
            # which also corrupted the front-matter-restoration fix just
            # below (it needs points[0] to be the real first chapter, not
            # a false hit sitting even earlier than the front matter it
            # was trying to restore).
            if len(matches) == 1:
                idx = self.doc.spine_index(fname)
                if idx != -1:
                    points.append((idx, fname, matches[0]))
        # Require a real minimum before trusting this heuristic -- a single
        # stray match (e.g. a book's own internal nav/TOC page incidentally
        # using an id like "chapter5" as a link target) is not evidence the
        # book actually uses chapter-anchor structure. A real Bible-style
        # book has hundreds+ of matches; magazines/articles have zero or
        # occasionally one false positive, never a real run of them.
        MIN_CHAPTER_ANCHOR_MATCHES = 5
        if len(points) >= MIN_CHAPTER_ANCHOR_MATCHES:
            points.sort(key=lambda p: p[0])
            # v0.1.38 fix: the chapterN heuristic only ever matches actual
            # Bible-book chapters, so front matter before the first real
            # chapter (cover, title page, the "Question N" intro articles
            # in nwt_E.epub) had NO nav points at all -- confirmed against
            # the real NWT TOC: "Bible Navigation" / title page / "An
            # Introduction to God's Word" / Questions 1-22 all precede
            # Genesis 1 with no chapterN anchor of their own. That meant
            # R2 from anywhere in front matter jumped straight past all of
            # it to Genesis 1 (pos<0 branch below always resolves to
            # target_pos=0, i.e. the first -- and previously ONLY -- real
            # entry), and L2 from Genesis 1 (nav point 0) had nothing
            # before it to go back to (target_pos=-1, rejected). Fix:
            # prepend TOC entries whose spine index falls before the first
            # chapter-anchor point, so front matter gets its own steppable
            # nav points too, same as any other book's TOC-based chapters.
            first_chapter_idx = points[0][0]
            flat = flatten_toc(self.doc.toc)
            front_points = []
            seen_idx = set()
            for entry in flat:
                f = entry.href.split("#")[0] if "#" in entry.href else entry.href
                anchor = entry.href.split("#", 1)[1] if "#" in entry.href else None
                idx = self.doc.spine_index(f)
                if idx != -1 and idx < first_chapter_idx and idx not in seen_idx:
                    front_points.append((idx, f, anchor))
                    seen_idx.add(idx)
            front_points.sort(key=lambda p: p[0])
            return front_points + points

        # fallback: flatten TOC, map each entry's target file to a spine index
        flat = flatten_toc(self.doc.toc)
        toc_points = []
        seen_idx = set()
        for entry in flat:
            f = entry.href.split("#")[0] if "#" in entry.href else entry.href
            anchor = entry.href.split("#", 1)[1] if "#" in entry.href else None
            idx = self.doc.spine_index(f)
            if idx != -1 and idx not in seen_idx:
                toc_points.append((idx, f, anchor))
                seen_idx.add(idx)
        toc_points.sort(key=lambda p: p[0])

        # If the TOC gives WAY fewer nav points than the spine actually has
        # content files (e.g. 17 months vs 741 spine files in a daily-text
        # booklet), it's worth checking whether each "hidden" file is really
        # its own standalone entry rather than a pagination fragment of the
        # one before it. JW daily-text publications (Examining the
        # Scriptures and similar) reliably open each day's entry with a
        # weekday name ("Thursday, January 1", "Friday, January 2", ...) --
        # a strong, low-false-positive signal that's very unlikely to
        # appear at the start of a Bible chapter or a magazine article, so
        # this can't accidentally make navigation worse for those. Gated to
        # only run this extra per-spine-file scan when the TOC already
        # looks suspiciously coarse, so well-behaved books (TOC roughly
        # tracks spine granularity 1:1, like magazines) never pay for it.
        spine_len = len(self.doc.spine)
        if spine_len > 50 and len(toc_points) < spine_len * 0.1:
            weekday_re = re.compile(
                r"(Sunday|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday),",
                re.IGNORECASE)
            daily_points = []
            for idx, fname in enumerate(self.doc.spine):
                try:
                    text, _links, _images, _anchors, _styles, _pspans = self.doc.get_page(fname)
                except Exception:
                    continue
                # search (not match) within a slightly wider window than
                # just the first ~40 chars -- the first day of each month
                # has a "January" heading before the weekday line (e.g.
                # "January\n \nThursday, January 1"), which an anchored
                # match at position 0 would miss
                if weekday_re.search(text[:80]):
                    daily_points.append((idx, fname, None))
            MIN_DAILY_MATCHES = 20  # a real year's worth is ~300+; this just
                                     # rules out a stray coincidental match
            if len(daily_points) >= MIN_DAILY_MATCHES:
                return daily_points

        if toc_points:
            return toc_points

        # last resort: every spine file is its own "chapter"
        return [(i, f, None) for i, f in enumerate(self.doc.spine)]

    # -------- page layout --------
    def _ensure_page_built(self):
        key = self.state.current_file
        if key == self._page_cache_key and self.state.current_anchor is None:
            return
        self._clear_text_texture_cache()
        # Check RAM cache first (v0.1.48) -- background prefetch may have
        # already parsed this file, saving the main-thread XML parse cost.
        _cached = self._page_text_cache.get(self.state.current_file)
        if _cached is not None:
            text, links, images, anchors, styles, para_spans = _cached
        else:
            try:
                text, links, images, anchors, styles, para_spans = self.doc.get_page(self.state.current_file)
                # v0.1.63: a page that parses to zero text AND zero images
                # is exactly the failure mode the Gutenberg svg-cover bug
                # produced (v0.1.62) -- silently blank, nothing to tell you
                # something's wrong. Log it (once, here, not on cache hits
                # -- see log_render_issue()) and swap in a visible on-screen
                # note rather than leaving a blank reading screen that looks
                # like the app itself is broken.
                if not text.strip() and not images:
                    log_render_issue(self.current_book_path, self.state.current_file,
                                      "page rendered blank (no text, no images)")
                    text = "(This page appears empty -- it may use formatting PicoReader doesn't support yet.)\n"
                self._page_text_cache_put(self.state.current_file,
                                          (text, links, images, anchors, styles, para_spans))
            except (KeyError, ValueError) as e:
                # stale bookmark/link pointing at a file no longer in this epub
                # (e.g. the file on disk was replaced with a different edition)
                _boot_log(f"could not load page {self.state.current_file}: {e}\n")
                fallback = self.doc.spine[0] if self.doc.spine else None
                if fallback and fallback != self.state.current_file:
                    self.state.current_file = fallback
                    self.state.current_anchor = None
                    text, links, images, anchors, styles, para_spans = self.doc.get_page(fallback)
                    self._page_text_cache_put(fallback,
                                              (text, links, images, anchors, styles, para_spans))
                else:
                    text, links, images, anchors, styles, para_spans = "(could not load this page)", [], [], {}, [], []
        self._links = links
        self._images = images
        self._anchors = anchors
        self._styles = styles
        self._para_spans = para_spans
        self._visible_image_keys = {self._img_key(im.src) for im in images}

        combined = [("link", i, l.start, l.end) for i, l in enumerate(links)]
        combined += [("image", i, im.start, im.end) for i, im in enumerate(images)]
        self._combined_spans = combined

        avail_w = SW - _sx(40)

        wrap_key = (key, self.fonts.size_index)
        _cached_wrap = self._wrapped_cache.get(wrap_key)
        if _cached_wrap is not None:
            lines, line_span_map, line_style_runs = _cached_wrap
        else:
            lines, line_span_map, line_style_runs = self._wrap(text, combined, avail_w)
            self._wrapped_cache_put(wrap_key, (lines, line_span_map, line_style_runs))
        self._lines = lines
        self._line_span_map = line_span_map
        self._line_style_runs = line_style_runs
        # Precompute cumulative absolute character offsets once (v0.1.46).
        # draw_reader used to recompute abs offset per line via sum(...range(li)),
        # which is O(n^2) -- severe lag on large pages (NWT chapters: 8000+ lines).
        offs = []
        running = 0
        for ln in lines:
            offs.append(running)
            running += len(ln) + 1   # +1 for the implicit newline separator
        self._line_abs_offsets = offs
        self._page_cache_key = key

        target_char_off = None
        if self.state.current_char_off is not None:
            # v0.1.39: exact-position restore (bookmark/resume-reading).
            # Same line-search as the anchor path below, just driven by a
            # raw character offset instead of a named anchor's offset --
            # this is what makes restore work for a spot the user merely
            # scrolled to, not just a named chapter/link target.
            char_off = self.state.current_char_off
            target_char_off = char_off
            running = 0
            target_line = 0
            for li, line in enumerate(lines):
                running += len(line) + 1
                if running >= char_off:
                    target_line = li
                    break
            self.scroll = max(0, target_line - 2)
        elif self.state.current_anchor and self.state.current_anchor in anchors:
            char_off = anchors[self.state.current_anchor]
            target_char_off = char_off
            running = 0
            target_line = 0
            for li, line in enumerate(lines):
                running += len(line) + 1
                if running >= char_off:
                    target_line = li
                    break
            self.scroll = max(0, target_line - 2)
        self.state.current_anchor = None
        self.state.current_char_off = None
        # v0.1.50: selected_span used to always reset to 0 (document-order
        # first span) here, regardless of where we actually navigated to.
        # For a same-file anchor jump (e.g. the Bible "CHAPTERS:" grid
        # linking to "#link0" right before "Chapter 1"), that meant the
        # cursor stayed on span 0 -- typically a link far above the new
        # scroll position -- and draw_reader's "snap selection to first
        # VISIBLE span" fallback would then grab whatever link happened to
        # be first on screen at the new scroll offset instead of the thing
        # actually navigated to. Confirmed via real on-device screenshots:
        # selecting Genesis chapter 1 scrolled to roughly the right place
        # but left the highlighted cursor on "45" (a leftover chapter-grid
        # number still visible above "Chapter 1"), nowhere near verse 1.
        # Fix: pick the span whose start is at-or-after the anchor/resume
        # char offset we just scrolled to, so the cursor lands on the
        # actual target link (or the next link after it).
        self.selected_span = 0
        if target_char_off is not None and self._combined_spans:
            best_idx, best_start = None, None
            for si, (kind, i, s, e) in enumerate(self._combined_spans):
                if s >= target_char_off and (best_start is None or s < best_start):
                    best_idx, best_start = si, s
            if best_idx is not None:
                self.selected_span = best_idx
        self._prefetch_next_images()
        self._prefetch_adjacent_chapters()  # v0.1.48: pre-parse prev/next chapter text

    def _clear_text_texture_cache(self, renderer=None):
        for tex, w, h in self._text_texture_cache.values():
            SDL.SDL_DestroyTexture(tex)
        self._text_texture_cache.clear()

    def has_pending_image_updates(self):
        """True if any image on the current page is still decoding, so the
        idle render loop knows to keep polling instead of going fully quiet.
        Uses get_status_snapshot() (v0.1.49) -- ONE lock acquisition per
        image instead of two (get() + is_upgrading() separately). Runs
        every frame by design (unchanged) so images never get stuck
        waiting for a button press; this only makes the check cheaper."""
        if not self.images_enabled or not self._images:
            return False
        for im in self._images:
            snap = self.image_loader.get_status_snapshot(self._img_key(im.src))
            if snap["result"] is None or snap["result"] == "loading":
                return True
            if snap["is_upgrading"]:
                return True
        return False

    def _prefetch_next_images(self):
        """Kick off background decode for images on the next page/chapter,
        so by the time the reader turns the page they're often already
        ready instead of showing a fresh 'Loading image...' placeholder."""
        if not self.images_enabled:
            return
        nxt = self.doc.next_in_spine(self.state.current_file)
        if not nxt:
            return

        def _do_prefetch():
            try:
                _text, _links, images, _anchors, _styles, _pspans = self.doc.get_page(nxt)
                for im in images:
                    key = self._img_key(im.src)
                    if self.image_loader.get(key) is None:
                        if self.image_loader.has_full_disk_cache(key):
                            self.image_loader.request(key, None,
                                                       priority=ImageLoader.PRIORITY_PREFETCH)
                        else:
                            jpeg_bytes = self.doc.get_image_bytes(im.src)
                            self.image_loader.request(key, jpeg_bytes,
                                                       priority=ImageLoader.PRIORITY_PREFETCH)
            except Exception as e:
                _boot_log(f"prefetch failed for {nxt}: {e}\n")

        threading.Thread(target=_do_prefetch, daemon=True).start()

    def _page_text_cache_put(self, href, result):
        """LRU insert into _page_text_cache, evicting oldest when full (v0.1.48)."""
        if href in self._page_text_cache:
            self._page_text_cache_order.remove(href)
        elif len(self._page_text_cache) >= self._PAGE_TEXT_CACHE_MAX:
            oldest = self._page_text_cache_order.pop(0)
            self._page_text_cache.pop(oldest, None)
        self._page_text_cache[href] = result
        self._page_text_cache_order.append(href)

    def _wrapped_cache_put(self, wrap_key, result):
        """LRU insert into _wrapped_cache, evicting oldest when full (v0.1.69).
        Same pattern as _page_text_cache_put -- kept as a separate method
        (not merged into one generic helper) so each cache's eviction
        stays simple to reason about independently."""
        if wrap_key in self._wrapped_cache:
            self._wrapped_cache_order.remove(wrap_key)
        elif len(self._wrapped_cache) >= self._WRAPPED_CACHE_MAX:
            oldest = self._wrapped_cache_order.pop(0)
            self._wrapped_cache.pop(oldest, None)
        self._wrapped_cache[wrap_key] = result
        self._wrapped_cache_order.append(wrap_key)

    def _prefetch_adjacent_chapters(self):
        """Background-parse the prev and next chapter files into
        _page_text_cache so L2/R2 jumps skip the main-thread XML cost
        (v0.1.48). Mirrors _prefetch_next_images() pattern. Only fires
        when chapter nav points exist (all books that have chapters).
        Thread-safe: each thread only writes its own href slot; LRU
        eviction uses a simple list (no concurrent writers since prefetch
        threads are daemon and we only fire one at a time per direction)."""
        if not self._chapter_nav_points or not self.doc:
            return
        current_idx = self.doc.spine_index(self.state.current_file)
        spine_indices = [p[0] for p in self._chapter_nav_points]
        import bisect
        pos = bisect.bisect_right(spine_indices, current_idx) - 1
        candidates = []
        # v0.1.69: widened from (-1, +1) to (-2, -1, +1, +2) -- Kaleb reads
        # ahead across more than just the immediate next chapter in a
        # sitting, so a 1-chapter prefetch window meant every second jump
        # was still a cold parse. RAM cost is bounded the same way as
        # before: candidates are skipped if already cached, and the
        # overall _page_text_cache is capped at 200 entries regardless
        # (v0.1.68), so widening this window can't grow memory beyond
        # that existing cap -- it just fills the cache with more USEFUL
        # entries sooner.
        for delta in (-2, -1, +1, +2):
            tp = pos + delta
            if 0 <= tp < len(self._chapter_nav_points):
                _, fname, _ = self._chapter_nav_points[tp]
                if fname not in self._page_text_cache:
                    candidates.append(fname)
        if not candidates:
            return

        doc_ref = self.doc  # capture for thread closure

        def _do_prefetch():
            for fname in candidates:
                try:
                    result = doc_ref.get_page(fname)
                    self._page_text_cache_put(fname, result)
                except Exception as e:
                    _boot_log(f"chapter prefetch failed for {fname}: {e}\n")

        threading.Thread(target=_do_prefetch, daemon=True).start()

    # -------- whole-book pre-render (Storage screen action) --------
    def start_prerender(self):
        """Kicks off a background walk of the ENTIRE book -- every spine
        file, every image -- enqueuing each one at PRIORITY_PRERENDER.
        Deliberately reuses the same single-worker priority queue that
        already serves normal reading (PRIORITY_VISIBLE/PREFETCH), rather
        than a separate thread pool: that queue already guarantees real
        reading needs always jump ahead of background work, so this can
        run for a long time (a full year's daily-text book, hundreds of
        images) without ever starving the UI or making scrolling/menu
        input feel unresponsive -- it just fills in the gaps."""
        if self._prerender_active:
            return
        book_id_value = self._book_id
        self._prerender_active = True
        self._prerender_scanning = True
        self._prerender_cancel = False
        self._prerender_total = 0
        self._prerender_done = 0
        self._prerender_book_id = book_id_value
        self._prerender_keys = []

        def _walk_and_enqueue():
            try:
                seen_srcs = set()
                # Phase 1: walk spine, discover images, update keys/total live
                # so draw_storage shows a live "Scanning..." count not 0/0.
                for fname in self.doc.spine:
                    if self._prerender_cancel or self._prerender_book_id != book_id_value:
                        return
                    try:
                        _text, _links, images, _anchors, _styles, _pspans = self.doc.get_page(fname)
                    except Exception:
                        continue
                    for im in images:
                        if im.src in seen_srcs:
                            continue
                        seen_srcs.add(im.src)
                        self._prerender_keys.append(self._img_key(im.src))
                        self._prerender_total += 1
                        self.dirty = True  # refresh Storage screen during scan
                # Phase 2: enqueue each image for background decode
                self._prerender_scanning = False
                for src in list(seen_srcs):
                    if self._prerender_cancel or self._prerender_book_id != book_id_value:
                        return
                    key = self._img_key(src)
                    if self.image_loader.is_full_res(key):
                        continue
                    if self.image_loader.has_full_disk_cache(key):
                        self.image_loader.request(key, None,
                                                   priority=ImageLoader.PRIORITY_PRERENDER)
                    else:
                        try:
                            jpeg_bytes = self.doc.get_image_bytes(src)
                        except Exception:
                            continue
                        self.image_loader.request(key, jpeg_bytes,
                                                   priority=ImageLoader.PRIORITY_PRERENDER)
            except Exception as e:
                _boot_log(f"prerender failed: {e}\n")
            finally:
                if self._prerender_book_id == book_id_value:
                    self._prerender_scanning = False
                    self._prerender_active = False
                    self.dirty = True

        self._prerender_thread = threading.Thread(target=_walk_and_enqueue, daemon=True)
        self._prerender_thread.start()

    def cancel_prerender(self):
        self._prerender_cancel = True
        self._prerender_active = False

    def prerender_progress(self):
        """Returns (done, total, scanning) where:
          done    = images fully decoded so far
          total   = images discovered so far (grows during scan phase)
          scanning = True while spine walk is still in progress
        done is checked against real decode results, not just queue depth.

        v0.1.65 fix (Kaleb reported): after a crash mid-prerender, restarting
        "Pre-render Book Images" LOOKED like it started over from 0% even
        though the on-disk image cache (IMG_CACHE_DIR, survives crashes/
        reboots) already had most images from the previous run -- and
        _walk_and_enqueue() WAS already correctly skipping the expensive
        raw-JPEG-decode step for those via has_full_disk_cache(). The real
        problem was just this progress count: is_full_res() only checks
        the in-memory _results dict, which starts empty every fresh
        process, so every disk-cached image still had to be individually
        re-touched through the single-worker queue (a real disk read each,
        serialized one at a time) before the bar would count it -- slow
        and visually indistinguishable from a genuine full restart, even
        though no JPEG was actually being re-decoded.
        Fix: also count a key as done if it's confirmed sitting on disk
        (has_full_disk_cache), without waiting for the worker to actually
        reload its bytes into RAM. Cheap (an os.path.exists check, no
        decode, no RAM cost) and makes the bar reflect prior work
        instantly on restart instead of re-draining the queue first."""
        total = self._prerender_total
        scanning = self._prerender_scanning
        if not total or not self._prerender_keys:
            return 0, total, scanning
        done = sum(1 for k in self._prerender_keys
                   if self.image_loader.is_full_res(k)
                   or self.image_loader.has_full_disk_cache(k))
        return done, total, scanning

    def _measure_words(self, para):
        """Split a paragraph into words plus each word's character offset
        within the paragraph (needed to map wrapped lines back to the
        original link/image span positions)."""
        words = para.split(" ")
        starts = []
        search_pos = 0
        for w in words:
            if w == "":
                starts.append(search_pos)
                continue
            start = para.find(w, search_pos)
            if start == -1:
                start = search_pos
            starts.append(start)
            search_pos = start + len(w)
        return words, starts

    def _line_spans(self, wline, abs_start, char_span):
        ranges = []
        cur = -1
        rstart = None
        for c in range(len(wline)):
            gidx = abs_start + c
            lk = char_span[gidx] if gidx < len(char_span) else -1
            if lk != cur:
                if cur != -1:
                    ranges.append((rstart, c, cur))
                cur = lk
                rstart = c
        if cur != -1:
            ranges.append((rstart, len(wline), cur))
        return ranges

    def _line_segments(self, line, ranges, style_runs):
        """Merges link/image ranges (drives color + selection highlight)
        and bold/italic style runs (drives font choice) into one fine-
        grained segment list, so a character that's e.g. both a link AND
        bold gets the link's color with the bold font -- neither
        dimension silently overrides the other. Returns
        [(seg_start, seg_end, sidx, bold, italic)] where sidx is -1 for
        "not a link/image", matching _line_span_map's existing convention."""
        n = len(line)
        if n == 0:
            return []
        cuts = {0, n}
        for (s, e, _sidx) in ranges:
            cuts.add(max(0, min(s, n)))
            cuts.add(max(0, min(e, n)))
        for (s, e, _b, _i) in style_runs:
            cuts.add(max(0, min(s, n)))
            cuts.add(max(0, min(e, n)))
        points = sorted(cuts)
        segments = []
        for a, b in zip(points, points[1:]):
            if a >= b:
                continue
            sidx = -1
            for (s, e, ridx) in ranges:
                if s <= a < e:
                    sidx = ridx
                    break
            bold = italic = False
            for (s, e, bb, ii) in style_runs:
                if s <= a < e:
                    bold, italic = bb, ii
                    break
            segments.append((a, b, sidx, bold, italic))
        return segments

    def _compute_line_style_runs(self, line_text, abs_start):
        """Splits one wrapped line into (run_start, run_end, bold, italic)
        runs in LINE-LOCAL coordinates, from self._styles (absolute-offset
        StyleSpans built by epub_engine.get_page()). Overlapping spans
        (e.g. <strong><em>...</em></strong>) combine via OR per character
        -- text that's both bold and italic renders as both, rather than
        one style silently winning. Returns a single (0, n, False, False)
        run for the whole line in the common no-styling case, cheaply --
        this only does the character-level work when self._styles is
        non-empty."""
        n = len(line_text)
        if not self._styles or n == 0:
            return [(0, n, False, False)]
        bold_flags = [False] * n
        italic_flags = [False] * n
        line_end = abs_start + n
        for sp in self._styles:
            if sp.end <= abs_start or sp.start >= line_end:
                continue
            s = max(sp.start, abs_start) - abs_start
            e = min(sp.end, line_end) - abs_start
            for c in range(s, e):
                if sp.bold:
                    bold_flags[c] = True
                if sp.italic:
                    italic_flags[c] = True
        runs = []
        run_start = 0
        for c in range(1, n + 1):
            if c == n or bold_flags[c] != bold_flags[run_start] or italic_flags[c] != italic_flags[run_start]:
                runs.append((run_start, c, bold_flags[run_start], italic_flags[run_start]))
                run_start = c
        return runs

    def _word_width(self, word, abs_word_start):
        """Measures a word's rendered width using the SAME font it will
        actually be drawn with at each character (v0.1.36 fix). Previously
        _wrap() measured every word with the plain regular font
        (self.fonts.body), even words that would later render bold/italic
        via draw_reader()'s per-segment app.fonts.body_styled(bold, italic)
        call. That mismatch mattered because the bold font renders
        measurably wider glyphs for identical text (confirmed at the
        FreeType level in v0.1.35: 108px vs 97px for the same string, ~11%
        wider) -- so a line judged to "fit" avail_w_px using the regular
        font's narrower measurement could render wider than the screen
        once its bold/italic runs were actually drawn, pushing text past
        the right edge instead of wrapping it to the next line. This
        splits the word into same-style sub-runs (usually just one, since
        StyleSpans almost always cover whole words) and measures each with
        its real font via body_styled(), matching draw_reader() exactly.
        Falls back to a single self.fonts.body measurement when there are
        no styles on the page at all, so the unstyled-text (majority) case
        pays no extra cost."""
        n = len(word)
        if not self._styles or n == 0:
            return text_width(self.fonts.body, word)

        def style_at(i):
            abs_i = abs_word_start + i
            b = it = False
            for sp in self._styles:
                if sp.start <= abs_i < sp.end:
                    if sp.bold:
                        b = True
                    if sp.italic:
                        it = True
            return b, it

        total = 0
        run_start = 0
        run_style = style_at(0)
        for c in range(1, n + 1):
            style = style_at(c) if c < n else None
            if c == n or style != run_style:
                sub = word[run_start:c]
                font = self.fonts.body_styled(*run_style)
                total += text_width(font, sub)
                run_start = c
                run_style = style
        return total

    def _wrap(self, text, combined, avail_w_px):
        """Word-wrap text to fit avail_w_px pixels, measuring each word's
        actual rendered width rather than approximating via a fixed
        character count -- character-count wrapping (using a wide
        reference character like 'M') systematically undercounts how much
        text fits per line, wasting screen width."""
        span_ranges = [(s, e) for (_, _, s, e) in combined]
        char_span = [-1] * len(text)
        for i, (s, e) in enumerate(span_ranges):
            for c in range(s, min(e, len(text))):
                char_span[c] = i

        space_w = text_width(self.fonts.body, " ") or max(4, _sx(6))

        lines = []
        line_span_map = []
        line_style_runs = []
        offset = 0
        for para in text.split("\n"):
            if para.strip() == "":
                lines.append("")
                line_span_map.append([])
                line_style_runs.append([(0, 0, False, False)])
                offset += len(para) + 1
                continue

            words, starts = self._measure_words(para)
            cur_words = []
            cur_start_idx = None
            cur_w = 0

            for wi, w in enumerate(words):
                if w == "":
                    continue
                w_w = self._word_width(w, offset + starts[wi])
                add_w = w_w + (space_w if cur_words else 0)
                if cur_words and cur_w + add_w > avail_w_px:
                    line_text = " ".join(cur_words)
                    abs_start = offset + starts[cur_start_idx]
                    lines.append(line_text)
                    line_span_map.append(self._line_spans(line_text, abs_start, char_span))
                    line_style_runs.append(self._compute_line_style_runs(line_text, abs_start))
                    cur_words = [w]
                    cur_start_idx = wi
                    cur_w = w_w
                else:
                    if not cur_words:
                        cur_start_idx = wi
                    cur_words.append(w)
                    cur_w += add_w

            if cur_words:
                line_text = " ".join(cur_words)
                abs_start = offset + starts[cur_start_idx]
                lines.append(line_text)
                line_span_map.append(self._line_spans(line_text, abs_start, char_span))
                line_style_runs.append(self._compute_line_style_runs(line_text, abs_start))

            offset += len(para) + 1

        return lines, line_span_map, line_style_runs

    def visible_span_indices(self, body_rows):
        """Which link/image spans are actually visible on screen right now.
        Must walk the SAME way draw_reader() does: an image consumes
        IMG_BOX_ROWS visual rows but is only one entry in self._lines, so a
        naive 1-row-per-line loop here would disagree with what's actually
        drawn (and could offer up links for selection that aren't visible,
        or skip ones that are). Row cost comes from _rows_for_li() -- the
        same single source of truth draw_reader() and page_down/page_up()
        use, so this automatically respects text-only mode too."""
        idxs = []
        row = 0
        li = self.scroll
        while row < body_rows:
            if li >= len(self._lines):
                break
            ranges = self._line_span_map[li]
            for (_, _, sidx) in ranges:
                if sidx != -1 and sidx not in idxs:
                    idxs.append(sidx)
            row += self._rows_for_li(li)
            li += 1
        return idxs

    def get_image_texture(self, renderer, image_span):
        key = self._img_key(image_span.src)
        cached = self._image_textures.get(key)
        if cached:
            self._image_textures.move_to_end(key)  # mark as recently used

        # Single lock acquisition for the whole status check (v0.1.49) --
        # was up to 2 separate lock calls (get() then get_with_full_flag())
        # on the success path. Same atomicity guarantee as the old
        # get_with_full_flag() (result and is_full always come from the
        # same snapshot, so a full-res decode landing mid-check can't
        # cause a blurry thumb to get permanently tagged as full-res).
        snap = self.image_loader.get_status_snapshot(key)
        result = snap["result"]

        if result is None:
            if self.image_loader.has_full_disk_cache(key):
                # Already decoded in a previous session -- skip reading the
                # raw JPEG out of the epub zip entirely. jpeg_bytes=None
                # signals _process() to load straight from the disk cache.
                self.image_loader.request(key, None)
            else:
                try:
                    jpeg_bytes = self.doc.get_image_bytes(image_span.src)
                    self.image_loader.request(key, jpeg_bytes)
                except Exception as e:
                    _boot_log(f"could not read image bytes for {key}: {e}\n")
            return cached  # nothing yet, caller shows placeholder

        if result in ("loading", "error"):
            if cached:
                return cached  # keep showing whatever we had (thumb) while full-res upgrades
            return "error" if result == "error" else None

        is_full = snap["is_full"]
        rgb, w, h = result

        # only rebuild the texture if we don't have one, or a better-res one arrived
        if cached and cached[3] == is_full:
            return cached

        buf = ctypes.create_string_buffer(rgb, len(rgb))
        surf = SDL.SDL_CreateRGBSurfaceFrom(
            buf, w, h, 24, w * 3,
            0x0000FF, 0x00FF00, 0xFF0000, 0
        )
        if not surf:
            return cached
        tex = SDL.SDL_CreateTextureFromSurface(renderer, surf)
        SDL.SDL_FreeSurface(surf)
        if not tex:
            return cached
        if cached:
            SDL.SDL_DestroyTexture(cached[0])
        entry = (tex, w, h, is_full, buf)  # keep buf alive (referenced by texture upload)
        self._image_textures[key] = entry
        self._image_textures.move_to_end(key)
        self._evict_image_textures_if_needed()
        return entry

    def _evict_image_textures_if_needed(self):
        while len(self._image_textures) > self.MAX_IMAGE_TEXTURES:
            old_key, old_entry = self._image_textures.popitem(last=False)  # evict least-recently-used
            SDL.SDL_DestroyTexture(old_entry[0])


    def follow_selected(self):
        if not self._combined_spans or not (0 <= self.selected_span < len(self._combined_spans)):
            return
        kind, i, _, _ = self._combined_spans[self.selected_span]
        if kind == "link":
            link = self._links[i]
            if link.target_file:
                self._scroll_stack.append(self.scroll)
                self.state.follow_link(link)
                self.scroll = 0
                self.selected_span = 0
                self._page_cache_key = None

    def go_back(self):
        if self.state and self.state.go_back():
            self.scroll = self._scroll_stack.pop() if self._scroll_stack else 0
            self.selected_span = 0
            self._page_cache_key = None
            return True
        return False

    def _rows_for_li(self, li):
        """Visual row cost of one _lines[] entry: IMG_BOX_ROWS for an
        image-only line, 1 for ordinary text. Mirrors the exact
        classification draw_reader() and visible_span_indices() use, so
        every place that walks lines agrees on how much screen space
        each one actually takes. In text-only mode (images_enabled=False)
        an image line renders as a single compact placeholder line
        instead of the full box, so it only costs 1 row here too --
        keeping this in sync with draw_reader() is what makes paging
        never skip/cut off content (same class of bug fixed in v0.1.23)."""
        if not self.images_enabled:
            return 1
        ranges = self._line_span_map[li]
        if len(ranges) == 1:
            s, e, sidx = ranges[0]
            if sidx != -1 and self._combined_spans[sidx][0] == "image" and (e - s) >= len(self._lines[li]):
                return IMG_BOX_ROWS
        return 1

    def page_down(self, body_rows):
        """Advance to the next screenful. Walks li-by-li accumulating the
        REAL per-line visual-row cost (an image line costs IMG_BOX_ROWS,
        not 1) instead of the old `scroll += body_rows`, which added a
        visual-row count directly onto self.scroll even though scroll is
        a _lines[] index -- any image on the page threw that off,
        sometimes over-advancing past an image entirely (skipping it),
        sometimes under-advancing so the same image reappeared. Also
        stops BEFORE an image that wouldn't fully fit in the remaining
        space on this screen, matching the same rule now in
        draw_reader(), so a page turn never lands you on a screen that
        cut an image off midway -- that image becomes the first thing
        shown on the next page instead."""
        n = len(self._lines)
        if not n:
            return
        li = self.scroll
        row = 0
        while li < n:
            cost = self._rows_for_li(li)
            if row > 0 and row + cost > body_rows:
                break
            row += cost
            li += 1
            if row >= body_rows:
                break
        self.scroll = min(li, max(0, n - 1))

    def page_up(self, body_rows):
        """Backward counterpart to page_down() -- walks li's downward
        from just before the current scroll, accumulating the same
        per-line row cost, so it lands exactly where a page_down() from
        the resulting position would return here. Fixes the same
        unit-mismatch page_down() had (old code did `scroll -=
        body_rows`, a visual-row count subtracted from a line-index)."""
        n = len(self._lines)
        if not n:
            return
        li = self.scroll - 1
        if li < 0:
            self.scroll = 0
            return
        row = 0
        while li >= 0:
            cost = self._rows_for_li(li)
            if row + cost > body_rows:
                break
            row += cost
            li -= 1
        self.scroll = max(0, li + 1)

    def next_chapter(self):
        return self._jump_chapter(+1)

    def prev_chapter(self):
        return self._jump_chapter(-1)

    def _jump_chapter(self, direction):
        if not self._chapter_nav_points:
            return False
        current_idx = self.doc.spine_index(self.state.current_file)
        spine_indices = [p[0] for p in self._chapter_nav_points]
        # find where we currently sit among nav points
        pos = bisect.bisect_right(spine_indices, current_idx) - 1
        if pos < 0:
            # Currently before the first real chapter/day entirely (e.g.
            # on a cover/front-matter page). "Next chapter" must land ON
            # chapter 0, not skip past it -- clamping pos to 0 here (the
            # old behavior) made target_pos = pos+1 jump straight to
            # chapter 1, permanently skipping day/chapter 1 for any book
            # with front matter (confirmed: this is why R2 from the cover
            # of a daily-text epub landed on Jan 2, never Jan 1).
            target_pos = 0 if direction > 0 else -1
        else:
            target_pos = pos + direction
        if target_pos < 0 or target_pos >= len(self._chapter_nav_points):
            return False
        _, fname, anchor = self._chapter_nav_points[target_pos]
        self.state.goto(fname, anchor, push_history=False)
        self.scroll = 0
        self.selected_span = 0
        self._page_cache_key = None
        return True

    def _toc_index_for_current_position(self, toc_flat):
        """Index into toc_flat of the entry nearest-at-or-before the current
        reading position, so opening the Chapters screen lands on 'you are
        here' instead of always the very top of a potentially very long
        list (66 Bible books, 741 daily entries, etc.)."""
        if not self.doc or not self.state or not toc_flat:
            return 0
        cur_idx = self.doc.spine_index(self.state.current_file)
        best_i, best_spine_idx = 0, -1
        for i, entry in enumerate(toc_flat):
            f = entry.href.split("#")[0] if "#" in entry.href else entry.href
            idx = self.doc.spine_index(f)
            if idx != -1 and idx <= cur_idx and idx > best_spine_idx:
                best_spine_idx = idx
                best_i = i
        return best_i

    def _current_location_label(self):
        """Best-effort human-readable label for the current reading position
        -- e.g. 'Psalms 91' for a Bible book, or the article title for a
        magazine -- instead of the raw internal spine filename (something
        like '1001061123-split20.xhtml'), which means nothing to a reader
        and made every bookmark look like it was only labeled by its
        save-date (the one part of the old label that WAS readable)."""
        import re
        if not self.doc or not self.state:
            return "Bookmark"
        cur_idx = self.doc.spine_index(self.state.current_file)

        # Section/book title: nearest top-level TOC entry at or before here.
        flat = flatten_toc(self.doc.toc)
        section_title = None
        best_idx = -1
        for entry in flat:
            f = entry.href.split("#")[0] if "#" in entry.href else entry.href
            idx = self.doc.spine_index(f)
            if idx != -1 and idx <= cur_idx and idx > best_idx:
                best_idx = idx
                section_title = entry.title

        # Chapter number: nearest structural chapterN anchor at or before here
        # (same index _jump_chapter uses for L2/R2) -- gives the "91" in
        # "Psalms 91" for Bible books. Magazines/articles won't have this,
        # and just fall back to the section title alone.
        chapter_num = None
        if self._chapter_nav_points:
            spine_indices = [p[0] for p in self._chapter_nav_points]
            pos = bisect.bisect_right(spine_indices, cur_idx) - 1
            if pos >= 0:
                _, _, anchor = self._chapter_nav_points[pos]
                if anchor:
                    m = re.search(r"(\d+)$", anchor)
                    if m:
                        chapter_num = m.group(1)

        if section_title:
            clean_title = section_title.replace(" Outline", "")
            if chapter_num:
                return f"{clean_title} {chapter_num}"
            return clean_title
        return self.state.current_file.split("/")[-1]

    def set_status(self, msg, duration=2.5):
        self.status_msg = msg
        self.status_until = time.time() + duration

    def _current_char_offset(self):
        """Character offset of the first line currently on screen (inverse
        of the restore math in _ensure_page_built()) -- captured fresh at
        bookmark/save time so it always reflects exactly where the user
        is, independent of whether a named anchor happens to apply here.
        Returns None if there's no page built yet (nothing to measure).

        The +1 matters: the restore loop finds the first line whose
        CUMULATIVE length (running >= char_off) reaches the target, and
        cumulative-through-line-(N-1) is numerically identical to "the
        start offset of line N" -- so capturing the bare start offset
        made restore land one line short of the actual scroll position
        every time (verified: 23/24 sampled positions off by exactly one
        line before this +1). Adding 1 pushes char_off just past that
        boundary so the same-line cumulative total is the first to
        satisfy >=, landing on the correct line. Verified exact (0
        mismatches) across all 72 possible scroll positions on a real
        chapter page."""
        if not getattr(self, "_lines", None):
            return None
        running = 0
        for li, line in enumerate(self._lines):
            if li >= self.scroll:
                return running + 1
            running += len(line) + 1
        return running + 1

    def bookmark_here(self):
        if not self.current_book_path or not self.state:
            return
        label = self._current_location_label()
        char_off = self._current_char_offset()
        result = add_bookmark(self.current_book_path, self.state.current_file,
                               self.state.current_anchor, label, char_off=char_off)
        if result == "added":
            self.set_status(f'Bookmarked "{label}"')
        elif result == "updated":
            self.set_status(f'Bookmark updated: "{label}"')
        elif result == "limit":
            self.set_status(
                f"Bookmark limit reached ({MAX_BOOKMARKS_PER_BOOK}) -- "
                "delete one from the Bookmarks screen first", duration=3.5)

    def save_progress(self):
        if self.current_book_path and self.state:
            char_off = self._current_char_offset()
            save_last_position(self.current_book_path, self.state.current_file,
                                self.state.current_anchor, char_off=char_off)


# ============================================================
# Rendering
# ============================================================
HINT_H_BASE = 40  # single-line height at the reference 18pt UI size
HINT_H_MAX_LINES = 3  # Absolute ceiling on hint bar lines. In practice the
                       # bar only uses 1-2 (see _hint_lines_needed()) --
                       # this is just the outer bound _hint_pt()'s font-
                       # shrink fallback is allowed to target before giving
                       # up and letting a line overflow width.

# The two longest hint strings in the app, used only to calibrate hint
# font size (_hint_pt()) and line count (_hint_lines_needed()) per global
# Font Size step -- NOT drawn directly. Keep in sync if a hint string grows.
_HINT_CALIBRATION_TEXTS = (
    "D-PAD Select/Scroll  A Follow  B Back  L/R Page  L2/R2 Chapter  Y Fast x10  X Menu  START Bookmark",
    "A Open  Y Sort  X Pin  SELECT Delete  L/R Font Size  L2 Download  START Menu  B Quit",
)


def _wrap_hint_text(font, text, max_w, max_lines=HINT_H_MAX_LINES):
    """Greedy word-wrap of the hint bar string (items separated by regular
    spaces, e.g. 'D-PAD Select/Scroll  A Follow  B Back ...') into as few
    lines as fit max_w, capped by max_lines.
    v0.1.61 BUG FIX: the previous version, on reaching the last allowed
    line, set cur = w (just the ONE word that overflowed) and then broke
    out of the loop entirely -- silently discarding every word after it.
    That's the actual cause of the clipped hint bar Kaleb reported (an
    orphaned "X" or "Y" alone on the last line): it wasn't a rendering
    overflow, the words were never being added at all. Confirmed by
    reproducing it directly: word counts drawn vs. total dropped words at
    21pt+ before this fix. Now the last allowed line keeps ALL remaining
    words appended (may exceed max_w and get renderer-clipped as a last
    resort) rather than ever dropping content outright."""
    words = text.split(" ")
    lines, cur = [], ""
    i = 0
    while i < len(words):
        w = words[i]
        trial = (cur + " " + w) if cur else w
        if len(lines) == max_lines - 1:
            # Last allowed line: pack everything remaining here rather
            # than dropping it. May overflow max_w -- acceptable, since
            # losing hint items entirely is worse than a visually tight
            # last line.
            cur = trial
            i += 1
            continue
        if text_width(font, trial) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
        i += 1
    if cur:
        lines.append(cur)
    return lines


def _hint_pt(fonts):
    """v0.1.60: point size to use for the hint bar at the CURRENT global
    Font Size setting -- normally just fonts.ui_small's size, but stepped
    down (floor 11pt) if even HINT_H_MAX_LINES=3 lines at max width isn't
    enough to fit the longest known hint strings (_HINT_CALIBRATION_TEXTS).
    This keeps hint_height() a pure function of the global size_index only
    (same value everywhere, still), it just may pick a smaller hint font at
    the top 1-2 Font Size steps than the rest of the UI uses. Cached per
    size_index on the FontManager instance so this isn't recomputed every
    frame."""
    if not fonts:
        return None
    cache = getattr(fonts, "_hint_pt_cache", None)
    if cache is None:
        cache = fonts._hint_pt_cache = {}
    if fonts.size_index in cache:
        return cache[fonts.size_index]
    base_pt = max(11, FontManager.SIZE_STEPS[fonts.size_index] - 4)  # == ui_small's pt
    max_w = SW - _sx(28)
    pt = base_pt
    while pt >= 11:
        font = fonts._get(pt)
        if font and all(
            len(_wrap_hint_text_unbounded(font, t, max_w)) <= HINT_H_MAX_LINES
            for t in _HINT_CALIBRATION_TEXTS
        ):
            break
        pt -= 2
    pt = max(11, pt)
    cache[fonts.size_index] = pt
    return pt


def _wrap_path_message(font, text, max_w):
    """Like _wrap_hint_text_unbounded, but also breaks on '/' when a
    single space-delimited token (e.g. a long filesystem path with no
    spaces in it) is wider than max_w on its own -- plain word-wrap
    can't help there since the whole path IS one "word". Found via
    Kaleb's report that the Library empty-state message ("No .epub
    files found in <LIBRARY_DIR>") still overflowed at large Font Size
    even after switching to _wrap_hint_text_unbounded, because the real
    on-device path (/run/muos/storage/application/PicoReader/library)
    has no spaces at all. Slashes are kept attached to the END of each
    segment (a/b/c -> "a/", "b/", "c") so the wrap reads naturally.
    Falls back to a character-level break for the rare case a single
    segment (no further slashes) is STILL too wide alone -- shouldn't
    happen for any real muOS path, but guarantees correctness rather
    than relying on paths always being reasonable."""
    def break_by_char(tok):
        out, cur = [], ""
        for ch in tok:
            trial = cur + ch
            if text_width(font, trial) <= max_w or not cur:
                cur = trial
            else:
                out.append(cur)
                cur = ch
        return out + ([cur] if cur else [])

    raw_words = text.split(" ")
    tokens = []
    for w in raw_words:
        if text_width(font, w) <= max_w or "/" not in w:
            tokens.append(w)
        else:
            parts = w.split("/")
            tokens.extend([p + "/" for p in parts[:-1]] + [parts[-1]])
    # any single token still too wide alone (no slash left to split on)
    # gets broken by character as a last resort
    final_tokens = []
    for tok in tokens:
        if text_width(font, tok) <= max_w:
            final_tokens.append(tok)
        else:
            final_tokens.extend(break_by_char(tok))
    lines, cur = [], ""
    for tok in final_tokens:
        if not tok:
            continue
        sep = "" if (not cur or cur.endswith("/")) else " "
        trial = cur + sep + tok
        if text_width(font, trial) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = tok
    if cur:
        lines.append(cur)
    return lines


def _wrap_hint_text_unbounded(font, text, max_w):
    """Same greedy wrap as _wrap_hint_text but without the line cap --
    used only by _hint_pt() to measure how many lines a calibration string
    actually needs at a candidate font size."""
    words = text.split(" ")
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w) if cur else w
        if text_width(font, trial) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _hint_lines_needed(fonts):
    """v0.1.61: how many lines the hint bar actually needs at the CURRENT
    global Font Size -- calibrated against the two longest hint strings in
    the app (_HINT_CALIBRATION_TEXTS), capped at HINT_H_MAX_LINES. Still a
    pure function of size_index only (not of any specific screen's hint
    text), so the v0.1.52 overlap-safety invariant holds: every screen
    reserves/fills the exact same height for a given Font Size. This
    replaces always reserving the HINT_H_MAX_LINES worst case -- Kaleb
    didn't want a permanently 3-line-thick bar on the 720x720 screen at
    small/medium Font Sizes where 1 line is all that's ever needed (only
    24pt+ actually needs 2; nothing needs 3 once _hint_pt()'s shrink-first
    step is applied). Cached per size_index."""
    if not fonts:
        return 1
    cache = getattr(fonts, "_hint_lines_cache", None)
    if cache is None:
        cache = fonts._hint_lines_cache = {}
    if fonts.size_index in cache:
        return cache[fonts.size_index]
    pt = _hint_pt(fonts)
    font = fonts._get(pt) if pt else None
    max_w = SW - _sx(28)
    if font:
        needed = max(
            len(_wrap_hint_text_unbounded(font, t, max_w))
            for t in _HINT_CALIBRATION_TEXTS
        )
    else:
        needed = HINT_H_MAX_LINES
    needed = max(1, min(needed, HINT_H_MAX_LINES))
    cache[fonts.size_index] = needed
    return needed


def hint_height(fonts):
    """Hint bar height in design units (pre-_sy scaling) -- v0.1.52:
    reserves the SAME height for the CURRENT font size regardless of what
    text any particular screen's hint bar actually needs. This is a
    function of font size only, not of any specific hint string or draw
    order, which is what makes it safe: every screen computes the exact
    same value, so a screen with a short hint can never leave part of a
    previous (taller) screen's hint text uncleared underneath it -- the
    bug that caused the popup MENU's hint to visibly overlap the reader's
    hint text at max Font Size.
    v0.1.60: uses _hint_pt() (may be smaller than ui_small at max Font
    Size) so the reserved height matches what draw_hint() actually uses.
    v0.1.61: uses _hint_lines_needed() (1-3, calibrated per Font Size)
    instead of always the HINT_H_MAX_LINES worst case -- was making the
    hint bar permanently 3 lines thick on the 720x720 screen even at
    small Font Size where 1 line is all that's ever needed."""
    pt = _hint_pt(fonts)
    lines = _hint_lines_needed(fonts)
    if fonts and pt:
        font = fonts._get(pt)
        line_h_design = TTF.TTF_FontHeight(font) / _SY
    else:
        line_h_design = HINT_H_BASE * 0.6
    return line_h_design * lines + HINT_H_BASE * 0.35


def _status_bar_h(fonts):
    """Height of the transient status-message bar (e.g. 'Font size: 32pt
    (largest)') -- v0.1.54. Was a fixed _sy(30)/_sy(22) pair sized for the
    old fixed-size UI font; at max Font Size the now-larger ui_small text
    no longer fit inside that fixed box and visually spilled into the
    hint bar directly below it (confirmed via Kaleb's on-device
    screenshot: 'Font size: 32pt (largest)' overlapping the hint text).
    Scales the same way _row_h() does."""
    return _row_h(fonts.ui_small, pad=10)


IMG_BOX_ROWS = 14  # sized to actually use the FULL_N=4 decoded resolution
                    # (was 6 -- that shrank a typical 1200x600 photo to ~48%
                    # of its decoded size, wasting more than half the decode
                    # work). Shared at module level so visible_span_indices()
                    # (link-selection scope) and draw_reader() (actual pixels)
                    # never disagree about how much visual space an image
                    # takes -- they used to compute this independently and
                    # drift apart.


def _round_top_corners_to_bg(renderer, x, y, w, radius):
    """"Rounds" the top-left/top-right corners of whatever was just
    drawn at (x, y, w, ...) by painting a quarter-circle of COL_BG back
    over each corner -- used for the hint bar (Kaleb's request: make
    the reading area above the hint bar read as having a curved bottom
    edge). Doesn't touch the bottom corners since those sit flush with
    the screen's own physical edge, where rounding wouldn't be visible.
    Reuses the same per-row quarter-circle math as fill_rect_rounded(),
    just inverted (paints the OUTSIDE-the-curve pixels back to
    background instead of keeping them as the rect's own color) --
    works because every screen already fills COL_BG behind the hint
    bar before draw_hint() runs, so "erase to COL_BG" is always
    correct here specifically."""
    if radius <= 0:
        return
    SDL.SDL_SetRenderDrawColor(renderer, COL_BG.r, COL_BG.g, COL_BG.b, COL_BG.a)
    for row in range(radius):
        dy = radius - row
        dx = int(math.sqrt(max(0, radius * radius - dy * dy)))
        inset = radius - dx
        if inset <= 0:
            continue
        left = Rect(x, y + row, inset, 1)
        SDL.SDL_RenderFillRect(renderer, ctypes.byref(left))
        right = Rect(x + w - inset, y + row, inset, 1)
        SDL.SDL_RenderFillRect(renderer, ctypes.byref(right))


def draw_hint(renderer, fonts, text):
    pt = _hint_pt(fonts)
    font = fonts._get(pt) if pt else fonts.ui_small
    max_w = SW - _sx(28)
    h = hint_height(fonts)
    max_lines = _hint_lines_needed(fonts)
    lines = _wrap_hint_text(font, text, max_w, max_lines) or [""]
    top_y = SH - _sy(h)
    # Always fill the FULL reserved area (not just what these lines need)
    # so nothing from a previous, taller hint draw can bleed through.
    fill_rect(renderer, 0, top_y, SW, _sy(h), COL_HINT_BG)
    _round_top_corners_to_bg(renderer, 0, top_y, SW, CORNER_RADIUS)
    row_h = _sy(h) / max_lines
    for li, line in enumerate(lines):
        render_text(renderer, font, line, COL_HINT_TEXT, _sx(14),
                    top_y + int(row_h * li) + _sy(9))


def draw_library(renderer, app):
    fill_rect(renderer, 0, 0, SW, SH, COL_BG)
    # v0.1.57: heading/sort-label/first-row Y positions used to be fixed
    # (_sy(16)/_sy(48)/_sy(70)) -- fine at the old fixed UI font size, but
    # once ui_heading/ui_small grew with Font Size the gaps between them
    # became too small and the "Sort:" line started overlapping the first
    # row's selection highlight (confirmed via Kaleb's on-device
    # screenshot). Now spaced using each line's actual font height.
    heading_y = _sy(16)
    render_text(renderer, app.fonts.ui_heading, "LIBRARY", COL_ACCENT, _sx(20), heading_y)
    sort_y = heading_y + TTF.TTF_FontHeight(app.fonts.ui_heading) + _sy(4)
    render_text(renderer, app.fonts.ui_small, f"Sort: {LIBRARY_SORT_LABELS[app.lib_sort_mode]}",
                COL_DIM, _sx(20), sort_y)

    row_h = _row_h(app.fonts.ui_body)
    top = sort_y + TTF.TTF_FontHeight(app.fonts.ui_small) + _sy(10)
    visible = (SH - top - _sy(hint_height(app.fonts))) // row_h
    row_max_w = SW - _sx(44)

    start = max(0, app.lib_index - visible // 2)
    for i in range(visible):
        bi = start + i
        if bi >= len(app.books):
            break
        book = app.books[bi]
        y = top + i * row_h
        armed = (bi == app._lib_delete_confirm_idx)
        if armed:
            fill_rect(renderer, _sx(10), y, SW - _sx(20), row_h - _sy(4), COL_WARNING)
        elif bi == app.lib_index:
            fill_rect_rounded(renderer, _sx(10), y, SW - _sx(20), row_h - _sy(4), COL_MENU_SEL_BG)
        color = COL_BG if armed else (COL_ACCENT if bi == app.lib_index else COL_TEXT)
        pin_prefix = "\u2665 " if book["filename"] in app.pinned else ""
        title_line = pin_prefix + book["title"]
        if app.lib_sort_mode == "author" and book.get("author"):
            title_line += f"  \u2014 {book['author']}"
        if armed:
            title_line = "Press SELECT again to DELETE, or move to cancel"
        render_text(renderer, app.fonts.ui_body, _fit_text(app.fonts.ui_body, title_line, row_max_w),
                    color, _sx(24), y + _sy(8))

    if not app.books:
        # v0.1.73: this used to be a single un-wrapped render_text() call
        # at a fixed _sy(100) -- fine at the old fixed UI font, but at
        # larger Font Size steps the full LIBRARY_DIR path ran off the
        # right edge of the screen (Kaleb's report), and the fixed y
        # position could also collide with the heading/sort line above
        # it once those grew taller with Font Size. Reuses the same
        # greedy word-wrap as the hint bar (_wrap_hint_text_unbounded)
        # and anchors to the already-dynamic `top` instead of a fixed
        # pixel offset.
        msg = f"No .epub files found in {LIBRARY_DIR}"
        empty_max_w = SW - _sx(48)
        empty_lines = (_wrap_path_message(app.fonts.ui_body, msg, empty_max_w)
                       if app.fonts.ui_body else [msg])
        empty_line_h = TTF.TTF_FontHeight(app.fonts.ui_body) + _sy(6)
        for ei, eline in enumerate(empty_lines):
            render_text(renderer, app.fonts.ui_body, eline, COL_DIM,
                        _sx(24), top + ei * empty_line_h)

    if app.status_msg and time.time() < app.status_until:
        _sb_h = _status_bar_h(app.fonts)
        fill_rect(renderer, 0, SH - _sy(hint_height(app.fonts)) - _sy(_sb_h), SW, _sy(_sb_h), COL_PANEL)
        render_text(renderer, app.fonts.ui_small, app.status_msg, COL_WARNING,
                    _sx(14), SH - _sy(hint_height(app.fonts)) - _sy(_sb_h) + _sy(6))

    lib_hint = "A Open  Y Sort  X Pin  SELECT Delete  L/R Font Size  START Menu  B Quit"
    if DOWNLOAD_PLUGINS:
        lib_hint = "A Open  Y Sort  X Pin  SELECT Delete  L/R Font Size  L2 Download  START Menu  B Quit"
    draw_hint(renderer, app.fonts, lib_hint)


def draw_reader(renderer, app):
    fill_rect(renderer, 0, 0, SW, SH, COL_BG)
    app._ensure_page_built()

    body_top = _sy(14)
    # v0.1.59: footer_h reserves dedicated space for the progress-percent
    # indicator BELOW the text area, subtracted from body_h before
    # body_rows is computed. Previously the percentage was positioned at
    # a fixed offset above the hint bar with no relationship to body_rows
    # -- when body_h didn't divide evenly by line_h (leftover remainder
    # smaller than the label's height, which varies with Font Size), the
    # last line of text and the percentage ended up sharing the same
    # vertical space (confirmed via Kaleb's on-device photo: "loyal," and
    # "26%" overlapping). Reserving the footer up front guarantees text
    # never lays out into where the percentage is drawn, regardless of
    # font size or how body_h divides.
    footer_h = TTF.TTF_FontHeight(app.fonts.ui_small) + _sy(14)
    body_h = SH - body_top - _sy(hint_height(app.fonts)) - footer_h
    line_h = _sy(app.fonts.SIZE_STEPS[app.fonts.size_index] + 6)
    body_rows = max(1, body_h // line_h)

    visible_spans = app.visible_span_indices(body_rows)
    if visible_spans and app.selected_span not in visible_spans:
        app.selected_span = visible_spans[0]

    row = 0   # visual screen-rows consumed so far (drives the y pixel offset
              # and the loop's exit condition against body_rows)
    li = app.scroll   # which _lines entry we're about to draw -- advances by
                       # exactly 1 per line regardless of how many visual
                       # rows that line ends up consuming on screen
    while row < body_rows:
        if li >= len(app._lines):
            break
        line = app._lines[li]
        ranges = app._line_span_map[li]
        y = body_top + row * line_h

        # detect an image-only line (the [IMG] placeholder occupies its own line)
        img_span_idx = None
        if ranges and len(ranges) == 1:
            s, e, sidx = ranges[0]
            if sidx != -1 and app._combined_spans[sidx][0] == "image" and (e - s) >= len(line):
                img_span_idx = sidx

        if img_span_idx is not None:
            if not app.images_enabled:
                # Text-only mode: never touch the decoder at all -- just a
                # single compact line, same row cost (1) as ordinary text,
                # matching _rows_for_li()'s text-only accounting so
                # pagination stays consistent with what's drawn here.
                is_selected = (img_span_idx == app.selected_span)
                color = COL_LINK_SEL if is_selected else COL_DIM
                render_text(renderer, app.fonts.ui_small, "[Image hidden -- text-only mode]",
                            color, _sx(20), y)
                row += 1
                li += 1
                continue
            # If this image wouldn't fully fit in what's left of the
            # screen, stop the page HERE instead of drawing it and
            # letting it overflow past the bottom (previously: an image
            # near the bottom of a page rendered cropped -- "half the
            # image" -- because nothing checked whether IMG_BOX_ROWS
            # would fit before drawing). row==0 means it's the very
            # first thing on this page, so draw it regardless (an image
            # taller than the whole body is a degenerate case, but still
            # better shown-clipped than never shown at all).
            if row > 0 and row + IMG_BOX_ROWS > body_rows:
                break
            _, i, _, _ = app._combined_spans[img_span_idx]
            image_span = app._images[i]
            box_h = line_h * IMG_BOX_ROWS
            box_w = SW - _sx(40)
            entry = app.get_image_texture(renderer, image_span)
            is_selected = (img_span_idx == app.selected_span)
            border_color = COL_LINK_SEL if is_selected else COL_DIM
            if entry and entry != "error":
                tex, iw, ih, is_full, _buf = entry
                # scale to fit box; allow upscale for small thumbnails so layout is stable
                scale = min(box_w / iw, box_h / ih) if iw and ih else 1.0
                dw, dh = int(iw * scale), int(ih * scale)
                dx = _sx(20) + (box_w - dw) // 2
                dy = y + (box_h - dh) // 2
                dst = Rect(dx, dy, dw, dh)
                SDL.SDL_RenderCopy(renderer, tex, None, ctypes.byref(dst))
                if not is_full:
                    render_text(renderer, app.fonts.ui_small, "improving...", COL_DIM,
                                dx, dy + dh + _sy(2))
            else:
                fill_rect_rounded(renderer, _sx(20), y + _sy(4), box_w, box_h - _sy(8), COL_PANEL)
                if entry == "error":
                    msg = "Image unavailable (unsupported JPEG features)"
                else:
                    secs = app.image_loader.seconds_loading(app._img_key(image_span.src))
                    msg = f"Loading image... ({int(secs)}s)" if secs is not None \
                        else "Loading image..."
                render_text(renderer, app.fonts.ui_small, msg, COL_DIM,
                            _sx(30), y + box_h // 2 - _sy(8))
            if is_selected:
                SDL.SDL_SetRenderDrawColor(renderer, border_color.r, border_color.g,
                                            border_color.b, 255)
                br = Rect(_sx(18), y + _sy(2), box_w + _sx(4), box_h - _sy(4))
                SDL.SDL_RenderDrawRect(renderer, ctypes.byref(br))
            row += IMG_BOX_ROWS
            li += 1
            continue

        # Determine paragraph-level formatting for this line (v0.1.42).
        # Offsets precomputed in _ensure_page_built (v0.1.46 -- was O(n^2)).
        line_abs_start = app._line_abs_offsets[li] if li < len(app._line_abs_offsets) else 0
        line_abs_end = line_abs_start + len(line)
        para_kind = None
        para_extra = ""
        for ps in app._para_spans:
            if ps.start < line_abs_end and ps.end > line_abs_start:
                para_kind = ps.kind
                para_extra = ps.extra
                break

        # box_rule lines: draw the rule text in COL_DIM, skip normal render.
        if para_kind == "box_rule":
            render_text_cached(app, renderer, app.fonts.small, line, COL_DIM, _sx(20), y)
            row += 1
            li += 1
            continue

        # All para kinds render as plain body text (v0.1.47).
        # JW classes sm/sh/si/sb/sj removed; superscript/caption no
        # longer get small font or grey -- uniform size and colour.
        # box_rule still uses small+dim for the visual divider line.
        indent_x = _sx(20)
        style_runs = app._line_style_runs[li] if li < len(app._line_style_runs) else [(0, len(line), False, False)]
        segments = app._line_segments(line, ranges, style_runs)
        x = indent_x

        for (s, e, sidx, bold, italic) in segments:
            seg = line[s:e]
            if not seg:
                continue
            font = app.fonts.body_styled(bold, italic)
            if sidx == -1:
                color = COL_TEXT
            else:
                kind = app._combined_spans[sidx][0]
                color = COL_LINK_SEL if sidx == app.selected_span else (
                    COL_LINK if kind == "link" else COL_ACCENT)
            x += render_text_cached(app, renderer, font, seg, color, x, y)
        row += 1
        li += 1

    # progress indicator
    if app._lines:
        pct = int(100 * app.scroll / max(1, len(app._lines) - body_rows))
        label = f"{pct}% [FAST]" if app.fast_scroll else f"{pct}%"
        color = COL_ACCENT if app.fast_scroll else COL_DIM
        label_w = text_width(app.fonts.ui_small, label)
        # v0.1.59: draw within the reserved footer_h band (right below the
        # last text row) rather than a fixed offset above the hint bar --
        # see footer_h comment above for why the old fixed offset could
        # collide with the last line of text.
        footer_top = body_top + body_rows * line_h
        render_text(renderer, app.fonts.ui_small, label, color,
                    SW - label_w - _sx(14), footer_top + _sy(6))

    if app.status_msg and time.time() < app.status_until:
        _sb_h = _status_bar_h(app.fonts)
        fill_rect(renderer, 0, SH - _sy(hint_height(app.fonts)) - _sy(_sb_h), SW, _sy(_sb_h), COL_PANEL)
        render_text(renderer, app.fonts.ui_small, app.status_msg, COL_ACCENT,
                    _sx(14), SH - _sy(hint_height(app.fonts)) - _sy(_sb_h) + _sy(6))

    draw_hint(renderer, app.fonts,
              "D-PAD Select/Scroll  A Follow  B Back  L/R Page  L2/R2 Chapter  Y Fast x10  X Menu  START Bookmark")


def draw_menu(renderer, app):
    draw_reader(renderer, app)
    overlay_w = _sx(360)
    fill_rect_rounded(renderer, SW - overlay_w, 0, overlay_w, SH - _sy(hint_height(app.fonts)), COL_PANEL)
    render_text(renderer, app.fonts.ui_heading, "MENU", COL_ACCENT, SW - overlay_w + _sx(20), _sy(20))
    row_h = _row_h(app.fonts.ui_body)
    top = _sy(80)
    item_max_w = overlay_w - _sx(44)
    n_items = len(MENU_ITEMS)
    # v0.1.54: this list used to draw every item unconditionally assuming
    # they'd always fit -- true at the old fixed UI font size, but not
    # once rows grew with Font Size. Windowed like Library/Chapters so it
    # scrolls instead of running off the bottom of the screen (confirmed
    # via Kaleb's on-device screenshots at max Font Size).
    visible = max(1, (SH - top - _sy(hint_height(app.fonts))) // row_h)
    start = max(0, min(app.menu_index - visible // 2, max(0, n_items - visible)))
    for i in range(visible):
        mi = start + i
        if mi >= n_items:
            break
        item = MENU_ITEMS[mi]
        y = top + i * row_h
        if mi == app.menu_index:
            fill_rect_rounded(renderer, SW - overlay_w + _sx(10), y, overlay_w - _sx(20), row_h - _sy(6), COL_MENU_SEL_BG)
        color = COL_ACCENT if mi == app.menu_index else COL_TEXT
        render_text(renderer, app.fonts.ui_body, _fit_text(app.fonts.ui_body, item, item_max_w),
                    color, SW - overlay_w + _sx(24), y + _sy(8))
    draw_hint(renderer, app.fonts, "UP/DOWN Select   A Confirm   B Close")


def draw_toc(renderer, app):
    fill_rect(renderer, 0, 0, SW, SH, COL_BG)
    render_text(renderer, app.fonts.ui_heading, "CHAPTERS", COL_ACCENT, _sx(20), _sy(16))
    row_h = _row_h(app.fonts.ui_body, pad=14)
    top = _sy(70)
    visible = (SH - top - _sy(hint_height(app.fonts))) // row_h
    row_max_w = SW - _sx(44)
    start = max(0, app.toc_index - visible // 2)
    for i in range(visible):
        ti = start + i
        if ti >= len(app.toc_flat):
            break
        entry = app.toc_flat[ti]
        y = top + i * row_h
        if ti == app.toc_index:
            fill_rect_rounded(renderer, _sx(10), y, SW - _sx(20), row_h - _sy(4), COL_MENU_SEL_BG)
        color = COL_ACCENT if ti == app.toc_index else COL_TEXT
        label = ("  " * entry.level) + entry.title
        render_text(renderer, app.fonts.ui_body, _fit_text(app.fonts.ui_body, label, row_max_w),
                    color, _sx(24), y + _sy(6))
    draw_hint(renderer, app.fonts, "UP/DOWN Select   L/R/Y +10   L2/R2 Prev/Next Book   A Go   B Cancel")


def draw_text_entry(renderer, app):
    fill_rect(renderer, 0, 0, SW, SH, COL_BG)
    # v0.1.57: prompt/hint text used to be drawn unwrapped at a fixed size
    # -- fine at the old fixed UI font, but at max Font Size a long prompt
    # (e.g. "Pub code (+ issue YYYYMM if needed)") or hint
    # ("w=Watchtower g=Awake! ...") ran past the right edge instead of
    # wrapping (confirmed via Kaleb's on-device screenshot). Both now wrap
    # up to 2 lines, same helper the hint bar uses.
    max_w = SW - _sx(40)
    prompt_lines = _wrap_hint_text(app.fonts.ui_heading, app.te_prompt, max_w) or [""]
    heading_h = TTF.TTF_FontHeight(app.fonts.ui_heading)
    y = _sy(16)
    for line in prompt_lines:
        render_text(renderer, app.fonts.ui_heading, line, COL_ACCENT, _sx(20), y)
        y += heading_h

    # typed-so-far value, in its own box near the top
    box_y = y + _sy(10)
    body_h = TTF.TTF_FontHeight(app.fonts.ui_body)
    box_h = body_h + _sy(20)
    fill_rect_rounded(renderer, _sx(20), box_y, SW - _sx(40), box_h, COL_PANEL)
    shown = app.te_value if app.te_value else "(type below, OK to confirm)"
    color = COL_TEXT if app.te_value else COL_DIM
    render_text(renderer, app.fonts.ui_body, _fit_text(app.fonts.ui_body, shown, SW - _sx(60)),
                color, _sx(30), box_y + _sy(10))

    status_y = box_y + box_h + _sy(10)
    small_h = TTF.TTF_FontHeight(app.fonts.ui_small)
    status_lines = []
    if app.te_checking:
        spinner = "|/-\\"[int(time.time() * 4) % 4]
        secs = int(time.time() - app.te_checking_start) if app.te_checking_start else 0
        status_lines = [f"Checking {spinner}  ({secs}s)"]
    elif app.te_error:
        status_lines = _wrap_hint_text(app.fonts.ui_small, app.te_error, max_w)
    elif app.te_hint:
        status_lines = _wrap_hint_text(app.fonts.ui_small, app.te_hint, max_w)
    status_color = COL_WARNING if app.te_error else COL_DIM
    for line in status_lines:
        render_text(renderer, app.fonts.ui_small, line, status_color, _sx(24), status_y)
        status_y += small_h

    # letter/digit/action grid -- ragged rows, so cell width is based on
    # the WIDEST row (10, the digit row) so every cell is the same size
    # regardless of which row it's in; narrower rows just don't fill the
    # full row width, which reads fine visually (left-aligned).
    rows = TEXT_ENTRY_GRID
    grid_top = status_y + _sy(10)
    max_cols = max(len(row) for row in rows)
    cell_w = (SW - _sx(40)) // max_cols
    cell_h = max(body_h, small_h) + _sy(24)
    for r, row in enumerate(rows):
        for c, (label, kind) in enumerate(row):
            x = _sx(20) + c * cell_w
            gy = grid_top + r * cell_h
            selected = (r == app.te_row and c == app.te_col)
            bg = COL_MENU_SEL_BG if selected else COL_PANEL
            fill_rect_rounded(renderer, x + _sx(3), gy + _sy(3), cell_w - _sx(6), cell_h - _sy(6), bg,
                               radius=_sx(3))
            fg = COL_ACCENT if selected else (COL_WARNING if kind in ("confirm", "cancel") else COL_TEXT)
            font = app.fonts.ui_small if kind not in ("char", "space") else app.fonts.ui_body
            render_text(renderer, font, _fit_text(font, label, cell_w - _sx(12)), fg, x + _sx(8), gy + _sy(10))

    draw_hint(renderer, app.fonts, "D-PAD Move   A Select   X Backspace   B Cancel")


def draw_download_categories(renderer, app):
    fill_rect(renderer, 0, 0, SW, SH, COL_BG)
    heading_y = _sy(16)
    name = getattr(app.dl_plugin, "PLUGIN_NAME", "Download") if app.dl_plugin else "Download"
    render_text(renderer, app.fonts.ui_heading, f"{name.upper()} -- CATEGORIES", COL_ACCENT,
                _sx(20), heading_y)
    categories = getattr(app.dl_plugin, "CATEGORIES", [])
    row_h = _row_h(app.fonts.ui_body)
    top = heading_y + TTF.TTF_FontHeight(app.fonts.ui_heading) + _sy(14)
    n_items = len(categories)
    visible = max(1, (SH - top - _sy(hint_height(app.fonts))) // row_h)
    start = max(0, min(app.dl_cat_index - visible // 2, max(0, n_items - visible)))
    for i in range(start, min(n_items, start + visible)):
        cat = categories[i]
        y = top + (i - start) * row_h
        if i == app.dl_cat_index:
            fill_rect_rounded(renderer, _sx(10), y, SW - _sx(20), row_h - _sy(4), COL_MENU_SEL_BG)
        color = COL_ACCENT if i == app.dl_cat_index else COL_TEXT
        render_text(renderer, app.fonts.ui_body, cat, color, _sx(24), y + _sy(10))
    draw_hint(renderer, app.fonts, "UP/DOWN Select   A Open   B Back")


def draw_download_sources(renderer, app):
    fill_rect(renderer, 0, 0, SW, SH, COL_BG)
    heading_y = _sy(16)
    render_text(renderer, app.fonts.ui_heading, "DOWNLOAD FROM", COL_ACCENT, _sx(20), heading_y)
    row_h = _row_h(app.fonts.ui_body)
    top = heading_y + TTF.TTF_FontHeight(app.fonts.ui_heading) + _sy(14)
    n_items = len(DOWNLOAD_PLUGINS)
    visible = max(1, (SH - top - _sy(hint_height(app.fonts))) // row_h)
    start = max(0, min(app.dl_source_index - visible // 2, max(0, n_items - visible)))
    for i in range(start, min(n_items, start + visible)):
        plugin = DOWNLOAD_PLUGINS[i]
        y = top + (i - start) * row_h
        if i == app.dl_source_index:
            fill_rect_rounded(renderer, _sx(10), y, SW - _sx(20), row_h - _sy(4), COL_MENU_SEL_BG)
        color = COL_ACCENT if i == app.dl_source_index else COL_TEXT
        name = getattr(plugin, "PLUGIN_NAME", plugin.__name__)
        render_text(renderer, app.fonts.ui_body, name, color, _sx(24), y + _sy(10))
    draw_hint(renderer, app.fonts, "UP/DOWN Select   A Open   B Back")


def draw_download_browse(renderer, app):
    fill_rect(renderer, 0, 0, SW, SH, COL_BG)
    name = getattr(app.dl_plugin, "PLUGIN_NAME", "Download") if app.dl_plugin else "Download"
    title = f"{name.upper()}"
    if app.dl_category:
        title += f" -- {app.dl_category}"
    if app.dl_query:
        title += f'  -- "{app.dl_query}"'
    if app.dl_page > 1:
        title += f"  (page {app.dl_page})"
    render_text(renderer, app.fonts.ui_heading, title, COL_ACCENT, _sx(20), _sy(16))

    title_h = TTF.TTF_FontHeight(app.fonts.ui_body)
    sub_h = TTF.TTF_FontHeight(app.fonts.ui_small)
    row_h = title_h + sub_h + _sy(20)
    top = _sy(16) + TTF.TTF_FontHeight(app.fonts.ui_heading) + _sy(14)

    if app.dl_loading:
        # v0.1.62: was static "Loading..." text -- on a slow/laggy
        # connection that's indistinguishable from the screen being
        # frozen, since nothing on screen changes frame to frame. A
        # spinner glyph plus elapsed seconds gives a visible heartbeat
        # so a genuinely slow network call doesn't look like a hang.
        spinner = "|/-\\"[int(time.time() * 4) % 4]
        secs = int(time.time() - app.dl_loading_start) if app.dl_loading_start else 0
        render_text(renderer, app.fonts.ui_body, f"Loading {spinner}  ({secs}s)", COL_DIM,
                    _sx(24), top)
    elif app.dl_load_error:
        render_text(renderer, app.fonts.ui_body, "Couldn't reach server:", COL_WARNING, _sx(24), top)
        render_text(renderer, app.fonts.ui_small, str(app.dl_load_error)[:70], COL_DIM,
                    _sx(24), top + title_h + _sy(6))
    elif not app.dl_items:
        render_text(renderer, app.fonts.ui_body, "No results.", COL_DIM, _sx(24), top)
    else:
        visible = max(1, (SH - top - _sy(hint_height(app.fonts))) // row_h)
        start = max(0, app.dl_index - visible // 2)
        for i in range(visible):
            di = start + i
            if di >= len(app.dl_items):
                break
            item = app.dl_items[di]
            y = top + i * row_h
            if di == app.dl_index:
                fill_rect_rounded(renderer, _sx(10), y, SW - _sx(20), row_h - _sy(4), COL_MENU_SEL_BG)
            color = COL_ACCENT if di == app.dl_index else COL_TEXT
            title_line = item.get("title", "")[:56]
            if di == app._dl_downloading_idx:
                title_line += "  (downloading...)"
            render_text(renderer, app.fonts.ui_body, title_line, color, _sx(24), y + _sy(6))
            render_text(renderer, app.fonts.ui_small, item.get("subtitle", "")[:70], COL_DIM,
                        _sx(24), y + title_h + _sy(10))

    if app.status_msg and time.time() < app.status_until:
        _sb_h = _status_bar_h(app.fonts)
        fill_rect(renderer, 0, SH - _sy(hint_height(app.fonts)) - _sy(_sb_h), SW, _sy(_sb_h), COL_PANEL)
        render_text(renderer, app.fonts.ui_small, app.status_msg, COL_ACCENT,
                    _sx(14), SH - _sy(hint_height(app.fonts)) - _sy(_sb_h) + _sy(6))

    hint = "UP/DOWN Select   A Download   B Back"
    if app.dl_has_next or app.dl_page > 1:
        hint = "UP/DOWN Select   L/R Page   A Download   B Back"
    if getattr(app.dl_plugin, "SUPPORTS_SEARCH", False):
        hint = hint.replace("B Back", "Y Search   B Back")
    elif getattr(app.dl_plugin, "SUPPORTS_MANUAL_CODE", False):
        hint = hint.replace("B Back", "Y Enter Code   B Back")
    draw_hint(renderer, app.fonts, hint)


def draw_library_menu(renderer, app):
    draw_library(renderer, app)
    overlay_w = _sx(320)
    fill_rect_rounded(renderer, SW - overlay_w, 0, overlay_w, SH - _sy(hint_height(app.fonts)), COL_PANEL)
    render_text(renderer, app.fonts.ui_heading, "MENU", COL_ACCENT, SW - overlay_w + _sx(20), _sy(20))
    row_h = _row_h(app.fonts.ui_body)
    top = _sy(76)
    item_max_w = overlay_w - _sx(40)
    n_items = len(LIBRARY_MENU_ITEMS)
    visible = max(1, (SH - top - _sy(hint_height(app.fonts))) // row_h)
    start = max(0, min(app.lib_menu_index - visible // 2, max(0, n_items - visible)))
    for i in range(start, min(n_items, start + visible)):
        item = LIBRARY_MENU_ITEMS[i]
        y = top + (i - start) * row_h
        label = item
        if (item, app.lib_sort_mode) in (
            ("Sort: Title A-Z", "title"), ("Sort: Author A-Z", "author"),
            ("Sort: Last Read", "last_read"), ("Sort: Recently Added", "recent")):
            label = item + "  *"  # mark the currently-active sort mode
        if item == "Download Books" and not DOWNLOAD_PLUGINS:
            continue  # hide entirely if no downloader plugin is present
        if i == app.lib_menu_index:
            fill_rect_rounded(renderer, SW - overlay_w + _sx(10), y, overlay_w - _sx(20), row_h - _sy(6), COL_MENU_SEL_BG)
        color = COL_ACCENT if i == app.lib_menu_index else COL_TEXT
        render_text(renderer, app.fonts.ui_body, _fit_text(app.fonts.ui_body, label, item_max_w),
                    color, SW - overlay_w + _sx(20), y + _sy(8))
    draw_hint(renderer, app.fonts, "UP/DOWN Select   A Confirm   B Close")


def draw_bookmarks(renderer, app):
    fill_rect(renderer, 0, 0, SW, SH, COL_BG)
    bms = [b for b in get_bookmarks(app.current_book_path) if b.get("label") != "__lastpos__"]
    render_text(renderer, app.fonts.ui_heading,
                f"BOOKMARKS ({len(bms)}/{MAX_BOOKMARKS_PER_BOOK})", COL_ACCENT, _sx(20), _sy(16))
    row_h = _sy(44)
    top = _sy(70)
    if not bms:
        render_text(renderer, app.fonts.ui_body, "No bookmarks yet. Press START while reading.",
                    COL_DIM, _sx(24), top)
    for i, bm in enumerate(bms):
        y = top + i * row_h
        armed = (i == app._bookmark_delete_confirm_idx)
        if armed:
            fill_rect(renderer, _sx(10), y, SW - _sx(20), row_h - _sy(4), COL_WARNING)
        elif i == app.bookmarks_index:
            fill_rect_rounded(renderer, _sx(10), y, SW - _sx(20), row_h - _sy(4), COL_MENU_SEL_BG)
        color = COL_BG if armed else (COL_ACCENT if i == app.bookmarks_index else COL_TEXT)
        ts = time.strftime("%b %d %H:%M", time.localtime(bm["ts"]))
        label = f"{bm['label'][:45]}  ({ts})"
        if armed:
            label = "Press X again to delete, or B to cancel"
        render_text(renderer, app.fonts.ui_body, label, color, _sx(24), y + _sy(8))
    draw_hint(renderer, app.fonts, "UP/DOWN Select   L/R/Y Jump 10   A Go   X Delete   B Cancel")


def draw_storage(renderer, app):
    fill_rect(renderer, 0, 0, SW, SH, COL_BG)
    render_text(renderer, app.fonts.ui_heading, "STORAGE", COL_ACCENT, _sx(20), _sy(16))

    cache_size = format_bytes(image_cache_size_bytes())
    orphan_count = len(orphaned_bookmark_book_paths())
    cache_state = "ON (cached to disk)" if app.disk_cache_enabled else "OFF (RAM-only)"
    backups = list_bookmark_backups()
    if backups:
        # filenames are bookmarks_backup_YYYYMMDD_HHMMSS.json
        ts_part = backups[0][len("bookmarks_backup_"):-len(".json")]
        try:
            latest_str = time.strftime("%b %d %H:%M",
                                        time.strptime(ts_part, "%Y%m%d_%H%M%S"))
        except ValueError:
            latest_str = "unknown time"
        backup_line = f"Bookmark backups: {len(backups)} (latest: {latest_str})"
    else:
        backup_line = "Bookmark backups: none yet"
    info_lines = [
        f"Image cache on disk: {cache_size} (cap 500 MB)",
        f"Orphaned bookmark sets: {orphan_count} deleted book(s)",
        f"Disk cache: {cache_state}",
        f"Images: {'ON' if app.images_enabled else 'OFF (text-only)'}",
        backup_line,
    ]
    if app.doc is not None and app._book_id:
        info_lines.insert(1, f"This book's cache: {format_bytes(book_cache_size_bytes(app._book_id))}")
    if app._prerender_active or app._prerender_total:
        done, total, scanning = app.prerender_progress()
        if scanning:
            info_lines.append(f"Pre-render: scanning book... ({total} images found so far)")
        elif app._prerender_active:
            info_lines.append(f"Pre-render: {done}/{total} images decoded (running)")
        elif total:
            info_lines.append(f"Pre-render: {done}/{total} images decoded (last run)")
    line_h = _row_h(app.fonts.ui_small, pad=6)
    y = _sy(50)
    for line in info_lines:
        render_text(renderer, app.fonts.ui_small, line, COL_DIM, _sx(20), y)
        y += line_h

    row_h = _row_h(app.fonts.ui_body)
    top = y + _sy(16)
    action_max_w = SW - _sx(40)
    n_items = len(STORAGE_ACTIONS)
    # v0.1.54: windowed like Library/Chapters/Menu -- this list used to
    # draw every action unconditionally, which ran past the bottom of
    # the screen once info_lines + row_h both grew with Font Size
    # (confirmed via Kaleb's on-device screenshot: "Pre-render Book
    # Images" and "Back" were pushed off-screen with no way to reach
    # them).
    visible = max(1, (SH - top - _sy(hint_height(app.fonts))) // row_h)
    start = max(0, min(app.storage_index - visible // 2, max(0, n_items - visible)))
    for idx in range(start, min(n_items, start + visible)):
        action = STORAGE_ACTIONS[idx]
        ry = top + (idx - start) * row_h
        armed = (idx == app._storage_confirm_idx)
        if armed:
            fill_rect(renderer, _sx(10), ry, SW - _sx(20), row_h - _sy(4), COL_WARNING)
        elif idx == app.storage_index:
            fill_rect_rounded(renderer, _sx(10), ry, SW - _sx(20), row_h - _sy(4), COL_MENU_SEL_BG)
        color = COL_BG if armed else (COL_ACCENT if idx == app.storage_index else COL_TEXT)
        label = action
        if action == "Pre-render Book Images" and app._prerender_active:
            done, total, scanning = app.prerender_progress()
            label = f"Cancel Pre-render (scanning... {total} found)" if scanning                 else f"Cancel Pre-render ({done}/{total})"
        if armed:
            label = "Press A again to confirm, or B to cancel"
        render_text(renderer, app.fonts.ui_body, _fit_text(app.fonts.ui_body, label, action_max_w),
                    color, _sx(24), ry + _sy(10))

    if app.status_msg and time.time() < app.status_until:
        msg_y = top + min(visible, n_items) * row_h + _sy(20)
        render_text(renderer, app.fonts.ui_small, app.status_msg, COL_ACCENT, _sx(20), msg_y)

    draw_hint(renderer, app.fonts, "UP/DOWN Select   A Confirm   B Back")


# ============================================================
# Main loop
# ============================================================
def main():
    if SDL.SDL_Init(SDL_INIT_VIDEO | SDL_INIT_JOYSTICK) != 0:
        _boot_log(f"SDL_Init failed: {SDL.SDL_GetError()}\n")
        sys.exit(1)

    win = SDL.SDL_CreateWindow(b"PicoReader", SDL_WINDOWPOS_CENTERED,
                                SDL_WINDOWPOS_CENTERED, SW, SH, 0)
    if not win:
        _boot_log(f"SDL_CreateWindow failed: {SDL.SDL_GetError()}\n")
        sys.exit(1)
    renderer = SDL.SDL_CreateRenderer(win, -1, 2)
    if not renderer:
        renderer = SDL.SDL_CreateRenderer(win, -1, 1)
    if not renderer:
        _boot_log(f"SDL_CreateRenderer failed: {SDL.SDL_GetError()}\n")
        sys.exit(1)

    if SDL.SDL_NumJoysticks() > 0:
        SDL.SDL_JoystickOpen(0)

    try:
        app = App(renderer)
    except Exception:
        import traceback
        _boot_log("\n--- App() init FAILED ---\n")
        _boot_log(traceback.format_exc())
        _boot_log("--- END ---\n")
        sys.exit(1)

    running = True

    class SDL_KeyboardEvent(ctypes.Structure):
        _fields_ = [("type", ctypes.c_uint32), ("timestamp", ctypes.c_uint32),
                    ("windowID", ctypes.c_uint32), ("state", ctypes.c_ubyte),
                    ("repeat", ctypes.c_ubyte), ("padding2", ctypes.c_ubyte),
                    ("padding3", ctypes.c_ubyte),
                    ("keysym_scancode", ctypes.c_int), ("keysym_sym", ctypes.c_int),
                    ("keysym_mod", ctypes.c_uint16), ("keysym_unused", ctypes.c_uint32)]

    class SDL_JoyHatEvent(ctypes.Structure):
        _fields_ = [("type", ctypes.c_uint32), ("timestamp", ctypes.c_uint32),
                    ("which", ctypes.c_int32), ("hat", ctypes.c_ubyte),
                    ("value", ctypes.c_ubyte), ("padding1", ctypes.c_ubyte),
                    ("padding2", ctypes.c_ubyte)]

    class SDL_JoyButtonEvent(ctypes.Structure):
        _fields_ = [("type", ctypes.c_uint32), ("timestamp", ctypes.c_uint32),
                    ("which", ctypes.c_int32), ("button", ctypes.c_ubyte),
                    ("state", ctypes.c_ubyte), ("padding1", ctypes.c_ubyte),
                    ("padding2", ctypes.c_ubyte)]

    ev_buf = (ctypes.c_byte * 56)()

    def poll_event():
        if SDL.SDL_PollEvent(ctypes.byref(ev_buf)) == 0:
            return None
        etype = ctypes.cast(ev_buf, ctypes.POINTER(ctypes.c_uint32))[0]
        return etype, ev_buf

    while running:
        while True:
            res = poll_event()
            if res is None:
                break
            etype, raw = res
            btn = None

            if etype == SDL_QUIT_EV:
                running = False
                break
            elif etype == SDL_KEYDOWN_EV:
                kev = ctypes.cast(raw, ctypes.POINTER(SDL_KeyboardEvent))[0]
                k = kev.keysym_sym
                if k == SDLK_ESCAPE: running = False
                elif k == SDLK_UP: btn = "UP"
                elif k == SDLK_DOWN: btn = "DOWN"
                elif k == SDLK_LEFT: btn = "LEFT"
                elif k == SDLK_RIGHT: btn = "RIGHT"
                elif k == SDLK_RETURN: btn = "A"
                elif k == SDLK_BACKSPACE: btn = "B"
                elif k == SDLK_TAB: btn = "X"
                elif k == SDLK_EQUALS: btn = "R"
                elif k == SDLK_MINUS: btn = "L"
            elif etype == SDL_JOYHATMOTION_EV:
                hev = ctypes.cast(raw, ctypes.POINTER(SDL_JoyHatEvent))[0]
                hv = hev.value
                if hv & SDL_HAT_UP: btn = "UP"
                elif hv & SDL_HAT_DOWN: btn = "DOWN"
                elif hv & SDL_HAT_LEFT: btn = "LEFT"
                elif hv & SDL_HAT_RIGHT: btn = "RIGHT"
            elif etype == SDL_JOYBUTTONDOWN_EV:
                bev = ctypes.cast(raw, ctypes.POINTER(SDL_JoyButtonEvent))[0]
                b = bev.button
                if b == JOY_A: btn = "A"
                elif b == JOY_B: btn = "B"
                elif b == JOY_X: btn = "X"
                elif b == JOY_Y: btn = "Y"
                elif b == JOY_L: btn = "L"
                elif b == JOY_R: btn = "R"
                elif b == JOY_L2: btn = "L2"
                elif b == JOY_R2: btn = "R2"
                elif b == JOY_START: btn = "START"
                elif b == JOY_BACK: btn = "SELECT"

            if btn:
                app.dirty = True
                handle_button(app, btn, SH - hint_height(app.fonts))
                if app.quit_requested:
                    running = False
                    break

        need_redraw = app.dirty
        if not need_redraw and app.screen == SCREEN_READER:
            need_redraw = app.has_pending_image_updates()
        if not need_redraw and app.screen == SCREEN_DOWNLOAD_BROWSE:
            need_redraw = app.dl_loading or app._dl_downloading_idx is not None
        if not need_redraw and app.screen == SCREEN_TEXT_ENTRY:
            need_redraw = app.te_checking
        if not need_redraw and app.screen == SCREEN_STORAGE:
            need_redraw = app._prerender_active
        if not need_redraw and app.status_msg and time.time() < app.status_until:
            need_redraw = True

        if need_redraw:
            if app.screen == SCREEN_LIBRARY:
                draw_library(renderer, app)
            elif app.screen == SCREEN_READER:
                draw_reader(renderer, app)
            elif app.screen == SCREEN_MENU:
                draw_menu(renderer, app)
            elif app.screen == SCREEN_TOC:
                draw_toc(renderer, app)
            elif app.screen == SCREEN_BOOKMARKS:
                draw_bookmarks(renderer, app)
            elif app.screen == SCREEN_STORAGE:
                draw_storage(renderer, app)
            elif app.screen == SCREEN_LIBRARY_MENU:
                draw_library_menu(renderer, app)
            elif app.screen == SCREEN_TEXT_ENTRY:
                draw_text_entry(renderer, app)
            elif app.screen == SCREEN_DOWNLOAD_SOURCES:
                draw_download_sources(renderer, app)
            elif app.screen == SCREEN_DOWNLOAD_CATEGORIES:
                draw_download_categories(renderer, app)
            elif app.screen == SCREEN_DOWNLOAD_BROWSE:
                draw_download_browse(renderer, app)

            SDL.SDL_RenderPresent(renderer)
            app.dirty = False
            time.sleep(0.016)
        else:
            # nothing to draw -- sleep longer to save CPU/battery while idle
            time.sleep(0.05)

    if app.current_book_path:
        app.save_progress()
    SDL.SDL_Quit()


def handle_button(app, btn, body_h_px):
    line_h = _sy(app.fonts.SIZE_STEPS[app.fonts.size_index] + 6)
    body_rows = max(1, body_h_px // line_h)

    if app.screen == SCREEN_LIBRARY:
        n = len(app.books)
        if btn == "UP":
            app.lib_index = (app.lib_index - 1) % n if n else 0
            app._lib_delete_confirm_idx = None
        elif btn == "DOWN":
            app.lib_index = (app.lib_index + 1) % n if n else 0
            app._lib_delete_confirm_idx = None
        elif btn == "Y":
            app.cycle_sort_mode()
            app._lib_delete_confirm_idx = None
        elif btn == "X" and app.books:
            app.toggle_pin(app.books[app.lib_index])
            app._lib_delete_confirm_idx = None
        elif btn == "A" and app.books:
            app._lib_delete_confirm_idx = None
            app.open_book(app.books[app.lib_index])
        elif btn == "SELECT" and app.books:
            if app._lib_delete_confirm_idx == app.lib_index:
                # second SELECT on the same row -- actually delete
                book = app.books[app.lib_index]
                title = book["title"]
                if app.delete_book(book):
                    app.refresh_library()  # also purges this book's image
                                            # cache, anchor cache, and pin
                                            # entry -- see delete_book()
                    app.lib_index = max(0, min(app.lib_index, len(app.books) - 1))
                    app.set_status(f'Deleted "{title}"')
                else:
                    app.set_status(f'Could not delete "{title}"')
                app._lib_delete_confirm_idx = None
            else:
                # first SELECT -- arm this row, require a second press so a
                # stray button press can't silently delete a book. Moved
                # here from B in v0.1.29 -- B sat right next to the D-pad
                # and normally means "go back" everywhere else in the app,
                # so it was too easy to hit by muscle memory and delete a
                # book by accident, even with the two-press confirm.
                app._lib_delete_confirm_idx = app.lib_index
        elif btn == "B":
            app.quit_requested = True
        elif btn == "L2" and DOWNLOAD_PLUGINS:
            app._lib_delete_confirm_idx = None
            if len(DOWNLOAD_PLUGINS) == 1:
                app.open_downloader(DOWNLOAD_PLUGINS[0])
            else:
                app.dl_source_index = 0
                app.screen = SCREEN_DOWNLOAD_SOURCES
        elif btn == "L":
            # v0.1.55: L/R were unmapped on the Library screen -- added as
            # a Font Size -/+ hotkey (Kaleb's request) so the setting is
            # reachable without opening the Library menu. Same logic/
            # status message as the "Font Size -/+" menu items.
            before = app.fonts.size_index
            app.fonts.smaller()
            app._page_cache_key = None
            pt = app.fonts.SIZE_STEPS[app.fonts.size_index]
            if app.fonts.size_index == before:
                app.set_status(f"Font size: {pt}pt (smallest)")
            else:
                app.set_status(f"Font size: {pt}pt")
        elif btn == "R":
            before = app.fonts.size_index
            app.fonts.bigger()
            app._page_cache_key = None
            pt = app.fonts.SIZE_STEPS[app.fonts.size_index]
            if app.fonts.size_index == before:
                app.set_status(f"Font size: {pt}pt (largest)")
            else:
                app.set_status(f"Font size: {pt}pt")
        elif btn == "START":
            app._lib_delete_confirm_idx = None
            app.lib_menu_index = 0
            app.screen = SCREEN_LIBRARY_MENU

    elif app.screen == SCREEN_LIBRARY_MENU:
        n = len(LIBRARY_MENU_ITEMS)
        if btn == "UP": app.lib_menu_index = (app.lib_menu_index - 1) % n
        elif btn == "DOWN": app.lib_menu_index = (app.lib_menu_index + 1) % n
        elif btn == "B": app.screen = SCREEN_LIBRARY
        elif btn == "A":
            choice = LIBRARY_MENU_ITEMS[app.lib_menu_index]
            sort_map = {"Sort: Title A-Z": "title", "Sort: Author A-Z": "author",
                        "Sort: Last Read": "last_read", "Sort: Recently Added": "recent"}
            if choice in sort_map:
                app.lib_sort_mode = sort_map[choice]
                app.books = sort_library(app.books, app.lib_sort_mode, app.pinned)
                app.lib_index = 0
                app.screen = SCREEN_LIBRARY
            elif choice == "Theme +":
                new_index = (THEME_INDEX + 1) % len(THEMES)
                apply_theme(new_index)
                save_settings({"theme_index": new_index})
                app._page_cache_key = None
                app.set_status(f"Theme: {THEMES[new_index]['name']}")
            elif choice == "Theme -":
                new_index = (THEME_INDEX - 1) % len(THEMES)
                apply_theme(new_index)
                save_settings({"theme_index": new_index})
                app._page_cache_key = None
                app.set_status(f"Theme: {THEMES[new_index]['name']}")
            elif choice == "Download Books" and DOWNLOAD_PLUGINS:
                if len(DOWNLOAD_PLUGINS) == 1:
                    app.open_downloader(DOWNLOAD_PLUGINS[0])
                else:
                    app.dl_source_index = 0
                    app.screen = SCREEN_DOWNLOAD_SOURCES
            elif choice == "Storage":
                app.storage_index = 0
                app._storage_confirm_idx = None
                app._storage_return_screen = SCREEN_LIBRARY_MENU
                app.screen = SCREEN_STORAGE
            elif choice == "Back":
                app.screen = SCREEN_LIBRARY

    elif app.screen == SCREEN_DOWNLOAD_SOURCES:
        n = len(DOWNLOAD_PLUGINS)
        if btn == "UP": app.dl_source_index = (app.dl_source_index - 1) % n if n else 0
        elif btn == "DOWN": app.dl_source_index = (app.dl_source_index + 1) % n if n else 0
        elif btn == "B": app.screen = SCREEN_LIBRARY
        elif btn == "A" and DOWNLOAD_PLUGINS:
            app.open_downloader(DOWNLOAD_PLUGINS[app.dl_source_index])

    elif app.screen == SCREEN_DOWNLOAD_CATEGORIES:
        categories = getattr(app.dl_plugin, "CATEGORIES", [])
        n = len(categories)
        if btn == "UP": app.dl_cat_index = (app.dl_cat_index - 1) % n if n else 0
        elif btn == "DOWN": app.dl_cat_index = (app.dl_cat_index + 1) % n if n else 0
        elif btn == "B":
            if len(DOWNLOAD_PLUGINS) > 1:
                app.screen = SCREEN_DOWNLOAD_SOURCES
            else:
                app.screen = SCREEN_LIBRARY
        elif btn == "A" and categories:
            app.open_category(categories[app.dl_cat_index])

    elif app.screen == SCREEN_DOWNLOAD_BROWSE:
        n = len(app.dl_items)
        if btn == "UP": app.dl_index = (app.dl_index - 1) % n if n else 0
        elif btn == "DOWN": app.dl_index = (app.dl_index + 1) % n if n else 0
        elif btn == "R" and app.dl_has_next: app.dl_next_page()
        elif btn == "L" and app.dl_page > 1: app.dl_prev_page()
        elif btn == "Y" and getattr(app.dl_plugin, "SUPPORTS_SEARCH", False):
            def _on_search_confirm(app, value):
                app.screen = SCREEN_DOWNLOAD_BROWSE
                app.start_search(value)
            app.open_text_entry("Search " + getattr(app.dl_plugin, "PLUGIN_NAME", ""),
                                 app.dl_query or "", _on_search_confirm, SCREEN_DOWNLOAD_BROWSE,
                                 hint="Search by title or author  (case-insensitive)")
        elif btn == "Y" and getattr(app.dl_plugin, "SUPPORTS_CATEGORIES", False):
            # Same search entry as SUPPORTS_SEARCH above, but scoped to the
            # currently-open category via start_search() -> _load_dl_page(),
            # which already threads self.dl_category through.
            def _on_cat_search_confirm(app, value):
                app.screen = SCREEN_DOWNLOAD_BROWSE
                app.start_search(value)
            cat_label = app.dl_category or getattr(app.dl_plugin, "PLUGIN_NAME", "")
            app.open_text_entry(f"Search {cat_label}", app.dl_query or "",
                                 _on_cat_search_confirm, SCREEN_DOWNLOAD_BROWSE,
                                 hint="Search by title  (case-insensitive)")
        elif btn == "Y" and getattr(app.dl_plugin, "SUPPORTS_MANUAL_CODE", False):
            def _on_code_validate(app, value):
                parts = value.strip().split()
                code = parts[0] if parts else ""
                issue = parts[1] if len(parts) > 1 else None
                item, err = app.dl_plugin.lookup_pub_code(code, issue)
                if item:
                    app.dl_items = [item]
                    app.dl_query = value
                    app.dl_page = 1
                    app.dl_has_next = False
                    app.dl_load_error = None
                    app.dl_index = 0
                    app.te_checking = False
                    app.screen = SCREEN_DOWNLOAD_BROWSE
                else:
                    app.te_checking = False
                    app.te_error = err or "Not found"
                app.dirty = True
            app.open_text_entry("Pub code (+ issue YYYYMM if needed)", "",
                                 None, SCREEN_DOWNLOAD_BROWSE, on_validate=_on_code_validate,
                                 hint=getattr(app.dl_plugin, "MANUAL_CODE_HINT", ""))
        elif btn == "B":
            if app.dl_category is not None:
                app.screen = SCREEN_DOWNLOAD_CATEGORIES
            elif len(DOWNLOAD_PLUGINS) > 1:
                app.screen = SCREEN_DOWNLOAD_SOURCES
            else:
                app.screen = SCREEN_LIBRARY
        elif btn == "A" and app.dl_items:
            app.start_download(app.dl_index)

    elif app.screen == SCREEN_TEXT_ENTRY:
        rows = TEXT_ENTRY_GRID
        if btn == "UP":
            app.te_row = (app.te_row - 1) % len(rows)
            app.te_col = min(app.te_col, len(rows[app.te_row]) - 1)
        elif btn == "DOWN":
            app.te_row = (app.te_row + 1) % len(rows)
            app.te_col = min(app.te_col, len(rows[app.te_row]) - 1)
        elif btn == "LEFT":
            app.te_col = (app.te_col - 1) % len(rows[app.te_row])
        elif btn == "RIGHT":
            app.te_col = (app.te_col + 1) % len(rows[app.te_row])
        elif btn == "X" and not app.te_checking:
            app.te_value = app.te_value[:-1]  # quick-backspace shortcut
            app.te_error = None
        elif btn == "B" and not app.te_checking:
            app.screen = app.te_return_screen  # cancel -- neither callback is called
        elif btn == "A" and not app.te_checking:
            label, kind = rows[app.te_row][app.te_col]
            if kind == "char":
                app.te_value += label
                app.te_error = None
            elif kind == "space":
                app.te_value += " "
                app.te_error = None
            elif kind == "backspace":
                app.te_value = app.te_value[:-1]
                app.te_error = None
            elif kind == "cancel":
                app.screen = app.te_return_screen
            elif kind == "confirm":
                value = app.te_value
                if app.te_on_validate:
                    app.te_checking = True
                    app.te_checking_start = time.time()
                    app.te_error = None
                    validate_fn = app.te_on_validate
                    threading.Thread(target=lambda: validate_fn(app, value), daemon=True).start()
                else:
                    callback = app.te_on_confirm
                    app.screen = app.te_return_screen
                    if callback:
                        callback(app, value)

    elif app.screen == SCREEN_READER:
        app._ensure_page_built()
        visible_spans = app.visible_span_indices(body_rows)
        step = 10 if app.fast_scroll else 1
        if btn == "UP":
            if app.selected_span > 0 and visible_spans and app.selected_span in visible_spans:
                pos = visible_spans.index(app.selected_span)
                app.selected_span = visible_spans[max(0, pos - step)]
            else:
                app.scroll = max(0, app.scroll - step)
        elif btn == "DOWN":
            if visible_spans and app.selected_span in visible_spans:
                pos = visible_spans.index(app.selected_span)
                if pos + step < len(visible_spans):
                    app.selected_span = visible_spans[pos + step]
                else:
                    app.scroll = min(app.scroll + step, max(0, len(app._lines) - body_rows))
            else:
                app.scroll = min(app.scroll + step, max(0, len(app._lines) - body_rows))
        elif btn == "LEFT":
            if app.selected_span > 0 and visible_spans and app.selected_span in visible_spans:
                pos = visible_spans.index(app.selected_span)
                app.selected_span = visible_spans[max(0, pos - 1)]
            else:
                app.scroll = max(0, app.scroll - 1)
        elif btn == "RIGHT":
            if visible_spans and app.selected_span in visible_spans:
                pos = visible_spans.index(app.selected_span)
                if pos + 1 < len(visible_spans):
                    app.selected_span = visible_spans[pos + 1]
                else:
                    app.scroll = min(app.scroll + 1, max(0, len(app._lines) - body_rows))
            else:
                app.scroll = min(app.scroll + 1, max(0, len(app._lines) - body_rows))
        elif btn == "A":
            app.follow_selected()
        elif btn == "B":
            if not app.go_back():
                app.save_progress()
                app.screen = SCREEN_LIBRARY
        elif btn == "L":
            app.page_up(body_rows)
        elif btn == "R":
            app.page_down(body_rows)
        elif btn == "L2":
            app.prev_chapter()
        elif btn == "R2":
            app.next_chapter()
        elif btn == "X":
            app.menu_index = 0
            app.screen = SCREEN_MENU
        elif btn == "Y":
            app.fast_scroll = not app.fast_scroll
        elif btn == "START":
            app.bookmark_here()

    elif app.screen == SCREEN_MENU:
        if btn == "UP": app.menu_index = (app.menu_index - 1) % len(MENU_ITEMS)
        elif btn == "DOWN": app.menu_index = (app.menu_index + 1) % len(MENU_ITEMS)
        elif btn == "B": app.screen = SCREEN_READER
        elif btn == "A":
            choice = MENU_ITEMS[app.menu_index]
            if choice == "Chapters":
                app.toc_flat = flatten_toc(app.doc.toc)
                app.toc_index = app._toc_index_for_current_position(app.toc_flat)
                app.screen = SCREEN_TOC
            elif choice == "Bookmarks":
                app.bookmarks_index = 0
                app._bookmark_delete_confirm_idx = None
                app.screen = SCREEN_BOOKMARKS
            elif choice == "Add Bookmark":
                app.bookmark_here()
                app.screen = SCREEN_READER
            elif choice == "Font Size +":
                before = app.fonts.size_index
                app.fonts.bigger()
                app._page_cache_key = None
                pt = app.fonts.SIZE_STEPS[app.fonts.size_index]
                if app.fonts.size_index == before:
                    app.set_status(f"Font size: {pt}pt (largest)")
                else:
                    app.set_status(f"Font size: {pt}pt")
            elif choice == "Font Size -":
                before = app.fonts.size_index
                app.fonts.smaller()
                app._page_cache_key = None
                pt = app.fonts.SIZE_STEPS[app.fonts.size_index]
                if app.fonts.size_index == before:
                    app.set_status(f"Font size: {pt}pt (smallest)")
                else:
                    app.set_status(f"Font size: {pt}pt")
            elif choice == "Theme +":
                new_index = (THEME_INDEX + 1) % len(THEMES)
                apply_theme(new_index)
                save_settings({"theme_index": new_index})
                app._page_cache_key = None
                app.set_status(f"Theme: {THEMES[new_index]['name']}")
            elif choice == "Theme -":
                new_index = (THEME_INDEX - 1) % len(THEMES)
                apply_theme(new_index)
                save_settings({"theme_index": new_index})
                app._page_cache_key = None
                app.set_status(f"Theme: {THEMES[new_index]['name']}")
            elif choice == "Library":
                app.save_progress()
                app.refresh_library()
                app.lib_index = 0
                app.screen = SCREEN_LIBRARY
            elif choice == "Storage":
                app.storage_index = 0
                app._storage_confirm_idx = None
                app._storage_return_screen = SCREEN_READER
                app.screen = SCREEN_STORAGE
            elif choice == "Resume":
                app.screen = SCREEN_READER

    elif app.screen == SCREEN_TOC:
        n = len(app.toc_flat)
        if btn == "UP": app.toc_index = (app.toc_index - 1) % n if n else 0
        elif btn == "DOWN": app.toc_index = (app.toc_index + 1) % n if n else 0
        elif btn == "Y": app.toc_index = min(n - 1, app.toc_index + 10)
        elif btn == "L": app.toc_index = max(0, app.toc_index - 10)
        elif btn == "R": app.toc_index = min(n - 1, app.toc_index + 10)
        elif btn == "L2":
            # Jump to the previous "real" section (book/article), skipping
            # over its "<Name> Outline" companion page. This epub's TOC
            # turned out to have NO level nesting at all (every entry is
            # level 0 -- Bible books, magazine articles, everything is
            # flat), so level couldn't be used to detect section
            # boundaries. Instead: each Bible book appears as two
            # consecutive entries, "Genesis Outline" then "Genesis" --
            # skip the Outline summary pages and land only on the real
            # book/article entry, which is what gives an actual
            # "previous/next book" jump instead of just stepping through
            # every Outline+book pair one at a time.
            for i in range(app.toc_index - 1, -1, -1):
                if not app.toc_flat[i].title.endswith(" Outline"):
                    app.toc_index = i
                    break
            else:
                app.toc_index = 0
        elif btn == "R2":
            for i in range(app.toc_index + 1, n):
                if not app.toc_flat[i].title.endswith(" Outline"):
                    app.toc_index = i
                    break
            else:
                app.toc_index = n - 1
        elif btn == "B": app.screen = SCREEN_READER
        elif btn == "A" and app.toc_flat:
            entry = app.toc_flat[app.toc_index]
            if "#" in entry.href:
                f, a = entry.href.split("#", 1)
            else:
                f, a = entry.href, None
            app._scroll_stack.append(app.scroll)
            app.state.goto(f, a)
            app.scroll = 0
            app.selected_span = 0
            app._page_cache_key = None
            app.screen = SCREEN_READER

    elif app.screen == SCREEN_BOOKMARKS:
        bms = [b for b in get_bookmarks(app.current_book_path) if b.get("label") != "__lastpos__"]
        n = len(bms)
        if btn == "UP":
            app.bookmarks_index = (app.bookmarks_index - 1) % n if n else 0
            app._bookmark_delete_confirm_idx = None
        elif btn == "DOWN":
            app.bookmarks_index = (app.bookmarks_index + 1) % n if n else 0
            app._bookmark_delete_confirm_idx = None
        elif btn == "Y":
            app.bookmarks_index = min(max(0, n - 1), app.bookmarks_index + 10)
            app._bookmark_delete_confirm_idx = None
        elif btn == "L":
            app.bookmarks_index = max(0, app.bookmarks_index - 10)
            app._bookmark_delete_confirm_idx = None
        elif btn == "R":
            app.bookmarks_index = min(max(0, n - 1), app.bookmarks_index + 10)
            app._bookmark_delete_confirm_idx = None
        elif btn == "B":
            if app._bookmark_delete_confirm_idx is not None:
                app._bookmark_delete_confirm_idx = None  # cancel pending delete first
            else:
                app.screen = SCREEN_READER
        elif btn == "X" and bms:
            if app._bookmark_delete_confirm_idx == app.bookmarks_index:
                # second X on the same row -- actually delete
                bm = bms[app.bookmarks_index]
                delete_bookmark(app.current_book_path, bm["file"], bm.get("anchor"), bm.get("ts"))
                app._bookmark_delete_confirm_idx = None
                app.bookmarks_index = max(0, min(app.bookmarks_index, n - 2))
                app.set_status("Bookmark deleted")
            else:
                # first X -- arm this row, require a second press to confirm
                # so a stray button press can't silently delete a bookmark
                app._bookmark_delete_confirm_idx = app.bookmarks_index
        elif btn == "A" and bms:
            bm = bms[app.bookmarks_index]
            app._scroll_stack.append(app.scroll)
            app.state.goto(bm["file"], bm.get("anchor"), char_off=bm.get("char_off"))
            app.scroll = 0
            app.selected_span = 0
            app._page_cache_key = None
            app._bookmark_delete_confirm_idx = None
            app.screen = SCREEN_READER

    elif app.screen == SCREEN_STORAGE:
        n = len(STORAGE_ACTIONS)
        if btn == "UP":
            app.storage_index = (app.storage_index - 1) % n
            app._storage_confirm_idx = None
        elif btn == "DOWN":
            app.storage_index = (app.storage_index + 1) % n
            app._storage_confirm_idx = None
        elif btn == "B":
            if app._storage_confirm_idx is not None:
                app._storage_confirm_idx = None  # cancel pending action first
            else:
                app.screen = app._storage_return_screen
        elif btn == "A":
            action = STORAGE_ACTIONS[app.storage_index]
            if action == "Back":
                app.screen = app._storage_return_screen
            elif action == "Toggle Disk Cache (RAM-only mode)":
                # Non-destructive, instant -- no confirm needed. Updates the
                # LIVE ImageLoader (not just the setting for next launch), so
                # it takes effect immediately without restarting.
                app.disk_cache_enabled = not app.disk_cache_enabled
                app.image_loader.disk_cache_enabled = app.disk_cache_enabled
                save_settings({"disk_cache_enabled": app.disk_cache_enabled})
                state = "ON (cached to disk)" if app.disk_cache_enabled else "OFF (RAM-only)"
                app.set_status(f"Disk cache: {state}")
            elif action == "Toggle Images (text-only mode)":
                # Non-destructive, instant. Turning images back ON doesn't
                # need to do anything extra -- _ensure_page_built() already
                # ran, images list is still intact, draw_reader() just
                # starts calling get_image_texture() again on the next
                # frame (which re-decodes or pulls from disk cache as
                # normal). Cancel any in-flight pre-render when switching
                # to text-only, since decoding images nobody will see
                # defeats the point of the mode.
                app.images_enabled = not app.images_enabled
                if not app.images_enabled and app._prerender_active:
                    app.cancel_prerender()
                save_settings({"images_enabled": app.images_enabled})
                state = "OFF (text-only)" if not app.images_enabled else "ON"
                app.set_status(f"Images: {state}")
            elif action == "Pre-render Book Images":
                # Non-destructive and instantly reversible (just enqueues
                # background decode work), so no confirm needed -- but
                # toggles: a second press while active cancels instead of
                # restarting.
                if app._prerender_active:
                    app.cancel_prerender()
                    app.set_status("Pre-render cancelled")
                elif app.doc is None:
                    app.set_status("Open a book first")
                else:
                    app.start_prerender()
                    app.set_status("Pre-rendering book images in the background...")
            elif action == "Backup Bookmarks Now":
                # Non-destructive, instant -- only ever ADDS a new backup
                # file, never touches live data, so no confirm needed.
                fname = backup_bookmarks()
                if fname:
                    app.set_status(f"Backed up to backups/{fname}")
                else:
                    app.set_status("Nothing to back up -- no bookmarks yet")
            elif app._storage_confirm_idx == app.storage_index:
                # second A on the same destructive/data-changing action --
                # actually do it
                app._storage_confirm_idx = None
                if action == "Clear Image Cache":
                    freed = clear_image_cache()
                    app.image_loader._results.clear()
                    app._image_textures.clear()
                    app.set_status(f"Image cache cleared -- {format_bytes(freed)} freed")
                elif action == "Clean Up Orphaned Bookmarks":
                    removed = clean_orphaned_bookmarks()
                    if removed:
                        app.set_status(f"Removed bookmarks for {removed} deleted book(s)")
                    else:
                        app.set_status("No orphaned bookmarks found")
                elif action == "Restore Latest Backup":
                    fname, books, added = restore_latest_backup()
                    if fname:
                        app.set_status(f"Restored {fname}: {added} bookmark(s) "
                                        f"across {books} book(s) merged in")
                    else:
                        app.set_status("No backup found to restore")
            elif action in ("Clear Image Cache", "Clean Up Orphaned Bookmarks",
                             "Restore Latest Backup"):
                # first A on a destructive/data-changing action -- arm it,
                # require a second press to confirm
                app._storage_confirm_idx = app.storage_index


if __name__ == "__main__":
    main()
