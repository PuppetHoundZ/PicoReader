"""
native_video.py

Current version: v26.07.20.38

Optional PicoReader feature: play JW.org video content (streamed directly
from jw-cdn.org, or downloaded local files) via muOS's native mpv or
ffplay binaries, with gamepad controls translated to each player's own
keyboard shortcuts via a self-contained Linux uinput virtual-keyboard --
no third-party binary (gptokeyb2/PortMaster) required. Fully MIT-licensed,
same as the rest of PicoReader; no bundled executables, no GPL component.

PLAYER SELECTION (v26.07.20.35): mpv is tried FIRST, ffplay is the
automatic fallback if mpv isn't found on a given device/build -- see
play_jw_video()'s own docstring for the full reasoning (mpv has a real
on-screen progress bar via --osd-bar, which ffplay structurally has no
equivalent for; also Kaleb's own confirmed working default for
downloaded videos already). Both players share close-enough default
keybindings (space/p=pause, q=quit, arrow-key seek) that switching
between them is invisible to whoever's holding the controller -- see
_MPV_INPUT_CONF for the small bundled config that makes mpv's bindings
match ffplay's exactly, plus adds a real +-10 minute skip (L1/R1 ->
Page Up/Down) for long (up to ~1hr) JW videos.

WHY UINPUT INSTEAD OF gptokeyb2: confirmed against muOS's own real source
(func.sh's GPTOKEYB() helper) that even muOS's own built-in Media Player
pulls the gptokeyb2 BINARY from PortMaster's install directory at runtime
-- meaning it is not guaranteed present on a stock muOS install (PortMaster
is a separate, optional setup step per muOS's own docs). Kaleb wants
PicoReader to remain a fully native app with no PortMaster dependency, so
this module implements the same underlying mechanism gptokeyb2 itself is
built on (Linux's /dev/uinput virtual-input-device API) directly, as
PicoReader's own code -- one implementation shared by both players, since
uinput key injection is player-agnostic (it's OS-level, not talking to
mpv/ffplay directly at all).

SCOPE (deliberate): JW.org sources only -- jw.org, wol.jw.org, jw-cdn.org.
No general "any URL" or "any local file" support. Every URL is validated
against JW_ALLOWED_DOMAINS before either player is ever invoked with it.

SECURITY: subprocess.run() is called with an argument LIST, never a shell
string -- no os.system()/os.execute()-style string interpolation anywhere
in this file, so a malicious/spoofed URL can't inject shell commands. This
is the one place in PicoReader that does real subprocess execution; every
other file in this project deliberately has none (see main.py's own
security-audit note). Scope is kept as narrow as possible specifically to
limit what that means in practice: validated JW-domain HTTPS URLs, or a
local file path this app itself just downloaded to ROMS/movies.

STATUS: CONFIRMED WORKING on real RG CubeXX-H hardware -- the uinput
device-creation/key-injection pipeline is proven functional (the B/quit
key specifically was exercised repeatedly, on purpose, throughout the
whole leftover-video-frame bug investigation -- see main.py's own AI
notes for that), and streaming/downloaded-file playback both work.
A/D-pad haven't been individually singled out in an explicit report the
way B has, but they share the exact same injection mechanism, so
there's no real reason to expect them to behave differently. The mpv
path specifically (added v26.07.20.35) is NOT yet confirmed on real
hardware -- logic-reviewed and dry-run tested only so far (mocked
subprocess calls, real input.conf file-write verified). Needs real
on-device verification before treating it as equally proven: does mpv
actually launch cleanly under muOS's confirmed KMSDRM-direct display
model; does --osd-bar render as expected; does the bundled input.conf
get picked up correctly; do L1/R1 actually deliver the +-10 minute
skip. The ffplay fallback path remains exactly as proven as before --
if mpv turns out to have any real-hardware issue, ffplay is still there
as a working path while mpv gets sorted out.
"""

import ctypes
import fcntl
import os
import struct
import subprocess
import threading
import time
import urllib.parse


# ---------------------------------------------------------------------------
# JW.org domain allowlist (same convention already used by jw_fetch.py for
# downloads -- applied here to streaming too).
JW_ALLOWED_DOMAINS = ("jw.org", "wol.jw.org", "jw-cdn.org")


def is_jw_video_url(url):
    """True only for https:// URLs whose host is exactly one of
    JW_ALLOWED_DOMAINS or a subdomain of one of them (e.g.
    "b.jw-cdn.org" matches "jw-cdn.org"; "notjw-cdn.org" does not --
    checked via a leading-dot boundary, not a bare suffix match)."""
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return False
    if parts.scheme != "https" or not parts.hostname:
        return False
    host = parts.hostname.lower()
    return any(host == d or host.endswith("." + d) for d in JW_ALLOWED_DOMAINS)


