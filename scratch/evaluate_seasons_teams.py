import sys
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')

df = pd.read_csv('data/players_merged.csv', low_memory=False)

# Filter for Men's players if gender column exists
if 'gender' in df.columns:
    df_m = df[df['gender'].str.upper() == 'M'].copy()
    if len(df_m) == 0:
        df_m = df.copy()
else:
    df_m = df.copy()

print(f"Men's players count: {len(df_m)}")

# Print unique top teams in database
print("\nUnique team names containing key queries:")
for q in ['Real Madrid', 'Bayern', 'City', 'Arsenal', 'Liverpool', 'Barcelona', 'Inter', 'Atlético', 'Dortmund', 'Juventus', 'Aston Villa', 'Tottenham', 'France', 'England', 'Belgium', 'Germany', 'Brazil', 'Argentina', 'Spain', 'Italy', 'Portugal', 'Netherlands', 'Norway']:
    matches = df_m[df_m['team'].str.contains(q, case=False, na=False)]['team'].unique()
    n_matches = df_m[df_m['nation'].str.contains(q, case=False, na=False)]['nation'].unique()
    print(f"  Query '{q}' -> Teams: {matches[:3]}, Nations: {n_matches[:3]}")

# Function to detail a specific team
def analyze_men_team(name, is_nation=False):
    col = 'nation' if is_nation else 'team'
    sub = df_m[df_m[col].str.lower() == name.lower()].copy()
    if len(sub) == 0:
        sub = df_m[df_m[col].str.lower().str.contains(name.lower())].copy()
    
    sub = sub.sort_values('overall', ascending=False)
    
    # GKs
    gks = sub[sub['position'].str.contains('GK', na=False)]
    
    # Physical / Target Men (ST/CF)
    st = sub[sub['position'].str.contains('ST|CF', na=False)]
    
    # Midfielders / Wingers / Shadow Strikers
    cams = sub[sub['position'].str.contains('CAM|CM|LM|RM|LW|RW', na=False)]
    
    print(f"\n==============================================")
    print(f" TEAM ANALYSIS: {name.upper()} ({'NATION' if is_nation else 'CLUB'})")
    print(f"==============================================")
    print("GOALKEEPERS:")
    for _, r in gks.head(3).iterrows():
        print(f"  • {r['name']:<22} | OVR: {r['overall']} | Height: {r['height']}cm | Styles: {r['play_styles']}")
    
    print("STRIKERS (TARGET MAN / FALSE 9 POTENTIAL):")
    for _, r in st.head(5).iterrows():
        print(f"  • {r['name']:<22} | Pos: {r['position']} | OVR: {r['overall']} | STR: {r['strength']} | HT: {r['height']}cm | PAC: {r['pace']} | SHO: {r['shooting']} | PAS: {r['passing']} | Styles: {r['play_styles']}")
        
    print("SHADOW STRIKERS / ATTACKERS / CREATORS:")
    for _, r in cams.head(6).iterrows():
        print(f"  • {r['name']:<22} | Pos: {r['position']} | OVR: {r['overall']} | PAC: {r['pace']} | SHO: {r['shooting']} | PAS: {r['passing']} | DRI: {r['dribbling']} | Styles: {r['play_styles']}")

# Run for top national teams & top clubs
for n in ['Belgium', 'France', 'England', 'Germany', 'Brazil', 'Argentina', 'Spain', 'Italy', 'Norway', 'Portugal']:
    analyze_men_team(n, is_nation=True)

for c in ['Real Madrid', 'FC Bayern München', 'Manchester City', 'Arsenal', 'Liverpool', 'FC Barcelona', 'Inter', 'Atlético de Madrid', 'Borussia Dortmund', 'Aston Villa']:
    analyze_men_team(c, is_nation=False)
