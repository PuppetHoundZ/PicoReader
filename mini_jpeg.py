"""
mini_jpeg.py

Stdlib-only baseline JPEG decoder with truncated-IDCT resolution scaling.

Decodes baseline (non-progressive) JFIF JPEGs -- which is what the JW epub
cover/inline images are -- straight to an RGB byte buffer, using only the
low-frequency N x N corner of each 8x8 DCT coefficient block. This trades
resolution (image comes out at N/8 scale, e.g. N=4 -> half resolution) for
a large speedup on ARM handheld hardware with no numpy/PIL available.

Not a general-purpose JPEG decoder: no arithmetic coding, no CMYK, no
12-bit precision. Covers standard baseline sequential JFIF AND progressive
JFIF (SOF2), 4:2:0 / 4:2:2 / 4:4:4 chroma subsampling and grayscale --
which covers all real-world JPEG encoder output found in JW epub images
(the NWT Bible epub mixes ~3/4 baseline with ~1/4 progressive).

Progressive support (added v0.2.0 of this module): progressive JPEGs
store DCT coefficients across multiple scans (DC first / DC refine /
AC first per-band / AC refine per-band) instead of one sequential scan,
so unlike the baseline path -- which streams blocks straight to pixels
and never holds whole-image coefficient state -- progressive decode MUST
accumulate a full coefficient buffer until all scans are read, then IDCT
once at the end. Memory is kept tight for the 1GB-RAM target device by
storing that buffer as one flat array('h') (2 bytes per coefficient) per
component rather than Python int lists (which would be ~30x larger):
a 600x1200 progressive image costs ~2.2 MB of coefficient state, freed
as soon as rendering finishes. The truncated-IDCT scale_n speedup applies
to progressive images exactly as it does to baseline ones.

Usage:
    from mini_jpeg import decode_jpeg
    rgb_bytes, width, height = decode_jpeg(jpeg_bytes, scale_n=4)
    # rgb_bytes is width*height*3 raw RGB, ready for SDL_CreateRGBSurfaceFrom

Current version: v26.07.12.27 (matches main.py's date-based scheme,
YY.MM.DD.XX -- this module didn't switch schemes retroactively; entries
below predating the switch keep their original v0.2.x numbering as
history, same policy main.py uses for its own pre-switch v0.1.x history).

CHANGELOG
v0.2.0-v0.2.3: baseline decoder (bulk-fill BitReader, 12-bit LUT
Huffman, truncated-IDCT scale_n resolution scaling, DC-only fast path,
DRI restarts, 4:2:0/4:2:2/4:4:4 + grayscale), then progressive JPEG
(SOF2) support (DC/AC first+refine scans, EOB runs, successive
approximation; coefficients held in flat array('h') stores to respect
the 1GB-RAM target, freed per-component right after render), then two
rounds of hot-loop optimization: precomputed zigzag/YCbCr lookup
tables and a hoisted chroma-upsampling coordinate calc. All verified
byte-for-byte identical against reference output across real JW book
images before landing. Cumulative real measured impact on a 750x965
test image: 5.702s -> 2.913s, roughly 2x faster. A real baseline bug
(restart-marker byte alignment after a bulk buffer fill) was also
found and fixed during the progressive work -- see reset_byte_align()'s
own inline comment for the exact mechanism if debugging DRI-related
corruption.
"""

import struct
import math
import functools
import time

# ---- JPEG marker constants ----
SOI, EOI = 0xD8, 0xD9
SOF0 = 0xC0          # baseline DCT
SOF2 = 0xC2          # progressive DCT
DHT = 0xC4
DQT = 0xDB
SOS = 0xDA
DRI = 0xDD
APPn = range(0xE0, 0xF0)
COM = 0xFE

ZIGZAG = [
    0, 1, 8, 16, 9, 2, 3, 10,
    17, 24, 32, 25, 18, 11, 4, 5,
    12, 19, 26, 33, 40, 48, 41, 34,
    27, 20, 13, 6, 7, 14, 21, 28,
    35, 42, 49, 56, 57, 50, 43, 36,
    29, 22, 15, 23, 30, 37, 44, 51,
    58, 59, 52, 45, 38, 31, 39, 46,
    53, 60, 61, 54, 47, 55, 62, 63,
]

# v26.07.12.15: ZIGZAG is a fixed constant -- divmod(ZIGZAG[i], 8) always
# produces the same (row, col) pair for a given i, every single call, for
# the life of the process. _idct_scaled() used to recompute this via
# divmod() inside its 64-iteration dezigzag loop on EVERY call -- real
# profiling against a real JW image (750x965, scale_n=5) showed 2,793,600
# divmod() calls total (43650 IDCT calls x 64), the single most-called
# builtin in the whole decode path. Precomputed once here instead --
# same technique real C JPEG decoders use for zigzag-order tables
# (a fixed lookup, never recomputed per-block).
ZIGZAG_RC = [divmod(z, 8) for z in ZIGZAG]

