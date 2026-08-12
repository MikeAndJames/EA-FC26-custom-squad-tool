"""explore_crc.py — figure out what the CRC fields in file/table headers cover."""
import struct
import zlib
from parse_t3db import Database

buf = open(r"E:\python\ea-fc26-tool\inspect\t3db.bin", "rb").read()
db = Database(buf)

file_crc = struct.unpack_from("<I", buf, 0x14)[0]
print(f"file header crc @0x14 = {file_crc:08x}")

t0 = db.tables[0]
t1 = db.tables[1]
print(f"t0 {t0.tag}: crc1={t0.crc1:08x} crc2={t0.crc2:08x} hdr@{t0.header_off:#x} data@{t0.data_off:#x} end@{t0.data_end:#x}")
print(f"t1 {t1.tag}: crc1={t1.crc1:08x} crc2={t1.crc2:08x}")

targets = {t0.crc1: "t0.crc1", t0.crc2: "t0.crc2", t1.crc1: "t1.crc1", t1.crc2: "t1.crc2", file_crc: "file_crc"}

def try_crc(label, data, init=0):
    c = zlib.crc32(data, init) & 0xFFFFFFFF
    for variant, val in (("crc32", c), ("~crc32", c ^ 0xFFFFFFFF)):
        if val in targets:
            print(f"  MATCH {targets[val]} = {variant}({label}) = {val:08x}")

# ranges to test for table 0 crcs
hdr = t0.header_off
try_crc("t0 hdr+4..data_end", buf[hdr+4:t0.data_end])
try_crc("t0 hdr+8..data_end", buf[hdr+8:t0.data_end])
try_crc("t0 fields+data", buf[hdr+40:t0.data_end])
try_crc("t0 data only", buf[t0.data_off:t0.data_end])
try_crc("t0 hdr(crc2 zeroed?)..", buf[hdr+0x28:t0.data_end])
try_crc("t0 full incl crc", buf[hdr:t0.data_end])
try_crc("file 0..0x14", buf[:0x14])
try_crc("file 0..0x18", buf[:0x18])
try_crc("file dir", buf[0x18:db.table_base])
try_crc("file all after crc", buf[0x18:])
try_crc("whole file", buf)
try_crc("file 0..0x10", buf[:0x10])

# maybe crc1 of table N covers table N-1, or crc chains. Test t1.crc1 over t0 region:
try_crc("t0 region for t1.crc1", buf[hdr:t1.header_off])
try_crc("t0 hdr+4..t1hdr", buf[hdr+4:t1.header_off])
try_crc("t0 data..t1hdr", buf[t0.data_off:t1.header_off])
try_crc("t0 fields..t1hdr", buf[hdr+40:t1.header_off])

# EA sometimes uses crc32 with init 0xFFFFFFFF without final xor, or MPEG-2. brute force smaller space:
# try every (start, end) on coarse grid for t0.crc2
import itertools
starts = [hdr, hdr+4, hdr+8, hdr+0x24, hdr+0x28, t0.data_off, t0.data_off- (t0.field_count*16)]
ends = [t0.data_end, t1.header_off, t0.data_off + t0.capacity*t0.record_size]
for s, e in itertools.product(starts, ends):
    if s >= e:
        continue
    for init in (0, 0xFFFFFFFF):
        c = zlib.crc32(buf[s:e], init) & 0xFFFFFFFF
        for v, lbl in ((c, "std"), (c ^ 0xFFFFFFFF, "xored")):
            if v in targets:
                print(f"  MATCH {targets[v]}: {lbl} init={init:#x} range [{s-hdr:+#x}..{e-hdr:+#x}] rel to hdr = {v:08x}")
