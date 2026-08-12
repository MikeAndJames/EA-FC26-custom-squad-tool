"""
patch_squads.py
===============

Apply player swaps to the squad databases in EA's settings folder that are
used for offline Kick Off.

By default only the game's own **Squads** saves are patched. The
MatchDay/SquadOnline caches are EXCLUDED unless you pass --include-caches,
because those caches are read by online modes (Seasons) and by Kick Off with
"live form" ON. Patching them leaks modded players into online play.

READS the EA settings folder (never writes to it). Patched copies, with the
SAME filenames, land in  output\settings_patched\  — deploy them with
deploy_squads.bat, which backs up the originals first.

Usage:
    python patch_squads.py                                    # Lukaku demo swap
    python patch_squads.py --player 192505 --from-team 47 --to-team 8 --jersey 90
    python patch_squads.py --swap 192505,47,8,90 --swap 158023,1,8,91

Wrapper format (FBCHUNKS squad-family files):
    ...prefix header...
    "SaveType_XXXXX\\0" main header (48 bytes) at offset ST
        u32 @ ST+16  = zlib CRC-32 over [ST+48, EOF)   (xAranaktu writes 0
                       for Squads and the game accepts that; EA's own
                       MatchDay/SquadOnline files carry the real value)
    T3DB payload ("DB\\x00\\x08", size at DB+8) somewhere after the header.
"""

import argparse
import glob
import os
import struct
import zlib

from parse_t3db import Database
from swap_players import move_player, fix_crcs, roster, crc_mpeg2  # noqa: F401

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS = r"C:\Users\james\AppData\Local\EA SPORTS FC 26\settings"
OUT_DIR = os.path.join(SCRIPT_DIR, "output", "settings_patched")

DB_MAGIC = b"DB\x00\x08"


def patch_wrapped_file(path, swaps):
    """Return patched bytes of an FBCHUNKS squad file, or None if no-op."""
    data = bytearray(open(path, "rb").read())

    db_off = data.find(DB_MAGIC)
    if db_off < 0:
        print(f"  SKIP {os.path.basename(path)}: no T3DB payload found")
        return None
    db_size = struct.unpack_from("<I", data, db_off + 8)[0]
    db_buf = bytearray(data[db_off: db_off + db_size])
    db = Database(bytes(db_buf))

    changed = False
    for (player, from_team, to_team, jersey) in swaps:
        cur = roster(db, to_team)
        if player in cur:
            print(f"  player {player} already in team {to_team} — skipping that swap")
            continue
        row = move_player(db_buf, db, player, from_team, to_team, jersey=jersey)
        print(f"  moved player {player}: team {from_team} -> {to_team} "
              f"(link row {row}, shirt #{jersey + 1})")
        changed = True
    if not changed:
        return None

    fix_crcs(db_buf, db)

    # verify the patched DB before splicing back
    db2 = Database(bytes(db_buf))
    for (player, from_team, to_team, _j) in swaps:
        assert player in roster(db2, to_team), f"verify failed: {player} not in {to_team}"
        assert player not in roster(db2, from_team), f"verify failed: {player} still in {from_team}"

    data[db_off: db_off + db_size] = db_buf

    # wrapper CRC: u32 at SaveType+16, zlib crc32 over [SaveType+48, EOF)
    st = data.find(b"SaveType")
    if st >= 0:
        stored = struct.unpack_from("<I", data, st + 16)[0]
        new_crc = zlib.crc32(bytes(data[st + 48:])) & 0xFFFFFFFF
        struct.pack_into("<I", data, st + 16, new_crc)
        print(f"  wrapper crc @{st + 16:#x}: {stored:08x} -> {new_crc:08x}")
    return bytes(data)


def main():
    ap = argparse.ArgumentParser(description="Patch swaps into Squads + cached MatchDay/SquadOnline files")
    ap.add_argument("--player", type=int, default=192505)
    ap.add_argument("--from-team", type=int, default=47)
    ap.add_argument("--to-team", type=int, default=8)
    ap.add_argument("--jersey", type=int, default=90, help="stored value; in-game shirt = value+1")
    ap.add_argument("--preset", type=str,
                    help="Name or path of a squad preset JSON file (e.g. 'Liverpool New Signings' or 'output/presets/big_guys.json')")
    ap.add_argument("--include-caches", action="store_true",
                    help="ALSO patch MatchDay*/SquadOnline* caches. DANGEROUS: "
                         "online modes (Seasons) and 'live form' read the caches, "
                         "so patched caches leak modded players into online play. "
                         "Kick Off (live form off) only needs the Squads saves.")
    args = ap.parse_args()
    if args.preset:
        from pathlib import Path
        from shortlist import load_preset, load_db, resolve_from_teams, assign_jerseys
        try:
            sl = load_preset(args.preset)
        except Exception as e:
            raise SystemExit(f"Error loading preset '{args.preset}': {e}")
        db_ref = load_db()
        resolve_from_teams(sl, db_ref)
        assign_jerseys(sl, db_ref)
        swaps = []
        for p in sl.players:
            if p.from_team is not None and p.jersey_stored is not None and p.from_team != sl.target_team:
                swaps.append((p.player_id, p.from_team, sl.target_team, p.jersey_stored))
        if not swaps:
            print(f"Preset '{sl.target_name}' loaded, but no valid player swaps needed.")
        else:
            print(f"Loaded preset '{sl.target_name}' (target {sl.target_team}): {len(swaps)} swaps queued.")
    elif args.swap:
        swaps = [tuple(int(x) for x in s.split(",")) for s in args.swap]
        for s in swaps:
            if len(s) != 4:
                raise SystemExit(f"bad --swap {s}: need PLAYER,FROM,TO,JERSEY")
    else:
        swaps = [(args.player, args.from_team, args.to_team, args.jersey)]

    targets = []
    # Squads* in the settings folder includes the game's own saves — one of
    # which is the ACTIVE squad (registered by GUID in the Settings file)
    # that Kick Off actually reads. Patching them all guarantees the active
    # one gets the edits with no in-game steps needed.
    # MatchDay*/SquadOnline* caches are EXCLUDED by default: Seasons and
    # 'live form' Kick Off read the caches, so patching them puts modded
    # players into online play (discovered the hard way, 2026-07-15).
    patterns = ["Squads*"]
    if args.include_caches:
        patterns += ["MatchDay*", "SquadOnline*"]
    for pattern in patterns:
        targets += sorted(glob.glob(os.path.join(SETTINGS, pattern)))
    # also re-patch our own newest Squads output so everything stays in sync
    squads_out = sorted(glob.glob(os.path.join(SCRIPT_DIR, "output", "Squads*")),
                        key=os.path.getmtime)
    if squads_out:
        targets.append(squads_out[-1])

    if not targets:
        raise SystemExit("nothing to patch — no MatchDay/SquadOnline in settings, no Squads in output")

    os.makedirs(OUT_DIR, exist_ok=True)
    for path in targets:
        name = os.path.basename(path)
        print(f"patching {name} ...")
        patched = patch_wrapped_file(path, swaps)
        if patched is None:
            print(f"  no changes needed for {name}")
            continue
        out_path = os.path.join(OUT_DIR, name)
        with open(out_path, "wb") as fh:
            fh.write(patched)
        print(f"  -> {out_path}")
    print("\nDone. Now run deploy_squads.bat (option 1) to back up originals and deploy.")


if __name__ == "__main__":
    main()