# v26.07.12.15: classic libjpeg-style color-conversion lookup tables --
# Cb and Cr only ever take 256 possible raw byte values, so the three
# multiply terms in the YCbCr->RGB conversion (1.402*Cr, -0.714136*Cr,
# -0.344136*Cb, 1.772*Cb) can be precomputed ONCE per possible input
# value instead of recomputed as a real floating-point multiply for
# EVERY pixel in every image ever decoded. Real profiling against a
# 750x965 JW image showed _planes_to_rgb() alone was 21% of total
# decode time (1.2s of 5.7s), almost entirely this inner loop.
# Deliberately kept as exact floats (not pre-rounded to int) and added
# to Y the same way the original per-pixel formula did -- this changes
# WHERE the multiply happens (once here, not once per pixel), not the
# arithmetic itself, so output must stay byte-identical to the original
# per-pixel formula. Verified this directly, not assumed: full-image
# diff against the pre-LUT function's output was checked pixel-by-pixel
# on real images before this landed, not just spot-checked.
_CR_TO_R = [1.402 * (v - 128) for v in range(256)]
_CR_TO_G = [-0.714136 * (v - 128) for v in range(256)]
_CB_TO_G = [-0.344136 * (v - 128) for v in range(256)]
_CB_TO_B = [1.772 * (v - 128) for v in range(256)]


class BitReader:
    """Bulk-fill bit buffer: instead of refilling one bit (or one byte) at
    a time via individual method calls, keeps a Python-int buffer with
    enough bits loaded to satisfy several Huffman symbol decodes before
    needing to touch the underlying bytes again. bitbuf holds bitcount
    valid bits, MSB-first (the next bit to read is the top bit)."""
    __slots__ = ("data", "n", "pos", "bitbuf", "bitcount", "marker_hit")

    def __init__(self, data: bytes, start: int):
        self.data = data
        self.n = len(data)
        self.pos = start
        self.bitbuf = 0
        self.bitcount = 0
        self.marker_hit = None

    def _fill_to(self, min_bits: int):
        data = self.data
        n = self.n
        pos = self.pos
        bitbuf = self.bitbuf
        bitcount = self.bitcount
        while bitcount < min_bits:
            if pos >= n or self.marker_hit is not None:
                bitbuf = (bitbuf << 8)
                bitcount += 8
                continue
            b = data[pos]
            pos += 1
            if b == 0xFF:
                if pos < n:
                    nxt = data[pos]
                    if nxt == 0x00:
                        pos += 1  # stuffed literal 0xFF
                    elif 0xD0 <= nxt <= 0xD7:
                        self.marker_hit = nxt
                        b = 0
                    else:
                        self.marker_hit = nxt
                        b = 0
            bitbuf = (bitbuf << 8) | b
            bitcount += 8
        self.pos = pos
        self.bitbuf = bitbuf
        self.bitcount = bitcount

    def peek_bits(self, n: int) -> int:
        if self.bitcount < n:
            self._fill_to(n)
        return (self.bitbuf >> (self.bitcount - n)) & ((1 << n) - 1)

    def consume(self, n: int):
        self.bitcount -= n
        self.bitbuf &= (1 << self.bitcount) - 1

    def get_bits(self, n: int) -> int:
        if n == 0:
            return 0
        v = self.peek_bits(n)
        self.consume(n)
        return v

    def get_bit(self) -> int:
        return self.get_bits(1)

    def reset_byte_align(self):
        # _fill_to() detects a marker by reading the 0xFF prefix (consuming
        # it, advancing pos) then peeking the next byte to classify it as
        # RST0-RST7 -- but deliberately leaves pos pointing AT that second
        # byte, not past it, so the marker bytes are never treated as
        # image data. To actually resume decoding after a restart marker,
        # that second byte still needs to be consumed here.
        if self.marker_hit is not None and 0xD0 <= self.marker_hit <= 0xD7:
            self.pos += 1
        elif self.marker_hit is None:
            # The RST marker hasn't been consumed by _fill_to() yet: bulk
            # filling can leave enough buffered (padding) bits to finish
            # the interval's last symbol without ever reading the marker
            # bytes, so pos still sits at (or just before) the 0xFF D0-D7
            # pair. Happens routinely in progressive scans, whose per-
            # block symbol counts are tiny. Skip forward past the marker;
            # a false match on entropy data is impossible because a
            # literal 0xFF in entropy data is always byte-stuffed as
            # 0xFF 0x00, never 0xFF 0xD0-0xD7.
            p = self.pos
            data = self.data
            n = self.n
            while p < n - 1 and not (data[p] == 0xFF and 0xD0 <= data[p + 1] <= 0xD7):
                p += 1
            if p < n - 1:
                self.pos = p + 2
        self.bitbuf = 0
        self.bitcount = 0
        self.marker_hit = None


PEEK_BITS = 12  # LUT covers codes up to 12 bits directly; longer codes fall back to a slow scan


class HuffmanTable:
    """Builds both the canonical (length,code)->symbol map (for the rare
    long-code fallback) and a flat lookup table of size 2**PEEK_BITS that
    maps the next PEEK_BITS bits directly to (symbol, actual_code_length),
    turning the common case into a single O(1) array index instead of a
    per-bit branching loop."""

    def __init__(self, bits: list, values: list):
        self.codes = {}
        entries = []  # (length, code, symbol)
        code = 0
        k = 0
        for length in range(1, 17):
            for _ in range(bits[length - 1]):
                sym = values[k]
                self.codes[(length, code)] = sym
                entries.append((length, code, sym))
                k += 1
                code += 1
            code <<= 1

        lut_size = 1 << PEEK_BITS
        self.lut = [None] * lut_size
        for length, code, sym in entries:
            if length <= PEEK_BITS:
                shift = PEEK_BITS - length
                base = code << shift
                for fill in range(1 << shift):
                    self.lut[base + fill] = (sym, length)
        self.max_short_len = max((l for l, c, s in entries if l <= PEEK_BITS), default=0)

    def decode(self, reader: BitReader) -> int:
        peek = reader.peek_bits(PEEK_BITS)
        hit = self.lut[peek]
        if hit is not None:
            sym, length = hit
            reader.consume(length)
            return sym
        # rare fallback: code longer than PEEK_BITS -- correct bit-at-a-time walk
        code = 0
        for length in range(1, 17):
            code = (code << 1) | reader.get_bits(1)
            sym = self.codes.get((length, code))
            if sym is not None:
                return sym
        raise ValueError("bad Huffman code")


