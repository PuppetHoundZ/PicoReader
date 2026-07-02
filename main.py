#!/usr/bin/env python3
"""
PicoReader for muOS (Anbernic RG CubeXX-H, 720x720)
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

Bold/italic (v0.1.35): get_page() returns FIVE values now (text, links,
images, anchor_offsets, styles) -- every call site must unpack all 5, or
it throws immediately on every page load (this exact regression shipped
mid-session once already; check any NEW get_page() call site the same
way). Pipeline: epub_engine's walk() emits StyleSpan (absolute text
offsets) for <strong>/<b>/<em>/<i> -> App._wrap() converts those into
per-line runs via _compute_line_style_runs() (NOT named
_line_style_runs -- that name collides with the instance attribute
storing its output and silently breaks) -> draw_reader() merges style
runs with link/image ranges via _line_segments() into fine-grained
(start, end, sidx, bold, italic) segments, one render_text_cached() call
per segment with app.fonts.body_styled(bold, italic) choosing the font.
Font files: assets/font-bold.ttf, font-italic.ttf, font-bolditalic.ttf,
same Liberation Sans 2.1.5 family as the bundled Regular (byte-verified
via checksum against the system fonts-liberation package). This
sandbox's dummy SDL video driver can't actually create textures
(SDL_CreateTextureFromSurface returns NULL, a known pre-existing
limitation, not a bug) -- so pixel-level rendering can't be visually
verified here; verify logic-level (font handle identity differs per
style, FreeType surface WIDTH differs between regular/bold for identical
text) plus zero-exception real-SDL walks instead, as this fix did.

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

v0.1.36 -- Fixed bold/italic word-wrap measurement mismatch: _wrap() was
    measuring every word's width with the plain regular font
    (self.fonts.body) even when that word would later render bold/italic
    via draw_reader()'s per-segment app.fonts.body_styled(bold, italic).
    Since the bold font renders ~11% wider glyphs for identical text
    (confirmed in v0.1.35: 108px vs 97px), a line judged to "fit"
    avail_w_px using the narrower regular-font measurement could render
    wider than the screen once its bold/italic runs were actually drawn --
    pushing text past the right edge instead of wrapping it to the next
    line. New _word_width() measures each word using the SAME font it
    will be drawn with (splitting into same-style sub-runs when a word
    straddles a style boundary, via body_styled() -- same logic pattern
    as the existing _compute_line_style_runs()), matching draw_reader()'s
    real rendering exactly. Unstyled pages (the common case, self._styles
    empty) take an unchanged fast path with zero added cost. Verified via
    a standalone simulation reproducing the exact 108px/97px ratio from
    the v0.1.35 changelog on a bolded word ("Genesis" in a citation-like
    sentence): old path measured it as narrower than its real bold render
    width; new path's measurement matches the true render width exactly.
    AST-parsed clean; confirmed no other call site referenced the removed
    local `font` variable inside _wrap().

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

Version: 0.1.36

Changelog:
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
# Colors -- minimalist, matches sorter's dark background style
# ============================================================
COL_BG = Color(18, 18, 22, 255)
COL_PANEL = Color(28, 28, 34, 255)
COL_TEXT = Color(225, 225, 230, 255)
COL_DIM = Color(140, 140, 150, 255)
COL_LINK = Color(120, 170, 255, 255)
COL_LINK_SEL = Color(255, 210, 90, 255)
COL_HINT_BG = Color(10, 10, 13, 255)
COL_HINT_TEXT = Color(180, 180, 190, 255)
COL_ACCENT = Color(90, 200, 140, 255)
COL_MENU_SEL_BG = Color(45, 45, 55, 255)
COL_WARNING = Color(230, 90, 90, 255)
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
    # Fixed reference size for UI chrome -- menus, hint bar, library/TOC/
    # bookmarks/storage screens, headings. These must NEVER scale with the
    # person's chosen reading-text size: "Font Size +/-" is meant to
    # control the actual book text only. Previously all UI text shared
    # the same size-index-driven properties as reader body text, so
    # increasing reading size also blew up the hint bar and menu popup
    # until they overflowed off the right edge of the screen. UI_STEP is
    # deliberately just the SIZE_STEPS default (18pt) -- same visual
    # size as before at the default reading size, so nothing looks
    # different unless the person has actually changed Font Size.
    UI_STEP = 18

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

    # -------- fixed-size UI chrome fonts (do not scale with reading size) --------
    @property
    def ui_body(self):
        return self._get(self.UI_STEP)

    @property
    def ui_small(self):
        return self._get(max(11, self.UI_STEP - 4))

    @property
    def ui_heading(self):
        return self._get(self.UI_STEP + 6)

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


def add_bookmark(book_path, file_path, anchor, label):
    """Returns 'added', 'updated' (an existing bookmark at the same
    file+anchor was refreshed instead of creating a duplicate), or
    'limit' (already at MAX_BOOKMARKS_PER_BOOK real bookmarks and this
    would have been a new one, not a duplicate update)."""
    data = load_bookmarks()
    entries = data.setdefault(book_path, [])

    # Duplicate check -- same file+anchor as an existing real bookmark
    # (excluding the internal __lastpos__ marker) just refreshes that
    # entry's label/timestamp rather than cluttering the list with a copy.
    for e in entries:
        if e.get("label") == "__lastpos__":
            continue
        if e.get("file") == file_path and e.get("anchor") == anchor:
            e["label"] = label
            e["ts"] = time.time()
            save_bookmarks(data)
            return "updated"

    real_count = sum(1 for e in entries if e.get("label") != "__lastpos__")
    if real_count >= MAX_BOOKMARKS_PER_BOOK:
        return "limit"

    entries.append({
        "file": file_path, "anchor": anchor, "label": label,
        "ts": time.time(),
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


def save_last_position(book_path, file_path, anchor):
    data = load_bookmarks()
    entries = data.setdefault(book_path, [])
    entries[:] = [e for e in entries if e.get("label") != "__lastpos__"]
    entries.append({"file": file_path, "anchor": anchor,
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
    MAX_CACHE_BYTES = 200 * 1024 * 1024  # 200MB cap on the on-disk image cache
    MAX_INMEMORY_IMAGES = 60  # ~60 decoded images kept in RAM at once (at
                               # typical real sizes from _pick_scale_n, that's
                               # roughly 15-25MB) -- unbounded before this,
                               # _results grew for the entire life of the app
                               # across every image in every book visited.

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
                    self._queue.put((priority, next(self._seq_counter), key, jpeg_bytes))
                return
            self._results[key] = {"thumb": "loading", "full": None, "priority": priority,
                                   "requested_at": time.time()}
        self._queue.put((priority, next(self._seq_counter), key, jpeg_bytes))

    def _worker_loop(self):
        while True:
            priority, _seq, key, jpeg_bytes = self._queue.get()
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
            with open(meta_file) as f:
                w, h = map(int, f.read().split(","))
            with open(cache_file, "rb") as f:
                rgb = f.read()
            try:
                os.utime(cache_file, None)  # touch for LRU recency
            except OSError:
                pass
            return rgb, w, h
        rgb, w, h = decode_jpeg(jpeg_bytes, scale_n=n)
        with open(cache_file, "wb") as f:
            f.write(rgb)
        with open(meta_file, "w") as f:
            f.write(f"{w},{h}")
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
                       "Sort: Recently Added", "Download Books", "Storage", "Back"]

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
              "Library", "Storage", "Resume"]

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
        self.te_error = None

        # Downloader plugin UI state.
        self.dl_source_index = 0     # selection on SCREEN_DOWNLOAD_SOURCES
        self.dl_plugin = None        # the module currently being browsed
        self.dl_items = []
        self.dl_index = 0
        self.dl_page = 1
        self.dl_query = None         # active search text, or None = browse popular
        self.dl_has_next = False
        self.dl_loading = False
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
        self._prerender_cancel = False
        self._prerender_total = 0
        self._prerender_keys = []
        self._prerender_book_id = None
        self._prerender_thread = None

        self._page_cache_key = None
        self._lines = []
        self._line_span_map = []
        self._line_style_runs = []
        self._combined_spans = []
        self._links = []
        self._images = []
        self._anchors = {}
        self._styles = []
        self._chapter_nav_points = []
        self._text_texture_cache = {}
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
    def open_text_entry(self, prompt, initial_value, on_confirm, return_screen, on_validate=None):
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
            calling either one."""
        self.te_value = initial_value or ""
        self.te_row = 0
        self.te_col = 0
        self.te_prompt = prompt
        self.te_on_confirm = on_confirm
        self.te_on_validate = on_validate
        self.te_checking = False
        self.te_error = None
        self.te_return_screen = return_screen
        self.screen = SCREEN_TEXT_ENTRY


    def open_downloader(self, plugin):
        """Switches to the browse screen for one plugin and kicks off its
        (network-bound) list_items() call on a background thread so the
        UI never blocks/freezes while waiting on a slow or absent
        connection -- same reasoning as every other network/decode call
        in this app."""
        self.dl_plugin = plugin
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
        self.dl_loading = True
        self.dl_load_error = None

        def _do_load():
            try:
                items, has_next, err = plugin.list_items(query=query, page=page)
            except Exception as e:
                items, has_next, err = [], False, str(e)
            # Guard against a stale response landing after the person
            # already backed out, switched plugins/pages, or started a
            # different search while this one was still in flight.
            if self.dl_plugin is plugin and self.dl_page == page and self.dl_query == query:
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
        else:
            start_file = self.doc.spine[2] if len(self.doc.spine) > 2 else self.doc.spine[0]
            start_anchor = None
        self.state = ReaderState(self.doc, start_file)
        self.state.current_anchor = start_anchor
        self.scroll = 0
        self.selected_span = 0
        self._scroll_stack = []
        self.screen = SCREEN_READER
        self._page_cache_key = None
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
            if matches:
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
            return points

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
                    text, _links, _images, _anchors, _styles = self.doc.get_page(fname)
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
        try:
            text, links, images, anchors, styles = self.doc.get_page(self.state.current_file)
        except (KeyError, ValueError) as e:
            # stale bookmark/link pointing at a file no longer in this epub
            # (e.g. the file on disk was replaced with a different edition)
            _boot_log(f"could not load page {self.state.current_file}: {e}\n")
            fallback = self.doc.spine[0] if self.doc.spine else None
            if fallback and fallback != self.state.current_file:
                self.state.current_file = fallback
                self.state.current_anchor = None
                text, links, images, anchors, styles = self.doc.get_page(fallback)
            else:
                text, links, images, anchors, styles = "(could not load this page)", [], [], {}, []
        self._links = links
        self._images = images
        self._anchors = anchors
        self._styles = styles
        self._visible_image_keys = {self._img_key(im.src) for im in images}

        combined = [("link", i, l.start, l.end) for i, l in enumerate(links)]
        combined += [("image", i, im.start, im.end) for i, im in enumerate(images)]
        self._combined_spans = combined

        avail_w = SW - _sx(40)

        lines, line_span_map, line_style_runs = self._wrap(text, combined, avail_w)
        self._lines = lines
        self._line_span_map = line_span_map
        self._line_style_runs = line_style_runs
        self._page_cache_key = key

        if self.state.current_anchor and self.state.current_anchor in anchors:
            char_off = anchors[self.state.current_anchor]
            running = 0
            target_line = 0
            for li, line in enumerate(lines):
                running += len(line) + 1
                if running >= char_off:
                    target_line = li
                    break
            self.scroll = max(0, target_line - 2)
        self.state.current_anchor = None
        self.selected_span = 0
        self._prefetch_next_images()

    def _clear_text_texture_cache(self, renderer=None):
        for tex, w, h in self._text_texture_cache.values():
            SDL.SDL_DestroyTexture(tex)
        self._text_texture_cache.clear()

    def has_pending_image_updates(self):
        """True if any image on the current page is still decoding, so the
        idle render loop knows to keep polling instead of going fully quiet."""
        if not self.images_enabled or not self._images:
            return False
        for im in self._images:
            result = self.image_loader.get(self._img_key(im.src))
            if result is None or result == "loading":
                return True
            if self.image_loader.is_upgrading(self._img_key(im.src)):
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
                _text, _links, images, _anchors, _styles = self.doc.get_page(nxt)
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
        self._prerender_cancel = False
        self._prerender_total = 0
        self._prerender_done = 0
        self._prerender_book_id = book_id_value
        self._prerender_keys = []

        def _walk_and_enqueue():
            try:
                seen_srcs = set()
                pending_srcs = []
                for fname in self.doc.spine:
                    if self._prerender_cancel or self._prerender_book_id != book_id_value:
                        return
                    try:
                        _text, _links, images, _anchors, _styles = self.doc.get_page(fname)
                    except Exception:
                        continue
                    for im in images:
                        if im.src in seen_srcs:
                            continue
                        seen_srcs.add(im.src)
                        pending_srcs.append(im.src)
                self._prerender_keys = [self._img_key(s) for s in pending_srcs]
                self._prerender_total = len(pending_srcs)
                for src in pending_srcs:
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
                    self._prerender_active = False
                    self.dirty = True

        self._prerender_thread = threading.Thread(target=_walk_and_enqueue, daemon=True)
        self._prerender_thread.start()

    def cancel_prerender(self):
        self._prerender_cancel = True
        self._prerender_active = False

    def prerender_progress(self):
        """(done, total) actually-decoded count for the active/last
        pre-render pass, checked against the real decode results rather
        than just how many were enqueued -- enqueueing is near-instant,
        decoding is the slow part, so this is what a progress bar should
        reflect."""
        total = self._prerender_total
        if not total or not self._prerender_keys:
            return 0, total
        done = sum(1 for k in self._prerender_keys if self.image_loader.is_full_res(k))
        return done, total

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
        result = self.image_loader.get(key)

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

        rgb, w, h = result
        is_full = self.image_loader.is_full_res(key)

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

    def bookmark_here(self):
        if not self.current_book_path or not self.state:
            return
        label = self._current_location_label()
        result = add_bookmark(self.current_book_path, self.state.current_file,
                               self.state.current_anchor, label)
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
            save_last_position(self.current_book_path, self.state.current_file,
                                self.state.current_anchor)


