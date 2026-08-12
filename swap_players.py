"""
swap_players.py
===============

Move a player between teams in an EA FC 26 squad T3DB buffer, fix the CRC
chain, and emit a game-importable FBCHUNKS squad file.

Never touches EA's own folders — output lands in E:\\python\\ea-fc26-tool\\output.
Copy the produced Squads* file into
  C:\\Users\\james\\AppData\\Local\\EA SPORTS FC 26\\settings\\
yourself, then (offline) Load Squads in game.

Usage:
    python swap_players.py                          # demo: Lukaku -> Liverpool
    python swap_players.py --player 192505 --from-team 47 --to-team 8 --jersey 90

Table/field map (obfuscated names are stable across tables):
    RrqT = teamplayerlinks   ykFq=playerid  mCXg=teamid
                             vjla=position (28=SUB, 29=RES)  JFiY=jerseynumber
    CZUM = players           ykFq=playerid  mpuH=overall  UERs=potential
    AGmV = teams             mCXg=teamid (primary key)

Integrity model (all CRC-32/MPEG-2: poly 0x04C11DB7, non-reflected,
init 0xFFFFFFFF, no final xor):
    file header crc @0x14        over bytes [0x00, 0x14)
    table[i].crc1                over previous chunk:
                                   i == 0 : the table directory [0x18, t0.hdr)
                                   i  > 0 : [t[i-1].hdr+0x28, t[i].hdr)
    table[i].crc2                over own header [hdr+0x04, hdr+0x24)
    trailing u32 at EOF          over [last.hdr+0x28, EOF-4)
"""

import argparse
import os
import sys

from parse_t3db import Database

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(SCRIPT_DIR, "FIFASquadFileDownloader"))
from main import save_squads  # noqa: E402

T3DB_PATH = os.path.join(SCRIPT_DIR, "inspect", "t3db.bin")
OUT_DIR = os.path.join(SCRIPT_DIR, "output")

TPL_TAG = "RrqT"          # teamplayerlinks
F_PLAYERID = "ykFq"
F_TEAMID = "mCXg"
F_JERSEY = "JFiY"
F_POSITION = "vjla"

POLY = 0x04C11DB7


def crc_mpeg2(data, init=0xFFFFFFFF):
    c = init
    for b in data:
        c ^= b << 24
        for _ in range(8):
            c = ((c << 1) ^ POLY if c & 0x80000000 else c << 1) & 0xFFFFFFFF
    return c


def write_int_lsb(buf, table, rec_idx, field, value):
    """Write `value` into a bit-packed int field (LSB-first bit order)."""
    if value >= (1 << field.width):
        raise ValueError(f"value {value} does not fit in {field.width} bits")
    rec_start = table.data_off + rec_idx * table.record_size
    bit = field.bitoff
    for i in range(field.width):
        byte_idx = rec_start + (bit >> 3)
        mask = 1 << (bit & 7)
        if (value >> i) & 1:
            buf[byte_idx] |= mask
        else:
            buf[byte_idx] &= ~mask & 0xFF
        bit += 1


def fix_crcs(buf, db):
    """Recompute the crc1 chain + trailing crc (data may have changed)."""
    tables = sorted(db.tables, key=lambda t: t.header_off)
    # t0.crc1 covers the directory — directory untouched, but recompute anyway
    import struct
    struct.pack_into("<I", buf, tables[0].header_off,
                     crc_mpeg2(buf[0x18:tables[0].header_off]))
    for prev, cur in zip(tables, tables[1:]):
        c = crc_mpeg2(buf[prev.header_off + 0x28: cur.header_off])
        struct.pack_into("<I", buf, cur.header_off, c)
    last = tables[-1]
    struct.pack_into("<I", buf, len(buf) - 4,
                     crc_mpeg2(buf[last.header_off + 0x28: len(buf) - 4]))
    # crc2 (own header) and file crc don't change for data-only edits, but
    # recompute them too so this function is safe after header edits as well
    for t in tables:
        struct.pack_into("<I", buf, t.header_off + 0x24,
                         crc_mpeg2(buf[t.header_off + 4: t.header_off + 0x24]))
    struct.pack_into("<I", buf, 0x14, crc_mpeg2(buf[:0x14]))


def field(table, name):
    return next(f for f in table.fields if f.name == name)