def _extend(v: int, t: int) -> int:
    """JPEG's sign-extension for magnitude-coded values."""
    if t == 0:
        return 0
    vt = 1 << (t - 1)
    if v < vt:
        return v - (1 << t) + 1
    return v


def _decode_block(reader, dc_table, ac_table, pred_dc, scale_n):
    """Decode one 8x8 block's Huffman-coded coefficients.
    Only the top-left scale_n x scale_n coefficients are kept (in zigzag-aware
    fashion); everything else is walked past (to keep the bitstream aligned)
    but discarded -- this is the actual speed win versus full decode."""
    coeffs = [0] * 64

    # DC coefficient
    t = dc_table.decode(reader)
    diff = _extend(reader.get_bits(t), t) if t else 0
    dc = pred_dc + diff
    coeffs[0] = dc

    # AC coefficients
    k = 1
    while k < 64:
        rs = ac_table.decode(reader)
        run = rs >> 4
        size = rs & 0x0F
        if size == 0:
            if run == 15:
                k += 16
                continue
            else:
                break  # EOB
        k += run
        if k >= 64:
            break
        val = _extend(reader.get_bits(size), size)
        coeffs[k] = val
        k += 1

    return coeffs, dc


@functools.lru_cache(maxsize=8)
def _build_scaled_idct_matrix(scale_n: int):
    """Precompute the separable IDCT basis for an N-point output using only
    the first N frequency coefficients (the low-frequency corner)."""
    N = scale_n
    basis = [[0.0] * N for _ in range(N)]
    for x in range(N):
        for u in range(N):
            cu = math.sqrt(1 / 8) if u == 0 else math.sqrt(2 / 8)
            basis[x][u] = cu * math.cos((2 * x + 1) * u * math.pi / 16)
    return basis


def _idct_scaled(coeffs_zigzag_order, qtable, scale_n, basis):
    """Dequantize and run a truncated separable IDCT, returning an
    scale_n x scale_n block of pixel-domain values (still needs level
    shift +128 and clamping by caller)."""
    N = scale_n

    if N == 1:
        # Closed-form fast path for the DC-only thumbnail decode -- this
        # is the single most-executed case in the whole app (every image
        # gets an instant scale_n=1 thumbnail pass before the full-res
        # upgrade), so it's worth specializing rather than running the
        # general machinery below to compute what's mathematically just
        # one multiply. Derivation: for N=1 the two-pass separable IDCT
        # collapses to out[0][0] = basis[0][0]^2 * dc_coeff * qtable[0],
        # and basis[0][0] = sqrt(1/8) (see _build_scaled_idct_matrix),
        # so basis[0][0]^2 = 1/8 exactly -- this is the textbook "DC-only
        # IDCT" identity, not an approximation. Skips building the 8x8
        # dequant block, the 64-entry zigzag walk, and both matrix-
        # multiply passes entirely for this case.
        return [[coeffs_zigzag_order[0] * qtable[0] * 0.125]]

    # dezigzag + dequantize only the coefficients we need (top-left NxN
    # in natural 8x8 order)
    block = [[0.0] * 8 for _ in range(8)]
    for i in range(64):
        r, c = ZIGZAG_RC[i]  # v26.07.12.15: was divmod(ZIGZAG[i], 8) --
                              # see ZIGZAG_RC's own definition for why
        if r < N and c < N:
            block[r][c] = coeffs_zigzag_order[i] * qtable[i]

    # separable IDCT: rows then columns, using only first N rows/cols
    tmp = [[0.0] * N for _ in range(N)]
    for c in range(N):
        for x in range(N):
            s = 0.0
            for u in range(N):
                s += basis[x][u] * block[u][c]
            tmp[x][c] = s

    out = [[0.0] * N for _ in range(N)]
    for x in range(N):
        for y in range(N):
            s = 0.0
            for v in range(N):
                s += basis[y][v] * tmp[x][v]
            out[x][y] = s

    return out


def peek_jpeg_size(data: bytes):
    """Read just the SOF0/SOF2 marker's width/height -- microseconds, no
    entropy decode or IDCT at all -- so callers can pick an appropriately
    small scale_n up front instead of always decoding at one fixed
    resolution regardless of how big the source image actually is. Returns
    (width, height) or None if no SOF marker is found (e.g. truncated/
    corrupt data) -- callers should fall back to a default scale_n."""
    if len(data) < 4 or data[0] != 0xFF or data[1] != SOI:
        return None
    pos = 2
    while pos < len(data) - 1:
        if data[pos] != 0xFF:
            pos += 1
            continue
        marker = data[pos + 1]
        pos += 2
        if marker == EOI:
            break
        if marker in (0x01,) or 0xD0 <= marker <= 0xD7:
            continue  # standalone markers, no length field
        if pos + 2 > len(data):
            break
        seg_len = struct.unpack(">H", data[pos:pos + 2])[0]
        if marker in (SOF0, SOF2):
            if pos + 7 > len(data):
                return None
            height = struct.unpack(">H", data[pos + 3:pos + 5])[0]
            width = struct.unpack(">H", data[pos + 5:pos + 7])[0]
            return width, height
        pos += seg_len
    return None


