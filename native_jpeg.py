"""
native_jpeg.py

Optional ctypes bridge to the system's libSDL2_image, used to decode JPEGs
at real C speed instead of mini_jpeg.py's pure-Python decoder.

BACKGROUND (v0.1.80): mini_jpeg.py exists because this project avoids
external dependencies -- no pip installs, stdlib ctypes-to-SDL2 only.
But a real freeze bug (whole app input stalling for several seconds
during image decode, confirmed on-device) traced back to mini_jpeg.py
simply being too slow on ARM: ~1s per real embedded photo even after
v0.1.79's GIL-yield tuning, because it's CPU-bound pure Python competing
with the main thread for the GIL. v0.1.78/v0.1.79 made that competition
fairer; they couldn't make the underlying decode itself fast.

Kaleb confirmed via muOS device file browsing (SFTP into /usr/lib) that
the RG CubeXX-H's muOS build actually ships libSDL2_image.so.0.800.2 and
libjpeg.so.8/.9 already -- this is NOT a new dependency we're adding to
the device, it's a library muOS already installs for its own use
(mpv, other apps) that we can load exactly the same way main.py already
loads libSDL2 itself. Verified end-to-end on a dev machine against real
embedded images from mwb_E_202507.epub: byte-for-byte correct RGB output
(0/325 sample points differed from mini_jpeg's own output by more than
rounding noise) and ~143x faster even decoding at full resolution vs.
mini_jpeg's already-downscaled output (0.070s vs 9.955s for all 18 real
images in that epub). On real ARM hardware, a C decoder isn't just faster
per-call -- it also doesn't hold Python's GIL at all during the decode,
which is the actual fix for the freeze, not just a speed bonus.
CONFIRMED ON REAL RG CUBEXX-H HARDWARE (same session this shipped):
Kaleb's exact words, "full native instantaneous image rendering." The
freeze this was built to fix is resolved, not just reduced.

FALLBACK: if libSDL2_image can't be loaded for any reason (missing on a
different muOS build/device, load failure, decode failure on a specific
malformed file), `available` is False and/or decode_jpeg_native() raises
-- main.py catches this and falls back to mini_jpeg.decode_jpeg()
automatically. mini_jpeg.py is NOT being removed; it's the safety net.

This module deliberately mirrors mini_jpeg.decode_jpeg()'s exact
signature and return contract -- (rgb_bytes, width, height), tightly
packed RGB24, scale_n meaning "decode/scale to n/8 of full resolution"
-- so main.py's ImageLoader needs zero changes beyond which function
`decode_jpeg` points to. Disk cache format, memory budgeting, and
texture-creation code are all unaffected.
"""

import ctypes
import ctypes.util

available = False
_SDL = None
_IMG = None

SDL_PIXELFORMAT_RGB24 = 0x17101803  # confirmed via SDL_GetPixelFormatName()
IMG_INIT_JPG = 0x00000001


class _SDL_Rect(ctypes.Structure):
    _fields_ = [("x", ctypes.c_int), ("y", ctypes.c_int),
                ("w", ctypes.c_int), ("h", ctypes.c_int)]


class _SDL_PixelFormat(ctypes.Structure):
    _fields_ = [
        ("format", ctypes.c_uint32), ("palette", ctypes.c_void_p),
        ("BitsPerPixel", ctypes.c_uint8), ("BytesPerPixel", ctypes.c_uint8),
        ("padding", ctypes.c_uint8 * 2),
        ("Rmask", ctypes.c_uint32), ("Gmask", ctypes.c_uint32),
        ("Bmask", ctypes.c_uint32), ("Amask", ctypes.c_uint32),
    ]


class _SDL_Surface(ctypes.Structure):
    pass


_SDL_Surface._fields_ = [
    ("flags", ctypes.c_uint32),
    ("format", ctypes.POINTER(_SDL_PixelFormat)),
    ("w", ctypes.c_int), ("h", ctypes.c_int), ("pitch", ctypes.c_int),
    ("pixels", ctypes.c_void_p), ("userdata", ctypes.c_void_p),
    ("locked", ctypes.c_int), ("lock_data", ctypes.c_void_p),
    ("clip_rect", _SDL_Rect),
    ("map", ctypes.c_void_p), ("refcount", ctypes.c_int),
]

