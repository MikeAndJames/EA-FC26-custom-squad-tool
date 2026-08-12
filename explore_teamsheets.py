"""
explore_teamsheets.py — hunt for a 'default teamsheets' table: some table whose
single record contains many playerid-sized fields holding one team's players
(kick-off likely builds matchday squads from it, not from teamplayerlinks).
"""
from parse_t3db import Database, FIELD_TYPE_INT

buf = open(r"E:\python\ea-fc26-tool\inspect\t3db.bin", "rb").read()
db = Database(buf)

def field(t, name):
    return next(f for f in t.fields if f.name == name)

# Liverpool roster (team 8) from teamplayerlinks
tpl = db.by_tag["RrqT"]
f_pid, f_tid = field(tpl, "ykFq"), field(tpl, "mCXg")
liverpool = set()
napoli = set()
for i in range(tpl.valid_records):
    tid = db.read_int_lsb(tpl, i, f_tid)
    if tid == 8:
        liverpool.add(db.read_int_lsb(tpl, i, f_pid))
    elif tid == 47:
        napoli.add(db.read_int_lsb(tpl, i, f_pid))

print(f"liverpool roster: {len(liverpool)} players, napoli: {len(napoli)}")

# scan every table: for each record, how many int-field values fall in the
# liverpool roster set? report best record per table if >= 8 matches
for t in db.tables:
    intfields = [f for f in t.fields if f.ftype == FIELD_TYPE_INT and 17 <= f.width <= 26]
    if len(intfields) < 10:   # need many playerid-like slots to be a teamsheet
        continue
    best = (0, -1)
    for r in range(t.valid_records):
        vals = [db.read_int_lsb(t, r, f) for f in intfields]
        n = sum(1 for v in vals if v in liverpool)
        if n > best[0]:
            best = (n, r)
    if best[0] >= 8:
        n, r = best
        print(f"\ntable {t.tag}: record {r} holds {n} liverpool players "
              f"({len(intfields)} playerid-like fields of {t.field_count} total, "
              f"{t.valid_records} records)")
        vals = [(f.name, f.bitoff, db.read_int_lsb(t, r, f)) for f in intfields]
        hits = [(nm, off, v) for nm, off, v in vals if v in liverpool]
        print("   sample:", hits[:8])
