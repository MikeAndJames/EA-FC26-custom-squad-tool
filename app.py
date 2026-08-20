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
from mini_me import MiniMeEngine
from dataclasses import asdict
from sabotage_draft_ui import init_draft_routes

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

    # --- Champions League / Elite Clubs ---
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

    # --- World Cup 2026 / International Teams ---
    1317: "🏴󠁧󠁢󠁥󠁮󠁧󠁿 England (National Team)",
    1334: "🇫🇷 France (National Team)",
    1368: "🇦🇷 Argentina (National Team)",
    1369: "🇧🇷 Brazil (National Team)",
    1361: "🇪🇸 Spain (National Team)",
    1336: "🇩🇪 Germany (National Team)",
    1353: "🇵🇹 Portugal (National Team)",
    1342: "🇮🇹 Italy (National Team)",
    1324: "🇧🇪 Belgium (National Team)",
    1327: "🇭🇷 Croatia (National Team)",
    1330: "🇩🇰 Denmark (National Team)",
    1351: "🇳🇴 Norway (National Team)",
    1352: "🇵🇱 Poland (National Team)",
    1358: "🏴󠁧󠁢󠁳󠁣󠁴󠁿 Scotland (National Team)",
    1366: "🏴󠁧󠁢󠁷󠁬󠁳󠁿 Wales (National Team)",
    1354: "🇮🇪 Republic of Ireland (National Team)",
    1363: "🇨🇭 Switzerland (National Team)",
    1364: "🇹🇷 Turkey (National Team)",
    1365: "🇺🇦 Ukraine (National Team)",
    1386: "🇺🇸 USA (National Team)",
    1385: "🇲🇽 Mexico (National Team)",
    1376: "🇺🇾 Uruguay (National Team)",
    1374: "🇵🇾 Paraguay (National Team)",
    1410: "🇯🇵 Japan (National Team)",
    1414: "🇦🇺 Australia (National Team)",
}

# ── app state (process-local; single-user POC) ──────────────────────────
df: pd.DataFrame = pd.DataFrame()
results_df: pd.DataFrame = pd.DataFrame()
shortlist = Shortlist(target_team=DEFAULT_TARGET, target_name=DEFAULT_TARGET_NAME)
last_nl_code: str = ""
status_msg: str = ""
nl_chat_history: list[dict[str, str]] = []

# widget refs filled in build_ui()
name_in = position_in = club_in = league_in = nation_in = playstyle_in = icons_only_in = None
min_ovr = max_ovr = max_wage = min_playstyles = min_age = max_age = None
extra_cols_sel = None
nl_in = provider_sel = model_sel = None
target_team_sel = None
preset_name_in = preset_sel = None
nl_display_cols: list[str] | None = None

EXTRA_COL_OPTIONS: dict[str, str] = {
    "alt_positions": "Alt Positions",
    "team": "Club",
    "league": "League",
    "nation": "Nationality",
    "pace": "Pace",
    "shooting": "Shooting",
    "passing": "Passing",
    "dribbling": "Dribbling",
    "defending": "Defending",
    "physical": "Physical",
    "vision": "Vision",
    "wage_eur": "Wage €",
    "value_eur": "Value €",
    "age": "Age",
    "height": "Height",
}


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
        
        # Auto-fill the input box with the loaded preset's name so hitting Save will overwrite it
        from pathlib import Path
        if preset_name_in:
            preset_name_in.value = Path(val).stem.replace("_", " ").title()

        render_basket.refresh()
        render_results.refresh()
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
    opts = {
        p["path"]: f"{p['preset_name']} ({p['target_name']}, {p['player_count']} p) [{p.get('mtime_str', '')}]"
        for p in presets
    }

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


def _get_pos_display(row) -> tuple[str, str, str]:
    def _val(key):
        if hasattr(row, "get"):
            v = row.get(key)
        else:
            v = getattr(row, key, None)
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return ""
        return str(v).strip()

    pos = _val("position")
    alt = _val("alt_positions")
    if alt.lower() == "nan":
        alt = ""

    if "," in pos or " " in pos:
        parts = [p.strip() for p in pos.replace(",", " ").split() if p.strip()]
        if parts:
            pos = parts[0]
            if not alt and len(parts) > 1:
                alt = " ".join(parts[1:])

    alt_list = []
    if alt:
        for p in alt.replace(",", " ").split():
            p_c = p.strip()
            if p_c and p_c != pos and p_c not in alt_list:
                alt_list.append(p_c)

    alt_str = ", ".join(alt_list)
    if alt_str:
        return pos, f"({alt_str})", f"{pos} ({alt_str})"
    return pos, "", pos