_SurfPtr = ctypes.POINTER(_SDL_Surface)

# Candidate paths, in order -- covers the muOS/RG-CubeXX-H confirmed
# location (/usr/lib) plus common alternate paths on other muOS devices
# and generic Linux, so this doesn't silently stop working if a future
# muOS build reorganizes lib paths. find_library() as a last resort.
_SDL_LIB_CANDIDATES = [
    "/usr/lib/libSDL2-2.0.so.0", "/usr/lib/libSDL2.so",
    "/usr/lib/aarch64-linux-gnu/libSDL2-2.0.so.0",
    "/lib/libSDL2-2.0.so.0",
]
_IMG_LIB_CANDIDATES = [
    "/usr/lib/libSDL2_image-2.0.so.0", "/usr/lib/libSDL2_image.so",
    "/usr/lib/aarch64-linux-gnu/libSDL2_image-2.0.so.0",
    "/lib/libSDL2_image-2.0.so.0",
]


def _try_load(candidates, find_name):
    for path in candidates:
        try:
            return ctypes.CDLL(path)
        except OSError:
            continue
    found = ctypes.util.find_library(find_name)
    if found:
        try:
            return ctypes.CDLL(found)
        except OSError:
            pass
    return None


def _init():
    """Attempt to load libSDL2_image and set up bindings. Safe to call
    multiple times; only does real work once. Never raises -- sets
    `available` True/False and logs the reason via the caller's own
    logging (main.py's _boot_log), passed in to avoid a circular import."""
    global available, _SDL, _IMG
    if _SDL is not None:
        return  # already attempted (success or failure)

    sdl = _try_load(_SDL_LIB_CANDIDATES, "SDL2")
    img = _try_load(_IMG_LIB_CANDIDATES, "SDL2_image")
    if sdl is None or img is None:
        _SDL, _IMG = False, False  # sentinel: attempted, unavailable
        available = False
        return

    try:
        sdl.SDL_RWFromConstMem.restype = ctypes.c_void_p
        sdl.SDL_RWFromConstMem.argtypes = [ctypes.c_void_p, ctypes.c_int]
        sdl.SDL_FreeSurface.argtypes = [_SurfPtr]
        sdl.SDL_GetError.restype = ctypes.c_char_p
        sdl.SDL_CreateRGBSurfaceWithFormat.restype = _SurfPtr
        sdl.SDL_CreateRGBSurfaceWithFormat.argtypes = [
            ctypes.c_uint32, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint32]
        sdl.SDL_UpperBlitScaled.restype = ctypes.c_int
        sdl.SDL_UpperBlitScaled.argtypes = [_SurfPtr, ctypes.POINTER(_SDL_Rect),
                                             _SurfPtr, ctypes.POINTER(_SDL_Rect)]
        sdl.SDL_ConvertSurfaceFormat.restype = _SurfPtr
        sdl.SDL_ConvertSurfaceFormat.argtypes = [_SurfPtr, ctypes.c_uint32, ctypes.c_uint32]

        img.IMG_Init.restype = ctypes.c_int
        img.IMG_Init.argtypes = [ctypes.c_int]
        img.IMG_Load_RW.restype = _SurfPtr
        img.IMG_Load_RW.argtypes = [ctypes.c_void_p, ctypes.c_int]

        # SDL_Init(0) -- no subsystems needed for RWops/Surface-only work.
        # Safe to call even though main.py's own SDL_Init(VIDEO|JOYSTICK)
        # runs separately; SDL reference-counts subsystem init.
        if hasattr(sdl, "SDL_WasInit") :
            pass  # no-op; just confirming the symbol exists on this build
        sdl.SDL_Init(0)
        img.IMG_Init(IMG_INIT_JPG)
    except (AttributeError, OSError):
        _SDL, _IMG = False, False
        available = False
        return

    _SDL, _IMG = sdl, img
    available = True


