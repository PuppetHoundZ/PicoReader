"""
mini_jpeg.py

Stdlib-only baseline JPEG decoder with truncated-IDCT resolution scaling.

Decodes baseline (non-progressive) JFIF JPEGs -- which is what the JW epub
cover/inline images are -- straight to an RGB byte buffer, using only the
low-frequency N x N corner of each 8x8 DCT coefficient block. This trades
resolution (image comes out at N/8 scale, e.g. N=4 -> half resolution) for
a large speedup on ARM handheld hardware with no numpy/PIL available.

Not a general-purpose JPEG decoder: no progressive DCT, no arithmetic
coding, no CMYK. Covers standard baseline sequential JFIF, 4:2:0 or 4:4:4
chroma subsampling, which is what real-world JPEG encoders (including the
ones used for JW epub images) produce.

Usage:
    from mini_jpeg import decode_jpeg
    rgb_bytes, width, height = decode_jpeg(jpeg_bytes, scale_n=4)
    # rgb_bytes is width*height*3 raw RGB, ready for SDL_CreateRGBSurfaceFrom
"""

import struct
import math
import functools

# ---- JPEG marker constants ----
SOI, EOI = 0xD8, 0xD9
SOF0 = 0xC0          # baseline DCT
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
        r, c = divmod(ZIGZAG[i], 8)
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
    """Read just the SOF0 marker's width/height -- microseconds, no entropy
    decode or IDCT at all -- so callers can pick an appropriately small
    scale_n up front instead of always decoding at one fixed resolution
    regardless of how big the source image actually is. Returns
    (width, height) or None if no SOF0 marker is found (e.g. truncated/
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
        if marker == SOF0:
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

        elif marker == SOF0:
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
            frame = {"width": width, "height": height, "components": components}

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
            p += 3  # Ss, Se, AhAl (ignored for baseline)
            entropy_start = p
            # entropy-coded data runs until next real marker; caller loop
            # below (image decode) handles walking it via BitReader
            return _decode_scan(
                data, entropy_start, frame, scan_components,
                qtables, huff_dc, huff_ac, restart_interval, scale_n
            )

        pos = seg_end

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

    # upsample chroma to luma plane resolution and convert to RGB
    y_comp = min(components, key=lambda c: 0 if c["id"] == 1 else 1)
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

    rgb = bytearray(out_w * out_h * 3)
    idx = 0
    for yy in range(out_h):
        cy = int(yy * y_ratio)
        crow = cy * cbw
        yrow = yy * yw
        for xx in range(out_w):
            cx = int(xx * x_ratio)
            Y = ydata[yrow + xx]
            Cb = cbdata[crow + cx] - 128
            Cr = crdata[crow + cx] - 128
            r = Y + 1.402 * Cr
            g = Y - 0.344136 * Cb - 0.714136 * Cr
            b = Y + 1.772 * Cb
            rgb[idx] = 0 if r < 0 else (255 if r > 255 else int(r))
            rgb[idx + 1] = 0 if g < 0 else (255 if g > 255 else int(g))
            rgb[idx + 2] = 0 if b < 0 else (255 if b > 255 else int(b))
            idx += 3

    return bytes(rgb), out_w, out_h


def save_ppm(rgb_bytes, w, h, path):
    """Debug helper: dump decoded RGB as a .ppm (viewable, no deps needed)."""
    with open(path, "wb") as f:
        f.write(f"P6\n{w} {h}\n255\n".encode("ascii"))
        f.write(rgb_bytes)
