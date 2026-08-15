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
    "acceleration", "sprint speed", "positioning", "finishing", "shot power",
    "long shots", "volleys", "penalties", "vision", "crossing", "free kick accuracy",
    "short passing", "long passing", "curve", "dribbling", "agility", "balance",
    "reactions", "ball control", "composure", "interceptions", "heading accuracy",
    "def awareness", "standing tackle", "sliding tackle", "jumping", "stamina",
    "strength", "aggression"
]

CORE_ATTRIBUTES = ["pace", "shooting", "passing", "dribbling", "defending", "physical"]

# Compatible position groupings
POSITION_GROUPS: dict[str, set[str]] = {
    "GK": {"GK"},
    "CB": {"CB", "SW", "RB", "LB", "CDM"},
    "LB": {"LB", "LWB", "LM", "CB"},
    "RB": {"RB", "RWB", "RM", "CB"},
    "CDM": {"CDM", "CM", "CB"},
    "CM": {"CM", "CAM", "CDM", "LM", "RM"},
    "CAM": {"CAM", "CM", "CF", "LW", "RW", "ST"},
    "LM": {"LM", "LW", "CM", "CAM", "LB"},
    "RM": {"RM", "RW", "CM", "CAM", "RB"},
    "LW": {"LW", "LM", "RW", "CAM", "ST", "CF"},
    "RW": {"RW", "RM", "LW", "CAM", "ST", "CF"},
    "CF": {"CF", "ST", "CAM", "LW", "RW"},
    "ST": {"ST", "CF", "CAM", "LW", "RW"},
}


class MiniMeEngine:
    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()
        
        # Ensure numeric features
        self.feature_cols = [c for c in SUB_ATTRIBUTES if c in self.df.columns]
        if len(self.feature_cols) < 10:
            self.feature_cols = [c for c in CORE_ATTRIBUTES if c in self.df.columns]
            
        for c in self.feature_cols:
            self.df[c] = pd.to_numeric(self.df[c], errors="coerce").fillna(55.0)
            
        self.X = self.df[self.feature_cols].values.astype(float)
        
        # Self-Median Deviation vectors
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
        drop_tolerance: int = 1,
        excluded_ids: set[int] | None = None,
        same_gender: bool = True,
        position_strict: bool = False,
    ) -> dict[str, Any] | None:
        """Find the single closest statistical Mini-Me clone for a player."""
        clones = self.find_top_clones(
            player_id=player_id,
            handicap_drop=handicap_drop,
            drop_tolerance=drop_tolerance,
            excluded_ids=excluded_ids,
            same_gender=same_gender,
            position_strict=position_strict,
            top_n=1,
        )
        return clones[0] if clones else None

    def find_top_clones(
        self,
        player_id: int,
        handicap_drop: int = 4,
        drop_tolerance: int = 1,
        excluded_ids: set[int] | None = None,
        same_gender: bool = True,
        position_strict: bool = False,
        top_n: int = 3,
    ) -> list[dict[str, Any]]:
        """Find top N closest statistical clones for a player at a target handicap."""
        if player_id not in self.pid_to_idx:
            return []
            
        t_idx = self.pid_to_idx[player_id]
        t_row = self.df.iloc[t_idx]
        t_ovr = int(t_row["overall"])
        t_pos = str(t_row.get("position", "CM")).upper()
        t_gender = str(t_row.get("gender", "M")).upper()
        t_vec = self.Z_unit[t_idx]
        
        min_ovr = max(45, t_ovr - handicap_drop - drop_tolerance)
        max_ovr = min(99, t_ovr - handicap_drop + drop_tolerance)
        
        excluded = set(excluded_ids or ())
        excluded.add(player_id)
        
        # Build candidate mask
        mask = (self.df["overall"] >= min_ovr) & (self.df["overall"] <= max_ovr)
        if same_gender and "gender" in self.df.columns:
            mask = mask & (self.df["gender"].astype(str).str.upper() == t_gender)
            
        cand_indices = [idx for idx in self.df[mask].index if int(self.df.iloc[idx]["player_id"]) not in excluded]
        if not cand_indices:
            return []
            
        # Position compatibility filtering
        if position_strict:
            cand_indices = [
                idx for idx in cand_indices
                if str(self.df.iloc[idx].get("position", "")).upper() == t_pos
            ]
        else:
            allowed_pos = POSITION_GROUPS.get(t_pos, {t_pos})
            cand_indices = [
                idx for idx in cand_indices
                if any(p in allowed_pos for p in str(self.df.iloc[idx].get("position", "")).upper().replace(",", " ").split())
                or any(p in allowed_pos for p in str(self.df.iloc[idx].get("alt_positions", "")).upper().replace(",", " ").split())
            ]
            
        if not cand_indices:
            return []
            
        # Vectorized cosine similarity on candidate slice
        cand_Z = self.Z_unit[cand_indices]
        sims = np.dot(cand_Z, t_vec)
        
        best_local_indices = np.argsort(-sims)[:top_n]
        
        results = []
        for bi in best_local_indices:
            idx = cand_indices[bi]
            cand_row = self.df.iloc[idx]
            sim_score = float(sims[bi])
            
            results.append({
                "target_player_id": player_id,
                "target_name": t_row["name"],
                "target_overall": t_ovr,
                "target_position": t_pos,
                "player_id": int(cand_row["player_id"]),
                "name": str(cand_row["name"]),
                "overall": int(cand_row["overall"]),
                "position": str(cand_row.get("position", "")),
                "alt_positions": str(cand_row.get("alt_positions", "")),
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
