import json
import random
import os
from pathlib import Path

# Load databases once
DATA_DIR = Path(__file__).parent / "data"
PLAYERS_FILE = DATA_DIR / "players.json"
ICONS_FILE = DATA_DIR / "icon_database.json"

_cached_players = None
_cached_icons = None

def get_all_players():
    global _cached_players
    if _cached_players is None:
        with open(PLAYERS_FILE, 'r', encoding='utf-8') as f:
            _cached_players = json.load(f)
    return _cached_players

def get_all_icons():
    global _cached_icons
    if _cached_icons is None:
        if ICONS_FILE.exists():
            with open(ICONS_FILE, 'r', encoding='utf-8') as f:
                _cached_icons = json.load(f)
        else:
            _cached_icons = []
    return _cached_icons

def resolve_team_id(team_name: str, default_id: int) -> int:
    name = (team_name or "").lower().strip()
    if "liverpool" in name: return 8
    if "man" in name and ("utd" in name or "united" in name): return 10
    if "man" in name and "city" in name: return 9
    if "leeds" in name: return 7
    if "ipswich" in name: return 93
    if "arsenal" in name: return 0
    if "chelsea" in name: return 4
    if "real" in name: return 242
    if "barca" in name or "barcelona" in name: return 240
    if "bayern" in name or "munich" in name or "münchen" in name: return 20
    if "dortmund" in name: return 21
    if "psg" in name or "paris" in name: return 72
    return default_id