# ---------------------------------------------------------------------------
# v26.07.20.15 (Kaleb's request): conditional pre-video memory trim.
# Deliberately NOT unconditional -- gc.collect()/malloc_trim() are not
# free (can pause tens to a couple hundred ms depending on what's
# allocated), so paying that cost before EVERY video, including short
# clips with no real memory pressure, would add a small consistent
# delay to the common case for no benefit. Instead this only acts when
# MemAvailable (Linux kernel's own "how much could actually be freed up
# for a new allocation" estimate -- NOT MemFree, which undercounts
# reclaimable cache/buffer memory) is genuinely low.
LOW_MEM_THRESHOLD_KB = 80 * 1024  # 80MB -- see maybe_trim_memory() docstring.
# v26.07.20.17 (Kaleb's request): lowered from 150MB. 150MB was a
# generous "definitely safe" guess, not measured. Kaleb correctly noted
# ffplay's own software-decode footprint at 480p/720p is genuinely small
# (tens of MB, not hundreds -- consistent with general embedded-Linux/
# RPi video player figures). 80MB is a middle ground: closer to what
# ffplay itself actually needs, while still leaving real headroom above
# that footprint for muOS's own background allocations and the gap
# between this check and ffplay finishing its own startup allocations --
# matching ffplay's footprint exactly would leave ~zero margin for
# anything else blipping during that window, which is exactly the
# scenario that causes an OOM-kill. Not derived from real on-device
# MemAvailable numbers yet -- the per-call logging added in v26.07.20.16
# is what should ultimately settle this: if real reading-session
# MemAvailable never approaches even 150MB in practice, that's the
# stronger signal for where this number truly belongs.


def get_mem_available_kb():
    """Returns /proc/meminfo's MemAvailable in KB, or None if it can't be
    read (e.g. not running on Linux, or the file format changes) --
    caller should treat None as "unknown, skip the check" rather than
    assuming either high or low pressure."""
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1])
    except Exception:
        pass
    return None


def _rss_kb():
    """Best-effort self RSS in KB via /proc/self/status -- for the
    before/after trim log line only, not used for the trim decision
    itself (that's MemAvailable, a system-wide figure, not this
    process's own RSS)."""
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1])
    except Exception:
        pass
    return None


def maybe_trim_memory(clear_caches_fn):
    """Checks real available RAM and, ONLY if it's below
    LOW_MEM_THRESHOLD_KB, calls `clear_caches_fn()` (caller-supplied --
    main.py's own texture-cache clearing, since this module has no
    knowledge of the reader's SDL state) then runs gc.collect() and
    glibc's malloc_trim(0) to actually hand freed memory back to the OS
    (gc.collect() alone frees it back to Python's/SDL's own allocator,
    but glibc doesn't always release that to the OS without an explicit
    trim). 80MB threshold: closer to ffplay's own real footprint while
    still leaving headroom for other allocations during the startup
    window (see LOW_MEM_THRESHOLD_KB's own comment for the reasoning) --
    not so low that it's basically "never fires". Returns True if a trim actually
    ran, False if skipped (either because there was enough headroom, or
    because MemAvailable couldn't be read at all -- fails safe by doing
    nothing rather than guessing). Best-effort: any exception from
    clear_caches_fn() itself is NOT caught here -- that's the caller's
    own reader-state logic and a bug there should surface normally, not
    be silently swallowed by this helper.

    v26.07.20.16 (Kaleb's question -- "how would I know if this is
    doing anything"): EVERY call now logs one line to FFPLAY_LOG with
    the MemAvailable reading and whether it skipped or trimmed, so a
    normal reading/video session on-device produces a visible record
    with no SSH/live-monitoring needed -- just check the log file
    afterward. When it DOES trim, also logs this process's own RSS
    before/after, so "did it actually free real memory" is answerable
    from the log alone, not just "did it decide to try"."""
    available = get_mem_available_kb()
    if available is None:
        _ffplay_log("[mem] MemAvailable unreadable -- skipped\n")
        return False
    if available >= LOW_MEM_THRESHOLD_KB:
        _ffplay_log(f"[mem] MemAvailable={available}KB (>= {LOW_MEM_THRESHOLD_KB}KB "
                     f"threshold) -- skipped, no trim needed\n")
        return False
    rss_before = _rss_kb()
    clear_caches_fn()
    import gc
    gc.collect()
    try:
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass  # non-glibc libc, or trim unavailable -- gc.collect() alone still helped some
    rss_after = _rss_kb()
    available_after = get_mem_available_kb()
    _ffplay_log(f"[mem] MemAvailable={available}KB (< {LOW_MEM_THRESHOLD_KB}KB threshold) "
                f"-- TRIMMED. RSS {rss_before}KB -> {rss_after}KB, "
                f"MemAvailable now {available_after}KB\n")
    return True