# ============================================================
# Rendering
# ============================================================
HINT_H = 40
IMG_BOX_ROWS = 14  # sized to actually use the FULL_N=4 decoded resolution
                    # (was 6 -- that shrank a typical 1200x600 photo to ~48%
                    # of its decoded size, wasting more than half the decode
                    # work). Shared at module level so visible_span_indices()
                    # (link-selection scope) and draw_reader() (actual pixels)
                    # never disagree about how much visual space an image
                    # takes -- they used to compute this independently and
                    # drift apart.


def draw_hint(renderer, fonts, text):
    fill_rect(renderer, 0, SH - _sy(HINT_H), SW, _sy(HINT_H), COL_HINT_BG)
    render_text(renderer, fonts.ui_small, text, COL_HINT_TEXT, _sx(14), SH - _sy(HINT_H) + _sy(9))


def draw_library(renderer, app):
    fill_rect(renderer, 0, 0, SW, SH, COL_BG)
    render_text(renderer, app.fonts.ui_heading, "LIBRARY", COL_ACCENT, _sx(20), _sy(16))
    render_text(renderer, app.fonts.ui_small, f"Sort: {LIBRARY_SORT_LABELS[app.lib_sort_mode]}",
                COL_DIM, _sx(20), _sy(48))

    row_h = _sy(46)
    top = _sy(70)
    visible = (SH - top - _sy(HINT_H)) // row_h

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
            fill_rect(renderer, _sx(10), y, SW - _sx(20), row_h - _sy(4), COL_MENU_SEL_BG)
        color = COL_BG if armed else (COL_ACCENT if bi == app.lib_index else COL_TEXT)
        pin_prefix = "\u2665 " if book["filename"] in app.pinned else ""
        title_line = pin_prefix + book["title"]
        if app.lib_sort_mode == "author" and book.get("author"):
            title_line += f"  \u2014 {book['author']}"
        if armed:
            title_line = "Press SELECT again to DELETE, or move to cancel"
        render_text(renderer, app.fonts.ui_body, title_line[:60], color, _sx(24), y + _sy(8))

    if not app.books:
        render_text(renderer, app.fonts.ui_body,
                    f"No .epub files found in {LIBRARY_DIR}", COL_DIM, _sx(24), _sy(100))

    if app.status_msg and time.time() < app.status_until:
        fill_rect(renderer, 0, SH - _sy(HINT_H) - _sy(30), SW, _sy(30), COL_PANEL)
        render_text(renderer, app.fonts.ui_small, app.status_msg, COL_WARNING,
                    _sx(14), SH - _sy(HINT_H) - _sy(22))

    lib_hint = "A Open  Y Sort  X Pin  SELECT Delete  START Menu  B Quit"
    if DOWNLOAD_PLUGINS:
        lib_hint = "A Open  Y Sort  X Pin  SELECT Delete  L2 Download  START Menu  B Quit"
    draw_hint(renderer, app.fonts, lib_hint)


