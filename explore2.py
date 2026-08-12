"""explore2.py — Lukaku's teamplayerlinks row, teams table names, players table id field."""
import struct
from collections import Counter
from parse_t3db import Database, FIELD_TYPE_STRING, FIELD_TYPE_INT

buf = open(r"E:\python\ea-fc26-tool\inspect\t3db.bin", "rb").read()
db = Database(buf)

def counts(t):
    return struct.unpack_from("<HH", buf, t.header_off + 0x14)  # cap, valid

def field(t, name):
    return next(f for f in t.fields if f.name == name)

# --- teamplayerlinks -----------------------------------------------------
tpl = db.by_tag["RrqT"]
cap, valid = counts(tpl)
f_pid = field(tpl, "ykFq")
f_tid = field(tpl, "mCXg")
print(f"RrqT (teamplayerlinks): {valid} rows, fields:")
for f in sorted(tpl.fields, key=lambda f: f.bitoff):
    print(f"   {f.name} off={f.bitoff:3d} w={f.width:2d} type={f.ftype}")

LUKAKU, SALAH = 192505, 209331
rows = []
for i in range(valid):
    pid = db.read_int_lsb(tpl, i, f_pid)
    if pid in (LUKAKU, SALAH):
        tid = db.read_int_lsb(tpl, i, f_tid)
        rows.append((i, pid, tid))
        allf = {f.name: db.read_int_lsb(tpl, i, f) for f in tpl.fields}
        print(f"  row {i}: playerid={pid} teamid={tid} full={allf}")

# --- teams table: dump full row for Liverpool + string field -------------
teams = db.by_tag["ONtg"]
cap_t, valid_t = counts(teams)
f_teamid = field(teams, "AwZu")
sfields = [f for f in teams.fields if f.ftype == FIELD_TYPE_STRING]
print(f"\nONtg (teams): {valid_t} rows, string fields: {[(f.name, f.bitoff, f.width) for f in sfields]}")
for i in range(valid_t):
    tid = db.read_int_lsb(teams, i, f_teamid)
    if tid in (9, 1943, 48, 45):
        strs = {f.name: db.read_string(teams, i, f) for f in sfields}
        print(f"  teams row {i}: teamid={tid} strings={strs}")

# what team is Lukaku's current teamid? print all team ids near his
print("\n--- CZUM candidate playerid fields ---")
cz = db.by_tag["CZUM"]
cap_c, valid_c = counts(cz)
known = {192505, 209331, 158023, 20801, 231747, 239085, 252371, 246191}
for f in cz.fields:
    if f.ftype != FIELD_TYPE_INT or f.width < 15:
        continue
    vals = set(db.read_int_lsb(cz, i, f) for i in range(valid_c))
    hits = known & vals
    if len(hits) >= 3:
        print(f"  CZUM field {f.name} off={f.bitoff} w={f.width}: {len(hits)}/8 knowns, distinct={len(vals)}")