# ---------------------------------------------------------------------------
# ffplay discovery -- confirmed native to muOS (per Kaleb, and per muOS's
# own documented built-in Media Player system, which lists FFPlay as its
# default engine: muos.dev/systems/misc/mediaplayer). Checked at the
# standard system path first, falling back to PATH lookup for safety
# across muOS builds/devices.
_FFPLAY_CANDIDATES = ("/usr/bin/ffplay", "ffplay")


def find_ffplay():
    for candidate in _FFPLAY_CANDIDATES:
        if os.path.isabs(candidate):
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
        else:
            from shutil import which
            found = which(candidate)
            if found:
                return found
    return None


# ---------------------------------------------------------------------------
# Minimal Linux uinput bridge -- creates a virtual keyboard device and
# injects key press/release events. Constants below are the standard
# stable Linux kernel UAPI values (linux/input-event-codes.h,
# linux/uinput.h), not muOS-specific.

_UINPUT_PATH = "/dev/uinput"

EV_SYN = 0x00
EV_KEY = 0x01
SYN_REPORT = 0

# Key codes ffplay's own keyboard shortcuts respond to.
KEY_SPACE = 57
KEY_Q = 16
KEY_LEFT = 105
KEY_RIGHT = 106
KEY_UP = 103
KEY_DOWN = 108
# v26.07.20.35: standard Linux evdev codes (linux/input-event-codes.h),
# same as the rest of this file -- not muOS-specific. Used for the new
# L1/R1 big-skip buttons (see _translate_loop).
KEY_PAGEUP = 104
KEY_PAGEDOWN = 109

_UI_SET_EVBIT = 0x40045564
_UI_SET_KEYBIT = 0x40045565
_UI_DEV_CREATE = 0x5501
_UI_DEV_DESTROY = 0x5502

# struct uinput_user_dev layout (older/portable UI_DEV_SETUP-free API):
# char name[UINPUT_MAX_NAME_SIZE=80]; struct input_id id (4x __u16 = 8
# bytes: bustype/vendor/product/version); __u32 ff_effects_max (4 bytes);
# then absmax[64]/absmin[64]/absfuzz[64]/absflat[64] (4 __s32 arrays of 64
# entries each = 1024 bytes) -- we leave all of that zeroed (this is a
# keyboard, not an absolute-axis device). Real kernel struct size is
# 80+8+4+1024 = 1116 bytes; verified against struct.calcsize() to catch
# any format-string drift before it silently writes a malformed device
# descriptor to the kernel.
_UINPUT_MAX_NAME_SIZE = 80
_UINPUT_USER_DEV_FMT = f"<{_UINPUT_MAX_NAME_SIZE}s HHHH I 1024x"
_DEVICE_NAME = b"PicoReader Virtual Keyboard"
assert struct.calcsize(_UINPUT_USER_DEV_FMT) == 1116, (
    "uinput_user_dev struct packing drifted from the real kernel size -- "
    "fix _UINPUT_USER_DEV_FMT before this is used")

# struct input_event layout: timeval (long sec, long usec -- 8 bytes each
# on 64-bit aarch64), then uint16 type, uint16 code, int32 value.
_INPUT_EVENT_FMT = "<qqHHi"


def _emit(fd, ev_type, code, value):
    ts = time.time()
    sec = int(ts)
    usec = int((ts - sec) * 1_000_000)
    os.write(fd, struct.pack(_INPUT_EVENT_FMT, sec, usec, ev_type, code, value))


