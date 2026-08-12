"""explore3.py — dump rosters for interesting teams; find overall-rating field in players table."""
import struct
from collections import Counter, defaultdict
from parse_t3db import Database, FIELD_TYPE_INT

buf = open(r"E:\python\ea-fc26-tool\inspect\t3db.bin", "rb").read()
db = Database(buf)

def field(t, name):
    return next(f for f in t.fields if f.name == name)

tpl = db.by_tag["RrqT"]
f_pid, f_tid = field(tpl, "ykFq"), field(tpl, "mCXg")

links = []
for i in range(tpl.valid_records):
    links.append((db.read_int_lsb(tpl, i, f_pid), db.read_int_lsb(tpl, i, f_tid)))

by_team = defaultdict(list)
for pid, tid in links:
    by_team[tid].append(pid)

# players table
cz = db.by_tag["CZUM"]
f_czpid = field(cz, "ykFq")
pid_row = {}
for i in range(cz.valid_records):
    pid_row[db.read_int_lsb(cz, i, f_czpid)] = i

# find candidate 'overall' field: 7-bit int, values 40..99 for all valid players
sample_rows = list(pid_row.values())[::200]
cands = []
for f in cz.fields:
    if f.ftype != FIELD_TYPE_INT or not (6 <= f.width <= 7):
        continue
    vals = [db.read_int_lsb(cz, r, f) for r in sample_rows]
    if all(40 <= v <= 99 for v in vals):
        cands.append((f, min(vals), max(vals)))
print("overall/potential candidates (7-bit, 40..99):")
for f, lo, hi in cands:
    known = {209331: "Salah", 192505: "Lukaku", 231747: "Mbappe", 239085: "Haaland", 158023: "Messi"}
    vals = {n: db.read_int_lsb(cz, pid_row[p], f) for p, n in known.items() if p in pid_row}
    print(f"  {f.name} off={f.bitoff} w={f.width} range {lo}-{hi}  {vals}")

print("\nteam sizes: ", {t: len(v) for t, v in sorted(by_team.items())[:10]}, "... total teams:", len(by_team))
for tid in (8, 9, 47, 48, 1943, 21, 132702):
    pids = by_team.get(tid, [])
    print(f"\n=== team {tid} ({len(pids)} players) ===")
    print(sorted(pids))