def _render_pos(row) -> None:
    p_main, p_alt, p_full = _get_pos_display(row)
    alt_text = p_alt.strip("()") if p_alt else ""
    with ui.column().classes("w-28 gap-0 leading-tight shrink-0 justify-center"):
        ui.label(p_main or "-").classes("font-extrabold text-xs text-blue-600 dark:text-blue-400")
        if alt_text:
            ui.label(alt_text).classes("text-[10px] text-gray-500 dark:text-gray-400 font-medium truncate max-w-full").tooltip(
                f"Primary: {p_main} | Alternate: {alt_text}"
            )


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

    p_main, p_alt, p_full = _get_pos_display(row)
    return ShortlistPlayer(
        player_id=int(_get("player_id")),
        name=str(_get("name") or ""),
        overall=_i("overall"),
        position=p_full,
        wage_eur=_f("wage_eur"),
        value_eur=_f("value_eur"),
        pace=_i("pace"),
        stamina=_i("stamina"),
    )


def do_search() -> None:
    global results_df, status_msg, nl_display_cols
    nl_display_cols = None
    name = (name_in.value or "").strip() if name_in else None
    pos = position_in.value if position_in and position_in.value and position_in.value != "Any" else None
    club = (club_in.value or "").strip() if club_in else None
    league = (league_in.value or "").strip() if league_in else None
    nation = (nation_in.value or "").strip() if nation_in else None
    ps = (playstyle_in.value or "").strip() if playstyle_in else None

    def _num(w):
        try:
            v = w.value
            if v is None or v == "":
                return None
            return type(v)(v) if not isinstance(v, (int, float)) else v
        except (TypeError, ValueError):
            return None

    try:
        min_o = int(min_ovr.value) if min_ovr and min_ovr.value not in (None, "") else None
    except (TypeError, ValueError):
        min_o = None
    try:
        max_o = int(max_ovr.value) if max_ovr and max_ovr.value not in (None, "") else None
    except (TypeError, ValueError):
        max_o = None
    try:
        max_w = float(max_wage.value) if max_wage and max_wage.value not in (None, "") else None
    except (TypeError, ValueError):
        max_w = None
    try:
        min_ps = int(min_playstyles.value) if min_playstyles and min_playstyles.value not in (None, "") else None
    except (TypeError, ValueError):
        min_ps = None
    try:
        min_a = int(min_age.value) if min_age and min_age.value not in (None, "") else None
    except (TypeError, ValueError):
        min_a = None
    try:
        max_a = int(max_age.value) if max_age and max_age.value not in (None, "") else None
    except (TypeError, ValueError):
        max_a = None

    icons_only = bool(icons_only_in.value) if icons_only_in else False

    results_df = filter_players(
        df,
        name=name or None,
        position=pos,
        club=club or None,
        league=league or None,
        nationality=nation or None,
        icons_only=icons_only,
        min_ovr=min_o,
        max_ovr=max_o,
        min_age=min_a,
        max_age=max_a,
        playstyle=ps or None,
        min_playstyles=min_ps,
        max_wage=max_w,
        gender="M",
        limit=200,
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
    with ui.row().classes("w-60 items-center no-wrap overflow-x-auto gap-1 shrink-0"):
        ui.badge(str(len(ps_list)), color="gray").classes("mr-1 text-xs shrink-0")
        for ps in ps_list:
            label, is_plus = _abbrev_play_style(ps)
            color = "amber-8" if is_plus else "purple-7"
            ui.badge(label, color=color).classes("text-xs whitespace-nowrap font-medium")


def _col_header_info(col: str) -> tuple[str, str]:
    c = str(col).lower()
    if c in ("team", "club"):
        return "CLUB", "w-32"
    if c == "league":
        return "LEAGUE", "w-32"
    if c in ("nation", "nationality"):
        return "NATIONALITY", "w-24"
    if c == "name":
        return "NAME", "w-36"
    if c == "play_styles":
        return "PLAY STYLES", "w-60"
    if c == "position":
        return "POS", "w-28"
    if c == "alt_positions":
        return "ALT POS", "w-24"
    if c == "overall":
        return "OVR", "w-8"
    if c == "pace":
        return "PAC", "w-8"
    if c == "stamina":
        return "STA", "w-8"
    if c in ("wage_eur", "value_eur"):
        return c.replace("_eur", "").upper(), "w-20"
    if c in ("age", "height", "weight"):
        return c.upper(), "w-12"
    return c[:6].upper(), "w-20"


def _render_col(col: str, row) -> None:
    val = row.get(col, "")
    c = str(col).lower()
    if c == "play_styles":
        _render_play_styles(row)
    elif c in ("wage_eur", "value_eur"):
        ui.label(_fmt_money(val)).classes("w-20 text-xs text-gray-500 shrink-0")
    elif c == "name":
        ui.label(str(val)).classes("font-medium w-36 truncate shrink-0").tooltip(str(val))
    elif c == "position":
        _render_pos(row)
    elif c == "alt_positions":
        alt_val = str(val) if (pd.notna(val) and val != "" and str(val).lower() != "nan") else "-"
        ui.label(alt_val).classes("w-24 text-xs text-gray-500 truncate shrink-0").tooltip(alt_val)
    elif c == "overall":
        ui.label(str(val) if pd.notna(val) else "-").classes("w-8 text-sm font-bold text-blue-600 shrink-0")
    elif c == "pace":
        v_str = str(int(val)) if (pd.notna(val) and str(val) != "") else "-"
        ui.label(v_str).classes("w-8 text-xs font-bold text-amber-700 dark:text-amber-400 shrink-0")
    elif c == "stamina":
        v_str = str(int(val)) if (pd.notna(val) and str(val) != "") else "-"
        ui.label(v_str).classes("w-8 text-xs font-bold text-emerald-700 dark:text-emerald-400 shrink-0")
    elif c in ("team", "club"):
        ui.label(str(val) if (pd.notna(val) and val != "") else "-").classes("w-32 text-xs text-gray-700 dark:text-gray-300 font-medium truncate")
    elif c == "league":
        ui.label(str(val) if (pd.notna(val) and val != "") else "-").classes("w-32 text-xs text-gray-500 truncate")
    elif c in ("nation", "nationality"):
        ui.label(str(val) if (pd.notna(val) and val != "") else "-").classes("w-24 text-xs text-gray-500 truncate")
    elif c in ("age", "height", "weight"):
        v_str = str(int(val)) if (pd.notna(val) and str(val) != "") else "-"
        ui.label(v_str).classes("w-12 text-xs text-gray-500")
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
                "py-1.5 px-2 gap-2 text-xs font-bold uppercase tracking-wider text-slate-600 dark:text-slate-300 rounded mb-1"
            ):
                if ai_cols:
                    for col in ai_cols:
                        title, w_cls = _col_header_info(col)
                        ui.label(title).classes(f"{w_cls} shrink-0")
                else:
                    ui.label("POS").classes("w-28 shrink-0")
                    ui.label("NAME").classes("w-36 shrink-0")
                    ui.label("OVR").classes("w-8 shrink-0")
                    ui.label("PAC").classes("w-8 shrink-0")
                    ui.label("STA").classes("w-8 shrink-0")
                    ui.label("PLAY STYLES").classes("w-60 shrink-0")
                    for col in extra_c:
                        title, w_cls = _col_header_info(col)
                        ui.label(title).classes(f"{w_cls} shrink-0")
                ui.space()
                ui.label("ACTION").classes("w-14 text-right shrink-0")

            # Data Rows
            for _, row in results_df.iterrows():
                pid = int(row["player_id"])
                in_squad = pid in shortlist.ids()
                with ui.row().classes(
                    "w-full items-center no-wrap border-b py-1 px-2 "
                    "hover:bg-slate-100 dark:hover:bg-slate-800 gap-2"
                ):
                    if ai_cols:
                        for col in ai_cols:
                            _render_col(col, row)
                    else:
                        # 1. POS | 2. NAME | 3. OVR
                        _render_pos(row)
                        ui.label(str(row.get("name", ""))).classes("font-medium w-36 truncate shrink-0").tooltip(str(row.get("name", "")))
                        ui.label(str(row.get("overall", ""))).classes("w-8 text-sm font-bold text-blue-600 shrink-0")

                        # 4. PAC (Pace)
                        pac_val = row.get("pace")
                        pac_str = str(int(pac_val)) if (pd.notna(pac_val) and str(pac_val) != "") else "-"
                        ui.label(pac_str).classes("w-8 text-xs font-bold text-amber-700 dark:text-amber-400 shrink-0")

                        # 5. STA (Stamina)
                        sta_val = row.get("stamina")
                        sta_str = str(int(sta_val)) if (pd.notna(sta_val) and str(sta_val) != "") else "-"
                        ui.label(sta_str).classes("w-8 text-xs font-bold text-emerald-700 dark:text-emerald-400 shrink-0")

                        # 6. Play styles count & list
                        _render_play_styles(row)

                        # 7. Dynamic extra columns
                        for col in extra_c:
                            _render_col(col, row)

                    ui.space()

                    # + / IN SQUAD button
                    with ui.row().classes("w-14 justify-end shrink-0"):
                        if in_squad:
                            ui.badge("IN SQUAD", color="green").classes("text-[10px]")
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
    ui.notify(f"Target team set to {name} (id {tid})", type="info")

