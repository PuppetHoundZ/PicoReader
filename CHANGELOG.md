# Changelog

Documentation and repo-metadata changes are logged here. Application
version history (main.py, YY.MM.DD.XX scheme) lives in main.py's own
AI notes/changelog block, not here.

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
