"""
native_image.py

Optional ctypes bridge to the system's libSDL2_image, used to decode
images (JPEG, PNG, and whatever else the device's SDL2_image build
supports -- see IMG_INIT_ALL below) at real C speed instead of
mini_jpeg.py's pure-Python JPEG-only decoder.

RENAMED from native_jpeg.py in v0.1.146 -- Kaleb asked for a name that's
more obviously accurate now that this handles more than JPEG (v0.1.145
generalized it to every SDL2_image format). The main decode function was
also renamed, from decode_jpeg_native() to decode_image_native(), for
the same reason. See v0.1.146 changelog in main.py for the full list of
what changed and what didn't.

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
malformed file), `available` is False and/or decode_image_native() raises
-- main.py catches this and falls back to mini_jpeg.decode_jpeg()
automatically. mini_jpeg.py is NOT being removed; it's the safety net --
though it remains JPEG-only (see v0.1.144/145 changelog entries), so
that fallback only helps for JPEG specifically.

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
supported_formats = set()  # v0.1.145: e.g. {"JPG", "PNG", "WEBP"} -- built
                            # from IMG_Init()'s actual return bitmask (see
                            # _init()), not just "we asked for it". Replaces
                            # v0.1.144's single png_available flag with a
                            # generic version so future formats don't need
                            # a new flag added by hand each time.
_SDL = None
_IMG = None
_have_linear_stretch = False  # SDL_SoftStretchLinear -- SDL 2.0.16+ only,
                               # see decode_image_native()'s v0.1.91 note

SDL_PIXELFORMAT_RGB24 = 0x17101803  # confirmed via SDL_GetPixelFormatName()
SDL_PIXELFORMAT_ARGB8888 = 0x16362004  # confirmed against SDL2 pixels.h --
                                        # see decode_image_native()'s v0.1.91
                                        # note for why this is needed
IMG_INIT_JPG = 0x00000001
IMG_INIT_PNG = 0x00000002
IMG_INIT_TIF = 0x00000004
IMG_INIT_WEBP = 0x00000008
IMG_INIT_JXL = 0x00000010   # SDL2_image 2.6.0+ -- harmless no-op bit on
                             # older builds, see _init()'s comment below
IMG_INIT_AVIF = 0x00000020  # SDL2_image 2.6.0+ -- same as above

# v0.1.145: every format flag OR'd together -- "handle whatever shows up"
# per Kaleb's ask, rather than hand-picking formats one request at a time.
IMG_INIT_ALL = (IMG_INIT_JPG | IMG_INIT_PNG | IMG_INIT_TIF |
                IMG_INIT_WEBP | IMG_INIT_JXL | IMG_INIT_AVIF)

# Human-readable names for the bitmask, used to build SUPPORTED_FORMATS
# below from whatever IMG_Init() actually reports back.
_FORMAT_FLAGS = [
    ("JPG", IMG_INIT_JPG), ("PNG", IMG_INIT_PNG), ("TIF", IMG_INIT_TIF),
    ("WEBP", IMG_INIT_WEBP), ("JXL", IMG_INIT_JXL), ("AVIF", IMG_INIT_AVIF),
]


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
    global available, _SDL, _IMG, _have_linear_stretch
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

        # SDL_SoftStretchLinear (SDL 2.0.16+) does genuine bilinear-filtered
        # scaling; SDL_UpperBlitScaled's classic path is nearest-neighbor
        # (SDL_SoftStretch) with no filtering at all -- see decode_jpeg_
        # native()'s v0.1.91 note. Optional: older muOS SDL2 builds may not
        # have it, so this is allowed to fail without disabling native
        # decode entirely -- just falls back to the old nearest-neighbor
        # blit for the downscale step.
        try:
            sdl.SDL_SoftStretchLinear.restype = ctypes.c_int
            sdl.SDL_SoftStretchLinear.argtypes = [_SurfPtr, ctypes.POINTER(_SDL_Rect),
                                                    _SurfPtr, ctypes.POINTER(_SDL_Rect)]
            _have_linear_stretch = True
        except AttributeError:
            _have_linear_stretch = False

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
        _initted_flags = img.IMG_Init(IMG_INIT_ALL)
        # v0.1.145: IMG_Init returns a bitmask of the formats that ACTUALLY
        # initialized -- not every muOS/SDL2_image build ships every
        # format library (libpng/libtiff/libwebp/etc. are dlopen'd
        # per-format, confirmed via SDL2_image's own source), so we don't
        # assume a format worked just because we asked for it. Building
        # supported_formats from the real return value means JPEG (or any
        # other already-working format) keeps working even if some other
        # format's library is missing on a given device -- and any format
        # IMG_Init doesn't recognize at all (bit not defined on an older
        # SDL2_image build) is harmlessly just never set, no crash either
        # way (unrecognized bits in the request are simply ignored by
        # IMG_Init, confirmed via SDL2_image's docs).
        global supported_formats
        supported_formats = {name for name, flag in _FORMAT_FLAGS
                              if _initted_flags & flag}
    except (AttributeError, OSError):
        _SDL, _IMG = False, False
        available = False
        return

    _SDL, _IMG = sdl, img
    available = True


def decode_image_native(jpeg_bytes, scale_n=4):
    """Decode image bytes via libSDL2_image, returning (rgb_bytes, w, h) --
    same contract as mini_jpeg.decode_jpeg(). Despite the name (kept for
    call-site compatibility -- see decode_jpeg() in main.py), this handles
    ANY format IMG_Load_RW recognizes from the byte content itself (it
    auto-detects the format, no hint needed) -- v0.1.145 requests every
    format SDL2_image knows how to init (JPG/PNG/TIF/WEBP/JXL/AVIF -- see
    IMG_INIT_ALL), so a new format showing up in a future EPUB just works
    without this file needing another one-line change, as long as the
    device's SDL2_image build has that format's library available. Check
    supported_formats (a set of short names, e.g. {"JPG","PNG","WEBP"})
    if a caller ever needs to know what's actually usable on this device.
    Note: any source with an alpha channel (PNG, WEBP, AVIF) gets its
    alpha silently dropped by the RGB24 conversion below (same as any
    non-RGB24 source format) -- fine for a reader displaying page images,
    not a general-purpose image pipeline. Raises RuntimeError on any
    failure (library unavailable, decode failure, unrecognized format) so
    the caller can fall back to mini_jpeg.decode_jpeg() cleanly -- though
    that fallback is JPEG-only (see mini_jpeg.py), so a non-JPEG format on
    a device without native decode support has no fallback path; it'll
    fail to display rather than silently downgrading. Acceptable per
    Kaleb's "native engine only" ask.
    """
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
            # v0.1.91: SDL_UpperBlitScaled uses SDL2's classic SDL_SoftStretch
            # under the hood, which is NEAREST-NEIGHBOR with no filtering at
            # all (confirmed against the SDL2 wiki/changelog -- SDL_Soft
            # StretchLinear, added in 2.0.16, is the first bilinear-filtered
            # option). That's fine for a mild downscale, but for a large
            # cover/photo being reduced a lot (small scale_n), nearest-
            # neighbor throws away most source pixels instead of blending
            # them, producing visible blockiness -- exactly Kaleb's report
            # that some covers look "crisp" (small downscale ratio, artifact
            # not visible) and others "blocky" (large downscale ratio, same
            # artifact very visible). SDL_SoftStretchLinear requires two
            # SAME-FORMAT 32bpp surfaces, so this path converts to ARGB8888
            # for the stretch, then converts back to RGB24 to keep this
            # function's existing output contract (tight RGB24) unchanged
            # for every caller. Falls back to the old nearest-neighbor path
            # if SDL_SoftStretchLinear isn't available on this muOS's SDL2
            # build (see _have_linear_stretch).
            if _have_linear_stretch:
                src32 = _SDL.SDL_ConvertSurfaceFormat(surf, SDL_PIXELFORMAT_ARGB8888, 0)
                if not src32:
                    raise RuntimeError(f"SDL_ConvertSurfaceFormat (ARGB8888) failed: {_SDL.SDL_GetError()}")
                dst32 = _SDL.SDL_CreateRGBSurfaceWithFormat(0, out_w, out_h, 32, SDL_PIXELFORMAT_ARGB8888)
                if not dst32:
                    _SDL.SDL_FreeSurface(src32)
                    raise RuntimeError(f"SDL_CreateRGBSurfaceWithFormat (ARGB8888) failed: {_SDL.SDL_GetError()}")
                stretch_ok = _SDL.SDL_SoftStretchLinear(src32, None, dst32, None) == 0
                _SDL.SDL_FreeSurface(src32)
                if not stretch_ok:
                    _SDL.SDL_FreeSurface(dst32)
                    raise RuntimeError(f"SDL_SoftStretchLinear failed: {_SDL.SDL_GetError()}")
                dst = _SDL.SDL_ConvertSurfaceFormat(dst32, SDL_PIXELFORMAT_RGB24, 0)
                _SDL.SDL_FreeSurface(dst32)
                if not dst:
                    raise RuntimeError(f"SDL_ConvertSurfaceFormat (RGB24) failed: {_SDL.SDL_GetError()}")
            else:
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