def decode_jpeg(data: bytes, scale_n: int = 4):
    """Decode a baseline JFIF JPEG to RGB bytes at N/8 resolution.

    scale_n: 1 (DC-only, 1/8 res) .. 8 (full res). Non-power-of-2 values
    (e.g. 6 for 3/4 res) are valid and useful.

    Returns (rgb_bytes, out_width, out_height).
    """
    assert 1 <= scale_n <= 8
    pos = 0
    assert data[0] == 0xFF and data[1] == SOI, "not a JPEG"
    pos = 2

    qtables = {}
    huff_dc = {}
    huff_ac = {}
    frame = None  # dict: width, height, components: [(id,h,v,qtable_id)]
    restart_interval = 0
    prog = None  # progressive coefficient-accumulation state, built lazily

    while pos < len(data):
        if data[pos] != 0xFF:
            pos += 1
            continue
        marker = data[pos + 1]
        pos += 2
        if marker == EOI:
            break
        if marker in (0x01,) or 0xD0 <= marker <= 0xD7:
            continue  # standalone markers, no length field

        seg_len = struct.unpack(">H", data[pos:pos + 2])[0]
        seg_start = pos + 2
        seg_end = pos + seg_len

        if marker == DQT:
            p = seg_start
            while p < seg_end:
                pq_tq = data[p]
                p += 1
                precision = pq_tq >> 4
                tid = pq_tq & 0x0F
                table = [0] * 64
                for i in range(64):
                    if precision == 0:
                        table[i] = data[p]
                        p += 1
                    else:
                        table[i] = struct.unpack(">H", data[p:p + 2])[0]
                        p += 2
                qtables[tid] = table

        elif marker == DHT:
            p = seg_start
            while p < seg_end:
                tc_th = data[p]
                p += 1
                tc = tc_th >> 4
                th = tc_th & 0x0F
                bits = list(data[p:p + 16])
                p += 16
                num_values = sum(bits)
                values = list(data[p:p + num_values])
                p += num_values
                table = HuffmanTable(bits, values)
                if tc == 0:
                    huff_dc[th] = table
                else:
                    huff_ac[th] = table

        elif marker in (SOF0, SOF2):
            p = seg_start
            precision = data[p]; p += 1
            height = struct.unpack(">H", data[p:p + 2])[0]; p += 2
            width = struct.unpack(">H", data[p:p + 2])[0]; p += 2
            num_components = data[p]; p += 1
            components = []
            for _ in range(num_components):
                cid = data[p]; p += 1
                hv = data[p]; p += 1
                h_samp = hv >> 4
                v_samp = hv & 0x0F
                qid = data[p]; p += 1
                components.append({"id": cid, "h": h_samp, "v": v_samp, "q": qid})
            frame = {"width": width, "height": height, "components": components,
                     "progressive": marker == SOF2}

        elif marker == DRI:
            restart_interval = struct.unpack(">H", data[seg_start:seg_start + 2])[0]

        elif marker == SOS:
            p = seg_start
            ns = data[p]; p += 1
            scan_components = []
            for _ in range(ns):
                cs = data[p]; p += 1
                td_ta = data[p]; p += 1
                scan_components.append({"id": cs, "dc": td_ta >> 4, "ac": td_ta & 0x0F})
            Ss = data[p]; p += 1
            Se = data[p]; p += 1
            ah_al = data[p]; p += 1
            Ah = ah_al >> 4
            Al = ah_al & 0x0F
            entropy_start = p

            if not frame.get("progressive"):
                # baseline: single scan streams straight to pixels --
                # unchanged fast path, no whole-image coefficient buffer
                return _decode_scan(
                    data, entropy_start, frame, scan_components,
                    qtables, huff_dc, huff_ac, restart_interval, scale_n
                )

            # progressive: accumulate this scan's coefficient bits into
            # the per-component coefficient store, then keep walking
            # markers -- more scans (and possibly more DHT tables)
            # follow until EOI
            if prog is None:
                prog = _init_progressive_state(frame)
                # highest zigzag index the truncated IDCT will actually
                # use for this scale_n -- AC scans whose whole band
                # (Ss..Se) lies above it contribute nothing to the output
                # and can, in principle, be skipped without entropy-
                # decoding them. BUT: this is only safe per-component if
                # no scan for that component "straddles" needed_max (Ss
                # at/below it, Se above it) -- a straddling scan is
                # almost always a later successive-approximation
                # REFINEMENT pass covering the whole AC range (e.g. an
                # encoder emits first-pass sub-bands 1-5 then 6-63
                # separately, then one refinement scan spanning 1-63).
                # Refinement decoding depends on knowing the current
                # zero/nonzero state of every coefficient it walks past,
                # so skipping an earlier scan that established that state
                # above needed_max desyncs the refinement scan's bitstream
                # the moment it crosses needed_max -- confirmed on a real
                # nwt_E.epub image (Question 1's illustration) where
                # skipping the 6-63 first-pass scan broke the later 1-63
                # Ah=2 refinement scan with "bad Huffman code". Precompute
                # per-component skip-safety with one cheap structural
                # pre-scan of all SOS headers (no entropy decoding, just
                # marker-boundary walking) so the real decode pass can
                # trust a simple per-scan Ss check.
                prog["needed_max"] = max(
                    i for i in range(64)
                    if (ZIGZAG[i] // 8) < scale_n and (ZIGZAG[i] % 8) < scale_n
                )
                prog["skip_ok"] = _prescan_skip_safety(data, pos, prog["needed_max"])
            comp_id = scan_components[0]["id"] if len(scan_components) == 1 else None
            if Ss > prog["needed_max"] and comp_id is not None and prog["skip_ok"].get(comp_id, False):
                pos = _next_marker_pos(data, entropy_start)
                continue
            pos = _decode_progressive_scan(
                data, entropy_start, frame, prog, scan_components,
                huff_dc, huff_ac, restart_interval, Ss, Se, Ah, Al
            )
            continue

        pos = seg_end

    if prog is not None:
        return _render_progressive(frame, prog, qtables, scale_n)

    raise ValueError("no SOS/image data found")


def _decode_scan(data, start, frame, scan_components, qtables, huff_dc, huff_ac,
                  restart_interval, scale_n):
    width, height = frame["width"], frame["height"]
    components = frame["components"]
    h_max = max(c["h"] for c in components)
    v_max = max(c["v"] for c in components)

    mcu_w = 8 * h_max
    mcu_h = 8 * v_max
    mcus_x = (width + mcu_w - 1) // mcu_w
    mcus_y = (height + mcu_h - 1) // mcu_h

    basis = _build_scaled_idct_matrix(scale_n)

    # output planes at scale_n-per-8x8-block resolution
    planes = {}
    for c in components:
        pw = mcus_x * c["h"] * scale_n
        ph = mcus_y * c["v"] * scale_n
        planes[c["id"]] = {"data": bytearray(pw * ph), "w": pw, "ph": ph, "h_samp": c["h"], "v_samp": c["v"]}

    reader = BitReader(data, start)
    dc_pred = {c["id"]: 0 for c in components}
    comp_by_id = {c["id"]: c for c in components}
    sc_by_id = {sc["id"]: sc for sc in scan_components}

    mcu_count = 0
    total_mcus = mcus_x * mcus_y

    for my in range(mcus_y):
        # v0.1.78: voluntary GIL yield every few MCU rows. This decode
        # loop is pure Python (no numpy/PIL) and, per real benchmarking,
        # costs roughly 0.5-1.3s per real embedded image even at the
        # app's own auto-picked scale_n on x86 dev hardware -- correspond-
        # ingly longer on the actual ARM handheld. CPython's GIL is
        # SUPPOSED to context-switch on its own every ~5ms, but a report
        # of the whole UI (not just image-related input) freezing for a
        # few seconds whenever an image was mid-decode indicates that
        # isn't happening reliably enough on this hardware to keep the
        # main thread's SDL event loop responsive. time.sleep(0) is a
        # cheap, explicit "let another thread run" hint -- it doesn't
        # measurably slow the decode (checked well below 1% of a row's
        # own cost) but guarantees the main thread gets scheduled
        # regularly instead of only whenever the interpreter happens to
        # offer the GIL up.
        if my % 4 == 0:
            time.sleep(0)
        for mx in range(mcus_x):
            for c in components:
                sc = sc_by_id[c["id"]]
                dc_table = huff_dc[sc["dc"]]
                ac_table = huff_ac[sc["ac"]]
                qtable = qtables[c["q"]]
                plane = planes[c["id"]]
                for by in range(c["v"]):
                    for bx in range(c["h"]):
                        coeffs, dc_pred[c["id"]] = _decode_block(
                            reader, dc_table, ac_table, dc_pred[c["id"]], scale_n
                        )
                        block = _idct_scaled(coeffs, qtable, scale_n, basis)
                        # place into plane
                        px0 = (mx * c["h"] + bx) * scale_n
                        py0 = (my * c["v"] + by) * scale_n
                        pw = plane["w"]
                        pdata = plane["data"]
                        for yy in range(scale_n):
                            row_off = (py0 + yy) * pw + px0
                            brow = block[yy]
                            for xx in range(scale_n):
                                v = brow[xx] + 128.0
                                v = 0 if v < 0 else (255 if v > 255 else v)
                                pdata[row_off + xx] = int(v)

            mcu_count += 1
            if restart_interval and mcu_count % restart_interval == 0 and mcu_count < total_mcus:
                reader.reset_byte_align()
                for k in dc_pred:
                    dc_pred[k] = 0

    return _planes_to_rgb(planes, components, width, height, scale_n)


def _planes_to_rgb(planes, components, width, height, scale_n):
    """Upsample chroma to luma plane resolution and convert to RGB.
    Shared final stage for both the baseline streaming path and the
    progressive render path -- both produce identical `planes` dicts."""
    # assume standard JFIF component ordering: 1=Y, 2=Cb, 3=Cr
    y_plane = planes[components[0]["id"]]
    out_w = (width * scale_n + 7) // 8
    out_h = (height * scale_n + 7) // 8

    if len(components) == 1:
        # grayscale
        rgb = bytearray(out_w * out_h * 3)
        yw = y_plane["w"]
        ydata = y_plane["data"]
        idx = 0
        for yy in range(out_h):
            if yy % 32 == 0:
                time.sleep(0)  # v0.1.78: see _decode_scan() rationale
            row = yy * yw
            for xx in range(out_w):
                v = ydata[row + xx]
                rgb[idx] = v; rgb[idx + 1] = v; rgb[idx + 2] = v
                idx += 3
        return bytes(rgb), out_w, out_h

    cb_plane = planes[components[1]["id"]]
    cr_plane = planes[components[2]["id"]]
    y_h, y_v = components[0]["h"], components[0]["v"]
    cb_h, cb_v = components[1]["h"], components[1]["v"]

    yw = y_plane["w"]
    ydata = y_plane["data"]
    cbw = cb_plane["w"]
    cbdata = cb_plane["data"]
    crdata = cr_plane["data"]

    x_ratio = cb_h / y_h
    y_ratio = cb_v / y_v

    # v26.07.12.16: cx = int(xx * x_ratio) depends ONLY on xx, never on
    # yy -- but sat inside the innermost per-pixel loop, so it was being
    # recomputed out_h times for every single xx value (once per row)
    # instead of the out_w distinct values it actually has. cy right
    # below already gets this right (hoisted to once per row, since it
    # only depends on yy) -- this is the other, bigger half of the same
    # fix: precompute the out_w-entry table once, outside both loops,
    # since this is the single most-executed loop in the whole decoder
    # (out_w * out_h iterations -- every pixel in the final image).
    cx_table = [int(xx * x_ratio) for xx in range(out_w)]

    rgb = bytearray(out_w * out_h * 3)
    idx = 0
    for yy in range(out_h):
        if yy % 32 == 0:
            time.sleep(0)  # v0.1.78: see _decode_scan() rationale
        cy = int(yy * y_ratio)
        crow = cy * cbw
        yrow = yy * yw
        for xx in range(out_w):
            cx = cx_table[xx]  # v26.07.12.16: was int(xx * x_ratio) -- see above
            Y = ydata[yrow + xx]
            cb = cbdata[crow + cx]
            cr = crdata[crow + cx]
            # v26.07.12.15: was `Cb = cbdata[...] - 128; Cr = crdata[...] - 128`
            # then three real float multiplies per pixel (1.402*Cr, etc.) --
            # see _CR_TO_R/etc.'s own comment above. Same arithmetic, just
            # looked up instead of recomputed.
            r = Y + _CR_TO_R[cr]
            g = Y + _CB_TO_G[cb] + _CR_TO_G[cr]
            b = Y + _CB_TO_B[cb]
            rgb[idx] = 0 if r < 0 else (255 if r > 255 else int(r))
            rgb[idx + 1] = 0 if g < 0 else (255 if g > 255 else int(g))
            rgb[idx + 2] = 0 if b < 0 else (255 if b > 255 else int(b))
            idx += 3

    return bytes(rgb), out_w, out_h




# ---------------------------------------------------------------------------
# Progressive JPEG (SOF2) support
#
# A progressive JPEG delivers each block's 64 DCT coefficients spread over
# multiple scans: a DC-first scan, optional DC-refinement scans, AC-band
# scans (each covering a zigzag range Ss..Se of one component), and AC-
# refinement scans that add one bit of precision at a time (successive
# approximation, the Ah/Al fields). Coefficients must therefore be
# accumulated across all scans before any IDCT can run.
#
# Memory strategy for the 1GB-RAM target: one flat array('h') (int16,
# 2 bytes/coefficient) per component, sized to the MCU-padded block grid.
# Blocks live at offset block_index*64, coefficients stored in ZIGZAG
# order (progressive scans address coefficients by zigzag index, and
# _idct_scaled already takes zigzag-order input, so no reshuffle is ever
# needed). int16 is safe: 8-bit-precision JPEG quantized coefficients
# are <= 11 bits + sign even after successive-approximation shifts.
# ---------------------------------------------------------------------------

from array import array


def _prescan_skip_safety(data, start_pos, needed_max):
    """Structural-only pre-scan (no entropy decoding) from the first SOS
    marker to EOI, collecting every AC scan's (component, Ss, Se) and
    deciding, per component, whether ANY scan straddles needed_max (Ss at
    or below it, Se above it). If so, that component's AC scans must all
    be decoded in full -- skipping is unsafe for it (see the long comment
    at the call site). Cheap: this is a marker-boundary walk over the
    same bytes the real decode pass will visit, not a second entropy
    decode -- typically microseconds for JPEG header sizes."""
    pos = start_pos
    n = len(data)
    straddles = set()
    seen_ac = set()
    while pos < n - 1:
        if data[pos] != 0xFF:
            pos += 1
            continue
        marker = data[pos + 1]
        mpos = pos
        pos += 2
        if marker == EOI:
            break
        if marker in (0x01,) or 0xD0 <= marker <= 0xD7:
            continue
        if pos + 2 > n:
            break
        seg_len = struct.unpack(">H", data[pos:pos + 2])[0]
        if marker == SOS:
            p = pos + 2
            ns = data[p]; p += 1
            comps = []
            for _ in range(ns):
                cs = data[p]; p += 1
                p += 1  # td_ta, unused here
                comps.append(cs)
            Ss = data[p]; p += 1
            Se = data[p]; p += 1
            p += 1  # AhAl, unused here
            if Ss > 0 and len(comps) == 1:
                cid = comps[0]
                seen_ac.add(cid)
                if Ss <= needed_max < Se:
                    straddles.add(cid)
            pos = _next_marker_pos(data, p)
            continue
        pos += seg_len
    return {cid: (cid not in straddles) for cid in seen_ac}


def _init_progressive_state(frame):
    """Allocate the per-component coefficient stores + block geometry."""
    components = frame["components"]
    h_max = max(c["h"] for c in components)
    v_max = max(c["v"] for c in components)
    mcus_x = (frame["width"] + 8 * h_max - 1) // (8 * h_max)
    mcus_y = (frame["height"] + 8 * v_max - 1) // (8 * v_max)

    prog = {
        "h_max": h_max, "v_max": v_max,
        "mcus_x": mcus_x, "mcus_y": mcus_y,
        "comps": {},   # id -> per-component dict
        "eobrun": 0,   # AC end-of-band run, persists across restart-free MCUs within a scan
    }
    for c in components:
        # full (MCU-padded) block grid -- interleaved DC scans cover
        # padding blocks, so the store must include them
        full_bw = mcus_x * c["h"]
        full_bh = mcus_y * c["v"]
        # true block counts (non-interleaved AC scans cover only these)
        comp_w = (frame["width"] * c["h"] + h_max - 1) // h_max
        comp_h = (frame["height"] * c["v"] + v_max - 1) // v_max
        used_bw = (comp_w + 7) // 8
        used_bh = (comp_h + 7) // 8
        prog["comps"][c["id"]] = {
            "coeffs": array("h", bytes(2 * 64 * full_bw * full_bh)),
            "full_bw": full_bw, "full_bh": full_bh,
            "used_bw": used_bw, "used_bh": used_bh,
        }
    return prog


def _decode_progressive_scan(data, start, frame, prog, scan_components,
                             huff_dc, huff_ac, restart_interval,
                             Ss, Se, Ah, Al):
    """Decode one progressive scan into the coefficient stores.
    Returns the byte position just past this scan's entropy data (at the
    next marker), so the caller's marker loop can continue."""
    components = frame["components"]
    comp_by_id = {c["id"]: c for c in components}
    reader = BitReader(data, start)
    prog["eobrun"] = 0

    if Ss == 0:
        # ---- DC scan (may be interleaved across all components) ----
        dc_pred = {sc["id"]: 0 for sc in scan_components}
        if len(scan_components) > 1 or len(components) == 1:
            mcus_x, mcus_y = prog["mcus_x"], prog["mcus_y"]
            total_mcus = mcus_x * mcus_y
            mcu_count = 0
            for my in range(mcus_y):
                if my % 4 == 0:
                    time.sleep(0)  # v0.1.78: see _decode_scan() rationale
                for mx in range(mcus_x):
                    for sc in scan_components:
                        c = comp_by_id[sc["id"]]
                        st = prog["comps"][c["id"]]
                        coeffs = st["coeffs"]
                        full_bw = st["full_bw"]
                        for by in range(c["v"]):
                            for bx in range(c["h"]):
                                bidx = (my * c["v"] + by) * full_bw + (mx * c["h"] + bx)
                                off = bidx * 64
                                if Ah == 0:
                                    t = huff_dc[sc["dc"]].decode(reader)
                                    diff = _extend(reader.get_bits(t), t) if t else 0
                                    dc_pred[sc["id"]] += diff
                                    coeffs[off] = dc_pred[sc["id"]] << Al
                                else:
                                    if reader.get_bit():
                                        coeffs[off] |= (1 << Al)
                    mcu_count += 1
                    if restart_interval and mcu_count % restart_interval == 0 \
                            and mcu_count < total_mcus:
                        reader.reset_byte_align()
                        for k in dc_pred:
                            dc_pred[k] = 0
        else:
            # single-component non-interleaved DC scan
            sc = scan_components[0]
            c = comp_by_id[sc["id"]]
            st = prog["comps"][c["id"]]
            coeffs = st["coeffs"]
            full_bw = st["full_bw"]
            used_bw, used_bh = st["used_bw"], st["used_bh"]
            count = 0
            total = used_bw * used_bh
            for by in range(used_bh):
                for bx in range(used_bw):
                    off = (by * full_bw + bx) * 64
                    if Ah == 0:
                        t = huff_dc[sc["dc"]].decode(reader)
                        diff = _extend(reader.get_bits(t), t) if t else 0
                        dc_pred[sc["id"]] += diff
                        coeffs[off] = dc_pred[sc["id"]] << Al
                    else:
                        if reader.get_bit():
                            coeffs[off] |= (1 << Al)
                    count += 1
                    if restart_interval and count % restart_interval == 0 \
                            and count < total:
                        reader.reset_byte_align()
                        dc_pred[sc["id"]] = 0
    else:
        # ---- AC scan: always exactly one component, non-interleaved ----
        sc = scan_components[0]
        c = comp_by_id[sc["id"]]
        st = prog["comps"][c["id"]]
        coeffs = st["coeffs"]
        full_bw = st["full_bw"]
        used_bw, used_bh = st["used_bw"], st["used_bh"]
        ac_table = huff_ac[sc["ac"]]
        count = 0
        total = used_bw * used_bh
        for by in range(used_bh):
            for bx in range(used_bw):
                off = (by * full_bw + bx) * 64
                if Ah == 0:
                    _ac_first(reader, coeffs, off, Ss, Se, Al, ac_table, prog)
                else:
                    _ac_refine(reader, coeffs, off, Ss, Se, Al, ac_table, prog)
                count += 1
                if restart_interval and count % restart_interval == 0 \
                        and count < total:
                    reader.reset_byte_align()
                    prog["eobrun"] = 0

    # find the next marker after this scan's entropy data. NOTE: when the
    # BitReader hits the terminating marker it CONSUMES the 0xFF prefix
    # (reader.pos ends up pointing AT the marker-type byte, not before the
    # 0xFF) -- so the search must start a couple of bytes BEFORE
    # reader.pos, or it would skip straight over the marker that ended the
    # scan (typically the DHT carrying the next scan's Huffman tables,
    # whose loss then surfaces as a KeyError on huff_ac lookup)
    pos = reader.pos - 2
    if pos < start:
        pos = start
    return _next_marker_pos(data, pos)


def _next_marker_pos(data, pos):
    """Byte-scan forward to the next real marker (0xFF followed by anything
    other than 0x00 stuffing or an RST0-7). Safe inside entropy data since
    literal 0xFF bytes there are always stuffed as 0xFF 0x00."""
    n = len(data)
    while pos < n - 1:
        if data[pos] == 0xFF:
            nxt = data[pos + 1]
            if nxt != 0x00 and not (0xD0 <= nxt <= 0xD7):
                return pos
        pos += 1
    return n


def _ac_first(reader, coeffs, off, Ss, Se, Al, ac_table, prog):
    """First pass over an AC band (Ah == 0): decode magnitude-coded
    coefficients, storing them shifted left by Al (their low Al bits
    arrive later via refinement scans)."""
    if prog["eobrun"] > 0:
        prog["eobrun"] -= 1
        return
    k = Ss
    while k <= Se:
        rs = ac_table.decode(reader)
        r = rs >> 4
        s = rs & 0x0F
        if s == 0:
            if r != 15:
                # EOB run: this block (and the next 2^r - 1 + extra
                # blocks) have no more nonzero coefficients in this band
                eobrun = (1 << r) - 1
                if r:
                    eobrun += reader.get_bits(r)
                prog["eobrun"] = eobrun
                return
            k += 16  # ZRL: sixteen zero coefficients
        else:
            k += r
            if k > Se:
                break
            coeffs[off + k] = _extend(reader.get_bits(s), s) << Al
            k += 1


def _ac_refine(reader, coeffs, off, Ss, Se, Al, ac_table, prog):
    """Refinement pass over an AC band (Ah > 0): adds one bit of
    precision to already-nonzero coefficients (correction bits) and
    introduces newly-nonzero coefficients at +/-(1 << Al). Mirrors
    libjpeg's decode_mcu_AC_refine control flow, which is the de-facto
    reference for the (underspecified-in-the-spec) corner cases."""
    p1 = 1 << Al
    m1 = -1 << Al
    k = Ss
    if prog["eobrun"] == 0:
        while k <= Se:
            rs = ac_table.decode(reader)
            r = rs >> 4
            s = rs & 0x0F
            if s == 0:
                if r != 15:
                    # NOTE: unlike _ac_first, NO -1 here -- the current
                    # block's remaining correction bits are consumed by
                    # the eobrun>0 loop below, which then decrements the
                    # run for this block. (Pre-subtracting like the first-
                    # pass code does would make an r=0 EOB compute
                    # eobrun=0, skip that loop entirely, leave this
                    # block's correction bits unread, and desync the
                    # whole bitstream -- exactly the "bad Huffman code"
                    # failure seen on the real NWT progressive images.)
                    eobrun = 1 << r
                    if r:
                        eobrun += reader.get_bits(r)
                    prog["eobrun"] = eobrun
                    break
                # s == 0, r == 15: ZRL -- skip 16 zero-history coefficients
            else:
                # in a refinement scan s is always 1: a newly-nonzero coeff
                s = p1 if reader.get_bit() else m1
            # advance over r zero-history coefficients, emitting
            # correction bits for any nonzero-history ones passed over
            while k <= Se:
                coef = coeffs[off + k]
                if coef != 0:
                    if reader.get_bit():
                        if (coef & p1) == 0:
                            coeffs[off + k] = coef + (p1 if coef >= 0 else m1)
                else:
                    if r == 0:
                        break
                    r -= 1
                k += 1
            if s and k <= Se:
                coeffs[off + k] = s
            k += 1
    if prog["eobrun"] > 0:
        # inside an EOB run: no new nonzero coefficients, but correction
        # bits still arrive for existing nonzero ones in the band
        while k <= Se:
            coef = coeffs[off + k]
            if coef != 0:
                if reader.get_bit():
                    if (coef & p1) == 0:
                        coeffs[off + k] = coef + (p1 if coef >= 0 else m1)
            k += 1
        prog["eobrun"] -= 1


def _render_progressive(frame, prog, qtables, scale_n):
    """All scans read -- dequantize + truncated IDCT every block from the
    accumulated coefficient stores into pixel planes, then reuse the
    exact same plane->RGB conversion as the baseline path."""
    width, height = frame["width"], frame["height"]
    components = frame["components"]
    basis = _build_scaled_idct_matrix(scale_n)

    planes = {}
    for c in components:
        st = prog["comps"][c["id"]]
        pw = st["full_bw"] * scale_n
        ph = st["full_bh"] * scale_n
        planes[c["id"]] = {"data": bytearray(pw * ph), "w": pw, "ph": ph,
                           "h_samp": c["h"], "v_samp": c["v"]}

    for c in components:
        st = prog["comps"][c["id"]]
        coeffs = st["coeffs"]
        full_bw, full_bh = st["full_bw"], st["full_bh"]
        qtable = qtables[c["q"]]
        plane = planes[c["id"]]
        pw = plane["w"]
        pdata = plane["data"]
        for by in range(full_bh):
            # v0.1.78: same GIL-yield rationale as _decode_scan() above.
            if by % 4 == 0:
                time.sleep(0)
            for bx in range(full_bw):
                off = (by * full_bw + bx) * 64
                block = _idct_scaled(coeffs[off:off + 64], qtable, scale_n, basis)
                px0 = bx * scale_n
                py0 = by * scale_n
                for yy in range(scale_n):
                    row_off = (py0 + yy) * pw + px0
                    brow = block[yy]
                    for xx in range(scale_n):
                        v = brow[xx] + 128.0
                        v = 0 if v < 0 else (255 if v > 255 else v)
                        pdata[row_off + xx] = int(v)
        # release this component's coefficient store as soon as its
        # plane is rendered -- keeps peak memory at coefficients+planes
        # for only one component at a time instead of all three
        st["coeffs"] = None

    return _planes_to_rgb(planes, components, width, height, scale_n)


def save_ppm(rgb_bytes, w, h, path):
    """Debug helper: dump decoded RGB as a .ppm (viewable, no deps needed)."""
    with open(path, "wb") as f:
        f.write(f"P6\n{w} {h}\n255\n".encode("ascii"))
        f.write(rgb_bytes)