@ui.refreshable
def render_basket() -> None:
    ui.label(f"Your squad ({len(shortlist.players)})").classes("text-lg font-bold")
    ui.label(
        f"Default Target: {shortlist.target_name} (id {shortlist.target_team})"
    ).classes("text-xs text-gray-500 font-medium mb-1")
    if not shortlist.players:
        ui.label("Empty — click + on search results.").classes("text-gray-400 italic")
        return
    for p in shortlist.players:
        with ui.row().classes("w-full items-center no-wrap border-b py-1 gap-1"):
            shirt = (p.jersey_stored + 1) if p.jersey_stored is not None else "?"
            # 1. POS | 2. NAME | 3. OVR
            _render_pos(p)
            ui.label(f"{p.name}").classes("font-medium w-28 truncate text-xs shrink-0").tooltip(p.name)
            ui.label(f"OVR {p.overall or '?'}").classes("w-12 text-xs font-bold text-gray-500 shrink-0")
            
            # Destination team dropdown per player
            cur_dest = p.target_team if p.target_team is not None else shortlist.target_team
            def _change_dest(e, player=p):
                player.target_team = int(e.value)
                ui.notify(f"{player.name} target set to team ID {e.value}", type="info")
            
            ui.select(
                options=PRESET_TARGET_TEAMS,
                value=cur_dest,
                on_change=_change_dest,
            ).classes("w-36 text-xs").props("dense outlined label=Destination")

            ui.button(
                icon="close",
                on_click=lambda pid=p.player_id: remove_player(pid),
            ).props("flat dense round color=negative").tooltip("Remove")