class VirtualKeyboard:
    """Context-manager wrapper around a /dev/uinput virtual keyboard.
    Returns None from create() (never raises) if uinput isn't available
    or accessible -- callers treat that as "no gamepad controls this
    session" and still let the video play, rather than failing the whole
    feature over an input-translation nicety."""

    def __init__(self, fd):
        self._fd = fd

    @classmethod
    def create(cls):
        try:
            fd = os.open(_UINPUT_PATH, os.O_WRONLY | os.O_NONBLOCK)
        except OSError:
            return None
        try:
            fcntl.ioctl(fd, _UI_SET_EVBIT, EV_KEY)
            for key in (KEY_SPACE, KEY_Q, KEY_LEFT, KEY_RIGHT, KEY_UP, KEY_DOWN,
                        KEY_PAGEUP, KEY_PAGEDOWN):
                fcntl.ioctl(fd, _UI_SET_KEYBIT, key)
            dev = struct.pack(_UINPUT_USER_DEV_FMT, _DEVICE_NAME, 0x03, 0x1234, 0x5678, 1, 0)
            os.write(fd, dev)
            fcntl.ioctl(fd, _UI_DEV_CREATE)
        except OSError:
            try:
                os.close(fd)
            except OSError:
                pass
            return None
        # Give the kernel/udev a beat to register the new input device
        # before anything tries to use it -- same short settle delay
        # gptokeyb2 itself effectively gets from process-startup overhead.
        time.sleep(0.1)
        return cls(fd)

    def tap(self, key):
        """Press and release, with a real SYN_REPORT after each half --
        ffplay (like most terminal/X11 input consumers) only sees a key
        event once EV_SYN/SYN_REPORT flushes it."""
        try:
            _emit(self._fd, EV_KEY, key, 1)
            _emit(self._fd, EV_SYN, SYN_REPORT, 0)
            _emit(self._fd, EV_KEY, key, 0)
            _emit(self._fd, EV_SYN, SYN_REPORT, 0)
        except OSError:
            pass

    def close(self):
        try:
            fcntl.ioctl(self._fd, _UI_DEV_DESTROY)
        except OSError:
            pass
        try:
            os.close(self._fd)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Joystick -> ffplay key translation.
#
# v26.07.20.02: rewritten to match PicoReader's REAL input model, found by
# reading main.py's own event loop directly rather than assuming. main.py
# reads input entirely via SDL_PollEvent() (SDL_JOYBUTTONDOWN_EV /
# SDL_JOYHATMOTION_EV events) -- it never calls SDL_JoystickGetButton() or
# SDL_JoystickUpdate() anywhere, and the SDL_JoystickOpen(0) return value
# isn't even stored. An earlier draft of this module polled joystick state
# directly, which doesn't match how this app (or this SDL setup) actually
# works, and would not have functioned correctly. This version instead
# runs its own SDL_PollEvent() loop, using the identical ctypes struct
# layouts main.py's own input loop uses (copied field-for-field, not
# re-derived) so there's no risk of a mismatched struct silently misreading
# event data. Safe to run on a background thread here specifically because
# the main thread is blocked inside subprocess.run() for ffplay's entire
# duration -- nothing else is polling the event queue concurrently during
# that window.
#
# Button mapping passed in as JOY_A/JOY_B (main.py's own runtime-detected,
# device-specific SDL button indices -- see main.py's _sdl_map lookup) so
# this stays correctly mapped across devices rather than hardcoding index
# values here.

SDL_JOYHATMOTION_EV = 0x602
SDL_JOYBUTTONDOWN_EV = 0x603
SDL_HAT_UP = 1
SDL_HAT_RIGHT = 2
SDL_HAT_DOWN = 4
SDL_HAT_LEFT = 8

_POLL_INTERVAL = 0.01  # SDL_PollEvent itself is non-blocking; this just
                        # caps CPU use between empty polls.


def _make_event_types():
    """Builds the same ctypes structs main.py's own poll loop uses,
    field-for-field identical -- kept local to this function (not
    module-level) since they're only needed inside _translate_loop, same
    scoping main.py itself uses for these."""
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

    return SDL_JoyHatEvent, SDL_JoyButtonEvent


