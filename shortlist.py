"""
shortlist.py
============
Pure shortlist / basket model for the custom-team explorer.

No UI — add/remove players, auto-assign free jersey numbers, resolve
live from-team from T3DB, export patch_squads.py --swap lines or JSON.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

from parse_t3db import Database
from swap_players import field as tpl_field, roster, TPL_TAG, F_PLAYERID, F_TEAMID, F_JERSEY

SCRIPT_DIR = Path(__file__).resolve().parent
T3DB_PATH = SCRIPT_DIR / "inspect" / "t3db.bin"


@dataclass
class ShortlistPlayer:
    player_id: int
    name: str
    overall: int | None = None
    position: str | None = None
    from_team: int | None = None
    target_team: int | None = None  # Per-player destination team override
    jersey_stored: int | None = None  # 0-based; in-game shirt = value + 1
    wage_eur: float | None = None
    value_eur: float | None = None
    pace: int | None = None
    stamina: int | None = None
    notes: str = ""


@dataclass
class Shortlist:
    target_team: int
    target_name: str = ""
    players: list[ShortlistPlayer] = field(default_factory=list)

    def ids(self) -> set[int]:
        return {p.player_id for p in self.players}

    def add(self, p: ShortlistPlayer) -> bool:
        """Return True if added, False if already present."""
        if p.player_id in self.ids():
            return False
        self.players.append(p)
        return True

    def remove(self, player_id: int) -> bool:
        before = len(self.players)
        self.players = [p for p in self.players if p.player_id != player_id]
        return len(self.players) < before

    def clear(self) -> None:
        self.players.clear()

    def to_dict(self) -> dict:
        return {
            "target_team": self.target_team,
            "target_name": self.target_name,
            "players": [asdict(p) for p in self.players],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Shortlist":
        sl = cls(
            target_team=int(d["target_team"]),
            target_name=str(d.get("target_name") or ""),
        )
        for raw in d.get("players") or []:
            sl.players.append(ShortlistPlayer(**{
                k: raw[k] for k in ShortlistPlayer.__dataclass_fields__ if k in raw
            }))
        return sl


def load_db(path: Path | None = None) -> Database:
    path = path or T3DB_PATH
    return Database(Path(path).read_bytes())


def find_club_team(db: Database, player_id: int, prefer_not: Iterable[int] | None = None) -> int | None:
    """
    Return a club team_id for this player from teamplayerlinks.
    Prefers non-national / non-listed teams; if multiple, pick the one
    with the larger 'club-like' roster (15-55) when possible.
    """
    prefer_not = set(prefer_not or ())
    tpl = db.by_tag[TPL_TAG]
    f_pid, f_tid = tpl_field(tpl, F_PLAYERID), tpl_field(tpl, F_TEAMID)
    teams = []
    for i in range(tpl.valid_records):
        if db.read_int_lsb(tpl, i, f_pid) == player_id:
            teams.append(db.read_int_lsb(tpl, i, f_tid))
    if not teams:
        return None
    # filter prefer_not
    candidates = [t for t in teams if t not in prefer_not] or teams
    # score by roster size in club-ish range
    best = None
    best_score = -1
    for t in candidates:
        n = len(roster(db, t))
        # prefer typical club sizes; national squads often 23+ too, but
        # club ids for big clubs are small numbers historically — not reliable.
        # Use: closer to 25 is more "club first team-ish"
        score = 100 - abs(n - 28)
        if n < 15:
            score -= 50
        if score > best_score:
            best_score = score
            best = t
    return best


def used_jerseys(db: Database, team_id: int) -> set[int]:
    """Stored jersey values (0-based) already on the team."""
    tpl = db.by_tag[TPL_TAG]
    f_pid, f_tid, f_j = (
        tpl_field(tpl, F_PLAYERID),
        tpl_field(tpl, F_TEAMID),
        tpl_field(tpl, F_JERSEY),
    )
    out: set[int] = set()
    for i in range(tpl.valid_records):
        if db.read_int_lsb(tpl, i, f_tid) == team_id:
            out.add(db.read_int_lsb(tpl, i, f_j))
    return out


def assign_jerseys(sl: Shortlist, db: Database, start: int = 70) -> None:
    """
    Assign jersey numbers to shortlist players.
    """
    used = used_jerseys(db, sl.target_team)
    for p in sl.players:
        if p.jersey_stored is not None:
            used.add(p.jersey_stored)
    # free numbers: prefer high kits (70+) then any 1-99
    free_order = list(range(start, 100)) + list(range(1, start))
    free_stored = [n - 1 for n in free_order if (n - 1) not in used]
    fi = 0
    for p in sl.players:
        if p.jersey_stored is not None:
            continue
        if fi >= len(free_stored):
            p.jersey_stored = 90  # last resort
        else:
            p.jersey_stored = free_stored[fi]
            fi += 1
        used.add(p.jersey_stored)


def resolve_from_teams(sl: Shortlist, db: Database) -> list[str]:
    """Set from_team on each player; return warning strings."""
    warnings = []
    for p in sl.players:
        to_team = p.target_team if p.target_team is not None else sl.target_team
        target_roster = set(roster(db, to_team))
        if p.player_id in target_roster:
            p.from_team = to_team
            warnings.append(f"{p.name} ({p.player_id}) already at target team {to_team}")
            continue
        club = find_club_team(db, p.player_id, prefer_not={to_team})
        if club is None:
            warnings.append(f"{p.name} ({p.player_id}): no teamplayerlinks row — cannot swap")
            p.from_team = None
        else:
            p.from_team = club
    return warnings


def export_swap_args(sl: Shortlist) -> list[str]:
    """CLI fragments: --swap PLAYER,FROM,TO,JERSEY (repeatable)."""
    args = []
    for p in sl.players:
        if p.from_team is None or p.jersey_stored is None:
            continue
        to_team = p.target_team if p.target_team is not None else sl.target_team
        if p.from_team == to_team:
            continue
        args.append(
            f"--swap {p.player_id},{p.from_team},{to_team},{p.jersey_stored}"
        )
    return args


def export_cli_command(sl: Shortlist) -> str:
    parts = ["python patch_squads.py"] + export_swap_args(sl)
    return " ".join(parts)


def save_json(sl: Shortlist, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sl.to_dict(), f, indent=2)


def load_json(path: Path) -> Shortlist:
    with open(path, encoding="utf-8") as f:
        return Shortlist.from_dict(json.load(f))


PRESETS_DIR = SCRIPT_DIR / "output" / "presets"


def sanitize_preset_filename(name: str) -> str:
    s = name.strip().lower()
    s = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in s)
    while "__" in s:
        s = s.replace("__", "_")
    s = s.strip("_")
    return s or "preset"


def list_presets(presets_dir: Path | None = None) -> list[dict]:
    """Scan presets directory and return list of preset info dicts."""
    p_dir = presets_dir or PRESETS_DIR
    if not p_dir.exists():
        return []
    res = []
    for p in sorted(p_dir.glob("*.json")):
        try:
            sl = load_json(p)
            res.append({
                "filename": p.name,
                "path": str(p),
                "preset_name": p.stem.replace("_", " ").title(),
                "target_team": sl.target_team,
                "target_name": sl.target_name,
                "player_count": len(sl.players),
            })
        except Exception:
            continue
    return res


def save_preset(sl: Shortlist, name: str, presets_dir: Path | None = None) -> Path:
    p_dir = presets_dir or PRESETS_DIR
    fname = sanitize_preset_filename(name) + ".json"
    target_path = p_dir / fname
    save_json(sl, target_path)
    return target_path


def load_preset(name_or_path: str | Path, presets_dir: Path | None = None) -> Shortlist:
    p_dir = presets_dir or PRESETS_DIR
    p = Path(name_or_path)
    if not p.is_file():
        # try as name in presets_dir
        fname = sanitize_preset_filename(str(name_or_path)) + ".json"
        p = p_dir / fname
        if not p.is_file():
            matches = list(p_dir.glob(f"*{sanitize_preset_filename(str(name_or_path))}*.json"))
            if matches:
                p = matches[0]
            else:
                raise FileNotFoundError(f"Preset '{name_or_path}' not found at {p}")
    return load_json(p)


def delete_preset(name_or_path: str | Path, presets_dir: Path | None = None) -> bool:
    try:
        p_dir = presets_dir or PRESETS_DIR
        p = Path(name_or_path)
        if not p.is_file():
            fname = sanitize_preset_filename(str(name_or_path)) + ".json"
            p = p_dir / fname
        if p.is_file():
            p.unlink()
            return True
        return False
    except Exception:
        return False