def draw_reader(renderer, app):
    fill_rect(renderer, 0, 0, SW, SH, COL_BG)
    app._ensure_page_built()

    body_top = _sy(14)
    body_h = SH - body_top - _sy(HINT_H)
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
                scale = min(box_w / iw, box_h / ih, 1.0) if iw and ih else 1.0
                # allow modest upscale of small thumbnails so layout doesn't jump around
                scale = min(box_w / iw, box_h / ih)
                dw, dh = int(iw * scale), int(ih * scale)
                dx = _sx(20) + (box_w - dw) // 2
                dy = y + (box_h - dh) // 2
                dst = Rect(dx, dy, dw, dh)
                SDL.SDL_RenderCopy(renderer, tex, None, ctypes.byref(dst))
                if not is_full:
                    render_text(renderer, app.fonts.ui_small, "improving...", COL_DIM,
                                dx, dy + dh + _sy(2))
            else:
                fill_rect(renderer, _sx(20), y + _sy(4), box_w, box_h - _sy(8), COL_PANEL)
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

        style_runs = app._line_style_runs[li] if li < len(app._line_style_runs) else [(0, len(line), False, False)]
        segments = app._line_segments(line, ranges, style_runs)
        x = _sx(20)
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
        render_text(renderer, app.fonts.ui_small, label, color,
                    SW - _sx(90 if app.fast_scroll else 50), SH - _sy(HINT_H) - _sy(24))

    if app.status_msg and time.time() < app.status_until:
        fill_rect(renderer, 0, SH - _sy(HINT_H) - _sy(30), SW, _sy(30), COL_PANEL)
        render_text(renderer, app.fonts.ui_small, app.status_msg, COL_ACCENT,
                    _sx(14), SH - _sy(HINT_H) - _sy(22))

    draw_hint(renderer, app.fonts,
              "D-PAD Select/Scroll  A Follow  B Back  L/R Page  L2/R2 Chapter  Y Fast x10  X Menu  START Bookmark")