mini_me_engine: MiniMeEngine | None = None

def get_mini_me_engine() -> MiniMeEngine:
    global mini_me_engine
    if mini_me_engine is None:
        mini_me_engine = MiniMeEngine(df)
    return mini_me_engine


POS_FILTER_OPTIONS = [
    "SAME", "ANY", "SKIP", "GK", "CB", "LB", "RB", "LWB", "RWB",
    "CDM", "CM", "CAM", "LM", "RM", "LW", "RW", "ST", "CF"
]


def open_mini_me_dialog() -> None:
    open_clone_dialog(mode="weaker")


def open_better_me_dialog() -> None:
    open_clone_dialog(mode="stronger")


def open_clone_dialog(mode: str = "weaker") -> None:
    if not shortlist.players:
        ui.notify("Add some players to your squad basket first (e.g. Leeds Legends)!", type="warning")
        return

    is_stronger = mode.lower() in ("stronger", "better")
    title_text = "⭐ Better-Me Super Squad Builder (Stronger Upgrades)" if is_stronger else "👥 Mini-Me Opponent Squad Builder (Weaker Clones)"
    desc_text = (
        "Matches every player on your team to their 5 closest STRONGER statistical upgrades (ranked from high to low by similarity). "
        "Pick legendary superstars or elite upgrades with the exact rating boost (+1 to +10) you want!"
        if is_stronger else
        "Matches every player on your team to their 5 closest weaker statistical clones (ranked from high to low by similarity). "
        "All candidate playable positions are shown to guarantee perfect position and flank fits."
    )
    icon_name = "auto_awesome" if is_stronger else "group_add"
    icon_color = "text-amber-500 dark:text-amber-400" if is_stronger else "text-indigo-600 dark:text-indigo-400"
    btn_color = "amber-700" if is_stronger else "indigo-700"
    pick_label = "Pick Better-Me Upgrade (Top 5 ranked by match)" if is_stronger else "Pick Mini-Me Clone (Top 5 ranked by match)"
    no_cand_msg = "No stronger upgrade found for this position." if is_stronger else "No weaker candidate found for this position."

    # Always ensure fresh engine with latest merged player data
    engine = MiniMeEngine(df)

    # Per-player state: {pid: {"pos_filter": str, "selected_clone_pid": int | None, "candidates": list}}
    state: dict[str, Any] = {
        "target_team": 93,  # Ipswich Town default
        "slots": {},
    }

    # Initialize slots for each player in basket
    for p in shortlist.players:
        pid = p.player_id
        clean_pos = str(p.position or "CM").split()[0].split("(")[0].strip().upper()
        
        # Lookup full position info
        dad_alt = ""
        p_match = df[df["player_id"] == pid]
        if not p_match.empty:
            dad_alt = str(p_match.iloc[0].get("alt_positions", "")).strip()
        if dad_alt == "nan":
            dad_alt = ""
        dad_full_pos = f"{p.position} ({dad_alt})" if dad_alt else (p.position or "POS")

        state["slots"][pid] = {
            "source": p,
            "clean_pos": clean_pos,
            "dad_full_pos": dad_full_pos,
            "pos_filter": f"SAME_{clean_pos}",
            "selected_clone_pid": None,
            "candidates": [],
        }

    def compute_all_candidates():
        used_pids = {p.player_id for p in shortlist.players}
        for pid, slot in state["slots"].items():
            pos_filter = slot["pos_filter"]
            if pos_filter == "SKIP":
                slot["candidates"] = []
                slot["selected_clone_pid"] = None
                continue

            # Pass clean role (e.g. "SAME", "RW", "LB", "CB", "ANY")
            req_role = "SAME" if pos_filter.startswith("SAME") else pos_filter
            cands = engine.find_top_clones(
                player_id=pid,
                mode=mode,
                position_filter=req_role,
                excluded_ids=used_pids,
                same_gender=True,
                top_n=5,
            )
            slot["candidates"] = cands
            cand_pids = [c["player_id"] for c in cands]
            if slot["selected_clone_pid"] not in cand_pids:
                slot["selected_clone_pid"] = cand_pids[0] if cand_pids else None

    compute_all_candidates()

    dialog = ui.dialog().classes("w-full")
    with dialog, ui.card().classes("w-[95vw] max-w-[1300px] h-[90vh] p-4 gap-3 flex flex-col"):
        with ui.row().classes("w-full items-center justify-between shrink-0 border-b pb-2"):
            with ui.row().classes("items-center gap-2"):
                ui.icon(icon_name, size="md").classes(icon_color)
                ui.label(title_text).classes("text-xl font-bold")
            ui.button(icon="close", on_click=dialog.close).props("flat round dense")

        ui.label(desc_text).classes("text-xs text-gray-500 shrink-0")

        with ui.row().classes("w-full items-center gap-4 bg-slate-100 dark:bg-slate-800 p-2 rounded shrink-0"):
            def _on_team_change(e):
                state["target_team"] = int(e.value)

            dest_label = "Better-Me Destination Team" if is_stronger else "Mini-Me Destination Team"
            ui.select(
                options=PRESET_TARGET_TEAMS,
                value=state["target_team"],
                label=dest_label,
                on_change=_on_team_change,
            ).classes("w-64").props("dense outlined")

            ui.button(
                "Recalculate All",
                on_click=lambda: [compute_all_candidates(), render_slots.refresh()],
                icon="refresh",
            ).props(f"dense unelevated color={'amber-700' if is_stronger else 'primary'}")

        @ui.refreshable
        def render_slots():
            with ui.element("div").classes("w-full overflow-y-auto flex-grow max-h-[64vh] pr-2"):
                with ui.column().classes("w-full gap-2"):
                    for pid, slot in state["slots"].items():
                        src = slot["source"]
                        cands = slot["candidates"]
                        cur_filter = slot["pos_filter"]
                        clean_p = slot["clean_pos"]
                        dad_full_p = slot["dad_full_pos"]

                        with ui.card().classes("w-full p-2 bg-slate-50 dark:bg-slate-900 border shadow-sm"):
                            with ui.row().classes("w-full items-center gap-3 no-wrap"):
                                # 1. Source Player Info (showing all positions)
                                with ui.row().classes("w-64 items-center gap-2 shrink-0"):
                                    _render_pos(src)
                                    with ui.column().classes("gap-0 w-36 truncate"):
                                        ui.label(src.name).classes("font-bold text-xs truncate").tooltip(src.name)
                                        ui.label(dad_full_p).classes("text-[10px] text-gray-500 truncate").tooltip(f"All positions: {dad_full_p}")
                                    ui.badge(f"{src.overall or '?'}", color="blue-8").classes("text-xs font-bold")

                                ui.label("➔").classes("text-gray-400 font-bold shrink-0")

                                # 2. Position Filter Dropdown for this slot
                                def _on_pos_change(e, s=slot, p_id=pid):
                                    s["pos_filter"] = str(e.value)
                                    used_pids = {p.player_id for p in shortlist.players}
                                    if s["pos_filter"] == "SKIP":
                                        s["candidates"] = []
                                        s["selected_clone_pid"] = None
                                    else:
                                        req_r = "SAME" if s["pos_filter"].startswith("SAME") else s["pos_filter"]
                                        s["candidates"] = engine.find_top_clones(
                                            player_id=p_id,
                                            mode=mode,
                                            position_filter=req_r,
                                            excluded_ids=used_pids,
                                            same_gender=True,
                                            top_n=5,
                                        )
                                        cand_pids = [c["player_id"] for c in s["candidates"]]
                                        s["selected_clone_pid"] = cand_pids[0] if cand_pids else None
                                    render_slots.refresh()

                                same_key = f"SAME_{clean_p}"
                                pos_labels = {
                                    same_key: f"Same ({clean_p})",
                                    "ANY": "Any Position",
                                    "SKIP": "🚫 SKIP Slot",
                                }
                                for p_code in POS_FILTER_OPTIONS:
                                    if p_code not in ("SAME", "ANY", "SKIP"):
                                        pos_labels[p_code] = p_code

                                ui.select(
                                    options=pos_labels,
                                    value=cur_filter,
                                    label="Search Role",
                                    on_change=_on_pos_change,
                                ).classes("w-40 text-xs shrink-0").props("dense outlined")

                                # 3. Candidate Choices (Top 3 suggestions with ALL positions displayed)
                                if cur_filter == "SKIP":
                                    ui.label("🚫 Skipped — will not clone this player.").classes("text-xs text-gray-400 italic flex-grow")
                                elif not cands:
                                    ui.label(no_cand_msg).classes("text-xs text-red-400 italic flex-grow")
                                else:
                                    cand_opts = {}
                                    for idx, c in enumerate(cands, 1):
                                        c_alt = c.get("alt_positions", "").strip()
                                        c_all_pos = f"{c['position']} ({c_alt})" if c_alt else c["position"]
                                        cand_opts[c["player_id"]] = (
                                            f"#{idx}: {c['name']} (OVR {c['overall']} {c['ovr_diff']:+d}, {c_all_pos}) "
                                            f"· {c['similarity_pct']} match · {c['team']}"
                                        )

                                    def _on_clone_select(e, s=slot):
                                        s["selected_clone_pid"] = int(e.value)

                                    ui.select(
                                        options=cand_opts,
                                        value=slot["selected_clone_pid"],
                                        label=pick_label,
                                        on_change=_on_clone_select,
                                    ).classes("flex-grow text-xs").props("dense outlined")

        render_slots()

        def do_add_to_basket():
            added_count = 0
            for pid, slot in state["slots"].items():
                chosen_pid = slot["selected_clone_pid"]
                if chosen_pid:
                    p_rows = df[df["player_id"] == chosen_pid]
                    if not p_rows.empty:
                        p_row = p_rows.iloc[0]
                        sp = ShortlistPlayer(
                            player_id=chosen_pid,
                            name=str(p_row.get("name", "")),
                            overall=int(p_row["overall"]) if pd.notna(p_row.get("overall")) else None,
                            position=str(p_row.get("position", "")),
                            target_team=state["target_team"],
                            wage_eur=float(p_row["wage_eur"]) if pd.notna(p_row.get("wage_eur")) else None,
                            value_eur=float(p_row["value_eur"]) if pd.notna(p_row.get("value_eur")) else None,
                            pace=int(p_row["pace"]) if pd.notna(p_row.get("pace")) else None,
                            stamina=int(p_row["stamina"]) if pd.notna(p_row.get("stamina")) else None,
                        )
                        if shortlist.add(sp):
                            added_count += 1
            render_basket.refresh()
            render_results.refresh()
            t_label = PRESET_TARGET_TEAMS.get(state["target_team"], f"Team {state['target_team']}")
            clone_type = "Better-Me" if is_stronger else "Mini-Me"
            ui.notify(f"Added {added_count} {clone_type} players to squad basket (Target: {t_label})", type="positive")
            dialog.close()

        def do_save_matchup_preset():
            dest_name = PRESET_TARGET_TEAMS.get(state['target_team'], 'Ipswich').split(' (')[0]
            prefix = "Better-Me" if is_stronger else "Mini-Me"
            preset_name = f"{shortlist.target_name} vs {dest_name} {prefix} Derby"
            for pid, slot in state["slots"].items():
                chosen_pid = slot["selected_clone_pid"]
                if chosen_pid:
                    p_rows = df[df["player_id"] == chosen_pid]
                    if not p_rows.empty:
                        p_row = p_rows.iloc[0]
                        sp = ShortlistPlayer(
                            player_id=chosen_pid,
                            name=str(p_row.get("name", "")),
                            overall=int(p_row["overall"]) if pd.notna(p_row.get("overall")) else None,
                            position=str(p_row.get("position", "")),
                            target_team=state["target_team"],
                            wage_eur=float(p_row["wage_eur"]) if pd.notna(p_row.get("wage_eur")) else None,
                            value_eur=float(p_row["value_eur"]) if pd.notna(p_row.get("value_eur")) else None,
                            pace=int(p_row["pace"]) if pd.notna(p_row.get("pace")) else None,
                            stamina=int(p_row["stamina"]) if pd.notna(p_row.get("stamina")) else None,
                        )
                        shortlist.add(sp)
            path = save_preset(shortlist, preset_name)
            render_preset_selector.refresh()
            render_basket.refresh()
            render_results.refresh()
            ui.notify(f"Saved matchup preset '{preset_name}' → {path.name}", type="positive")
            dialog.close()

        with ui.row().classes("w-full justify-between items-center mt-2 shrink-0 border-t pt-2"):
            ui.button("Cancel", on_click=dialog.close).props("flat")
            with ui.row().classes("gap-2"):
                ui.button("💾 Save Matchup Preset", on_click=do_save_matchup_preset, icon="save").props("unelevated color=secondary")
                add_title = "⭐ Add Better-Me Clones" if is_stronger else "➕ Add Mini-Me Clones"
                ui.button(add_title, on_click=do_add_to_basket, icon=icon_name).props(f"unelevated color={btn_color} text-white font-bold")

    dialog.open()


