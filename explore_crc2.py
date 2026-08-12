"""explore_crc2.py — brute force CRC32 variants (reflection/init/xorout) over candidate ranges."""
import struct
import itertools
from parse_t3db import Database

buf = open(r"E:\python\ea-fc26-tool\inspect\t3db.bin", "rb").read()
db = Database(buf)

def make_crc_fn(poly, reflect):
    table = []
    if reflect:
        rpoly = 0
        p = poly
        for _ in range(32):
            rpoly = (rpoly << 1) | (p & 1)
            p >>= 1
        for i in range(256):
            c = i
            for _ in range(8):
                c = (c >> 1) ^ (rpoly if c & 1 else 0)
            table.append(c)
        def crc(data, init):
            c = init
            for b in data:
                c = (c >> 8) ^ table[(c ^ b) & 0xFF]
            return c & 0xFFFFFFFF
    else:
        for i in range(256):
            c = i << 24
            for _ in range(8):
                c = ((c << 1) ^ poly if c & 0x80000000 else c << 1) & 0xFFFFFFFF
            table.append(c)
        def crc(data, init):
            c = init
            for b in data:
                c = ((c << 8) & 0xFFFFFFFF) ^ table[((c >> 24) ^ b) & 0xFF]
            return c & 0xFFFFFFFF
    return crc

t0 = db.tables[0]
t1 = db.tables[1]
file_crc = struct.unpack_from("<I", buf, 0x14)[0]
targets = {t0.crc1: "t0.crc1", t0.crc2: "t0.crc2", t1.crc1: "t1.crc1", file_crc: "file_crc"}

hdr = t0.header_off
ranges = {
    "t0 hdr+4..end": (hdr + 4, t0.data_end),
    "t0 hdr+8..end": (hdr + 8, t0.data_end),
    "t0 fields..end": (hdr + 40, t0.data_end),
    "t0 data..end": (t0.data_off, t0.data_end),
    "t0 hdr..end": (hdr, t0.data_end),
    "t0 hdr+4..hdr40": (hdr + 4, hdr + 40),
    "t0 hdr+4..dataoff": (hdr + 4, t0.data_off),
    "file 0..0x14": (0, 0x14),
    "file 0x18..t0": (0x18, hdr),
    "file 0x18..end": (0x18, len(buf)),
    "t0 crc2+4..end": (hdr + 0x28, t0.data_end),
}

polys = [0x04C11DB7, 0x1EDC6F41, 0xA833982B, 0x741B8CD7]
found = False
for poly in polys:
    for reflect in (True, False):
        crc = make_crc_fn(poly, reflect)
        for name, (s, e) in ranges.items():
            for init in (0, 0xFFFFFFFF):
                c = crc(buf[s:e], init)
                for v, lbl in ((c, "raw"), (c ^ 0xFFFFFFFF, "xorout")):
                    if v in targets:
                        print(f"MATCH {targets[v]} poly={poly:#x} reflect={reflect} init={init:#x} {lbl} range={name} -> {v:08x}")
                        found = True
if not found:
    print("no matches")