def draw_menu(renderer, app):
    draw_reader(renderer, app)
    overlay_w = _sx(360)
    fill_rect(renderer, SW - overlay_w, 0, overlay_w, SH - _sy(HINT_H), COL_PANEL)
    render_text(renderer, app.fonts.ui_heading, "MENU", COL_ACCENT, SW - overlay_w + _sx(20), _sy(20))
    row_h = _sy(50)
    top = _sy(80)
    for i, item in enumerate(MENU_ITEMS):
        y = top + i * row_h
        if i == app.menu_index:
            fill_rect(renderer, SW - overlay_w + _sx(10), y, overlay_w - _sx(20), row_h - _sy(6), COL_MENU_SEL_BG)
        color = COL_ACCENT if i == app.menu_index else COL_TEXT
        render_text(renderer, app.fonts.ui_body, item, color, SW - overlay_w + _sx(24), y + _sy(8))
    draw_hint(renderer, app.fonts, "UP/DOWN Select   A Confirm   B Close")


def draw_toc(renderer, app):
    fill_rect(renderer, 0, 0, SW, SH, COL_BG)
    render_text(renderer, app.fonts.ui_heading, "CHAPTERS", COL_ACCENT, _sx(20), _sy(16))
    row_h = _sy(40)
    top = _sy(70)
    visible = (SH - top - _sy(HINT_H)) // row_h
    start = max(0, app.toc_index - visible // 2)
    for i in range(visible):
        ti = start + i
        if ti >= len(app.toc_flat):
            break
        entry = app.toc_flat[ti]
        y = top + i * row_h
        if ti == app.toc_index:
            fill_rect(renderer, _sx(10), y, SW - _sx(20), row_h - _sy(4), COL_MENU_SEL_BG)
        color = COL_ACCENT if ti == app.toc_index else COL_TEXT
        label = ("  " * entry.level) + entry.title
        render_text(renderer, app.fonts.ui_body, label[:60], color, _sx(24), y + _sy(6))
    draw_hint(renderer, app.fonts, "UP/DOWN Select   L/R/Y +10   L2/R2 Prev/Next Book   A Go   B Cancel")


def draw_text_entry(renderer, app):
    fill_rect(renderer, 0, 0, SW, SH, COL_BG)
    render_text(renderer, app.fonts.ui_heading, app.te_prompt, COL_ACCENT, _sx(20), _sy(16))

    # typed-so-far value, in its own box near the top
    box_y = _sy(60)
    fill_rect(renderer, _sx(20), box_y, SW - _sx(40), _sy(44), COL_PANEL)
    shown = app.te_value if app.te_value else "(type below, OK to confirm)"
    color = COL_TEXT if app.te_value else COL_DIM
    render_text(renderer, app.fonts.ui_body, shown[:50], color, _sx(30), box_y + _sy(10))

    status_y = box_y + _sy(50)
    if app.te_checking:
        render_text(renderer, app.fonts.ui_small, "Checking...", COL_DIM, _sx(24), status_y)
    elif app.te_error:
        render_text(renderer, app.fonts.ui_small, app.te_error[:70], COL_WARNING, _sx(24), status_y)

    # letter/digit/action grid -- ragged rows, so cell width is based on
    # the WIDEST row (10, the digit row) so every cell is the same size
    # regardless of which row it's in; narrower rows just don't fill the
    # full row width, which reads fine visually (left-aligned).
    rows = TEXT_ENTRY_GRID
    grid_top = box_y + _sy(80)
    max_cols = max(len(row) for row in rows)
    cell_w = (SW - _sx(40)) // max_cols
    cell_h = _sy(58)
    for r, row in enumerate(rows):
        for c, (label, kind) in enumerate(row):
            x = _sx(20) + c * cell_w
            y = grid_top + r * cell_h
            selected = (r == app.te_row and c == app.te_col)
            bg = COL_MENU_SEL_BG if selected else COL_PANEL
            fill_rect(renderer, x + _sx(3), y + _sy(3), cell_w - _sx(6), cell_h - _sy(6), bg)
            fg = COL_ACCENT if selected else (COL_WARNING if kind in ("confirm", "cancel") else COL_TEXT)
            font = app.fonts.ui_small if kind not in ("char", "space") else app.fonts.ui_body
            render_text(renderer, font, label, fg, x + _sx(8), y + _sy(14))

    draw_hint(renderer, app.fonts, "D-PAD Move   A Select   X Backspace   B Cancel")


def draw_download_sources(renderer, app):
    fill_rect(renderer, 0, 0, SW, SH, COL_BG)
    render_text(renderer, app.fonts.ui_heading, "DOWNLOAD FROM", COL_ACCENT, _sx(20), _sy(16))
    row_h = _sy(46)
    top = _sy(70)
    for i, plugin in enumerate(DOWNLOAD_PLUGINS):
        y = top + i * row_h
        if i == app.dl_source_index:
            fill_rect(renderer, _sx(10), y, SW - _sx(20), row_h - _sy(4), COL_MENU_SEL_BG)
        color = COL_ACCENT if i == app.dl_source_index else COL_TEXT
        name = getattr(plugin, "PLUGIN_NAME", plugin.__name__)
        render_text(renderer, app.fonts.ui_body, name, color, _sx(24), y + _sy(10))
    draw_hint(renderer, app.fonts, "UP/DOWN Select   A Open   B Back")


def draw_download_browse(renderer, app):
    fill_rect(renderer, 0, 0, SW, SH, COL_BG)
    name = getattr(app.dl_plugin, "PLUGIN_NAME", "Download") if app.dl_plugin else "Download"
    title = f"{name.upper()}"
    if app.dl_query:
        title += f'  -- "{app.dl_query}"'
    if app.dl_page > 1:
        title += f"  (page {app.dl_page})"
    render_text(renderer, app.fonts.ui_heading, title, COL_ACCENT, _sx(20), _sy(16))

    row_h = _sy(52)
    top = _sy(70)

    if app.dl_loading:
        render_text(renderer, app.fonts.ui_body, "Loading...", COL_DIM, _sx(24), top)
    elif app.dl_load_error:
        render_text(renderer, app.fonts.ui_body, "Couldn't reach server:", COL_WARNING, _sx(24), top)
        render_text(renderer, app.fonts.ui_small, str(app.dl_load_error)[:70], COL_DIM,
                    _sx(24), top + _sy(26))
    elif not app.dl_items:
        render_text(renderer, app.fonts.ui_body, "No results.", COL_DIM, _sx(24), top)
    else:
        visible = max(1, (SH - top - _sy(HINT_H)) // row_h)
        start = max(0, app.dl_index - visible // 2)
        for i in range(visible):
            di = start + i
            if di >= len(app.dl_items):
                break
            item = app.dl_items[di]
            y = top + i * row_h
            if di == app.dl_index:
                fill_rect(renderer, _sx(10), y, SW - _sx(20), row_h - _sy(4), COL_MENU_SEL_BG)
            color = COL_ACCENT if di == app.dl_index else COL_TEXT
            title_line = item.get("title", "")[:56]
            if di == app._dl_downloading_idx:
                title_line += "  (downloading...)"
            render_text(renderer, app.fonts.ui_body, title_line, color, _sx(24), y + _sy(6))
            render_text(renderer, app.fonts.ui_small, item.get("subtitle", "")[:70], COL_DIM,
                        _sx(24), y + _sy(28))

    if app.status_msg and time.time() < app.status_until:
        fill_rect(renderer, 0, SH - _sy(HINT_H) - _sy(30), SW, _sy(30), COL_PANEL)
        render_text(renderer, app.fonts.ui_small, app.status_msg, COL_ACCENT,
                    _sx(14), SH - _sy(HINT_H) - _sy(22))

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
    fill_rect(renderer, SW - overlay_w, 0, overlay_w, SH - _sy(HINT_H), COL_PANEL)
    render_text(renderer, app.fonts.ui_heading, "MENU", COL_ACCENT, SW - overlay_w + _sx(20), _sy(20))
    row_h = _sy(46)
    top = _sy(76)
    for i, item in enumerate(LIBRARY_MENU_ITEMS):
        y = top + i * row_h
        label = item
        if (item, app.lib_sort_mode) in (
            ("Sort: Title A-Z", "title"), ("Sort: Author A-Z", "author"),
            ("Sort: Last Read", "last_read"), ("Sort: Recently Added", "recent")):
            label = item + "  *"  # mark the currently-active sort mode
        if item == "Download Books" and not DOWNLOAD_PLUGINS:
            continue  # hide entirely if no downloader plugin is present
        if i == app.lib_menu_index:
            fill_rect(renderer, SW - overlay_w + _sx(10), y, overlay_w - _sx(20), row_h - _sy(6), COL_MENU_SEL_BG)
        color = COL_ACCENT if i == app.lib_menu_index else COL_TEXT
        render_text(renderer, app.fonts.ui_body, label, color, SW - overlay_w + _sx(20), y + _sy(8))
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
            fill_rect(renderer, _sx(10), y, SW - _sx(20), row_h - _sy(4), COL_MENU_SEL_BG)
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
        f"Image cache on disk: {cache_size} (cap 200 MB)",
        f"Orphaned bookmark sets: {orphan_count} deleted book(s)",
        f"Disk cache: {cache_state}",
        f"Images: {'ON' if app.images_enabled else 'OFF (text-only)'}",
        backup_line,
    ]
    if app.doc is not None and app._book_id:
        info_lines.insert(1, f"This book's cache: {format_bytes(book_cache_size_bytes(app._book_id))}")
    if app._prerender_active or app._prerender_total:
        done, total = app.prerender_progress()
        if app._prerender_active:
            info_lines.append(f"Pre-render: {done}/{total} images decoded (running in background)")
        elif total:
            info_lines.append(f"Pre-render: {done}/{total} images decoded (last run)")
    y = _sy(50)
    for line in info_lines:
        render_text(renderer, app.fonts.ui_small, line, COL_DIM, _sx(20), y)
        y += _sy(22)

    row_h = _sy(44)
    top = y + _sy(16)
    for i, action in enumerate(STORAGE_ACTIONS):
        ry = top + i * row_h
        armed = (i == app._storage_confirm_idx)
        if armed:
            fill_rect(renderer, _sx(10), ry, SW - _sx(20), row_h - _sy(4), COL_WARNING)
        elif i == app.storage_index:
            fill_rect(renderer, _sx(10), ry, SW - _sx(20), row_h - _sy(4), COL_MENU_SEL_BG)
        color = COL_BG if armed else (COL_ACCENT if i == app.storage_index else COL_TEXT)
        label = action
        if action == "Pre-render Book Images" and app._prerender_active:
            done, total = app.prerender_progress()
            label = f"Cancel Pre-render ({done}/{total})"
        if armed:
            label = "Press A again to confirm, or B to cancel"
        render_text(renderer, app.fonts.ui_body, label, color, _sx(24), ry + _sy(10))

    if app.status_msg and time.time() < app.status_until:
        msg_y = top + len(STORAGE_ACTIONS) * row_h + _sy(20)
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
                handle_button(app, btn, SH - HINT_H)
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
                                 app.dl_query or "", _on_search_confirm, SCREEN_DOWNLOAD_BROWSE)
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
                                 None, SCREEN_DOWNLOAD_BROWSE, on_validate=_on_code_validate)
        elif btn == "B":
            if len(DOWNLOAD_PLUGINS) > 1:
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
            app.state.goto(bm["file"], bm.get("anchor"))
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
