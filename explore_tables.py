"""
explore_tables.py — identify which obfuscated table/field holds player IDs,
team IDs, and names, by testing known EA IDs under both bit orders.
"""
import struct
from parse_t3db import Database, FIELD_TYPE_STRING, FIELD_TYPE_INT

KNOWN_PLAYERIDS = {
    192505: "Lukaku",
    209331: "Salah",
    158023: "Messi",
    20801: "Cristiano Ronaldo",
    231747: "Mbappe",
    239085: "Haaland",
    252371: "Bellingham",
    246191: "Saka",
}
KNOWN_TEAMIDS = {9: "Liverpool", 1943: "Bournemouth", 1: "Arsenal", 5: "Chelsea", 10: "Man Utd", 11: "Man City", 18: "Tottenham", 1318: "England", 21: "Real Madrid?"}

buf = open(r"E:\python\ea-fc26-tool\inspect\t3db.bin", "rb").read()
db = Database(buf)

def all_values(table, field, reader):
    return [reader(table, i, field) for i in range(min(table.unk3, table.capacity))]

# valid record count is the u16 we stored as unk3? -- fix: recompute
# (parse_t3db stored capacity at +0x14 and valid at +0x16 incorrectly; do it raw)
def table_counts(t):
    cap, valid = struct.unpack_from("<HH", buf, t.header_off + 0x14)
    return cap, valid

print("=== searching int fields for known player IDs ===")
for t in db.tables:
    cap, valid = table_counts(t)
    if valid < 1000:
        continue
    for f in t.fields:
        if f.ftype != FIELD_TYPE_INT or f.width < 17 or f.width > 32:
            continue
        for order, reader in (("lsb", db.read_int_lsb), ("msb", db.read_int_msb)):
            vals = set()
            for i in range(valid):
                vals.add(reader(t, i, f))
            hits = [KNOWN_PLAYERIDS[v] for v in KNOWN_PLAYERIDS if v in vals]
            if len(hits) >= 4:
                print(f"  table {t.tag} field {f.name} (off={f.bitoff} w={f.width}) order={order}: "
                      f"{len(hits)}/{len(KNOWN_PLAYERIDS)} known players -> {hits}")

print("\n=== searching int fields for team-ID-like distribution ===")
for t in db.tables:
    cap, valid = table_counts(t)
    if valid < 500:
        continue
    for f in t.fields:
        if f.ftype != FIELD_TYPE_INT or f.width < 12 or f.width > 32:
            continue
        for order, reader in (("lsb", db.read_int_lsb), ("msb", db.read_int_msb)):
            vals = [reader(t, i, f) for i in range(valid)]
            sv = set(vals)
            hits = sum(1 for k in KNOWN_TEAMIDS if k in sv)
            if hits >= 7:
                from collections import Counter
                c = Counter(vals)
                print(f"  table {t.tag} field {f.name} (off={f.bitoff} w={f.width}) order={order}: "
                      f"{hits}/9 known teamids, liverpool(9) x{c.get(9,0)}, bournemouth(1943) x{c.get(1943,0)}, distinct={len(sv)}")
