"""Audit every squad file (settings, backup, output) for modded players at Liverpool."""
import glob, os, struct, sys

sys.path.insert(0, r"E:\python\ea-fc26-tool")
from parse_t3db import Database

WATCH = {158023: "Messi", 192505: "Lukaku", 200145: "Casemiro"}
DB_MAGIC = b"DB\x00\x08"

LOCATIONS = [
    r"C:\Users\james\AppData\Local\EA SPORTS FC 26\settings",
    r"E:\python\ea-fc26-tool\backup",
    r"E:\python\ea-fc26-tool\backup\cache",
    r"E:\python\ea-fc26-tool\output",
    r"E:\python\ea-fc26-tool\output\settings_patched",
]

def check(path):
    data = open(path, "rb").read()
    off = data.find(DB_MAGIC)
    if off < 0:
        return None
    size = struct.unpack_from("<I", data, off + 8)[0]
    try:
        db = Database(data[off: off + size])
    except Exception as e:
        return f"unparseable ({e})"
    tpl = db.by_tag["RrqT"]
    f = {x.name: x for x in tpl.fields}
    found = []
    for i in range(tpl.valid_records):
        pid = db.read_int_lsb(tpl, i, f["ykFq"])
        if pid in WATCH and db.read_int_lsb(tpl, i, f["mCXg"]) == 8:
            found.append(WATCH[pid])
    return found

for loc in LOCATIONS:
    print(f"\n== {loc}")
    files = []
    for pat in ("Squads*", "MatchDay*", "SquadOnline*"):
        files += sorted(glob.glob(os.path.join(loc, pat)))
    if not files:
        print("   (no squad files)")
    for p in files:
        r = check(p)
        if r is None:
            continue
        status = "CLEAN" if r == [] else ("MODDED: " + ", ".join(r) if isinstance(r, list) else r)
        print(f"   {os.path.basename(p):32s} {status} @Liverpool")
