# Son Challenge — Build Your Dream FC 26 Team

**Goal:** Use the FC 26 Team Builder to put 5 players you like into Leeds United, then see them in Kick Off.

## What you need

- FC 26 closed.
- This folder open in a terminal: `E:\python\ea-fc26-tool`

## Steps

### 1. Start the app

```bash
python app.py
```

Open your browser at: **http://127.0.0.1:8080**

### 2. Search for players

> **Natural language needs an API key.** If you want to ask questions in plain English, ask an adult to set `GROQ_API_KEY` or `GEMINI_API_KEY` in the terminal first.

Try one of these searches:

- Fast wingers: set **Max wage €** high and **Min OVR** to `80`, then click **Search**.
- Play style hunters: type a style like `Rapid` in the **PlayStyle** box.
- By name: type a name in the **Name** box, e.g. `Bellingham`.

Or use **Natural language** (only if an API key is set):

> "English strikers under 80 overall with pace above 85"

### 3. Build your squad

- Click the **+** button next to a player to add them to your squad.
- Add **5 players** you want at Leeds.
- If you change your mind, click the **×** to remove a player.

### 4. Export the swaps

Click **Export swaps**.

The app will show you a command like:

```bash
python patch_squads.py --swap 123456,12,7,90 --swap 234567,34,7,91 ...
```

Copy that command.

### 5. Run the patch

**Important:** FC 26 must be closed for this step.

With the game closed, paste and run the command in the terminal.

### 6. Deploy

Run:

```bash
deploy_squads.bat
```

Choose **option 1** to copy the patched squads into the game folder.

### 7. Test in-game

1. Make sure you are **offline** (disconnect internet).
2. Launch FC 26.
3. Go straight to **Kick Off**.
4. Pick **Leeds United** (white shirts).
5. Check if your 5 players are in the squad!

## Challenge checklist

- [ ] Started the app
- [ ] Found at least one player using search
- [ ] Found at least one player using natural language
- [ ] Added 5 players to the squad
- [ ] Exported the swaps
- [ ] Ran the patch command
- [ ] Deployed with `deploy_squads.bat`
- [ ] Saw the players in Kick Off

## Bonus challenges

1. **Moneyball:** Build a team where the total wage is under €200,000 per week.
2. **One from each Prem team:** Pick one player from 5 different Premier League clubs.
3. **Freaky team:** Find the tallest, slowest defenders you can, or the fastest players with low shooting.
4. **Restore:** With FC 26 closed, run `deploy_squads.bat` option 2 to put the original squads back before going online.

## Safety rules

- **Only play offline Kick Off with modded squads.**
- **Never play online modes** (Seasons, FUT, co-op) with patched squads.
- Always restore the original squads before going back online.

Good luck! 🎮