def decode_jpeg_native(jpeg_bytes, scale_n=4):
    """Decode JPEG bytes via libSDL2_image, returning (rgb_bytes, w, h) --
    same contract as mini_jpeg.decode_jpeg(). Raises RuntimeError on any
    failure (library unavailable, decode failure, unexpected format) so
    the caller can fall back to mini_jpeg.decode_jpeg() cleanly."""
    _init()
    if not available:
        raise RuntimeError("libSDL2_image not available on this device")

    buf = ctypes.create_string_buffer(jpeg_bytes, len(jpeg_bytes))
    rw = _SDL.SDL_RWFromConstMem(buf, len(jpeg_bytes))
    surf = _IMG.IMG_Load_RW(rw, 1)
    if not surf:
        raise RuntimeError(f"IMG_Load_RW failed: {_SDL.SDL_GetError()}")

    try:
        # JPEGs decode to RGB24 via SDL2_image's libjpeg backend in every
        # case observed, but converting defensively costs nothing when
        # it's already a no-op-equivalent format, and protects against a
        # future SDL2_image build or an edge-case JPEG variant (e.g. some
        # CMYK JPEGs) producing something else.
        if surf.contents.format.contents.format != SDL_PIXELFORMAT_RGB24:
            converted = _SDL.SDL_ConvertSurfaceFormat(surf, SDL_PIXELFORMAT_RGB24, 0)
            _SDL.SDL_FreeSurface(surf)
            if not converted:
                raise RuntimeError(f"SDL_ConvertSurfaceFormat failed: {_SDL.SDL_GetError()}")
            surf = converted

        src_w, src_h = surf.contents.w, surf.contents.h
        if scale_n >= 8 or src_w <= 0 or src_h <= 0:
            out_w, out_h = src_w, src_h
            final = surf
            owns_final = False
        else:
            # v0.1.80 fix: mini_jpeg.py's own scaling (see _planes_to_rgb's
            # out_w/out_h formula) rounds UP -- (dim * scale_n + 7) // 8 --
            # not down. A first pass here used floor division
            # (src_w * scale_n // 8) and produced a real off-by-one on
            # most non-multiple-of-8 image dimensions (caught by
            # cross-checking against mini_jpeg's own output before this
            # ever reached main.py). Matching the exact same rounding
            # keeps disk-cache sizing, UI layout, and anything else that
            # assumes mini_jpeg's dimension convention unaffected by
            # which decoder actually produced the bytes.
            out_w = max(1, (src_w * scale_n + 7) // 8)
            out_h = max(1, (src_h * scale_n + 7) // 8)
            dst = _SDL.SDL_CreateRGBSurfaceWithFormat(0, out_w, out_h, 24, SDL_PIXELFORMAT_RGB24)
            if not dst:
                raise RuntimeError(f"SDL_CreateRGBSurfaceWithFormat failed: {_SDL.SDL_GetError()}")
            if _SDL.SDL_UpperBlitScaled(surf, None, dst, None) != 0:
                _SDL.SDL_FreeSurface(dst)
                raise RuntimeError(f"SDL_UpperBlitScaled failed: {_SDL.SDL_GetError()}")
            final = dst
            owns_final = True

        pitch = final.contents.pitch
        tight_row = out_w * 3
        if pitch == tight_row:
            rgb_bytes = ctypes.string_at(final.contents.pixels, tight_row * out_h)
        else:
            # Defensive path: strip row padding if the driver ever returns
            # a padded pitch (not observed on the dev-machine build, but
            # not guaranteed by the SDL2 API either).
            rows = []
            base = final.contents.pixels
            for row in range(out_h):
                rows.append(ctypes.string_at(base + row * pitch, tight_row))
            rgb_bytes = b"".join(rows)

        if owns_final:
            _SDL.SDL_FreeSurface(final)
        return rgb_bytes, out_w, out_h
    finally:
        _SDL.SDL_FreeSurface(surf)
