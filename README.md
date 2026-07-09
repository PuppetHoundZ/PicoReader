# PicoReader

PicoReader is an EPUB reader for the **Anbernic RG CubeXX-H** running
**muOS**. It's built from scratch in Python with no external
dependencies — no PIL/Pillow, no pip installs, nothing to set up. Just
copy it on and start reading.

Image decoding uses the device's own native `libSDL2_image`/`libjpeg`
libraries for speed, but that's never a hard requirement — a complete,
pure-Python JPEG decoder is built in as an automatic fallback. If a
future muOS update ever changes or removes those native libraries,
PicoReader keeps working on its own rather than breaking.

It's a companion app to
[Pico8FavsSorter](https://github.com/PuppetHoundZ/MuOS-Pico8-Favs-Sorter),
another muOS app for the same device.

The CubeXX-H's square 720×720 screen wasn't an accident of this
project — it's a deliberate design choice by the device itself, and
part of why it was bought in the first place. It was picked for
running PICO-8 games (which are natively square), with minimalism as
the whole point. The ebook reader started as a smaller side idea on
the same hardware and ended up becoming the main passion project.

## Quick start

1. Grab `PicoReader.muxapp` from [Releases](../../releases).
2. Install it like any other `.muxapp` through muOS's Archive Manager —
   or unzip it directly into `/run/muos/storage/application/` so you end
   up with `/run/muos/storage/application/PicoReader/`.
3. Copy your `.epub` files into PicoReader's library folder.
4. Launch PicoReader from the Applications menu and start reading.

## What it can do

- **Reads real-world EPUBs**, including ones with complex formatting,
  footnotes, and internal links — not just simple text files.
- **Shows images**, including progressive JPEGs, using a JPEG decoder
  built from scratch for this project (there's no PIL/Pillow on-device
  to do this for us), with a much faster native decode path used
  automatically when the device has `libSDL2_image` available.
- **Adjustable text size** that applies everywhere — the book text,
  menus, and every list on screen — not just the reading area.
- **Bookmarks and "resume reading"** that return you to the exact spot
  you left off, down to the paragraph.
- **A full table of contents / chapter browser**, plus quick
  next/previous chapter buttons.
- **Library organization** — pin favorites, mark books Finished/
  Unfinished with a filter to match, sort by title/author/last read/
  recently added, and a "Continue Reading" shortcut that jumps straight
  into your most recently read book. There's also an optional "Open
  Last Book on Launch" toggle if you'd rather skip the Library screen
  entirely and land right back in your book on startup.
- **A built-in image cache** you can manage from the Settings screen,
  including a RAM-only mode if you'd rather not write to disk at all.
- **Optional book downloaders** — browse and download books right on
  the device (see below).

## Controls

Every screen shows its own control hints at the bottom, so you're never
guessing. The basics:

| Button | While reading | In the Library |
|---|---|---|
| D-PAD | Scroll / move between links | Move selection (LEFT/RIGHT jump 10) |
| A | Follow a link / confirm | Open the selected book |
| B | Go back | Quit |
| L / R | Previous / next page | Font size smaller / larger |
| L2 / R2 | Previous / next chapter | Open downloader (if installed) |
| Y | Toggle fast-scroll | Change sort order |
| X | Open the menu | Pin a book |
| START | Add a bookmark here | Open the Library menu |
| SELECT | -- | Mark the book Finished / Unfinished |

Book delete lives in the Library menu (START → Delete Book) rather than
on a bare button — it always targets whichever book was highlighted
when you opened the menu, and needs a second press to confirm. The
Library menu also has sort/filter shortcuts, theme switching, and the
Settings screen (image cache, RAM-only mode, Continue Reading /
Open Last Book on Launch, and more).

## Downloading books on-device

PicoReader can browse and download books without needing a computer.
Included out of the box is `gutenberg_fetch.py`, which pulls
public-domain books from [Project Gutenberg](https://www.gutenberg.org)
via the community-run [Gutendex](https://gutendex.com) API.

Want to add your own source? See `PLUGIN_TEMPLATE.py` for the plugin
contract — it's a small, self-contained interface.

## Requirements

- An Anbernic RG CubeXX-H, or another muOS device with Python 3 and
  SDL2/SDL2_ttf available.

## Other-resolution device support (added v0.1.148)

PicoReader is built and tested primarily on the **RG CubeXX-H (720×720)**.
Starting with v0.1.148 it also runs on other muOS screen sizes without
any layout changes, by detecting the real screen at boot and having
SDL2 scale the app's fixed 720×720 canvas to fit — centered, with black
bars on the sides rather than stretching. Confirmed device groupings
(via community.muos.dev): 640×480 (RG28XX, RG35XX/+/2024/H/SP, RG40XX
H/V), 720×480 (RG34XX family), 720×720 (RGCubeXX — primary target),
1024×768 (TrimUI Brick), 1280×720 (TrimUI Smart Pro).

**Honest status:** this has been verified through headless simulation
(real SDL2, no exceptions, correct scale factors confirmed via SDL's
own API, across all resolutions above) but has **not** been confirmed
on real non-CubeXX hardware — the author only owns a CubeXX-H. The
approach follows a standard, well-documented SDL2 pattern
(`SDL_RenderSetLogicalSize`) and avoids a specific real-world bug found
in another muOS app during this work (non-uniform X/Y scaling that
stretches the UI instead of preserving aspect ratio), but "should
work" is not the same claim as "confirmed working." The CubeXX-H path
itself is completely unaffected by this change (separate code branch,
zero risk of regression there). If you test this on another device and
it looks right — or doesn't — please open an issue or PR.

## Building the `.muxapp` yourself

The app is just the contents of this repo. Zip the folder so its files
sit at the **root** of the zip (not inside an extra `application/`
folder), name it `PicoReader.muxapp`, and install it the same way as a
downloaded release.

## Project files

| File | What it does |
|---|---|
| `main.py` | The app itself — UI, controls, state, image handling |
| `epub_engine.py` | Parses EPUB files (no external libraries needed) |
| `mini_jpeg.py` | Decodes JPEG images, including progressive JPEGs, in pure Python |
| `native_image.py` | Optional ctypes bridge to the device's own `libSDL2_image` for much faster decoding of JPEG, PNG, and other formats — used automatically when available, with `mini_jpeg.py` as the automatic JPEG-only fallback |
| `mux_launch.sh` | Tells muOS how to launch the app |
| `gutenberg_fetch.py` | The built-in Project Gutenberg downloader |
| `PLUGIN_TEMPLATE.py` | Starting point for writing your own downloader |
| `assets/` | Bundled fonts (see License below) |

`main.py` keeps its own changelog and architecture notes at the top of
the file, for anyone — human or AI — picking the project back up later.

## License

This project's own code is MIT licensed. The bundled Liberation Sans
fonts are third-party and stay under the SIL Open Font License 1.1.
Both full license texts are in [`LICENSE`](LICENSE).

## A note from the author

I tested this app extensively with the amazingly designed and complex
EPUBs published by JW.org, and it handles them incredibly well. EPUBs of
this kind are some of the most complex I've come across, and until
building this reader I hadn't found a satisfactory way to read them
anywhere outside of Apple's iBooks.

I used Claude Code as a tool throughout development, but the UI, the
overall design philosophy, and the plugin architecture were designed by
me.

## Credits

- [Liberation Sans](https://github.com/liberationfonts) — Red Hat /
  Google, SIL Open Font License 1.1
- [Gutendex](https://gutendex.com) — Gareth Johnson, MIT licensed, used
  as an API only (no code bundled)
- Built for [muOS](https://muos.dev) on the Anbernic RG CubeXX-H
