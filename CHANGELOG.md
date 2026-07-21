# Changelog

Documentation and repo-metadata changes are logged here. Application
version history (main.py, YY.MM.DD.XX scheme) lives in main.py's own
AI notes/changelog block, not here.

## v26.07.20.39 — 2026-07-21

### Added
- **mpv is now the primary video player**, with automatic fallback to
  ffplay if mpv isn't found on a device. Primary reason: a real
  on-screen progress bar (mpv's `--osd-bar`) for JW videos that can run
  up to an hour long — ffplay has no equivalent for this.
- New **Video Player** setting (Auto / mpv / ffplay), in both the
  reader's Video Settings menu and the standalone Settings screen.
  "Auto" preserves the default mpv-preferred/ffplay-fallback behavior;
  the other two force a specific player (falling back to the other one
  only if the forced choice genuinely isn't available on the device).
- **L1/R1 now skip ±10 minutes** during video playback (mapped to Page
  Up/Down), for quickly navigating long videos. On mpv this is exact
  and unconditional via a bundled input config; on ffplay it uses that
  player's own native chapter/10-minute-jump behavior.
- **Right analog stick support** on devices that have one: up/down
  turns pages, left/right jumps chapters. Automatically inert (no
  effect, no crash) on devices without a physical second stick.
- Compiled muOS device reference documentation (screen resolutions,
  analog stick presence, control mappings) sourced directly from
  MustardOS's own repositories, covering every currently known
  supported device.

### Fixed
- **Leftover video frame stuck on screen** after stopping an in-book
  video link early — a real, reproducible bug on real hardware. Root
  cause: that specific playback path ran on a background thread, which
  is now eliminated entirely; all video playback happens on the main
  thread, matching how the library's video-browsing playback path
  already worked correctly.
- **Two UI "ghost gap" bugs**: hiding the "Video Settings" menu row
  (when the video module isn't bundled) or the "Download Books" row
  (when no downloader plugin is bundled) previously left a blank gap
  in the menu and shifted every item below it down by one row. Both
  menus now close up correctly with no gap, matching an existing fix
  already applied elsewhere in the app.
- mpv network-resilience flags were incomplete (missing base reconnect
  flags alongside the more specific ones), meaning a dropped
  connection during streaming may not have reliably reconnected.
- A failed write of mpv's bundled input config no longer risks
  affecting playback — mpv simply falls back to its own default
  controls if that file can't be written for any reason.
- Video playback failures (bad link, dropped connection, corrupted
  stream) are now correctly reported as failures instead of silently
  being treated as a normal, successful playback session.
- Diagnostic log files (crash log, video-player log) are now capped in
  size instead of growing indefinitely over long-term use.

## v26.07.18.12 — 2026-07-18

**Note on versioning:** this release switches PicoReader's public GitHub
release tags from the earlier `0.1.x` scheme to the same `YY.MM.DD.XX`
date-based scheme already used internally in `main.py`'s own changelog.
Going forward, release tags will always match the app version they were
built from — no separate release-numbering track. This release corresponds
to app build `v26.07.18.11`; the `.12` release tag marks the packaging/
documentation commit on top of that build.

### Fixed
- `LICENSE.md` trimmed to pure, unmodified MIT license text. It previously
  included extra paragraphs (scope note + font license pointer) that kept
  GitHub's license detector from auto-recognizing it as MIT.
- `FONT_LICENSE.txt` now carries the scope clarification that used to sit
  in `LICENSE.md` (which source files MIT covers vs. the separately
  licensed bundled fonts), plus a corrected claim — it now says "license
  summary" instead of falsely claiming to contain the full legal text, and
  links to the canonical Bitstream Vera license for that.

### Added
- `README.md` Screenshots section, with real captures (not mockups) of the
  Library and Reader screens, plus a five-theme gallery (Default, Dim Warm,
  Deep Amber, Red Shift, Adventure). Captured by running the actual
  `main.py` render pipeline headlessly (SDL2 dummy driver, real bundled
  font, real `apply_theme()`/`draw_library()`/`draw_reader()` calls) against
  a real public-domain library (Project Gutenberg's top-10-yesterday list
  plus Sherlock Holmes) rather than hand-drawn placeholders.
- `screenshots/` folder: `library.png`, `reader.png`,
  `theme_default.png`, `theme_dim_warm.png`, `theme_deep_amber.png`,
  `theme_red_shift.png`, `theme_adventure.png`.