class DraftSession:
    def __init__(self, team_a_name, team_b_name, min_ovr, max_ovr, allow_legends, cards_per_round, opponent_blocks_first, allow_blocking=True):
        self.team_a_name = team_a_name
        self.team_b_name = team_b_name
        self.min_ovr = min_ovr or 0
        self.max_ovr = max_ovr or 99
        self.allow_legends = allow_legends
        self.cards_per_round = cards_per_round
        self.opponent_blocks_first = opponent_blocks_first
        self.allow_blocking = allow_blocking
        
        self.team_a_squad = []
        self.team_b_squad = []
        
        self.round_number = 1
        self.max_rounds = 10
        self.state = "INIT" # INIT, BAN, PICK, LEFTOVER, PICK_1, PICK_2, FINISHED
        self.current_board = []
        self.banned_idx = None
        self.picked_idx = None
        self.leftover_idx = None
        self.first_picked_idx = None
        self.second_picked_idx = None
        
        self._build_pool()
        self.start_new_round()

    def _build_pool(self):
        pool = []
        for p in get_all_players():
            # Exclude GKs from outfield draft pool and filter out female players
            if p.get("position", "") == "GK" or p.get("overall", 0) < self.min_ovr or p.get("overall", 0) > self.max_ovr or p.get("gender") == "F":
                continue
            p["is_icon"] = False
            pool.append(p)
            
        if self.allow_legends:
            for p in get_all_icons():
                if p.get("position", "") == "GK" or p.get("overall", 0) < self.min_ovr or p.get("overall", 0) > self.max_ovr:
                    continue
                p["is_icon"] = True
                p["play_styles"] = [] # Mystery!
                pool.append(p)
                
        random.shuffle(pool)
        self.pool = pool

    def start_new_round(self):
        if self.round_number > self.max_rounds:
            self.state = "FINISHED"
            self.assign_goalkeepers()
            return

        self.banned_idx = None
        self.picked_idx = None
        self.leftover_idx = None
        self.first_picked_idx = None
        self.second_picked_idx = None

        if self.allow_blocking:
            self.state = "BAN"
        else:
            self.state = "PICK_1"
        
        # Pop cards from pool
        self.current_board = []
        for _ in range(self.cards_per_round):
            if self.pool:
                self.current_board.append(self.pool.pop())
                
    def get_turn_info(self):
        # Determine roles based on round and config
        is_odd = (self.round_number % 2 != 0)
        
        if self.opponent_blocks_first:
            first_team = "Team B" if is_odd else "Team A"
            second_team = "Team A" if is_odd else "Team B"
        else:
            first_team = "Team A" if is_odd else "Team B"
            second_team = "Team B" if is_odd else "Team A"
            
        if self.allow_blocking:
            blocker = first_team
            picker = second_team
            if self.state == "BAN":
                return blocker, "BAN"
            elif self.state == "PICK":
                return picker, "PICK"
            elif self.state == "LEFTOVER":
                return blocker, "LEFTOVER"
        else:
            if self.state == "PICK_1":
                return first_team, "PICK"
            elif self.state == "PICK_2":
                return second_team, "PICK"
        return None, None

    def take_action(self, card_idx):
        if card_idx < 0 or card_idx >= len(self.current_board):
            return False
            
        if self.allow_blocking:
            if card_idx in (self.banned_idx, self.picked_idx, self.leftover_idx):
                return False # already used
        else:
            if card_idx in (self.first_picked_idx, self.second_picked_idx):
                return False # already used
            
        active_team, action_type = self.get_turn_info()
        card = self.current_board[card_idx]
        
        if self.allow_blocking:
            if self.state == "BAN":
                self.banned_idx = card_idx
                self.state = "PICK"
                
            elif self.state == "PICK":
                self.picked_idx = card_idx
                if active_team == "Team A":
                    self.team_a_squad.append(card)
                else:
                    self.team_b_squad.append(card)
                self.state = "LEFTOVER"
                
            elif self.state == "LEFTOVER":
                self.leftover_idx = card_idx
                if active_team == "Team A":
                    self.team_a_squad.append(card)
                else:
                    self.team_b_squad.append(card)
                
                # End of round!
                self.round_number += 1
                self.start_new_round()
        else:
            if self.state == "PICK_1":
                self.first_picked_idx = card_idx
                if active_team == "Team A":
                    self.team_a_squad.append(card)
                else:
                    self.team_b_squad.append(card)
                self.state = "PICK_2"
                
            elif self.state == "PICK_2":
                self.second_picked_idx = card_idx
                if active_team == "Team A":
                    self.team_a_squad.append(card)
                else:
                    self.team_b_squad.append(card)
                
                # End of round!
                self.round_number += 1
                self.start_new_round()
            
        self._save_backup()
        return True

    def assign_goalkeepers(self):
        # Calculate combined average OVR
        total_ovr = sum(p.get("overall", 0) for p in self.team_a_squad) + sum(p.get("overall", 0) for p in self.team_b_squad)
        count = len(self.team_a_squad) + len(self.team_b_squad)
        if count == 0:
            return
            
        avg_ovr = total_ovr / count
        
        # Find closest GK
        gks = [p for p in get_all_players() if p.get("position", "") == "GK" and p.get("gender") != "F"]
        if self.allow_legends:
            gks.extend([p for p in get_all_icons() if p.get("position", "") == "GK"])
            
        gks.sort(key=lambda p: abs(p.get("overall", 0) - avg_ovr))
        
        # Add to squads
        if len(gks) >= 2:
            self.team_a_gk = gks[0]
            self.team_b_gk = gks[1]
        elif len(gks) == 1:
            self.team_a_gk = gks[0]
            self.team_b_gk = gks[0]
            
        self._save_backup()

    def _save_backup(self):
        from shortlist import Shortlist, ShortlistPlayer, save_preset
        
        sl = Shortlist(target_team=0, target_name="Draft Match Backup")
        
        def add_player(p_dict, t_id):
            if not p_dict: return
            sl.add(ShortlistPlayer(
                player_id=p_dict["player_id"],
                name=p_dict["name"],
                overall=p_dict.get("overall"),
                position=p_dict.get("position"),
                target_team=t_id
            ))

        tid_a = resolve_team_id(self.team_a_name, 8)
        tid_b = resolve_team_id(self.team_b_name, 10)

        # Team A -> Liverpool (8) by default
        if getattr(self, 'team_a_gk', None):
            add_player(self.team_a_gk, tid_a)
        for p in self.team_a_squad:
            add_player(p, tid_a)
            
        # Team B -> Man Utd (10) by default
        if getattr(self, 'team_b_gk', None):
            add_player(self.team_b_gk, tid_b)
        for p in self.team_b_squad:
            add_player(p, tid_b)
            
        try:
            save_preset(sl, "temp_draft")
        except Exception:
            pass # Fail silently so draft doesn't crash if save fails

# In-memory storage for active draft session
active_draft = None
