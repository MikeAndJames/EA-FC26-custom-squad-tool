# EA FC 26 Moneyball Squad Tool

## What James wants (the mission)

James and their son play **EA FC 26 offline Kick-Off matches** and get bored of
the stock teams. The goal: James gives an AI (you) **natural language or a
spreadsheet/list**, and you edit the squad database to build custom teams.
Examples of requests to expect:

- "Sign really freaky players: tall and slow, or fast with no end product"
- "One player from each Prem team"
- "Make a team out of our fantasy football squads" (list of names)
- "Moneyball: best team under a wage/rating budget"
- "Swap Lukaku to Liverpool"

**End state**: a `.py` file that you or any future AI can edit to implement any
list of swaps — James supplies players/teams in plain English or a list, the
script does the byte surgery, out pops a file the game imports.

## Hard rules

- **OFFLINE ONLY.** Modified squads are for offline Kick-Off. James disconnects
  the internet before loading them so EA anti-cheat (Javelin) never sees them.
- **NEVER PLAY ONLINE MODES (Seasons/FUT/co-op) WITH MODDED DATA PRESENT.**
  2026-07-15: modded players appeared in the Seasons team picker because we
  had patched the MatchDay/SquadOnline caches. Playing a ranked match like
  that = cheating vs real people + account-ban territory. Resisted (just!).
- **NEVER patch the MatchDay*/SquadOnline* caches.** Online modes and
  "live form" Kick Off read the caches; offline Kick Off (live form OFF)
  reads the active-GUID Squads save. Patch Squads saves only —
  `patch_squads.py` now excludes caches unless `--include-caches`.
  Before any online session: restore pristine caches (deploy_squads.bat
  option 2) or delete them so the game re-downloads.
