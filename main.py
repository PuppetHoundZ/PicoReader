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
  D-PAD LEFT/RIGHT  cycle link selection left/right on same line (reader);
                    (Library) quick-scroll, jump 10 rows (v0.1.110)
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
project back up. This describes the CURRENT build only (v26.07.10.10).

v26.07.10.10: reworked the corner-mask contrast fix from v26.07.10.08 --
Kaleb wanted corners "totally black" rather than theme-tinted, so
instead lightened each theme's own COL_BG (see THEMES' individual bg
comments) and reverted _draw_screen_frame()'s corner color back to
pure black (0,0,0) unconditionally. Landed on 1.5:1 contrast against
pure black after live-iterating through several targets in this
session, each rendered as real screenshots before deciding: 3:1 (too
close to the original ask but still visibly grey) -> 2.7:1 -> 2.2:1 ->
1.9:1 -> 1.5:1, Kaleb's explicit final brief being "subtle but just
barely noticeable" -- deliberately BELOW the WCAG 3:1 UI-component
minimum discussed earlier; this was an aesthetic choice, not an
accessibility target. Per-theme new bg values, each theme's own hue
preserved (scaled the theme's existing hint_bg color up, not a flat
neutral grey): Default/Adventure (43,43,50), Dim Warm (52,42,33), Deep
Amber (53,42,30), Red Shift (62,37,37) -- Red Shift specifically
double-checked since Kaleb named it directly ("if they were in red
shift it will render properly"). Also cleaned up a leftover duplicated
paragraph in _draw_screen_frame()'s docstring from the v26.07.10.08
edit (copy-paste artifact, no functional effect, just redundant text).
Verified via real pixel readback across all 5 themes: corner is
exactly (0,0,0) every time, bg is measurably lighter than the corner
every time, never equal. Full regression clean.

v26.07.10.09: splash subtitle face changed again (Kaleb's request) --
requested string used U+2E1C/U+2E1D (decorative low double-quote
brackets) and U+FF61 (halfwidth ideographic dot), all missing from
this font (confirmed via fontTools cmap, same recurring situation as
every other face this project has needed). U+2661 (♡) IS present and
kept as-is. Substituted ˋ/ˊ (modifier letter grave/acute) for the
bracket marks and ˚ for the dot -- same "hands framing a happy face"
shape, all confirmed-present glyphs. Verified this session: fits SW
with margin at every Font Size step (306px at the smallest up to 695px
at the largest, vs. 720px SW -- narrowest margin at the top step, but
still fits), full regression clean.

v26.07.10.08: _draw_screen_frame()'s corner mask (the BMO-style cut on
all 4 corners, every screen) is no longer pure black -- Kaleb reported
not seeing it on the new splash screen, which led to a real measured
finding, not just a splash-specific bug: pure black against every
theme's COL_BG measured ~1.06-1.15:1 WCAG contrast (well under the 3:1
UI-component minimum), so it's been near-invisible on EVERY screen,
every theme, since v0.1.131 -- the splash just made it obvious. Tried
COL_PANEL next (measured equally poor, ~1.03-1.11:1). Tried COL_ACCENT
(real contrast, 2.6-15.3:1, but turns corners into a bold theme-color
cut, abandoning the black-bezel look). Landed on the current theme's
own COL_BG lightened +85 per channel (clamped 255) -- keeps each
theme's hue (Red Shift's frame reads as a lighter red-grey, not flat
neutral grey -- Kaleb's specific ask: "if they were in red shift it
will render properly"), measured 3.1-3.4:1 across all 5 themes,
clearing the WCAG minimum on every one. Multiplicative darkening was
tried and measured FIRST, before landing on lightening -- doesn't
work, there's no headroom below an already near-zero-luminance bg.
Verified this session: real pixel readback (not a screenshot) confirms
the corner is now visibly distinct from bg on all 5 themes, Red Shift
included -- corner sum-of-channels > bg sum-of-channels every time,
never equal.

v26.07.10.07: splash "PICO READER" title is now 50% bigger (Kaleb's
request -- title text only, the face above it and subtitle below it
are unchanged). New Fonts.splash_title property: same pattern as the
existing heading/ui_heading properties (a plain _get() call off
SIZE_STEPS[size_index]), just *1.5, so it still scales with the Font
Size setting instead of being a fixed pixel value. draw_splash()'s
layout math updated to use face_h/title_h separately now that the two
lines are different font sizes (was a single shared `font` var doing
double duty for both). Tested across all 7 Font Size steps this
session: confirmed the actual rendered ratio lands at ~1.5x
ui_heading's height every time (1.46-1.51x, TTF_FontHeight rounding),
and confirmed the full "PICO READER" string still fits SW with margin
at every step, largest included (349px vs. 720px SW at the top step).

v26.07.10.06: extended the boot splash (Kaleb's request). Sequence is
now: title types over SPLASH_TYPE_SECONDS (2.0s, unchanged) -> a new
subtitle (SPLASH_SUBTITLE, "Designed with Love by: Kaleb Fabsik" + a
face) types near the bottom over SPLASH_SUBTITLE_TYPE_SECONDS (2.0s,
starts only once the title finishes) -> everything holds for SPLASH_
HOLD_SECONDS (3.0s) -> hands off to the real destination screen. 2 + 2
+ 3 = SPLASH_TOTAL_SECONDS = 7.0s, matching Kaleb's exact spec (tested
directly this session: SPLASH_TOTAL_SECONDS == 7.0). Subtitle drawn in
app.fonts.ui_body (smaller than the title's ui_heading -- the full
string is much longer and needs to comfortably fit SW), same fixed-x/
full-final-width centering approach the title already used, for the
same anti-jitter reason. Also: splash is now skippable via START/A/B
(handle_button()'s new SCREEN_SPLASH branch, checked first before the
Library branch) -- jumps straight to app._splash_dest_screen, same
target draw_splash() itself would hand off to once its timer runs out.
Confirmed a non-skip button (tested with UP) does NOT dismiss it.
Requested subtitle face used U+3063 (Hiragana small tsu) and U+02F6
(same missing modifier-letter mark flagged in earlier sessions), both
absent from this font (confirmed via fontTools cmap) -- substituted
with a face built from confirmed-present glyphs only, same as every
other face this project uses. Also flagged to Kaleb (not silently
"corrected"): the original subtitle string looked like it had a
mismatched extra closing paren partway through.

v26.07.10.05: two more changes, Kaleb's requests. (1) Boot splash --
new SCREEN_SPLASH, shown before whatever App.__init__ actually resolves
as the real destination (Library, or Reader if Open Last Book on
Launch just found one -- captured into self._splash_dest_screen as the
LAST thing __init__ does, same ordering reasoning as Open Last Book
itself). draw_splash() shows FACE_MENU_LOGO above SPLASH_TITLE
("PICO READER"), same font/color as the Menu overlay's logo
(ui_heading/COL_ACCENT) per Kaleb's explicit request to match --
SPLASH_TITLE spells itself left-to-right over SPLASH_TYPE_SECONDS
(2.0s), holds fully spelled for SPLASH_HOLD_SECONDS (2.0s), then
delegates straight to draw_library()/draw_reader() once
SPLASH_TOTAL_SECONDS elapses (rather than just flipping app.screen and
returning blank, which would paint one empty frame first). The
revealed prefix is drawn at a FIXED x computed once from the FULL
final string's width -- confirmed by testing this needs to NOT
recenter every frame, or the growing text visibly drifts instead of
reading as being typed in place. Needed two other wire-ups: the main
loop's screen-dispatch (checked first, before Library) and its
need_redraw fallback chain (splash always redraws, no button to wait
for -- same shape as the existing SCREEN_READER/pending-image-update
case). Tested via a second real App() instance this session: confirmed
the initial screen really is SPLASH, confirmed the reveal count is
correct at t=0/1.0s/3.0s (still splash, mid-type vs. fully held), and
confirmed it correctly hands off to the real destination screen once
past SPLASH_TOTAL_SECONDS. (2) Exit toast now uses FACE_DONE (the
existing download-completion cheer face) instead of last session's
dedicated FACE_EXIT, which was removed as dead code -- Kaleb's request
to reuse the same "done" face rather than a separate exit-only one.

v26.07.10.04: two more cosmetic additions, Kaleb's requests. (1) Menu
screen logo -- draw_menu()'s plain "MENU" label replaced with
FACE_MENU_LOGO on its own line and "PICO READER" below it, both
centered in the 360px overlay, same ui_heading font size the old label
already used (a literally bigger font risked overflowing this narrow
sidebar at large Font Size settings -- confirmed via this session's
test sweep across every Font Size step: both lines fit with margin to
spare at all 7 sizes, from 65/123px at the smallest up to 124/234px at
the largest, well under the 360px overlay). (2) Exit toast -- pressing
B on the Library screen (the only place App.quit_requested gets set,
confirmed by search) now shows "Exiting Pico Reader" + FACE_EXIT for
EXIT_TOAST_SECONDS (0.9s) before the window actually closes, instead
of vanishing the instant B is pressed: sets the status message, draws
one more Library frame, presents it, SDL_Delay()s, then quits. Both
new faces (FACE_MENU_LOGO, FACE_EXIT) follow the same substitution
approach as v26.07.10.03's faces -- the originally requested glyphs
(U+02F6, U+15DC, halfwidth katakana U+FF89/U+FF9E) are missing from
DejaVu Sans Condensed (confirmed via fontTools cmap), so equivalents
were built from confirmed-present glyphs only (˚ for the sparkle-cheek
mark, ◡ for the compressed mouth, plain "~" for the hand-wave).
Verified this session: draw_menu() and the exit-toast draw_library()
call both render without error at every Font Size, real SDL2/SDL2_ttf.

v26.07.10.03: two features, Kaleb's requests. (1) Mid-wrap abort for the
live large-page loading screen: B/L2/R2 now break out of an in-progress
synchronous wrap instead of only being acted on after it finishes.
Reuses _wrap()'s existing per-paragraph progress_cb checkpoint (already
there for the percentage display) -- App._poll_wrap_abort_button() polls
for a matching JOYBUTTONDOWN at each throttled (~4x/second) tick and
raises App._WrapAbortRequested if found; _ensure_page_built() catches
it, restores a snapshot of self._links/_styles/_styles_starts/
_styles_prefix_max_end/_para_spans/_visible_image_keys/_combined_spans/
_anchors/_images taken before the new page started overwriting them
(self._lines is never touched by an aborted attempt, so this keeps
self._lines and the restored fields a matched pair instead of one
describing the abandoned page and the other the old one -- same save/
restore shape _prerender_one_extreme_page() already used for exactly
this reason around self._styles alone), queues the abandoned page at
the FRONT of the existing _extreme_page_queue (priority over the
proactively-scanned FIFO -- this one was actually asked for), then
performs the requested navigation via the exact same go_back()/
prev_chapter()/next_chapter() methods B/L2/R2 already call normally,
and recurses into _ensure_page_built() once more so draw_reader()
never renders a stale frame that same cycle. _wrap() itself has no
try/except around its progress_cb call and never mutates self during
its loop (confirmed by reading it) -- an abort at any paragraph
boundary can't leave self in a half-set state beyond what's explicitly
snapshotted/restored. "back" specifically: if there's no link-history
to go back to (go_back() returns False), this correctly falls through
to the SAME "exit to Library, keep current_file where it was" behavior
a normal B press has in that situation -- confirmed this is intentional
(resuming later should return to the actual last-read position, not an
abandoned in-progress page), not a bug, while writing this session's
test suite. draw_reader()'s own pre-wrap peek (the "Rendering large
page..." screen shown before _ensure_page_built() even runs) now also
shows queue position ("(queued, N ahead)" / "(queued, next up)") when
the upcoming page is already sitting in _extreme_page_queue, so
returning to a previously-bailed-on page shows real status instead of
a plain unmoving message. Tested this session with real SDL2/SDL2_ttf,
a real App() instance, and NWT's real 108,741-char page (its real max
-- confirmed still under the real 133,000 shipped threshold, so this
has ZERO effect on NWT's actual on-device behavior; the threshold was
only lowered in the test harness, exactly the existing project
precedent for exercising this mechanism without Enjoy Life Forever/
Daily Text on hand): all 3 actions (back/prev_chapter/next_chapter)
aborting at the first available tick, each followed by a full state-
consistency check (page_cache_key/current_file match, styles arrays in
sync, no premature/corrupt disk-cache entry); background-queue drain
via _prerender_one_extreme_page() correctly completes and persists the
abandoned page; revisiting it afterward loads from disk instantly, no
re-wrap. Plus a 20-page regression sample at the REAL threshold: zero
errors. (2) Cosmetic: small kaomoji-style faces on loading/status
screens (Kaleb's request) -- FACE_THINKING_A/_B cycle every
FACE_CYCLE_SECONDS on any in-progress message (Downloading/Rendering/
Pre-rendering/Loading), FACE_DONE appears on any completion/already-
satisfied message (downloaded/already), via one choke point each:
_draw_status_bar() (every toast in the app) and
_draw_large_page_loading_screen(). The ORIGINALLY requested faces used
Kannada/Malayalam script characters DejaVu Sans Condensed doesn't
cover (confirmed via direct fontTools cmap inspection) -- since this
font's glyph-substitution table is empty, those would've rendered as
blank tofu with zero fallback, so equivalent faces were built entirely
from glyphs individually confirmed present (fontTools cmap AND real
TTF_GlyphIsProvided32 AND an actual SDL_RenderReadPixels check that
real ink -- not a blank box -- gets painted).

v26.07.10.02: "Search Audio" -- follow-up to v26.07.10.01's Audio
feature, after Kaleb asked whether the DEFAULT keyword search surfaces
audio results now that a download path for them exists. Confirmed
directly: no -- and this exposed a real, separate gap along the way.
The general keyword search (Y from Categories, jw_fetch.list_items()
with a query) is DELIBERATELY EPUB-only by design (its own comment:
"video-only results aren't shown here") -- that's unrelated to audio
and wasn't touched. But _walk_search_results() (OmniSearch response
parsing, shared by every search_jw() caller) was ALSO silently
dropping real subtype="audio" hits from the raw API response --
confirmed live: filter="audio", q="love" returns 12 real results
(lank format "pub-XXX_N_AUDIO", same shape as video's "pub-XXX_N_VIDEO")
that were simply discarded before this fix, not because the API lacked
them but because the parser only recognized "video"/"publication"
subtypes -- true when that code was written (no audio download path
existed yet), stale now. Fixed at the source: _walk_search_results()
now tags subtype="audio" items with _kind="audio" (+ "duration" as the
subtitle, e.g. "4:16" -- a real field on audio hits, more useful here
than a text snippet). New "Search Audio" entry in AUDIO_SOURCES,
mirroring "Search Videos" exactly: search_jw(filter="audio"), lazy
resolve at download time only (resolve_search_audio_item() ->
resolve_audio_link(), parsing the pub-XXX_N_AUDIO lank via new
_AUDIO_LINK_RE -- mirrors _VIDEO_LINK_RE, confirmed live across several
queries that every real audio lank found follows this simple pub+track
shape, no docid variant seen the way video has one). start_download()'s
audio branch now has the same "already resolved vs. needs
resolving" branch the video branch already had. Full live test:
searched "love" -> 12 real results (some are duplicate titles, e.g.
"154. Unfailing Love" appearing twice -- likely vocal/instrumental
variants, same track-numbering behavior already seen in the Songbook
source) -> downloaded the first result end-to-end through the lazy-
resolve path, confirmed real MP3 landed in find_music_dir()'s path.

v26.07.10.01: MP3 audio downloads (Kaleb's bug-report feature request #9)
-- new "Audio" entry in Download Books > JW (jw_fetch.CATEGORY_AUDIO,
same pseudo-category pattern as CATEGORY_VIDEOS), saving into muOS's
native GMU Music Player content folder. Folder path confirmed against
Kaleb's own device (ROMS/Music, capital M) -- unlike ROMS/movies, muOS
itself has no fixed default naming for music content (muos.dev docs are
explicit that content folder names are fully user-defined), so this is
specifically Kaleb's setup, not a muOS-wide convention like "movies" is.
Three real AUDIO_SOURCES entries, all confirmed live against
GETPUBMEDIALINKS?fileformat=MP3 this session (real files downloaded and
verified, not just listed): "Watchtower Study Audio (This Week)"
(auto-resolves the RSS-confirmed latest issue, same chain
generate_mwb_back_issues() already uses, no picker needed), "Songbook --
Sing Out Joyfully to Jehovah" (pub=sjjm, 326 tracks, already self-
numbered in each title), and "Bible Reading Audio (NWT)" (pub=nwt,
needs a booknum -- the one AUDIO_SOURCES entry marked "books": True,
which opens a new Bible-book sub-picker screen,
SCREEN_DOWNLOAD_AUDIO_BOOKS, driven by jw_fetch.BIBLE_BOOKS' fixed
66-book table, before calling the loader). Architecture mirrors
VIDEO_SOURCES/SCREEN_DOWNLOAD_VIDEO_SOURCES closely: jw_fetch.py owns
find_music_dir()/download_audio()/list_audio_items()/
list_watchtower_study_audio(), main.py's App.dl_is_audio flag threads
through start_download() (audio branch: find_music_dir()+
download_audio(), no refresh_library(), same as the video branch) and
draw_download_browse()'s title/hint (had to explicitly exclude audio
mode from the SUPPORTS_SEARCH/SUPPORTS_MANUAL_CODE hint/button branches,
which otherwise incorrectly fired off JW_PLUGIN's own flags -- those
apply to the EPUB browse path, not audio). B-back navigation is
history-aware: from a direct source (Study Audio, Songbook) B returns
to SCREEN_DOWNLOAD_AUDIO_SOURCES; from the Bible source B returns to
SCREEN_DOWNLOAD_AUDIO_BOOKS instead (App._pending_audio_source tracks
which), so picking a different book doesn't require re-opening Audio
from scratch. Full button-driven end-to-end test this session: Library
Menu -> Download Books -> JW -> Categories -> Audio -> each of the 3
sources -> real download, for all three; confirmed B navigation lands
correctly in both cases; confirmed a real downloaded MP3 (Watchtower
Study audio, 9,762,559 bytes) matches the API's reported filesize
exactly, landed in find_music_dir()'s real path. Daily Text audio
(es26 pub) was checked and does NOT work via this same booknum/issue
shape (404) -- not included in AUDIO_SOURCES, flagged here in case a
future session finds the right param shape for it.

v26.07.09.22: disk-cache-read loading screen (v26.07.09.19) upgraded from
a flat "Loading cached page..." message to a live elapsed-seconds counter
("Loading cached page... Ns") -- the open idea flagged at the end of the
v26.07.09.21 session. Unlike the fresh-wrap path (_wrap()'s progress_cb,
called at natural per-paragraph chunk points), a single pickle.load()
call has no chunk points to hook a percentage into. Solved instead by
moving the actual disk read onto a background thread
(App._load_wrap_from_disk_with_progress()) and polling from the main
thread every ~0.25s to redraw the elapsed count + pump SDL events --
safe to background because pickle.load()/file I/O never touches
SDL_ttf, same reasoning _prerender_extreme_pages_scan() already relies
on for ITS background thread (unlike the wrap itself, which stays
synchronous/main-thread per the existing SDL_ttf-off-main-thread
constraint). Verified with an artificially-slowed disk read (1.2s) in
this session's harness: counter correctly showed 0s -> 1s across the
simulated wait, updating every ~0.25s as designed.

Also this session: independently re-verified the v26.07.09.21 claims
against real EPUBs rather than taking the prior session's numbers on
faith. Two corrections to what was previously reported: (1) the
uploaded lffi_E.epub ("Enjoy Life Forever!--Brochure") is the short
21-file introductory brochure, NOT the source of the previously-cited
4.5M-character "Track Your Bible Reading" page -- its real largest
page is only 61,981 characters. That extreme page must have come from
a different/fuller edition not present in this session's uploads, so
its exact timing numbers are Kaleb's on-device reports, not something
re-confirmed here. (2) NWT's real largest page (108,741 chars, of
3941 spine files) sits under BOTH real thresholds (133K/266K) -- so at
real thresholds this session's two available books produce zero
loading-screen/prerender activity, exactly matching the "NWT: zero
candidates" claim from v26.07.09.21's own regression note. To actually
exercise the loading-screen/disk-cache/prerender MECHANISM (not
available at real thresholds with these two books), thresholds were
temporarily lowered in the test harness only (never in shipped code)
so NWT's real 108,741-char page crossed both tiers. Confirmed: (a)
cold wrap shows the percentage loading screen and persists to disk;
(b) a completely fresh App() instance (simulated restart) loads that
same page from disk in a fraction of the cold-wrap time, with
byte-identical wrapped-line output; (c) the background prerender scan
finds the page, queues it, and drains the queue only on a frame where
the CURRENTLY-viewed page needs no work of its own -- confirmed it
never delays real navigation to a DIFFERENT page. Full spine regression
(3941 NWT + 21 Enjoy Life Forever pages, two passes each) at REAL
thresholds: zero lockups, zero exceptions.

v26.07.09.21: two changes together. (1) CORRECTED
LARGE_PAGE_LOADING_THRESHOLD -- v26.07.09.20's 50K was based on a
mistaken cross-book comparison (Kaleb clarified all his real timing
numbers were the SAME Enjoy Life Forever page throughout, at two font
sizes, not two different books as assumed). Real numbers (85s/78s cold
wrap for that one 4.5M-char page, ~17-19 us/char, confirmed linear via
direct sandbox measurement) -> 133K chars for the loading-screen tier
(~2.5s), 266K for a new pre-render tier. (2) NEW: pages over
PRERENDER_THRESHOLD are now wrapped proactively when a book is opened
(App._prerender_extreme_pages_scan()/_prerender_one_extreme_page()),
not waited for on first navigation -- background-scanned (safe: no
SDL_ttf calls) then processed one at a time on the main thread only
when the currently-viewed page doesn't itself need work that frame.
Verified live: Enjoy Life Forever's background scan found 6 qualifying
pages on open; by the 2nd-3rd draw_reader() call during ordinary
reading (never navigating to the extreme page), its disk cache already
existed. Full regression across NWT's 3941-file spine (worst case,
background scan correctly found zero candidates, matching its real max
page size) plus 3 other books: no lockups, no exceptions.

v26.07.09.20: lowered LARGE_PAGE_LOADING_THRESHOLD from 100K to 50K
characters -- see its own module-level comment for the real reasoning
(Kaleb's on-device cold-wrap time for Daily Text's 461K-char page,
40-50s, scales to ~8-10s for a 90K-char page, which was previously
UNDER the old threshold and got zero warning for a real, felt wait).
Real consequence, confirmed via sampling: this roughly triples scope on
some books -- Enjoy Life Forever goes from 7 to 21 sampled pages over
threshold (~13%), Courage from 4 to 16 (~12%) -- no longer the "~2%
extreme outliers" the original 100K was calibrated for, but a
deliberate tradeoff toward catching real wait time over just rarity.

v26.07.09.19: two follow-ups from Kaleb's on-device test of v26.07.09.18
(real numbers: 40-50s -> 4s). (1) The wrap-computation loading screen
now shows a live percentage, throttled to ~4x/second -- _wrap() takes an
optional progress_cb(fraction) called each paragraph, _ensure_page_
built() wires it up only when a renderer is available and the page is
over threshold. Also pumps SDL_PumpEvents() on each update -- doesn't
make input actionable mid-wrap (still can't be, same SDL_ttf-off-main-
thread constraint, confirmed via real research this session: FreeType's
own docs are explicit that concurrent access needs a separate FT_Library
per thread, not just "unverified" -- a real redesign, not a small
change, so left alone), but keeps the OS from considering the process
fully unresponsive during the wait. (2) The disk-cache-LOAD path (reading
an already-cached extreme page back, ~4s on real hardware per Kaleb's
report) now ALSO shows a loading message ("Loading cached page...",
distinct wording from the fresh-computation one) -- previously this path
showed nothing at all for its own real duration, which is exactly what
prompted this fix ("4 seconds is long enough to be like hmmm I wonder if
it broke").

v26.07.09.18: added a disk cache for extreme pages ONLY (see
WRAP_CACHE_DIR/LARGE_PAGE_LOADING_THRESHOLD -- same 100K-char threshold
as the v26.07.09.17 loading screen, deliberately narrow, NOT a general-
purpose cache -- Kaleb's explicit request). A page over threshold is
wrapped once (still synchronous, still main-thread -- no new SDL_ttf
threading risk) and persisted to disk; every visit after that, even
after closing the book or restarting the app, loads instantly instead
of re-wrapping. Verified live: Enjoy Life Forever's "Track Your Bible
Reading" page (4.5M characters, the largest page found in this
project's testing) -- cold wrap 7.99s -> loaded from disk in a totally
fresh App() instance (simulating an app restart) in 0.91s, with
byte-identical content confirmed line-by-line. Cleaned up automatically
on book deletion via the same {book_id}__ prefix convention/glob
pattern IMG_CACHE_DIR already uses (scan_library()'s stale-entry
cleanup, and delete_book_cache() -- both updated).
expensive to build even after the v26.07.09.15/.16 algorithmic fixes
(some pages are just genuinely huge -- e.g. Enjoy Life Forever's
4.5M-character page still takes several seconds even with zero
remaining O(n x m) blowups, per profiling: it's now proportional to
real word count, not a bug). draw_reader() peeks at the upcoming page's
text length BEFORE calling _ensure_page_built() -- if it exceeds
LARGE_PAGE_LOADING_THRESHOLD (50K chars as of v26.07.09.20 -- see its
own module-level comment for why it moved down from the original 100K:
frequency data alone wasn't calibrated against real device wait time) AND isn't already wrap-cached, shows "Rendering
large page..." and presents that frame BEFORE doing the actual
(still synchronous, still main-thread) wrap. Deliberately NOT
backgrounded -- _wrap() calls into SDL_ttf, and calling SDL_ttf off the
main thread has never been verified safe on this hardware (see
_ensure_page_built()'s v0.1.69 comment), so this only adds visible
feedback around the existing synchronous cost, not a threading change.

v26.07.09.15/.16: fixed THREE instances of the same O(n x m) blowup
pattern in text layout, all found in one sweep after Kaleb asked whether
other books could hit a similar bug to the confirmed Daily Text lockup.
They could, and worse: (1) main.py's style_at() -- linear scan over
every style span per character, 35s alone on a 2697-span page; (2)
main.py's _compute_line_style_runs() -- same shape per LINE instead of
per character, found a page in Enjoy Life Forever with 31,390 style
spans across 4.5M characters that TIMED OUT past 30s before this fix;
(3) epub_engine.py's remap() -- a partial-linear-scan over collapsed-
blank-line ranges, called once per offset being remapped (134,097 times
on that same huge page). All three fixed via bisect + a precomputed
cumulative/prefix array instead of a scan. That worst-case page: was
uncompletable (30s+ timeout) -> 16.2s (fix 1+2) -> 8.8s (fix 3). Full
regression across all 6 available books (Daily Text, Enjoy Life Forever,
Courage, NWT, another Bible translation, a Watchtower issue), 10 R2
presses each with real draws: zero lockups.
There is no separate changelog file or historical version log anymore
-- non-obvious behavior is explained via inline "# vYY.MM.DD.XX" comments
directly above the relevant code as you read through the file, not in
one big block up here. What follows is a snapshot of current
architecture, conventions, and known trouble spots.

VERSIONING SCHEME CHANGE (v26.07.09.01): switched from the old
sequential v0.1.X counter (last value: v0.1.162) to a date-based scheme:
YY.MM.DD.XX, where YY.MM.DD is today's date and XX is a same-day counter
starting at 01 and incrementing per change, resetting to 01 each new
calendar day. No more major/minor/patch semantics -- the date IS the
version. All prior "v0.1.X" references throughout this file are historical
and untouched; only new changes going forward use the new format.

Current screen/feature set: 5 color themes, 7 Font Size steps, JW.org +
Project Gutenberg download plugins, Image Maximize Mode (fullscreen
zoom/pan on a selected image), Library with sort/pin/finished/filter,
bookmarks with history, Chapters (TOC) navigation, per-book Storage/
cache controls, and JW video browsing (all four video categories --
Enjoy Life Forever, JW Broadcasting, Governing Body Updates, The Good
News According to Jesus -- plus a 5th "Search Videos" entry (v26.07.09.08)
for live free-text search against jw.org's own search API, all unified
under one "Videos" entry reached via Download Books > JW). v26.07.09.09:
this whole picker is now driven entirely by jw_fetch.py's own
VIDEO_SOURCES registry (label + loader function name + args per entry)
instead of main.py hardcoding JW titles/pub codes and four near-duplicate
opener methods -- see open_plugin_video_list() and VIDEO_SOURCE_BY_LABEL
for the generic replacement. Falls back to the old hardcoded behavior if
an older jw_fetch.py lacks VIDEO_SOURCES. "Search Videos" only appears if
the loaded jw_fetch.py actually has search_jw() (same hasattr-gating
convention as JW_VIDEO_SUPPORTED) -- see jw_fetch.py's own search_jw()/
resolve_search_video_item() docstrings for the full design (why video
resolution is lazy, why this is scoped to the JW Videos picker only and
not a general search feature, per Kaleb's explicit instruction). v26.07.09.10/.11: leaving the JW plugin entirely (not just backing
out of a sub-screen within it) now clears the cached OmniSearch bearer
token -- see jw_fetch.py's clear_search_token_cache(). Search (Y) and
Manual Code (SELECT, JW only) are now reachable directly from the
Categories screen too, not just after opening a category -- same
SUPPORTS_SEARCH/SUPPORTS_MANUAL_CODE gating as Browse already used.
jw_fetch.py's old "What's New (RSS)" category is now labeled "New
Issues" -- unchanged behavior (still only detects new periodical
issues via RSS), renamed because the old label implied general JW.org
news and was confirmed confusing. Multi-resolution letterboxing (v0.1.148) lets the
app run on any muOS screen size while keeping its fixed 720x720 layout
untouched -- see the SDL_RenderSetLogicalSize()/window-creation comments
in main() for how. v0.1.149: two small fixes from Kaleb's photo review --
the status/toast bar (_draw_status_bar()) now rounds its BOTTOM corners
to COL_HINT_BG (was square, only the top was rounded -- see
_round_image_bottom_corners_to_hint() call site); and epub_engine.py
substitutes the rare U+2024 "one dot leader" meter glyph (seen in some
JW.org magazine content) for U+00B7, since Liberation Sans has no glyph
for U+2024 and was drawing missing-glyph boxes -- see
_sub_missing_glyphs() in epub_engine.py's text walker. v0.1.150:
bundled font switched from Liberation Sans to Inter (OFL 1.1) -- see
FONT_PATHS comment in this file and FONT_LICENSE.txt for full
reasoning/provenance. Confirmed via direct cmap checks (not
assumption) against all 15 of Kaleb's real EPUBs across a dozen
open-source candidates -- no body-text font checked (Liberation,
Arimo, Nimbus Sans, Noto Sans, Carlito, Work Sans, Manrope, Readex
Pro, Hanken Grotesk; DejaVu was the one exception that covered every
gap but was rejected on visual grounds) natively covers the 5
confirmed-missing glyphs (index bullet U+2750, discussion-bullet
U+25B8, schedule-bullet U+25FC, breadcrumb-arrow U+27A4, checkbox-tick
U+2714). Inter was chosen for best available substitute shapes (real
check mark and triangle-bullet glyphs) plus visual preference, not
because it solves the gap outright. Full regression (all 15 books x 7
Font Sizes, all UI screens, hint bar, toast bar) passed clean before
the switch. Liberation Sans remains as an on-device system-path
fallback in FONT_PATHS (not bundled) in case the bundled Inter files
are ever missing. v0.1.151: superseded by a switch to DejaVu Sans,
after side-by-side on-device screenshot comparison -- DejaVu covers
every glyph gap found (the 5 above, plus box-drawing divider lines and
the full Hebrew block used in Bible acrostic headers) with REAL native
glyphs, not substitutes. The substitution system itself was also
reworked from a hardcoded per-font table to a dynamic one: main.py now
checks the active font's actual cmap via TTF_GlyphIsProvided32 at
startup (see the block right after FONT_PATH is resolved) and only
populates epub_engine.set_active_glyph_subs() with entries the active
font is actually missing -- for DejaVu that's an empty table, so real
glyphs render untouched. If a future font swap reintroduces a gap,
this adapts automatically instead of needing another manual audit.
v0.1.152: switched again, from DejaVu Sans to DejaVu Sans Condensed --
narrower letterforms closer to Liberation Sans's original proportions
(Kaleb's preference), same full glyph coverage confirmed via direct
cmap check (5,918 glyphs, identical to regular DejaVu Sans -- NOT the
same as DejaVu SERIF Condensed, which was also checked and rejected:
smaller glyph set, missing 4 of the 6 target glyphs, zero Hebrew).
v0.1.153: hint bar padding fix (Kaleb's photo report). DejaVu Sans
Condensed is still wider than Liberation Sans/Inter at the same pt, so
at 18pt the Library screen's longest hint string tipped over into 2
reserved lines where it used to fit in 1 -- and because hint_height()
reserves ONE shared bar height across every screen (v0.1.52 invariant),
every screen's bar got bumped to that 2-line height, even ones whose
own hint only ever draws 1 line. Confirmed via SDL_RenderReadPixels:
~40% empty padding above AND below the text at 18pt. _hint_pt() now
does a cheap (<=3pt) tie-break shrink after its existing floor-11
fallback: if a small pt reduction gets the calibration strings to wrap
into fewer lines, it takes it. Fixes 18pt (60px bar -> 36px, back to a
true 1-line bar) and 32pt (131px -> 86px, 3 lines -> 2, freeing real
body-text space) without touching 21/24/28pt, whose 2-line bars were
already proportionate (a 4pt+ trim would've been needed there to drop
a line, out of the cheap-shrink budget -- left alone deliberately).
Also v0.1.153: toast/status bar (_draw_status_bar()) redesigned from a
full-width bar to a text-hugging pill, per Kaleb's photo annotation --
was filling the full screen width with COL_PANEL even for a short
message like "Bookmark added", leaving a large empty band to the
right of the text. Now sized to the widest wrapped line + padding,
left-anchored at TOAST_PILL_MARGIN_X, fully rounded (stadium-shape,
radius=bar_h//2) via the existing fill_rect_rounded() -- no longer
needs the old erase-to-background corner helpers since it's a
floating pill, not a bar touching the screen edges. Also tightened
TOAST_ROW_PAD/TOAST_LINE_GAP (10->4, 6->3): DejaVu Sans Condensed's
TTF_FontHeight runs notably taller than its real glyph ink (confirmed
via pixel readback: ~17px reported vs ~10px actual ink at 18pt), so
the old flat padding (tuned for Liberation/Inter) compounded on top of
that into visible excess. Confirmed via pixel readback across all 7
Font Sizes and 4 real toast strings (including descenders) that
nothing clips at any size.
Also v0.1.153: tightened the shared list-row padding used by Library,
Bookmarks, the Menu popup, TOC, Storage's action list, and all 3
Download screens (Kaleb: "feel natural yet minimal"). All but TOC
route through _row_h()'s DEFAULT pad, dropped 20->14; TOC's own
explicit pad dropped 14->10; draw_download_browse()'s two-line
title+subtitle row (which predates/bypasses _row_h(), own separate
formula) dropped its matching +20->+14. Same root cause as the hint/
toast fixes: DejaVu Sans Condensed's TTF_FontHeight runs taller than
Liberation Sans/Inter's did, so the old flat pads (tuned pre-switch)
were compounding into ~46-62% dead space per row. New values restore
the original ~8px-per-side breathing room the v0.1.74 comment
describes, confirmed via pixel readback across all 7 Font Sizes with
NO clipping in any selection-highlight box or row text on any of
these screens. Storage's own info-line stats block (pad=6) was
checked and left alone -- already tight/correct, not part of this bug.
Reader body text (_reader_body_layout()) was also reviewed at Kaleb's
request: unlike the UI chrome above, its line_h is NOT built from
TTF_FontHeight() -- it uses the raw point size + a small flat leading
(6-8px), a v0.1.116 design that's independent of any one font's real
metrics, so it isn't subject to the same over-padding bug. Real risk
checked instead: at max Font Size (32pt) DejaVu's actual FontHeight
(38px) now exactly equals line_h (38px) -- zero theoretical slack,
where Liberation Sans had comfortable headroom. Stress-tested against
all 8 of Kaleb's real EPUBs at 32pt via real consecutive-line ink-gap
measurement: no overlap in any book (smallest observed gap 7px, real
text rarely hits the font's absolute ascent+descent bounding box on
both adjacent lines at once). No change made -- confirmed safe as-is,
but worth re-checking if a future font swap makes FontHeight exceed
line_h outright.

v0.1.154 BUG FIX (Kaleb's report: "%age indicator goes over 100%"):
ReaderState.page_down() (the L/R page-turn method) clamped its final
scroll position to `min(li, max(0, n - 1))` -- n-1 is the last LINE
index, a completely different (and wrong) ceiling than every other
scroll path in the app uses. UP/DOWN d-pad scrolling, and the reader's
%-complete indicator's own denominator, both correctly use
`max(0, n - body_rows)` (the scroll position that shows the final full
screen). Letting page_down() land anywhere up to n-1 meant repeated
L/R at the end of a book kept advancing scroll well past that correct
ceiling straight through to the last line -- confirmed via real
page_down() simulation against all 8 of Kaleb's books at 3 Font Sizes:
short books (front-matter-only, or under one screenful) reached pct=
300-900% before this fix. This was also the direct cause of Kaleb's
second question ("clamp so it doesn't scroll past the end of a
chapter's image or text") -- the same overshoot scrolled the last
screen mostly blank instead of stopping with content flush to the
bottom. Fixed by using the same `max(0, n - body_rows)` ceiling
page_up() and the d-pad handlers already use. Confirmed via the same
real-book simulation: all 8 books x 3 Font Sizes now land at exactly
scroll <= ceiling and pct <= 100% every time, and a direct pixel
check on the final page (New World Translation, 18pt) shows text ink
ending only 31px above the body's bottom edge -- essentially flush,
not scrolled past. Mid-document forward/backward paging re-verified
unaffected (5 pages forward + 5 back returns to the exact starting
scroll).

v0.1.155: two changes from a broader JW download/search bug-check
(downloaded and tested against "Walk Courageously With God" and the
NWT specifically, plus live network calls against every category and
all 4 video sources).
(1) BUG FIX: jw_fetch.py's lookup_pub_code() (the manual pub-code
entry path) pulled the publication title straight from the API's raw
pubName field with no HTML-unescaping. Confirmed live: the "nwt" pub
code's own pubName contains a literal "&nbsp;" entity, so the Download
Browse screen showed "...(2013&nbsp;Revision)" instead of a real
space. Fixed with html.unescape() at the 3 call sites that surface
this field (the main title, plus 2 "no EPUB available" error
messages). Confirmed the resulting real U+00A0 non-breaking-space
character IS natively provided by DejaVu Sans Condensed (checked via
TTF_GlyphIsProvided32, not assumed) before shipping, so this doesn't
trade one display bug for a missing-glyph box. Scanned 181 real items
across 3 other categories (regular browse/search path, not the manual-
code path) for the same issue -- came back clean, so this was isolated
to lookup_pub_code().
(2) NEW: X-Help overlay (SCREEN_DOWNLOAD_HELP / draw_download_help())
on the Download Sources, Categories, and Browse screens -- Kaleb: "this
code thing is confusing". Plain-language explanation of Search (Y) vs.
manual Pub Code entry (SELECT -- see v0.1.156 below for why this isn't
Y), with real examples (wcg, nwt) and where to find a pub code (the
last segment of a wol.jw.org publication URL). Scrolls if it overflows
at large Font Size (confirmed via pixel readback across all 7 sizes --
only 28pt/32pt actually need it, 4 and 10 lines respectively, both
clamp correctly). B returns to whichever of the 3 screens opened it
(app.dl_help_return_screen), not always the same one.

v0.1.156 BUG FIX (Kaleb's follow-up question on the Help text: "when
can you use title: search, I thought it was all codes all the time?"):
that confusion turned out to be a REAL, pre-existing bug the Help
screen had unknowingly documented as if it were correct behavior.
jw_fetch.py declares BOTH SUPPORTS_CATEGORIES=True and
SUPPORTS_MANUAL_CODE=True. handle_button()'s Y-button elif chain
checked SUPPORTS_CATEGORIES before SUPPORTS_MANUAL_CODE, so for the
live JW_PLUGIN config, Y ALWAYS took the category-search branch --
manual pub-code entry was completely unreachable through normal
navigation. Confirmed directly: simulated pressing Y on a real
category ("Books & Brochures") landed on "Search Books & Brochures",
never the code screen. Worse, the hint bar's OWN text (built
separately, a different elif chain that never checked
SUPPORTS_CATEGORIES at all) claimed "Y Enter Code" in this exact
situation -- the displayed hint and the real Y behavior had drifted
apart, which is exactly what made this feel confusing rather than
simply undiscoverable. Fixed by moving manual code entry to its own
button, SELECT (unused on this screen), so category-scoped search (Y)
and manual pub-code lookup (SELECT) are both independently reachable
instead of one silently shadowing the other; corrected the hint-bar
logic to add the missing SUPPORTS_CATEGORIES branch (now correctly
shows "Y Search") and to advertise "SELECT Code" as its own item.
Updated the Help screen text to match (PUB CODE is now documented
under SELECT, not Y). Confirmed via direct simulation: Y now opens
"Search Books & Brochures", SELECT independently opens the pub-code
prompt, and a real code (wcg) submitted through the SELECT path still
resolves correctly end-to-end. Also confirmed the new, slightly
longer Browse hint string (84 chars) stays comfortably under both
existing hint-bar calibration strings (98/106 chars), so no additional
calibration change was needed for it to display without clipping.

v0.1.157: same shadowing pattern as v0.1.156, found from Kaleb asking
"so when does category topic search even get used?" -- gutenberg_fetch.py
declares BOTH SUPPORTS_SEARCH=True and SUPPORTS_CATEGORIES=True, and
the Y-button elif chain checked SUPPORTS_SEARCH first, so Gutenberg
always hit the generic "Search Project Gutenberg" branch -- the
category-scoped "Search {category}" branch was unreachable for it,
mirroring exactly how SUPPORTS_CATEGORIES had shadowed
SUPPORTS_MANUAL_CODE for JW. Confirmed directly: opened Gutenberg's
"Adventure" category, pressed Y -- prompt said "Search Project
Gutenberg", not "Search Adventure". UNLIKE the JW case, this was
cosmetic rather than functional: both branches call the identical
app.start_search(value), which already threads self.dl_category
through regardless of which branch's prompt opened the box --
confirmed by actually searching "island" inside Adventure and getting
correctly-scoped results (Treasure Island, etc.) even with the
mislabeled prompt. Fixed anyway since a mismatched label is exactly
the kind of thing that reads as confusing even when nothing is
actually broken: merged the two elif branches into one -- label is
now "Search {category}" whenever a category is currently open
(regardless of which flag(s) got the plugin there), else "Search
{plugin name}", matching what start_search() actually does either
way. Confirmed via direct simulation: Gutenberg/Adventure now shows
"Search Adventure" and searches stay correctly scoped; JW/Books &
Brochures is unaffected ("Search Books & Brochures", as before); the
no-category fallback (plain plugin name) still works too. Also
checked jw_fetch.py's MANUAL_CODE_HINT text (the pub-code entry
screen's own on-screen format hint) for the same kind of confusion --
already solid (concrete worked examples, previously revised for
exactly this reason per its own comment history), no change needed.

v0.1.158: added 12 new publications to STATIC_PUBLICATIONS, per Kaleb's
request. All 12 verified LIVE against GETPUBMEDIALINKS before being
added (real pubName + confirmed EPUB availability via an actual API
round-trip for each) -- pub codes were NOT just taken on faith from the
download URLs Kaleb supplied, matching this project's standing rule.
6 of Kaleb's requested titles (rr, ia, jr, jd, bt, mbs) were already
present from an earlier session -- only the missing 12 (lr, my, th,
rj, ypq, hf, yc, mb, hl, ll, lc, lf) were added. All filed under
CATEGORY_BOOKS ("Books & Brochures") since that's the only category
this plugin has for both books and brochures -- there's no separate
CATEGORY_BROCHURES to split Kaleb's two supplied lists into. Confirmed
no duplicate pub codes anywhere in the resulting 46-entry list, that
all 12 appear correctly in a real list_items(category=CATEGORY_BOOKS)
call (36 items total, up from 24), and that the Books & Brochures
Download Browse screen renders the larger list cleanly at all 7 Font
Sizes with no errors.

v0.1.159: extended Awake! ("g") back issues to Sept 2011, per Kaleb's
request to check Watchtower/Awake!/Watchtower Study back to 2011.
EVERY month 2011-2015 individually checked against GETPUBMEDIALINKS
for all three pub codes (w, wp, g) -- not spot-checked, all 180
month-checks done live. Result at the time: Watchtower ("w") and
Public Watchtower ("wp") appeared 100% 404 for the entire 2011-2015
range. Awake! ("g") IS available: 404 through Aug 2011, then HTTP 200
every month from Sept 2011 through Dec 2015 (52 consecutive months,
zero gaps). Added AWAKE_MONTHLY_START/END and
generate_awake_monthly_issues(), wired into list_items()'s Awake
branch alongside the existing 2016+ AWAKE_BACK_ISSUES list -- Awake!
category now shows 80 total back issues (up from 28), no duplicates.
IMPORTANT CORRECTION -- see v0.1.160 immediately below: the "w"/"wp"
100%-404 finding above was actually a false negative caused by testing
the wrong issue-code FORMAT, not a real absence of EPUB content.

v0.1.160 BUG FIX / CORRECTION to v0.1.159: Kaleb supplied a real
working URL (w_E_20151215.epub) that revealed the true pre-2016
Watchtower issue-code format is DAY-based (YYYYMMDD), not month-only
(YYYYMM) -- the v0.1.159 check used month-only for the pre-2016 sweep
too (copied from the 2016+ format) and got 100% 404 as a result, wrongly
concluding EPUB didn't exist before 2016 for either edition. Re-swept
EVERY month 2011-2015 with the corrected day-based format for both
pub codes: Study Watchtower ("w") always uses day 15
(w_E_YYYYMM15.epub), Public Watchtower ("wp") always uses day 1
(wp_E_YYYYMM01.epub) -- both confirmed HTTP 200 with a real EPUB for
all 52 consecutive months, Sept 2011 through Dec 2015, zero gaps
(Aug 2011 and earlier still genuinely 404 for both). Also confirmed
the Jan 2016 boundary is clean: the day-based codes 404 from Jan 2016
on, while the existing month-only codes succeed from exactly that
point -- no overlap between the two eras. Added
WATCHTOWER_MONTHLY_START/END, W_DAY/WP_DAY constants, and
generate_w_pre2016_issues()/generate_wp_pre2016_issues(), wired into
list_items()'s Watchtower branch alongside the existing 2016+
generators. CATEGORY_WATCHTOWER now shows 259 total items (179 "w" +
80 "wp", up from roughly a third that before), no duplicate issues.
Confirmed via real list_items(category=CATEGORY_WATCHTOWER) call and
rendered the full 259-item list through draw_download_browse() at all
7 Font Sizes with no errors.

v0.1.161 BUG FIX (Kaleb's report: NWT chapters -- especially Psalms --
opening "a couple lines in" rather than at the true top, worse for
Hebrew/poetry-heavy formatting). Root cause traced structurally (char
offsets and line counts only -- never the actual scripture text):
_ensure_page_built()'s anchor-based scroll positioning (used by
_jump_chapter() and TOC taps) unconditionally applied a "look back 2
lines from the target" adjustment, regardless of how far the target
actually was from the top of the page. Each Bible chapter already
lives in its own split file with a "chapterN" anchor placed at verse
1 -- so any heading/superscription content BEFORE that anchor was
silently hidden except for its last 2 lines. Checked all 150 Psalms
structurally: 120 of 150 (80%) have MORE than 2 lines of such content
before their anchor -- Psalm 1 alone has 8, landing scroll at 6
instead of 0. This is NOT actually Hebrew-specific -- it's a general
property of anchor-vs-heading placement that only becomes visible
once there's more than 2 lines of pre-anchor content, which happens
to be common in Psalms/poetry but isn't caused by the Hebrew glyph
support itself. Confirmed Bible-wide, not just Psalms, per Kaleb's
request to check recursively: swept ALL 1189 anchor-based chapter nav
points across the entire NWT (every book, not a sample) -- before the
fix, many were nonzero; after the fix, zero exceptions. Fix: only
apply the 2-line lookback when the anchor target is actually off-
screen (target_line >= body_rows) -- when it's already within the
first screen (the overwhelming majority of fresh chapter-opens), scroll
stays 0, showing all heading content from the true top, matching what
_jump_chapter() already intended (it explicitly sets self.scroll = 0
right after goto(), which this code was silently overwriting).
Confirmed the legitimate deep-anchor case (bookmark restore, a
same-file link far down a long combined page) still gets the helpful
lookback: synthetic off-screen target in Psalm 119 (chosen for being
the Bible's longest chapter) still landed at exactly target_line - 2,
unaffected. Full app regression and the Courage+NWT deep bug-check
both re-run clean after this change.

v0.1.162 BUG FIX (Kaleb's question: "would a reference at the complete
end of an article scroll back off the screen now that we have the
100% scroll fix?"). Turned out to be a real, related bug -- same class
as v0.1.154 (page_down()'s pct>100% overshoot), reachable through a
DIFFERENT path that v0.1.154 never touched. Confirmed directly: a
target on the very last line of Psalm 119 (737 lines, body_rows=24)
landed scroll at 734 via the anchor/bookmark-restore path -- but the
ceiling page_down()/the pct display both use is only 713, so pct read
102% again, just via a footnote/cross-reference jump instead of a
page-turn button press. The target itself stayed visible either way
(mathematically guaranteed for a true end-of-chapter position), so
this was a pct-display bug, not a content-hiding one. Root cause:
neither of _ensure_page_built()'s two scroll-setting branches
(bookmark-restore, anchor-jump) clamped their result against the same
ceiling page_down() respects -- each computed target_line from raw
document position with no awareness of it. Fix: added one clamp,
`self.scroll = min(self.scroll, max(0, len(self._lines) - body_rows))`,
applied once after both branches, matching page_down()'s own formula
exactly. Confirmed via the same real Psalm 119 test: scroll now clamps
to exactly 713, pct reads exactly 100% (never over), and the target
is still fully visible -- now at the bottom of the screen rather than
near the top, which is the more natural place for the literal last
thing in a chapter to sit. Reran the full recursive Bible-wide check
from v0.1.161 with this same end-of-chapter scenario: swept all 1189
anchor-based chapters, testing a jump to each chapter's own last line
-- zero problems across the board (no pct>100%, no scroll exceeding
the ceiling, target always visible). Full app regression and the
Courage+NWT deep bug-check both re-run clean after this change too.

UI: 5 color themes (Default, Dim Warm, Deep Amber, Red Shift, Adventure)
via THEMES list + apply_theme(index) -- rebinds module-level COL_*
globals that every draw_* function already reads by name, so adding a
6th theme is just one new dict entry, no per-screen code changes.
Dim Warm/Deep Amber/Red Shift are bedtime palettes (progressively less
blue, more amber/red). Saved as settings.json "theme_index".
Global Font Size setting scales ALL UI text (reading + hint bar + menus
+ Library/Chapters/Storage) via dynamic row heights/wrapping
(_row_h(), _fit_text()) -- nothing overflows at any of the 7 font-size
steps. If something clips/overlaps at large Font Size, it's almost
certainly a spot still using a fixed pixel constant instead of one of
these two helpers.
Selector highlights, popup windows, and the hint bar's top corners are
rounded (fill_rect_rounded(), CORNER_RADIUS = 6px scaled, 3px for the
text-entry keyboard cells specifically -- tighter clearance there).
No SDL2_gfx linked; this is a cheap quarter-circle mask approximation.
Text color is fully theme-driven system-wide -- no hardcoded colors.

JW.org plugin (jw_fetch.py, PRIVATE, never publish): category picker
(Bibles/Books & Brochures/Tracts/Watchtower/Awake!/Meeting Workbooks),
search scoped per-category, manual pub-code entry. All pub codes
individually verified live against GETPUBMEDIALINKS before being
hardcoded -- never guessed. Watchtower and Meeting Workbook have full
generated back-issue lists (safe: both are non-monthly-but-regular).
Awake! has a hard-coded back-issue list instead (2016-2025, 28 issues)
since its publish frequency changed twice (6/yr 2016-17, 3/yr 2018-21,
1/yr 2022+) -- see jw_fetch.py's own docstring for the verification
method and how to extend it when a new issue ships.
Gutenberg plugin (gutenberg_fetch.py, public): handles both plain <img>
covers and SVG-wrapped covers (<svg><image xlink:href>); download
screens show a spinner + elapsed seconds instead of static "Loading...";
any spine page that renders fully blank (no text, no images) logs to
data/render_issues.log and shows a visible on-screen note.

Architecture, three files:
  main.py         SDL2/ctypes UI, App class (all mutable reader state),
                   ImageLoader (background decode, priority queue),
                   ReaderState (current file/anchor/history)
  epub_engine.py  EpubDocument: manifest/spine/TOC (NCX+nav) parsing,
                   get_page() (HTML->wrapped text+links+images+anchors),
                   pure stdlib only
  mini_jpeg.py    from-scratch JPEG decoder (no PIL/Pillow available),
                   full progressive JPEG (SOF2) support since v0.2.0.
                   Fallback path only as of v0.1.80 -- see native_image.py.
                   Remains JPEG-only (native_image.py handles every other
                   format -- see its own docstring)
  native_image.py v0.1.80+ (renamed from native_jpeg.py in v0.1.146 once
                   v0.1.145 generalized it beyond JPEG): ctypes bridge to
                   the system libSDL2_image (confirmed present on RG
                   CubeXX-H muOS at /usr/lib) for real C-speed decode of
                   JPEG/PNG/TIF/WEBP/JXL/AVIF. decode_jpeg() in main.py
                   tries this first, falls back to mini_jpeg.py
                   automatically if unavailable/fails (JPEG only)

Recurring bug shape to watch for: UNIT MISMATCHES between "_lines[]
index" (li) and "visual screen rows" (row). An image is ONE _lines[]
entry but costs IMG_BOX_ROWS (14) visual rows to draw. Any code that
scrolls/pages MUST walk li and row as separate counters (see
App._rows_for_li(), draw_reader(), visible_span_indices() for the
canonical pattern) -- mixing them is exactly what caused a real
image-skip/cutoff bug early on. If a report sounds like "images
skip/cut off/reappear when paging," check this first.

Chapter/day navigation (L2/R2, and the "Chapters" TOC screen) are TWO
SEPARATE systems, easy to conflate when debugging:
  - Chapters screen = doc.toc, straight from the EPUB's NCX/nav (coarse
    -- e.g. one "January" entry for a whole month in a daily-text book).
  - L2/R2 = App._chapter_nav_points, a heuristic (chapterN anchors, else
    TOC, else weekday-prefix detection for daily-text books, else raw
    spine) built once per book open. _jump_chapter()'s bisect math must
    handle sitting BEFORE the first nav point (front matter) correctly.

Image cache keys are ALWAYS "{book_id}__{internal epub path}" (see
App._img_key), book_id = sha1(book_path)[:16], flat directory
(IMG_CACHE_DIR), no per-book subfolders. Per-book size/delete is a
filename-prefix match (book_cache_size_bytes/delete_book_cache) -- do
NOT introduce a second scoping scheme. Disk cache is crash-safe;
MAX_CACHE_BYTES 500MB, MAX_INMEMORY_IMAGES 80.
Decode-target box (ImageLoader.TARGET_BOX_W/H, 480x272) only affects
which scale_n mini_jpeg decodes at -- NOT the on-screen display size
(that's SW-40 wide x IMG_BOX_ROWS tall, computed in draw_reader()).

Fonts: bundled assets/font.ttf (+ -bold/-italic/-bolditalic variants)
are Liberation Sans 2.1.5, SIL OFL, checked FIRST in FONT_PATHS --
confirmed by device evidence that DejaVu isn't actually present on this
hardware. Rebuilt v0.1.76 directly from the official
liberationfonts/liberation-fonts GitHub repo at tag 2.1.5 (fontforge
build from source, not a third-party mirror) -- see FONT_LICENSE.txt
for the exact commit and verification method.

get_page() returns SIX values: text, links, images, anchor_offsets,
styles, para_spans. Every call site must unpack all 6. ParaSpan kinds
still active: superscript, caption, box_rule only (JW paragraph classes
sm/sh/si/sb/sj were removed -- caused incorrect italic/indent/grey
rendering on Bible text; pagenum markers also removed, silently
skipped). draw_reader() resolves active ParaSpan per line via
_line_abs_offsets[] (precomputed once in _ensure_page_built).
_page_text_cache (200-entry RAM-only LRU) eliminates XML parse lag on
distant chapter/scripture jumps. _wrapped_cache, keyed by (href,
font_size_index), skips the SDL_ttf word-wrap pass on revisits to a
page already built at the current font size (same-thread memoization;
not populated from the background prefetch thread since SDL_ttf calls
off the main thread haven't been verified safe on this hardware). Both
cleared on open_book().

Bold/italic: StyleSpans from walk() -> _compute_line_style_runs() ->
_line_segments() -> per-segment render with body_styled(bold, italic).
epub_engine.py's walk() treats <tr> specially: a row is forced onto its
own line ONLY if its cells' average text length exceeds ~10 chars (real
chapter titles) -- short compact grids (like the JW Bible's book-nav
table) flow/wrap naturally instead. This threshold was derived from two
real Gutenberg books with different TOC table shapes; if a future table
renders wrong, get real numbers from the actual book before adjusting
the threshold, don't guess a new one.

Every fix ships with an AST-parse check and, wherever feasible, a
standalone simulation (a types.SimpleNamespace/plain-function harness
reproducing the exact bug scenario) run BEFORE delivery, not just after.
This sandbox has real SDL2 installed (SDL_VIDEODRIVER=dummy,
SDL_AUDIODRIVER=dummy) -- main.py, App, and every draw_*/handle_button
function can be imported and driven for real, no physical device
needed. After ANY edit touching handle_button()'s screen dispatch chain
(the long if/elif app.screen==... ladder), re-verify by actually
constructing App(renderer) and calling handle_button() with real button
strings -- AST-parsing alone has missed a real bug here before (a
str_replace that silently deleted a critical "elif" line and merged two
screens' input handling together; still syntactically valid Python).
Crash log for boot/runtime failures: /tmp/picoreader_crash.log.

===========================================================================
TARGET HARDWARE: Anbernic RG CubeXX-H, 720x720 display, running MustardOS
(muOS) Funky Jacaranda. The device has 1GB of RAM total. This is a hard
constraint on everything: avoid unbounded caches, avoid loading whole
large assets into memory when a streaming/chunked approach is possible,
and be skeptical of any change that meaningfully grows steady-state
memory use. When in doubt, ask before adding a cache, buffer, or preload
step that isn't obviously small and bounded.

OPEN SOURCE ATTRIBUTION -- ALWAYS FLAG IT: Any time a change ships,
touches, or references code/assets that did not originate in this
project, say so explicitly and plainly. Applies to the bundled fonts
(Liberation Sans family, SIL OFL), MustardOS/muOS source referenced for
launcher/controller behavior, and any future library or snippet pulled
in from elsewhere. Never let an open-source dependency pass by silently
as if it were original work.

MUSTARDOS SOURCE ACCESS: The MustardOS GitHub org (github.com/MustardOS)
and its "internal" repo (board configs, sdl_map, func.sh, etc.) ARE
reachable via web_fetch/the GitHub Contents API from this environment --
try that first. Only ask the user to open a GitHub page and paste its
contents back if a direct fetch genuinely fails (blocked path, private
repo, rate limit, etc.) -- don't ask preemptively when a fetch would work.

TROUBLESHOOTING ORDER: before changing any code, check (1) this file's
own AI notes/changelog, (2) the relevant GitHub repo's source/issues/
README, (3) muos.dev docs/forums. All three are directly web_fetch-able.
Discord is NOT fetchable from here -- if a relevant Discord thread might
have the answer, ask the person to paste the text/screenshot rather than
trying to fetch it. Only fall back to theorizing from first principles
once those sources come up empty, and say so explicitly when that's
what's happening (don't present a guess as a confirmed root cause).

CURRENT STATE header above may go stale (see VERSION NUMBERING below) --
this project's real current version lives in the changelog, not the
header line.

DELIVERY FORMAT -- ALWAYS BOTH: Every delivery that changes app files
must include (1) the individual changed file(s) and (2) a full .muxapp
zip bundle containing everything needed to run (main.py + epub_engine.py
+ mini_jpeg.py + assets/ + mux_launch.sh, etc.), so the person can test
on-device quickly AND push individual file diffs to GitHub. Never ship
only one of the two.

.MUXAPP ZIP STRUCTURE -- GET THIS EXACTLY RIGHT, IT HAS REGRESSED BEFORE:
the zip's TOP-LEVEL ENTRY must be a "PicoReader/" folder containing every
file (main.py, epub_engine.py, mini_jpeg.py, jw_fetch.py,
gutenberg_fetch.py, mux_launch.sh, assets/, README.md, LICENSE.md) --
files must NOT sit loose at the zip root. Confirmed against a real
working on-device install. Build it by staging everything inside a
"PicoReader/" directory, then zip from ONE LEVEL ABOVE it:
    zip -r PicoReader.muxapp PicoReader/
NOT from inside the staging folder itself (zip -r ../out.muxapp .) --
that omits the wrapping folder and makes muOS's unpacker dump files
straight into applications/ instead of applications/PicoReader/, which
breaks the install silently (app just won't launch, no clear error).
This exact mistake has happened more than once across sessions --
always run `unzip -l` on the finished .muxapp and confirm every path
listed starts with "PicoReader/" before delivering it.

NEVER ASSUME -- ALWAYS ASK: Standing instruction from the project owner.
Get clarification before making changes whenever the request, root cause,
or intended behavior is not fully clear from evidence already gathered
(crash logs, screenshots, real code, or explicit confirmation). Don't
present theories as confirmed fixes. Don't start editing code on an
ambiguous request -- ask first, then act once confirmed.

VERSION NUMBERING (scheme changed v26.07.09.01): format is YY.MM.DD.XX
-- today's date plus a same-day counter (01, 02, 03...) that resets each
new calendar day. The "CURRENT STATE" line near the top of this docstring
is the single source of truth for the current version. Before assigning
a new version number: (1) confirm today's real date rather than assuming,
(2) grep this file for inline "# vYY.MM.DD." comments to find the
highest existing date+counter and sanity-check the header line hasn't
gone stale, (3) if it's the same calendar day as the last entry,
increment XX; if it's a new day, reset to 01. Pre-scheme-change history
(v0.1.1 through v0.1.162) stays in old format, untouched -- don't
renumber it.

START is deliberately unbound outside the Reader screen -- reserved for
the downloader plugin trigger, which ended up bound to Library-screen L2
instead once actually built. Don't repurpose it without checking first.

DOWNLOADER PLUGINS: gutenberg_fetch.py (public/GitHub-safe) and
jw_fetch.py (PRIVATE -- never publish this one) are optional,
self-contained modules main.py loads defensively at import time into
DOWNLOAD_PLUGINS (empty list if neither file is present -- the app must
work identically either way). Contract: PLUGIN_NAME, list_items(query,
page)->(items,has_next,err), download(item,dest_dir)->(ok,msg,path).
See gutenberg_fetch.py's docstring for the full contract.

===========================================================================
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
import pickle
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
    import epub_engine
    from epub_engine import EpubDocument, ReaderState, TocEntry
    from mini_jpeg import decode_jpeg as _decode_jpeg_pure_python, peek_jpeg_size
except Exception:
    import traceback
    _boot_log("\n--- IMPORT FAILURE (epub_engine / mini_jpeg) ---\n")
    _boot_log(traceback.format_exc())
    _boot_log("--- END ---\n")
    sys.exit(1)

# v0.1.80 -- native_image.py is OPTIONAL, same spirit as the downloader
# plugins below: the app must work identically whether it's present/
# loadable or not. It's a ctypes bridge to the system's libSDL2_image
# (confirmed present on the RG CubeXX-H's muOS build at /usr/lib --
# Kaleb found it via SFTP file browsing), used to decode images at real C
# speed instead of mini_jpeg.py's pure-Python JPEG-only decoder. See
# native_image.py's own module docstring for the full story (this is the
# actual fix for the image-decode freeze bug, not just a speed
# optimization -- a C decode doesn't hold Python's GIL the whole time the
# way mini_jpeg.py's decode loop does). mini_jpeg.py is NOT being
# removed: if native_image fails to load OR fails to decode a specific
# file for any reason, decode_jpeg() below falls straight back to the
# pure-Python path, per-call, silently.
# v0.1.146: renamed from native_jpeg.py -- Kaleb asked for a name that's
# more obviously accurate now that this handles more than JPEG (v0.1.145
# generalized it to every SDL2_image format: JPG/PNG/TIF/WEBP/JXL/AVIF).
try:
    import native_image
except Exception:
    native_image = None


def decode_jpeg(jpeg_bytes, scale_n=4):
    """Drop-in replacement for mini_jpeg.decode_jpeg() with the identical
    (rgb_bytes, w, h) contract. Tries the native libSDL2_image path first
    (fast, doesn't hold the GIL); falls back to the pure-Python decoder
    on any failure -- missing library, decode error, anything. This
    function is what every other call site in this file uses; neither
    ImageLoader nor anything else needs to know or care which decoder
    actually ran. NOTE: still named decode_jpeg (not decode_image) --
    kept as-is in v0.1.146's rename since every call site already treats
    it as "the" image decode entry point regardless of format, so
    renaming this specific one would only add churn across the file
    without changing behavior; the module/function names that actually
    described a JPEG-only assumption (native_jpeg.py, decode_jpeg_native)
    were the misleading ones and those did get renamed."""
    if native_image is not None:
        try:
            return native_image.decode_image_native(jpeg_bytes, scale_n=scale_n)
        except Exception as e:
            _boot_log(f"native_image decode failed, falling back to mini_jpeg: {e}\n")
    return _decode_jpeg_pure_python(jpeg_bytes, scale_n=scale_n)

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

# v0.1.90: direct reference to jw_fetch specifically (not just "any
# plugin in DOWNLOAD_PLUGINS") for the video-download feature, since
# video support is JW-specific (gutenberg_fetch has no videos) and only
# exists if jw_fetch has the v0.1.90 list_video_items()/download_video()
# functions -- older jw_fetch.py builds won't have them, so this checks
# for the attribute rather than assuming any jw_fetch import supports it.
JW_PLUGIN = next((m for m in DOWNLOAD_PLUGINS if m.__name__ == "jw_fetch"), None)
JW_VIDEO_SUPPORTED = bool(JW_PLUGIN and hasattr(JW_PLUGIN, "list_video_items"))

# ============================================================
# Paths
# ============================================================
APP_DIR = os.path.dirname(os.path.abspath(__file__))


def find_books_dir():
    """v0.1.102: SD1/SD2-aware location for muOS's shared 'Book Reader'
    content folder -- same principle/candidates as jw_fetch.py's
    find_movies_dir() for ROMS/movies. muos.dev documents "Book Reader"
    as an existing muOS system (https://muos.dev/systems/misc/bookreader,
    currently served by the third-party mReader core) with its own
    ROMS/Book Reader content folder. Sharing that folder -- rather than
    keeping books inside PicoReader's own app directory -- is what would
    let PicoReader register as an alternative core for the SAME system
    later, and just generally puts books where the rest of muOS's
    content already lives. Checks both real muOS mount points and
    returns the first that exists; falls back to creating the SD1 path
    if neither exists yet, so a fresh setup still works.

    Kaleb confirmed OK losing existing bookmarks/reading-progress for
    this move (personal library, testing device only) -- so unlike
    find_movies_dir() there's no old-location migration here, just a
    straight switch. If that ever matters for someone else's setup:
    bookmarks are keyed by the book's full file path (see
    load_bookmarks/save_bookmarks), so moving this folder orphans any
    progress recorded under the old path -- worth a real migration step
    (rewrite matching bookmarks.json keys) rather than silent data loss
    if a future move needs to preserve reading history."""
    candidates = [
        "/mnt/sdcard/ROMS/Book Reader",
        "/mnt/mmc/ROMS/Book Reader",
    ]
    for path in candidates:
        if os.path.isdir(path):
            return path
    fallback = candidates[0]
    try:
        os.makedirs(fallback, exist_ok=True)
    except OSError:
        pass
    return fallback


LIBRARY_DIR = os.environ.get("EPUB_LIBRARY_DIR", find_books_dir())
DATA_DIR = os.path.join(APP_DIR, "data")
BOOKMARKS_PATH = os.path.join(DATA_DIR, "bookmarks.json")
SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")
LIBRARY_CACHE_PATH = os.path.join(DATA_DIR, "library_cache.json")
PINNED_PATH = os.path.join(DATA_DIR, "pinned.json")
ANCHOR_CACHE_DIR = os.path.join(DATA_DIR, "anchor_cache")
IMG_CACHE_DIR = os.path.join(DATA_DIR, "img_cache")
# v26.07.09.18: disk cache for WRAPPED (laid-out) page results, but ONLY
# for genuinely extreme pages (see LARGE_PAGE_LOADING_THRESHOLD) -- NOT
# a general-purpose cache like IMG_CACHE_DIR. Confirmed via real
# measurement: this only ever applies to ~2% of pages across a real
# library (2 pages found across 6 whole books tested), and costs single-
# digit MB per page (6.37MB for the single largest page found, Enjoy
# Life Forever's "Track Your Bible Reading"). Kaleb's explicit request:
# keep this narrow -- extreme pages only, not a blanket disk cache.
WRAP_CACHE_DIR = os.path.join(DATA_DIR, "wrap_cache")
# v26.07.09.17/.18/.20/.21: threshold (in characters) above which a page
# (a) shows a loading screen with a live percentage before the
# synchronous wrap (draw_reader()) and (b) is persisted to WRAP_CACHE_DIR
# so that cost is only ever paid ONCE per (book, page, font size), not
# every visit. v26.07.09.21 CORRECTION: v26.07.09.20's 50K was based on
# a mistaken cross-book comparison (Kaleb clarified all his real timing
# numbers were actually Enjoy Life Forever's "Track Your Bible Reading"
# page throughout, at two font sizes -- not two different books/pages as
# I'd assumed). Real, consistent numbers for that ONE 4,532,633-char
# page: 85s cold wrap at the largest font, 78s at 21pt -- both ~17-19
# microseconds/char, and confirmed via direct sandbox measurement
# (same page, same two font sizes) that this scales linearly and
# consistently, no anomaly. Kaleb's own criteria: pages estimated over
# ~2.5s get the loading screen+counter; pages over ~5s get pre-rendered
# at book-open instead of waited for on-demand (see
# PRERENDER_THRESHOLD below). Using the slightly-slower 18.8 us/char
# (largest-font) rate for both, conservatively:
#   2.5s / 18.8us = ~133,000 chars -- LARGE_PAGE_LOADING_THRESHOLD
#   5.0s / 18.8us = ~266,000 chars -- PRERENDER_THRESHOLD
LARGE_PAGE_LOADING_THRESHOLD = 133_000
# v26.07.09.21: pages over this size are wrapped proactively when the
# book is OPENED (see App._prerender_extreme_pages_scan(), backgrounded
# since it's pure XML parsing/zip reads -- no SDL_ttf calls, unlike the
# wrap itself -- see that method's docstring for why this needed its own
# background-thread safety check, same class of risk the chapter-nav
# scan already ran into once), rather than waited for on first
# navigation. Both extremely rare in practice: exhaustive scan across
# Kaleb's whole tested library (4,980 real pages) found only 14 pages
# over the OLD 100K threshold, so pre-rendering the handful over 266K
# adds negligible book-open cost for the vast majority of books that
# have zero qualifying pages at all.
PRERENDER_THRESHOLD = 266_000
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
SDL_WINDOW_FULLSCREEN_DESKTOP = 0x00001001

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


class SDL_DisplayMode(ctypes.Structure):
    _fields_ = [("format", ctypes.c_uint32), ("w", ctypes.c_int),
                ("h", ctypes.c_int), ("refresh_rate", ctypes.c_int),
                ("driverdata", ctypes.c_void_p)]


SDL.SDL_CreateWindow.restype = ctypes.c_void_p
SDL.SDL_CreateRenderer.restype = ctypes.c_void_p
SDL.SDL_GetError.restype = ctypes.c_char_p
SDL.SDL_GetDesktopDisplayMode.argtypes = [ctypes.c_int, ctypes.POINTER(SDL_DisplayMode)]
SDL.SDL_GetDesktopDisplayMode.restype = ctypes.c_int
SDL.SDL_RenderSetLogicalSize.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
SDL.SDL_RenderSetLogicalSize.restype = ctypes.c_int
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
# v0.1.151: for runtime "does the ACTIVE font actually have this glyph"
# checks (drives the glyph-substitution system below) rather than
# hardcoding substitutions based on whichever font happened to be
# bundled at the time someone last checked. TTF_GlyphIsProvided32 takes
# a full Uint32 codepoint (unlike the older 16-bit TTF_GlyphIsProvided,
# which can't represent anything above the Basic Multilingual Plane
# ceiling some of these symbols sit near) and returns the glyph index,
# or 0 if the font has no glyph for that codepoint.
TTF.TTF_GlyphIsProvided32.restype = ctypes.c_int32
TTF.TTF_GlyphIsProvided32.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
SDL.SDL_CreateRGBSurfaceFrom.restype = ctypes.c_void_p
SDL.SDL_CreateRGBSurfaceFrom.argtypes = [
    ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32,
]
SDL.SDL_CreateTextureFromSurface.restype = ctypes.c_void_p
HAS_TTF = TTF.TTF_Init() == 0
_boot_log(f"TTF_Init: {'OK' if HAS_TTF else 'FAILED -- ' + SDL.SDL_GetError().decode('utf-8', errors='replace')}\n")

FONT_PATHS = [
    # v0.1.152: switched from DejaVu Sans to DejaVu Sans Condensed --
    # same 5,918-glyph coverage (confirmed via direct cmap check, not
    # assumption -- unlike DejaVu SERIF Condensed, which was also
    # checked and rejected: smaller glyph set, missing 4 of our 6 target
    # glyphs, and zero Hebrew coverage. "Condensed" doesn't mean the
    # same thing across DejaVu's Sans vs Serif branches). Narrower
    # letterforms than regular DejaVu Sans, closer in spirit to the
    # original Liberation Sans proportions Kaleb preferred, while
    # keeping every glyph gap closed (Dingbats/Geometric Shapes,
    # box-drawing dividers, full Hebrew block) with real native glyphs
    # -- no substitution table entries are active for this font either
    # (see the dynamic TTF_GlyphIsProvided32 check below).
    # v0.1.151: bundled font switched from Inter to DejaVu Sans (public
    # domain-ish Bitstream Vera-derived license, see FONT_LICENSE.txt).
    # Confirmed via direct cmap inspection: DejaVu covers every glyph
    # gap found across all 15 of Kaleb's real EPUBs natively (index/
    # schedule bullets, discussion-bullets, breadcrumb arrows, checkbox
    # ticks, box-drawing divider lines, and the full Hebrew block used
    # in Psalm acrostic headers). Inter and Arimo were both checked and
    # rejected for this role specifically because neither bundles
    # Dingbats/Geometric Shapes or Hebrew -- that's a real, verified gap
    # in those fonts, not a bundling oversight.
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

# v0.1.151: DYNAMIC glyph-substitution table -- replaces the old
# hardcoded-per-font approach (v0.1.149/150 assumed Liberation Sans,
# then Inter, lacked these glyphs; each font swap needed a manual
# re-audit of every known problem book). Instead, this checks the
# ACTIVE bundled font's real cmap via TTF_GlyphIsProvided32 once at
# startup and only substitutes codepoints it's actually missing --
# e.g. DejaVu Sans (as of v0.1.151) has every one of these natively, so
# this table ends up empty and epub_engine.py renders the real glyphs
# untouched. If a future font swap brings back a gap, this catches it
# automatically without another manual per-book audit.
# candidate -> (substitute, human label for the boot log)
_GLYPH_SUB_CANDIDATES = {
    0x2024: (0x00B7, "ONE DOT LEADER -> MIDDLE DOT"),
    0x2750: (0x25A0, "UPPER RIGHT DROP-SHADOWED WHITE SQUARE -> BLACK SQUARE"),
    0x25B8: (0x2023, "BLACK RIGHT-POINTING SMALL TRIANGLE -> TRIANGULAR BULLET"),
    0x25FC: (0x25A0, "BLACK MEDIUM SQUARE -> BLACK SQUARE"),
    0x27A4: (0x2192, "BLACK RIGHTWARDS ARROWHEAD -> RIGHTWARDS ARROW"),
    0x2714: (0x2713, "HEAVY CHECK MARK -> CHECK MARK"),
}
_ACTIVE_GLYPH_SUBS = {}
if HAS_TTF and FONT_PATH:
    _probe_font = TTF.TTF_OpenFont(FONT_PATH.encode(), 18)
    if _probe_font:
        for _cp, (_sub_cp, _label) in _GLYPH_SUB_CANDIDATES.items():
            if not TTF.TTF_GlyphIsProvided32(_probe_font, _cp):
                _ACTIVE_GLYPH_SUBS[chr(_cp)] = chr(_sub_cp)
                _boot_log(f"glyph sub ACTIVE: {_label} (font lacks U+{_cp:04X})\n")
            else:
                _boot_log(f"glyph sub not needed: font has U+{_cp:04X} natively\n")
        TTF.TTF_CloseFont(_probe_font)
    else:
        # Can't probe -- fail safe by assuming all candidates need
        # substituting, same as the old hardcoded behavior, rather than
        # risking tofu boxes with no fallback at all.
        _boot_log("glyph sub: probe font failed to open, substituting all candidates as a safe default\n")
        _ACTIVE_GLYPH_SUBS = {chr(cp): chr(sub) for cp, (sub, _l) in _GLYPH_SUB_CANDIDATES.items()}

# Also verify the three hardcoded Library-screen icon glyphs (pin heart,
# continue-reading pointer, finished checkmark -- drawn directly in
# draw_library(), not routed through the substitution table above since
# they're app UI chrome, not EPUB content). No fallback is wired up for
# these today because every font checked so far (Liberation, Inter,
# DejaVu) has all three -- but this logs a boot warning rather than
# staying silent if a future font swap ever breaks that assumption, so
# it surfaces immediately instead of needing another manual screenshot
# audit to notice.
if HAS_TTF and FONT_PATH:
    _probe_font2 = TTF.TTF_OpenFont(FONT_PATH.encode(), 18)
    if _probe_font2:
        for _cp, _label in [(0x2665, "pin heart"), (0x25BA, "continue-reading pointer"), (0x2713, "finished checkmark")]:
            if not TTF.TTF_GlyphIsProvided32(_probe_font2, _cp):
                _boot_log(f"WARNING: Library icon glyph U+{_cp:04X} ({_label}) missing from active font -- will render as tofu, no fallback wired up\n")
        TTF.TTF_CloseFont(_probe_font2)

epub_engine.set_active_glyph_subs(_ACTIVE_GLYPH_SUBS)

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
        # v26.07.10.10: bg lightened from (18,18,22) to (43,43,50) --
        # Kaleb's request, after iterating live through several contrast
        # targets (3:1 -> 2.7:1 -> 2.2:1 -> 1.9:1 -> settled on 1.5:1,
        # "subtle but just barely noticeable") so _draw_screen_frame()'s
        # corner mask (reverted to pure black this same session, see its
        # own docstring) reads as a visible edge instead of disappearing
        # into an almost-identical near-black bg. Measured: 1.49:1
        # against pure black -- deliberately BELOW the WCAG 3:1 UI
        # minimum discussed earlier in the session; this was an explicit
        # aesthetic choice (subtle, not a strong edge), not an
        # accessibility target.
        "bg": (43, 43, 50), "panel": (28, 28, 34), "text": (225, 225, 230),
        "dim": (140, 140, 150), "link": (61, 125, 118), "link_sel": (222, 178, 108),
        # v0.1.130: hint_bg/hint_text dimmed (Kaleb: hint bar felt too bright/
        # prominent) -- hint_bg lifted from "bg minus ~8" to "bg minus 3" so
        # the bar recedes into the page instead of reading as a separately-
        # lit panel. hint_text initially set to match this theme's own
        # "dim" tone exactly, but that FAILED WCAG AA contrast (4.5:1) on 3
        # of the 5 themes once checked -- this theme's dim tone already
        # passes (5.74:1) against the new hint_bg, so it's used as-is.
        # Kaleb confirmed the direction via a rendered mockup (real bundled
        # font, actual RGB values) before this was applied.
        # v0.1.147: Kaleb wants the hint bar visibly grey rather than
        # near-black -- hint_bg lifted from (15,15,19) to (34,34,39),
        # roughly midway to this theme's own panel color (28,28,34) so it
        # reads as a genuinely lighter panel, not just a darker copy of
        # bg. Contrast against hint_text recomputed (WCAG relative
        # luminance, not eyeballed): 4.76:1, still comfortably above the
        # 4.5:1 AA floor the v0.1.130 comment above established as the
        # bar for this project -- hint_text itself didn't need to change
        # here (this theme had contrast headroom to spare).
        "hint_bg": (34, 34, 39), "hint_text": (140, 140, 150),
        "accent": (95, 168, 156), "menu_sel_bg": (45, 45, 55), "warning": (230, 90, 90),
    },
    {
        # ~2700K-ish warm gray/amber -- gentle general night reading,
        # not as aggressive as the two below.
        "name": "Dim Warm",
        # v26.07.10.10: bg lightened, same reasoning/session as Default
        # theme above -- see its comment. 1.50:1 against pure black.
        "bg": (52, 42, 33), "panel": (36, 29, 23), "text": (201, 184, 150),
        "dim": (140, 120, 95), "link": (217, 148, 74), "link_sel": (240, 190, 120),
        # v0.1.130: see Default theme's comment. This theme's exact "dim"
        # tone (140,120,95) only measured 4.43:1 against the new hint_bg --
        # just under WCAG AA's 4.5:1 -- so hint_text is a slightly brighter
        # version of the same warm hue (not a different color, just +4%
        # scaled up) rather than the literal "dim" tuple, landing at 4.75:1.
        # v0.1.147: same "grey, not near-black" request as Default theme
        # above -- hint_bg lifted from (23,17,13) to (40,32,25). This
        # theme's existing hint_text no longer cleared 4.5:1 against the
        # brighter hint_bg (dropped to 4.07:1), so hint_text was scaled
        # up ~7% (same warm hue, not a different color -- same technique
        # the v0.1.130 comment below used originally) to land at 4.60:1.
        "hint_bg": (40, 32, 25), "hint_text": (156, 134, 106),
        "accent": (201, 140, 80), "menu_sel_bg": (55, 43, 32), "warning": (216, 110, 80),
    },
    {
        # Strong blue-light reduction, sepia/candlelight feel.
        "name": "Deep Amber",
        # v26.07.10.10: bg lightened, same reasoning/session as Default
        # theme above -- see its comment. 1.50:1 against pure black.
        "bg": (53, 42, 30), "panel": (30, 23, 16), "text": (184, 122, 61),
        "dim": (130, 92, 55), "link": (201, 120, 46), "link_sel": (230, 165, 80),
        # v0.1.130: see Default theme's comment. This theme's exact "dim"
        # tone only measured 3.26:1 against the new hint_bg -- well under
        # WCAG AA -- so hint_text is a brighter version of the same hue
        # (scaled ~24% up, not a different color), landing at 4.61:1.
        # v0.1.147: same "grey, not near-black" request -- hint_bg lifted
        # from (17,13,9) to (32,25,18). hint_text scaled up ~5% (same
        # hue) to restore 4.5:1+ against the brighter hint_bg -- lands
        # at 4.52:1.
        "hint_bg": (32, 25, 18), "hint_text": (169, 120, 71),
        "accent": (201, 120, 46), "menu_sel_bg": (48, 36, 24), "warning": (200, 100, 70),
    },
    {
        # Near-zero blue channel -- the most aggressive option, meant
        # for right before sleep.
        "name": "Red Shift",
        # v26.07.10.10: bg lightened, same reasoning/session as Default
        # theme above -- see its comment. 1.50:1 against pure black.
        # Specifically called out by Kaleb during this session as the
        # theme to double-check ("if they were in red shift it will
        # render properly") -- confirmed via direct pixel readback.
        "bg": (62, 37, 37), "panel": (24, 12, 12), "text": (176, 90, 74),
        "dim": (120, 60, 50), "link": (196, 90, 70), "link_sel": (214, 120, 90),
        # v0.1.130: see Default theme's comment. This theme's exact "dim"
        # tone only measured 2.39:1 against the new hint_bg -- the worst
        # of the 5 themes, since Red Shift's near-zero blue/green channels
        # weigh very low in perceived luminance -- so hint_text needed a
        # larger brightness scale (~56% up, still the same red hue, not a
        # different color) to reach 4.63:1.
        # v0.1.147: same "grey, not near-black" request -- hint_bg lifted
        # from (13,5,5) to (30,18,18). hint_text scaled up ~5% (same
        # hue) to restore 4.5:1+ against the brighter hint_bg -- lands
        # at 4.57:1.
        "hint_bg": (30, 18, 18), "hint_text": (196, 99, 82),
        "accent": (140, 58, 46), "menu_sel_bg": (40, 18, 18), "warning": (200, 80, 60),
    },
    {
        # Kaleb's requested palette: dark background kept (his explicit
        # ask), accent colors drawn from fan-made BMO/Adventure Time
        # palette references (Lospec "Beemo", ColorsWall "bmo design") --
        # no official studio palette exists, so treat as close
        # approximations, not exact brand colors.
        "name": "Adventure",
        # v26.07.10.10: bg lightened, same reasoning/session as Default
        # theme above -- see its comment. 1.49:1 against pure black.
        "bg": (43, 43, 50), "panel": (26, 26, 30), "text": (180, 200, 190),
        "dim": (140, 145, 142), "link": (68, 176, 151), "link_sel": (255, 236, 71),
        # v0.1.130: see Default theme's comment.
        # v0.1.147: same "grey, not near-black" request as the other 4
        # themes -- hint_bg lifted from (11,11,13) to (28,28,32).
        # hint_text unchanged -- this theme had contrast headroom to
        # spare (was 6.14:1), still comfortably above 4.5:1 at 5.30:1.
        "hint_bg": (28, 28, 32), "hint_text": (140, 145, 142),
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

    @property
    def splash_title(self):
        """v26.07.10.07: boot splash's "PICO READER" title, 50% bigger
        than ui_heading (Kaleb's request -- title only, not the face or
        subtitle above/below it). Built the same way heading/ui_heading
        already are (a plain _get() call off SIZE_STEPS[size_index]),
        not a fixed pixel value, so it still scales with the Font Size
        setting like every other UI font in this app -- confirmed via
        this session's test sweep that it fits SW at every step."""
        return self._get(int((self.SIZE_STEPS[self.size_index] + 6) * 1.5))

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
    if os.path.isdir(WRAP_CACHE_DIR):
        for fname in os.listdir(WRAP_CACHE_DIR):
            if fname.startswith(prefix):
                path = os.path.join(WRAP_CACHE_DIR, fname)
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
    MAX_INMEMORY_IMAGES = 32  # v26.07.09.13: raised from 24 -- Kaleb wanted
                               # more headroom for fewer CPU-costly re-
                               # decodes when scrolling back through
                               # recently-viewed images (real concern given
                               # Disk Cache is OFF by default, so a cache
                               # miss means a full re-decode, not a cheap
                               # disk re-read). Worst case (every slot a
                               # native ~11MB decode) is ~352MB -- stacked
                               # with the separate GPU texture cache's own
                               # ~178MB worst case (MAX_IMAGE_TEXTURES=12),
                               # that's ~530MB before the rest of the app/
                               # OS. Considered 50 (~550MB alone, ~728MB+
                               # stacked) but that starts crowding the 1GB
                               # budget in a genuinely bad case; 32 is a
                               # real increase over the previous 24 without
                               # reaching that territory. Real average use
                               # is far below either worst case -- most
                               # entries are ordinary inline images
                               # (~250-400KB), not native maximize-mode
                               # decodes.

    # Target size used to PICK a decode resolution. Through v0.1.79 this
    # was deliberately smaller than the real on-screen image box
    # specifically to keep mini_jpeg.py's pure-Python decode fast --
    # images were decoded at well under their display size and upscaled,
    # trading visible sharpness for speed. That tradeoff no longer makes
    # sense: native_jpeg.py (real libSDL2_image, ~143x faster per the
    # v0.1.80 benchmark) decodes the full JPEG regardless of this
    # constant -- only the final SDL_BlitScaled downscale step depends on
    # it, and that's cheap at any size.
    #
    # v0.1.81: exact 16:9 at the device's full native width (720x405,
    # 720*9/16=405) -- deliberately a bit WIDER than the real on-screen
    # box (SW-40=680), so images render with a small lossless-ish
    # downscale at draw time instead of an upscale. Verified real impact
    # against mwb_E_202507.epub's actual images (not estimated): most
    # 1200x675 photos move from scale_n 4->5 (592KB->925KB decoded
    # each); worst case at MAX_INMEMORY_IMAGES=80 goes from ~44MB to
    # ~67MB -- comfortably inside the 1GB budget. mini_jpeg.py's
    # fallback path honors the same constant via the same
    # _pick_scale_n() call, so quality improves on that path too, just
    # slower per-image as always.
    TARGET_BOX_W = 720
    TARGET_BOX_H = 405

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

    def request(self, key, jpeg_bytes, priority=PRIORITY_VISIBLE, force_scale_n=None):
        """v26.07.09.07: force_scale_n lets a caller bypass _pick_scale_n()'s
        target-box-based choice and demand a specific decode scale
        instead -- used by Image Maximize Mode to request scale_n=8
        (true native resolution) regardless of what the shared inline
        target box would otherwise pick. None (default) preserves every
        existing caller's behavior unchanged."""
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
                    self._queue.put((priority, next(self._seq_counter), key, jpeg_bytes, force_scale_n))
                return
            self._results[key] = {"thumb": "loading", "full": None, "priority": priority,
                                   "requested_at": time.time()}
            self._pending_counts[priority] += 1
        self._queue.put((priority, next(self._seq_counter), key, jpeg_bytes, force_scale_n))

    # v0.1.66 -- Small sleep inserted between PRERENDER decodes only.
    # Doesn't slow down real reading (VISIBLE/PREFETCH are never delayed),
    # but caps sustained CPU/heat during a long whole-book background
    # pre-render pass. 30ms is small enough that pre-render of a full
    # book still finishes in a reasonable time, but large enough to give
    # the render loop and any newly-arriving reading request a real gap.
    PRERENDER_THROTTLE_SECONDS = 0.03

    def _worker_loop(self):
        while True:
            priority, _seq, key, jpeg_bytes, force_scale_n = self._queue.get()
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
                    self._queue.put((priority, next(self._seq_counter), key, jpeg_bytes, force_scale_n))
                    self._queue.task_done()
                    time.sleep(0.01)  # brief yield, avoid a busy spin
                    continue

            try:
                self._process(key, jpeg_bytes, priority, force_scale_n=force_scale_n)
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

    def _process(self, key, jpeg_bytes, priority, force_scale_n=None):
        """v26.07.09.07: force_scale_n bypasses _pick_scale_n() below --
        used for Image Maximize Mode's native-resolution requests. Both
        is_relevant() checks in this method are ALSO skipped when
        force_scale_n is set: is_relevant is keyed against
        App._visible_image_keys, which only ever tracks the CURRENT
        page's INLINE image keys -- a native-suffixed key
        (App._img_key(src) + _IMGVIEW_NATIVE_KEY_SUFFIX) can never appear
        in that set, so without this bypass every native request would
        look "irrelevant" and get silently dropped or refused its
        full-res upgrade the instant it was requested. A native request
        is inherently "the one image the user is looking at right now"
        -- there's no equivalent of "scrolled past it already" the way
        there is for inline images arriving off-screen."""
        with self._lock:
            entry = self._results.get(key)
            if entry is not None and isinstance(entry.get("full"), tuple):
                return  # already fully resolved by an earlier queue entry for this key

        if force_scale_n is None and priority == self.PRIORITY_VISIBLE \
                and self.is_relevant is not None and not self.is_relevant(key):
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
        full_n = force_scale_n if force_scale_n is not None else (
            self._pick_scale_n(*peeked) if peeked else self.FULL_N)

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
        if force_scale_n is None and priority == self.PRIORITY_VISIBLE \
                and self.is_relevant is not None and not self.is_relevant(key):
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


def _row_h(font, pad=14):
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
    breathing room instead, comfortably more than CORNER_RADIUS.
    v0.1.153: default dropped 20->14 (Kaleb: "feel natural yet minimal"
    after the DejaVu Sans Condensed switch). DejaVu's own TTF_FontHeight
    already runs taller than Liberation Sans/Inter's did at the same pt
    (confirmed via pixel readback across all 7 Font Sizes), so the old
    flat +20 -- originally sized to ADD ~8px of breathing room on top of
    a tighter font's metrics -- was now compounding on top of DejaVu's
    already-larger box, landing at ~23-27px of dead space per row
    (46-62% of row_h) instead of the intended ~8px. 14 restores that
    same ~8-10px clearance per side against DejaVu's real metrics,
    confirmed via the same pixel-readback method, no clipping at any
    size. Affects every screen that calls _row_h() with its default pad
    (Library, Bookmarks, Menu popup, Storage's action list, all 3
    Download list screens) -- TOC and Storage's info-line block pass
    their own explicit pad and are unaffected by this default change."""
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

SCREEN_FRAME_RADIUS = _sx(28)  # v0.1.131: the BMO-style OUTER screen frame,
                         # deliberately much larger/more pronounced than
                         # CORNER_RADIUS -- Kaleb wants the whole physical
                         # 720x720 canvas to read as one curved-corner
                         # "device face" (like BMO's screen), separate from
                         # and on top of the smaller per-panel rounding
                         # everywhere else. Always solid black regardless
                         # of theme (Kaleb: "to match whatever future
                         # screen use bars on screens that are wider" --
                         # i.e. this frame is meant to blend with future
                         # letterbox bars on non-square muOS devices, not
                         # with the current theme's background). v0.1.135
                         # briefly added a FRAME_EDGE_COLOR stroke along
                         # the curve boundary for bottom-corner contrast
                         # against dark content; removed entirely in
                         # v0.1.139 (Kaleb: it read as a confusing extra
                         # mark rather than a fix) -- see
                         # _draw_screen_frame()'s docstring.

IMG_MAXIMIZE_CORNER_RADIUS = _sx(20)  # v0.1.136: Kaleb sent a photo with
                         # red annotations showing exactly what he wants
                         # -- the MAXIMIZED IMAGE's own bottom-left/right
                         # corners rounded off where the image meets the
                         # hint bar below it, not the hint bar's corners
                         # (that's the separate, existing, much smaller
                         # CORNER_RADIUS treatment every hint bar already
                         # has). Deliberately its own size: bigger than
                         # the subtle per-panel CORNER_RADIUS (6px, would
                         # be too small to read clearly per Kaleb's
                         # annotation) but smaller than the bold outer
                         # SCREEN_FRAME_RADIUS (28px, that's the physical
                         # screen edge, a different visual element
                         # entirely) -- this is a third, distinct size
                         # for a third, distinct junction.


def _frame_corner_inset_at_row(radius, row):
    """Same per-row quarter-circle boundary math as _draw_screen_frame()
    itself, pulled out standalone so it can be used to CALCULATE a safe
    margin (below) instead of only to draw."""
    dy = radius - row
    dx = int(math.sqrt(max(0, radius * radius - dy * dy)))
    return radius - dx


def _min_safe_gap_from_corner(radius, x_offset, buffer_px):
    """v0.1.133: how close (in px) can a left-aligned text block's BOTTOM
    edge get to the screen's bottom edge, at horizontal offset x_offset,
    before SCREEN_FRAME_RADIUS's corner mask starts cutting into it?
    Walks the same per-row inset the frame itself paints and returns the
    smallest gap-to-edge where inset + buffer_px <= x_offset -- i.e. the
    frame's cut, plus a safety cushion for font hinting/antialiasing
    variance, still clears the text's left edge. Computed once at import
    (radius/offset are both fixed constants), not per-frame."""
    for gap in range(1, radius + 2):
        row = gap - 1
        inset = _frame_corner_inset_at_row(radius, row) if row < radius else 0
        if inset + buffer_px <= x_offset:
            return gap
    return radius + 1  # pathological fallback, never expected to hit


HINT_CORNER_RADIUS = SCREEN_FRAME_RADIUS  # v0.1.137: Kaleb's request --
                        # the hint bar's top-left/right corners were
                        # using the small per-panel CORNER_RADIUS (6px),
                        # visible but subtle (confirmed working at every
                        # Font Size via his own photos at 16pt and 32pt).
                        # He wants it "close to the overall screen
                        # corners" -- i.e. matching SCREEN_FRAME_RADIUS's
                        # visual weight, not a separate smaller size.
                        # Actual applied radius is still clamped to
                        # bar_h//2 at draw time (same clamp
                        # fill_rect_rounded already uses everywhere) --
                        # at the two smallest Font Size steps the hint
                        # bar itself isn't tall enough for the full 28px,
                        # so it naturally scales down there rather than
                        # producing a degenerate/overlapping shape.
                        # v0.1.139: also now used by _draw_status_bar()
                        # (the toast bar) -- see HINT_SIDE_PAD below,
                        # which is likewise shared by both bars now.

HINT_SIDE_PAD = HINT_CORNER_RADIUS + _sx(4)  # v0.1.137: hint bar's text
                        # left/right padding, sized to always clear the
                        # bigger HINT_CORNER_RADIUS above (Kaleb: "at
                        # smaller fonts it may need to pad the text left
                        # and right"). Deliberately a FIXED value (not
                        # computed per-call from the actual clamped
                        # radius, which would vary by Font Size) so the
                        # 3 places that need to agree on the hint bar's
                        # usable text width (_hint_pt()'s calibration
                        # search, _hint_lines_needed(), and draw_hint()
                        # itself) can't drift out of sync with each
                        # other -- using the WORST-CASE (largest)
                        # padding everywhere is conservative (wastes a
                        # little width at the two smallest Font Sizes,
                        # where the actual clamped radius is smaller than
                        # this) but guarantees text can never sit under
                        # the curve at ANY Font Size.

WRAP_SAFETY_MARGIN = _sx(16)  # v0.1.134: _wrap()'s greedy line-packer
                        # decides whether a word fits by SUMMING each
                        # word's individually-measured width + a fixed
                        # space width -- but SDL_ttf's real glyph
                        # spacing/hinting for the final joined line (one
                        # single text_width() call, which is how
                        # draw_reader() actually renders it) can measure
                        # slightly WIDER than that sum, especially on
                        # lines with many short space-separated tokens
                        # (confirmed via headless regression sweep: up to
                        # 9px drift on a 26-word numeric list at the
                        # smallest Font Size). This margin is subtracted
                        # from the packing decision's budget only (not
                        # from actual rendering/centering elsewhere), so
                        # a line the packer judges as "fitting" always has
                        # a little headroom against that measurement
                        # drift. Only affects the wrap DECISION for
                        # normal multi-word lines; _force_break_word()'s
                        # single-word chunks don't have this drift (no
                        # summing involved) and aren't affected.

HINT_BOTTOM_SAFE_GAP = _min_safe_gap_from_corner(
    SCREEN_FRAME_RADIUS, HINT_SIDE_PAD, buffer_px=_sx(6))
# v0.1.133 BUG FOUND (Kaleb asked to bug-check the frame against hint bar
# text): simulated every real hint string in the app against the actual
# corner-mask math at every Font Size (headless SDL2_ttf, real bundled
# font, real wrap/centering functions -- not guessed). At max Font Size,
# the Library screen's hint ("A Open  Y Sort  X Pin  ...  B Quit") is
# long enough to wrap to the full HINT_H_MAX_LINES=3 ceiling, filling the
# reserved bar height tightly enough that the last line's bottom sat only
# ~2px above the screen edge -- squarely inside SCREEN_FRAME_RADIUS's
# corner cut (~21px inset at that row vs. the text's 14px left offset,
# an actual -7px overlap, confirmed by simulation, not a near-miss).
# Every OTHER hint string in the app had 13-42px of margin at every Font
# Size -- this was specific to the one hint long enough to hit the
# 3-line ceiling. Fix: draw_hint() now clamps its vertical centering so
# the text block's bottom edge never sits closer than
# HINT_BOTTOM_SAFE_GAP to the screen edge, even if that means giving up
# perfect centering in this one tight case (safety over cosmetics) --
# see draw_hint().
# v0.1.137: reference x_offset changed from the old flat HINT_TEXT_X
# (14px) to HINT_SIDE_PAD (now ~32px, since draw_hint() draws its text
# there instead -- see HINT_SIDE_PAD above). A bigger x_offset can only
# make this margin MORE conservative (the frame's corner cut shrinks the
# further a column sits from the actual corner), so this naturally
# stayed safe through that change -- re-verified via the full regression
# sweep after implementing, not just by this reasoning alone.


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


def draw_rect_rounded_outline(renderer, x, y, w, h, color, radius, thickness=None):
    """v0.1.132: OUTLINE version of fill_rect_rounded() -- draws a rounded
    rect's border only (used for the image selection/link highlight),
    not a filled panel. fill_rect_rounded()'s per-row quarter-circle
    mask fills solid from the curve inward to the rect's edge, which is
    correct for a filled background but would paint a solid triangle at
    each corner here instead of a thin ring. This paints only a
    `thickness`-wide band that hugs the same per-row curve boundary
    (inset), so it stays visually consistent with every other rounded
    element in the app while remaining a true outline.
    IMPORTANT (image border specifically): the caller is responsible for
    keeping `radius` small enough to fit inside whatever real margin
    exists between this border and the image/content it surrounds (e.g.
    capped at min(pad_x, pad_y) for the reader's image selection box) --
    that's what guarantees the curve only ever cuts into empty margin
    and never reveals a squared-off corner of the thing being
    highlighted. This function itself does no clamping against that
    margin since it has no knowledge of it; only against w//2, h//2."""
    if thickness is None:
        thickness = max(1, _sx(2))
    radius = max(0, min(radius, w // 2, h // 2))
    SDL.SDL_SetRenderDrawColor(renderer, color.r, color.g, color.b, color.a)
    if radius == 0:
        top = Rect(x, y, w, thickness)
        SDL.SDL_RenderFillRect(renderer, ctypes.byref(top))
        bottom = Rect(x, y + h - thickness, w, thickness)
        SDL.SDL_RenderFillRect(renderer, ctypes.byref(bottom))
        left = Rect(x, y, thickness, h)
        SDL.SDL_RenderFillRect(renderer, ctypes.byref(left))
        right = Rect(x + w - thickness, y, thickness, h)
        SDL.SDL_RenderFillRect(renderer, ctypes.byref(right))
        return
    # straight edges, inset by radius, same as fill_rect_rounded's layout
    top = Rect(x + radius, y, w - 2 * radius, thickness)
    SDL.SDL_RenderFillRect(renderer, ctypes.byref(top))
    bottom = Rect(x + radius, y + h - thickness, w - 2 * radius, thickness)
    SDL.SDL_RenderFillRect(renderer, ctypes.byref(bottom))
    left = Rect(x, y + radius, thickness, h - 2 * radius)
    SDL.SDL_RenderFillRect(renderer, ctypes.byref(left))
    right = Rect(x + w - thickness, y + radius, thickness, h - 2 * radius)
    SDL.SDL_RenderFillRect(renderer, ctypes.byref(right))
    # 4 corners: same per-row quarter-circle boundary as fill_rect_rounded,
    # but each row only paints a `thickness`-wide strip starting AT the
    # curve (not filled all the way to the rect edge) -- a thin ring
    # instead of a solid corner triangle.
    for row in range(radius):
        dy = radius - row
        dx = int(math.sqrt(max(0, radius * radius - dy * dy)))
        inset = radius - dx
        if inset >= radius:
            continue
        rw = min(thickness, radius - inset)
        tl = Rect(x + inset, y + row, rw, 1)
        SDL.SDL_RenderFillRect(renderer, ctypes.byref(tl))
        tr = Rect(x + w - inset - rw, y + row, rw, 1)
        SDL.SDL_RenderFillRect(renderer, ctypes.byref(tr))
        bl = Rect(x + inset, y + h - 1 - row, rw, 1)
        SDL.SDL_RenderFillRect(renderer, ctypes.byref(bl))
        br = Rect(x + w - inset - rw, y + h - 1 - row, rw, 1)
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
            os.path.join(WRAP_CACHE_DIR, f"{stale_id}__*"),
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
        finished = load_finished()
        if fname in finished:
            finished.discard(fname)
            save_finished(finished)

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


FINISHED_PATH = os.path.join(DATA_DIR, "finished.json")


def load_finished():
    if os.path.exists(FINISHED_PATH):
        try:
            with open(FINISHED_PATH) as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()


def save_finished(finished_set):
    try:
        with open(FINISHED_PATH, "w") as f:
            json.dump(sorted(finished_set), f)
    except Exception:
        pass


LIBRARY_FILTER_MODES = ["all", "unfinished", "finished"]
LIBRARY_FILTER_LABELS = {"all": "All", "unfinished": "Unfinished", "finished": "Finished"}

LIBRARY_SORT_MODES = ["title", "author", "last_read", "recent"]
LIBRARY_SORT_LABELS = {
    "title": "Title A-Z", "author": "Author A-Z",
    "last_read": "Last Read", "recent": "Recently Added",
}


def _book_last_read_ts(book):
    last = get_last_position(book["path"])
    return last.get("ts", 0) if last else 0


def _relative_time(ts):
    """v0.1.122: "2d ago"-style relative timestamp for the Library list
    when sorted by Last Read (Kaleb's request). Deliberately coarse/
    short (fits a crowded row alongside title + pin/finished markers +
    progress %) rather than a precise duration. Returns None for ts=0
    (never read) so callers can skip it entirely rather than showing a
    meaningless "just now"."""
    if not ts:
        return None
    delta = time.time() - ts
    if delta < 0:
        delta = 0  # clock skew guard -- never show a negative age
    if delta < 60:
        return "just now"
    if delta < 3600:
        return f"{int(delta // 60)}m ago"
    if delta < 86400:
        return f"{int(delta // 3600)}h ago"
    if delta < 86400 * 7:
        return f"{int(delta // 86400)}d ago"
    if delta < 86400 * 30:
        return f"{int(delta // (86400 * 7))}w ago"
    if delta < 86400 * 365:
        return f"{int(delta // (86400 * 30))}mo ago"
    return f"{int(delta // (86400 * 365))}y ago"


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
SCREEN_SPLASH = "splash"  # v26.07.10.05: boot splash, shown before whatever
                    # App.__init__ would otherwise land on (Library, or
                    # Reader if Open Last Book on Launch resolved one) --
                    # see App.__init__'s tail and draw_splash().
SCREEN_MENU = "menu"
SCREEN_TOC = "toc"
SCREEN_BOOKMARKS = "bookmarks"
SCREEN_STORAGE = "storage"
SCREEN_DOWNLOAD_SOURCES = "download_sources"  # pick a plugin (only shown
                                               # if more than one is loaded)
SCREEN_DOWNLOAD_CATEGORIES = "download_categories"  # pick a category, for
                                               # plugins with SUPPORTS_CATEGORIES
SCREEN_DOWNLOAD_VIDEO_SOURCES = "download_video_sources"  # v0.1.110: pick
                                               # WHICH video source, reached
                                               # from the category picker's
                                               # "Videos" entry (jw_fetch's
                                               # CATEGORY_VIDEOS) -- replaces
                                               # the four separate Library
                                               # Menu video entries
SCREEN_DOWNLOAD_AUDIO_SOURCES = "download_audio_sources"  # v26.07.10.01:
                                               # same idea as
                                               # SCREEN_DOWNLOAD_VIDEO_SOURCES,
                                               # reached from CATEGORY_AUDIO
SCREEN_DOWNLOAD_AUDIO_BOOKS = "download_audio_books"  # v26.07.10.01: the
                                               # Bible-book sub-picker for
                                               # AUDIO_SOURCES entries
                                               # marked "books": True --
                                               # unlike every video source,
                                               # NWT audio needs a booknum
                                               # before it can list anything
SCREEN_DOWNLOAD_BROWSE = "download_browse"    # browse/download from the
                                               # selected plugin
SCREEN_DOWNLOAD_HELP = "download_help"  # v0.1.155: static help overlay
                        # explaining Search vs. manual pub-code entry --
                        # Kaleb: "this code thing is confusing". Opened
                        # with X from Sources/Categories/Browse, returns
                        # to whichever of those opened it.
SCREEN_LIBRARY_MENU = "library_menu"          # START on Library -- sort
                                               # shortcuts + Download +
                                               # Storage (v0.1.29)
SCREEN_IMAGE_VIEW = "image_view"              # v0.1.124: fullscreen image
                                               # maximize mode -- A on a
                                               # selected reader image.
                                               # Reader's self.state/
                                               # self.scroll/self.selected_span
                                               # are untouched while here;
                                               # B returns to the exact
                                               # same reading position.
SCREEN_TEXT_ENTRY = "text_entry"              # generic D-pad letter-grid
                                               # text input (v0.1.30) --
                                               # not tied to any one
                                               # feature; anything needing
                                               # typed input can reuse it

# v26.07.09.09: VIDEO_SOURCE_ITEMS and VIDEO_SOURCE_BY_LABEL are now
# built FROM jw_fetch.py's own VIDEO_SOURCES registry (see that file's
# docstring) instead of hardcoding JW titles/pub codes here -- this is
# the whole point of the registry: adding/removing a JW video source in
# the future is a jw_fetch.py-only change, zero main.py touch needed.
# Falls back to the OLD hardcoded 4-item list (+ conditional Search
# Videos) if the loaded jw_fetch.py predates VIDEO_SOURCES -- same
# defensive gating philosophy as JW_VIDEO_SUPPORTED above, so an older
# jw_fetch.py build still works exactly as it did before this change.
if JW_PLUGIN and hasattr(JW_PLUGIN, "VIDEO_SOURCES"):
    VIDEO_SOURCE_BY_LABEL = {src["label"]: src for src in JW_PLUGIN.VIDEO_SOURCES}
else:
    # Fallback registry, used only if the loaded jw_fetch.py predates
    # VIDEO_SOURCES -- kept so an older jw_fetch.py paired with this
    # main.py still actually works, not just avoids crashing. In normal
    # use this whole branch is dead code: the jw_fetch.py shipped
    # alongside this main.py always has VIDEO_SOURCES.
    VIDEO_SOURCE_BY_LABEL = {
        "Enjoy Life Forever": {"loader": "list_video_items", "args": {"pub": "lffv"}},
        "JW Broadcasting": {"loader": "list_broadcast_items", "args": {}},
        "Governing Body Updates": {"loader": "check_new_gb_updates", "args": {}},
        "The Good News According to Jesus": {"loader": "list_good_news_items", "args": {}},
    }
    if JW_PLUGIN and hasattr(JW_PLUGIN, "search_jw"):
        VIDEO_SOURCE_BY_LABEL["Search Videos"] = {"search": True}

if JW_PLUGIN and hasattr(JW_PLUGIN, "VIDEO_SOURCES"):
    VIDEO_SOURCE_ITEMS = [src["label"] for src in JW_PLUGIN.VIDEO_SOURCES]
else:
    VIDEO_SOURCE_ITEMS = list(VIDEO_SOURCE_BY_LABEL.keys())
VIDEO_SOURCE_ITEMS.append("Back")

# v26.07.10.01: AUDIO_SOURCE_BY_LABEL/AUDIO_SOURCE_ITEMS -- same registry-
# driven pattern as VIDEO_SOURCE_BY_LABEL above, built from jw_fetch's
# AUDIO_SOURCES. No hardcoded-fallback branch here (unlike VIDEO_SOURCE_
# BY_LABEL's old-jw_fetch.py compatibility path) -- AUDIO_SOURCES is new
# in this same jw_fetch.py version, there's no older build to stay
# compatible with.
if JW_PLUGIN and hasattr(JW_PLUGIN, "AUDIO_SOURCES"):
    AUDIO_SOURCE_BY_LABEL = {src["label"]: src for src in JW_PLUGIN.AUDIO_SOURCES}
    AUDIO_SOURCE_ITEMS = [src["label"] for src in JW_PLUGIN.AUDIO_SOURCES]
else:
    AUDIO_SOURCE_BY_LABEL = {}
    AUDIO_SOURCE_ITEMS = []
AUDIO_SOURCE_ITEMS.append("Back")

# v26.07.09.02: added "Pin/Unpin Selected" and "Mark Finished/Unfinished"
# -- moved off the Library screen's persistent hint bar (X and SELECT
# respectively) to declutter it down to the 4-5 highest-frequency
# actions. The X/SELECT button mappings themselves are UNCHANGED and
# still work exactly as before -- this just gives the same actions a
# second, discoverable path via the menu, matching Delete Book's
# existing "acts on whichever book was highlighted at START" pattern.
LIBRARY_MENU_ITEMS = ["Continue Reading", "Pin/Unpin Selected", "Mark Finished/Unfinished",
                       "Sort: Title A-Z", "Sort: Author A-Z", "Sort: Last Read",
                       "Sort: Recently Added", "Filter: Cycle", "Clear All Finished", "Theme +", "Theme -",
                       "Download Books", "Settings", "Delete Book", "Back"]

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
              "Theme +", "Theme -", "Immersive Mode", "Library", "Settings", "Resume"]

STORAGE_ACTIONS = ["Clear Image Cache", "Clean Up Orphaned Bookmarks",
                    "Backup Bookmarks Now", "Restore Latest Backup",
                    "Toggle Disk Cache (RAM-only mode)", "Toggle Images (text-only mode)",
                    "Toggle Open Last Book on Launch",
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
        self.finished = load_finished()
        self.lib_sort_mode = "title"
        self.lib_filter_mode = "all"  # v0.1.117: All/Unfinished/Finished,
                                       # resets each launch same as sort mode
        self._all_books = []  # unfiltered disk scan; self.books is the
                               # filtered+sorted view derived from this
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

        # v0.1.124: Image Maximize Mode. Deliberately NOT part of the
        # scroll/state/selected_span bookkeeping above -- entering/leaving
        # this screen never touches those, so returning to the reader is
        # always exactly where you left it (see SCREEN_IMAGE_VIEW comment).
        self._imgview_span = None       # ImageSpan currently maximized
        self._imgview_pending_reset = False  # True right after entry, until
                                              # the texture's real dims are
                                              # known and zoom/pan are set
        self._imgview_native_w = 0      # dims the current zoom/pan bounds
        self._imgview_native_h = 0      # were computed against
        self._imgview_zoom = 1.0
        self._imgview_zoom_min = 1.0    # cropped-to-fill scale
        self._imgview_zoom_max = 1.0    # native-resolution scale (>= min)
        self._imgview_pan_x = 0.0       # top-left of the visible crop,
        self._imgview_pan_y = 0.0       # in native image pixels

        self.menu_index = 0
        self.toc_flat = []
        self.toc_index = 0
        self.bookmarks_index = 0
        self._bookmark_delete_confirm_idx = None  # armed-for-delete row, or None
        # v0.1.117: book delete moved from a direct SELECT press on the
        # Library screen into the Library Menu (START), to free SELECT up
        # for the new Finished/Unfinished toggle. The target book is
        # captured when START is pressed (whichever row was highlighted),
        # and _menu_delete_armed is the same "press again to confirm"
        # pattern the old _lib_delete_confirm_idx used, just scoped to
        # the menu instead of the list.
        # v26.07.09.02: renamed from _menu_delete_target -- now shared by
        # Delete Book, Pin/Unpin Selected, and Mark Finished/Unfinished,
        # all of which act on whichever book was highlighted at the
        # moment START opened the Library Menu (there's no book list
        # inside the menu itself to re-select from).
        self._menu_target_book = None
        self._menu_delete_armed = False
        # v0.1.122: same two-press confirm pattern as _menu_delete_armed,
        # for the new bulk "Clear All Finished" action (Kaleb's request
        # #3) -- clearing potentially many books' Finished marks at once
        # gets the same accidental-press protection a single delete does.
        self._menu_clear_finished_armed = False
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
        self.dl_help_return_screen = SCREEN_DOWNLOAD_CATEGORIES  # v0.1.155:
                                      # which screen X-Help was opened from,
                                      # so B returns to the right place
                                      # instead of always the same screen.
        self.dl_help_scroll = 0      # v0.1.155: scroll offset on the help
                                      # overlay, in case it overflows the
                                      # screen at large Font Size.
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
        self._dl_video_all_items = []  # v0.1.110: unfiltered video catalog, see search_video_items()
        self.video_source_index = 0    # v0.1.110: selection on SCREEN_DOWNLOAD_VIDEO_SOURCES
        self.dl_is_video = False  # v0.1.90: True while SCREEN_DOWNLOAD_BROWSE is
                                   # showing a video catalog (jw_fetch videos)
                                   # rather than an EPUB catalog -- start_download()
                                   # and the B-back handler both branch on this
                                   # instead of duplicating the whole browse screen.
        # v26.07.10.01: audio-source state, mirroring the video fields just
        # above exactly -- dl_is_audio is start_download()/the B-back
        # handler's audio branch, audio_source_index is the selection on
        # SCREEN_DOWNLOAD_AUDIO_SOURCES, audio_book_index is the selection
        # on SCREEN_DOWNLOAD_AUDIO_BOOKS (the Bible-book sub-picker), and
        # _pending_audio_source remembers WHICH AUDIO_SOURCES entry opened
        # the book picker so choosing a book knows which loader/args to
        # call with booknum added in.
        self.audio_source_index = 0
        self.audio_book_index = 0
        self.dl_is_audio = False
        self._pending_audio_source = None

        self.status_msg = None   # brief on-screen feedback (bookmark saved/
        self.status_until = 0    # updated/limit-reached, delete confirmed, etc.
        self._link_video_downloading = False  # v0.1.98: guards against
                                   # double-triggering a video download if A
                                   # is mashed on the same in-text video link
                                   # while one is already resolving/downloading.

        self._visible_image_keys = set()  # images on the currently-built page
        # v0.1.82: default flipped True->False. The 500MB on-disk image
        # cache existed mainly to avoid re-paying mini_jpeg.py's slow
        # pure-Python decode across app restarts. With native_jpeg.py
        # confirmed instant on-device, that benefit is now negligible --
        # what's left is real cost: SD card write wear and 500MB of
        # storage for a cache that buys almost nothing. RAM-only
        # (MAX_INMEMORY_IMAGES=80, ~40-70MB depending on image mix) still
        # makes scrolling within a session instant either way. Existing
        # installs that already have a saved "disk_cache_enabled" value
        # keep whatever they had -- this only changes the default for
        # people who've never touched the toggle. Still user-togglable
        # from the Storage screen for anyone who prefers persistence
        # (e.g. still relying on the mini_jpeg fallback on a device
        # without libSDL2_image, where re-decode cost is real again).
        self.disk_cache_enabled = load_settings().get("disk_cache_enabled", False)
        self.images_enabled = load_settings().get("images_enabled", True)
        # v0.1.123: "Open Last Book on Launch" (Kaleb's request, built on
        # top of the existing Continue Reading feature) -- defaults OFF
        # since it changes what screen greets you on startup, unlike the
        # other Settings toggles which are all in-session behavior tweaks.
        self.open_last_book_enabled = load_settings().get("open_last_book_enabled", False)
        # v26.07.09.04: Immersive Mode -- hides the Reader screen's hint
        # bar (visuals only; the reserved bottom margin/body_rows are
        # UNCHANGED, so pagination math can't drift out of sync with what
        # v0.1.86 already fixed once). Persisted like the other reader
        # toggles above. X still opens the Menu even with the bar hidden
        # -- only the on-screen TEXT disappears, not the button mapping.
        self.immersive_mode = load_settings().get("immersive_mode", False)
        self.image_loader = ImageLoader(
            IMG_CACHE_DIR,
            is_relevant=lambda key: key in self._visible_image_keys,
            disk_cache_enabled=self.disk_cache_enabled,
            on_update=lambda: setattr(self, "dirty", True),
        )
        self._image_textures = OrderedDict()   # key -> (texture, w, h, is_full_res)
        self._image_dims_cache = {}   # img_key -> (w,h) or (0,0)/None if
                                       # unreadable -- see App._image_dims()
        # v26.07.09.07: lowered from 24 -- GPU-side texture memory is a
        # smaller, separate budget from the RAM decode cache above, and
        # each texture is uncompressed RGBA (4 bytes/pixel, bigger than
        # the 3-byte RGB24 decode buffer). A native 2400x1543 texture is
        # ~14.8MB; worst case at 12 if every slot held one: ~178MB.
        # Frees headroom for Image Maximize Mode's native-res textures
        # without the old 24-slot cap risking ~355MB worst case.
        self.MAX_IMAGE_TEXTURES = 12            # bounded LRU: caps GPU texture memory
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
        self._styles_starts = []
        self._styles_prefix_max_end = []
        self._para_spans = []
        self._chapter_nav_points = []
        self._nav_scan_book_id = None
        self._extreme_page_queue = []
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
        self._wrapped_cache = {}           # (href, size_index) -> (lines, line_span_map, line_style_runs, line_abs_starts) -- v0.1.114 added line_abs_starts
        self._wrapped_cache_order = []
        self._WRAPPED_CACHE_MAX = 200       # same bound as _page_text_cache; see v0.1.69 changelog for the combined RAM estimate
        self.dirty = True

        # v0.1.123: "Open Last Book on Launch" (Kaleb's request). Must be
        # the LAST thing __init__ does, not right after refresh_library()
        # -- open_book() reads/clears self._prerender_active,
        # self._page_text_cache(_order), and self._wrapped_cache, none of
        # which exist yet that early in __init__ (they're all set up
        # further down, same as self.doc/self.state themselves). Calling
        # it before that point would crash with AttributeError on first
        # launch with the toggle on. open_continue_reading() already
        # no-ops safely (just a status message, screen stays SCREEN_
        # LIBRARY) if nothing has ever been read, or if the last-read
        # book was since deleted/moved -- exactly the same fallback path
        # Kaleb confirmed he wants ("fall back to library always").
        if self.open_last_book_enabled:
            self.open_continue_reading()

        # v26.07.10.05: boot splash (Kaleb's request) -- by this point
        # self.screen already holds the REAL destination (Library, or
        # Reader if Open Last Book on Launch just resolved one two lines
        # up) -- save it and show the splash first, letting draw_splash()
        # hand off to it once the animation finishes. Deliberately the
        # very last thing __init__ does, same reasoning as Open Last
        # Book above: nothing here depends on anything defined later.
        self._splash_dest_screen = self.screen
        self.screen = SCREEN_SPLASH
        self._splash_start = time.time()

    # -------- library --------
    # v26.07.09.07: appended to _img_key()'s output to form a SEPARATE
    # cache key for Image Maximize Mode's native-resolution decode --
    # deliberately distinct from the plain inline-purpose key for the
    # same image, so the two never collide, shadow, or evict each other.
    # See the request()/_process() docstrings above for why sharing one
    # key would silently break both requesting native res at all AND
    # the is_relevant() relevance check.
    _IMGVIEW_NATIVE_KEY_SUFFIX = "__native"  # NOT "::native" -- this key
                                              # flows straight into the
                                              # on-disk cache filename
                                              # (_cache_path()), and
                                              # muOS SD cards are commonly
                                              # FAT32, which disallows ":"
                                              # in filenames. Underscore
                                              # is safe on every
                                              # filesystem this app runs
                                              # on.

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
        self._all_books = scan_library()  # may purge stale pin entries for deleted books on disk
        self.pinned = load_pinned()
        self.finished = load_finished()
        self._apply_library_view()

    def _apply_library_view(self):
        """Single place that turns _all_books into the displayed self.books
        -- applies the Filter (All/Unfinished/Finished) first, then the
        active Sort mode (which also handles pinned-float-to-top). Every
        action that can change filter membership, sort mode, or pin/
        finished status must go through this instead of re-sorting
        self.books directly, or a change made while a filter is active
        would silently sort/re-add books that shouldn't be visible."""
        if self.lib_filter_mode == "finished":
            filtered = [b for b in self._all_books if b["filename"] in self.finished]
        elif self.lib_filter_mode == "unfinished":
            filtered = [b for b in self._all_books if b["filename"] not in self.finished]
        else:
            filtered = self._all_books
        self.books = sort_library(filtered, self.lib_sort_mode, self.pinned)

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
        self.dl_is_video = False  # v0.1.90: this is the EPUB browse path
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

    def open_plugin_video_list(self, loader_name, **kwargs):
        """v26.07.09.09: generic replacement for the four near-identical
        open_video_downloader()/open_broadcast_downloader()/
        open_gb_update_downloader()/open_good_news_downloader() methods
        this used to be -- each did the exact same 15 lines of state
        setup and background-thread loading, differing only in WHICH
        JW_PLUGIN function they called. Now driven entirely by
        JW_PLUGIN.VIDEO_SOURCES (see jw_fetch.py's docstring for that
        registry's shape): main.py doesn't need to know the JW-specific
        function names or pub codes up front, it just calls whichever
        one the plugin declared, by name, via getattr().

        loader_name: name of a JW_PLUGIN function, e.g. "list_video_items"
        kwargs: passed straight through to that function, e.g. pub="lffv"

        Same dl_is_video=True reuse of SCREEN_DOWNLOAD_BROWSE as before --
        the browse screen and start_download()'s video branch don't know
        or care which specific loader populated the list."""
        self.dl_plugin = JW_PLUGIN
        self.dl_is_video = True
        self.dl_category = None
        self.dl_items = []
        self.dl_index = 0
        self.dl_page = 1
        self.dl_query = None
        self.dl_has_next = False
        self.dl_load_error = None
        self.dl_loading = True
        self.dl_loading_start = time.time()
        self.screen = SCREEN_DOWNLOAD_BROWSE

        def _do_load():
            try:
                loader = getattr(JW_PLUGIN, loader_name)
                items, err = loader(**kwargs)
            except Exception as e:
                items, err = [], str(e)
            if self.dl_is_video:  # guard: person didn't back out meanwhile
                self._dl_video_all_items = items
                self.dl_items = items
                self.dl_load_error = err
                self.dl_index = 0
                self.dl_loading = False
                self.dirty = True  # see _load_dl_page's class-wide note on this

        threading.Thread(target=_do_load, daemon=True).start()

    def open_plugin_audio_list(self, loader_name, **kwargs):
        """v26.07.10.01: audio equivalent of open_plugin_video_list() --
        same generic getattr(JW_PLUGIN, loader_name)(**kwargs) shape, same
        background-thread loading. Reuses SCREEN_DOWNLOAD_BROWSE via
        dl_is_audio=True instead of dl_is_video=True -- the browse screen
        and start_download() branch on dl_is_audio the same way they
        already branch on dl_is_video, just routing to find_music_dir()/
        download_audio() instead of find_movies_dir()/download_video()."""
        self.dl_plugin = JW_PLUGIN
        self.dl_is_audio = True
        self.dl_category = None
        self.dl_items = []
        self.dl_index = 0
        self.dl_page = 1
        self.dl_query = None
        self.dl_has_next = False
        self.dl_load_error = None
        self.dl_loading = True
        self.dl_loading_start = time.time()
        self.screen = SCREEN_DOWNLOAD_BROWSE

        def _do_load():
            try:
                loader = getattr(JW_PLUGIN, loader_name)
                items, err = loader(**kwargs)
            except Exception as e:
                items, err = [], str(e)
            if self.dl_is_audio:  # guard: person didn't back out meanwhile
                self.dl_items = items
                self.dl_load_error = err
                self.dl_index = 0
                self.dl_loading = False
                self.dirty = True

        threading.Thread(target=_do_load, daemon=True).start()

    def search_video_items(self, query):
        """v0.1.110: client-side title search for the video browse list.
        None of the four video sources (Enjoy Life Forever, JW
        Broadcasting, Governing Body Updates, The Good News According to
        Jesus) have a server-side search of their own -- each is fetched
        as one small complete list up front -- so this just filters the
        already-loaded self._dl_video_all_items by a case-insensitive
        substring match on title. Empty query restores the full list."""
        query = (query or "").strip()
        self.dl_query = query or None
        source = self._dl_video_all_items
        if not query:
            self.dl_items = source
        else:
            q = query.lower()
            self.dl_items = [it for it in source if q in it.get("title", "").lower()]
        self.dl_index = 0
        self.dirty = True

    def open_category(self, category):
        """Opens the browse screen scoped to one category (see
        jw_fetch.CATEGORIES) -- same loading pattern as open_downloader()."""
        self.dl_category = category
        self.dl_is_video = False  # v0.1.90: this is the EPUB browse path
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

        if self.dl_is_video:
            # v0.1.90: video path -- saves into muOS's native Media Player
            # content folder (ROMS/movies) instead of LIBRARY_DIR, and
            # does NOT call refresh_library() on success (it's not an
            # EPUB). Deliberately hands off to muOS's own native player
            # rather than launching mpv in-process -- see the v0.1.90
            # changelog entry for why (mpv can't read PicoReader's raw
            # SDL_Joystick input without bundling gptokeyb2, confirmed
            # via CTupe's real source; muOS's native Media Player already
            # gives correct controls for free via its own SETUP_APP).
            self.set_status(f'Downloading "{item["title"]}"...', duration=60)

            def _do_video_download():
                try:
                    video_item = item
                    if not video_item.get("_video_url") and video_item.get("_raw_lank"):
                        # v26.07.09.08: "Search Videos" results are lazily
                        # resolved -- search_jw() doesn't hit
                        # GETPUBMEDIALINKS for every result up front (one
                        # extra round-trip per result just to BROWSE would
                        # be wasteful); only resolve the one actually
                        # chosen, right here, right before downloading it.
                        resolved, rerr = JW_PLUGIN.resolve_search_video_item(video_item)
                        if not resolved:
                            raise RuntimeError(rerr or "Could not resolve video")
                        video_item = resolved
                    movies_dir = JW_PLUGIN.find_movies_dir()
                    ok, msg, _path = JW_PLUGIN.download_video(video_item, movies_dir)
                except Exception as e:
                    ok, msg = False, f"Download failed: {e}"
                self._dl_downloading_idx = None
                if ok:
                    msg = (f'"{item["title"]}" downloaded. Exit PicoReader and open '
                           f'ROM Collection -> Movies to watch it.')
                self.set_status(msg, duration=6.0)
                self.dirty = True

            threading.Thread(target=_do_video_download, daemon=True).start()
            return

        if self.dl_is_audio:
            # v26.07.10.01: audio path -- saves into muOS's native GMU
            # Music Player content folder (ROMS/Music), same shape as the
            # video branch just above (no refresh_library(), not an EPUB).
            # No lazy-resolve step needed (unlike Search Videos' _raw_lank
            # handling) -- every AUDIO_SOURCES loader already returns a
            # ready _audio_url per item, confirmed live this session.
            self.set_status(f'Downloading "{item["title"]}"...', duration=60)

            def _do_audio_download():
                try:
                    audio_item = item
                    if not audio_item.get("_audio_url") and audio_item.get("_raw_lank"):
                        # v26.07.10.02: "Search Audio" results are lazily
                        # resolved -- same reasoning as the video branch's
                        # identical check just above (one extra round-trip
                        # per result just to BROWSE would be wasteful;
                        # only resolve the one actually chosen).
                        resolved, rerr = JW_PLUGIN.resolve_search_audio_item(audio_item)
                        if not resolved:
                            raise RuntimeError(rerr or "Could not resolve audio")
                        audio_item = resolved
                    music_dir = JW_PLUGIN.find_music_dir()
                    ok, msg, _path = JW_PLUGIN.download_audio(audio_item, music_dir)
                except Exception as e:
                    ok, msg = False, f"Download failed: {e}"
                self._dl_downloading_idx = None
                if ok:
                    msg = (f'"{item["title"]}" downloaded. Exit PicoReader and open '
                           f'ROM Collection -> Music to listen to it.')
                self.set_status(msg, duration=6.0)
                self.dirty = True

            threading.Thread(target=_do_audio_download, daemon=True).start()
            return

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
        self._apply_library_view()
        self.lib_index = 0

    def cycle_filter_mode(self):
        idx = LIBRARY_FILTER_MODES.index(self.lib_filter_mode)
        self.lib_filter_mode = LIBRARY_FILTER_MODES[(idx + 1) % len(LIBRARY_FILTER_MODES)]
        self._apply_library_view()
        self.lib_index = 0

    def toggle_pin(self, book):
        fname = book["filename"]
        if fname in self.pinned:
            self.pinned.discard(fname)
        else:
            self.pinned.add(fname)
        save_pinned(self.pinned)
        selected_path = book["path"]
        self._apply_library_view()
        # keep the selection on the same book after the re-sort moves it
        for i, b in enumerate(self.books):
            if b["path"] == selected_path:
                self.lib_index = i
                break

    def toggle_finished(self, book):
        fname = book["filename"]
        was_finished = fname in self.finished
        if was_finished:
            self.finished.discard(fname)
        else:
            self.finished.add(fname)
        save_finished(self.finished)
        selected_path = book["path"]
        self._apply_library_view()
        # unlike toggle_pin, this can remove the book from view entirely
        # (e.g. marking a book Finished while the Unfinished filter is
        # active) -- fall back to clamping the index instead of leaving
        # lib_index stale/out of range if the book is no longer present.
        for i, b in enumerate(self.books):
            if b["path"] == selected_path:
                self.lib_index = i
                break
        else:
            self.lib_index = max(0, min(self.lib_index, len(self.books) - 1))
        self.set_status("Marked Finished" if not was_finished else "Marked Unfinished")

    def clear_all_finished(self):
        """v0.1.122: bulk-clear every Finished mark at once (Kaleb's
        request #3) -- e.g. resetting a season of workbooks instead of
        un-marking each one individually. Only clears the marks
        themselves, never touches any book file. Re-applies the library
        view afterward since this can empty out the Finished filter
        entirely (falls back to All automatically via _apply_library_view
        picking up the now-empty self.finished, same as any other
        finished-state change)."""
        count = len(self.finished)
        self.finished = set()
        save_finished(self.finished)
        self._apply_library_view()
        self.lib_index = max(0, min(self.lib_index, len(self.books) - 1))
        self.set_status(f"Cleared {count} Finished mark" + ("s" if count != 1 else ""))

    def most_recent_book(self):
        """The book with the most recent last-read timestamp across the
        full library (self._all_books, unaffected by the active Filter),
        or None if nothing has ever been read. Shared by
        open_continue_reading() and draw_library_menu()'s dynamic label
        so the two can never disagree about which book "Continue
        Reading" points at."""
        candidates = [(b, _book_last_read_ts(b)) for b in self._all_books]
        candidates = [(b, ts) for b, ts in candidates if ts > 0]
        if not candidates:
            return None
        return max(candidates, key=lambda pair: pair[1])[0]

    def open_continue_reading(self):
        """v0.1.122: 'Continue Reading' Library Menu shortcut (Kaleb's
        request) -- jumps straight into whichever book has the most
        recent last-read timestamp, restoring exact position via the
        same get_last_position() open_book() already uses for a normal
        tap. No-ops with a status message if nothing has ever been read."""
        book = self.most_recent_book()
        if book is None:
            self.set_status("No books read yet")
            return
        self.open_book(book)

    def open_book(self, book):
        if self._prerender_active:
            self.cancel_prerender()
        cache_key = book_id(book["path"])
        # v26.07.09.12: release the PREVIOUS book's cached images before
        # loading the new one -- until now nothing ever cleared this on a
        # book switch, so images (including Image Maximize Mode's ~11MB
        # native-res entries) from books you've already left could still
        # be sitting in RAM/GPU memory when a new, heavier book opens.
        # Confirmed via real measurement: ordinary reading alone (no
        # maximize) already accumulates 100+ cached entries and tens of
        # MB of RSS growth in a single session. Skipped when re-opening
        # the SAME book (e.g. "Continue Reading") -- no reason to throw
        # away images you're about to need again immediately.
        if self._book_id is not None and self._book_id != cache_key:
            self.image_loader._results.clear()
            for _key, entry in self._image_textures.items():
                SDL.SDL_DestroyTexture(entry[0])
            self._image_textures.clear()
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
        self._image_dims_cache.clear()       # v0.1.84: img_keys are book-
                                              # namespaced already, but no
                                              # reason to keep growing it
        # v26.07.09.12: fast path only, always synchronous -- L2/R2 has a
        # usable (if coarser, for daily-text-shaped books) answer from the
        # very first press. See _build_chapter_nav_points()'s docstring.
        self._chapter_nav_points = self._build_chapter_nav_points()
        self._nav_scan_book_id = self._book_id  # staleness guard for the
                                                  # background thread below
        if self._daily_nav_scan_gate():
            # v26.07.09.12: the expensive per-day upgrade scan, backgrounded
            # -- see _build_daily_nav_points_slow()'s docstring for why.
            # Runs off the main thread; swaps in the finer nav points when
            # done, guarded against the person having since closed this
            # book or opened a different one.
            scan_book_id = self._book_id

            def _do_daily_scan():
                try:
                    result = self._build_daily_nav_points_slow()
                except Exception as e:
                    _boot_log(f"background daily-nav scan failed: {e}\n")
                    return
                if result and self._nav_scan_book_id == scan_book_id:
                    self._chapter_nav_points = result
                    self.dirty = True
            threading.Thread(target=_do_daily_scan, daemon=True).start()

        # v26.07.09.21: background scan for pages over PRERENDER_THRESHOLD
        # -- see _prerender_extreme_pages_scan()'s docstring for why this
        # needs its own background thread (safe: pure XML parsing, no
        # SDL_ttf calls, unlike the wrap itself) and _extreme_page_queue's
        # comment for how draw_reader() processes whatever it finds.
        # Deliberately separate from _prerender_active/cancel_prerender()
        # above -- that's the existing, unrelated whole-book IMAGE
        # pre-render feature; this is scoped narrowly to extreme TEXT
        # pages only.
        self._extreme_page_queue = []
        scan_book_id = self._book_id

        def _do_extreme_page_scan():
            try:
                found = self._prerender_extreme_pages_scan()
            except Exception as e:
                _boot_log(f"background extreme-page scan failed: {e}\n")
                return
            if found and self._book_id == scan_book_id:
                self._extreme_page_queue = found
                self.dirty = True
        threading.Thread(target=_do_extreme_page_scan, daemon=True).start()

    def _build_chapter_nav_points(self):
        """Build an ordered list of (spine_index, file, anchor) representing
        real 'chapters' for L2/R2 navigation. Prefers structural chapterN
        anchors (e.g. Bible books: Exodus 1, Exodus 2, ...) so navigation
        lands on actual chapters rather than internal split/nav fragments.
        Falls back to TOC entries. v26.07.09.12: the further fallback (per-
        day weekday-prefixed entries for daily-text booklets whose TOC is
        much coarser than their real content) is NO LONGER attempted here
        -- that scan reads every spine file and was the confirmed cause of
        a real on-device freeze (see _daily_nav_scan_gate()/
        _build_daily_nav_points_slow()'s docstrings). This function now
        ONLY returns the fast path, always synchronously, so L2/R2 has
        something usable from the very first press. open_book() separately
        kicks off the slow per-day upgrade in a background thread and
        swaps it in when ready -- see open_book()'s daily-scan block."""
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

            # v0.1.77 fix: back matter AFTER the last chapterN point (e.g.
            # nwt_E.epub's "Appendix A"/"Appendix B", each its own real
            # multi-page section between Malachi and Matthew, or after
            # Revelation) had no nav points either -- only front matter
            # was ever prepended. Symptom Kaleb hit: R2 from Revelation 22
            # (or from anywhere inside an appendix opened via the TOC
            # popup) always landed on the same neighboring real chapter
            # instead of stepping through the appendix's own pages,
            # because bisect_right in _jump_chapter() only ever sees the
            # points list -- any spine index not in it is invisible to
            # L2/R2. Same fix shape as front_points: pull in TOC entries
            # for any spine index that falls in a gap between two
            # consecutive chapterN points (or after the very last one),
            # so appendices/back matter get real, steppable nav points
            # too, wherever in the spine they happen to sit.
            covered = {p[0] for p in points} | {p[0] for p in front_points}
            gap_points = []
            seen_idx = set()
            for entry in flat:
                f = entry.href.split("#")[0] if "#" in entry.href else entry.href
                anchor = entry.href.split("#", 1)[1] if "#" in entry.href else None
                idx = self.doc.spine_index(f)
                if (idx != -1 and idx not in covered and idx not in seen_idx
                        and idx > first_chapter_idx):
                    gap_points.append((idx, f, anchor))
                    seen_idx.add(idx)
            all_points = front_points + points + gap_points
            all_points.sort(key=lambda p: p[0])
            return all_points

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

        if toc_points:
            return toc_points

        # last resort: every spine file is its own "chapter"
        return [(i, f, None) for i, f in enumerate(self.doc.spine)]

    def _daily_nav_scan_gate(self):
        """True if this book's TOC looks coarse enough relative to its
        spine that the slow per-day upgrade scan (_build_daily_nav_points_
        slow()) is worth running at all -- same threshold the old inline
        check used (e.g. 17 months vs 741 spine files in a daily-text
        booklet). Cheap: no per-file reads, just counts."""
        spine_len = len(self.doc.spine) if self.doc else 0
        toc_len = len(flatten_toc(self.doc.toc)) if self.doc else 0
        return spine_len > 50 and toc_len < spine_len * 0.1

    def _build_daily_nav_points_slow(self):
        """v26.07.09.12: the expensive half of the old
        _build_chapter_nav_points() -- pulled out so it can run on a
        BACKGROUND thread instead of blocking open_book(). This is the
        exact scan v0.1.77 already optimized once (raw byte read + cheap
        regex instead of a full XML parse per file) after it caused a
        real on-device freeze on a 740-file daily-text epub -- confirmed
        via Kaleb's report that the v0.1.77 optimization alone still
        wasn't enough on the real ARM device (1GB RAM, no JIT): even the
        cheaper per-file cost, done synchronously 740+ times before the
        reader could process any input, was long enough to read as a full
        hang requiring a hard reboot. Rather than trying to shrink the
        per-file cost further, this version keeps the exact same cheap
        scan but moves it off the main thread entirely -- CPython's GIL
        means this doesn't run in true parallel with rendering, but it DOES
        get preempted roughly every 5ms (default sys.getswitchinterval()),
        so the render/input loop keeps getting slices throughout instead of
        being frozen solid for the scan's whole duration like before.
        Returns the same shape _build_chapter_nav_points() does (a nav
        points list) or None if the daily-weekday heuristic didn't find
        enough real matches (caller should keep using the fast-path
        result already in place)."""
        import re
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

        weekday_re = re.compile(
            r"(Sunday|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday),",
            re.IGNORECASE)
        tag_re = re.compile(r"<[^>]+>")
        daily_points = []
        for idx, fname in enumerate(self.doc.spine):
            try:
                raw = self.doc._read(fname)
            except Exception:
                continue
            snippet = tag_re.sub(" ", raw[:2000])
            if weekday_re.search(snippet[:200]):
                daily_points.append((idx, fname, None))
        MIN_DAILY_MATCHES = 20  # a real year's worth is ~300+; this just
                                 # rules out a stray coincidental match
        if len(daily_points) < MIN_DAILY_MATCHES:
            return None

        first_day_idx = daily_points[0][0]
        front_points = []
        seen_idx = set()
        for entry in flat:
            f = entry.href.split("#")[0] if "#" in entry.href else entry.href
            anchor = entry.href.split("#", 1)[1] if "#" in entry.href else None
            idx = self.doc.spine_index(f)
            if idx != -1 and idx < first_day_idx and idx not in seen_idx:
                front_points.append((idx, f, anchor))
                seen_idx.add(idx)
        front_points.sort(key=lambda p: p[0])
        return front_points + daily_points

    # -------- page layout --------
    class _WrapAbortRequested(Exception):
        """v26.07.10.03: raised from inside a live wrap's progress_cb
        when _poll_wrap_abort_button() catches B/L2/R2 mid-wrap.
        Carries the requested action ("back"/"prev_chapter"/
        "next_chapter") as args[0]. _wrap() itself has no try/except
        around its progress_cb call (confirmed by reading it), so this
        propagates straight out to the caller's try/except -- and
        _wrap() never mutates self during its loop (only reads
        self._styles via _word_width()), so an abort at any paragraph
        boundary leaves self untouched beyond what _ensure_page_built()
        already explicitly snapshots/restores."""
        pass

    def _poll_wrap_abort_button(self):
        """v26.07.10.03: called from the LIVE (non-prerender) wrap's
        progress_cb at each throttled checkpoint, to let B/L2/R2 break
        out of an in-progress synchronous wrap instead of only being
        acted on after it finishes -- Kaleb's request: back out of the
        book, or skip to the previous/next chapter, while a genuinely
        expensive page keeps rendering in the background via the
        existing extreme-page queue (see _handle_wrap_abort()).

        Drains every currently-queued SDL event looking for a
        JOYBUTTONDOWN matching B/L2/R2; anything else (including plain
        navigation presses that aren't an abort request) is discarded,
        not requeued -- same precedent as the main loop's existing
        STALE_INPUT_MS handling (v0.1.79), which already drops input
        queued during a stall rather than replaying it once things
        catch up. No keyboard equivalent for L2/R2 exists anywhere else
        in this app (see main()'s SDL_KEYDOWN_EV branch), so none is
        added here either -- this only ever fires from a real joystick
        on-device, or a synthetic JOYBUTTONDOWN in test harnesses.

        Self-contained (defines its own tiny ctypes struct rather than
        reaching into main()'s local SDL_JoyButtonEvent) so this can't
        be affected by, or accidentally affect, the main event loop's
        own event buffer."""
        class _JoyButtonEvent(ctypes.Structure):
            _fields_ = [("type", ctypes.c_uint32), ("timestamp", ctypes.c_uint32),
                        ("which", ctypes.c_int32), ("button", ctypes.c_ubyte),
                        ("state", ctypes.c_ubyte), ("padding1", ctypes.c_ubyte),
                        ("padding2", ctypes.c_ubyte)]
        ev = (ctypes.c_byte * 56)()
        action = None
        while SDL.SDL_PollEvent(ctypes.byref(ev)) != 0:
            etype = ctypes.cast(ev, ctypes.POINTER(ctypes.c_uint32))[0]
            if etype != SDL_JOYBUTTONDOWN_EV:
                continue
            bev = ctypes.cast(ev, ctypes.POINTER(_JoyButtonEvent))[0]
            b = bev.button
            if b == JOY_B:
                action = "back"
            elif b == JOY_L2:
                action = "prev_chapter"
            elif b == JOY_R2:
                action = "next_chapter"
            # keep draining the queue -- last match wins, consistent
            # with ordinary one-button-per-frame handling elsewhere
        return action

    def _handle_wrap_abort(self, aborted_key):
        """v26.07.10.03: called right after a live wrap raises
        _WrapAbortRequested. Queues the abandoned page for background
        completion (front of _extreme_page_queue -- priority over the
        proactively-scanned FIFO entries already there, since this one
        was actually asked for) unless it's already queued or already
        disk-cached, then performs the requested navigation via the
        SAME real methods the button would have called normally
        (go_back()/prev_chapter()/next_chapter()) -- no new navigation
        logic, just letting the existing one run before the wrap would
        otherwise have finished."""
        if (aborted_key not in self._extreme_page_queue
                and not os.path.isfile(self._wrap_cache_path(aborted_key))):
            self._extreme_page_queue.insert(0, aborted_key)

    def _ensure_page_built(self, renderer=None):
        key = self.state.current_file
        if key == self._page_cache_key and self.state.current_anchor is None:
            return
        # v26.07.10.03: snapshot of the page-scoped fields below, taken
        # BEFORE any of them get overwritten for the NEW page (key).
        # Only used if the live wrap further down gets aborted (see
        # _poll_wrap_abort_button()/_handle_wrap_abort()) -- restored in
        # that case so self._lines (deliberately left untouched by an
        # abort, still describing the OLD page) and self._styles/_links/
        # _images/etc stay a matched pair instead of one describing the
        # new abandoned page and the other the old one. Same save/
        # restore shape _prerender_one_extreme_page() already uses
        # around self._styles for the identical reason.
        _prev_links = self._links
        _prev_images = self._images
        _prev_anchors = self._anchors
        _prev_styles = self._styles
        _prev_styles_starts = getattr(self, "_styles_starts", [])
        _prev_styles_prefix_max_end = getattr(self, "_styles_prefix_max_end", [])
        _prev_para_spans = self._para_spans
        _prev_visible_image_keys = self._visible_image_keys
        _prev_combined_spans = getattr(self, "_combined_spans", [])
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
        # v26.07.09.15 BUG FIX (Kaleb's report -- real CPU lockup confirmed
        # via profiling: 42.8s to draw a single page, 35s of it in
        # style_at()'s linear scan over self._styles, called 377,369 times
        # on a 2697-style-span page). style_at() (inside _word_width(), used
        # by _wrap() for every word on the page) used to do a full linear
        # scan of ALL style spans on EVERY character-position query --
        # O(chars x spans), catastrophic on any page with both a lot of
        # text AND a lot of style spans (this one: ~461K chars, 2697 spans,
        # from 51 footnote citations each contributing bold/italic runs).
        # Fixed by precomputing a sorted starts[] array (bisect target) and
        # a running prefix-max-end array ONCE per page here, so style_at()
        # can binary-search to the right neighborhood and stop scanning
        # backward as soon as prefix_max_end proves no earlier span could
        # possibly still cover the query position -- correct even with
        # overlapping/duplicate spans (confirmed real duplicates exist in
        # this same page), not just a bounded-window heuristic.
        self._styles_starts = [sp.start for sp in styles]
        running_max = 0
        prefix_max_end = []
        for sp in styles:
            running_max = max(running_max, sp.end)
            prefix_max_end.append(running_max)
        self._styles_prefix_max_end = prefix_max_end
        self._para_spans = para_spans
        self._visible_image_keys = {self._img_key(im.src) for im in images}
        # v0.1.110: eagerly kick off decode for THIS page's images the
        # instant they're known, instead of waiting for draw_reader()'s
        # per-line get_image_texture() call to request() them for the
        # first time. Matters most for a cover-only page (single image,
        # no text) opened cold: a slow first decode (cold dlopen of
        # libSDL2_image, or a big portrait cover) could still land after
        # the first frame's placeholder was already painted and dirty
        # briefly cleared -- v0.1.83's fix closed the mid-draw race but
        # not this earlier one, since nothing had asked for the decode
        # yet at that point. Starting the request here, before the
        # first draw_reader() call even happens, gives the background
        # decode a head start and makes has_pending_image_updates()
        # correctly report "still loading" from frame one, so the idle
        # loop keeps redrawing until it's actually ready instead of the
        # image only appearing after an unrelated button press forces
        # a redraw.
        if getattr(self, "images_enabled", True) and images:
            self._request_page_images(images)

        combined = [("link", i, l.start, l.end) for i, l in enumerate(links)]
        combined += [("image", i, im.start, im.end) for i, im in enumerate(images)]
        self._combined_spans = combined

        avail_w = SW - _sx(40)

        wrap_key = (key, self.fonts.size_index)
        _cached_wrap = self._wrapped_cache.get(wrap_key)
        if _cached_wrap is not None:
            lines, line_span_map, line_style_runs, line_abs_starts = _cached_wrap
        else:
            # v26.07.09.19: chunked progress counter for the loading
            # screen, added after Kaleb's on-device test (real numbers:
            # 40-50s -> 4s with the v26.07.09.15/.16 algorithmic fixes +
            # v26.07.09.18 disk cache) still felt uncertain with a flat,
            # unmoving "Rendering large page..." message the whole time.
            # _wrap() calls progress_cb(fraction) periodically (throttled
            # to ~4x/second, not every paragraph) -- see _wrap()'s own
            # progress_cb parameter comment. Also pumps SDL events each
            # update so the OS doesn't consider the process fully hung
            # even though input still can't be ACTED on until the page
            # data is ready (same SDL_ttf-off-main-thread constraint as
            # before -- see the v26.07.09.17 comment above).
            progress_cb = None
            if renderer is not None and len(text) > LARGE_PAGE_LOADING_THRESHOLD:
                _last_update = [0.0]

                def progress_cb(fraction):
                    now = time.time()
                    if now - _last_update[0] < 0.25:
                        return
                    _last_update[0] = now
                    # v26.07.10.03: check for a B/L2/R2 bail-out BEFORE
                    # drawing this tick's frame -- see
                    # _poll_wrap_abort_button()'s docstring. Checked at
                    # the same throttled (~4x/second) cadence as the
                    # progress redraw itself, not every paragraph, so
                    # this can't meaningfully slow the wrap down.
                    _abort_action = self._poll_wrap_abort_button()
                    if _abort_action:
                        raise self._WrapAbortRequested(_abort_action)
                    _draw_large_page_loading_screen(renderer, self, percent=fraction)
                    SDL.SDL_RenderPresent(renderer)
                    SDL.SDL_PumpEvents()
            try:
                lines, line_span_map, line_style_runs, line_abs_starts = self._wrap(
                    text, combined, avail_w, progress_cb=progress_cb)
            except self._WrapAbortRequested as _abort:
                # v26.07.10.03: restore the page-scoped fields snapshotted
                # at the top of this function -- self._lines etc were
                # never touched by this aborted attempt, so restoring
                # _links/_styles/etc back to the OLD page keeps them a
                # matched pair again instead of describing two different
                # pages. Queue this page for background completion, then
                # perform the requested navigation via the exact same
                # methods B/L2/R2 already call in handle_button() --
                # this recomputes self._lines etc for the NEW page via a
                # fresh call to this same function, so draw_reader()
                # doesn't render a stale frame this cycle.
                self._links = _prev_links
                self._images = _prev_images
                self._anchors = _prev_anchors
                self._styles = _prev_styles
                self._styles_starts = _prev_styles_starts
                self._styles_prefix_max_end = _prev_styles_prefix_max_end
                self._para_spans = _prev_para_spans
                self._visible_image_keys = _prev_visible_image_keys
                self._combined_spans = _prev_combined_spans
                self._handle_wrap_abort(key)
                action = _abort.args[0]
                if action == "back":
                    if not self.go_back():
                        self.save_progress()
                        self.screen = SCREEN_LIBRARY
                elif action == "prev_chapter":
                    self.prev_chapter()
                elif action == "next_chapter":
                    self.next_chapter()
                if self.screen == SCREEN_READER:
                    self._ensure_page_built(renderer)
                return
            result = (lines, line_span_map, line_style_runs, line_abs_starts)
            self._wrapped_cache_put(wrap_key, result)
            # v26.07.09.18: persist to disk ONLY for genuinely extreme
            # pages (see WRAP_CACHE_DIR/LARGE_PAGE_LOADING_THRESHOLD's
            # module-level comments) -- this is the actual "only pay the
            # cost once, ever" fix; the RAM cache alone is lost on every
            # book close/switch (App.open_book() clears it deliberately,
            # see the v26.07.09.12 cache-cleanup comment there).
            if len(text) > LARGE_PAGE_LOADING_THRESHOLD:
                self._save_wrap_to_disk(key, result)
        self._lines = lines
        self._line_span_map = line_span_map
        self._line_style_runs = line_style_runs
        # v0.1.114: THE REAL BUG behind "text randomly renders small/dim"
        # (Kaleb, g_E_201507.epub's malaria article: "If you are planning
        # to visit a land where malaria is endemic..." rendering small
        # and grey like a box_rule divider, when the markup shows it's a
        # normal bold paragraph). This used to be recomputed here via
        # `running += len(ln) + 1` per line, treating EVERY line as if it
        # were followed by exactly one real "\n" -- true for a line that
        # ends an actual paragraph, but wrong for a wrapped sub-line
        # inside a multi-line paragraph, which is followed by a SPACE in
        # the real text, not a newline. That per-line assumption drifted
        # the offset further off the true value with every wrapped
        # paragraph on the page, and the drift accumulates for the rest
        # of the document. Confirmed empirically against the real epub:
        # by the time the page reached the "If you are planning..."
        # paragraph, this recomputation put it at offset 2332 -- 75
        # characters short of its TRUE offset, 2407 -- which happened to
        # fall inside the immediately preceding box_rule ParaSpan's range
        # (2372-2404), so draw_reader()'s para_kind lookup wrongly
        # matched "box_rule" and rendered it in fonts.small + COL_DIM.
        # Fixed at the source instead: _wrap() now tracks and returns the
        # TRUE abs_start it already computes correctly for each line
        # (used for line_span_map/line_style_runs) as line_abs_starts, so
        # this is just assigned directly -- no separate recomputation,
        # and no way for it to drift out of sync with the values
        # everything else on the page already relies on.
        self._line_abs_offsets = line_abs_starts
        self._page_cache_key = key

        target_char_off = None
        body_rows = _reader_body_layout(self.fonts)[2]
        if self.state.current_char_off is not None:
            # v0.1.39: exact-position restore (bookmark/resume-reading).
            # Same line-search as the anchor path below, just driven by a
            # raw character offset instead of a named anchor's offset --
            # this is what makes restore work for a spot the user merely
            # scrolled to, not just a named chapter/link target.
            # v0.1.115: this used to rebuild a `running` total via
            # `len(line) + 1` per line, same buggy assumption as the
            # box_rule text-misclassification bug (v0.1.114) -- every
            # wrapped sub-line before the target silently drifted this
            # search further from the true position, so resuming a book
            # or jumping to a bookmark could land a few lines off,
            # worse the deeper into a chapter the saved position was.
            # line_abs_starts (just computed above, correct by
            # construction) already IS each line's true start offset in
            # ascending order, so the target line is simply the last one
            # whose start is still <= char_off -- no reconstruction, no
            # drift.
            char_off = self.state.current_char_off
            target_char_off = char_off
            target_line = 0
            for li, off in enumerate(line_abs_starts):
                if off <= char_off:
                    target_line = li
                else:
                    break
            self.scroll = max(0, target_line - 2)
        elif self.state.current_anchor and self.state.current_anchor in anchors:
            char_off = anchors[self.state.current_anchor]
            target_char_off = char_off
            target_line = 0
            for li, off in enumerate(line_abs_starts):
                if off <= char_off:
                    target_line = li
                else:
                    break
            # v0.1.161 BUG FIX (Kaleb's report: NWT chapters -- especially
            # Psalms -- opening a "couple lines in" instead of at the true
            # top). Root cause: this branch always did `target_line - 2`
            # unconditionally, the same as the bookmark-restore branch
            # above. That's reasonable for a genuinely deep in-page
            # anchor (e.g. a footnote/cross-reference link far down a
            # long combined file) -- but chapter-open navigation
            # (_jump_chapter(), TOC taps) ALSO goes through this exact
            # branch, and each Bible chapter already lives in its OWN
            # split file (confirmed: 1001061123.xhtml, -split2.xhtml,
            # -split3.xhtml, ... one file per chapter) with its own
            # "chapterN" anchor placed at verse 1 -- so any heading/
            # superscription content before that anchor was silently
            # hidden except for 2 lines of it. Checked structurally (char
            # offsets and line counts only, not the actual scripture
            # text) across all 150 Psalms: confirmed 120 of 150 (80%)
            # have MORE than 2 lines of such content before their
            # "chapterN" anchor -- Psalm 1 alone has 8, so scroll landed
            # at 6 instead of 0, hiding the first 6 lines outright.
            # Root cause wasn't Hebrew-specific formatting itself, but it
            # only becomes visible with THIS much pre-anchor content --
            # confirmed the whole rest of the Bible too (next_chapter()/
            # TOC jump across every book), not just Psalms/poetry, since
            # this is a general property of how anchors are placed
            # relative to headings, not a Hebrew-rendering bug.
            # Fix: only apply the 2-line lookback when the anchor target
            # is actually off-screen already (target_line >= body_rows) --
            # in that case a small lookback still helps orient the
            # reader. When the anchor is already within the first
            # screen (the overwhelmingly common case for a fresh
            # chapter-open), just show scroll=0 so ALL heading content
            # from the true top is visible, matching what _jump_chapter()
            # already intended by setting self.scroll = 0 right after
            # goto() -- that intent was being silently overwritten here
            # before this fix.
            if target_line >= body_rows:
                self.scroll = max(0, target_line - 2)
            else:
                self.scroll = 0
        # v0.1.162 BUG FIX (Kaleb's question: "would a reference at the
        # very end of an article scroll back off the screen now that we
        # have the 100% scroll fix?"). Answer: the target itself stays
        # visible either way, but a DIFFERENT symptom of the exact same
        # bug class as v0.1.154 (page_down's pct>100% overshoot) turned
        # out to still be reachable through this anchor/char_off path,
        # which v0.1.154 never touched -- confirmed directly: jumping to
        # a target on the very last line of Psalm 119 (737 lines,
        # body_rows=24) landed scroll at 734, while the ceiling
        # page_down()/the pct display both use is only 713 -- so pct
        # would read 102% again, just via a footnote/cross-reference
        # jump instead of a page-turn. Both scroll-setting branches above
        # (bookmark-restore and anchor-jump) compute target_line from raw
        # document position with no awareness of the SAME ceiling
        # page_down() respects, so either could push scroll past it near
        # the true end of a chapter. Fix: clamp scroll to that same
        # ceiling here too, once, after both branches -- matches
        # page_down()'s own max(0, n - body_rows) exactly. Confirmed via
        # the same real Psalm 119 last-line test that this still leaves
        # the target fully visible (mathematically guaranteed: the very
        # last line is always within body_rows of that ceiling), just at
        # the bottom of the screen instead of near the top -- and that
        # pct now reads exactly 100%, never over, for any anchor/bookmark
        # jump landing anywhere in the final screenful of a chapter.
        self.scroll = min(self.scroll, max(0, len(self._lines) - body_rows))
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

    def _wrap_cache_path(self, key):
        """v26.07.09.18: on-disk path for an extreme page's wrap result --
        see WRAP_CACHE_DIR's module-level comment for scope (extreme
        pages only, not a general cache). Filename mirrors the existing
        ImageLoader._cache_path() convention: {book_id}__ prefix (so the
        existing stale-book cleanup in scan_library()'s glob pattern
        picks these up automatically, no separate cleanup path needed)
        + a filesystem-safe encoding of the spine href + the font size
        index (wrap results genuinely differ per size, same as the RAM
        cache's (href, size_index) key)."""
        safe_href = key.replace("/", "_").replace("\\", "_")
        fname = f"{self._book_id}__{safe_href}__{self.fonts.size_index}.pkl"
        return os.path.join(WRAP_CACHE_DIR, fname)

    def _load_wrap_from_disk(self, key):
        """Returns the cached (lines, line_span_map, line_style_runs,
        line_abs_starts) tuple for this page/font-size if a disk cache
        entry exists and loads cleanly, else None. Deliberately fails
        soft (returns None, logs, doesn't raise) on any read/unpickle
        error -- a corrupt or missing cache entry should just fall back
        to a normal (slower) wrap, never crash the app."""
        if not self._book_id:
            return None
        path = self._wrap_cache_path(key)
        if not os.path.isfile(path):
            return None
        try:
            with open(path, "rb") as f:
                return pickle.load(f)
        except Exception as e:
            _boot_log(f"wrap cache read failed for {path}: {e}\n")
            return None

    def _load_wrap_from_disk_with_progress(self, renderer, key):
        """v26.07.09.22: elapsed-seconds version of _load_wrap_from_disk()
        for the loading screen's disk-cache-read path. Kaleb's on-device
        report: ~4s for a 6MB cache file -- long enough to want feedback,
        but unlike the fresh-wrap path (_wrap()'s progress_cb, called at
        natural per-paragraph chunk points) a single pickle.load() call
        has no chunk points to hook into. Runs the actual read in a
        background thread instead -- SAFE to do (unlike _wrap() itself),
        since pickle.load()/file I/O never touches SDL_ttf, the same
        reasoning _prerender_extreme_pages_scan() already relies on for
        its own background thread. Polls from the main thread, redrawing
        "Loading cached page... Ns" every ~0.25s (same throttle as the
        fresh-wrap percentage) and pumping SDL events so the OS doesn't
        consider the process hung, until the background read finishes.
        Scoped narrowly to the same extreme-page loading-screen gate as
        everything else in this feature -- draw_reader() is the only
        caller."""
        result_box = {}

        def _do_load():
            result_box["value"] = self._load_wrap_from_disk(key)

        t = threading.Thread(target=_do_load, daemon=True)
        start = time.time()
        t.start()
        last_update = 0.0
        while t.is_alive():
            now = time.time()
            if now - last_update >= 0.25:
                last_update = now
                _draw_large_page_loading_screen(
                    renderer, self, message=f"Loading cached page... {int(now - start)}s")
                SDL.SDL_RenderPresent(renderer)
                SDL.SDL_PumpEvents()
            time.sleep(0.03)
        t.join()
        return result_box.get("value")

    def _prerender_one_extreme_page(self, renderer, href):
        """v26.07.09.21: wraps ONE page found by
        _prerender_extreme_pages_scan() and saves it to disk -- called
        from draw_reader() when app._extreme_page_queue has entries.
        Deliberately processes the CURRENTLY-viewed page's text/styles
        via get_page(), NOT self._links/_images/_styles etc (those belong
        to whatever page is actually on screen right now -- this must not
        touch them, or the live reading session would show wrong style
        info until the next real navigation). self._styles/_styles_starts/
        _styles_prefix_max_end are saved and restored around the _wrap()
        call for the same reason -- style_at()/_compute_line_style_runs()
        read those as instance state, not parameters, so this page's
        wrap would otherwise corrupt the currently-displayed page's."""
        try:
            text, links, images, anchors, styles, para_spans = self.doc.get_page(href)
        except Exception as e:
            _boot_log(f"prerender scan: could not load {href}: {e}\n")
            return

        _saved_styles = self._styles
        _saved_starts = self._styles_starts
        _saved_prefix = self._styles_prefix_max_end
        try:
            self._styles = styles
            self._styles_starts = [sp.start for sp in styles]
            running_max = 0
            prefix_max_end = []
            for sp in styles:
                running_max = max(running_max, sp.end)
                prefix_max_end.append(running_max)
            self._styles_prefix_max_end = prefix_max_end

            combined = [("link", i, l.start, l.end) for i, l in enumerate(links)]
            combined += [("image", i, im.start, im.end) for i, im in enumerate(images)]
            avail_w = SW - _sx(40)

            _last_update = [0.0]

            def progress_cb(fraction):
                now = time.time()
                if now - _last_update[0] < 0.25:
                    return
                _last_update[0] = now
                _draw_large_page_loading_screen(renderer, self, percent=fraction,
                                                 message="Pre-rendering large page...")
                SDL.SDL_RenderPresent(renderer)
                SDL.SDL_PumpEvents()

            result = self._wrap(text, combined, avail_w, progress_cb=progress_cb)
            self._save_wrap_to_disk(href, result)
        finally:
            self._styles = _saved_styles
            self._styles_starts = _saved_starts
            self._styles_prefix_max_end = _saved_prefix

    def _prerender_extreme_pages_scan(self):
        """v26.07.09.21: finds every spine file whose text exceeds
        PRERENDER_THRESHOLD and doesn't already have a disk wrap-cache
        entry for the current font size -- returns a list of hrefs for
        draw_reader() to wrap+cache proactively, one per frame, instead
        of waiting for on-demand navigation to hit them cold.

        SAFE to call from a background thread -- unlike _wrap() (which
        this does NOT call), this only does self.doc.get_page() (a zip
        read + XML parse) and a disk-cache-file-exists check, neither of
        which touch SDL_ttf/FreeType. Confirmed via direct measurement
        this session that a full-spine scan of get_page() alone (no wrap)
        can still take real time on a large book (2.5s for NWT's 3941
        spine files, in this sandbox -- real ARM hardware likely slower
        given the pattern seen elsewhere this session), which is exactly
        why this is backgrounded rather than run synchronously in
        open_book() the way the (much cheaper) chapter-nav fast-path is."""
        found = []
        if not self.doc:
            return found
        for f in self.doc.spine:
            try:
                text = self.doc.get_page(f)[0]
            except Exception:
                continue
            if len(text) > PRERENDER_THRESHOLD and not os.path.isfile(self._wrap_cache_path(f)):
                found.append(f)
        return found

    def _save_wrap_to_disk(self, key, result):
        """Persists an extreme page's freshly-computed wrap result to
        WRAP_CACHE_DIR so it's never recomputed for this exact (book,
        page, font size) again -- not even after closing the book or
        restarting the app. Fails soft (logs, doesn't raise) on any
        write error -- this is a pure optimization, never something that
        should be able to break reading if the disk is full/read-only."""
        if not self._book_id:
            return
        try:
            os.makedirs(WRAP_CACHE_DIR, exist_ok=True)
            path = self._wrap_cache_path(key)
            with open(path, "wb") as f:
                pickle.dump(result, f, protocol=pickle.HIGHEST_PROTOCOL)
        except Exception as e:
            _boot_log(f"wrap cache write failed for {key}: {e}\n")

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
        # v26.07.09.16 BUG FIX: same O(lines x spans) shape as style_at()'s
        # v26.07.09.15 fix, found via Kaleb's follow-up question about
        # whether other books could hit the same class of bug -- they
        # could, and worse: Enjoy Life Forever has a single page with
        # 31,390 style spans across 4.5M characters (~56,000 wrapped
        # lines), which timed out past 30 SECONDS with the old linear
        # scan here (this function iterated every one of 31,390 spans for
        # EVERY line -- ~1.7 billion iterations). Same fix: bisect to the
        # spans that could possibly overlap [abs_start, line_end), using
        # self._styles_prefix_max_end for a correct backward early-exit,
        # instead of scanning the whole list every time.
        upper_idx = bisect.bisect_left(self._styles_starts, line_end)
        j = upper_idx - 1
        while j >= 0:
            sp = self._styles[j]
            if sp.end > abs_start:
                s = max(sp.start, abs_start) - abs_start
                e = min(sp.end, line_end) - abs_start
                for c in range(s, e):
                    if sp.bold:
                        bold_flags[c] = True
                    if sp.italic:
                        italic_flags[c] = True
            if self._styles_prefix_max_end[j] <= abs_start:
                break
            j -= 1
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
            # v26.07.09.15: binary search + prefix-max-end early exit,
            # replacing a full linear scan over every style span on the
            # page -- see self._styles_starts/_styles_prefix_max_end's
            # assignment comment (_ensure_page_built()) for the full
            # story. bisect_right finds the rightmost span whose start
            # is <= abs_i; walking backward from there is safe to stop
            # the moment prefix_max_end proves no span at or before that
            # index could possibly still cover abs_i (its end would have
            # to exceed abs_i, and prefix_max_end is the max end seen so
            # far in start-order) -- correct even with overlapping or
            # duplicate spans, not just a bounded-window guess.
            idx = bisect.bisect_right(self._styles_starts, abs_i) - 1
            j = idx
            while j >= 0:
                sp = self._styles[j]
                if sp.start <= abs_i < sp.end:
                    if sp.bold:
                        b = True
                    if sp.italic:
                        it = True
                if self._styles_prefix_max_end[j] <= abs_i:
                    break
                j -= 1
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

    def _force_break_word(self, word, abs_word_start, avail_w_px):
        """v0.1.134: split a single unbreakable "word" (no interior spaces
        -- e.g. epub_engine's 32-char box-supplement divider rule
        ("\u2500"*32) or a raw dot-leader run from a book's own TOC
        formatting) into chunks that each fit avail_w_px. Only called
        when the word ALONE is wider than avail_w_px -- normal words
        never reach this path, so this can't change wrapping for the
        overwhelming majority of real text. Uses the same style-aware
        _word_width() measurement as normal wrapping (binary search per
        chunk boundary), so a force-broken bold/italic run still measures
        correctly. Confirmed via headless regression sweep across every
        real book on hand: at large Font Size, these two cases were the
        only ones where a single word's width could exceed avail_w_px at
        all -- see v0.1.134 changelog."""
        chunks = []
        n = len(word)
        i = 0
        while i < n:
            lo, hi = i + 1, n
            best = i + 1  # always take >=1 char, even if it alone overflows
            while lo <= hi:
                mid = (lo + hi) // 2
                w = self._word_width(word[i:mid], abs_word_start + i)
                if w <= avail_w_px:
                    best = mid
                    lo = mid + 1
                else:
                    hi = mid - 1
            chunks.append((i, best))
            i = best
        return chunks

    def _wrap(self, text, combined, avail_w_px, progress_cb=None):
        """Word-wrap text to fit avail_w_px pixels, measuring each word's
        actual rendered width rather than approximating via a fixed
        character count -- character-count wrapping (using a wide
        reference character like 'M') systematically undercounts how much
        text fits per line, wasting screen width.

        v0.1.114: also tracks and returns line_abs_starts -- the TRUE
        absolute character offset of each returned line in the original
        text -- instead of leaving callers to reconstruct it themselves.
        See _ensure_page_built()'s note on why that reconstruction was
        wrong for wrapped (multi-line) paragraphs.

        v26.07.09.19: progress_cb(fraction), if given, is called after
        each paragraph with offset/len(text) as a rough completion
        fraction -- NOT called every paragraph unconditionally (the
        caller in _ensure_page_built() throttles to ~4x/second itself,
        this just gives it the chance every paragraph boundary, which is
        frequent enough to feel smooth without being every single word)."""
        text_len = len(text) or 1
        span_ranges = [(s, e) for (_, _, s, e) in combined]
        char_span = [-1] * len(text)
        for i, (s, e) in enumerate(span_ranges):
            for c in range(s, min(e, len(text))):
                char_span[c] = i

        space_w = text_width(self.fonts.body, " ") or max(4, _sx(6))

        lines = []
        line_span_map = []
        line_style_runs = []
        line_abs_starts = []
        offset = 0
        for para in text.split("\n"):
            if progress_cb is not None:
                progress_cb(offset / text_len)
            if para.strip() == "":
                lines.append("")
                line_span_map.append([])
                line_style_runs.append([(0, 0, False, False)])
                line_abs_starts.append(offset)
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
                # v0.1.134 BUG FIX: a word with NO interior spaces (e.g.
                # epub_engine's 32-char box-rule divider, or a raw
                # dot-leader run from a book's own TOC) that's wider than
                # avail_w_px all by itself used to just get appended as
                # the sole content of its line regardless -- the `if
                # cur_words and ...` guard below is False when cur_words
                # is empty, so it fell through to the plain append branch
                # and rendered past the right margin. Confirmed via
                # headless regression sweep at large Font Size across
                # every real book on hand. Force-break it into
                # avail_w_px-fitting chunks instead, each becoming its
                # own line, before it ever reaches the normal packing
                # logic below.
                if w_w > avail_w_px:
                    if cur_words:
                        line_text = " ".join(cur_words)
                        abs_start = offset + starts[cur_start_idx]
                        lines.append(line_text)
                        line_span_map.append(self._line_spans(line_text, abs_start, char_span))
                        line_style_runs.append(self._compute_line_style_runs(line_text, abs_start))
                        line_abs_starts.append(abs_start)
                        cur_words = []
                        cur_w = 0
                    abs_w_start = offset + starts[wi]
                    for cs, ce in self._force_break_word(w, abs_w_start, avail_w_px):
                        chunk_text = w[cs:ce]
                        abs_start = abs_w_start + cs
                        lines.append(chunk_text)
                        line_span_map.append(self._line_spans(chunk_text, abs_start, char_span))
                        line_style_runs.append(self._compute_line_style_runs(chunk_text, abs_start))
                        line_abs_starts.append(abs_start)
                    continue
                add_w = w_w + (space_w if cur_words else 0)
                # v0.1.134: subtract WRAP_SAFETY_MARGIN from the packing
                # budget here specifically -- this decision sums each
                # word's width independently, which can measure a few px
                # narrower than the real joined-line text_width() call
                # draw_reader() actually renders (SDL_ttf glyph
                # spacing/hinting drift, worse with more short words per
                # line). The oversized-single-word check above and
                # _force_break_word()'s chunk boundaries both measure a
                # single contiguous string directly, so they don't have
                # this drift and intentionally use the full avail_w_px.
                if cur_words and cur_w + add_w > avail_w_px - WRAP_SAFETY_MARGIN:
                    line_text = " ".join(cur_words)
                    abs_start = offset + starts[cur_start_idx]
                    lines.append(line_text)
                    line_span_map.append(self._line_spans(line_text, abs_start, char_span))
                    line_style_runs.append(self._compute_line_style_runs(line_text, abs_start))
                    line_abs_starts.append(abs_start)
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
                line_abs_starts.append(abs_start)

            offset += len(para) + 1

        return lines, line_span_map, line_style_runs, line_abs_starts

    def visible_span_indices(self, line_h, body_rows):
        """Which link/image spans are actually visible on screen right now.
        Must walk the SAME way draw_reader() does: an image consumes
        several visual rows (now dynamic per its own aspect ratio, see
        _image_box_rows()) but is only one entry in self._lines, so a
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
            row += self._rows_for_li(li, line_h, body_rows)
            li += 1
        return idxs

    def _request_page_images(self, images):
        """v0.1.110: kick off image_loader.request() for every image on
        the page that isn't already decoded/decoding. The first image
        gets PRIORITY_VISIBLE (same as get_image_texture()'s normal
        request); the rest use PREFETCH so a multi-image page doesn't
        starve other work. get_image_texture() still does its own
        request() too on the frame it actually draws each image --
        request() is a no-op if a decode for that key is already
        pending/done (see ImageLoader.request()), so calling it twice
        here and there is harmless, just belt-and-suspenders for the
        first-image-on-a-cold-open race."""
        for i, im in enumerate(images):
            key = self._img_key(im.src)
            if self.image_loader.get(key) is not None:
                continue
            priority = ImageLoader.PRIORITY_VISIBLE if i == 0 else ImageLoader.PRIORITY_PREFETCH
            try:
                if self.image_loader.has_full_disk_cache(key):
                    self.image_loader.request(key, None, priority=priority)
                else:
                    jpeg_bytes = self.doc.get_image_bytes(im.src)
                    self.image_loader.request(key, jpeg_bytes, priority=priority)
            except Exception as e:
                _boot_log(f"could not pre-request image bytes for {key}: {e}\n")

    def get_image_texture(self, renderer, image_span, full_native=False):
        """v26.07.09.07: full_native=True (Image Maximize Mode only) uses a
        SEPARATE cache key (_IMGVIEW_NATIVE_KEY_SUFFIX) and requests
        force_scale_n=8 (true native resolution) instead of the shared
        inline target-box scale. Never reuses or overwrites the plain
        inline-purpose entry for the same image -- see
        _IMGVIEW_NATIVE_KEY_SUFFIX's own comment for why that matters."""
        base_key = self._img_key(image_span.src)
        key = base_key + self._IMGVIEW_NATIVE_KEY_SUFFIX if full_native else base_key
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
                    self.image_loader.request(
                        key, jpeg_bytes,
                        force_scale_n=8 if full_native else None)
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
            if link.kind == "external":
                # v0.1.98: previously silently did nothing (target_file is
                # None for external links, and the old code only acted
                # when target_file was set). There's no in-app browser, so
                # for a plain link, surface the URL via the existing
                # status_msg toast (same one used for "Bookmark added").
                # v0.1.98 (second pass): if it's actually a JW video link
                # (confirmed real format via lffi_E.epub:
                # "finder?lank=pub-lffv_11_VIDEO&wtlocale=E"), resolve and
                # download it straight to ROMS/movies instead, reusing the
                # exact same background-thread pattern start_download()
                # already uses for the Storage-screen video browser.
                kind, ident, issue, track = (JW_PLUGIN.parse_video_link(link.href)
                                             if JW_VIDEO_SUPPORTED else (None, None, None, None))
                if kind is not None and not self._link_video_downloading:
                    self._link_video_downloading = True
                    if kind == "docid":
                        self.set_status("Resolving video...", duration=20)
                    else:
                        self.set_status(f"Resolving video ({ident} #{track})...", duration=20)

                    def _do_link_video():
                        try:
                            item, err = JW_PLUGIN.resolve_video_link(link.href)
                            if item is None:
                                self._link_video_downloading = False
                                self.set_status(err or "Video not found", duration=5.0)
                                self.dirty = True
                                return
                            movies_dir = JW_PLUGIN.find_movies_dir()
                            ok, msg, _path = JW_PLUGIN.download_video(item, movies_dir)
                        except Exception as e:
                            ok, msg = False, f"Download failed: {e}"
                        self._link_video_downloading = False
                        if ok:
                            msg = (f'"{item["title"]}" downloaded. Exit PicoReader '
                                   f'and open ROM Collection -> Movies to watch it.')
                        self.set_status(msg, duration=6.0)
                        self.dirty = True

                    threading.Thread(target=_do_link_video, daemon=True).start()
                else:
                    # Not a recognized video link (e.g. a "finder?docid=..."
                    # page link with no video) -- nothing to auto-resolve,
                    # so just show the URL. v0.1.101: the status bar now
                    # wraps long messages across multiple lines on its own
                    # (_draw_status_bar/_status_msg_lines), so the full
                    # URL is shown instead of being cut short with "...".
                    self.set_status(link.href, duration=6.0)
            elif link.target_file:
                self._scroll_stack.append(self.scroll)
                self.state.follow_link(link)
                self.scroll = 0
                self.selected_span = 0
                self._page_cache_key = None
        elif kind == "image":
            # v0.1.124: Image Maximize Mode. Deliberately does not touch
            # self.state/self.scroll/self.selected_span -- B just switches
            # the screen back, so the reader is exactly as it was.
            self.enter_image_view(self._images[i])

    def enter_image_view(self, image_span):
        self._imgview_span = image_span
        self._imgview_pending_reset = True
        self._imgview_native_w = 0
        self._imgview_native_h = 0
        self.screen = SCREEN_IMAGE_VIEW

    def _imgview_viewport_h(self):
        """v0.1.129: Image Maximize Mode's actual usable height -- SH minus
        the hint bar drawn on top of it. Kaleb's bug report: the image was
        drawn full-screen edge-to-edge (SW x SH) with the hint bar simply
        overlaid afterward, but hint_height() varies with Font Size (it
        can wrap to 2-3 lines at larger sizes), so a bigger Font Size
        covered MORE of the image's bottom than the zoom/pan math ever
        accounted for -- the crop region was computed against the full
        screen, not the actually-visible area above the bar. Every zoom/
        pan method below uses this instead of a bare SH so the fill/zoom/
        pan bounds are always computed against exactly what's visible,
        at whatever Font Size is currently active. hint_height() returns
        pre-_sy-scaling design units (same convention every other screen
        already follows -- see hint_height()'s own docstring), hence the
        _sy() wrap here.

        v26.07.09.06: now passes _IMGVIEW_HINT_CALIBRATION instead of
        using the app-wide default -- this screen's hint text is much
        shorter than any other screen's, and every pixel reclaimed here
        is a pixel of actual image, not just body text. draw_image_view()
        MUST pass the same calibration to every draw_hint() call it
        makes, or the bar drawn on screen won't match the space reserved
        here."""
        return SH - _sy(hint_height(self.fonts, calibration=_IMGVIEW_HINT_CALIBRATION))

    def _imgview_reset(self, iw, ih):
        """(Re)computes zoom bounds and centers the crop for a native image
        size of iw x ih. Called once per entry, the moment real decoded
        dims are known (v0.1.124 design: always reset on entry -- Kaleb
        confirmed simplicity over persisting zoom/pan per image)."""
        self._imgview_native_w = iw
        self._imgview_native_h = ih
        vh = self._imgview_viewport_h()
        zoom_min = max(SW / iw, vh / ih) if iw and ih else 1.0
        # Cap at ~native resolution (1 image px = 1 screen px), but never
        # below the fill scale -- a small image that already needs >1x
        # upscale just to fill the screen has no extra zoom headroom
        # (Kaleb: cropped-to-fill start + native-res ceiling).
        zoom_max = max(zoom_min, 1.0)
        self._imgview_zoom_min = zoom_min
        self._imgview_zoom_max = zoom_max
        self._imgview_zoom = zoom_min  # start cropped-to-fill
        crop_w = SW / self._imgview_zoom
        crop_h = vh / self._imgview_zoom
        self._imgview_pan_x = max(0.0, (iw - crop_w) / 2.0)
        self._imgview_pan_y = max(0.0, (ih - crop_h) / 2.0)
        self._imgview_pending_reset = False

    def _imgview_zoom_by(self, factor):
        if not self._imgview_native_w or not self._imgview_native_h:
            return
        iw, ih = self._imgview_native_w, self._imgview_native_h
        vh = self._imgview_viewport_h()
        old_zoom = self._imgview_zoom
        old_crop_w = SW / old_zoom
        old_crop_h = vh / old_zoom
        # keep the center of the current crop fixed while zooming
        cx = self._imgview_pan_x + old_crop_w / 2.0
        cy = self._imgview_pan_y + old_crop_h / 2.0
        new_zoom = min(self._imgview_zoom_max, max(self._imgview_zoom_min, old_zoom * factor))
        self._imgview_zoom = new_zoom
        new_crop_w = SW / new_zoom
        new_crop_h = vh / new_zoom
        self._imgview_pan_x = cx - new_crop_w / 2.0
        self._imgview_pan_y = cy - new_crop_h / 2.0
        self._imgview_clamp_pan()

    def _imgview_pan_by(self, dx_frac, dy_frac):
        if not self._imgview_native_w or not self._imgview_native_h:
            return
        vh = self._imgview_viewport_h()
        crop_w = SW / self._imgview_zoom
        crop_h = vh / self._imgview_zoom
        self._imgview_pan_x += crop_w * dx_frac
        self._imgview_pan_y += crop_h * dy_frac
        self._imgview_clamp_pan()

    def _imgview_clamp_pan(self):
        iw, ih = self._imgview_native_w, self._imgview_native_h
        vh = self._imgview_viewport_h()
        crop_w = min(iw, SW / self._imgview_zoom)
        crop_h = min(ih, vh / self._imgview_zoom)
        self._imgview_pan_x = min(max(0.0, iw - crop_w), max(0.0, self._imgview_pan_x))
        self._imgview_pan_y = min(max(0.0, ih - crop_h), max(0.0, self._imgview_pan_y))

    def go_back(self):
        if self.state and self.state.go_back():
            self.scroll = self._scroll_stack.pop() if self._scroll_stack else 0
            self.selected_span = 0
            self._page_cache_key = None
            return True
        return False

    def _image_dims(self, image_span):
        """Cached natural (width, height) from the image's JPEG header --
        peek_jpeg_size() only, no decode. Returns None if unreadable.
        Cached by img_key since the header never changes for a given
        image (unlike box row count, which now depends on the current
        Font Size too -- see _image_box_rows())."""
        key = self._img_key(image_span.src)
        cached = self._image_dims_cache.get(key)
        if cached is not None:
            return cached if cached != (0, 0) else None
        dims = None
        try:
            jpeg_bytes = self.doc.get_image_bytes(image_span.src)
            dims = peek_jpeg_size(jpeg_bytes)
        except Exception:
            pass
        self._image_dims_cache[key] = dims if dims else (0, 0)
        return dims

    def _image_box_rows(self, image_span, line_h, body_rows):
        """Row-reservation for one image (v0.1.87): width is always
        locked to the full content width (matches get_image_texture's
        drawing math), height is fully dynamic per the image's own
        aspect ratio -- rounded UP to the next whole text line so
        surrounding text always resumes cleanly at a line boundary
        instead of a sub-line remainder (Kaleb: "snap to each respective
        text line"), and capped at body_rows so no single image can ever
        claim more than one full screen of the viewable text area above
        the hint bar (Kaleb: "cap at the max aspect ratio of the
        viewable text on screen"). Replaces the old two-tier
        IMG_BOX_ROWS/IMG_BOX_ROWS_PORTRAIT split from v0.1.84 -- that
        fixed portrait covers being width-shrunk, but (a) still let a
        20-row portrait box run past the hint bar at small Font Sizes
        where body_rows < 20, and (b) forced thin chapter-header banner
        images (Courage/Enjoy Life Forever) into a full 14-row box far
        taller than they need. Depends on line_h/body_rows (which vary
        with Font Size), so -- unlike the old cache -- nothing here is
        cached across Font Size changes; only the cheap, unchanging
        (width, height) header peek is (_image_dims_cache).

        v0.1.100 fix: Kaleb found the real Courage book's chapter banner
        (confirmed 1200x85px from the actual wcg_E.epub) didn't span the
        full 680px content width at 18pt/21pt, but did at 32pt. Root
        cause -- rows was `ceil(natural_h/line_h)`, which doesn't account
        for the pad_y inset (draw_reader's IMG_PAD_Y) subtracted from the
        box AFTER this runs. At 18pt/21pt the rounding-up margin was
        smaller than that 8px inset, so avail_h dipped BELOW natural_h and
        height became the accidental binding constraint in
        get_image_texture's `scale = min(avail_w/iw, avail_h/ih)` -- the
        banner scaled down to stay inside a too-short box instead of
        filling the width it was designed to. Verified with the exact
        real numbers: 18pt gave avail_h=40 vs natural_h=47.6 (shrinks to
        564px); 32pt gave avail_h=68 vs 47.6 (fits, full 672px). Fix:
        add the same 2*IMG_PAD_Y back into the rows calculation so
        avail_h can never fall below natural_h at ANY Font Size --
        width is then always the binding (or exactly-equal) constraint,
        matching what box_w was already designed to guarantee."""
        dims = self._image_dims(image_span)
        if not dims or not dims[0] or not dims[1]:
            return min(IMG_BOX_ROWS, body_rows)  # fallback: unreadable header
        iw, ih = dims
        avail_w = (SW - _sx(40)) - 2 * _sx(4)  # matches get_image_texture's inset
        natural_h = ih * (avail_w / iw)
        rows = math.ceil((natural_h + 2 * IMG_PAD_Y) / line_h)
        rows = max(MIN_IMG_BOX_ROWS, rows)
        # v0.1.121: was a flat CAP_MARGIN_ROWS=3 regardless of body_rows;
        # now scales with it via _cap_margin_rows() -- see that function's
        # docstring for why (Kaleb's "one line text pages" report on a
        # real workbook cover). Only affects images that are ALREADY
        # being capped (rows > body_rows - margin) -- an image that
        # already fits comfortably is completely untouched by this,
        # since min() only ever shrinks toward whichever value is smaller.
        capped_rows = max(MIN_IMG_BOX_ROWS, body_rows - _cap_margin_rows(body_rows))
        return min(rows, capped_rows)

    def _rows_for_li(self, li, line_h, body_rows):
        """Visual row cost of one _lines[] entry: this image's box-row
        reservation (see _image_box_rows()) for an image-only line, 1 for
        ordinary text. Mirrors the exact classification draw_reader() and
        visible_span_indices() use, so every place that walks lines agrees
        on how much screen space each one actually takes. In text-only
        mode (images_enabled=False) an image line renders as a single
        compact placeholder line instead of the full box, so it only costs
        1 row here too -- keeping this in sync with draw_reader() is what
        makes paging never skip/cut off content (same class of bug fixed
        in v0.1.23)."""
        if not self.images_enabled:
            return 1
        ranges = self._line_span_map[li]
        if len(ranges) == 1:
            s, e, sidx = ranges[0]
            if sidx != -1 and self._combined_spans[sidx][0] == "image" and (e - s) >= len(self._lines[li]):
                _, i, _, _ = self._combined_spans[sidx]
                return self._image_box_rows(self._images[i], line_h, body_rows)
        return 1

    def _li_is_blank(self, li):
        """True if _lines[li] contributes no visible content on its own
        -- i.e. a whitespace-only text line, NOT an image line. Used by
        page_down()/page_up()'s "is this really the first thing on the
        page" exemption (v0.1.111) so it agrees with draw_reader()'s own
        content_drawn tracking -- both need to treat leading blank lines
        the same way, or paging and drawing disagree on where a page
        actually starts (the exact unit-mismatch bug class these
        functions already guard against elsewhere, see _rows_for_li()'s
        docstring)."""
        ranges = self._line_span_map[li]
        if len(ranges) == 1:
            s, e, sidx = ranges[0]
            if sidx != -1 and self._combined_spans[sidx][0] == "image" and (e - s) >= len(self._lines[li]):
                return False  # an image line is always real content
        return self._lines[li].strip() == ""

    def page_down(self, line_h, body_rows):
        """Advance to the next screenful. Walks li-by-li accumulating the
        REAL per-line visual-row cost (dynamic per image now, see
        _image_box_rows()) instead of the old `scroll += body_rows`, which
        added a visual-row count directly onto self.scroll even though
        scroll is a _lines[] index -- any image on the page threw that
        off, sometimes over-advancing past an image entirely (skipping
        it), sometimes under-advancing so the same image reappeared. Also
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
        content_drawn = False  # v0.1.111: see _li_is_blank()'s docstring
        while li < n:
            cost = self._rows_for_li(li, line_h, body_rows)
            if content_drawn and row + cost > body_rows:
                break
            if not self._li_is_blank(li):
                content_drawn = True
            row += cost
            li += 1
            if row >= body_rows:
                break
        # v0.1.154 BUG FIX (Kaleb's report): was `min(li, max(0, n - 1))` --
        # a DIFFERENT, wrong ceiling than every other scroll path in the
        # app uses (UP/DOWN d-pad clamps to `max(0, n - body_rows)`, and
        # the reader's %-complete indicator divides by that exact same
        # value). n-1 is the last LINE index, not the scroll position that
        # shows the final full screen -- letting page_down() (L/R
        # page-turn) land anywhere up to n-1 meant repeated page-turns
        # could scroll well past the last real screenful into blank
        # space, AND pushed the % indicator's denominator (n-body_rows)
        # below the numerator (scroll), so pct could read over 100%.
        # Confirmed via real page_down() simulation on Kaleb's own books:
        # repeated L/R at end of book reached pct=900% on some titles
        # before this fix (short books, or ones with front matter, where
        # n-1 sat far past n-body_rows). Now clamped to the same
        # `max(0, n - body_rows)` ceiling as everywhere else, so the last
        # page-turn always lands exactly on the final screenful -- text
        # or image flush to the bottom, nothing beyond it -- and pct
        # cannot exceed 100%.
        self.scroll = min(li, max(0, n - body_rows))

    def page_up(self, line_h, body_rows):
        """Backward counterpart to page_down() -- walks li's downward
        from just before the current scroll, accumulating the same
        per-line row cost, so it lands exactly where a page_down() from
        the resulting position would return here. Fixes the same
        unit-mismatch page_down() had (old code did `scroll -=
        body_rows`, a visual-row count subtracted from a line-index).

        v0.1.85 fix: was missing page_down()'s `row > 0` guard on the
        break condition, so it wasn't symmetric. Consequence: an image
        whose row cost alone exceeds body_rows would break out of this
        loop on its very first iteration, before li ever moved --
        self.scroll ended up unchanged, so L1 did nothing at all on that
        image. page_down() always includes at least the first/nearest
        item (showing an oversized one clipped rather than skipping it
        outright, matching draw_reader()'s own row==0 exception) --
        page_up() now does the same, so L1 and R1 behave symmetrically
        around any image, oversized or not."""
        n = len(self._lines)
        if not n:
            return
        li = self.scroll - 1
        if li < 0:
            self.scroll = 0
            return
        row = 0
        content_drawn = False  # v0.1.111: see _li_is_blank()'s docstring
        while li >= 0:
            cost = self._rows_for_li(li, line_h, body_rows)
            if content_drawn and row + cost > body_rows:
                break
            if not self._li_is_blank(li):
                content_drawn = True
            row += cost
            li -= 1
            if row >= body_rows:
                break
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
        """Character offset of the first line currently on screen --
        captured fresh at bookmark/save time so it always reflects
        exactly where the user is, independent of whether a named anchor
        happens to apply here. Returns None if there's no page built yet
        (nothing to measure).

        v0.1.115: simplified to just read self._line_abs_offsets[scroll]
        directly -- that's already each line's true start offset (see
        v0.1.114's fix), so no reconstruction is needed at all. The old
        version rebuilt a `running` total via `len(line) + 1` per line,
        the exact same buggy assumption as the box_rule
        text-misclassification bug: correct for a line ending a real
        paragraph, wrong for a wrapped sub-line. Every wrapped paragraph
        before self.scroll drifted the saved offset further off, so a
        bookmark or resume-position saved deep in a chapter could
        restore a few lines short. The restore search in
        _ensure_page_built() was fixed the same way (v0.1.115) to look
        for the last line whose true start is <= this value, so the two
        halves of save/restore now agree by construction instead of
        coincidentally cancelling out."""
        if not getattr(self, "_lines", None) or not getattr(self, "_line_abs_offsets", None):
            return None
        if self.scroll < len(self._line_abs_offsets):
            return self._line_abs_offsets[self.scroll]
        return self._line_abs_offsets[-1] if self._line_abs_offsets else None

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
# Font Size step -- NOT drawn directly. Keep in sync if any real hint
# string grows past these -- including the download Browse screen's
# worst-case combination (Page + Search + Code + Help all present at
# once), which is currently shorter than the Reader hint below and so
# isn't one of the two calibration strings itself, but would need to
# become one if it ever grows further.
_HINT_CALIBRATION_TEXTS = (
    "D-PAD Scroll  A Follow  B Back  L/R Page  L2/R2 Chap  Y Fast x10  X Menu  START Bookmark",
    "A Open  Y Sort  LEFT/RIGHT Jump 10  L/R Font Size  L2 Download  START Menu  B Quit",
)

# v26.07.09.06: Image Maximize Mode's OWN calibration -- deliberately NOT
# part of _HINT_CALIBRATION_TEXTS above. This screen's hint text is much
# shorter than any other screen's, and unlike a text screen (where a
# taller reserved bar just costs one fewer body-text row), here the
# reserved strip subtracts directly from image display area -- worth a
# dedicated, smaller calibration. Safe because this screen never layers
# on top of another screen's already-drawn hint bar (see _hint_pt()'s
# docstring for why that matters for the anti-overlap invariant). Must
# contain the actual full hint text this screen ever draws -- if that
# text ever changes, update this too, or the shrink-loop will calibrate
# against a stale (now-wrong) string, same class of bug the main
# calibration tuple above just had.
_IMGVIEW_HINT_CALIBRATION = (
    "D-PAD Pan  L/R Zoom Out/In  B Back",
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


def _hint_pt(fonts, calibration=None):
    """v0.1.60: point size to use for the hint bar at the CURRENT global
    Font Size setting -- normally just fonts.ui_small's size, but stepped
    down (floor 11pt) if even HINT_H_MAX_LINES=3 lines at max width isn't
    enough to fit the longest known hint strings (_HINT_CALIBRATION_TEXTS).
    This keeps hint_height() a pure function of the global size_index only
    (same value everywhere, still), it just may pick a smaller hint font at
    the top 1-2 Font Size steps than the rest of the UI uses. Cached per
    size_index on the FontManager instance so this isn't recomputed every
    frame.

    v26.07.09.06: calibration is an OPTIONAL override (defaults to the
    module-level _HINT_CALIBRATION_TEXTS, i.e. every existing caller is
    unaffected). A caller can pass its OWN calibration tuple instead --
    used by Image Maximize Mode, whose hint text is far shorter than any
    other screen's, so calibrating against the app-wide worst case wasted
    real image display area for no reason (that reserved strip subtracts
    directly from image pixels on THIS screen, unlike text screens where
    it just costs a body-text row). Safe to do only because Image
    Maximize Mode does its own full-screen redraw every frame and never
    overlays on top of another screen's already-drawn hint bar the way
    e.g. the popup Menu does over Reader -- so the v0.1.52 anti-overlap
    invariant (every screen reserves the SAME height) doesn't apply here;
    that invariant exists to stop a REUSED draw call's taller bar from
    bleeding through a shorter one layered on top of it, which this
    screen structurally can't do. Cached separately (keyed by whether an
    override was given) so the two calibrations never collide in the
    same FontManager instance's cache.

    v0.1.153 BUG FOUND (Kaleb's photo report, after the DejaVu Sans
    Condensed switch): DejaVu Sans Condensed is still noticeably wider
    than Liberation Sans/Inter were at the same pt, so at 18pt the LIBRARY
    screen's calibration string (_HINT_CALIBRATION_TEXTS[1]) now needs 2
    lines where it used to fit on 1 -- and because hint_height() reserves
    ONE shared bar height across every screen (the v0.1.52 anti-overlap
    invariant), EVERY screen's hint bar got bumped to the 2-line reserved
    height at 18pt, even screens whose own hint (e.g. the reader's) only
    ever draws 1 line. Confirmed via real SDL_RenderReadPixels: at 18pt
    the reader hint bar reserved 60px for a single ~13px-tall line of
    text -- ~40% empty padding above AND below. Root cause was that the
    old shrink-loop only ever stepped pt down when HINT_H_MAX_LINES=3
    wasn't enough; it never considered stepping down to reclaim a lost
    line when a SMALL pt reduction would do it.
    Fix: after the existing floor-11 fallback, try a cheap (<=3pt) further
    reduction -- if some pt within that budget gets the calibration set
    to wrap into fewer lines than the current pt does, take the LARGEST
    such pt (least visual size cost) instead. Confirmed via the same
    real-font search: 18pt needs only a 1pt trim (14->13) to drop from 2
    lines back to 1; 32pt needs only a 3pt trim (28->25) to drop from 3
    lines to 2 -- both well within budget. 21pt/24pt/28pt would need a
    4pt+ trim to drop a line (out of budget) and are deliberately left
    alone -- their 2-line hint bars were already only ~20% padding
    (proportionate, not a bug) because those screens' hints genuinely
    span 2 real lines at that size."""
    if not fonts:
        return None
    calib_texts = calibration if calibration is not None else _HINT_CALIBRATION_TEXTS
    cache_attr = "_hint_pt_cache" if calibration is None else "_hint_pt_cache_alt"
    cache = getattr(fonts, cache_attr, None)
    if cache is None:
        cache = {}
        setattr(fonts, cache_attr, cache)
    if fonts.size_index in cache:
        return cache[fonts.size_index]
    base_pt = max(11, FontManager.SIZE_STEPS[fonts.size_index] - 4)  # == ui_small's pt
    max_w = SW - 2 * HINT_SIDE_PAD  # v0.1.137: was SW - _sx(28) (matched the
                        # old flat 14px-each-side HINT_TEXT_X padding) --
                        # must stay in sync with draw_hint()'s own max_w
                        # and the actual HINT_SIDE_PAD text x-offset, or
                        # this calibration would pick a font size that
                        # doesn't actually fit in what draw_hint() really
                        # has available.

    def _lines_at(candidate_pt):
        f = fonts._get(candidate_pt)
        if not f:
            return HINT_H_MAX_LINES
        return max(
            len(_wrap_hint_text_unbounded(f, t, max_w))
            for t in calib_texts
        )

    pt = base_pt
    while pt >= 11 and _lines_at(pt) > HINT_H_MAX_LINES:
        pt -= 2
    pt = max(11, pt)

    # v0.1.153: cheap tie-break shrink -- see docstring above.
    HINT_TIEBREAK_MAX_SHRINK = 3
    lines_at_pt = _lines_at(pt)
    floor_budget = max(11, pt - HINT_TIEBREAK_MAX_SHRINK)
    for candidate in range(pt - 1, floor_budget - 1, -1):
        if _lines_at(candidate) < lines_at_pt:
            pt = candidate
            break

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


def _force_break_plain_word(font, word, max_w):
    """v0.1.139 BUG FOUND: same class of bug as App._force_break_word()
    (v0.1.134, body text) -- a "word" with no interior spaces wider than
    max_w all by itself (confirmed real: App.handle_button sets the
    toast/status message directly to a raw link href on link-follow,
    self.set_status(link.href, ...) -- a bare URL has no spaces at all)
    just overflowed instead of wrapping. This is the standalone
    (non-style-aware) equivalent for _wrap_hint_text_unbounded() --
    toast/hint text is never styled bold/italic, so no need for
    App._force_break_word()'s per-character style lookup here, just a
    plain text_width() binary search per chunk. Only triggers when a
    single word alone exceeds max_w; ordinary words are unaffected."""
    chunks = []
    n = len(word)
    i = 0
    while i < n:
        lo, hi = i + 1, n
        best = i + 1
        while lo <= hi:
            mid = (lo + hi) // 2
            if text_width(font, word[i:mid]) <= max_w:
                best = mid
                lo = mid + 1
            else:
                hi = mid - 1
        chunks.append(word[i:best])
        i = best
    return chunks


def _wrap_hint_text_unbounded(font, text, max_w):
    """Same greedy wrap as _wrap_hint_text but without the line cap --
    used only by _hint_pt() to measure how many lines a calibration string
    actually needs at a candidate font size."""
    words = text.split(" ")
    lines, cur = [], ""
    for w in words:
        if text_width(font, w) > max_w:
            # v0.1.139: oversized lone word (e.g. a raw URL from
            # set_status(link.href, ...)) -- flush whatever's pending,
            # force-break this word into its own line(s), and continue.
            if cur:
                lines.append(cur)
                cur = ""
            lines.extend(_force_break_plain_word(font, w, max_w))
            continue
        trial = (cur + " " + w) if cur else w
        if text_width(font, trial) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _hint_lines_needed(fonts, calibration=None):
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
    step is applied). Cached per size_index.

    v26.07.09.06: calibration override, same as _hint_pt() above -- see
    that docstring for why this is safe to override for Image Maximize
    Mode specifically without breaking the anti-overlap invariant for
    every other screen (which still uses the default, app-wide
    calibration)."""
    if not fonts:
        return 1
    calib_texts = calibration if calibration is not None else _HINT_CALIBRATION_TEXTS
    cache_attr = "_hint_lines_cache" if calibration is None else "_hint_lines_cache_alt"
    cache = getattr(fonts, cache_attr, None)
    if cache is None:
        cache = {}
        setattr(fonts, cache_attr, cache)
    if fonts.size_index in cache:
        return cache[fonts.size_index]
    pt = _hint_pt(fonts, calibration=calibration)
    font = fonts._get(pt) if pt else None
    max_w = SW - 2 * HINT_SIDE_PAD  # v0.1.137: kept in sync with _hint_pt()
                        # and draw_hint() -- see _hint_pt()'s comment.
    if font:
        needed = max(
            len(_wrap_hint_text_unbounded(font, t, max_w))
            for t in calib_texts
        )
    else:
        needed = HINT_H_MAX_LINES
    needed = max(1, min(needed, HINT_H_MAX_LINES))
    cache[fonts.size_index] = needed
    return needed


def _reader_body_layout(fonts):
    """Single source of truth for the reader screen's body layout:
    (body_top, line_h, body_rows) in real pixels/rows for the CURRENT
    Font Size. MUST be used by every caller that needs body_rows for the
    reader screen.

    v0.1.86 fix: draw_reader() and handle_button() used to compute
    body_rows via two INDEPENDENT formulas that quietly disagreed --
    handle_button()'s never subtracted body_top or footer_h at all, and
    used hint_height()'s return value (explicitly documented as
    pre-_sy-scaling "design units") directly against real-pixel SH
    without scaling it. Confirmed via the real bundled font: this
    produced a 1-2 row overcount in handle_button() at EVERY Font Size
    (14pt through 32pt), not uniquely at 24pt -- 24pt is just where it
    happened to line up badly for a given book's line layout. Since
    handle_button() is what actually drives page_up()/page_down() and
    the UP/DOWN scroll clamp, believing more rows fit on a page than
    draw_reader() would actually draw meant scroll could be advanced
    straight past an image the real screen never had room for --
    "skips the image entirely" (Kaleb). Fixed by giving both callers the
    exact same formula instead of two hand-copied ones."""
    body_top = _sy(14)
    footer_h = TTF.TTF_FontHeight(fonts.ui_small) + _sy(14)
    body_h = SH - body_top - _sy(hint_height(fonts)) - footer_h
    # v0.1.116: leading was a flat +6px regardless of font size, so as
    # actual glyph height grows with size (measured directly off the
    # bundled Liberation Sans metrics) the +6 became a shrinking
    # fraction of line height -- ~24% extra breathing room at 14pt but
    # only ~3% at 32pt. Kaleb confirmed the tight packing at large Font
    # Size is wanted (fits more text on screen) and should stay as-is;
    # only the smaller sizes needed "a tad" more room. SIZE_STEPS[0:3]
    # are 14/16/18 -- those three get +8 instead of +6, every larger
    # step is untouched.
    pt = fonts.SIZE_STEPS[fonts.size_index]
    leading = 8 if pt <= 18 else 6
    line_h = _sy(pt + leading)
    body_rows = max(1, body_h // line_h)
    return body_top, line_h, body_rows


def hint_height(fonts, calibration=None):
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
    small Font Size where 1 line is all that's ever needed.

    v26.07.09.06: optional calibration override, passed straight through
    to _hint_pt()/_hint_lines_needed() -- see _hint_pt()'s docstring for
    which screen uses this and why it's safe."""
    pt = _hint_pt(fonts, calibration=calibration)
    lines = _hint_lines_needed(fonts, calibration=calibration)
    if fonts and pt:
        font = fonts._get(pt)
        # v0.1.133 BUG FIX: was TTF_FontHeight(font)/_SY alone -- draw_hint()
        # actually spaces lines using TTF_FontHeight(font) + _sy(6) (a 6px
        # per-line gap), so for a 3-line hint this formula under-reserved
        # by ~18px design-unit-equivalent, letting the real text block be
        # TALLER than the bar meant to hold it. Confirmed via headless
        # simulation with the real bundled font: at max Font Size, the
        # Library screen's hint (the one hint string long enough to need
        # all 3 lines) had content_h=114 vs. a reserved bar_h of only 110
        # -- an actual overflow, not just tight. Matching the same +6
        # per-line gap here is what guarantees bar_h is always >= the
        # real content height draw_hint() will compute.
        line_h_design = (TTF.TTF_FontHeight(font) + _sy(6)) / _SY
    else:
        line_h_design = HINT_H_BASE * 0.6
    return line_h_design * lines + HINT_H_BASE * 0.35


def _status_msg_lines(fonts, msg):
    """v0.1.101: wrap a long status/toast message (e.g. a jw.org link URL)
    across multiple lines instead of overflowing off the right edge.
    Kaleb: "the toast hint for the download doesn't text wrap at larger
    font sizes" -- ui_small grows with reader Font Size (see
    _status_bar_h's own comment below), so a URL that fit on one line at
    14pt increasingly doesn't at 32pt, and a single render_text() call
    was never going to wrap on its own regardless of size. Short
    messages ("Bookmark added") just come back as a single-item list,
    unaffected.
    v0.1.139: width now matches HINT_SIDE_PAD (same padding the toast's
    own corner-rounding needs -- see _draw_status_bar()) instead of the
    old flat _sx(28). No line cap here (_wrap_hint_text_unbounded), so
    unlike the hint bar there's no calibration to keep in sync -- a
    narrower width just means it may wrap to one more line, which the
    bar already grows to fit."""
    return _wrap_hint_text_unbounded(fonts.ui_small, msg, SW - 2 * HINT_SIDE_PAD)


def _draw_status_bar(renderer, fonts, msg, color, bottom_y):
    """v0.1.101: draws a (possibly multi-line) status/toast bar whose
    bottom edge sits at bottom_y (e.g. just above the hint bar), growing
    UPWARD as needed for extra lines instead of a single fixed-height
    bar. Replaces 3 near-identical single-line call sites in
    draw_reader()/draw_library()/draw_download_browse() that each
    independently called _status_bar_h() + one render_text() -- keeping
    this in one place means a future tweak can't drift out of sync
    between the three screens the way three hand-copied blocks could.

    v0.1.153 DESIGN CHANGE (Kaleb's photo annotation): was a full-width
    (x=0, w=SW) bar -- looked like a large empty band whenever the
    message was short ("Bookmark added" etc.), since the panel color
    filled the whole screen width regardless of how little text it held.
    Now a pill: width hugs the widest wrapped line (+ TOAST_PILL_PAD_X
    each side), left-anchored at TOAST_PILL_MARGIN_X from the screen
    edge (matching where the old bar's text used to start), with fully
    rounded (stadium-shape) ends via fill_rect_rounded's radius=bar_h//2
    -- no need for the old erase-to-background corner helpers, since a
    floating pill that doesn't touch the bottom/side screen edges
    doesn't need them.
    v0.1.153: also tightened vertical padding -- see TOAST_ROW_PAD/
    TOAST_LINE_GAP comments (DejaVu Sans Condensed's real glyph ink runs
    notably shorter than its own TTF_FontHeight metric).
    v26.07.10.03: passes msg through _kaomoji_for_status() here (one
    choke point -- every toast in the app draws through this single
    function) so "Downloading..."/"...downloaded"/"...already ..."
    messages get their face without touching the ~6 individual
    set_status() call sites."""
    msg = _kaomoji_for_status(msg)
    lines = _status_msg_lines(fonts, msg)
    line_h = TTF.TTF_FontHeight(fonts.ui_small) + _sy(TOAST_LINE_GAP)
    bar_h = max(_status_bar_h(fonts), line_h * len(lines) + _sy(TOAST_ROW_PAD))
    top_y = bottom_y - bar_h

    text_w = max((text_width(fonts.ui_small, line) for line in lines), default=0)
    max_pill_w = SW - 2 * TOAST_PILL_MARGIN_X
    pill_w = min(max_pill_w, text_w + 2 * TOAST_PILL_PAD_X)
    pill_x = TOAST_PILL_MARGIN_X

    fill_rect_rounded(renderer, pill_x, top_y, pill_w, bar_h, COL_PANEL,
                       radius=bar_h // 2)

    content_h = line_h * len(lines)
    start_y = top_y + max(0, (bar_h - content_h) // 2)
    for i, line in enumerate(lines):
        render_text(renderer, fonts.ui_small, line, color,
                     pill_x + TOAST_PILL_PAD_X, start_y + i * line_h + _sy(3))
    return bar_h


TOAST_ROW_PAD = 4  # v0.1.153: was a flat 10 (see _status_bar_h/_draw_status_bar
                    # docstrings) -- reduced because DejaVu Sans Condensed's
                    # TTF_FontHeight already runs well taller than its real
                    # glyph ink (confirmed via pixel readback: ~17px reported
                    # height vs ~10px actual ink for "Bookmark added" at
                    # 18pt), so the old Liberation/Inter-tuned padding piled
                    # on top of that was excessive. Confirmed via pixel
                    # readback across all 7 Font Sizes and several real
                    # toast strings (including descenders) that this does
                    # NOT clip any glyph at any size before shipping.
TOAST_LINE_GAP = 3  # v0.1.153: was 6, same reasoning as TOAST_ROW_PAD above.
TOAST_PILL_MARGIN_X = _sx(14)  # gap from the screen's left edge to the
                    # pill's own left edge (v0.1.153, new pill-shape toast --
                    # Kaleb's photo annotation: the old bar spanned the full
                    # screen width even when the message was short, leaving a
                    # large empty band to the right of the text).
TOAST_PILL_PAD_X = _sx(16)  # internal padding from the pill's edge to the
                    # text itself, each side.

# v26.07.10.03: small kaomoji-style faces for loading/status feedback
# (Kaleb's request). Built ONLY from glyphs confirmed present in the
# bundled DejaVu Sans Condensed font -- the originally requested faces
# used Kannada (U+0CB0) and Malayalam (U+0D26/U+0D4D/U+0D3F) script
# characters plus U+02F5, none of which this font covers. Confirmed via
# direct cmap inspection (fontTools) this session: this font's runtime
# glyph-substitution table is empty (see FONT_LICENSE.txt/module notes
# elsewhere), so a missing glyph renders as a blank box with no
# fallback -- not a cosmetic risk worth taking for a loading-screen
# decoration. Every character below was individually verified present
# in font.ttf's cmap before use.
FACE_THINKING_A = "(\u00ac\u203f\u00ac)"      # (¬‿¬)
FACE_THINKING_B = "(\u2299_\u2299)?"          # (⊙_⊙)?
FACE_DONE = "\u0669(\u25d5\u203f\u25d5)\u06f6 \u2727"  # ٩(◕‿◕)۶ ✧
FACE_CYCLE_SECONDS = 0.6  # how often the thinking face swaps A/B

# v26.07.10.04: two more faces (Kaleb's request) -- the Menu screen's
# logo, and the exit-toast face. Same reasoning as above: the ORIGINAL
# requests used U+02F6 (MODIFIER LETTER MIDDLE DOUBLE ACUTE ACCENT,
# missing from this font), U+15DC (Canadian Aboriginal Syllabics,
# missing), and halfwidth katakana U+FF89/U+FF9E (missing) -- confirmed
# via the same fontTools cmap check as before. Substitutes below use
# only glyphs individually confirmed present: ˚ (U+02DA, small ring)
# stands in for the missing sparkle-cheek mark, ◡ (U+25E1, lower half
# circle) stands in for the missing compressed "w" mouth, and a plain
# ASCII "~" replaces the missing katakana hand-wave, keeping the same
# "waving off" feel.
FACE_MENU_LOGO = "(\u02da\u1d54 \u1d55 \u1d54\u02da)"    # (˚ᵔ ᵕ ᵔ˚)
EXIT_TOAST_SECONDS = 0.9  # how long the "Exiting..." toast shows before
                    # the window actually closes -- long enough to
                    # register as a deliberate goodbye, short enough
                    # not to feel like the app is hanging on exit.

# v26.07.10.05/.06: boot splash timing (Kaleb's request) -- title types
# over SPLASH_TYPE_SECONDS, then the subtitle types over SPLASH_
# SUBTITLE_TYPE_SECONDS, then everything holds for SPLASH_HOLD_SECONDS
# before handing off to the real destination screen. 2 + 2 + 3 = 7s
# total, matching Kaleb's exact spec. See draw_splash().
SPLASH_TYPE_SECONDS = 2.0
SPLASH_SUBTITLE_TYPE_SECONDS = 2.0
SPLASH_HOLD_SECONDS = 3.0
SPLASH_TITLE_END = SPLASH_TYPE_SECONDS
SPLASH_SUBTITLE_END = SPLASH_TITLE_END + SPLASH_SUBTITLE_TYPE_SECONDS
SPLASH_TOTAL_SECONDS = SPLASH_SUBTITLE_END + SPLASH_HOLD_SECONDS
SPLASH_TITLE = "PICO READER"
# v26.07.10.06/.09: subtitle face. v26.07.10.09's requested string
# (⸜(｡˃ ᵕ ˂ )⸝♡) uses U+2E1C/U+2E1D (decorative low double-quote
# brackets) and U+FF61 (halfwidth ideographic full stop), all three
# absent from this font (confirmed via fontTools cmap) -- ♡ (U+2661)
# IS present and kept as-is. Substituted the three missing marks with
# ˋ/ˊ (modifier letter grave/acute, confirmed present) standing in for
# the ⸜/⸝ sparkle-hand brackets, and ˚ for the ｡ dot -- same "hands
# framing a happy face" shape, all confirmed-present glyphs.
SPLASH_SUBTITLE = "Designed with Love by: Kaleb Fabsik \u02cb(\u02da\u02c3 \u1d55 \u02c2 )\u02ca\u2661"


def _kaomoji_for_status(msg):
    """Appends a small face to certain status/loading strings -- a
    cycling 'thinking' face for anything still in progress
    (Downloading/Rendering/Pre-rendering/Loading), a fixed 'done' face
    for anything reporting completion or an already-satisfied request
    (downloaded/already). Purely cosmetic and text-based -- does not
    change what these messages say, only appends to them, so it can't
    affect any logic elsewhere that inspects msg content. See
    FACE_THINKING_A/_B/FACE_DONE for why these specific glyphs were
    chosen over the originally requested ones."""
    low = msg.lower()
    if low.startswith(("downloading", "rendering", "pre-rendering", "loading")):
        face = (FACE_THINKING_A if int(time.time() / FACE_CYCLE_SECONDS) % 2 == 0
                else FACE_THINKING_B)
        return f"{msg}  {face}"
    if "downloaded" in low or "already" in low:
        return f"{msg}  {FACE_DONE}"
    return msg


def _status_bar_h(fonts):
    """Height of the transient status-message bar (e.g. 'Font size: 32pt
    (largest)') -- v0.1.54. Was a fixed _sy(30)/_sy(22) pair sized for the
    old fixed-size UI font; at max Font Size the now-larger ui_small text
    no longer fit inside that fixed box and visually spilled into the
    hint bar directly below it (confirmed via Kaleb's on-device
    screenshot: 'Font size: 32pt (largest)' overlapping the hint text).
    Scales the same way _row_h() does.
    v0.1.153: pad dropped 10->TOAST_ROW_PAD (4) -- see _draw_status_bar's
    docstring for why (DejaVu Sans Condensed's real glyph ink runs well
    short of its own TTF_FontHeight; the old flat padding was tuned for
    Liberation Sans/Inter's tighter metrics and became excessive on top
    of DejaVu's already-taller FontHeight)."""
    return _row_h(fonts.ui_small, pad=TOAST_ROW_PAD)


IMG_BOX_ROWS = 14  # v0.1.87: no longer the normal-case box size (that's
                    # fully dynamic now, see App._image_box_rows()) -- kept
                    # only as the fallback for an image whose header can't
                    # be read/peeked, so a bad image still can't break
                    # pagination.

IMG_PAD_Y = 4  # v0.1.100: the inset draw_reader() insets an image box by on
               # top/bottom (pad_y = _sy(IMG_PAD_Y) there) -- pulled out as
               # a shared constant so _image_box_rows()'s row math (which
               # needs to know this same inset to guarantee avail_h never
               # drops below natural_h) can't silently drift out of sync
               # with the actual draw-time inset the way two independently
               # hand-copied "4"s could.

MIN_IMG_BOX_ROWS = 1  # v0.1.99: was 3 (v0.1.87). BUG FOUND during Kaleb's
                    # "bug check everything" request: v0.1.97's top-align/
                    # border-hug change only repositioned the image/border
                    # WITHIN the reserved box -- it never touched box_rows
                    # itself, and row += box_rows (draw_reader) is what
                    # actually decides when text resumes. So the floor of
                    # 3 was still forcing thin banners (Section 1 Timeline,
                    # Courage/Enjoy Life Forever headers) to reserve 3 full
                    # text-line-heights before text continued, regardless
                    # of how the image was drawn inside that space -- the
                    # v0.1.97 fix was cosmetic only and did NOT fix the
                    # reported bug. ceil(natural_h/line_h) in
                    # _image_box_rows() already guarantees >=1 for any
                    # image with real height, so this floor is now just a
                    # defensive minimum (e.g. a malformed header reporting
                    # near-zero height), not a forced 3-row pad. Combined
                    # with v0.1.97's top-align, a thin banner now reserves
                    # ~1 line of space and the image sits flush at its top.

MIN_CAP_MARGIN_ROWS = 3  # v0.1.113's original flat value, now used as the
                    # floor for _cap_margin_rows() rather than a constant
                    # used directly -- see that function's docstring.


def _cap_margin_rows(body_rows):
    """v0.1.121: CAP_MARGIN_ROWS was a flat 3 regardless of Font Size, so
    a fully-capped image (e.g. a portrait meeting-workbook cover) always
    left EXACTLY 3 rows for trailing content whether body_rows was 28
    (14pt) or 16 (32pt) -- proportionally that's generous breathing room
    at 32pt but barely one short heading's worth at 14pt, and confirmed
    on a real workbook cover page (202025160.xhtml) to push everything
    after the title (copyright line, cover-picture caption) onto a
    second, nearly-empty page -- Kaleb's "one line text pages" report.
    Now scales at 20% of body_rows, floored at MIN_CAP_MARGIN_ROWS (3)
    so 32pt -- already the tightest case, and the one Kaleb specifically
    tuned to 3 in v0.1.112/113 -- is completely unchanged; only the
    larger body_rows counts at smaller Font Sizes get more headroom."""
    return max(MIN_CAP_MARGIN_ROWS, round(body_rows * 0.20))


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


def _round_image_bottom_corners_to_hint(renderer, img_bottom_y, radius):
    """v0.1.136: rounds the BOTTOM-left/right corners of the maximized
    image itself (Image Maximize Mode only) by painting COL_HINT_BG
    quarter-circles over the image's own last few rows, right where it
    meets the hint bar below -- Kaleb's request, via a photo with red
    annotations showing exactly this. This is the mirror image of
    _round_top_corners_to_bg() (which rounds the HINT BAR's top corners
    to reveal whatever's ABOVE it) -- here it's the IMAGE's bottom
    corners being rounded to reveal the hint bar's own color, so the
    curve reads as "the image's corners are cut away, blending into the
    hint bar" rather than "the hint bar has rounded corners poking into
    the image." Must be called AFTER the image's SDL_RenderCopy but
    BEFORE draw_hint() draws the actual hint bar rectangle (harmless
    either order since the two don't overlap in y, but this keeps the
    z-order intuitive). img_bottom_y is the image's own bottom edge
    (== the hint bar's top edge, App._imgview_viewport_h())."""
    if radius <= 0:
        return
    SDL.SDL_SetRenderDrawColor(renderer, COL_HINT_BG.r, COL_HINT_BG.g,
                                COL_HINT_BG.b, COL_HINT_BG.a)
    for row in range(radius):
        dy = radius - row
        dx = int(math.sqrt(max(0, radius * radius - dy * dy)))
        inset = radius - dx
        if inset <= 0:
            continue
        y = img_bottom_y - 1 - row
        left = Rect(0, y, inset, 1)
        SDL.SDL_RenderFillRect(renderer, ctypes.byref(left))
        right = Rect(SW - inset, y, inset, 1)
        SDL.SDL_RenderFillRect(renderer, ctypes.byref(right))


def _draw_screen_frame(renderer, bottom_radius=None):
    """v0.1.131: BMO-style outer screen frame -- masks all FOUR corners of
    the whole 720x720 canvas with a quarter-circle cut, always, on every
    screen (Kaleb's request, see SCREEN_FRAME_RADIUS above).
    Called exactly once per frame, right before SDL_RenderPresent, AFTER
    every screen's own draw_*() has finished -- this is deliberately NOT
    baked into individual draw_*() functions so it can never be
    forgotten on a screen (including SCREEN_IMAGE_VIEW, where it will
    correctly clip the corners of a full-bleed maximized image, which is
    exactly what Kaleb asked for). Same per-row quarter-circle mask
    technique as fill_rect_rounded()/_round_top_corners_to_bg(), just
    applied to all 4 corners of the physical screen instead of one
    panel's edge, and with its own larger SCREEN_FRAME_RADIUS instead of
    the small per-panel CORNER_RADIUS.

    COLOR HISTORY (Kaleb's report -- corners invisible on the real splash
    screen, traced to a real measured problem: pure black against every
    theme's original COL_BG measured ~1.06-1.15:1 WCAG contrast, well
    under the 3:1 UI minimum, so corners were near-invisible on EVERY
    screen/theme since v0.1.131, not something newly broken by the
    splash). v26.07.10.08 tried lightening the CORNER instead (COL_BG
    +85, theme-tinted) to fix this without touching any theme's palette.
    v26.07.10.10 reverted that -- Kaleb explicitly wanted corners
    "totally black" -- and lightened each theme's own COL_BG instead
    (see THEMES' bg comments), settling on 1.5:1 contrast against pure
    black after live-iterating through several targets (3:1 -> 2.7:1 ->
    2.2:1 -> 1.9:1 -> 1.5:1, "subtle but just barely noticeable" was
    the explicit brief) -- deliberately below the WCAG 3:1 UI minimum,
    an aesthetic choice, not an accessibility target. COL_PANEL and
    COL_ACCENT were both evaluated as alternatives to a bg change during
    the v26.07.10.08 pass -- panel measured equally poor to black
    (~1.03-1.11:1, a subtle surface-elevation shade, not built for bold
    edges), accent gave real contrast but turned corners into a bold
    theme-color cut, abandoning the black-bezel look entirely.

    v0.1.135 added a FRAME_EDGE_COLOR stroke along the curve boundary
    (Image Maximize Mode's bottom corners had near-zero contrast against
    the near-black hint bar there). v0.1.138 restricted it to bottom
    corners only after Kaleb reported it looking like an unwanted
    "highlight" on the top corners, which never needed it. v0.1.139:
    Kaleb reported the bottom-corner stroke ITSELF now reads as a
    separate, oddly-placed small mark that undermines the hint bar's own
    (bigger, v0.1.137) curve directly above it -- "give the impression
    that the hint bar has no curve when it actually does." Removed
    entirely, per his explicit direction ("remove it completely") --
    every corner is back to a plain, stroke-free black cut, the original
    v0.1.131 look. Note: this reopens the original v0.1.135 problem
    (Image Maximize Mode's bottom corners have low contrast against the
    dark hint bar there specifically) -- Kaleb's instruction was clear
    and direct, so honored as-is; that screen can be revisited
    separately if it turns out to matter in practice.

    v26.07.09.14 BUG FIX (Kaleb's report -- hint bar corners "come to a
    point" at small Font Size steps): root cause wasn't the hint bar's
    OWN corner-rounding math (draw_hint()/_round_top_corners_to_bg() --
    traced through by hand, genuinely a smooth quarter-circle at every
    radius). It's that THIS function's bottom-corner mask is always the
    same fixed SCREEN_FRAME_RADIUS (28px), regardless of how tall the
    hint bar underneath it actually is. Confirmed: the hint bar is only
    ~33px tall at the smallest Font Size step vs ~92px at the largest --
    a fixed 28px cut consumes ~85% of the bar's height at the smallest
    size but only ~30% at the largest, which reads as a disproportionate,
    steep-looking cut rather than a gentle curve at small sizes.
    bottom_radius now lets the caller (the main render loop, which knows
    the current hint bar height via app.fonts) scale the BOTTOM corners
    down to match; top corners are untouched (always the full fixed
    radius) since they're never adjacent to the hint bar."""
    top_radius = max(0, min(SCREEN_FRAME_RADIUS, SW // 2, SH // 2))
    if bottom_radius is None:
        bottom_radius = top_radius
    else:
        bottom_radius = max(0, min(bottom_radius, SW // 2, SH // 2))
    max_radius = max(top_radius, bottom_radius)
    if max_radius <= 0:
        return
    # v26.07.10.10: reverted to pure black (Kaleb's request: "totally
    # black" corners) -- the v26.07.10.08 theme-tinted +85 approach is
    # no longer needed now that each theme's bg itself was lightened
    # (see THEMES' bg comments) specifically to give pure black
    # something to contrast against, rather than lightening the corner
    # to contrast against an unchanged near-black bg.
    SDL.SDL_SetRenderDrawColor(renderer, 0, 0, 0, 255)
    for row in range(max_radius):
        if row < top_radius:
            dy = top_radius - row
            dx = int(math.sqrt(max(0, top_radius * top_radius - dy * dy)))
            inset = top_radius - dx
            if inset > 0:
                tl = Rect(0, row, inset, 1)
                SDL.SDL_RenderFillRect(renderer, ctypes.byref(tl))
                tr = Rect(SW - inset, row, inset, 1)
                SDL.SDL_RenderFillRect(renderer, ctypes.byref(tr))
        if row < bottom_radius:
            dy = bottom_radius - row
            dx = int(math.sqrt(max(0, bottom_radius * bottom_radius - dy * dy)))
            inset = bottom_radius - dx
            if inset > 0:
                bl = Rect(0, SH - 1 - row, inset, 1)
                SDL.SDL_RenderFillRect(renderer, ctypes.byref(bl))
                br = Rect(SW - inset, SH - 1 - row, inset, 1)
                SDL.SDL_RenderFillRect(renderer, ctypes.byref(br))


def draw_hint(renderer, fonts, text, skip_top_corners=False, calibration=None):
    """v0.1.136: skip_top_corners lets a caller suppress this function's
    own top-corner erase-to-COL_BG (_round_top_corners_to_bg) -- needed
    by Image Maximize Mode, which now rounds the IMAGE's bottom corners
    into COL_HINT_BG instead (see _round_image_bottom_corners_to_hint()
    and its docstring for why that's the correct direction there, unlike
    every other screen where erasing to COL_BG is correct because the
    content directly above the hint bar really is COL_BG).

    v26.07.09.06: calibration override, passed straight through to
    _hint_pt()/hint_height()/_hint_lines_needed() -- see _hint_pt()'s
    docstring. A caller passing this MUST use the exact same calibration
    value on every draw_hint() call it makes (Image Maximize Mode's 3
    call sites all do), so the bar height this function draws always
    matches whatever the caller's own layout math (e.g.
    App._imgview_viewport_h()) reserved for it."""
    pt = _hint_pt(fonts, calibration=calibration)
    font = fonts._get(pt) if pt else fonts.ui_small
    max_w = SW - 2 * HINT_SIDE_PAD  # v0.1.137: kept in sync with _hint_pt()
                        # and _hint_lines_needed() -- see _hint_pt()'s comment.
    h = hint_height(fonts, calibration=calibration)
    max_lines = _hint_lines_needed(fonts, calibration=calibration)
    lines = _wrap_hint_text(font, text, max_w, max_lines) or [""]
    bar_h = _sy(h)
    top_y = SH - bar_h
    # Always fill the FULL reserved area (not just what these lines need)
    # so nothing from a previous, taller hint draw can bleed through.
    fill_rect(renderer, 0, top_y, SW, bar_h, COL_HINT_BG)
    if not skip_top_corners:
        # v0.1.137: target radius bumped from CORNER_RADIUS (6px) to
        # HINT_CORNER_RADIUS (matches SCREEN_FRAME_RADIUS, 28px) --
        # Kaleb wants the hint bar's top corners "close to the overall
        # screen corners." Still clamped to bar_h // 2 (same clamp
        # fill_rect_rounded uses) so the two smallest Font Size steps,
        # where the bar itself is thinner than 2*28px, scale down
        # naturally instead of producing an overlapping/degenerate
        # curve.
        corner_radius = min(HINT_CORNER_RADIUS, bar_h // 2)
        _round_top_corners_to_bg(renderer, 0, top_y, SW, corner_radius)
    # v0.1.131: was `row_h = bar_h / max_lines` -- fine when a hint used
    # every reserved line, but bar_h is sized for the FONT SIZE's worst
    # case (max_lines), not this particular string's actual line count.
    # A short hint ("B Back") at a Font Size where max_lines=2 or 3 was
    # always drawn starting at the top slot, leaving the rest of the bar
    # empty below it instead of centered in it. Now centers the actual
    # `lines` block within the full bar height regardless of how many
    # lines the reserved worst-case allows.
    line_h = TTF.TTF_FontHeight(font) + _sy(6)
    content_h = line_h * len(lines)
    start_y = top_y + max(0, (bar_h - content_h) // 2)
    # v0.1.133 BUG FIX: pure centering (above) can push the text block's
    # bottom edge into SCREEN_FRAME_RADIUS's corner cut when a hint wraps
    # to enough lines to nearly fill the reserved bar height (confirmed
    # via simulation -- the Library screen's hint at max Font Size, see
    # HINT_BOTTOM_SAFE_GAP's comment above). Clamp so the block's bottom
    # never sits closer than HINT_BOTTOM_SAFE_GAP to SH -- if that means
    # giving up perfect centering in this one tight case, that's fine;
    # not clipping matters more than pixel-perfect centering.
    max_start_y = SH - HINT_BOTTOM_SAFE_GAP - content_h
    start_y = min(start_y, max_start_y)
    start_y = max(start_y, top_y)  # never push above the bar's own top
    for li, line in enumerate(lines):
        render_text(renderer, font, line, COL_HINT_TEXT, HINT_SIDE_PAD,
                    start_y + li * line_h + _sy(3))


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
    # v26.07.09.02: tightened gap under heading (4->2) -- this line was
    # already COL_DIM + ui_small (smallest UI font), i.e. already treated
    # as secondary metadata; the only remaining minimalism tweak was
    # spacing it closer to the heading it belongs to, rather than floating
    # with an even gap top and bottom like body content would.
    sort_y = heading_y + TTF.TTF_FontHeight(app.fonts.ui_heading) + _sy(2)
    sort_line = f"Sort: {LIBRARY_SORT_LABELS[app.lib_sort_mode]}"
    if app.lib_filter_mode != "all":
        sort_line += f"   Filter: {LIBRARY_FILTER_LABELS[app.lib_filter_mode]}"
    render_text(renderer, app.fonts.ui_small, _fit_text(app.fonts.ui_small, sort_line, SW - _sx(40)),
                COL_DIM, _sx(20), sort_y)

    row_h = _row_h(app.fonts.ui_body)
    top = sort_y + TTF.TTF_FontHeight(app.fonts.ui_small) + _sy(10)
    visible = (SH - top - _sy(hint_height(app.fonts))) // row_h
    row_max_w = SW - _sx(44)

    # v0.1.125: Kaleb's report -- a book that's been started only ever
    # showed a bare "42%" suffix, indistinguishable at a glance from any
    # other partially-read book, and the only way to tell WHICH one was
    # actually resumable via "Continue Reading" was to switch to Last
    # Read sort or open the Library Menu. Reuses most_recent_book()
    # unchanged (same function the Library Menu's dynamic label and
    # open_continue_reading() already share) so this can never disagree
    # with what "Continue Reading" actually opens.
    #
    # v0.1.127: v0.1.126 replaced the percentage on this one row with the
    # book's chapter/section name (required briefly opening the book's
    # EpubDocument for TOC parsing). Kaleb decided that was more than
    # this needed -- reverted, and simplified further: the percentage is
    # now gone from EVERY row (not just this one), replaced by literal
    # "Continue Reading" text on just this row. No per-book I/O at all
    # anymore, back to a plain fixed-height row loop like v0.1.125 (no
    # variable row heights, no wrapping, no chapter-label cache).
    continue_book = app.most_recent_book()
    continue_filename = continue_book["filename"] if continue_book else None

    # v26.07.09.02: fixed-width icon gutter for resume/pin/finished
    # markers -- reserves room for the worst case (all three glyphs +
    # inter-glyph spaces) once, up front, so every row's title starts at
    # the same x regardless of which icons that particular book shows.
    # v26.07.09.14: Kaleb's report -- the fixed-width gutter above (kept
    # for reference in the comment history just below) reserved room for
    # the WORST case on every single row, even rows with zero icons,
    # which read as wasted space on the left of most titles. Reverted to
    # a per-row dynamic width: icons (if any) push the title right by
    # exactly their own width + a small gap; a row with no icons starts
    # its title right at the left margin. Trade-off, explicitly chosen by
    # Kaleb over the v26.07.09.02 alignment guarantee: titles no longer
    # all start at the same x, but no row wastes space it isn't using.

    start = max(0, app.lib_index - visible // 2)
    for i in range(visible):
        bi = start + i
        if bi >= len(app.books):
            break
        book = app.books[bi]
        y = top + i * row_h
        # v0.1.117: the armed-for-delete row used to live here (SELECT on
        # this screen) -- delete moved into the Library Menu (START), so
        # SELECT is now the Finished/Unfinished toggle and this row is
        # back to a plain selection highlight.
        if bi == app.lib_index:
            fill_rect_rounded(renderer, _sx(10), y, SW - _sx(20), row_h - _sy(4), COL_MENU_SEL_BG)
        color = COL_ACCENT if bi == app.lib_index else COL_TEXT
        is_continue = continue_filename is not None and book["filename"] == continue_filename
        # v0.1.133 BUG FIX: U+25B6 (BLACK RIGHT-POINTING TRIANGLE) is NOT
        # in the bundled Liberation Sans font (assets/font.ttf) -- Kaleb
        # reported the Continue Reading marker rendering blank. Confirmed
        # via fontTools cmap check, not present. Checked the WHOLE prefix
        # set while fixing this and found finished_prefix's U+2713 (CHECK
        # MARK) is ALSO missing from the same font -- same bug, just not
        # yet reported. pin_prefix's U+2665 (HEART) IS present, unchanged.
        # Replaced both with glyphs confirmed present via cmap AND
        # visually verified by rasterizing with the actual bundled font
        # (not just "present in cmap" -- confirmed they draw a real
        # glyph, not an empty/placeholder outline):
        #   continue: U+25B6 -> U+25BA (BLACK RIGHT-POINTING POINTER, ►)
        #             same solid-right-triangle meaning, closest visual
        #             match to what was intended.
        #   finished: U+2713 -> U+221A (SQUARE ROOT, √) -- common
        #             checkmark substitute in fonts lacking a true check
        #             glyph; reads clearly as "done" at this size.
        # v0.1.150: finished indicator restored to the originally-intended
        # U+2713 (real CHECK MARK, ✓) now that the bundled font is Inter,
        # which has it -- re-verified via TTF_RenderUTF8_Blended (not
        # just cmap presence) that it rasterizes a real, non-empty glyph
        # before switching back. The √ compromise above was specifically
        # a Liberation Sans limitation, not a permanent design choice.
        # v26.07.09.02: status icons (resume/pin/finished) moved out of
        # the title text and into a fixed-width left gutter (icon_gutter_w,
        # computed once above the loop). Previously these were plain text
        # prepended to the title string, which meant the title's fit
        # budget shrank or grew row-by-row depending on which icons that
        # particular book happened to have -- titles didn't line up
        # visually, and the v0.1.128 fix above had to reserve THIS row's
        # exact icon width out of THIS row's title budget. Now every row
        # reserves the SAME fixed gutter regardless of which icons (if
        # any) it actually shows, so titles start at the same x on every
        # row and the reserved-width math below only has to account for
        # the suffix, not icons.
        icons_str = ""
        if is_continue:
            icons_str += "\u25ba"  # unambiguous "resume here" marker,
                                    # leftmost so it reads before pin/finished
        if book["filename"] in app.pinned:
            icons_str += ("\u2665" if not icons_str else " \u2665")
        if book["filename"] in app.finished:
            icons_str += ("\u2713" if not icons_str else " \u2713")
        suffix = ""
        if app.lib_sort_mode == "author" and book.get("author"):
            # v0.1.128: cap the author fragment itself (not just the
            # overall reserved width below) -- real book metadata here is
            # always short ("WATCHTOWER" for every JW epub on hand), but
            # nothing stops some other source's metadata from being a
            # long co-author list, and an uncapped author name could
            # alone exceed the row before the title/Continue Reading
            # budgeting below even gets a say.
            author_fitted = _fit_text(app.fonts.ui_body, book["author"], row_max_w // 3)
            suffix += f"  \u2014 {author_fitted}"
        # v0.1.127: literal "Continue Reading" replaces the old percentage
        # suffix, and ONLY on this one row -- every other book's row has
        # no progress indicator at all anymore.
        if is_continue:
            suffix += "  Continue Reading"
        if app.lib_sort_mode == "last_read":
            rel = _relative_time(_book_last_read_ts(book))
            if rel:
                suffix += f"  ({rel})"
        # v0.1.128: Kaleb asked about large Font Sizes -- measured real
        # widths with the bundled font and found _fit_text() truncating
        # the whole "prefix+title+suffix" line from the END, which at
        # 28pt/32pt with a realistic book title silently ate "Continue
        # Reading" itself (or the author/relative-time suffix) instead of
        # the title. Fix: reserve the prefix+suffix width first, fit ONLY
        # the title into whatever's left, then reassemble -- the marker
        # and "Continue Reading"/author/relative-time now always survive
        # in full at every Font Size; if anything has to give, it's the
        # title getting an ellipsis, never the suffix.
        suffix_w = text_width(app.fonts.ui_body, suffix)
        icon_w = (text_width(app.fonts.ui_body, icons_str) + _sx(10)) if icons_str else 0
        title_budget = max(_sx(40), row_max_w - icon_w - suffix_w)
        fitted_title = _fit_text(app.fonts.ui_body, book["title"], title_budget)
        title_line = fitted_title + suffix
        # v0.1.125: the continue-book row also gets its own accent color
        # (unless it's ALSO the current selection highlight, which
        # already gets COL_ACCENT) so the marker reads clearly even at
        # the smallest Font Size step where the glyph itself is tiny.
        if is_continue and bi != app.lib_index:
            color = COL_ACCENT
        if icons_str:
            render_text(renderer, app.fonts.ui_body, icons_str, color, _sx(24), y + _sy(8))
        render_text(renderer, app.fonts.ui_body, title_line, color, _sx(24) + icon_w, y + _sy(8))

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
        _draw_status_bar(renderer, app.fonts, app.status_msg, COL_WARNING,
                          SH - _sy(hint_height(app.fonts)))

    # v26.07.09.02: X Pin and SELECT Finished dropped from this bar (was
    # 8-9 shortcuts, often wrapping to 2+ lines at larger Font Sizes).
    # X and SELECT still work exactly as before -- unchanged -- and both
    # actions are now ALSO reachable via the Library Menu (START) as
    # "Pin/Unpin Selected" and "Mark Finished/Unfinished", same pattern
    # as Delete Book. Sort keeps its bar shortcut (Y) since it's used
    # often enough to justify staying dual-access; Jump 10 stays too,
    # since it's a scroll aid, not a toggle, and doesn't fit the menu's
    # "configure" pattern the same way.
    lib_hint = "A Open  Y Sort  LEFT/RIGHT Jump 10  L/R Font Size  START Menu  B Quit"
    if DOWNLOAD_PLUGINS:
        lib_hint = "A Open  Y Sort  LEFT/RIGHT Jump 10  L/R Font Size  L2 Download  START Menu  B Quit"
    draw_hint(renderer, app.fonts, lib_hint)


def _draw_large_page_loading_screen(renderer, app, percent=None, message=None):
    """v26.07.09.17/.19: centered loading message shown before
    draw_reader() commits to building (or disk-loading) a genuinely
    expensive page. percent (0.0-1.0), if given, appends a live "NN%" --
    added after Kaleb's on-device test: a flat, unmoving message across
    several real seconds reads as "did this break?" without one. message
    lets the disk-cache-load path (App._load_wrap_from_disk(), a single
    fast-ish but non-trivial file read -- also flagged by Kaleb as long
    enough to want feedback) show its own wording instead of implying a
    fresh computation is happening.
    v26.07.10.03: appends the cycling thinking face via
    _kaomoji_for_status() whenever this screen is actually showing
    progress (percent given) -- every wording variant used here
    ("Rendering...", "Pre-rendering...", "Loading cached page...")
    starts with a word _kaomoji_for_status() already matches."""
    font = app.fonts.ui_heading
    msg = message or "Rendering large page..."
    if percent is not None:
        msg = f"{msg}  {int(percent * 100)}%"
        msg = _kaomoji_for_status(msg)
    w = text_width(font, msg)
    x = max(_sx(20), (SW - w) // 2)
    y = (SH - TTF.TTF_FontHeight(font)) // 2
    render_text(renderer, font, msg, COL_TEXT, x, y)


def draw_reader(renderer, app):
    fill_rect(renderer, 0, 0, SW, SH, COL_BG)

    # v26.07.09.17: for the (rare) case where the page about to be built
    # is expensive enough that _ensure_page_built() below will take a
    # real, felt amount of time -- show a loading message and present it
    # FIRST, so the person gets feedback instead of an apparent freeze.
    # This can't move the actual work to a background thread (see
    # _ensure_page_built()'s v0.1.69 comment: _wrap() calls into SDL_ttf,
    # and calling SDL_ttf off the main thread has never been verified
    # safe on this hardware) -- the wrap itself stays synchronous, this
    # just adds visible feedback around it. Threshold picked from real
    # measurement across 4 books (506 sampled pages): median page is
    # ~5.6K characters, 90th percentile ~44K -- only genuine outlier
    # pages (2% of sampled pages) exceed 100K, so this can't flash on
    # ordinary reading, only the pages that actually need it.
    key = app.state.current_file
    needs_build = app.doc and (key != app._page_cache_key or app.state.current_anchor is not None)
    if needs_build:
        wrap_key = (key, app.fonts.size_index)
        if wrap_key not in app._wrapped_cache:
            # v26.07.09.18: check the on-disk extreme-page cache before
            # deciding a fresh wrap is needed at all -- if this exact
            # (book, page, font size) was already wrapped once before
            # (even in a previous session), load it straight into RAM
            # instead of redoing the wrap. See App._load_wrap_from_disk()/
            # _save_wrap_to_disk() and WRAP_CACHE_DIR's module-level
            # comment for scope/threshold.
            # v26.07.09.19: this disk read is itself non-trivial on real
            # hardware (Kaleb's on-device report: ~4s for a 6MB file) --
            # show a loading message for THIS path too, distinct wording
            # ("Loading cached page...") since it's not doing a fresh
            # computation, just reading one back.
            # v26.07.09.22: upgraded from a static message to a live
            # elapsed-seconds counter -- see
            # App._load_wrap_from_disk_with_progress()'s docstring for why
            # this is safe to background (pickle.load()/file I/O never
            # touches SDL_ttf, unlike _wrap() itself).
            if os.path.isfile(app._wrap_cache_path(key)):
                _disk_loaded = app._load_wrap_from_disk_with_progress(renderer, key)
            else:
                _disk_loaded = None
            if _disk_loaded is not None:
                app._wrapped_cache_put(wrap_key, _disk_loaded)
        if wrap_key not in app._wrapped_cache:
            cached = app._page_text_cache.get(key)
            if cached is not None:
                peek_text = cached[0]
            else:
                try:
                    page_result = app.doc.get_page(key)
                    app._page_text_cache_put(key, page_result)
                    peek_text = page_result[0]
                except Exception:
                    peek_text = ""
            if len(peek_text) > LARGE_PAGE_LOADING_THRESHOLD:
                # v26.07.10.03: if this exact page is sitting in
                # _extreme_page_queue (either from the proactive
                # book-open scan, or re-queued after a B/L2/R2 bail-out
                # -- see _handle_wrap_abort()), say so, with its
                # position, instead of a plain "Rendering..." that gives
                # no sense of whether background progress has been
                # happening. Purely informational -- this frame still
                # goes on to call _ensure_page_built() below either way,
                # same as always.
                if key in app._extreme_page_queue:
                    _qpos = app._extreme_page_queue.index(key)
                    _qmsg = ("Rendering large page... (queued, next up)" if _qpos == 0
                             else f"Rendering large page... (queued, {_qpos} ahead)")
                    _draw_large_page_loading_screen(renderer, app, message=_qmsg)
                else:
                    _draw_large_page_loading_screen(renderer, app)
                SDL.SDL_RenderPresent(renderer)
    elif app._extreme_page_queue:
        # v26.07.09.21: only touch the background pre-render queue when
        # the CURRENTLY-viewed page didn't itself need any work this
        # frame -- never delay the person's own navigation to do
        # proactive work for a page they haven't asked for yet. One
        # candidate per draw_reader() call (not the whole queue at once)
        # so this can't itself become a multi-page synchronous stall.
        href = app._extreme_page_queue.pop(0)
        if not os.path.isfile(app._wrap_cache_path(href)):
            app._prerender_one_extreme_page(renderer, href)

    app._ensure_page_built(renderer)

    body_top, line_h, body_rows = _reader_body_layout(app.fonts)

    visible_spans = app.visible_span_indices(line_h, body_rows)
    if visible_spans and app.selected_span not in visible_spans:
        app.selected_span = visible_spans[0]

    row = 0   # visual screen-rows consumed so far (drives the y pixel offset
              # and the loop's exit condition against body_rows)
    li = app.scroll   # which _lines entry we're about to draw -- advances by
                       # exactly 1 per line regardless of how many visual
                       # rows that line ends up consuming on screen
    content_drawn = False  # v0.1.111: true once anything NON-BLANK has
                            # actually been drawn on this page. Needed
                            # because the "first thing on the page always
                            # draws" exemption below used to key off
                            # row==0 literally -- but a page can legitimately
                            # start with one or more blank/whitespace-only
                            # _lines[] entries (epub_engine emits a real
                            # "" line for any whitespace-only paragraph,
                            # e.g. the stray text nodes HTML leaves around
                            # a block-level <img> -- confirmed via
                            # g_E_201507.epub's cover.xhtml: get_page()
                            # returns " \n [IMG]\n \n ", which _wrap()
                            # splits into _lines = ["", "[IMG]", "", ""]).
                            # With row==0 taken by that leading blank line,
                            # the image lands at row==1, the exemption no
                            # longer applies, and a portrait cover's
                            # box_rows (up to IMG_BOX_ROWS_PORTRAIT=20) can
                            # push row+box_rows past body_rows -- so the
                            # loop broke BEFORE ever drawing the image,
                            # leaving the page completely blank until a
                            # page-turn advanced scroll past the blank
                            # line (Kaleb: "renders immediately but...
                            # cutting it off... like a text line below").
                            # Tracking real content instead of raw row
                            # count means any number of leading blank
                            # lines no longer defeats the exemption.
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
                content_drawn = True
                row += 1
                li += 1
                continue
            _, i, _, _ = app._combined_spans[img_span_idx]
            image_span = app._images[i]
            box_rows = app._image_box_rows(image_span, line_h, body_rows)
            # If this image wouldn't fully fit in what's left of the
            # screen, stop the page HERE instead of drawing it and
            # letting it overflow past the bottom (previously: an image
            # near the bottom of a page rendered cropped -- "half the
            # image" -- because nothing checked whether its box would fit
            # before drawing). If nothing real has been drawn on this
            # page yet (content_drawn is False -- see its definition
            # above), this is effectively the first thing on the page
            # even if row > 0 because of leading blank lines, so draw it
            # regardless (an image taller than the whole body is a
            # degenerate case, but still better shown-clipped than never
            # shown at all).
            if content_drawn and row + box_rows > body_rows:
                break
            box_h = line_h * box_rows
            box_w = SW - _sx(40)
            entry = app.get_image_texture(renderer, image_span)
            is_selected = (img_span_idx == app.selected_span)
            border_color = COL_LINK_SEL if is_selected else COL_DIM
            # v0.1.83 fix: the image used to be scaled to fit the FULL
            # box_w x box_h, while the selection border below is drawn
            # INSET from that box (the panel is inset by pad_y=_sy(4) on
            # each side, border a couple px outside the panel). Most JW
            # photos are close to 16:9 -- the same ratio as
            # ImageLoader.TARGET_BOX_W/H -- so at many font sizes the
            # scaled image's height (dh) landed right at or past box_h,
            # visibly overlapping/crossing the border line instead of
            # sitting cleanly inside it (confirmed by Kaleb across
            # "Enjoy Life Forever"/"Courage" at multiple font sizes).
            # Fix: scale against the SAME inset region the panel/border
            # actually occupy, so there's always a real margin between
            # the image edge and the border, at any font size.
            pad_x, pad_y = _sx(4), _sy(IMG_PAD_Y)
            avail_w = box_w - 2 * pad_x
            avail_h = box_h - 2 * pad_y
            if entry and entry != "error":
                tex, iw, ih, is_full, _buf = entry
                # scale to fit the inset box; allow upscale for small
                # thumbnails so layout is stable
                scale = min(avail_w / iw, avail_h / ih) if iw and ih else 1.0
                dw, dh = int(iw * scale), int(ih * scale)
                dx = _sx(20) + pad_x + (avail_w - dw) // 2
                # v0.1.97: top-align instead of vertically centering. A thin
                # banner (Courage/Enjoy Life Forever chapter-header strips)
                # keeps a much taller box than its own height needs (see
                # MIN_IMG_BOX_ROWS), and centering split that leftover space
                # above AND below the image -- so text still didn't resume
                # until after all that dead space (Kaleb: "before text
                # continues"). Top-aligning puts all the leftover space
                # below the image instead, and the border-hugging logic
                # right below shrinks the visible box to match, so the
                # gap before the next line shrinks to just the normal
                # image/text spacing. box_h/box_rows (pagination) are
                # untouched -- only where the image/border draw INSIDE
                # that reserved space changes.
                dy = y + pad_y
                dst = Rect(dx, dy, dw, dh)
                SDL.SDL_RenderCopy(renderer, tex, None, ctypes.byref(dst))
                if not is_full:
                    render_text(renderer, app.fonts.ui_small, "improving...", COL_DIM,
                                dx, dy + dh + _sy(2))
                # v0.1.96: for a portrait/height-limited image (scaled down
                # because of avail_h, not avail_w -- confirmed via real
                # test images from the Courage epub that this always
                # leaves real leftover horizontal space, never a rounding
                # sliver), hug the selection border to the actual drawn
                # picture width instead of the full page width, so the
                # highlight doesn't surround a lot of empty side margin.
                # ONLY the border rect changes here -- box_w/box_h (what
                # _image_box_rows()/pagination/scroll actually use) are
                # untouched, so this can't desync page-turn/scroll math
                # from what's drawn. That exact desync (border drawn
                # against a different box than the one row-math assumed)
                # is the v0.1.83 bug class this is deliberately avoiding.
                if dh >= avail_h - 1 and dw < avail_w:
                    border_w = dw + 2 * pad_x
                    border_dx = dx - pad_x
                else:
                    border_w = box_w
                    border_dx = _sx(18)
                # v0.1.97: mirror the above, but for HEIGHT -- a thin
                # banner is width-filled (dw ~= avail_w) but far shorter
                # than avail_h. Hug the border to the image's actual
                # height (now top-aligned via dy above) instead of the
                # full box_h, so the selection/panel box doesn't visually
                # surround a lot of empty space under a thin banner.
                if dw >= avail_w - 1 and dh < avail_h - 1:
                    border_h = dh + 2 * pad_y
                    border_dy = y
                else:
                    border_h = box_h - _sy(4)
                    border_dy = y + _sy(2)
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
                border_w = box_w
                border_dx = _sx(18)
                border_h = box_h - _sy(4)
                border_dy = y + _sy(2)
            if is_selected:
                # v0.1.132: rounded outline, Kaleb's request -- radius is
                # deliberately capped at min(pad_x, pad_y) (the existing
                # margin between this border and the actual image/panel
                # it surrounds), NOT the app-wide CORNER_RADIUS. That cap
                # is what guarantees the curve only ever dips into empty
                # margin and can never reveal a squared-off image corner
                # poking through -- see draw_rect_rounded_outline()'s
                # docstring. Doesn't touch dw/dh/box_w/box_h/pad_x/pad_y
                # or any of the sizing math above, purely how the
                # existing border rect gets drawn.
                img_border_radius = min(pad_x, pad_y)
                draw_rect_rounded_outline(renderer, border_dx, border_dy,
                                           border_w + _sx(4), border_h,
                                           border_color, img_border_radius)
            row += box_rows
            li += 1
            content_drawn = True
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
            content_drawn = True
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
        if line.strip():
            content_drawn = True
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
        _draw_status_bar(renderer, app.fonts, app.status_msg, COL_ACCENT,
                          SH - _sy(hint_height(app.fonts)))

    # v26.07.09.04: Immersive Mode hides this bar's TEXT/GRAPHICS only --
    # the reserved bottom margin body_rows accounts for via
    # _reader_body_layout() is completely untouched, so pagination can
    # never disagree with what's drawn (see that function's docstring
    # for the exact historical bug this sidesteps). X still opens the
    # Menu even with nothing drawn here.
    if not app.immersive_mode:
        draw_hint(renderer, app.fonts,
                  "D-PAD Scroll  A Follow  B Back  L/R Page  L2/R2 Chap  Y Fast x10  X Menu  START Bookmark")
                  # v26.07.09.03: "Select/Scroll" -> "Scroll" and "Chapter" ->
                  # "Chap" -- wording-only trim for a bit of extra width
                  # headroom at 21pt+ (still wraps to 2 lines there, same as
                  # before -- this screen's bar was never actually 3+ lines
                  # or overflowing, unlike the old Library bar; every item
                  # here is a core reading control, not a toggle/setting, so
                  # nothing was moved into the Menu).


IMGVIEW_ZOOM_STEP = 1.15       # multiplicative zoom per L/R press
IMGVIEW_PAN_STEP_FRAC = 0.14   # fraction of the visible crop moved per D-pad
                                # press. No auto-repeat-while-held exists in
                                # this app's input model (SDL_JOYBUTTONDOWN
                                # discrete events only), so this is a
                                # per-press step, not a scroll rate. Kaleb
                                # confirmed keeping 0.14 (not dropping to
                                # 0.10-0.12) after discussing the tradeoff.


def draw_image_view(renderer, app):
    """v0.1.124: fullscreen Image Maximize Mode. v0.1.129 fix: the image
    now fills exactly the space ABOVE the hint bar (SW x viewport_h, see
    App._imgview_viewport_h()), not the full SW x SH with the hint bar
    simply drawn on top -- Kaleb's bug report: hint_height() varies with
    Font Size (can wrap to 2-3 lines at larger sizes), so a taller hint
    bar was silently covering more of the image's bottom than the old
    full-screen zoom/pan math ever accounted for. Reuses
    App.get_image_texture() unchanged, so it shares the exact same
    decode/cache/upgrade pipeline as the inline reader."""
    fill_rect(renderer, 0, 0, SW, SH, COL_BG)
    image_span = app._imgview_span
    if image_span is None:
        draw_hint(renderer, app.fonts, "B Back", calibration=_IMGVIEW_HINT_CALIBRATION)
        return

    vh = app._imgview_viewport_h()

    entry = app.get_image_texture(renderer, image_span, full_native=True)
    if not entry or entry == "error":
        msg = "Image failed to load" if entry == "error" else "Loading image..."
        color = COL_DIM
        tw = text_width(app.fonts.ui_small, msg)
        render_text(renderer, app.fonts.ui_small, msg, color,
                    (SW - tw) // 2, vh // 2)
        draw_hint(renderer, app.fonts, "B Back", calibration=_IMGVIEW_HINT_CALIBRATION)
        return

    tex, iw, ih, is_full, _buf = entry
    # Reset (or re-clamp, if the texture upgraded from a thumb to full-res
    # mid-view -- rare with native_jpeg's near-instant decode, but
    # mini_jpeg's progressive fallback can still land a low-res band
    # first) against whatever dims we actually have right now.
    if app._imgview_pending_reset or (iw, ih) != (app._imgview_native_w, app._imgview_native_h):
        if app._imgview_pending_reset:
            app._imgview_reset(iw, ih)
        else:
            # dims changed after the initial reset (thumb -> full-res
            # upgrade) -- rescale the existing pan/zoom proportionally
            # instead of re-centering, so an in-progress zoom/pan isn't
            # jarringly reset out from under the user.
            old_w = max(1, app._imgview_native_w)
            old_h = max(1, app._imgview_native_h)
            scale_x = iw / old_w
            scale_y = ih / old_h
            app._imgview_native_w, app._imgview_native_h = iw, ih
            app._imgview_zoom_min = max(SW / iw, vh / ih) if iw and ih else 1.0
            app._imgview_zoom_max = max(app._imgview_zoom_min, 1.0)
            app._imgview_zoom = min(app._imgview_zoom_max,
                                     max(app._imgview_zoom_min, app._imgview_zoom))
            app._imgview_pan_x *= scale_x
            app._imgview_pan_y *= scale_y
            app._imgview_clamp_pan()

    crop_w = min(iw, SW / app._imgview_zoom)
    crop_h = min(ih, vh / app._imgview_zoom)
    src = Rect(int(app._imgview_pan_x), int(app._imgview_pan_y),
               max(1, int(crop_w)), max(1, int(crop_h)))
    dst = Rect(0, 0, SW, vh)
    SDL.SDL_RenderCopy(renderer, tex, ctypes.byref(src), ctypes.byref(dst))

    if not is_full:
        render_text(renderer, app.fonts.ui_small, "improving...", COL_DIM,
                    _sx(14), _sy(10))

    # v0.1.136: round the image's own bottom-left/right corners into the
    # hint bar's color, Kaleb's request (photo with red annotations) --
    # see _round_image_bottom_corners_to_hint()'s docstring. skip_top_corners=True
    # below because this already handles that exact junction from the
    # image side; the hint bar's own default corner treatment
    # (erase-to-COL_BG) would be wrong here specifically, since the
    # content directly above the hint bar on this screen is the image,
    # not COL_BG.
    _round_image_bottom_corners_to_hint(renderer, vh, IMG_MAXIMIZE_CORNER_RADIUS)
    draw_hint(renderer, app.fonts,
              "D-PAD Pan  L/R Zoom Out/In  B Back", skip_top_corners=True,
              calibration=_IMGVIEW_HINT_CALIBRATION)


def draw_splash(renderer, app):
    """v26.07.10.05/.06: boot splash (Kaleb's request) -- FACE_MENU_LOGO
    above SPLASH_TITLE (spells left-to-right over SPLASH_TYPE_SECONDS),
    then SPLASH_SUBTITLE near the bottom (spells left-to-right over the
    following SPLASH_SUBTITLE_TYPE_SECONDS), then everything holds for
    SPLASH_HOLD_SECONDS before handing off to app._splash_dest_screen
    (whatever App.__init__ actually resolved -- Library, or Reader if
    Open Last Book on Launch found one). Skippable via START/A/B --
    see handle_button()'s SCREEN_SPLASH branch.

    Both typed strings are drawn at a FIXED x, computed once from each
    string's OWN full final width, so the block is centered as if
    already complete rather than re-centering every frame as it grows
    -- a recentering prefix visibly drifts/jitters instead of reading
    as text being typed in place (confirmed while building the title
    animation last session).

    Delegates straight to draw_library()/draw_reader() once finished,
    rather than just flipping app.screen and returning blank, so this
    frame doesn't paint one empty frame before the real screen appears."""
    elapsed = time.time() - app._splash_start
    if elapsed >= SPLASH_TOTAL_SECONDS:
        app.screen = app._splash_dest_screen
        if app.screen == SCREEN_READER:
            draw_reader(renderer, app)
        else:
            draw_library(renderer, app)
        return

    fill_rect(renderer, 0, 0, SW, SH, COL_BG)
    face_font = app.fonts.ui_heading
    title_font = app.fonts.splash_title  # v26.07.10.07: 50% bigger than
                    # ui_heading (Kaleb's request) -- face above it
                    # stays at ui_heading, unchanged.
    line_gap = _sy(10)

    face_w = text_width(face_font, FACE_MENU_LOGO)
    title_w = text_width(title_font, SPLASH_TITLE)
    face_h = TTF.TTF_FontHeight(face_font)
    title_h = TTF.TTF_FontHeight(title_font)
    block_h = face_h + title_h + line_gap
    top_y = (SH - block_h) // 2

    face_x = max(_sx(10), (SW - face_w) // 2)
    render_text(renderer, face_font, FACE_MENU_LOGO, COL_ACCENT, face_x, top_y)

    if elapsed < SPLASH_TITLE_END:
        reveal_n = int(len(SPLASH_TITLE) * (elapsed / SPLASH_TYPE_SECONDS))
        reveal_n = max(0, min(len(SPLASH_TITLE), reveal_n))
    else:
        reveal_n = len(SPLASH_TITLE)
    visible_title = SPLASH_TITLE[:reveal_n]

    title_x = max(_sx(10), (SW - title_w) // 2)  # fixed start, based on FULL text width
    title_y = top_y + face_h + line_gap
    if visible_title:
        render_text(renderer, title_font, visible_title, COL_ACCENT, title_x, title_y)

    # v26.07.10.06: subtitle, near the bottom, only starts typing once
    # the title is fully spelled (elapsed >= SPLASH_TITLE_END) --
    # smaller font (ui_body) since the full string is much longer than
    # the title and needs to comfortably fit SW at every Font Size.
    if elapsed >= SPLASH_TITLE_END:
        sub_font = app.fonts.ui_body
        sub_w = text_width(sub_font, SPLASH_SUBTITLE)
        if elapsed < SPLASH_SUBTITLE_END:
            sub_frac = (elapsed - SPLASH_TITLE_END) / SPLASH_SUBTITLE_TYPE_SECONDS
            sub_reveal_n = int(len(SPLASH_SUBTITLE) * sub_frac)
            sub_reveal_n = max(0, min(len(SPLASH_SUBTITLE), sub_reveal_n))
        else:
            sub_reveal_n = len(SPLASH_SUBTITLE)
        visible_sub = SPLASH_SUBTITLE[:sub_reveal_n]
        sub_x = max(_sx(10), (SW - sub_w) // 2)  # fixed start, based on FULL subtitle width
        sub_y = SH - _sy(hint_height(app.fonts)) - TTF.TTF_FontHeight(sub_font) - _sy(24)
        if visible_sub:
            render_text(renderer, sub_font, visible_sub, COL_ACCENT, sub_x, sub_y)


def draw_menu(renderer, app):
    draw_reader(renderer, app)
    overlay_w = _sx(360)
    fill_rect_rounded(renderer, SW - overlay_w, 0, overlay_w, SH - _sy(hint_height(app.fonts)), COL_PANEL)
    # v26.07.10.04: small logo (Kaleb's request) instead of a plain
    # "MENU" label -- face on its own line, "PICO READER" below it,
    # both centered in the overlay's width. Uses ui_heading (already
    # proven to fit this 360px-wide overlay via the old "MENU" label at
    # the same font) rather than a bigger font, since a literally larger
    # face risks overflowing this narrow sidebar at large Font Size
    # settings -- centered + same size as before is the safe "nice and
    # large relative to the menu items below it" reading of the request.
    _logo_font = app.fonts.ui_heading
    _logo_y = _sy(16)
    _face_w = text_width(_logo_font, FACE_MENU_LOGO)
    render_text(renderer, _logo_font, FACE_MENU_LOGO, COL_ACCENT,
                SW - overlay_w + max(_sx(10), (overlay_w - _face_w) // 2), _logo_y)
    _title_y = _logo_y + TTF.TTF_FontHeight(_logo_font) + _sy(2)
    _title_w = text_width(_logo_font, "PICO READER")
    render_text(renderer, _logo_font, "PICO READER", COL_ACCENT,
                SW - overlay_w + max(_sx(10), (overlay_w - _title_w) // 2), _title_y)
    row_h = _row_h(app.fonts.ui_body)
    top = _title_y + TTF.TTF_FontHeight(_logo_font) + _sy(14)
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
        label = item
        if item == "Immersive Mode":
            label = f"Immersive Mode: {'On' if app.immersive_mode else 'Off'}"
        if mi == app.menu_index:
            fill_rect_rounded(renderer, SW - overlay_w + _sx(10), y, overlay_w - _sx(20), row_h - _sy(6), COL_MENU_SEL_BG)
        color = COL_ACCENT if mi == app.menu_index else COL_TEXT
        render_text(renderer, app.fonts.ui_body, _fit_text(app.fonts.ui_body, label, item_max_w),
                    color, SW - overlay_w + _sx(24), y + _sy(8))
    draw_hint(renderer, app.fonts, "UP/DOWN Select   A Confirm   B Close")


def draw_toc(renderer, app):
    fill_rect(renderer, 0, 0, SW, SH, COL_BG)
    render_text(renderer, app.fonts.ui_heading, "CHAPTERS", COL_ACCENT, _sx(20), _sy(16))
    row_h = _row_h(app.fonts.ui_body, pad=10)  # v0.1.153: was 14, tightened
                        # to match the new default (see _row_h() docstring)
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


HELP_PARAGRAPHS = [
    # v0.1.155: Kaleb: "this code thing is confusing" -- plain-language
    # explanation of the two ways to find a publication, shown via a new
    # X-Help overlay from Sources/Categories/Browse. Examples use pub
    # codes already verified live against the real API (wcg, nwt), not
    # guessed -- see main.py's AI NOTES for the verification method.
    # Each entry is (text, is_heading) -- explicit, not guessed from
    # capitalization, since a heading like "SEARCH (Y button)" isn't
    # actually all-uppercase itself.
    ("SEARCH (Y button)", True),
    ("Type any word from a title -- for example \"courage\" -- to search "
     "within the current category, or across everything if this source "
     "doesn't use categories.", False),
    ("PUB CODE (SELECT button)", True),
    ("A separate, always-available shortcut for when you already know "
     "exactly which publication you want -- JW.org's own internal short "
     "name for it.", False),
    ("Where to find it: open the publication on wol.jw.org -- the LAST "
     "part of that page's web address is the code.", False),
    ("Example: wol.jw.org/en/wol/publication/r1/lp-e/wcg  ->  code is "
     "\"wcg\" (Walk Courageously With God).", False),
    ("Example: \"nwt\" is the code for the New World Translation (the "
     "Bible).", False),
    ("For a monthly issue (Watchtower, Awake!), add the date after the "
     "code, as YYYYMM -- for example: wp 202601", False),
]


def draw_download_help(renderer, app):
    fill_rect(renderer, 0, 0, SW, SH, COL_BG)
    heading_y = _sy(16)
    render_text(renderer, app.fonts.ui_heading, "SEARCH & PUB CODE HELP", COL_ACCENT,
                _sx(20), heading_y)
    top = heading_y + TTF.TTF_FontHeight(app.fonts.ui_heading) + _sy(14)
    max_w = SW - _sx(48)
    font = app.fonts.ui_body
    line_h = TTF.TTF_FontHeight(font) + _sy(6)

    # Flatten paragraphs into wrapped lines, carrying each source
    # paragraph's is_heading flag onto every wrapped line it produces.
    all_lines = []  # list of (text, is_heading)
    for para, is_heading in HELP_PARAGRAPHS:
        wrapped = _wrap_hint_text_unbounded(font, para, max_w) or [para]
        for line in wrapped:
            all_lines.append((line, is_heading))

    visible = max(1, (SH - top - _sy(hint_height(app.fonts))) // line_h)
    total = len(all_lines)
    max_scroll = max(0, total - visible)
    app.dl_help_scroll = max(0, min(getattr(app, "dl_help_scroll", 0), max_scroll))

    y = top
    for i in range(app.dl_help_scroll, min(total, app.dl_help_scroll + visible)):
        text, is_heading = all_lines[i]
        color = COL_ACCENT if is_heading else COL_TEXT
        render_text(renderer, font, text, color, _sx(24), y)
        y += line_h

    hint = "UP/DOWN Scroll   B Back" if max_scroll > 0 else "B Back"
    draw_hint(renderer, app.fonts, hint)


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
    hint_parts = ["UP/DOWN Select", "L/R Jump 10"]
    if getattr(app.dl_plugin, "SUPPORTS_SEARCH", False):
        hint_parts.append("Y Search")
    if getattr(app.dl_plugin, "SUPPORTS_MANUAL_CODE", False):
        hint_parts.append("SELECT Code")
    hint_parts += ["A Open", "X Help", "B Back"]
    draw_hint(renderer, app.fonts, "   ".join(hint_parts))


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
    draw_hint(renderer, app.fonts, "UP/DOWN Select   A Open   X Help   B Back")


def draw_download_video_sources(renderer, app):
    """v0.1.110: the small picker that replaced the four separate Library
    Menu video entries -- reached via Download Books > JW > Videos (the
    CATEGORY_VIDEOS pseudo-category). Same simple list pattern as
    draw_download_sources() above."""
    fill_rect(renderer, 0, 0, SW, SH, COL_BG)
    heading_y = _sy(16)
    render_text(renderer, app.fonts.ui_heading, "VIDEOS", COL_ACCENT, _sx(20), heading_y)
    row_h = _row_h(app.fonts.ui_body)
    top = heading_y + TTF.TTF_FontHeight(app.fonts.ui_heading) + _sy(14)
    n_items = len(VIDEO_SOURCE_ITEMS)
    visible = max(1, (SH - top - _sy(hint_height(app.fonts))) // row_h)
    start = max(0, min(app.video_source_index - visible // 2, max(0, n_items - visible)))
    for i in range(start, min(n_items, start + visible)):
        y = top + (i - start) * row_h
        if i == app.video_source_index:
            fill_rect_rounded(renderer, _sx(10), y, SW - _sx(20), row_h - _sy(4), COL_MENU_SEL_BG)
        color = COL_ACCENT if i == app.video_source_index else COL_TEXT
        render_text(renderer, app.fonts.ui_body, VIDEO_SOURCE_ITEMS[i], color, _sx(24), y + _sy(10))
    draw_hint(renderer, app.fonts, "UP/DOWN Select   A Open   B Back")


def draw_download_audio_sources(renderer, app):
    """v26.07.10.01: audio equivalent of draw_download_video_sources() --
    reached via Download Books > JW > Audio (CATEGORY_AUDIO). Identical
    layout, just AUDIO_SOURCE_ITEMS/audio_source_index instead of
    VIDEO_SOURCE_ITEMS/video_source_index."""
    fill_rect(renderer, 0, 0, SW, SH, COL_BG)
    heading_y = _sy(16)
    render_text(renderer, app.fonts.ui_heading, "AUDIO", COL_ACCENT, _sx(20), heading_y)
    row_h = _row_h(app.fonts.ui_body)
    top = heading_y + TTF.TTF_FontHeight(app.fonts.ui_heading) + _sy(14)
    n_items = len(AUDIO_SOURCE_ITEMS)
    visible = max(1, (SH - top - _sy(hint_height(app.fonts))) // row_h)
    start = max(0, min(app.audio_source_index - visible // 2, max(0, n_items - visible)))
    for i in range(start, min(n_items, start + visible)):
        y = top + (i - start) * row_h
        if i == app.audio_source_index:
            fill_rect_rounded(renderer, _sx(10), y, SW - _sx(20), row_h - _sy(4), COL_MENU_SEL_BG)
        color = COL_ACCENT if i == app.audio_source_index else COL_TEXT
        render_text(renderer, app.fonts.ui_body, AUDIO_SOURCE_ITEMS[i], color, _sx(24), y + _sy(10))
    draw_hint(renderer, app.fonts, "UP/DOWN Select   A Open   B Back")


def draw_download_audio_books(renderer, app):
    """v26.07.10.01: Bible-book sub-picker for AUDIO_SOURCES entries
    marked "books": True (currently just "Bible Reading Audio (NWT)") --
    same simple list pattern as the other pickers, driven by
    jw_fetch.BIBLE_BOOKS (66 fixed entries, see that table's own comment
    for why it's safe to hardcode)."""
    fill_rect(renderer, 0, 0, SW, SH, COL_BG)
    heading_y = _sy(16)
    render_text(renderer, app.fonts.ui_heading, "BIBLE BOOK", COL_ACCENT, _sx(20), heading_y)
    row_h = _row_h(app.fonts.ui_body)
    top = heading_y + TTF.TTF_FontHeight(app.fonts.ui_heading) + _sy(14)
    books = getattr(JW_PLUGIN, "BIBLE_BOOKS", [])
    n_items = len(books)
    visible = max(1, (SH - top - _sy(hint_height(app.fonts))) // row_h)
    start = max(0, min(app.audio_book_index - visible // 2, max(0, n_items - visible)))
    for i in range(start, min(n_items, start + visible)):
        y = top + (i - start) * row_h
        if i == app.audio_book_index:
            fill_rect_rounded(renderer, _sx(10), y, SW - _sx(20), row_h - _sy(4), COL_MENU_SEL_BG)
        color = COL_ACCENT if i == app.audio_book_index else COL_TEXT
        _, name = books[i]
        render_text(renderer, app.fonts.ui_body, name, color, _sx(24), y + _sy(10))
    draw_hint(renderer, app.fonts, "UP/DOWN Select   A Open   B Back")


def draw_download_browse(renderer, app):
    fill_rect(renderer, 0, 0, SW, SH, COL_BG)
    name = ("JW Videos" if app.dl_is_video else
             "JW Audio" if app.dl_is_audio else
             (getattr(app.dl_plugin, "PLUGIN_NAME", "Download") if app.dl_plugin else "Download"))
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
    row_h = title_h + sub_h + _sy(14)  # v0.1.153: was +_sy(20) -- same
                        # DejaVu-metrics retune as _row_h()'s default pad
                        # (this two-line row predates/bypasses _row_h(),
                        # so it needed its own matching adjustment).
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
        whats_new = getattr(app.dl_plugin, "CATEGORY_WHATS_NEW", None)
        msg = ("No new publications detected via RSS right now."
               if whats_new and app.dl_category == whats_new else "No results.")
        render_text(renderer, app.fonts.ui_body, msg, COL_DIM, _sx(24), top)
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
        _draw_status_bar(renderer, app.fonts, app.status_msg, COL_ACCENT,
                          SH - _sy(hint_height(app.fonts)))

    hint = "UP/DOWN Select   A Download   B Back"
    if app.dl_has_next or app.dl_page > 1:
        hint = "UP/DOWN Select   L/R Page   A Download   B Back"
    elif app.dl_items:
        # v0.1.88: no server-side pages to flip through, but L/R still do
        # something useful here -- jump 10 items locally -- so say so.
        hint = "UP/DOWN Select   L/R Jump 10   A Download   B Back"
    if app.dl_is_video:
        # v0.1.110: video mode has its own Y binding (client-side title
        # search, see App.search_video_items()) -- unrelated to the
        # underlying plugin's SUPPORTS_SEARCH/SUPPORTS_MANUAL_CODE flags.
        hint = hint.replace("B Back", "Y Search   B Back")
    elif app.dl_is_audio:
        # v26.07.10.01: audio mode has no search/manual-code binding of
        # its own (both AUDIO_SOURCES entries are simple lists -- the
        # Study Edition source is a single resolved issue, the Bible
        # source is already narrowed to one book by the time you're
        # here) -- plain hint, and specifically skips the
        # SUPPORTS_SEARCH/SUPPORTS_MANUAL_CODE checks below, which would
        # otherwise incorrectly fire off JW_PLUGIN's OWN flags (still
        # set on app.dl_plugin) even though neither applies to this
        # screen the way it does for the EPUB browse path.
        pass
    elif getattr(app.dl_plugin, "SUPPORTS_SEARCH", False):
        hint = hint.replace("B Back", "Y Search   B Back")
    elif getattr(app.dl_plugin, "SUPPORTS_CATEGORIES", False):
        # v0.1.156 BUG FIX: this branch was MISSING entirely -- the hint
        # text fell straight through to the SUPPORTS_MANUAL_CODE branch
        # below and said "Y Enter Code", even though handle_button()'s
        # own elif chain checks SUPPORTS_CATEGORIES first and Y actually
        # opens a category-scoped title search instead. Confirmed via
        # direct simulation the hint and the real behavior had drifted
        # apart. Now matches what Y actually does.
        hint = hint.replace("B Back", "Y Search   B Back")
    if not app.dl_is_video and not app.dl_is_audio and getattr(app.dl_plugin, "SUPPORTS_MANUAL_CODE", False):
        # v0.1.156: SELECT (not Y -- see handle_button()'s SELECT branch
        # docstring) is now its own, always-reachable binding whenever a
        # plugin declares this, regardless of whether it ALSO supports
        # search/categories -- previously this and the categories-search
        # branch shared the single Y button via an elif chain, silently
        # shadowing one or the other.
        hint = hint.replace("B Back", "SELECT Code   B Back")
    hint = hint.replace("B Back", "X Help   B Back")
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
        if item == "Continue Reading":
            recent = app.most_recent_book()
            label = f"Continue: {recent['title']}" if recent else "Continue Reading (none yet)"
        if item == "Pin/Unpin Selected":
            tgt = app._menu_target_book
            if tgt:
                is_pinned = tgt["filename"] in app.pinned
                label = f"{'Unpin' if is_pinned else 'Pin'}: {tgt['title']}"
            else:
                label = "Pin/Unpin Selected"
        if item == "Mark Finished/Unfinished":
            tgt = app._menu_target_book
            if tgt:
                is_finished = tgt["filename"] in app.finished
                label = f"{'Mark Unfinished' if is_finished else 'Mark Finished'}: {tgt['title']}"
            else:
                label = "Mark Finished/Unfinished"
        if item == "Filter: Cycle":
            label = f"Filter: {LIBRARY_FILTER_LABELS[app.lib_filter_mode]}"
        armed_delete = False
        if item == "Delete Book":
            if app._menu_delete_armed:
                label = "Press A again to DELETE"
                armed_delete = True
            elif app._menu_target_book:
                label = f"Delete: {app._menu_target_book['title']}"
            else:
                label = "Delete Book"
        armed_clear = False
        if item == "Clear All Finished":
            n_finished = len(app.finished)
            if app._menu_clear_finished_armed:
                label = f"Press A again to clear {n_finished} mark" + ("s" if n_finished != 1 else "")
                armed_clear = True
            else:
                label = f"Clear All Finished ({n_finished})"
        armed_warning = armed_delete or armed_clear
        if armed_warning:
            fill_rect_rounded(renderer, SW - overlay_w + _sx(10), y, overlay_w - _sx(20), row_h - _sy(6), COL_WARNING)
        elif i == app.lib_menu_index:
            fill_rect_rounded(renderer, SW - overlay_w + _sx(10), y, overlay_w - _sx(20), row_h - _sy(6), COL_MENU_SEL_BG)
        color = COL_BG if armed_warning else (COL_ACCENT if i == app.lib_menu_index else COL_TEXT)
        render_text(renderer, app.fonts.ui_body, _fit_text(app.fonts.ui_body, label, item_max_w),
                    color, SW - overlay_w + _sx(20), y + _sy(8))
    draw_hint(renderer, app.fonts, "UP/DOWN Select   A Confirm   B Close")


def draw_bookmarks(renderer, app):
    fill_rect(renderer, 0, 0, SW, SH, COL_BG)
    bms = [b for b in get_bookmarks(app.current_book_path) if b.get("label") != "__lastpos__"]
    render_text(renderer, app.fonts.ui_heading,
                f"BOOKMARKS ({len(bms)}/{MAX_BOOKMARKS_PER_BOOK})", COL_ACCENT, _sx(20), _sy(16))
    # v0.1.131: was a fixed _sy(44), unlike every other list screen which
    # uses the shared _row_h() helper -- at large Font Size settings the
    # fixed height didn't grow with the text, so rows lost their vertical
    # centering (and risked clipping) exactly where it matters most.
    # _row_h()'s pad=20 default + the existing "y + _sy(8)" text offset
    # below already works out to equal padding above/below the text on
    # every other screen, so this makes Bookmarks consistent with that.
    row_h = _row_h(app.fonts.ui_body)
    top = _sy(70)
    if not bms:
        render_text(renderer, app.fonts.ui_body, "No bookmarks yet. Press START while reading.",
                    COL_DIM, _sx(24), top)
    for i, bm in enumerate(bms):
        y = top + i * row_h
        armed = (i == app._bookmark_delete_confirm_idx)
        if armed:
            fill_rect_rounded(renderer, _sx(10), y, SW - _sx(20), row_h - _sy(4), COL_WARNING)
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
    render_text(renderer, app.fonts.ui_heading, "SETTINGS", COL_ACCENT, _sx(20), _sy(16))

    # v26.07.09.05: this screen used to show a separate "info_lines"
    # block of static text ABOVE the action list (cache size, orphan
    # count, disk-cache ON/OFF, images ON/OFF, open-last-book ON/OFF,
    # backup count+timestamp) -- every one of those duplicated
    # information that's now folded directly into its corresponding
    # action's own label below (same pattern already used for Immersive
    # Mode's "On/Off" suffix and Pre-render's existing progress label).
    # Kaleb's request: the toggle/action row itself should show its own
    # state/stats, not a disconnected line elsewhere on screen. This also
    # directly shrinks the vertical space this screen needs, which is
    # what caused the real v0.1.54 overflow bug (info_lines + action
    # list together running off the bottom of the screen) -- removing
    # the duplicate block helps that, it doesn't just declutter.
    cache_size = format_bytes(image_cache_size_bytes())
    orphan_count = len(orphaned_bookmark_book_paths())
    backups = list_bookmark_backups()
    if backups:
        # filenames are bookmarks_backup_YYYYMMDD_HHMMSS.json
        ts_part = backups[0][len("bookmarks_backup_"):-len(".json")]
        try:
            latest_str = time.strftime("%b %d %H:%M",
                                        time.strptime(ts_part, "%Y%m%d_%H%M%S"))
        except ValueError:
            latest_str = "unknown time"
    else:
        latest_str = None

    row_h = _row_h(app.fonts.ui_body)
    top = _sy(60)
    action_max_w = SW - _sx(40)
    n_items = len(STORAGE_ACTIONS)
    # v0.1.54: windowed like Library/Chapters/Menu -- this list used to
    # draw every action unconditionally, which ran past the bottom of
    # the screen once info_lines + row_h both grew with Font Size
    # (confirmed via Kaleb's on-device screenshot: "Pre-render Book
    # Images" and "Back" were pushed off-screen with no way to reach
    # them). v26.07.09.05: info_lines is gone now (folded into action
    # labels above), so this has even more headroom than before.
    visible = max(1, (SH - top - _sy(hint_height(app.fonts))) // row_h)
    start = max(0, min(app.storage_index - visible // 2, max(0, n_items - visible)))
    for idx in range(start, min(n_items, start + visible)):
        action = STORAGE_ACTIONS[idx]
        # v0.1.122: checked BEFORE any drawing (highlight box included) --
        # unlike the Library Menu's existing "Download Books" hide, which
        # continues after the highlight box already drew, so a selection
        # landing on a hidden row there paints a blank highlighted rect.
        # Checking first avoids that here.
        if action == "Pre-render Book Images" and native_image is not None and native_image.available:
            continue
        ry = top + (idx - start) * row_h
        armed = (idx == app._storage_confirm_idx)
        if armed:
            fill_rect_rounded(renderer, _sx(10), ry, SW - _sx(20), row_h - _sy(4), COL_WARNING)
        elif idx == app.storage_index:
            fill_rect_rounded(renderer, _sx(10), ry, SW - _sx(20), row_h - _sy(4), COL_MENU_SEL_BG)
        color = COL_BG if armed else (COL_ACCENT if idx == app.storage_index else COL_TEXT)
        label = action
        if action == "Clear Image Cache":
            if app.doc is not None and app._book_id:
                book_size = format_bytes(book_cache_size_bytes(app._book_id))
                label = f"Clear Image Cache ({cache_size} total, {book_size} this book)"
            else:
                label = f"Clear Image Cache ({cache_size})"
        elif action == "Clean Up Orphaned Bookmarks":
            label = f"Clean Up Orphaned Bookmarks ({orphan_count} deleted book(s))"
        elif action == "Backup Bookmarks Now":
            label = (f"Backup Bookmarks Now (last: {latest_str})" if latest_str
                     else "Backup Bookmarks Now (no backups yet)")
        elif action == "Restore Latest Backup":
            label = (f"Restore Latest Backup ({len(backups)} available, latest {latest_str})"
                     if backups else "Restore Latest Backup (none available)")
        elif action == "Toggle Disk Cache (RAM-only mode)":
            state = "ON (cached to disk)" if app.disk_cache_enabled else "OFF (RAM-only)"
            label = f"Disk Cache: {state}"
        elif action == "Toggle Images (text-only mode)":
            state = "ON" if app.images_enabled else "OFF (text-only)"
            label = f"Images: {state}"
        elif action == "Toggle Open Last Book on Launch":
            state = "ON" if app.open_last_book_enabled else "OFF"
            label = f"Open Last Book on Launch: {state}"
        if action == "Pre-render Book Images":
            if app._prerender_active:
                done, total, scanning = app.prerender_progress()
                label = (f"Cancel Pre-render (scanning... {total} found)" if scanning
                         else f"Cancel Pre-render ({done}/{total})")
            elif app._prerender_total:
                done, total, _ = app.prerender_progress()
                label = f"Pre-render Book Images (last run: {done}/{total})"
        if armed:
            label = "Press A again to confirm, or B to cancel"
        # v26.07.09.14 BUG FIX (Kaleb's report -- selector "not centered"):
        # this used to be a fixed ry + _sy(10) offset regardless of
        # row_h, so as row_h grows with Font Size the text sits closer
        # and closer to the TOP of the highlight box instead of centered
        # in it -- same bug class draw_hint() already fixed properly
        # (v0.1.131) by centering the text block within the full bar
        # height rather than anchoring it to one edge.
        text_h = TTF.TTF_FontHeight(app.fonts.ui_body)
        text_y = ry + max(0, (row_h - _sy(4) - text_h) // 2)
        render_text(renderer, app.fonts.ui_body, _fit_text(app.fonts.ui_body, label, action_max_w),
                    color, _sx(24), text_y)

    if app.status_msg and time.time() < app.status_until:
        msg_y = top + min(visible, n_items) * row_h + _sy(20)
        line_h = TTF.TTF_FontHeight(app.fonts.ui_small) + _sy(6)
        for i, line in enumerate(_status_msg_lines(app.fonts, app.status_msg)):
            render_text(renderer, app.fonts.ui_small, line, COL_ACCENT, _sx(20), msg_y + i * line_h)

    draw_hint(renderer, app.fonts, "UP/DOWN Select   A Confirm   B Back")


# ============================================================
# Main loop
# ============================================================
def main():
    # v0.1.79: CPython's default GIL switch interval (5ms) turned out not
    # to be tight enough on the real ARM device -- Kaleb confirmed a real
    # background-decode stall (image loading, and worse, whole-book
    # pre-render) still froze ALL input for several seconds even after
    # the v0.1.78 cooperative time.sleep(0) yields added inside
    # mini_jpeg.py's hot loops. Those cooperative yields only offer the
    # GIL up at convenient points; they don't change how urgently
    # CPython actually forces a handoff between offers, which is what
    # setswitchinterval controls. Dropping it to 1ms (from the 5ms
    # default) makes the interpreter force that handoff five times more
    # often, giving the main thread's SDL_PollEvent/render loop far more
    # regular chances to run even while the decode thread is continuously
    # CPU-bound between yield points. This is a global interpreter
    # setting (affects all threads, not just image decode) but the cost
    # is a small constant amount of extra thread-switch bookkeeping --
    # negligible next to a multi-hundred-millisecond JPEG decode.
    sys.setswitchinterval(0.001)

    if SDL.SDL_Init(SDL_INIT_VIDEO | SDL_INIT_JOYSTICK) != 0:
        _boot_log(f"SDL_Init failed: {SDL.SDL_GetError()}\n")
        sys.exit(1)

    # v0.1.148: detect the real device resolution so the app's fixed
    # 720x720 internal canvas can letterbox/pillarbox onto other muOS
    # screens (640x480 RG28XX/RG35XX family, 720x480 RG34XX, 1024x768
    # TrimUI Brick, 1280x720 TrimUI Smart Pro -- confirmed groupings via
    # community.muos.dev). RGCubeXX-H (720x720) keeps the exact original
    # window path (no fullscreen flag, no scaling) so there is zero
    # regression risk on the primary dev device.
    disp_mode = SDL_DisplayMode()
    if SDL.SDL_GetDesktopDisplayMode(0, ctypes.byref(disp_mode)) == 0 and disp_mode.w > 0 and disp_mode.h > 0:
        DEV_W, DEV_H = disp_mode.w, disp_mode.h
    else:
        DEV_W, DEV_H = SW, SH  # detection failed -- fall back to native square

    _boot_log(f"Detected display: {DEV_W}x{DEV_H}\n")

    if (DEV_W, DEV_H) == (SW, SH):
        win = SDL.SDL_CreateWindow(b"PicoReader", SDL_WINDOWPOS_CENTERED,
                                    SDL_WINDOWPOS_CENTERED, SW, SH, 0)
    else:
        win = SDL.SDL_CreateWindow(b"PicoReader", SDL_WINDOWPOS_CENTERED,
                                    SDL_WINDOWPOS_CENTERED, DEV_W, DEV_H,
                                    SDL_WINDOW_FULLSCREEN_DESKTOP)
    if not win:
        _boot_log(f"SDL_CreateWindow failed: {SDL.SDL_GetError()}\n")
        sys.exit(1)
    renderer = SDL.SDL_CreateRenderer(win, -1, 2)
    if not renderer:
        renderer = SDL.SDL_CreateRenderer(win, -1, 1)
    if not renderer:
        _boot_log(f"SDL_CreateRenderer failed: {SDL.SDL_GetError()}\n")
        sys.exit(1)

    # v0.1.148: pin the renderer's logical coordinate space to the app's
    # native 720x720 canvas. On the CubeXX-H this is a 1:1 no-op (window
    # already is 720x720). On any other resolution SDL2 itself computes
    # the integer-safe scale-to-fit and centers it -- none of the app's
    # own layout math (SW/SH/_sx/_sy, used everywhere) has to change.
    SDL.SDL_RenderSetLogicalSize(renderer, SW, SH)

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
    SDL.SDL_GetTicks.restype = ctypes.c_uint32

    # v0.1.79: input avalanche fix. During a long background-decode
    # stall (see mini_jpeg.py / ImageLoader notes), SDL still queues
    # every button press that happens while the app can't get back to
    # its event loop -- confirmed by Kaleb: mashing B during a hang,
    # thinking it wasn't registering, then having ALL of those presses
    # fire back-to-back the instant it recovered, backing out of the
    # reader -> library -> clean out of the app in one frame. The inner
    # `while True: poll_event()` loop below already drains the whole
    # queue before the next redraw, with no way to tell "just pressed"
    # apart from "queued 2 seconds ago" -- so it acted on all of them as
    # if they'd just happened. Every SDL button/key/hat event carries its
    # own timestamp (SDL_GetTicks() at the moment it was generated), so
    # any event older than STALE_INPUT_MS versus *now* almost certainly
    # queued up during a stall rather than being a deliberate rapid
    # button mash -- drop it instead of acting on it. Doesn't touch
    # legitimate fast double-taps (350ms is generous for that) and
    # doesn't fix the underlying stall itself, but stops one stall from
    # cascading into an accidental app exit.
    STALE_INPUT_MS = 350

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
            ev_timestamp = None

            if etype == SDL_QUIT_EV:
                running = False
                break
            elif etype == SDL_KEYDOWN_EV:
                kev = ctypes.cast(raw, ctypes.POINTER(SDL_KeyboardEvent))[0]
                ev_timestamp = kev.timestamp
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
                ev_timestamp = hev.timestamp
                hv = hev.value
                if hv & SDL_HAT_UP: btn = "UP"
                elif hv & SDL_HAT_DOWN: btn = "DOWN"
                elif hv & SDL_HAT_LEFT: btn = "LEFT"
                elif hv & SDL_HAT_RIGHT: btn = "RIGHT"
            elif etype == SDL_JOYBUTTONDOWN_EV:
                bev = ctypes.cast(raw, ctypes.POINTER(SDL_JoyButtonEvent))[0]
                ev_timestamp = bev.timestamp
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

            if btn and ev_timestamp is not None:
                # v0.1.79: uint32-wraparound-safe "how old is this event"
                age_ms = (SDL.SDL_GetTicks() - ev_timestamp) & 0xFFFFFFFF
                if age_ms > STALE_INPUT_MS:
                    btn = None  # drop it -- queued during a stall, not a live press

            if btn:
                app.dirty = True
                handle_button(app, btn)
                if app.quit_requested:
                    # v26.07.10.04: brief exit toast (Kaleb's request)
                    # instead of the window just vanishing the instant B
                    # is pressed. quit_requested is only ever set from
                    # SCREEN_LIBRARY's B handler (confirmed -- the only
                    # site in this file), so drawing draw_library() here
                    # is always the correct screen to show the toast on.
                    # v26.07.10.05: switched from FACE_EXIT to FACE_DONE
                    # -- Kaleb's request to reuse the same "done" cheer
                    # face the download-completion toasts already use,
                    # rather than a dedicated exit-only face.
                    app.set_status(f"Exiting Pico Reader {FACE_DONE}", duration=EXIT_TOAST_SECONDS)
                    SDL.SDL_SetRenderDrawColor(renderer, 0, 0, 0, 255)
                    SDL.SDL_RenderClear(renderer)
                    draw_library(renderer, app)
                    SDL.SDL_RenderPresent(renderer)
                    SDL.SDL_Delay(int(EXIT_TOAST_SECONDS * 1000))
                    running = False
                    break

        need_redraw = app.dirty
        if not need_redraw and app.screen == SCREEN_SPLASH:
            need_redraw = True  # must animate every frame, no button press to wait for
        if not need_redraw and app.screen == SCREEN_READER:
            need_redraw = app.has_pending_image_updates()
        if not need_redraw and app.screen == SCREEN_IMAGE_VIEW and app._imgview_span is not None:
            snap = app.image_loader.get_status_snapshot(app._img_key(app._imgview_span.src))
            need_redraw = snap["result"] is None or snap["result"] == "loading" or snap["is_upgrading"]
        if not need_redraw and app.screen == SCREEN_DOWNLOAD_BROWSE:
            need_redraw = app.dl_loading or app._dl_downloading_idx is not None
        if not need_redraw and app.screen == SCREEN_TEXT_ENTRY:
            need_redraw = app.te_checking
        if not need_redraw and app.screen == SCREEN_STORAGE:
            need_redraw = app._prerender_active
        if not need_redraw and app.status_msg and time.time() < app.status_until:
            need_redraw = True

        if need_redraw:
            # v0.1.83 fix: clear dirty BEFORE drawing, not after. The old
            # order (draw, then app.dirty=False) raced with the ImageLoader
            # worker thread's on_update() callback (setattr(self,"dirty",
            # True), fired the instant a background decode lands -- see
            # ImageLoader._worker_loop()). With native_jpeg's near-instant
            # decode, a VISIBLE-priority image can finish decoding WHILE
            # this exact frame is still being drawn (the frame started out
            # drawing the "Loading image..." placeholder, unaware the
            # result would land a moment later on another thread). If
            # on_update() set dirty=True mid-draw, the old `app.dirty =
            # False` at the end of this block silently clobbered it, and
            # has_pending_image_updates() no longer reported anything
            # pending (the decode was already done) -- so the render loop
            # went idle with the completed image never actually painted,
            # requiring an unrelated button press (which force-sets
            # dirty=True) to finally show it. Root cause of "first cover
            # image doesn't appear until L1/R1/dpad" (Kaleb) -- present
            # with mini_jpeg too but rare there; native's speed makes the
            # race land almost every time. Fix: snapshot-and-clear BEFORE
            # drawing, so any dirty=True set mid-draw by the worker thread
            # survives into the next loop iteration -- worst case one
            # harmless extra redraw.
            app.dirty = False

            # v0.1.148: full-target clear (not just the 720x720 logical
            # viewport) so any pillarbox/letterbox bars on non-square
            # devices are actually painted black every frame -- SDL_Render
            # Clear() clears the whole physical render target regardless
            # of SDL_RenderSetLogicalSize, while every draw_* call below
            # only ever touches the scaled 720x720 viewport. On the
            # CubeXX-H (no bars) this is a harmless redundant fill, since
            # every screen already paints its own full-canvas background.
            SDL.SDL_SetRenderDrawColor(renderer, 0, 0, 0, 255)
            SDL.SDL_RenderClear(renderer)

            if app.screen == SCREEN_SPLASH:
                draw_splash(renderer, app)
            elif app.screen == SCREEN_LIBRARY:
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
            elif app.screen == SCREEN_DOWNLOAD_VIDEO_SOURCES:
                draw_download_video_sources(renderer, app)
            elif app.screen == SCREEN_DOWNLOAD_AUDIO_SOURCES:
                draw_download_audio_sources(renderer, app)
            elif app.screen == SCREEN_DOWNLOAD_AUDIO_BOOKS:
                draw_download_audio_books(renderer, app)
            elif app.screen == SCREEN_DOWNLOAD_BROWSE:
                draw_download_browse(renderer, app)
            elif app.screen == SCREEN_DOWNLOAD_HELP:
                draw_download_help(renderer, app)
            elif app.screen == SCREEN_IMAGE_VIEW:
                draw_image_view(renderer, app)

            # v0.1.131: BMO-style outer screen frame -- always last, after
            # every screen's own drawing, so it can't be forgotten on any
            # individual screen (see _draw_screen_frame() docstring).
            # v26.07.09.14: bottom_radius scaled to the CURRENT hint bar
            # height so its fixed-size corner mask doesn't disproportionately
            # dominate a short hint bar at small Font Size steps -- see
            # _draw_screen_frame()'s docstring for the full story.
            _bottom_radius = min(SCREEN_FRAME_RADIUS, _sy(hint_height(app.fonts)) // 2)
            _draw_screen_frame(renderer, bottom_radius=_bottom_radius)

            SDL.SDL_RenderPresent(renderer)
            time.sleep(0.016)
        else:
            # nothing to draw -- sleep longer to save CPU/battery while idle
            time.sleep(0.05)

    if app.current_book_path:
        app.save_progress()
    SDL.SDL_Quit()


def handle_button(app, btn, body_h_px=None):
    # body_h_px param kept for call-site compatibility but no longer used
    # -- v0.1.86: replaced with _reader_body_layout(), the same formula
    # draw_reader() uses, so the two can never disagree about body_rows
    # again. See _reader_body_layout()'s docstring for the bug this fixes.
    _body_top, line_h, body_rows = _reader_body_layout(app.fonts)

    if app.screen == SCREEN_SPLASH:
        # v26.07.10.06: START/A/B all skip straight to the real
        # destination (Kaleb's request) -- same target draw_splash()
        # itself hands off to once its timer runs out, just triggered
        # early instead of waiting.
        if btn in ("START", "A", "B"):
            app.screen = app._splash_dest_screen
        return

    if app.screen == SCREEN_LIBRARY:
        n = len(app.books)
        if btn == "UP":
            app.lib_index = (app.lib_index - 1) % n if n else 0
        elif btn == "DOWN":
            app.lib_index = (app.lib_index + 1) % n if n else 0
        elif btn == "Y":
            app.cycle_sort_mode()
        elif btn == "LEFT" and n:
            # v0.1.110: quick-scroll -- D-pad LEFT/RIGHT jump 10 rows at a
            # time, same convention as Chapters/Bookmarks' L/R. Clamps
            # rather than wraps, so a long library doesn't quietly loop
            # you back to the opposite end.
            app.lib_index = max(0, app.lib_index - 10)
        elif btn == "RIGHT" and n:
            app.lib_index = min(n - 1, app.lib_index + 10)
        elif btn == "X" and app.books:
            app.toggle_pin(app.books[app.lib_index])
        elif btn == "A" and app.books:
            app.open_book(app.books[app.lib_index])
        elif btn == "SELECT" and app.books:
            # v0.1.117: SELECT used to be book-delete (press twice to
            # confirm) -- moved to a "Delete Book" entry in the Library
            # Menu (START) so SELECT could become the Finished/Unfinished
            # marker Kaleb asked for, matching X/pin's one-press toggle
            # feel since marking a book finished isn't destructive and
            # doesn't need a confirm step.
            app.toggle_finished(app.books[app.lib_index])
        elif btn == "B":
            app.quit_requested = True
        elif btn == "L2" and DOWNLOAD_PLUGINS:
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
            app.lib_menu_index = 0
            # capture whichever book was highlighted right now -- Delete
            # Book in the menu always targets this, not whatever's
            # highlighted once inside the menu (there's no book list
            # shown there)
            app._menu_target_book = app.books[app.lib_index] if app.books else None
            app._menu_delete_armed = False
            app.screen = SCREEN_LIBRARY_MENU

    elif app.screen == SCREEN_LIBRARY_MENU:
        n = len(LIBRARY_MENU_ITEMS)
        if btn == "UP":
            app.lib_menu_index = (app.lib_menu_index - 1) % n
            app._menu_delete_armed = False
            app._menu_clear_finished_armed = False
        elif btn == "DOWN":
            app.lib_menu_index = (app.lib_menu_index + 1) % n
            app._menu_delete_armed = False
            app._menu_clear_finished_armed = False
        elif btn == "B":
            app._menu_delete_armed = False
            app._menu_clear_finished_armed = False
            app.screen = SCREEN_LIBRARY
        elif btn == "A":
            choice = LIBRARY_MENU_ITEMS[app.lib_menu_index]
            if choice != "Delete Book":
                app._menu_delete_armed = False
            if choice != "Clear All Finished":
                app._menu_clear_finished_armed = False
            sort_map = {"Sort: Title A-Z": "title", "Sort: Author A-Z": "author",
                        "Sort: Last Read": "last_read", "Sort: Recently Added": "recent"}
            if choice in sort_map:
                app.lib_sort_mode = sort_map[choice]
                app._apply_library_view()
                app.lib_index = 0
                app.screen = SCREEN_LIBRARY
            elif choice == "Continue Reading":
                app.open_continue_reading()
            elif choice == "Pin/Unpin Selected":
                if app._menu_target_book:
                    app.toggle_pin(app._menu_target_book)
                    # stays open, same as Filter/Theme -- lets the label
                    # update in place so the toggle's new state is visible
                    # without re-opening the menu
            elif choice == "Mark Finished/Unfinished":
                if app._menu_target_book:
                    app.toggle_finished(app._menu_target_book)
                    # stays open -- same reasoning as Pin/Unpin above
            elif choice == "Filter: Cycle":
                app.cycle_filter_mode()
                # stays open, same as Theme +/- -- lets Kaleb cycle
                # through All/Unfinished/Finished and see the label
                # update without re-opening the menu each time
            elif choice == "Clear All Finished":
                if len(app.finished) == 0:
                    pass  # nothing to clear -- no-op, same spirit as
                          # Delete Book's "nothing was highlighted" no-op
                elif app._menu_clear_finished_armed:
                    app.clear_all_finished()
                    app._menu_clear_finished_armed = False
                    # stays open (unlike Delete Book) -- clearing marks
                    # isn't as disruptive as removing a book file, and
                    # Kaleb may want to keep adjusting Filter/Sort right
                    # after seeing the count clear
                else:
                    app._menu_clear_finished_armed = True
            elif choice == "Delete Book":
                if app._menu_target_book is None:
                    pass  # nothing was highlighted when START was pressed
                elif app._menu_delete_armed:
                    book = app._menu_target_book
                    title = book["title"]
                    if app.delete_book(book):
                        app.refresh_library()  # also purges this book's
                                                # image cache, anchor cache,
                                                # and pin/finished entries
                                                # -- see delete_book()
                        app.lib_index = max(0, min(app.lib_index, len(app.books) - 1))
                        app.set_status(f'Deleted "{title}"')
                    else:
                        app.set_status(f'Could not delete "{title}"')
                    app._menu_delete_armed = False
                    app._menu_target_book = None
                    app.screen = SCREEN_LIBRARY
                else:
                    # first press -- arm it, same two-press-confirm safety
                    # the old Library-screen SELECT delete used
                    app._menu_delete_armed = True
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
            elif choice == "Settings":
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
        elif btn == "X":
            app.dl_help_return_screen = SCREEN_DOWNLOAD_SOURCES
            app.dl_help_scroll = 0
            app.screen = SCREEN_DOWNLOAD_HELP

    elif app.screen == SCREEN_DOWNLOAD_CATEGORIES:
        categories = getattr(app.dl_plugin, "CATEGORIES", [])
        n = len(categories)
        if btn == "UP": app.dl_cat_index = (app.dl_cat_index - 1) % n if n else 0
        elif btn == "DOWN": app.dl_cat_index = (app.dl_cat_index + 1) % n if n else 0
        elif btn == "R" and n:
            # v0.1.88: jump ~10 items at a time -- Kaleb's request, since
            # some plugins' CATEGORIES lists (JW back-issue categories,
            # Gutenberg's 17-entry picker) are long enough that one-at-a-
            # time UP/DOWN got tedious once these became full scrollable
            # lists instead of the old paged browsing.
            app.dl_cat_index = min(app.dl_cat_index + 10, n - 1)
        elif btn == "L" and n:
            app.dl_cat_index = max(app.dl_cat_index - 10, 0)
        elif btn == "Y" and getattr(app.dl_plugin, "SUPPORTS_SEARCH", False):
            # v26.07.09.11: Search used to only be reachable AFTER opening
            # some category first (SCREEN_DOWNLOAD_BROWSE's own Y handler)
            # -- forcing an extra, pointless hop through a category just to
            # search. Added here too so it's available from the very first
            # JW/Gutenberg screen. dl_category is still None at this point
            # (nothing chosen yet), so this is a plugin-wide search, same
            # as searching with no category ever mattered to start_search().
            def _on_cat_search_confirm(app, value):
                app.screen = SCREEN_DOWNLOAD_BROWSE
                app.start_search(value)
            label = getattr(app.dl_plugin, "PLUGIN_NAME", "")
            app.open_text_entry(f"Search {label}", "",
                                 _on_cat_search_confirm, SCREEN_DOWNLOAD_CATEGORIES,
                                 hint="Search by title or author  (case-insensitive)")
        elif btn == "SELECT" and getattr(app.dl_plugin, "SUPPORTS_MANUAL_CODE", False):
            # v26.07.09.11: same reasoning as the Y handler just above --
            # Manual Code was Browse-only before, forcing an unnecessary
            # category hop first. Mirrors SCREEN_DOWNLOAD_BROWSE's SELECT
            # handler exactly.
            def _on_cat_code_validate(app, value):
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
                                 None, SCREEN_DOWNLOAD_CATEGORIES, on_validate=_on_cat_code_validate,
                                 hint=getattr(app.dl_plugin, "MANUAL_CODE_HINT", ""))
        elif btn == "B":
            # v26.07.09.10: incognito-style search token -- leaving the
            # plugin entirely (not just backing out of a sub-screen
            # that stays inside it) forgets any cached OmniSearch
            # bearer token, so the NEXT visit fetches fresh rather than
            # silently reusing one from a prior, unrelated session in
            # this plugin. getattr-gated: older jw_fetch.py builds
            # without clear_search_token_cache() just skip this, same
            # graceful-degradation convention as every other optional
            # jw_fetch.py feature check in this file.
            clear_fn = getattr(app.dl_plugin, "clear_search_token_cache", None)
            if clear_fn:
                clear_fn()
            if len(DOWNLOAD_PLUGINS) > 1:
                app.screen = SCREEN_DOWNLOAD_SOURCES
            else:
                app.screen = SCREEN_LIBRARY
        elif btn == "A" and categories:
            # v0.1.110: jw_fetch.CATEGORY_VIDEOS is a pseudo-category (like
            # CATEGORY_WHATS_NEW) that doesn't route through
            # open_category()/list_items() -- it opens the small video-
            # source picker instead (Enjoy Life Forever / JW Broadcasting /
            # Governing Body Updates / The Good News According to Jesus),
            # replacing what used to be four separate Library Menu entries.
            chosen = categories[app.dl_cat_index]
            if chosen == getattr(app.dl_plugin, "CATEGORY_VIDEOS", None):
                app.video_source_index = 0
                app.screen = SCREEN_DOWNLOAD_VIDEO_SOURCES
            elif chosen == getattr(app.dl_plugin, "CATEGORY_AUDIO", None):
                # v26.07.10.01: same pseudo-category pattern as
                # CATEGORY_VIDEOS just above.
                app.audio_source_index = 0
                app._pending_audio_source = None
                app.screen = SCREEN_DOWNLOAD_AUDIO_SOURCES
            else:
                app.open_category(chosen)
        elif btn == "X":
            app.dl_help_return_screen = SCREEN_DOWNLOAD_CATEGORIES
            app.dl_help_scroll = 0
            app.screen = SCREEN_DOWNLOAD_HELP

    elif app.screen == SCREEN_DOWNLOAD_VIDEO_SOURCES:
        n = len(VIDEO_SOURCE_ITEMS)
        if btn == "UP": app.video_source_index = (app.video_source_index - 1) % n
        elif btn == "DOWN": app.video_source_index = (app.video_source_index + 1) % n
        elif btn == "B": app.screen = SCREEN_DOWNLOAD_CATEGORIES
        elif btn == "A":
            choice = VIDEO_SOURCE_ITEMS[app.video_source_index]
            source = VIDEO_SOURCE_BY_LABEL.get(choice)
            if source and source.get("search"):
                def _on_video_search_validate(app, value):
                    query = (value or "").strip()
                    if not query:
                        app.te_checking = False
                        app.te_error = "Type something to search for"
                        app.dirty = True
                        return
                    try:
                        results, err = JW_PLUGIN.search_jw(query, filter="videos")
                    except Exception as e:
                        results, err = [], str(e)
                    items = [it for it in (results or []) if it.get("_kind") == "video"]
                    if err or not items:
                        app.te_checking = False
                        app.te_error = err or f'No videos found for "{query}"'
                        app.dirty = True
                        return
                    app.dl_plugin = JW_PLUGIN
                    app.dl_is_video = True
                    app.dl_category = None
                    app._dl_video_all_items = items
                    app.dl_items = items
                    app.dl_index = 0
                    app.dl_page = 1
                    app.dl_query = query
                    app.dl_has_next = False
                    app.dl_load_error = None
                    app.te_checking = False
                    app.screen = SCREEN_DOWNLOAD_BROWSE
                    app.dirty = True
                app.open_text_entry("Search JW Videos", "", None,
                                     SCREEN_DOWNLOAD_VIDEO_SOURCES,
                                     on_validate=_on_video_search_validate,
                                     hint='e.g. "faith", "family life", "Jeremiah"')
            elif source:
                app.open_plugin_video_list(source["loader"], **source.get("args", {}))
            else:
                # choice == "Back", or (defensive) an unrecognized label --
                # either way, there's nothing to open.
                app.screen = SCREEN_DOWNLOAD_CATEGORIES

    elif app.screen == SCREEN_DOWNLOAD_AUDIO_SOURCES:
        # v26.07.10.01/.02: same shape as SCREEN_DOWNLOAD_VIDEO_SOURCES
        # just above -- "search" special-case now included (v26.07.10.02:
        # Search Audio, mirroring Search Videos exactly) alongside the
        # "books" special-case: a source marked "books": True (Bible
        # Reading Audio) opens the Bible-book sub-picker instead of
        # calling its loader directly -- the loader/args are still
        # exactly what gets called once a book is chosen there, just
        # with booknum added in.
        n = len(AUDIO_SOURCE_ITEMS)
        if btn == "UP": app.audio_source_index = (app.audio_source_index - 1) % n
        elif btn == "DOWN": app.audio_source_index = (app.audio_source_index + 1) % n
        elif btn == "B": app.screen = SCREEN_DOWNLOAD_CATEGORIES
        elif btn == "A":
            choice = AUDIO_SOURCE_ITEMS[app.audio_source_index]
            source = AUDIO_SOURCE_BY_LABEL.get(choice)
            if source and source.get("search"):
                # v26.07.10.02: mirrors the video "Search Videos" handler
                # exactly -- search_jw(filter="audio"), keep only
                # _kind=="audio" hits (unresolved, _raw_lank only --
                # resolved lazily at download time in start_download()'s
                # audio branch, same as video).
                def _on_audio_search_validate(app, value):
                    query = (value or "").strip()
                    if not query:
                        app.te_checking = False
                        app.te_error = "Type something to search for"
                        app.dirty = True
                        return
                    try:
                        results, err = JW_PLUGIN.search_jw(query, filter="audio")
                    except Exception as e:
                        results, err = [], str(e)
                    items = [it for it in (results or []) if it.get("_kind") == "audio"]
                    if err or not items:
                        app.te_checking = False
                        app.te_error = err or f'No audio found for "{query}"'
                        app.dirty = True
                        return
                    app.dl_plugin = JW_PLUGIN
                    app.dl_is_audio = True
                    app._pending_audio_source = None
                    app.dl_category = None
                    app.dl_items = items
                    app.dl_index = 0
                    app.dl_page = 1
                    app.dl_query = query
                    app.dl_has_next = False
                    app.dl_load_error = None
                    app.te_checking = False
                    app.screen = SCREEN_DOWNLOAD_BROWSE
                    app.dirty = True
                app.open_text_entry("Search Audio", "", None,
                                     SCREEN_DOWNLOAD_AUDIO_SOURCES,
                                     on_validate=_on_audio_search_validate,
                                     hint='e.g. "love", "faith", "psalm"')
            elif source and source.get("books"):
                app._pending_audio_source = source
                app.audio_book_index = 0
                app.screen = SCREEN_DOWNLOAD_AUDIO_BOOKS
            elif source:
                app._pending_audio_source = None
                app.open_plugin_audio_list(source["loader"], **source.get("args", {}))
            else:
                # choice == "Back"
                app.screen = SCREEN_DOWNLOAD_CATEGORIES

    elif app.screen == SCREEN_DOWNLOAD_AUDIO_BOOKS:
        # v26.07.10.01: Bible-book sub-picker -- only reachable via a
        # "books": True AUDIO_SOURCES entry, so app._pending_audio_source
        # is always set here. Choosing a book adds its booknum to that
        # source's own args and calls its loader exactly like any other
        # audio source would.
        books = getattr(JW_PLUGIN, "BIBLE_BOOKS", [])
        n = len(books)
        if btn == "UP": app.audio_book_index = (app.audio_book_index - 1) % n if n else 0
        elif btn == "DOWN": app.audio_book_index = (app.audio_book_index + 1) % n if n else 0
        elif btn == "B": app.screen = SCREEN_DOWNLOAD_AUDIO_SOURCES
        elif btn == "A" and n:
            booknum, _name = books[app.audio_book_index]
            source = app._pending_audio_source
            if source:
                args = dict(source.get("args", {}))
                args["booknum"] = booknum
                app.open_plugin_audio_list(source["loader"], **args)

    elif app.screen == SCREEN_DOWNLOAD_BROWSE:
        n = len(app.dl_items)
        if btn == "UP": app.dl_index = (app.dl_index - 1) % n if n else 0
        elif btn == "DOWN": app.dl_index = (app.dl_index + 1) % n if n else 0
        elif btn == "R":
            # v0.1.88: R already meant "next page" when the plugin paginates
            # server-side (has_next=True). Some lists -- e.g. a JW back-
            # issue category, or a Gutenberg category -- come back as one
            # single page with no next/prev at all, so R used to just do
            # nothing there even though the list itself can be 20-30+ items.
            # Falls back to a local ~10-item jump in that case, so the same
            # button always does something useful on every list screen.
            if app.dl_has_next:
                app.dl_next_page()
            elif n:
                app.dl_index = min(app.dl_index + 10, n - 1)
        elif btn == "L":
            if app.dl_page > 1:
                app.dl_prev_page()
            elif n:
                app.dl_index = max(app.dl_index - 10, 0)
        elif btn == "Y" and app.dl_is_video:
            # v0.1.110: none of the four video sources have server-side
            # search -- each is fetched as one small complete list -- so
            # this is a client-side title filter over the already-loaded
            # catalog. See App.search_video_items().
            def _on_video_search_confirm(app, value):
                app.screen = SCREEN_DOWNLOAD_BROWSE
                app.search_video_items(value)
            app.open_text_entry("Search Videos", app.dl_query or "",
                                 _on_video_search_confirm, SCREEN_DOWNLOAD_BROWSE,
                                 hint="Search by title  (case-insensitive, blank clears)")
        elif btn == "Y" and not app.dl_is_video and not app.dl_is_audio and (
                getattr(app.dl_plugin, "SUPPORTS_SEARCH", False)
                or getattr(app.dl_plugin, "SUPPORTS_CATEGORIES", False)):
            # v0.1.157 BUG FIX (Kaleb's follow-up question: "when does
            # category topic search even get used?"): this used to be
            # TWO separate elif branches -- one for SUPPORTS_SEARCH, one
            # for SUPPORTS_CATEGORIES -- both calling the exact same
            # app.start_search(value), which already threads
            # self.dl_category through regardless of which branch opened
            # the box. Since elif only checks the first match, a plugin
            # declaring BOTH flags (gutenberg_fetch.py does) always hit
            # the SUPPORTS_SEARCH branch, silently shadowing the
            # SUPPORTS_CATEGORIES one -- same shadowing pattern as the
            # Y/SELECT bug just fixed above, except this one was
            # cosmetic rather than functional: confirmed via direct
            # simulation that searching inside Gutenberg's "Adventure"
            # category already correctly stayed scoped to Adventure
            # either way (dl_category isn't affected by which branch
            # fired), but the prompt shown was the generic "Search
            # Project Gutenberg" instead of the more specific "Search
            # Adventure" -- misleading about what the search would
            # actually be scoped to. Now a single branch: label is
            # "Search {category}" whenever a category is currently
            # open (regardless of which flag(s) got it there), else
            # "Search {plugin name}" -- matching what start_search()
            # actually does either way.
            def _on_search_confirm(app, value):
                app.screen = SCREEN_DOWNLOAD_BROWSE
                app.start_search(value)
            label = app.dl_category or getattr(app.dl_plugin, "PLUGIN_NAME", "")
            app.open_text_entry(f"Search {label}", app.dl_query or "",
                                 _on_search_confirm, SCREEN_DOWNLOAD_BROWSE,
                                 hint="Search by title or author  (case-insensitive)")
        elif btn == "SELECT" and not app.dl_is_video and not app.dl_is_audio and getattr(app.dl_plugin, "SUPPORTS_MANUAL_CODE", False):
            # v0.1.156 BUG FIX (Kaleb's report, follow-up to the Help
            # screen): this used to be bound to Y, in an elif chain AFTER
            # the SUPPORTS_CATEGORIES branch above. jw_fetch.py declares
            # BOTH SUPPORTS_CATEGORIES=True and SUPPORTS_MANUAL_CODE=True,
            # and elif only ever checks the first matching branch -- so
            # for the actual live JW_PLUGIN config, this code was
            # completely unreachable: Y always hit the category-search
            # branch above instead. Confirmed directly: simulated
            # pressing Y on a real category ("Books & Brochures") landed
            # on "Search Books & Brochures", never the code-entry screen,
            # even though the hint bar text (built separately, see
            # draw_download_browse()) claimed "Y Enter Code" for exactly
            # this situation -- the hint text and the real Y behavior had
            # drifted out of sync. Moved to its own button (SELECT, free
            # on this screen) so category search and manual code entry
            # are BOTH reachable rather than one silently shadowing the
            # other.
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
            if app.dl_is_video:
                # v0.1.110: video browse is now opened from
                # SCREEN_DOWNLOAD_VIDEO_SOURCES (Download Books > JW >
                # Videos), not directly from the Library Menu -- so B goes
                # back there, letting Kaleb pick a different video source
                # without walking all the way back through Library Menu >
                # Download Books > JW > Videos again.
                app.dl_is_video = False
                app.screen = SCREEN_DOWNLOAD_VIDEO_SOURCES
            elif app.dl_is_audio:
                # v26.07.10.01: same idea as the video branch just above --
                # B goes back to whichever audio picker screen got you
                # here. If a Bible book was chosen first (books-type
                # source), that's SCREEN_DOWNLOAD_AUDIO_BOOKS (so you can
                # pick a different book without re-opening Audio from
                # scratch); otherwise (e.g. Watchtower Study Audio, no
                # book picker involved) it's SCREEN_DOWNLOAD_AUDIO_SOURCES.
                app.dl_is_audio = False
                app.screen = (SCREEN_DOWNLOAD_AUDIO_BOOKS if app._pending_audio_source
                              else SCREEN_DOWNLOAD_AUDIO_SOURCES)
            elif app.dl_category is not None:
                # v26.07.09.14 BUG FIX (Kaleb's report): dl_category used
                # to just persist here, unreset -- so a search started
                # from the Categories screen (either Gutenberg's main
                # search, or JW's Y/SELECT shortcuts added directly to
                # this screen in v26.07.09.11) could silently inherit
                # whatever category was last browsed, instead of
                # searching everything like the Categories screen implies
                # it should. Categories now always genuinely means "no
                # category" the moment you land on it.
                app.dl_category = None
                app.screen = SCREEN_DOWNLOAD_CATEGORIES
            elif len(DOWNLOAD_PLUGINS) > 1:
                # v26.07.09.10: see the matching comment at the
                # SCREEN_DOWNLOAD_CATEGORIES B-handler -- this is the
                # OTHER real exit point that leaves the plugin entirely
                # (the two branches above, video-sources and
                # categories, both stay inside it and must NOT clear
                # the token).
                clear_fn = getattr(app.dl_plugin, "clear_search_token_cache", None)
                if clear_fn:
                    clear_fn()
                app.screen = SCREEN_DOWNLOAD_SOURCES
            else:
                clear_fn = getattr(app.dl_plugin, "clear_search_token_cache", None)
                if clear_fn:
                    clear_fn()
                app.screen = SCREEN_LIBRARY
        elif btn == "A" and app.dl_items:
            app.start_download(app.dl_index)
        elif btn == "X":
            app.dl_help_return_screen = SCREEN_DOWNLOAD_BROWSE
            app.dl_help_scroll = 0
            app.screen = SCREEN_DOWNLOAD_HELP

    elif app.screen == SCREEN_DOWNLOAD_HELP:
        if btn == "UP":
            app.dl_help_scroll = max(0, app.dl_help_scroll - 1)
        elif btn == "DOWN":
            app.dl_help_scroll += 1  # clamped for real inside draw_download_help()
        elif btn == "B":
            app.screen = app.dl_help_return_screen

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
        visible_spans = app.visible_span_indices(line_h, body_rows)
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
            app.page_up(line_h, body_rows)
        elif btn == "R":
            app.page_down(line_h, body_rows)
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

    elif app.screen == SCREEN_IMAGE_VIEW:
        pan_step = IMGVIEW_PAN_STEP_FRAC
        if btn == "UP":
            app._imgview_pan_by(0.0, -pan_step)
        elif btn == "DOWN":
            app._imgview_pan_by(0.0, pan_step)
        elif btn == "LEFT":
            app._imgview_pan_by(-pan_step, 0.0)
        elif btn == "RIGHT":
            app._imgview_pan_by(pan_step, 0.0)
        elif btn == "R":
            app._imgview_zoom_by(IMGVIEW_ZOOM_STEP)
        elif btn == "L":
            app._imgview_zoom_by(1.0 / IMGVIEW_ZOOM_STEP)
        elif btn == "B":
            app.screen = SCREEN_READER

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
            elif choice == "Immersive Mode":
                app.immersive_mode = not app.immersive_mode
                save_settings({"immersive_mode": app.immersive_mode})
                # stays open, same as Theme +/- -- lets the label update
                # in place without re-opening the menu
            elif choice == "Library":
                app.save_progress()
                app.refresh_library()
                app.lib_index = 0
                app.screen = SCREEN_LIBRARY
            elif choice == "Settings":
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

        def _storage_hidden(idx):
            return (STORAGE_ACTIONS[idx] == "Pre-render Book Images"
                    and native_image is not None and native_image.available)

        if btn == "UP":
            new_idx = app.storage_index
            for _ in range(n):
                new_idx = (new_idx - 1) % n
                if not _storage_hidden(new_idx):
                    break
            app.storage_index = new_idx
            app._storage_confirm_idx = None
        elif btn == "DOWN":
            new_idx = app.storage_index
            for _ in range(n):
                new_idx = (new_idx + 1) % n
                if not _storage_hidden(new_idx):
                    break
            app.storage_index = new_idx
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
            elif action == "Toggle Open Last Book on Launch":
                # Non-destructive, instant -- only affects the NEXT app
                # launch (checked once at the end of App.__init__), no
                # live behavior to update right now.
                app.open_last_book_enabled = not app.open_last_book_enabled
                save_settings({"open_last_book_enabled": app.open_last_book_enabled})
                state = "ON" if app.open_last_book_enabled else "OFF"
                app.set_status(f"Open Last Book on Launch: {state}")
            elif action == "Pre-render Book Images":
                # v0.1.82: confirmed on-device (Kaleb: "full native
                # instantaneous image rendering") that native_jpeg.py's
                # real libSDL2_image decode is fast enough that
                # pre-warming the cache ahead of time has nothing
                # meaningful left to buy -- the whole reason this feature
                # existed was to front-load mini_jpeg.py's slow decode so
                # it wasn't happening while someone was trying to read.
                # Kept as a real, working feature for the mini_jpeg
                # fallback path (a device/build without libSDL2_image
                # still benefits from it), but a no-op with an
                # explanatory message when native decode is already
                # doing the job -- avoids pointless CPU/disk-cache-write
                # work for zero real benefit on the common fast path.
                if native_image is not None and native_image.available:
                    app.set_status("Not needed -- native fast image decode is already active")
                elif app._prerender_active:
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
                    # v26.07.09.12 BUG FIX: this used to be a bare
                    # app._image_textures.clear() -- dropped the Python
                    # dict references but never called SDL_DestroyTexture()
                    # on the entries themselves first, unlike
                    # _evict_image_textures_if_needed()'s LRU path (which
                    # always destroys before removing). A real GPU-memory
                    # leak: pressing this action repeatedly freed the RAM
                    # decode cache but not the GPU texture memory alongside it.
                    for _key, entry in app._image_textures.items():
                        SDL.SDL_DestroyTexture(entry[0])
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
