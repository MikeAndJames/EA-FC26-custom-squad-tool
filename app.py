"""
app.py — FC 26 custom-team browser (NiceGUI)

McDonald's-basket UX:
  search / filter / NL  →  results with [+]  →  squad panel always visible
  new search does NOT clear the basket

Default sandbox target: Leeds United (team_id 7) — same A–Z letter as
Liverpool, white shirts, easy to spot in Kick Off.

Run:
    python app.py
    # opens http://127.0.0.1:8080

Optional:
    set GROQ_API_KEY=...     # natural language filters
    set GEMINI_API_KEY=...   # fallback provider
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from nicegui import ui

from player_data import filter_players, load_players, search_by_name
from shortlist import (
    Shortlist,
    ShortlistPlayer,
    assign_jerseys,
    delete_preset,
    export_cli_command,
    list_presets,
    load_db,
    load_preset,
    resolve_from_teams,
    save_json,
    save_preset,
)
from nl_query import ask_nl, run_filter_code, run_nl_query

SCRIPT_DIR = Path(__file__).resolve().parent
# Leeds United — verified via find_sandbox_teams.py (Prem, roster ~26, letter L)
DEFAULT_TARGET = 7
DEFAULT_TARGET_NAME = "Leeds United"
EXPORT_PATH = SCRIPT_DIR / "output" / "shortlist.json"

PRESET_TARGET_TEAMS: dict[int, str] = {
    # --- Premier League ---
    7: "Leeds United (Prem)",
    8: "Liverpool (Prem)",
    9: "Manchester City (Prem)",
    10: "Man Utd (Prem)",
    0: "Arsenal (Prem)",
    4: "Chelsea (Prem)",
    17: "Spurs (Prem)",
    1: "Aston Villa (Prem)",
    12: "Newcastle Utd (Prem)",
    13: "Nott'm Forest (Prem)",
    18: "West Ham (Prem)",
    109: "Wolves (Prem)",
    143: "Fulham (Prem)",
    6: "Everton (Prem)",
    1798: "Crystal Palace (Prem)",
    1807: "Brighton (Prem)",
    1924: "Brentford (Prem)",
    1942: "AFC Bournemouth (Prem)",
    1795: "Burnley (Prem)",
    16: "Southampton (Prem)",
    94: "Leicester City (Prem)",
    93: "Ipswich (Prem)",
    105: "Sunderland (Prem)",

    # --- Champions League Group 1 / Elite ---
    242: "Real Madrid (UCL)",
    240: "FC Barcelona (UCL)",
    20: "FC Bayern München (UCL)",
    21: "Borussia Dortmund (UCL)",
    31: "Bayer Leverkusen (UCL)",
    112171: "RB Leipzig (UCL)",
    72: "Paris SG (UCL)",
    131681: "Inter Milan / Lombardia (UCL)",
    131680: "AC Milan / Milano (UCL)",
    44: "Juventus (UCL)",
    47: "SSC Napoli (UCL)",
    51: "AS Roma (UCL)",
    239: "Atlético de Madrid (UCL)",
    233: "SL Benfica (UCL)",
    236: "Sporting CP (UCL)",
    235: "FC Porto (UCL)",
    244: "Ajax (UCL)",
    246: "PSV (UCL)",
    245: "Feyenoord (UCL)",
    77: "Celtic (UCL)",
    324: "Galatasaray (UCL)",
    68: "AS Monaco (UCL)",
}

# ── app state (process-local; single-user POC) ──────────────────────────
df: pd.DataFrame = pd.DataFrame()
results_df: pd.DataFrame = pd.DataFrame()
shortlist = Shortlist(target_team=DEFAULT_TARGET, target_name=DEFAULT_TARGET_NAME)
last_nl_code: str = ""
status_msg: str = ""
nl_chat_history: list[dict[str, str]] = []

# widget refs filled in build_ui()
name_in = position_in = playstyle_in = None
min_ovr = max_ovr = max_wage = min_playstyles = None
extra_cols_sel = None
nl_in = provider_sel = model_sel = None
export_cmd_area = export_warn_area = None
target_team_sel = None
preset_name_in = preset_sel = None
nl_display_cols: list[str] | None = None


def do_save_preset() -> None:
    name = (preset_name_in.value or "").strip()
    if not name:
        ui.notify("Type a preset name first (e.g. Liverpool New Signings)", type="warning")
        return
    if not shortlist.players:
        ui.notify("Squad is empty — add some players first", type="warning")
        return
    path = save_preset(shortlist, name)
    render_preset_selector.refresh()
    ui.notify(f"Saved preset '{name}' → {path.name}", type="positive")


def do_load_preset() -> None:
    global shortlist
    val = preset_sel.value if preset_sel else None
    if not val:
        ui.notify("Select a preset from the dropdown first", type="warning")
        return
    try:
        sl = load_preset(val)
        shortlist.target_team = sl.target_team
        shortlist.target_name = sl.target_name
        shortlist.players = sl.players
        if target_team_sel:
            target_team_sel.value = shortlist.target_team
        render_basket.refresh()
        render_results.refresh()
        render_export_info.refresh()
        ui.notify(f"Loaded preset '{sl.target_name}' ({len(sl.players)} players)", type="positive")
    except Exception as e:
        ui.notify(f"Error loading preset: {e}", type="negative")


def do_delete_preset() -> None:
    val = preset_sel.value if preset_sel else None
    if not val:
        ui.notify("Select a preset from the dropdown first", type="warning")
        return
    if delete_preset(val):
        render_preset_selector.refresh()
        ui.notify("Preset deleted", type="info")
    else:
        ui.notify("Failed to delete preset", type="negative")


@ui.refreshable
def render_preset_selector() -> None:
    global preset_name_in, preset_sel
    presets = list_presets()
    opts = {p["path"]: f"{p['preset_name']} ({p['target_name']}, {p['player_count']} p)" for p in presets}

    with ui.column().classes("w-full gap-2"):
        ui.label("Squad Presets").classes("text-xs font-bold text-gray-500 uppercase tracking-wider")
        with ui.row().classes("w-full gap-1 items-center"):
            preset_name_in = ui.input(placeholder="Preset name (e.g. Big Guys)").classes("flex-grow")
            ui.button("Save", on_click=do_save_preset, icon="save").props("dense unelevated color=secondary")

        if opts:
            with ui.row().classes("w-full gap-1 items-center"):
                preset_sel = ui.select(options=opts, label="Load saved preset").classes("flex-grow")
                ui.button(icon="folder_open", on_click=do_load_preset).props("dense unelevated color=primary").tooltip("Load selected preset")
                ui.button(icon="delete", on_click=do_delete_preset).props("dense flat color=negative").tooltip("Delete selected preset")


def _fmt_money(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    try:
        n = float(v)
    except (TypeError, ValueError):
        return "—"
    if n >= 1_000_000:
        return f"€{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"€{n / 1_000:.0f}K"
    return f"€{n:.0f}"


def _row_to_player(row) -> ShortlistPlayer:
    def _get(key):
        if hasattr(row, "get"):
            return row.get(key)
        return getattr(row, key, None)

    def _i(key):
        v = _get(key)
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return None
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    def _f(key):
        v = _get(key)
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    return ShortlistPlayer(
        player_id=int(_get("player_id")),
        name=str(_get("name") or ""),
        overall=_i("overall"),
        position=str(_get("position") or ""),
        wage_eur=_f("wage_eur"),
        value_eur=_f("value_eur"),
        pace=_i("pace"),
        stamina=_i("stamina"),
    )


def do_search() -> None:
    global results_df, status_msg, nl_display_cols
    nl_display_cols = None
    name = (name_in.value or "").strip()
    pos = position_in.value if position_in.value and position_in.value != "Any" else None
    ps = (playstyle_in.value or "").strip() or None

    def _num(w):
        try:
            v = w.value
            if v is None or v == "":
                return None
            return type(v)(v) if not isinstance(v, (int, float)) else v
        except (TypeError, ValueError):
            return None

    try:
        min_o = int(min_ovr.value) if min_ovr.value not in (None, "") else None
    except (TypeError, ValueError):
        min_o = None
    try:
        max_o = int(max_ovr.value) if max_ovr.value not in (None, "") else None
    except (TypeError, ValueError):
        max_o = None
    try:
        max_w = float(max_wage.value) if max_wage.value not in (None, "") else None
    except (TypeError, ValueError):
        max_w = None
    try:
        min_ps = int(min_playstyles.value) if min_playstyles.value not in (None, "") else None
    except (TypeError, ValueError):
        min_ps = None

    results_df = filter_players(
        df,
        name=name or None,
        position=pos,
        min_ovr=min_o,
        max_ovr=max_o,
        playstyle=ps,
        min_playstyles=min_ps,
        max_wage=max_w,
        gender="M",
        limit=60,
    )
    status_msg = f"{len(results_df)} players"
    render_results.refresh()
    status_label.refresh()


def do_nl() -> None:
    global results_df, last_nl_code, status_msg, nl_chat_history, nl_display_cols
    q = (nl_in.value or "").strip()
    if not q:
        ui.notify("Type a natural language query first", type="warning")
        return
    provider = provider_sel.value or "groq"
    model = model_sel.value if provider == "groq" else None
    result, code, err, new_entries, display_cols = run_nl_query(
        q, df, provider=provider, model=model, history=nl_chat_history, max_retries=1
    )
    # Transparent fallback if qwen hits its Groq rate limit.
    if err and provider == "groq" and model == "qwen/qwen3.6-27b" and "rate limit" in err.lower():
        ui.notify("qwen rate limited — trying openai/gpt-oss-120b…", type="warning")
        result, code, err, new_entries, display_cols = run_nl_query(
            q, df, provider=provider, model="openai/gpt-oss-120b",
            history=nl_chat_history, max_retries=1,
        )
    if err:
        ui.notify(err, type="negative")
        status_msg = err
        status_label.refresh()
        return
    last_nl_code = code or ""
    nl_display_cols = display_cols
    nl_chat_history.extend(new_entries)
    # Keep history bounded to avoid token bloat (last 6 messages ≈ 3 turns)
    nl_chat_history = nl_chat_history[-6:]
    results_df = result if result is not None else df.head(0)
    status_msg = f"NL → {len(results_df)} players"
    code_view.refresh()
    render_results.refresh()
    status_label.refresh()
    ui.notify(f"Found {len(results_df)} players", type="positive")


def add_player(pid: int) -> None:
    row = df[df["player_id"] == pid]
    if row.empty:
        row = results_df[results_df["player_id"] == pid]
    if row.empty:
        ui.notify(f"player {pid} not found", type="warning")
        return
    p = _row_to_player(row.iloc[0])
    if shortlist.add(p):
        ui.notify(f"Added {p.name}", type="positive")
    else:
        ui.notify(f"{p.name} already in squad", type="info")
    render_basket.refresh()
    render_results.refresh()


def remove_player(pid: int) -> None:
    shortlist.remove(pid)
    render_basket.refresh()
    render_results.refresh()


def clear_basket() -> None:
    shortlist.clear()
    render_basket.refresh()
    render_results.refresh()
    ui.notify("Squad cleared")


def clear_nl_chat() -> None:
    global nl_chat_history
    nl_chat_history.clear()
    ui.notify("NL chat cleared")


def do_export() -> None:
    global status_msg
    try:
        db = load_db()
    except Exception as e:
        ui.notify(f"Cannot load T3DB: {e}", type="negative")
        return
    warns = resolve_from_teams(shortlist, db)
    assign_jerseys(shortlist, db)
    save_json(shortlist, EXPORT_PATH)
    cmd = export_cli_command(shortlist)
    export_cmd_area.value = cmd
    export_warn_area.value = "\n".join(warns) if warns else "(no warnings)"
    status_msg = f"Exported {len(shortlist.players)} players → {EXPORT_PATH.name}"
    status_label.refresh()
    render_basket.refresh()
    ui.notify("Export ready — copy the command below", type="positive")


@ui.refreshable
def status_label() -> None:
    ui.label(status_msg or "Ready").classes("text-sm text-gray-500")


@ui.refreshable
def code_view() -> None:
    if last_nl_code:
        with ui.expansion("What the AI ran (pandas)", icon="code").classes("w-full"):
            ui.code(last_nl_code, language="python").classes("w-full")


_PS_ABBREV_MAP = {
    # Passing & Playmaking
    "incisive pass": "Incisive",
    "long ball pass": "Long Ball",
    "pinged pass": "Pinged Pass",
    "whipped pass": "Whipped",
    "whipped cross": "Whipped",
    "tiki taka": "Tiki Taka",
    "dead ball": "Dead Ball",
    # Shooting
    "finesse shot": "Finesse",
    "power shot": "Pwr Shot",
    "chip shot": "Chip Shot",
    "low driven shot": "Low Driven",
    "precision header": "Prec Header",
    "power header": "Pwr Header",
    # Dribbling & Ball Control
    "technical": "Technical",
    "technical dribbler": "Technical",
    "first touch": "1st Touch",
    "rapid": "Rapid",
    "quick step": "Quick Step",
    "trickster": "Trickster",
    "press proven": "Press Prv",
    "gamechanger": "Gamechanger",
    # Defending & Physical
    "intercept": "Intercept",
    "anticipate": "Anticipate",
    "slide tackle": "Slide Tkl",
    "jockey": "Jockey",
    "block": "Block",
    "bruiser": "Bruiser",
    "enforcer": "Enforcer",
    "relentless": "Relentless",
    "acrobatic": "Acrobatic",
    "aerial fortress": "Aerial",
    "aerial": "Aerial",
    "trivela": "Trivela",
    "long throw": "Long Throw",
    "far throw": "Far Throw",
    "inventive": "Inventive",
    # Goalkeeping
    "cross claimer": "Cross Claim",
    "far reach": "Far Reach",
    "deflector": "Deflector",
    "footwork": "Footwork",
    "rush out": "Rush Out",
}


def _abbrev_play_style(ps: str) -> tuple[str, bool]:
    clean = ps.strip()
    is_plus = clean.endswith("+")
    base = clean[:-1].strip() if is_plus else clean
    short_base = _PS_ABBREV_MAP.get(base.lower(), base)
    return (f"{short_base}+" if is_plus else short_base), is_plus


def _render_play_styles(row) -> None:
    play_styles = str(row.get("play_styles", ""))
    ps_list = [p.strip() for p in play_styles.split("|") if p and p.strip().lower() not in ("nan", "none")]
    with ui.row().classes("w-96 items-center no-wrap overflow-x-auto gap-1"):
        ui.badge(str(len(ps_list)), color="gray").classes("mr-1 text-xs shrink-0")
        for ps in ps_list:
            label, is_plus = _abbrev_play_style(ps)
            color = "amber-8" if is_plus else "purple-7"
            ui.badge(label, color=color).classes("text-xs whitespace-nowrap font-medium")


def _render_col(col: str, row) -> None:
    val = row.get(col, "")
    if col == "play_styles":
        _render_play_styles(row)
    elif col in ("wage_eur", "value_eur"):
        ui.label(_fmt_money(val)).classes("w-20 text-xs text-gray-500")
    elif col == "name":
        ui.label(str(val)).classes("font-medium w-44 truncate")
    elif col == "position":
        ui.label(str(val)).classes("w-10 text-sm font-bold")
    elif col == "overall":
        ui.label(str(val) if pd.notna(val) else "-").classes("w-8 text-sm font-bold text-blue-600")
    elif col == "pace":
        v_str = str(int(val)) if (pd.notna(val) and str(val) != "") else "-"
        ui.label(v_str).classes("w-10 text-xs font-bold text-amber-700 dark:text-amber-400")
    elif col == "stamina":
        v_str = str(int(val)) if (pd.notna(val) and str(val) != "") else "-"
        ui.label(v_str).classes("w-10 text-xs font-bold text-emerald-700 dark:text-emerald-400")
    else:
        ui.label(str(val)).classes("w-20 text-xs text-gray-500 truncate")


@ui.refreshable
def render_results() -> None:
    if results_df is None or results_df.empty:
        ui.label("No results — search or ask NL.").classes("text-gray-500")
        return

    extra_c = extra_cols_sel.value if extra_cols_sel else []
    ai_cols = nl_display_cols

    with ui.element("div").classes("w-full overflow-x-auto overflow-y-auto").style("max-height: 70vh"):
        with ui.column().classes("w-full gap-1 min-w-max"):
            # Header Row
            with ui.row().classes(
                "w-full items-center no-wrap bg-slate-200 dark:bg-slate-800 "
                "py-1.5 px-2 gap-3 text-xs font-bold uppercase tracking-wider text-slate-600 dark:text-slate-300 rounded mb-1"
            ):
                if ai_cols:
                    for col in ai_cols:
                        w_cls = "w-44" if col == "name" else ("w-96" if col == "play_styles" else ("w-10" if col in ("position", "pace", "stamina") else ("w-8" if col == "overall" else "w-20")))
                        ui.label(col.replace("_", " ").upper()).classes(w_cls)
                else:
                    ui.label("POS").classes("w-10")
                    ui.label("NAME").classes("w-44")
                    ui.label("OVR").classes("w-8")
                    ui.label("PAC").classes("w-10")
                    ui.label("STA").classes("w-10")
                    ui.label("PLAY STYLES").classes("w-96")
                    for col in extra_c:
                        ui.label(col[:6].upper()).classes("w-20")
                ui.space()
                ui.label("ACTION").classes("w-16 text-right")

            # Data Rows
            for _, row in results_df.iterrows():
                pid = int(row["player_id"])
                in_squad = pid in shortlist.ids()
                with ui.row().classes(
                    "w-full items-center no-wrap border-b py-1 px-2 "
                    "hover:bg-slate-100 dark:hover:bg-slate-800 gap-3"
                ):
                    if ai_cols:
                        for col in ai_cols:
                            _render_col(col, row)
                    else:
                        # 1. POS | 2. NAME | 3. OVR
                        ui.label(str(row.get("position", ""))).classes("w-10 text-sm font-bold")
                        ui.label(str(row.get("name", ""))).classes("font-medium w-44 truncate")
                        ui.label(str(row.get("overall", ""))).classes("w-8 text-sm font-bold text-blue-600")

                        # 4. PAC (Pace)
                        pac_val = row.get("pace")
                        pac_str = str(int(pac_val)) if (pd.notna(pac_val) and str(pac_val) != "") else "-"
                        ui.label(pac_str).classes("w-10 text-xs font-bold text-amber-700 dark:text-amber-400")

                        # 5. STA (Stamina)
                        sta_val = row.get("stamina")
                        sta_str = str(int(sta_val)) if (pd.notna(sta_val) and str(sta_val) != "") else "-"
                        ui.label(sta_str).classes("w-10 text-xs font-bold text-emerald-700 dark:text-emerald-400")

                        # 6. Play styles count & list
                        _render_play_styles(row)

                        # 7. Dynamic extra columns
                        for col in extra_c:
                            val = row.get(col, "")
                            if col in ("wage_eur", "value_eur"):
                                val = _fmt_money(val)
                            ui.label(f"{col[:3].upper()} {val}").classes("w-20 text-xs text-gray-500 truncate")

                    ui.space()

                    # + / IN SQUAD button
                    if in_squad:
                        ui.badge("IN SQUAD", color="green")
                    else:
                        ui.button("+", on_click=lambda p=pid: add_player(p)).props(
                            "round dense unelevated color=primary"
                        ).tooltip("Add to squad")


def on_target_team_change(e) -> None:
    try:
        tid = int(e.value)
    except (TypeError, ValueError):
        return
    label = PRESET_TARGET_TEAMS.get(tid, f"Team {tid}")
    name = label.split(" (")[0]
    shortlist.target_team = tid
    shortlist.target_name = name
    render_basket.refresh()
    render_export_info.refresh()
    ui.notify(f"Target team set to {name} (id {tid})", type="info")


@ui.refreshable
def render_export_info() -> None:
    ui.label(
        f"FC 26 closed → run this → deploy_squads.bat option 1 → "
        f"offline Kick Off → pick {shortlist.target_name}"
    ).classes("text-xs text-gray-500")


@ui.refreshable
def render_basket() -> None:
    ui.label(f"Your squad ({len(shortlist.players)})").classes("text-lg font-bold")
    ui.label(
        f"Target: {shortlist.target_name} (id {shortlist.target_team})"
    ).classes("text-sm text-gray-500 font-medium")
    if not shortlist.players:
        ui.label("Empty — click + on search results.").classes("text-gray-400 italic")
        return
    for p in shortlist.players:
        with ui.row().classes("w-full items-center no-wrap border-b py-1 gap-2"):
            shirt = (p.jersey_stored + 1) if p.jersey_stored is not None else "?"
            # 1. POS | 2. NAME | 3. OVR
            ui.label(f"{p.position or ''}").classes("w-10 text-xs font-bold")
            ui.label(f"{p.name}").classes("font-medium flex-grow truncate")
            ui.label(f"OVR {p.overall or '?'}").classes("w-12 text-sm font-bold text-gray-500")
            ui.label(f"#{shirt}").classes("w-8 text-xs text-gray-400")
            ui.button(
                icon="close",
                on_click=lambda pid=p.player_id: remove_player(pid),
            ).props("flat dense round color=negative").tooltip("Remove")


def build_ui() -> None:
    global name_in, position_in, playstyle_in, min_ovr, max_ovr
    global max_wage, min_playstyles, extra_cols_sel, nl_in, provider_sel, model_sel
    global export_cmd_area, export_warn_area, target_team_sel

    ui.page_title("FC 26 Team Builder")
    ui.colors(primary="#FFCD00")  # Leeds gold-ish

    with ui.header().classes("items-center justify-between bg-neutral-900 p-2"):
        ui.label("⚽ FC 26 Custom Team Builder").classes("text-base font-bold text-white")
        ui.label("→ Premier League & Champions League Teams · OFFLINE Kick Off only").classes(
            "text-xs text-white opacity-80"
        )

    with ui.row().classes("w-full no-wrap gap-2 p-2").style("min-height: 85vh"):
        # LEFT: search
        with ui.column().classes("gap-1").style("flex: 2; min-width: 0"):
            ui.label("Search").classes("text-base font-bold")

            with ui.row().classes("w-full gap-1 items-end flex-wrap"):
                name_in = ui.input("Name", placeholder="Salah, Messi…").classes("w-48")
                name_in.on("keydown.enter", lambda: do_search())
                positions = [
                    "Any", "GK", "CB", "LB", "RB", "CDM", "CM", "CAM",
                    "LM", "RM", "LW", "RW", "ST", "CF",
                ]
                position_in = ui.select(
                    positions, value="Any", label="Position"
                ).classes("w-28")
                playstyle_in = ui.input(
                    "PlayStyle", placeholder="Finesse, Rapid…"
                ).classes("w-40")
                min_ovr = ui.number("Min OVR", value=None, min=40, max=99).classes("w-24")
                max_ovr = ui.number("Max OVR", value=None, min=40, max=99).classes("w-24")
                min_playstyles = ui.number("Min playstyles", value=None, min=0, max=20).classes("w-24")
                max_wage = ui.number("Max wage €", value=None).classes("w-28")
                extra_cols_sel = ui.select(
                    [
                        "pace", "shooting", "passing", "dribbling",
                        "defending", "physical", "vision", "wage_eur", "value_eur",
                    ],
                    multiple=True,
                    label="Extra cols",
                    on_change=lambda: render_results.refresh(),
                ).classes("w-48")
                ui.button("Search", on_click=do_search, icon="search").props(
                    "unelevated"
                )

            with ui.card().classes("w-full p-2"):
                ui.label("Natural language").classes("font-medium text-sm")
                ui.label(
                    'e.g. "tall slow CBs under 50k wage" · '
                    '"pace merchants ST under 80 OVR"'
                ).classes("text-xs text-gray-500")
                with ui.row().classes("w-full gap-1 items-end"):
                    nl_in = ui.input(
                        placeholder="Ask in plain English…"
                    ).classes("flex-grow")
                    nl_in.on("keydown.enter", lambda: do_nl())
                    provider_sel = ui.select(
                        ["groq", "gemini"], value="groq", label="API"
                    ).classes("w-28")
                    model_sel = ui.select(
                        ["qwen/qwen3.6-27b", "openai/gpt-oss-120b"],
                        value="qwen/qwen3.6-27b",
                        label="Model",
                    ).classes("w-40")
                    ui.button("Ask AI", on_click=do_nl, icon="smart_toy").props(
                        "unelevated color=secondary"
                    )
                    ui.button("Clear chat", on_click=clear_nl_chat, icon="delete").props(
                        "flat"
                    )
                code_view()

            status_label()
            ui.separator()
            render_results()

        # RIGHT: basket
        with ui.column().classes("gap-2").style("flex: 1; min-width: 280px"):
            with ui.card().classes("w-full"):
                render_preset_selector()
                ui.separator().classes("my-2")
                ui.label("Preferred Target Team").classes("text-xs font-bold text-gray-500 uppercase tracking-wider")
                target_team_sel = ui.select(
                    options=PRESET_TARGET_TEAMS,
                    value=shortlist.target_team,
                    on_change=on_target_team_change,
                ).classes("w-full").props("dense outlined")
                ui.separator().classes("my-1")
                render_basket()
                with ui.row().classes("w-full gap-2 mt-2"):
                    ui.button("Clear", on_click=clear_basket, icon="delete").props(
                        "flat"
                    )
                    ui.button(
                        "Export swaps", on_click=do_export, icon="download"
                    ).props("unelevated color=primary")

            with ui.card().classes("w-full"):
                ui.label("Export command").classes("font-medium")
                render_export_info()
                export_cmd_area = (
                    ui.textarea(value="").classes("w-full").props("readonly rows=4")
                )
                export_warn_area = (
                    ui.textarea(label="Warnings", value="")
                    .classes("w-full")
                    .props("readonly rows=2")
                )
                ui.label(f"Also saved to {EXPORT_PATH}").classes(
                    "text-xs text-gray-400"
                )

            with ui.card().classes("w-full"):
                ui.markdown(
                    "**Safety:** offline Kick Off only. "
                    "Never go online with modded squads. "
                    "Restore via `deploy_squads.bat` option 2 before online play."
                ).classes("text-sm")


def main() -> None:
    global df, results_df, status_msg
    df = load_players()
    results_df = df.head(0)
    status_msg = f"Loaded {len(df)} players — try a search"
    build_ui()
    ui.run(
        title="FC 26 Team Builder",
        host="127.0.0.1",
        port=8080,
        reload=False,
        show=True,
    )


if __name__ in {"__main__", "__mp_main__"}:
    main()