def move_player(buf, db, playerid, from_team, to_team, jersey=None, position=None):
    tpl = db.by_tag[TPL_TAG]
    f_pid, f_tid = field(tpl, F_PLAYERID), field(tpl, F_TEAMID)
    hits = []
    for i in range(tpl.valid_records):
        if (db.read_int_lsb(tpl, i, f_pid) == playerid
                and db.read_int_lsb(tpl, i, f_tid) == from_team):
            hits.append(i)
    if not hits:
        raise SystemExit(f"no teamplayerlinks row for player {playerid} in team {from_team}")
    if len(hits) > 1:
        raise SystemExit(f"ambiguous: {len(hits)} rows for player {playerid} in team {from_team}")
    row = hits[0]
    write_int_lsb(buf, tpl, row, f_tid, to_team)
    if jersey is not None:
        write_int_lsb(buf, tpl, row, field(tpl, F_JERSEY), jersey)
    if position is not None:
        write_int_lsb(buf, tpl, row, field(tpl, F_POSITION), position)
    return row


def roster(db, teamid):
    tpl = db.by_tag[TPL_TAG]
    f_pid, f_tid = field(tpl, F_PLAYERID), field(tpl, F_TEAMID)
    return sorted(db.read_int_lsb(tpl, i, f_pid)
                  for i in range(tpl.valid_records)
                  if db.read_int_lsb(tpl, i, f_tid) == teamid)


def main():
    ap = argparse.ArgumentParser(description="Move a player between teams in an FC 26 squad file")
    ap.add_argument("--player", type=int, default=192505, help="EA player id (default Lukaku)")
    ap.add_argument("--from-team", type=int, default=47, help="current team id (default Napoli)")
    ap.add_argument("--to-team", type=int, default=8, help="destination team id (default Liverpool)")
    ap.add_argument("--jersey", type=int, default=90, help="new shirt number (default 90)")
    ap.add_argument("--t3db", default=T3DB_PATH)
    ap.add_argument("--out-name", default="Squads20260709000000",
                    help="output squad filename (game expects Squads<date><time>)")
    args = ap.parse_args()

    buf = bytearray(open(args.t3db, "rb").read())
    db = Database(bytes(buf))

    before_from = roster(db, args.from_team)
    before_to = roster(db, args.to_team)
    print(f"before: team {args.from_team} has {len(before_from)} players "
          f"(player {args.player} present: {args.player in before_from})")
    print(f"before: team {args.to_team} has {len(before_to)} players "
          f"(player {args.player} present: {args.player in before_to})")

    row = move_player(buf, db, args.player, args.from_team, args.to_team, jersey=args.jersey)
    print(f"patched teamplayerlinks row {row}: team {args.from_team} -> {args.to_team}, "
          f"jersey -> {args.jersey}")
    fix_crcs(buf, db)

    # verify by re-parsing the modified buffer
    db2 = Database(bytes(buf))
    after_from = roster(db2, args.from_team)
    after_to = roster(db2, args.to_team)
    ok = args.player not in after_from and args.player in after_to
    print(f"after : team {args.from_team} has {len(after_from)} players, "
          f"team {args.to_team} has {len(after_to)} players "
          f"(player moved: {'YES' if ok else 'NO'})")
    if not ok:
        raise SystemExit("verification failed — not writing output")

    # verify CRC chain self-consistency
    tables = sorted(db2.tables, key=lambda t: t.header_off)
    assert crc_mpeg2(bytes(buf[0x18:tables[0].header_off])) == tables[0].crc1
    for prev, cur in zip(tables, tables[1:]):
        assert crc_mpeg2(bytes(buf[prev.header_off + 0x28: cur.header_off])) == cur.crc1
    import struct
    assert struct.unpack_from("<I", buf, len(buf) - 4)[0] == \
        crc_mpeg2(bytes(buf[tables[-1].header_off + 0x28: len(buf) - 4]))
    print("crc chain verified OK")

    os.makedirs(OUT_DIR, exist_ok=True)
    raw_out = os.path.join(OUT_DIR, "t3db_modified.bin")
    with open(raw_out, "wb") as fh:
        fh.write(buf)
    print(f"wrote raw modified T3DB: {raw_out}")

    save_squads(bytes(buf), OUT_DIR, args.out_name)
    print(f"wrote game-importable file: {os.path.join(OUT_DIR, args.out_name)}")
    print("\nNext (manual) steps:")
    print(r"  1. copy output\%s to C:\Users\james\AppData\Local\EA SPORTS FC 26\settings\ " % args.out_name)
    print("  2. go offline, launch FC 26, Settings > Customize > Profile > Load Squads")


if __name__ == "__main__":
    main()
