import sys
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')

df = pd.read_csv('data/players_merged.csv', low_memory=False)

strikers = ['Lukaku', 'Haaland', 'Kane', 'Sørloth', 'Lewandowski', 'Gyökeres', 'Osimhen', 'Morata', 'Giroud', 'Vlahović', 'Guirassy', 'Alvarez', 'Griezmann', 'Retegui', 'Scamacca']
pattern = '|'.join(strikers)
found = df[df['name'].str.contains(pattern, case=False, na=False) & (df['position'].str.contains('ST|CF', na=False)) & (df['overall'] >= 80)]

print("================ KEY TARGET MEN & FALSE 9 STRIKERS ================")
for idx, r in found.sort_values('overall', ascending=False).iterrows():
    print(f"{r['name']:<22} | OVR: {r['overall']} | Club: {r['team']:<20} | Nation: {r['nation']:<12} | STR: {r['strength']} | HT: {r['height']}cm | SPAS: {r['short_passing']} | VIS: {r['vision']} | Styles: {r['play_styles']}")
