"""
parse_t3db.py
=============

Proper parser for EA's classic "DB\\x00\\x08" database format (the T3DB buffer
inside FC 26 squad files). Derived empirically from inspect/t3db.bin:

File header:
    0x00  char[2] "DB"
    0x02  u16    version (0x0800 LE -> displays as 00 08)
    0x04  u32    unknown (0)
    0x08  u32    total file size
    0x0C  u32    unknown (0)
    0x10  u32    table count
    0x14  u32    crc32
    0x18  table directory: count * { char[4] tag, u32 offset }
          offsets are relative to the end of the directory (table_base)

Table header (40 bytes):
    +0x00 u32 crc32
    +0x04 u32 unknown (2)
    +0x08 u32 record size in BYTES
    +0x0C u32 valid (written) record count
    +0x10 u32 unknown (0)
    +0x14 u16 record capacity (allocated rows)
    +0x16 u16 unknown
    +0x18 u16 unknown (0)
    +0x1A u16 unknown (0xFFFF)
    +0x1C u32 field count
    +0x20 u32 unknown (0)
    +0x24 u32 crc32 (field/data crc)

Field descriptor (16 bytes each, immediately after table header):
    +0x00 u32 type       (0 = string, 3 = int, 4 = float, ...)
    +0x04 u32 bit offset within record
    +0x08 char[4] name   (EA's obfuscated 4-char column code)
    +0x0C u32 bit width

Record data starts right after the descriptors:
    capacity * record_size bytes, fields bit-packed inside each record.

Bit packing order is determined empirically (see BitReader flavors below).
"""

import struct
import sys

FIELD_TYPE_STRING = 0
FIELD_TYPE_INT = 3
FIELD_TYPE_FLOAT = 4


class Field:
    __slots__ = ("ftype", "bitoff", "name", "width")

    def __init__(self, ftype, bitoff, name, width):
        self.ftype = ftype
        self.bitoff = bitoff
        self.name = name
        self.width = width

    def __repr__(self):
        return f"Field({self.name!r} type={self.ftype} off={self.bitoff} w={self.width})"


class Table:
    def __init__(self, tag, header_off, data):
        self.tag = tag
        self.header_off = header_off
        (self.crc1, self.unk1, self.record_size, self.rec_bits_minus1,
         self.unk2, self.capacity, self.valid_records, self.unk4, self.unk5,
         raw_field_count, self.unk6, self.crc2) = struct.unpack_from(
            "<IIIIIHHHHIII", data, header_off)
        # bit 8 of the field-count word is a flag (tables with it set carry a
        # small trailing chunk after the record data); low byte = field count
        self.field_count_flag = bool(raw_field_count & 0x100)
        self.field_count = raw_field_count & 0xFF
        self.fields = []
        off = header_off + 40
        for _ in range(self.field_count):
            ftype, bitoff, name, width = struct.unpack_from("<II4sI", data, off)
            self.fields.append(Field(ftype, bitoff, name.decode("latin1"), width))
            off += 16
        self.data_off = off
        self.data_end = off + self.capacity * self.record_size
        # sort a copy by bit offset for readable output
        self.fields_by_off = sorted(self.fields, key=lambda f: f.bitoff)

    def __repr__(self):
        return (f"Table({self.tag!r} recsize={self.record_size} "
                f"valid={self.valid_records} cap={self.capacity} "
                f"fields={self.field_count})")


class Database:
    def __init__(self, buf):
        self.buf = buf
        assert buf[:2] == b"DB", "not a DB file"
        self.table_count = struct.unpack_from("<I", buf, 0x10)[0]
        dir_off = 0x18
        self.table_base = dir_off + self.table_count * 8
        self.tables = []
        self.by_tag = {}
        for i in range(self.table_count):
            tag = buf[dir_off + i * 8: dir_off + i * 8 + 4].decode("latin1")
            off = struct.unpack_from("<I", buf, dir_off + i * 8 + 4)[0]
            t = Table(tag, self.table_base + off, buf)
            self.tables.append(t)
            self.by_tag[tag] = t

    # ---- record readers -----------------------------------------------
    def read_int_msb(self, table, rec_idx, field):
        """Big-endian bitstream: bit 0 = MSB of byte 0."""
        base_bit = 0
        rec_start = table.data_off + rec_idx * table.record_size
        val = 0
        bit = field.bitoff + base_bit
        for _ in range(field.width):
            byte = self.buf[rec_start + (bit >> 3)]
            val = (val << 1) | ((byte >> (7 - (bit & 7))) & 1)
            bit += 1
        return val

    def read_int_lsb(self, table, rec_idx, field):
        """Little-endian bitstream: bit 0 = LSB of byte 0."""
        rec_start = table.data_off + rec_idx * table.record_size
        val = 0
        bit = field.bitoff
        for i in range(field.width):
            byte = self.buf[rec_start + (bit >> 3)]
            val |= ((byte >> (bit & 7)) & 1) << i
            bit += 1
        return val

    def read_string(self, table, rec_idx, field):
        rec_start = table.data_off + rec_idx * table.record_size
        start = rec_start + field.bitoff // 8
        raw = self.buf[start: start + field.width // 8]
        return raw.split(b"\x00")[0].decode("utf-8", errors="replace")


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else r"E:\python\ea-fc26-tool\inspect\t3db.bin"
    buf = open(path, "rb").read()
    db = Database(buf)
    print(f"tables: {db.table_count}")
    for t in db.tables:
        str_fields = sum(1 for f in t.fields if f.ftype == FIELD_TYPE_STRING)
        print(f"  {t.tag}  recsize={t.record_size:4d}  valid={t.valid_records:6d}  "
              f"cap={t.capacity:6d}  fields={t.field_count:3d}  strfields={str_fields}")


if __name__ == "__main__":
    main()
