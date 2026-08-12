"""
inspect_squads.py
=================

Reads whichever EA FC 26 squad .bin was downloaded most recently by
FIFASquadFileDownloader (auto-discovered, so the script survives EA's weekly
roster updates), decompresses it with xAranaktu's LZX-style unpack() into the
raw T3DB buffer, saves it to disk, and reports basic structure plus ASCII greps
for known team / player names so we can see what's actually inside.

CAUTION: EA Sports DBs typically store strings in a central pool and reference
them by index, so naive ASCII greps for team / player names will usually miss.
We grep anyway because it's cheap and occasionally picks up embedded copy text.
"""

import glob
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(SCRIPT_DIR, "FIFASquadFileDownloader"))

from main import unpack, T3DB  # noqa: E402

RESULTS_DIR = os.path.join(SCRIPT_DIR, "FIFASquadFileDownloader", "result")
OUT_DIR = os.path.join(SCRIPT_DIR, "inspect")
OUT_T3DB = os.path.join(OUT_DIR, "t3db.bin")

# Strings we are hoping to find somewhere in the buffer. Plain-text ASCII greps
# almost never hit EA's compressed DB payload, but they occasionally match
# embedded copy text or asset paths.
NEEDLES = [
    b"Liverpool",
    b"Bournemouth",
    b"Doak",
    b"Salah",
    b"Manchester",
    b"Arsenal",
    b"Tottenham",
    b"Chelsea",
    b"Ben",
]


def latest_pc64_squad_bin():
    """Pick the most recently modified PC64 squad .bin under results/.

    Auto-discovers so we don't break every Tuesday when EA pushes a new roster.
    """
    pattern = os.path.join(RESULTS_DIR, "PC64", "squads", "*", "squads_*.bin")
    matches = glob.glob(pattern)
    # glob is case-sensitive on Linux; some EA folders are spelled PC64, others pc64.
    if not matches:
        pattern = os.path.join(RESULTS_DIR, "*", "squads", "*", "squads_*.bin")
        matches = [m for m in glob.glob(pattern) if "\\pc64\\" in m.lower() or "\\PC64\\" in m]
    if not matches:
        return None
    matches.sort(key=os.path.getmtime, reverse=True)
    return matches[0]


def hex_dump(data, offset, length):
    """Print a hex+ascii dump of `length` bytes starting at `offset`."""
    end = min(offset + length, len(data))
    for i in range(offset, end, 16):
        chunk = data[i : i + 16]
        hex_str = " ".join(f"{b:02x}" for b in chunk)
        ascii_str = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        print(f"  {i:08x}  {hex_str:<48}  |{ascii_str}|")


def find_strings(data, needles):
    """Grep for ASCII needles in the raw buffer."""
    for needle in needles:
        hits = []
        pos = 0
        while True:
            pos = data.find(needle, pos)
            if pos < 0:
                break
            hits.append(pos)
            pos += len(needle)
        if not hits:
            print(f"  {needle.decode(errors='replace')!r:>20} : NOT FOUND as ASCII")
            continue

        print(f"  {needle.decode(errors='replace')!r:>20} : hit {len(hits)}x")
        for p in hits[:5]:
            start = max(0, p - 16)
            end = min(len(data), p + len(needle) + 32)
            ctx = data[start:end]
            ascii_str = "".join(chr(b) if 32 <= b < 127 else "." for b in ctx)
            print(f"      @{p:>9d} (0x{p:08x}): {ascii_str}")


def try_table_directory(data):
    """Crude table-directory heuristic.

    Walks the first few KB looking for 4-byte little-endian values that point
    INTO the buffer and land on a region with high ASCII density. EMA DBs are
    known to put table offsets in such regions but the precise header layout
    is undocumented. We use this to surface candidate anchors for human
    inspection, not as a parser.
    """
    body = data[8 : min(len(data), 4096)]
    candidates = []
    for off in range(0, len(body) - 12, 4):
        anchor = int.from_bytes(body[off : off + 4], "little")
        if 0 < anchor < len(data) - 16:
            ctx = data[anchor : anchor + 48]
            ascii_count = sum(1 for b in ctx if 32 <= b < 127)
            if ascii_count >= 30:  # tight-ish: 30/48 printable
                candidates.append((off, anchor, ascii_count))
    candidates.sort(key=lambda t: -t[2])
    print(f"\n  top {min(8, len(candidates))} table-directory anchor candidates:")
    for off, anchor, density in candidates[:8]:
        ctx = data[anchor : anchor + 48]
        ascii_str = "".join(chr(b) if 32 <= b < 127 else "." for b in ctx)
        print(f"    header_off={off:5d}  anchor=0x{anchor:08x}  ascii={density:3d}/48  | {ascii_str}")


def main():
    bin_path = latest_pc64_squad_bin()
    if not bin_path:
        print("FATAL: no squad .bin found under FIFASquadFileDownloader/result.")
        print("       Run FIFASquadFileDownloader/main.py first.")
        sys.exit(1)

    print(f"Reading: {bin_path}")
    buf, declared_size = unpack(bin_path)
    print(f"  declared_size = {declared_size:,}")
    print(f"  actual_size   = {len(buf):,}")

    magic_ok = buf[:4] == T3DB
    print(f"\nMagic bytes 0..4: {buf[:4].hex()}  "
          f"(expected {T3DB.hex()})  -> {'[OK]' if magic_ok else '[FAIL]'}")
    if not magic_ok:
        print("  WARNING: unexpected magic - downstream parsing will be wrong.")

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_T3DB, "wb") as fh:
        fh.write(buf)
    print(f"\nWrote raw T3DB: {OUT_T3DB}  ({len(buf):,} bytes)")

    print("\n--- first 32 KB hex dump ---")
    hex_dump(buf, 0, 32768)

    print("\n--- ASCII greps (will usually be empty) ---")
    find_strings(buf, NEEDLES)

    print("\n--- table-directory heuristic ---")
    try_table_directory(buf)


if __name__ == "__main__":
    main()
