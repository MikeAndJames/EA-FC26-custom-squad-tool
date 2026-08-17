"""
mini_me.py
==========
Player Archetype & "Mini-Me" Clone Engine for EA FC 26.

Uses Self-Median Deviation (Robust Z-Score) on all 29 player sub-attributes
to find statistically similar players at a lower overall rating (handicap).
"""

from __future__ import annotations

from typing import Any
import numpy as np
import pandas as pd

SUB_ATTRIBUTES = [
    "pace", "shooting", "passing", "dribbling", "defending", "physical",
    "acceleration", "sprint_speed", "sprint speed", "positioning", "finishing", "shot_power", "shot power",
    "long_shots", "long shots", "volleys", "penalties", "vision", "crossing", "free_kick_accuracy", "free kick accuracy",
    "short_passing", "short passing", "long_passing", "long passing", "curve", "agility", "balance",
    "reactions", "ball_control", "ball control", "composure", "interceptions", "heading_accuracy", "heading accuracy",
    "def_awareness", "def awareness", "standing_tackle", "standing tackle", "sliding_tackle", "sliding tackle",
    "jumping", "stamina", "strength", "aggression"
]

CORE_ATTRIBUTES = ["pace", "shooting", "passing", "dribbling", "defending", "physical"]

# Strict flank and role equivalences (LB never matches RB or ST; RW never matches ST or CB)
POSITION_EQUIVALENCES: dict[str, set[str]] = {
    "GK": {"GK"},
    "CB": {"CB", "SW"},
    "LB": {"LB", "LWB"},
    "RB": {"RB", "RWB"},
    "LWB": {"LWB", "LB", "LM"},
    "RWB": {"RWB", "RB", "RM"},
    "CDM": {"CDM", "CM"},
    "CM": {"CM", "CDM", "CAM"},
    "CAM": {"CAM", "CM", "CF"},
    "LM": {"LM", "LW", "LWB"},
    "RM": {"RM", "RW", "RWB"},
    "LW": {"LW", "LM", "LF"},
    "RW": {"RW", "RM", "RF"},
    "CF": {"CF", "ST", "CAM"},
    "ST": {"ST", "CF"},
}


