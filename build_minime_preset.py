import player_data as pd_mod
import pandas as pd
from mini_me import MiniMeEngine
from shortlist import Shortlist, ShortlistPlayer, save_preset

df = pd_mod.load_players()
engine = MiniMeEngine(df)

# Dad's 11 Leeds players
dad_pids = [
    51539,   # Edwin van der Sar (87 GK)
    274967,  # John Arne Riise (85 LB)
    238443,  # Laurent Blanc (87 CB)
    167680,  # Ronald Koeman (87 CB)
    1615,    # Lilian Thuram (87 RB)
    1668,    # Claude Makelele (86 CDM)
    246,     # Paul Scholes (87 CM)
    240,     # Roy Keane (85 CM)
    28130,   # Ronaldinho (92 LW)
    268513,  # Jairzinho (88 RW)
    166149,  # Hugo Sanchez (88 ST)
]

sl = Shortlist(target_team=7, target_name="Leeds vs Ipswich Derby")
used_pids = set(dad_pids)

print("=== 1. DAD PLAYERS (LEEDS - TEAM 7) ===")
for pid in dad_pids:
    row = df[df["player_id"] == pid].iloc[0]
    sp = ShortlistPlayer(
        player_id=pid,
        name=str(row["name"]),
        overall=int(row["overall"]),
        position=str(row["position"]),
        target_team=7,
        wage_eur=float(row["wage_eur"]) if pd.notna(row.get("wage_eur")) else None,
        value_eur=float(row["value_eur"]) if pd.notna(row.get("value_eur")) else None,
        pace=int(row["pace"]) if pd.notna(row.get("pace")) else None,
        stamina=int(row["stamina"]) if pd.notna(row.get("stamina")) else None,
    )
    sl.add(sp)
    print(f"  Leeds #{len(sl.players):2d}: {row['name']} (OVR {row['overall']} {row['position']})")

print("\n=== 2. SON PLAYERS (IPSWICH - TEAM 93) ===")
for pid in dad_pids:
    dad_row = df[df["player_id"] == pid].iloc[0]
    clones = engine.find_top_clones(pid, position_filter="SAME", excluded_ids=used_pids, top_n=1)
    if clones:
        c = clones[0]
        c_pid = c["player_id"]
        used_pids.add(c_pid)
        c_row = df[df["player_id"] == c_pid].iloc[0]
        sp = ShortlistPlayer(
            player_id=c_pid,
            name=str(c_row["name"]),
            overall=int(c_row["overall"]),
            position=str(c_row["position"]),
            target_team=93,
            wage_eur=float(c_row["wage_eur"]) if pd.notna(c_row.get("wage_eur")) else None,
            value_eur=float(c_row["value_eur"]) if pd.notna(c_row.get("value_eur")) else None,
            pace=int(c_row["pace"]) if pd.notna(c_row.get("pace")) else None,
            stamina=int(c_row["stamina"]) if pd.notna(c_row.get("stamina")) else None,
        )
        sl.add(sp)
        c_pos = f"{c['position']} ({c['alt_positions']})" if c.get("alt_positions") else c["position"]
        print(f"  Ipswich (vs {dad_row['name']}): {c['name']} (OVR {c['overall']} {c['ovr_diff']:+d}, {c_pos}) | {c['similarity_pct']} | Club: {c['team']}")

path = save_preset(sl, "minime")
print(f"\nSUCCESSFULLY SAVED COMPLETE 22-PLAYER PRESET TO: {path} (Total players: {len(sl.players)})")