def _translate_loop(sdl, joy_a, joy_b, vkbd, stop_event, joy_l1=None, joy_r1=None):
    SDL_JoyHatEvent, SDL_JoyButtonEvent = _make_event_types()
    ev_buf = (ctypes.c_byte * 56)()

    while not stop_event.is_set():
        while sdl.SDL_PollEvent(ctypes.byref(ev_buf)) != 0:
            etype = ctypes.cast(ev_buf, ctypes.POINTER(ctypes.c_uint32))[0]
            if etype == SDL_JOYBUTTONDOWN_EV:
                bev = ctypes.cast(ev_buf, ctypes.POINTER(SDL_JoyButtonEvent))[0]
                if bev.button == joy_a:
                    vkbd.tap(KEY_SPACE)   # A -- pause/play
                elif bev.button == joy_b:
                    vkbd.tap(KEY_Q)       # B -- quit
                # v26.07.20.35 (Kaleb's request -- long JW videos, up to
                # ~1hr, need a coarser jump than +-10s/+-1min alone).
                # L1/R1 -> Page Up/Down -> a real, exact +-10 minute
                # seek via the bundled mpv input.conf (see its own
                # comment above); on ffplay this still works too via
                # ffplay's own native PGUP/PGDOWN handling, just with
                # ffplay's chapter-dependent fallback behavior instead
                # of an unconditional guarantee. Optional -- None is
                # always safe, same tolerant pattern as joy_a/joy_b.
                elif joy_l1 is not None and bev.button == joy_l1:
                    vkbd.tap(KEY_PAGEDOWN)  # L1 -- skip back ~10 min
                elif joy_r1 is not None and bev.button == joy_r1:
                    vkbd.tap(KEY_PAGEUP)    # R1 -- skip forward ~10 min
            elif etype == SDL_JOYHATMOTION_EV:
                hev = ctypes.cast(ev_buf, ctypes.POINTER(SDL_JoyHatEvent))[0]
                hv = hev.value
                if hv & SDL_HAT_LEFT:
                    vkbd.tap(KEY_LEFT)    # seek -10s
                elif hv & SDL_HAT_RIGHT:
                    vkbd.tap(KEY_RIGHT)   # seek +10s
                elif hv & SDL_HAT_UP:
                    vkbd.tap(KEY_UP)      # seek +1min
                elif hv & SDL_HAT_DOWN:
                    vkbd.tap(KEY_DOWN)    # seek -1min
        time.sleep(_POLL_INTERVAL)


# v26.07.20.13 (Kaleb's request -- cleanup #1): base ffplay args
# collapsed into one named constant instead of being built inline inside
# play_jw_video(), so the full flag set is readable/auditable in one
# place. Same behavior as v26.07.20.12, no functional change.
_FFPLAY_BASE_ARGS = [
    "-fs", "-framedrop",
    "-reconnect", "1", "-reconnect_streamed", "1",
    "-reconnect_at_eof", "1", "-reconnect_delay_max", "2",
    # v26.07.20.14 (Kaleb's request -- bug check #3): -rw_timeout is an
    # HTTP-protocol read/write timeout in MICROSECONDS. Without it, a
    # connection that hangs (accepted but never sends data -- distinct
    # from a hard failure, which -reconnect already covers) has no
    # bound at all: ffplay just sits there indefinitely with no
    # feedback to the user and no chance for -reconnect logic to kick
    # in, since that only fires on an actual completed
    # failure/disconnect, not a stall. 15s is generous enough to not
    # false-positive on a slow-but-working connection while still
    # failing a truly dead one in reasonable time. Harmlessly ignored
    # for local file playback, same as the reconnect flags.
    "-rw_timeout", "15000000",
]

# v26.07.20.13 (Kaleb's request -- cleanup #2): ffplay's own stderr, at
# "error" verbosity, is appended here instead of being discarded via
# "-loglevel quiet". Previously a real ffplay crash on-device left NO
# trail at all -- just "video stopped" with nothing to go on. Mirrors
# main.py's own CRASH_LOG convention (/tmp/picoreader_crash.log) but
# kept in a separate file so a long JW-video session doesn't interleave
# with/bloat the app's own crash log.
FFPLAY_LOG = "/tmp/picoreader_ffplay.log"
# v26.07.20.18 (Kaleb's request -- log hygiene): caps FFPLAY_LOG at 1MB,
# same convention/cap as main.py's CRASH_LOG (LOG_CAP_BYTES) -- this log
# now fires on EVERY video play (v26.07.20.16 mem-trim logging), not
# just failures, so it's the more likely of the two to actually grow
# large over time. Simple truncate-on-cap, not real rotation -- same
# reasoning as CRASH_LOG's own comment.
_FFPLAY_LOG_CAP_BYTES = 1024 * 1024

# NOT included in _FFPLAY_BASE_ARGS: any -hwaccel/-codec:v h264_v4l2m2m
# flag. Whether this SoC + muOS's bundled ffmpeg build actually expose a
# working hardware decoder is UNVERIFIED -- ffplay itself has a history
# of not supporting -hwaccel reliably even on devices where ffmpeg does.
# Needs a real on-device check (`ffmpeg -decoders | grep v4l2` via
# SSH/telnet) before ever adding this -- do not guess.


