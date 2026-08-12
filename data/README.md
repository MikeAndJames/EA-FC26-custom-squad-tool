# Player reference data

Offline name/stats dictionary for the explorer and name→ID lookup.
**Live club membership always comes from the EA squad T3DB**, not these CSVs.

## Files

| Path | What |
|---|---|
| `raw/flynn28_fc26_update2.csv` | Newer attrs + play styles (from msmc API / flynn28-style, fc26 update 2). No wage/value. |
| `raw/rovnez_sofifa_players.csv` | Older SoFIFA dump (via EAFC26-DataHub). Has `value_eur`, `wage_eur`. |
| `players_merged.csv` | **Use this** — flynn28 attrs left-joined to wage/value by `player_id`. |
| `players.json` | Same data, slim JSON for tooling. |

## Refresh

```bash
python player_data.py --download   # re-fetch both sources
python player_data.py              # merge + write players_merged.csv
```

Or drop Kaggle zips into `raw/` with the same filenames and run `python player_data.py`.

## Sources

- https://www.kaggle.com/datasets/flynn28/eafc26-player-database  
- https://api.msmc.cc/api/eafc (mirror of flynn28-style data)  
- https://www.kaggle.com/datasets/rovnez/fc-26-fifa-26-player-data  
- GitHub mirror used for wage/value: ismailoksuz/EAFC26-DataHub `data/players.csv`
