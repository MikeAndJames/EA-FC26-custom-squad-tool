"""
find_sandbox_teams.py
=====================
Rank clubs by (small roster + A–Z proximity to Liverpool) so Kick Off
needs as few team-select clicks as possible from the default Liverpool.

Uses the live T3DB teamplayerlinks roster counts (truth), and player CSV
team names (majority vote per team_id) for human-readable labels.

Usage:
    python find_sandbox_teams.py
    python find_sandbox_teams.py --top 20 --prem-only
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

from parse_t3db import Database
from swap_players import roster, field, TPL_TAG, F_PLAYERID, F_TEAMID

SCRIPT_DIR = Path(__file__).resolve().parent
T3DB_PATH = SCRIPT_DIR / "inspect" / "t3db.bin"
LIVERPOOL_ID = 8
LIVERPOOL_NAME = "Liverpool"

# Common Prem name fragments for filtering when league string is messy
PREM_HINTS = (
    "premier league",
    "eng premier",
    "english premier",
)


def load_t3db(path: Path) -> Database:
    if not path.exists():
        raise SystemExit(f"missing T3DB: {path}")
    return Database(path.read_bytes())


def all_rosters(db: Database) -> dict[int, set[int]]:
    """One-pass team_id -> set of player_ids."""
    tpl = db.by_tag[TPL_TAG]
    f_pid, f_tid = field(tpl, F_PLAYERID), field(tpl, F_TEAMID)
    out: dict[int, set[int]] = defaultdict(set)
    for i in range(tpl.valid_records):
        out[db.read_int_lsb(tpl, i, f_tid)].add(db.read_int_lsb(tpl, i, f_pid))
    return dict(out)


def all_team_sizes(db: Database) -> dict[int, int]:
    return {tid: len(pids) for tid, pids in all_rosters(db).items()}


def build_team_names(db: Database, players_df, rosters: dict[int, set[int]] | None = None) -> dict[int, str]:
    """
    Map team_id -> club name.

    For each CSV club, find the live team_id whose *roster* best overlaps
    the set of player_ids that list that club. This avoids attaching club
    names to national-team rows (those share players but poor roster fit).
    """
    if rosters is None:
        rosters = all_rosters(db)
    club_rosters = {tid: pids for tid, pids in rosters.items() if 15 <= len(pids) <= 45}
    sizes = {tid: len(pids) for tid, pids in club_rosters.items()}

    by_club: dict[str, set[int]] = defaultdict(set)
    for row in players_df.itertuples(index=False):
        team_name = str(getattr(row, "team", "") or "").strip()
        if not team_name or team_name.lower() in ("nan", "none"):
            continue
        by_club[team_name].add(int(row.player_id))

    names: dict[int, str] = {}
    best_score: dict[int, float] = {}

    for club_name, pid_set in by_club.items():
        if len(pid_set) < 8:
            continue
        cand_hits: Counter[int] = Counter()
        for tid, rset in club_rosters.items():
            overlap = len(pid_set & rset)
            if overlap >= 8:
                cand_hits[tid] = overlap
        for tid, overlap in cand_hits.most_common(5):
            size = sizes[tid]
            fit = overlap / size
            if fit < 0.45:
                continue
            score = fit * 100 + overlap
            if score > best_score.get(tid, -1):
                best_score[tid] = score
                names[tid] = club_name

    names[LIVERPOOL_ID] = LIVERPOOL_NAME
    return names


def build_team_leagues(db: Database, players_df, names: dict[int, str]) -> dict[int, str]:
    """
    League only for *named* clubs: majority CSV league among players
    whose CSV team name matches the mapped club name (not whole roster —
    that labels national teams as Premier League).
    """
    # club_name -> majority league
    club_league: dict[str, str] = {}
    tmp: dict[str, Counter[str]] = defaultdict(Counter)
    for row in players_df.itertuples(index=False):
        team_name = str(getattr(row, "team", "") or "").strip()
        league = str(getattr(row, "league", "") or "").strip()
        if not team_name or not league:
            continue
        if team_name.lower() in ("nan", "none") or league.lower() in ("nan", "none"):
            continue
        tmp[team_name][league] += 1
    for club, ctr in tmp.items():
        club_league[club] = ctr.most_common(1)[0][0]

    return {
        tid: club_league[name]
        for tid, name in names.items()
        if name in club_league
    }


def is_prem(league: str) -> bool:
    s = (league or "").lower()
    return any(h in s for h in PREM_HINTS)


def alpha_distance(a: str, b: str) -> int:
    """Rough A–Z steps: difference of first letter, then name order among L*."""
    a = (a or "").strip()
    b = (b or "").strip()
    if not a or not b:
        return 99
    # primary: first-letter distance
    la, lb = a[0].upper(), b[0].upper()
    if not la.isalpha() or not lb.isalpha():
        return 50
    return abs(ord(la) - ord(lb))


def rank_teams(
    sizes: dict[int, int],
    names: dict[int, str],
    leagues: dict[int, str],
    *,
    prem_only: bool = False,
    min_size: int = 11,
    max_size: int = 60,
) -> list[dict]:
    rows = []
    for tid, size in sizes.items():
        if size < min_size or size > max_size:
            continue
        name = names.get(tid, f"team_{tid}")
        league = leagues.get(tid, "")
        if prem_only and not is_prem(league):
            # also allow name-known Prem clubs with empty league
            if not is_prem(league) and name not in (
                # fallback: skip non-prem when filter on
            ):
                if not is_prem(league):
                    continue
        ad = alpha_distance(name, LIVERPOOL_NAME)
        # lower score = better sandbox
        # Weight A–Z heavily: Kick Off is stepped from Liverpool.
        score = ad * 40 + size
        rows.append({
            "team_id": tid,
            "name": name,
            "league": league,
            "roster": size,
            "alpha_dist": ad,
            "score": score,
            "is_prem": is_prem(league),
        })
    rows.sort(key=lambda r: (r["score"], r["roster"], r["name"]))
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description="Find small clubs near Liverpool for sandbox testing")
    ap.add_argument("--t3db", default=str(T3DB_PATH))
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--prem-only", action="store_true", help="only Premier League (by CSV league)")
    ap.add_argument("--all-tiny", action="store_true", help="also print tiniest squads anywhere")
    args = ap.parse_args()

    from player_data import load_players

    db = load_t3db(Path(args.t3db))
    rosters = all_rosters(db)
    sizes = {tid: len(pids) for tid, pids in rosters.items()}
    print(f"teams with links: {len(sizes)}")
    print(f"Liverpool (id {LIVERPOOL_ID}): {sizes.get(LIVERPOOL_ID, '?')} players")

    players = load_players()
    # men only for club naming votes if gender present
    if "gender" in players.columns:
        players = players[players["gender"].astype(str).str.upper().str.startswith("M")]

    names = build_team_names(db, players, rosters)
    leagues = build_team_leagues(db, players, names)

    print("\n=== Best sandbox candidates (small roster + near 'Liverpool' A–Z) ===")
    ranked = rank_teams(sizes, names, leagues, prem_only=args.prem_only)
    # Prefer Prem first in display when not filtering
    if not args.prem_only:
        prem = [r for r in ranked if r["is_prem"]]
        other = [r for r in ranked if not r["is_prem"]]
        display = prem[: args.top] + ([{"_sep": True}] if prem and other else []) + other[: max(5, args.top // 2)]
    else:
        display = ranked[: args.top]

    print(f"{'score':>6} {'roster':>6} {'A-Z':>4} {'id':>6}  name  (league)")
    for r in display:
        if r.get("_sep"):
            print("--- non-Prem / other ---")
            continue
        print(
            f"{r['score']:6d} {r['roster']:6d} {r['alpha_dist']:4d} {r['team_id']:6d}  "
            f"{r['name']}  ({r['league'] or '?'})"
        )

    if args.all_tiny or True:
        print("\n=== Tiniest squads (any league, size 15–35) ===")
        tiny = sorted(
            (
                {
                    "team_id": tid,
                    "name": names.get(tid, f"team_{tid}"),
                    "league": leagues.get(tid, ""),
                    "roster": size,
                }
                for tid, size in sizes.items()
                if 15 <= size <= 35
            ),
            key=lambda r: (r["roster"], r["name"]),
        )[: args.top]
        for r in tiny:
            ad = alpha_distance(r["name"], LIVERPOOL_NAME)
            print(
                f"  roster={r['roster']:2d} A-Z={ad:2d} id={r['team_id']:<6d} "
                f"{r['name']} ({r['league'] or '?'})"
            )

    # recommendation — prefer Leeds United (id 7) when present: letter L,
    # Prem, white kits, easy to spot. Otherwise top Prem by score.
    LEEDS_ID = 7
    prem_ranked = [r for r in ranked if r["is_prem"]]
    leeds = next((r for r in prem_ranked if r["team_id"] == LEEDS_ID), None)
    pick = leeds or (prem_ranked[0] if prem_ranked else (ranked[0] if ranked else None))
    if pick:
        print("\n*** Suggested sandbox ***")
        note = " (project default)" if pick["team_id"] == LEEDS_ID else ""
        print(
            f"  {pick['name']}  team_id={pick['team_id']}  "
            f"roster={pick['roster']}  alpha_dist={pick['alpha_dist']}{note}"
        )
        print("  Use this as --to-team in patch_squads / explorer export.")
        print("  Kick Off: start at Liverpool, step A–Z toward this name.")
        if pick["team_id"] == LEEDS_ID:
            print("  White shirts = custom XI is easy to see on the pitch.")


if __name__ == "__main__":
    main()