- **Never write into EA's folders.** Output stays in this project's `output\`.
  James manually copies files to
  `C:\Users\james\AppData\Local\EA SPORTS FC 26\settings\` and tests himself.
- Everything in `E:\python\ea-fc26-tool` is ours to modify freely.
- Free/open-source only; no Patreon tools.
- Python 3.11, stdlib only (no pip needed so far). Windows.

## Status (2026-07-15) — ZERO-TOUCH PIPELINE CONFIRMED WORKING

**2026-07-15 test PASSED**: patched Messi→Liverpool + Lukaku-revert directly
into the game's active save (`patch_squads.py` → `deploy_squads.bat`), James
went straight into Kick Off with NO in-game steps — Messi appeared in the
Liverpool squad (shirt #19, reserves). The GUID mechanism below is confirmed:
patching the active in-game save in place (preserving wrapper+GUID) is all
that's needed. `patch_squads.py --swap P,FROM,TO,JERSEY` (repeatable) is the
working multi-swap interface.


- Format fully reverse-engineered. Lukaku (192505) Napoli→Liverpool swap done
  and **confirmed working in Kick Off** — but only after the missing piece
  below was discovered.
- **THE KICK-OFF MYSTERY — SOLVED (mechanism confirmed by GUID evidence):**
  - Test 1+2 (offline): our file loads via Load Squads, Lukaku appears in
    squad/team-sheet views, but NOT in Kick Off. Patching the MatchDay /
    SquadOnline caches did NOT fix it (they were byte-identical-deployed and
    kick-off still ignored them — those caches are NOT kick-off's source).
  - James then did an in-game **Save Squads** ("Squads 1" →
    `Squads20260714234700894`) plus an in-game Casemiro transfer — and BOTH
    edited players appeared in Kick Off.
  - Why: in-game saves carry a **16-byte GUID** in the FBCHUNKS wrapper (at
    prefix+0x50 and again at SaveType+0x1C). The game's `Settings<timestamp>`
    file stores the **active squad's GUID** (found `2dfa97ad...1dd1` in both
    the save and Settings). Load Squads only loads into session memory;
    **Save Squads registers the file's GUID as active; Kick Off reads the
    active-GUID save.** xAranaktu-style generated files have GUID=0 and are
    never active.
- **The working pipeline (no in-game steps needed)**: patch the game's own
  active save file **in place** — keep its wrapper+GUID, edit the T3DB
  inside, fix DB CRC chain + wrapper zlib CRC. `patch_squads.py` now patches
  every `Squads*`/`MatchDay*`/`SquadOnline*` in the settings folder, so the
  active one always gets the edits. One-time bootstrap per profile: there
  must exist at least one in-game save (James already made "Squads 1").
  **Next test: a fresh swap patched into the active save, offline kick-off,
  zero in-game steps.**
- **Workflow (settled 2026-07-15)**: zero-touch is the primary route — see
  THE ROUTINE section. Load Squads → Save Squads survives as the fallback
  only. Safety habit: batch-restore + audit_squads.py before going back
  online so modded data is never active online.
- **SOURCE MAP (confirmed by James's 2026-07-15 online experiments):**
  - Offline Kick Off, live form OFF → **active-GUID Squads save**
  - Kick Off with "live form" ON → **MatchDay/SquadOnline caches** (Casemiro,
    who existed only in the save, vanished; Messi, patched into the caches,
    stayed)
  - Seasons (online) → **SquadOnline cache** (Messi appeared there; in-game
    Save Squads and Reset All Squads did NOT remove him — those only touch
    the save side, never the caches)
  - "Download latest updates" does NOT refresh a cache if EA's roster
    version is unchanged — a patched cache with the same version metadata
    is treated as current
- Kick-off squad structure: XI (11) + subs (12) + reserves (7) = 30.
- The game's load→save round-trip PRESERVED our patched bytes exactly
  (Lukaku row identical after re-save) — format work fully validated. The
  re-save also reordered the table directory, proving table order is
  arbitrary.
- In-game transfer semantics observed (Casemiro Man Utd→Liverpool via squad
  editor): the game did NOT edit his Man Utd link row — it **repurposed his
  Brazil national-team link row** into the Liverpool link (players CAN hold
  two club links simultaneously) and reshuffled Brazil's XI/sub/res
  positions. Also bumped one field in his players row (`vTpl` +1418,
  meaning unknown). In-game "reset squads" restores the game's built-in
  default DB (James saw Ben Gannon-Doak back at Liverpool).

## THE ROUTINE — how to change squads, start to finish

1. **FC 26 closed.** (Also: if the game saved/reset squads since last time,
   filenames in settings changed — the routine handles this automatically.)
2. `python patch_squads.py --swap PLAYER,FROM,TO,JERSEY` (repeat `--swap`
   per move; JERSEY is stored value = in-game shirt − 1). Patches every
   Squads save in the settings folder read-only → `output\settings_patched\`.
3. `deploy_squads.bat` → option 1. (Auto-backs-up any never-seen game
   saves first, then copies the patched saves over the originals.)
4. **GO OFFLINE** → launch → straight to Kick Off. Zero in-game steps
   (confirmed 2026-07-15). Fallback if a player is missing: Load Squads →
   Save Squads → Kick Off.
5. **Before going back online**: `deploy_squads.bat` → option 2 (restore),
   then `python audit_squads.py` — everything must say CLEAN.

## FUT file findings (2026-07-15, read-only inspection)

`FutSquads*` in settings = **EA's stock FUT reference DB** (byte-structure
identical to the CDN download; row counts match exactly). It contains ZERO
personal data — James's club/cards/first team live server-side only. Never
edit FutSquads (FUT = online = ban territory). But it's a goldmine of
**local reference data** (same 82-table T3DB schema as squads):
- **Icons pool = team 112657** (183 players, OVR up to 94) and **Heroes
  pool = team 114604** (93 players, OVR 84-88), with full CZUM stats.
- **106/183 icons and 57/93 heroes ALSO exist in the regular squads DB's
  CZUM** (no club links) → putting e.g. prime Barnes in Liverpool for
  offline Kick Off may be a single added/edited teamplayerlinks row with
  existing tech. The other 77/36 would need CZUM row copies from the FUT DB.
- **Plain-text names live here** (unlike the squads DB): `lyxL` = 1,601
  team names, `ImNE` = 55 popular teams (name + teamid + kit id?), `Knen` =
  903 real managers (first/full/last name + team), `mDGw` = formations.
  → free local source for `data\teams.json`.

## The files (read in this order)

| File | What it is |
|---|---|
| `parse_t3db.py` | **THE format bible.** Full docstring spec of the T3DB layout + working parser (`Database`, `Table`, `Field`, bit readers). Read this first. |
| `swap_players.py` | The working swap CLI + CRC repair (`fix_crcs`), bit writer (`write_int_lsb`), roster reader. Build the future team-builder on these functions. |
| `patch_squads.py` | **The main tool.** Applies swaps to ALL squad DBs in EA's settings folder (`Squads*` incl. the game's own saves — one of which is the ACTIVE one kick-off reads — plus `MatchDay*`/`SquadOnline*` caches). Reads settings read-only, patches the T3DB inside each FBCHUNKS wrapper in place (preserving wrapper + GUID), fixes the wrapper CRC (zlib crc32 over `[SaveType+48, EOF)` stored at `SaveType+16`), writes to `output\settings_patched\`. Run right before deploying — filenames change whenever the game saves. |
| `audit_squads.py` | **Safety check.** Scans every squad file in EA settings, `backup\`, and `output\` and reports which contain modded players at Liverpool (extend WATCH dict as needed). **Run before any online session.** |
| `deploy_squads.bat` | James's deploy/backup/restore menu. Manages ONLY `Squads*`/`MatchDay*`/`SquadOnline*`. Auto-backs-up at startup every never-seen game-created file: `backup\` (squad saves), `backup\cache\` (caches); files whose names exist in `output\` are ours and are skipped. |
| `FIFASquadFileDownloader\main.py` | xAranaktu's tool: downloads EA's weekly roster from the CDN (`unpack()`), wraps a T3DB buffer into a game-importable FBCHUNKS file (`save_squads()`). |
| `inspect\t3db.bin` | The pristine 10.4 MB decompressed T3DB buffer (source of truth for edits). Regenerate any Tuesday with `inspect_squads.py` after running the downloader. |
| `explore*.py` | The one-off scripts that derived the format. Keep for reference on *how* to derive more fields. |
| `output\` | Modified buffers + game-ready files land here. |

## The cryptology — how the format was cracked (the tricks)

Full byte-level spec is in `parse_t3db.py`'s docstring. The story + traps:

1. **Records are bit-packed, LSB-first** (bit 0 = LSB of byte 0). A playerid
   is a 19-bit field at an arbitrary bit offset. This is why a whole earlier
   session failed: byte-aligned searches for IDs find nothing. **Never grep
   the buffer for values; parse it.**
2. **SoFIFA player IDs = EA player IDs.** (Lukaku 192505 ✓ Salah 209331 ✓.)
   The earlier session concluded they differ — wrong; see trick 1.
3. **Field/table names are obfuscated** 4-char codes, but they are **stable
   across tables**: `ykFq` = playerid everywhere, `mCXg` = teamid everywhere.
   Tables were identified *by content*, not names: hunt for a field where 8/8
   known player IDs appear; check a teamid field by squad-size distribution
   (Liverpool ×27, Bournemouth ×25).
4. **Table header gotcha**: the field-count word's bit 8 (0x100) is a flag
   (table carries a small trailing chunk), not part of the count. Low byte =
   real field count. Misreading this makes the parser run off into record data.
5. **CRC chain** (the game will likely reject files without this): all
   checksums are **CRC-32/MPEG-2** (poly 0x04C11DB7, non-reflected, init
   0xFFFFFFFF, no final xor). Each table's `crc1` covers the *previous*
   table's descriptors+data (table 0's covers the directory); `crc2` covers
   the table's own header; u32 @0x14 covers file bytes [0,0x14); trailing u32
   at EOF covers the last table. `swap_players.fix_crcs()` repairs all of it.
   Verified against all 83 tables before any edit was attempted.
6. **Verify-by-diff discipline**: after any edit, re-parse the modified buffer
   and byte-diff against pristine. A one-player team swap must be a handful of
   bytes (record bits + one crc). Big diffs mean a bug.

## Known table/field map

| tag | table | fields (name @bitoff, width) |
|---|---|---|
| `RrqT` | teamplayerlinks, 23,774 rows | `ykFq`=playerid @88,19 · `mCXg`=teamid @48,18 · `vjla`=position @23,6 (28=SUB, 29=RES) · `JFiY`=jerseynumber **stored 0-based: in-game shirt = value+1** @16,7 · `JMld`=row key @29,19 |
| `RnPg` | empty twin of teamplayerlinks (identical 16 fields, 0 rows) | purpose unknown |
| `amvY` | player season stats per competition, 4,379 rows | `ykFq`=playerid · `LhXN`=competition id (13=Prem, 31=Serie A, 20x=European comps) · `MERA`=goals · `nVWT`=appearances · `xEsZ`=assists · `Ebea`=clean sheets. NOT teamsheets — red herring. |
| `CZUM` | players, 21,598 rows, 145 fields | `ykFq`=playerid @926,19 · `mpuH`=overall @320,7 · `UERs`=potential @998,7 · 140+ unmapped (pace, height, age... — derive via known players) |
| `AGmV` | teams, 842 rows | `mCXg`=teamid @817,18 (primary key) |
| `amvY` | player↔team links (4,379 rows) | has `ykFq`+`JMld`; purpose unmapped |

**Verified team IDs** (by roster membership — do NOT trust old FIFA id lore):
Liverpool = **8** (not 9!), Man City = 9, Napoli = 47, Bournemouth = 1943
(probable, unverified). National teams exist too (Belgium ≈ 1324, players have
one link row per team).

**Names are NOT in the squad DB.** The game resolves nameids against its
install-side locale DB. Any name-based interface needs an external
`playerid→name` / `teamid→name` mapping (SoFIFA or an FC26 dataset dump —
IDs match, see trick 2).

## External player/team reference data

We investigated public datasets that map EA player IDs to human-readable
names and attributes. The best source found so far:

- **Kaggle:** `flynn28/eafc26-player-database` —
  https://www.kaggle.com/datasets/flynn28/eafc26-player-database

This dataset is derived from scraping SoFIFA. As of mid-July 2026 it is
**more current** than the older `rovnez/EAFC26-DataHub` mirror — it
includes data **post-February 2026**, so roughly two snapshots a year (around the major transfer windows).
That means:

- ✅ **Good for:** name → player ID lookup; base attributes (pace, shooting,
  passing, dribbling, defending, physical, height, age, potential, etc.);
  nationality; club/league info at the time of scraping.
- ❌ **Stale for:** moves after its latest scrape; any attribute rebalances EA
  pushed in later patches; newly promoted/added players.
- ✅ **Doesn't matter for current club:** the live EA squad file already tells
  us which team a player is at *right now* via the `teamplayerlinks` table.
  We only need the CSV to resolve "Messi" → `158023`; the squad file tells
  us his current team ID, and `patch_squads.py` moves him.

So the CSV is still a perfectly usable offline dictionary for names and
attributes, even if it isn't current on transfers. If a newer scraped
dataset appears, we can swap it in as `data/players.csv` without touching
the squad-editing logic.

## The explorer layer (`app.py`)

A browser-based team builder sits on top of the core patch tools:

```bash
python app.py
# → http://127.0.0.1:8080
```

It loads `data/players_merged.csv` (~17,873 players), lets you search/filter
or ask natural-language questions, add players to a basket, and export a
ready-to-run `patch_squads.py` command.

Install the explorer dependencies first:

```bash
pip install -r requirements-explorer.txt
```

- **Default sandbox target**: Leeds United (`team_id = 7`). Chosen because it
  is Premier League, starts with "L" (fewer Kick Off menu steps from
  Liverpool), and has distinctive white kits — easy to spot in-game.
- **Search filters**: name, position, min/max OVR, max wage, play style,
  minimum number of play styles.
- **Search results columns**: POS, NAME, OVR, number of play styles, and a
  scrollable list of play styles. Use the **Extra cols** dropdown to add any
  of `pace`, `shooting`, `passing`, `dribbling`, `defending`, `physical`,
  `vision`, `wage_eur`, or `value_eur` to the grid.
- **Squad panel (right side)**: POS, NAME, OVR, shirt number, with a remove
  button.
- **Natural language**: set `GROQ_API_KEY` and/or `GEMINI_API_KEY`. The
  default Groq model is now `qwen/qwen3.6-27b` (Qwen seems more comfortable
  with NiceGUI/pandas code generation). A dropdown in the UI lets you switch
  to `openai/gpt-oss-120b`. Override with `GROQ_MODEL=...`.
  Suggested fallback chain: `qwen/qwen3.6-27b` → `openai/gpt-oss-120b`
  → `llama-3.1-8b-instant` (fastest, smallest).
- **Rate-limit fallback**: if `qwen/qwen3.6-27b` hits a Groq rate limit, the
  app automatically retries the same query with `openai/gpt-oss-120b` and
  shows a warning toast.
- **Iterative NL chat**: the NL box keeps a short conversation history, so
  follow-ups like "players over 38" → "highest vision" refine the previous
  result. Click **Clear chat** to reset history. If generated pandas code
  errors, the model gets one retry with the error message (reflection).
- **AI-driven columns**: in natural-language mode the model can optionally
  set `display_cols = [...]` to choose which columns appear in the results
  table (e.g. `['position', 'name', 'overall', 'pace', 'vision',
  'play_styles']`). If omitted, the UI falls back to the default POS/NAME/OVR
  + play styles layout.
- **Export**: writes `output/shortlist.json` and prints the full
  `python patch_squads.py --swap ...` command.

Workflow:
1. FC 26 closed.
2. Search / NL → click `+` to build your squad.
3. Click **Export swaps**.
4. Run the printed command.
5. Run `deploy_squads.bat` option 1.
6. Go offline, launch FC 26, Kick Off → pick Leeds United.

## Data merge (`player_data.py`)

Reference player data is built from two public SoFIFA-derived dumps:

| Source | What it gives |
|---|---|
| `data/raw/flynn28_fc26_update2.csv` | Newer attributes, play styles, positions |
| `data/raw/rovnez_sofifa_players.csv` | Older dump with `value_eur` / `wage_eur` |

`python player_data.py` left-joins the two on `player_id` and writes
`data/players_merged.csv` + `data/players.json`. ~90% of players end up with
wage/value. Re-run with `--download` to refresh both sources.

## Roadmap for future sessions

1. **Wait for James's in-game test result** of `output\Squads20260709000000`.
2. **Build the name maps**: `data\players.json` (playerid → name, plus useful
   attrs) and `data\teams.json`. Source: SoFIFA scrape or a public FC26
   dataset. This unlocks everything below.
3. **Map more player fields in `CZUM`** for freaky-player queries: sample
   known players (Haaland tall/fast, Messi short, Van Dijk tall/slow-ish) and
   match candidate bit fields against real-world values — same technique as
   `explore3.py` used for overall/potential.
4. **Build `build_team.py`** on top of `swap_players.py`'s functions: input a
   JSON/CSV spec like
   `{"team": 8, "players": ["Lukaku", "name or id", ...], "evict": true}`
   or a swap list; resolve names via `data\players.json`; do all moves in one
   pass; one `fix_crcs()`; emit one file. Handle: jersey clashes (assign free
   numbers), position slots (incoming extras → `vjla`=29 reserve), squad-size
   limits (~52 max per team; keep sane).
5. **Natural-language layer** = you. When James says "tall slow defenders for
   Bournemouth", you query the parsed DB + name map, generate the spec, run
   the script, hand back the file. No LLM-in-the-loop code needed — the AI
   session IS the interface.
6. Weekly refresh: EA pushes rosters Tuesdays. Re-run
   `FIFASquadFileDownloader\main.py` (needs internet), then `inspect_squads.py`
   to regenerate `inspect\t3db.bin`, then re-apply swaps (they're scripted, so
   this is cheap). Note: fresh downloads only happen if the version folder
   under `result\` doesn't already exist — delete old version folders or the
   downloader skips.

## Handy verified IDs for sanity checks

Players: Lukaku 192505, Salah 209331, Messi 158023, C. Ronaldo 20801,
Mbappé 231747, Haaland 239085, Bellingham 252371, Saka 246191,
Van Dijk 203376, Alisson 212831, Wirtz 256630, De Bruyne 192985.