def build_ui() -> None:
    global name_in, position_in, club_in, league_in, nation_in, playstyle_in, min_ovr, max_ovr, icons_only_in
    global max_wage, min_playstyles, min_age, max_age, extra_cols_sel, nl_in, provider_sel, model_sel
    global target_team_sel

    ui.page_title("FC 26 Team Builder")
    ui.colors(primary="#FFCD00")  # Leeds gold-ish

    with ui.header().classes("items-center justify-between bg-neutral-900 p-2"):
        ui.label("⚽ FC 26 Custom Team Builder").classes("text-base font-bold text-white")
        ui.label("→ Premier League, Champions League & World Cup National Teams · OFFLINE Kick Off only").classes(
            "text-xs text-white opacity-80"
        )

    with ui.row().classes("w-full no-wrap gap-2 p-2").style("min-height: 85vh"):
        # LEFT: search
        with ui.column().classes("gap-1").style("flex: 2; min-width: 0"):
            ui.label("Search").classes("text-base font-bold")

            with ui.row().classes("w-full gap-1 items-end flex-wrap"):
                name_in = ui.input("Name", placeholder="Salah, Messi…").classes("w-36")
                name_in.on("keydown.enter", lambda: do_search())
                positions = [
                    "Any", "GK", "CB", "LB", "RB", "CDM", "CM", "CAM",
                    "LM", "RM", "LW", "RW", "ST", "CF",
                ]
                position_in = ui.select(
                    positions, value="Any", label="Position"
                ).classes("w-24")
                club_in = ui.input("Club", placeholder="Liverpool, Real…").classes("w-36")
                club_in.on("keydown.enter", lambda: do_search())
                league_in = ui.input("League", placeholder="Premier League…").classes("w-36")
                league_in.on("keydown.enter", lambda: do_search())
                nation_in = ui.input("Nationality", placeholder="England, Spain…").classes("w-32")
                nation_in.on("keydown.enter", lambda: do_search())
                playstyle_in = ui.input(
                    "PlayStyle", placeholder="Finesse, Rapid…"
                ).classes("w-32")
                min_ovr = ui.number("Min OVR", value=None, min=40, max=99).classes("w-20")
                max_ovr = ui.number("Max OVR", value=None, min=40, max=99).classes("w-20")
                min_age = ui.number("Min Age", value=None, min=15, max=45).classes("w-20")
                min_age.on("keydown.enter", lambda: do_search())
                max_age = ui.number("Max Age", value=None, min=15, max=45).classes("w-20")
                max_age.on("keydown.enter", lambda: do_search())
                min_playstyles = ui.number("Min playstyles", value=None, min=0, max=20).classes("w-24")
                max_wage = ui.number("Max wage €", value=None).classes("w-28")
                icons_only_in = ui.checkbox("⭐ Icons Only", value=False).classes("self-center text-xs font-bold text-amber-600 dark:text-amber-400 mb-1")
                icons_only_in.on("change", lambda: do_search())
                extra_cols_sel = ui.select(
                    EXTRA_COL_OPTIONS,
                    multiple=True,
                    label="Extra cols",
                    on_change=lambda: render_results.refresh(),
                ).classes("w-44")
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
                        ["openai/gpt-oss-120b", "qwen/qwen3.6-27b"],
                        value="openai/gpt-oss-120b",
                        label="Model",
                    ).classes("w-44")
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
                with ui.row().classes("w-full gap-2 mt-2 items-center justify-between flex-wrap"):
                    ui.button("Clear", on_click=clear_basket, icon="delete").props(
                        "flat"
                    )
                    ui.button("Draft Mode", on_click=lambda: ui.navigate.to('/draft/setup'), icon="style").props(
                        "flat color=purple"
                    )
                    with ui.row().classes("gap-1 items-center"):
                        ui.button("👥 Mini-Me", on_click=open_mini_me_dialog, icon="group_add").props(
                            "unelevated color=indigo-700 text-white font-bold"
                        ).tooltip("Generate a weaker balanced clone squad (e.g. for Ipswich)")
                        ui.button("⭐ Better-Me", on_click=open_better_me_dialog, icon="auto_awesome").props(
                            "unelevated color=amber-700 text-white font-bold"
                        ).tooltip("Generate an upgraded stronger clone squad (higher OVR)")


def main() -> None:
    global df, results_df, status_msg
    df = load_players()
    results_df = df.head(0)
    status_msg = f"Loaded {len(df)} players — try a search"
    
    @ui.page('/')
    def index():
        build_ui()
        
    init_draft_routes()
    ui.run(
        title="FC 26 Team Builder",
        host="127.0.0.1",
        port=8080,
        reload=False,
        show=True,
    )


if __name__ in {"__main__", "__mp_main__"}:
    main()