def _ffplay_log(msg):
    try:
        if os.path.exists(FFPLAY_LOG) and os.path.getsize(FFPLAY_LOG) > _FFPLAY_LOG_CAP_BYTES:
            os.remove(FFPLAY_LOG)
        with open(FFPLAY_LOG, "a") as f:
            f.write(msg)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# mpv discovery -- confirmed present on muOS as a selectable Media Player
# core (same as ffplay), and confirmed by Kaleb as already his real
# default player for downloaded videos on his own device. Same
# candidate-list-then-PATH-fallback pattern as find_ffplay().
_MPV_CANDIDATES = ("/usr/bin/mpv", "mpv")


def find_mpv():
    for candidate in _MPV_CANDIDATES:
        if os.path.isabs(candidate):
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
        else:
            from shutil import which
            found = which(candidate)
            if found:
                return found
    return None


# v26.07.20.35 (Kaleb's request -- switching to mpv, primarily for its
# real OSD progress bar, which ffplay structurally has no equivalent
# for -- confirmed via ffmpeg-devel's own mailing list history). Custom
# mpv input.conf, written to disk once per launch (tiny file, cheap):
# SPACE/p/q/arrows match ffplay's existing bindings exactly (same feel,
# no retraining), and PGUP/PGDOWN are EXPLICITLY bound to a real
# seek +-600 command -- this is actually a real improvement over
# ffplay's own page-up/down behavior, which only falls back to a plain
# 10-minute jump when a file has NO chapters; ours is unconditional and
# exact regardless of chapter data, which JW videos don't have anyway.
# This is what backs the new L1/R1 "skip a lot" buttons for long
# (up to ~1 hour) JW videos -- see _translate_loop's own comment.
_MPV_INPUT_CONF_PATH = "/tmp/picoreader_mpv_input.conf"
_MPV_INPUT_CONF = """\
SPACE cycle pause
p cycle pause
q quit
LEFT seek -10
RIGHT seek 10
UP seek 60
DOWN seek -60
PGUP seek 600
PGDWN seek -600
"""


def _write_mpv_input_conf():
    """Best-effort -- if this fails, mpv just falls back to its OWN
    built-in default bindings (which are close enough for the basics:
    space/p=pause, q=quit, arrows=seek -- only the exact seek amounts
    and the big L1/R1 jump wouldn't match). Never raises."""
    try:
        with open(_MPV_INPUT_CONF_PATH, "w") as f:
            f.write(_MPV_INPUT_CONF)
        return True
    except Exception:
        return False


# mpv's own defaults for everything not overridden above: --fs already
# applied via the CLI flag below; --panscan=1.0 (fill_screen mode) is
# mpv's built-in "zoom to fill, cropping overflow" -- genuinely simpler
# than ffplay's manual scale+crop -vf filter chain, same visual result.
#
# v26.07.20.37 (Kaleb's request -- checked muOS's own actual mpv
# invocation directly, github.com/MustardOS/internal
# script/launch/ext-mpv.sh): its real, shipped, tested command is
# "--no-config --fullscreen --keepaspect=yes --video-zoom=0
# --video-align-x=0 --video-align-y=0" -- notably, NO --vo override at
# all (settles the earlier "should we force --vo=drm for weak-GPU
# safety" question: muOS's own team, who tested this across their real
# supported devices, didn't feel the need to override mpv's own default
# vo selection either -- dropped that idea, no real evidence supported
# it). Also confirmed muOS's own script has ZERO reconnect/framedrop/
# osd-bar/msg-level flags -- our additions here are genuine value-adds
# on top of muOS's bare-minimum baseline, not in conflict with anything
# proven. Adopted --no-config from muOS's own script: prevents any
# stray user mpv config file on the device from silently interfering
# with these settings -- same defensive reasoning muOS's own team
# already applied.
_MPV_BASE_ARGS = [
    "--no-config",
    "--fs",
    "--osd-bar", "--osd-level=1",   # the whole reason for this switch
    "--framedrop=vo",               # same reasoning as ffplay's -framedrop
    "--network-timeout=15",         # same reasoning as ffplay's -rw_timeout
    "--msg-level=all=error",        # same reasoning as ffplay's -loglevel error
    # v26.07.20.36 BUG FIX (found during a requested re-review, not a
    # live report): this previously only passed
    # "reconnect_streamed=1,reconnect_delay_max=2" -- MISSING the base
    # "reconnect=1" and "reconnect_at_eof=1" flags. reconnect_streamed is
    # an ADDITIONAL flag on top of the base reconnect option in
    # ffmpeg/libavformat (which mpv uses directly for network streams
    # via --stream-lavf-o) -- without reconnect=1 also set, plain HTTP
    # reconnect likely never triggered at all, meaning this network-
    # resilience feature was silently incomplete since it first shipped.
    # Now matches the ffplay path's own complete, already-established
    # four-flag set exactly (see _FFPLAY_BASE_ARGS above).
    "--stream-lavf-o=reconnect=1,reconnect_streamed=1,reconnect_at_eof=1,reconnect_delay_max=2",
]


