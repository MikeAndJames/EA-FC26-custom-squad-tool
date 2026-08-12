import sys
import pandas as pd

# Set stdout encoding
sys.stdout.reconfigure(encoding='utf-8')

df = pd.read_csv('data/players_merged.csv', low_memory=False)

# Clean string columns
for col in ['name', 'team', 'nation', 'position', 'play_styles']:
    if col in df.columns:
        df[col] = df[col].fillna('').astype(str)

print(f"Total players loaded: {len(df)}")

# Filter top GKs (OVR >= 84)
top_gks = df[df['position'].str.contains('GK', na=False) & (df['overall'] >= 84)].sort_values('overall', ascending=False)

print("\n================ TOP GOALKEEPERS (84+) ================")
for idx, row in top_gks.iterrows():
    print(f"{row['name']:<25} | OVR: {row['overall']} | Club: {row['team']:<22} | Nation: {row['nation']:<15} | Styles: {row['play_styles'][:40]}")

# Function to evaluate a team (by club name or nation name)
def evaluate_team(team_name, is_nation=False):
    col = 'nation' if is_nation else 'team'
    t_df = df[df[col].str.lower() == team_name.lower()].copy()
    if len(t_df) == 0:
        # try partial match
        t_df = df[df[col].str.lower().str.contains(team_name.lower())].copy()
    
    t_df = t_df.sort_values('overall', ascending=False)
    
    # GKs
    gks = t_df[t_df['position'].str.contains('GK', na=False)]
    best_gk = gks.iloc[0] if len(gks) > 0 else None
    
    # Target Men / Physical ST (ST/CF with Strength >= 80 or Height >= 185)
    st_df = t_df[t_df['position'].str.contains('ST|CF', na=False)]
    target_men = st_df[(st_df['strength'] >= 78) | (st_df['height'] >= 185)].sort_values('overall', ascending=False)
    false9_men = st_df[(st_df['short_passing'] >= 75) & (st_df['vision'] >= 75)].sort_values('overall', ascending=False)
    
    # Shadow Strikers / Inside Forwards (CAM, RW, LW, CF, RM, LM with Pace >= 80 or Positioning >= 80 or Shooting >= 78)
    shadow_strikers = t_df[t_df['position'].str.contains('CAM|LW|RW|CF|LM|RM|ST', na=False) & (t_df['overall'] >= 80)].sort_values('overall', ascending=False)
    
    return {
        'team': team_name,
        'count': len(t_df),
        'best_gk': f"{best_gk['name']} ({best_gk['overall']})" if best_gk is not None else "None",
        'gk_ovr': best_gk['overall'] if best_gk is not None else 0,
        'top_target_men': [f"{r['name']} (OVR {r['overall']}, STR {r['strength']}, HT {r['height']}cm)" for _, r in target_men.head(3).iterrows()],
        'top_false9': [f"{r['name']} (OVR {r['overall']}, SPAS {r['short_passing']}, VIS {r['vision']})" for _, r in false9_men.head(3).iterrows()],
        'top_attackers': [f"{r['name']} ({r['position']} OVR {r['overall']}, PAC {r['pace']}, SHO {r['shooting']}, PAS {r['passing']})" for _, r in shadow_strikers.head(5).iterrows()]
    }

print("\n================ EVALUATING TOP NATIONS ================")
nations = ['Belgium', 'England', 'France', 'Germany', 'Brazil', 'Argentina', 'Spain', 'Italy', 'Portugal', 'Netherlands', 'Norway']
for n in nations:
    res = evaluate_team(n, is_nation=True)
    print(f"\n--- {n.upper()} ---")
    print(f"GK: {res['best_gk']}")
    print(f"Target Men: {', '.join(res['top_target_men']) if res['top_target_men'] else 'None'}")
    print(f"False 9 Options: {', '.join(res['top_false9']) if res['top_false9'] else 'None'}")
    print(f"Shadow Strikers / Attackers: {', '.join(res['top_attackers'][:4])}")

print("\n================ EVALUATING TOP CLUBS ================")
clubs = ['Real Madrid', 'FC Bayern München', 'Manchester City', 'Paris Saint-Germain', 'Arsenal', 'Liverpool', 'FC Barcelona', 'Inter', 'Atlético de Madrid', 'Borussia Dortmund', 'Juventus', 'Aston Villa', 'Tottenham Hotspur']
for c in clubs:
    res = evaluate_team(c, is_nation=False)
    print(f"\n--- {c.upper()} ---")
    print(f"GK: {res['best_gk']}")
    print(f"Target Men: {', '.join(res['top_target_men']) if res['top_target_men'] else 'None'}")
    print(f"False 9 Options: {', '.join(res['top_false9']) if res['top_false9'] else 'None'}")
    print(f"Shadow Strikers / Attackers: {', '.join(res['top_attackers'][:4])}")