class MiniMeEngine:
    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()

        # Core attributes are 100% populated for both Icons and Active squad players
        self.feature_cols = [c for c in CORE_ATTRIBUTES if c in self.df.columns]

        for c in self.feature_cols:
            self.df[c] = pd.to_numeric(self.df[c], errors="coerce").fillna(50.0)

        self.X = self.df[self.feature_cols].values.astype(float)

        # Self-Median Deviation vectors (Robust Z-Score)
        medians = np.median(self.X, axis=1, keepdims=True)
        mads = np.median(np.abs(self.X - medians), axis=1, keepdims=True)
        mads[mads == 0] = 1.0
        self.Z = (self.X - medians) / mads

        norms = np.linalg.norm(self.Z, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        self.Z_unit = self.Z / norms

        # Index lookup by player_id
        self.pid_to_idx = {int(pid): idx for idx, pid in enumerate(self.df["player_id"])}

    def find_clone(
        self,
        player_id: int,
        handicap_drop: int = 4,
        drop_tolerance: int = 2,
        position_filter: str | None = None,
        excluded_ids: set[int] | None = None,
        same_gender: bool = True,
    ) -> dict[str, Any] | None:
        """Find the single closest statistical Mini-Me clone for a player."""
        clones = self.find_top_clones(
            player_id=player_id,
            handicap_drop=handicap_drop,
            drop_tolerance=drop_tolerance,
            position_filter=position_filter,
            excluded_ids=excluded_ids,
            same_gender=same_gender,
            top_n=1,
        )
        return clones[0] if clones else None

    def find_top_clones(
        self,
        player_id: int,
        mode: str = "weaker",
        handicap_drop: int | None = None,
        drop_tolerance: int = 2,
        position_filter: str | None = None,
        excluded_ids: set[int] | None = None,
        same_gender: bool = True,
        top_n: int = 5,
    ) -> list[dict[str, Any]]:
        """Find top N closest statistical clones (weaker for Mini-Me, stronger for Better-Me) ranked by similarity."""
        if player_id not in self.pid_to_idx:
            return []

        t_idx = self.pid_to_idx[player_id]
        t_row = self.df.iloc[t_idx]
        t_ovr = int(t_row["overall"])
        t_pos_raw = str(t_row.get("position", "CM")).upper().strip()
        t_pos = t_pos_raw.split()[0].split("(")[0].strip()
        t_gender = str(t_row.get("gender", "M")).upper().strip()
        t_vec = self.Z_unit[t_idx]

        is_stronger = mode.lower() in ("stronger", "better")

        if is_stronger:
            # Better-Me: strictly stronger players (OVR > t_ovr)
            min_ovr = t_ovr + 1
            max_ovr = 99
        else:
            # Mini-Me: strictly weaker players (OVR < t_ovr)
            if handicap_drop is not None and handicap_drop > 0:
                min_ovr = max(45, t_ovr - handicap_drop - drop_tolerance)
                max_ovr = min(t_ovr - 1, t_ovr - handicap_drop + drop_tolerance)
            else:
                min_ovr = max(50, t_ovr - 15)
                max_ovr = t_ovr - 1

            if min_ovr > max_ovr:
                min_ovr = max(45, t_ovr - 8)
                max_ovr = t_ovr - 1

        excluded = set(excluded_ids or ())
        excluded.add(player_id)

        # Build candidate mask
        mask = (self.df["overall"] >= min_ovr) & (self.df["overall"] <= max_ovr)
        if same_gender and "gender" in self.df.columns:
            mask = mask & (self.df["gender"].astype(str).str.upper() == t_gender)

        cand_indices = [idx for idx in self.df[mask].index if int(self.df.iloc[idx]["player_id"]) not in excluded]
        if not cand_indices:
            return []

        # Position filtering
        pos_req = (position_filter or "AUTO").strip().upper()
        if pos_req.startswith("SAME"):
            pos_req = t_pos
        elif pos_req in ("AUTO", ""):
            pos_req = t_pos

        if pos_req != "ANY":
            allowed = POSITION_EQUIVALENCES.get(pos_req, {pos_req})

            def _matches_pos(idx: int) -> bool:
                p_main = str(self.df.iloc[idx].get("position", "")).upper().strip()
                p_alt = str(self.df.iloc[idx].get("alt_positions", "")).upper().strip()
                tokens = set(p_main.replace(",", " ").split() + p_alt.replace(",", " ").split())
                return bool(tokens.intersection(allowed))

            filtered_cand = [idx for idx in cand_indices if _matches_pos(idx)]
            if filtered_cand:
                cand_indices = filtered_cand
            else:
                return []

        if not cand_indices:
            return []

        # Vectorized cosine similarity on candidate slice
        cand_Z = self.Z_unit[cand_indices]
        sims = np.dot(cand_Z, t_vec)

        # Rank strictly from high to low by pure statistical similarity
        best_local_indices = np.argsort(-sims)[:top_n]

        results = []
        for bi in best_local_indices:
            idx = cand_indices[bi]
            cand_row = self.df.iloc[idx]
            sim_score = float(sims[bi])
            c_pos = str(cand_row.get("position", "")).strip()
            c_alt = str(cand_row.get("alt_positions", "")).strip()
            if c_alt == "nan":
                c_alt = ""

            results.append({
                "target_player_id": player_id,
                "target_name": t_row["name"],
                "target_overall": t_ovr,
                "target_position": t_pos,
                "player_id": int(cand_row["player_id"]),
                "name": str(cand_row["name"]),
                "overall": int(cand_row["overall"]),
                "position": c_pos,
                "alt_positions": c_alt,
                "team": str(cand_row.get("team", "")),
                "similarity": sim_score,
                "similarity_pct": f"{sim_score * 100:.1f}%",
                "ovr_diff": int(cand_row["overall"]) - t_ovr,
            })

        return results

    def clone_squad(
        self,
        source_players: list[dict[str, Any]],
        handicap_drop: int = 4,
        drop_tolerance: int = 1,
        target_team_id: int = 93,
        target_team_name: str = "Ipswich",
    ) -> list[dict[str, Any]]:
        """
        Take a list of shortlist player dicts and generate a full Mini-Me opponent squad.
        Avoids picking the same candidate player multiple times.
        """
        used_pids: set[int] = {int(p["player_id"]) for p in source_players}
        cloned_squad: list[dict[str, Any]] = []
        
        for p in source_players:
            pid = int(p["player_id"])
            clone = self.find_clone(
                player_id=pid,
                handicap_drop=handicap_drop,
                drop_tolerance=drop_tolerance,
                excluded_ids=used_pids,
                same_gender=True,
                position_strict=False,
            )
            if clone:
                used_pids.add(clone["player_id"])
                clone_player = dict(clone)
                clone_player["target_team"] = target_team_id
                clone_player["target_team_name"] = target_team_name
                clone_player["matched_to_name"] = p.get("name", "")
                clone_player["matched_to_ovr"] = p.get("overall", "")
                cloned_squad.append(clone_player)
                
        return cloned_squad