# ---------------------------------------------------------------------------
def play_jw_video(source, is_local, sdl=None, joy_a=None, joy_b=None,
                   fill_screen=False, screen_w=None, screen_h=None,
                   joy_l1=None, joy_r1=None, player_pref="auto"):
    """Plays a JW.org video, fullscreen, blocking until it exits.
    `source` is either a local file path (is_local=True) or a validated
    https:// JW-domain URL (is_local=False) -- validation is the
    CALLER's responsibility via is_jw_video_url() before this is ever
    invoked, same pattern as gutenberg_fetch.py's download-time checks.
    `sdl` is the app's already-imported SDL module; `joy_a`/`joy_b` are
    main.py's own runtime-detected JOY_A/JOY_B button-index constants
    (see main.py's _sdl_map-derived globals) -- pass all three to get
    gamepad controls, or omit them to just play without controls.
    `joy_l1`/`joy_r1` (optional) add the big +-10min skip buttons -- see
    _translate_loop's own comment. If uinput isn't available on this
    device, video still plays, just without gamepad controls; caller
    should toast that if sdl/joy_a/joy_b were passed but the vkbd
    failed to init (checked via the returned message).

    v26.07.20.35 (Kaleb's request): PLAYER SELECTION -- mpv is tried
    FIRST by default (Kaleb's own confirmed real default for downloaded
    videos on his device already, and the only way to get a real OSD
    progress bar -- ffplay structurally has no equivalent, confirmed via
    ffmpeg-devel's own mailing list history of a never-mainlined patch
    proposal). Falls back to ffplay automatically if mpv isn't found on
    a given device/build -- same tolerant discovery pattern already
    used everywhere else in this file (native_image.py's libSDL2_image
    fallback to mini_jpeg.py is the same shape). Both players share the
    same basic keybindings (space/p=pause, q=quit, arrows=seek) so
    switching between them is invisible to the person holding the
    controller either way.

    v26.07.20.38 (Kaleb's request): `player_pref` -- "auto" (default,
    behavior described above), "mpv", or "ffplay" for an explicit manual
    override. Even with an explicit choice, this STILL falls back to
    the other player if the preferred one genuinely isn't found on this
    device -- same tolerant philosophy as "auto" and as every other
    player-discovery path in this file; an explicit preference means
    "prefer this one", not "only this one, fail hard otherwise".

    `fill_screen` picks between two scaling modes -- same concept as
    CTupe's own FILL_VF_ARG/FIT_VF_ARG split, driven by the CALLER's
    real per-device SW/SH so "fill" is correct on every aspect ratio
    PicoReader itself already supports:
      - fill_screen=False (default): letterboxed/pillarboxed fit,
        preserving aspect ratio, nothing cropped or stretched. mpv:
        its own default behavior (no extra flag needed). ffplay: no
        -vf filter at all, same reasoning.
      - fill_screen=True: crop-to-fill, no letterbox bars, no
        distortion -- some edge content is cropped for any video whose
        native aspect ratio doesn't match the device's. mpv: a single
        "--panscan=1.0" flag (mpv's own built-in zoom-to-fill). ffplay:
        the existing manual "-vf scale=W:H:...,crop=W:H" filter chain
        (v26.07.20.10's fix, kept for the fallback path). If
        fill_screen=True but screen_w/screen_h weren't given, silently
        falls back to fit rather than guessing a resolution.
    Returns (ok: bool, message: str | None)."""
    if not is_local and not is_jw_video_url(source):
        return False, "Not a JW.org video source"
    if is_local and not os.path.isfile(source):
        return False, "Video file not found"

    # v26.07.20.38: explicit player_pref still falls back to the other
    # player if the preferred one isn't found -- "prefer", not "only".
    if player_pref == "ffplay":
        player_bin = find_ffplay()
        using_mpv = False
        if not player_bin:
            player_bin = find_mpv()
            using_mpv = player_bin is not None
    else:  # "auto" or "mpv" (or any unrecognized value -- fail safe to auto)
        player_bin = find_mpv()
        using_mpv = player_bin is not None
        if not using_mpv:
            player_bin = find_ffplay()
    if not player_bin:
        return False, "No video player (mpv or ffplay) found on this device"

    want_controls = sdl is not None and joy_a is not None and joy_b is not None
    vkbd = VirtualKeyboard.create() if want_controls else None
    stop_event = threading.Event()
    thread = None
    if vkbd is not None:
        thread = threading.Thread(
            target=_translate_loop, args=(sdl, joy_a, joy_b, vkbd, stop_event, joy_l1, joy_r1),
            daemon=True)
        thread.start()

    if using_mpv:
        # v26.07.20.36 BUG FIX (found during a requested re-review, not
        # a live report): previously always passed --input-conf
        # regardless of whether the write actually succeeded, pointing
        # mpv at a possibly-nonexistent file -- unclear/unverified
        # whether mpv treats that as a hard launch failure or a soft
        # warn-and-continue, so better not to risk it. Now only include
        # the flag if the write actually succeeded; otherwise mpv just
        # falls back to its own built-in default bindings (still gives
        # pause/quit/basic seek, just without the custom L1/R1 mapping
        # and without matching ffplay's exact seek amounts) rather than
        # risk breaking every mpv launch over one failed file write.
        input_conf_ok = _write_mpv_input_conf()
        args = list(_MPV_BASE_ARGS)
        if input_conf_ok:
            args += [f"--input-conf={_MPV_INPUT_CONF_PATH}"]
        # v26.07.20.36 BUG FIX: previously gated on
        # "fill_screen and screen_w and screen_h", inherited from
        # ffplay's branch below -- but that requirement is ffplay-
        # specific (its manual scale+crop needs explicit numbers).
        # mpv's --panscan=1.0 is a relative zoom-to-fill flag and needs
        # no dimensions at all; gating it on screen_w/screen_h being
        # truthy meant fill_screen could silently fail to apply on mpv
        # in any edge case where those happened to be None/0, even
        # though nothing was actually stopping it from working.
        if fill_screen:
            args += ["--panscan=1.0"]
        else:
            # v26.07.20.37: explicit fit-mode flags matching muOS's own
            # real ext-mpv.sh exactly, rather than relying on mpv's bare
            # defaults to happen to produce the same letterboxed result
            # -- removes any doubt, since this is the literal invocation
            # muOS's own built-in Media Player uses and has presumably
            # been tested against every supported device.
            args += ["--keepaspect=yes", "--video-zoom=0",
                     "--video-align-x=0", "--video-align-y=0"]
        args = [player_bin] + args + [source]
    else:
        args = list(_FFPLAY_BASE_ARGS)
        if fill_screen and screen_w and screen_h:
            w, h = int(screen_w), int(screen_h)
            args += ["-vf", f"scale={w}:{h}:force_original_aspect_ratio=increase:"
                             f"flags=fast_bilinear,crop={w}:{h}"]
        args = [player_bin] + args + [source, "-autoexit", "-loglevel", "error"]

    try:
        result = subprocess.run(args, check=False, stderr=subprocess.PIPE, text=True)
        if result.stderr:
            _ffplay_log(f"\n--- {source} ({'mpv' if using_mpv else 'ffplay'}) ---\n{result.stderr}")
    except OSError as e:
        return False, f"Couldn't start {'mpv' if using_mpv else 'ffplay'}: {e}"
    finally:
        stop_event.set()
        if thread is not None:
            thread.join(timeout=2)
        if vkbd is not None:
            vkbd.close()

    # v26.07.20.14 BUG FIX (Kaleb's request -- bug check): previously
    # this always returned (True, None) regardless of how the player
    # actually exited, so a real failure (bad URL, dead connection,
    # corrupt stream) was silently reported to the caller as a normal
    # successful playback session -- the UI had zero way to tell the
    # difference from the user just watching the whole video and
    # quitting normally. Both players exit 0 on a clean end-of-file or
    # a normal user quit; a non-zero code means it actually failed to
    # play. Surface that, with a short reason pulled from stderr (first
    # non-empty line only -- verbose players can be multi-line and this
    # becomes a toast message, not a log dump; full detail is always in
    # FFPLAY_LOG regardless of which player was used).
    if result.returncode != 0:
        reason = next((ln for ln in result.stderr.splitlines() if ln.strip()),
                       None) if result.stderr else None
        msg = f"Video playback failed: {reason}" if reason else "Video playback failed"
        return False, msg

    if vkbd is None and want_controls:
        return True, "Played without gamepad controls (uinput unavailable)"
    return True, None
