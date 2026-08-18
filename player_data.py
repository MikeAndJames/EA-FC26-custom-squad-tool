"""
player_data.py
==============
Load and merge EA FC 26 player reference CSVs.

Primary (attrs / playstyles): data/raw/flynn28_fc26_update2.csv
  (from msmc API / flynn28-style dump — newer stats, no wage/value)

Secondary (wage/value): data/raw/rovnez_sofifa_players.csv
  (SoFIFA-style dump via EAFC26-DataHub — has value_eur, wage_eur)

Join key: player_id. Prefer flynn28 attrs; keep wage/value from old dump.

Usage:
    python player_data.py              # merge + write data/players_merged.csv
    python player_data.py --report     # merge quality only
"""

from __future__ import annotations

import argparse
import os
import unicodedata
from pathlib import Path

import pandas as pd


def strip_accents(s: str) -> str:
    if not s or not isinstance(s, str):
        return ""
    s = (
        s.replace("ø", "o")
        .replace("Ø", "O")
        .replace("ß", "ss")
        .replace("æ", "ae")
        .replace("Æ", "AE")
        .replace("ł", "l")
        .replace("Ł", "L")
        .replace("đ", "d")
        .replace("Đ", "D")
    )
    nfd = unicodedata.normalize("NFD", s)
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
MERGED_CSV = DATA_DIR / "players_merged.csv"
MERGED_JSON = DATA_DIR / "players.json"

NEW_CSV = RAW_DIR / "flynn28_fc26_update2.csv"
OLD_CSV = RAW_DIR / "rovnez_sofifa_players.csv"

# Canonical column names used by explorer / shortlist / NL
RENAME_NEW = {
    "id": "player_id",
    "name": "name",
    "ovr": "overall",
    "pac": "pace",
    "sho": "shooting",
    "pas": "passing",
    "dri": "dribbling",
    "def": "defending",
    "phy": "physical",
    "sprint speed": "sprint_speed",
    "shot power": "shot_power",
    "long shots": "long_shots",
    "free kick accuracy": "fk_accuracy",
    "short passing": "short_passing",
    "long passing": "long_passing",
    "ball control": "ball_control",
    "heading accuracy": "heading_accuracy",
    "def awareness": "def_awareness",
    "standing tackle": "standing_tackle",
    "sliding tackle": "sliding_tackle",
    "preferred foot": "preferred_foot",
    "skill moves": "skill_moves",
    "weak foot": "weak_foot",
    "alternative positions": "alt_positions",
    "play style": "play_styles",
}


def _to_int_id(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").astype("Int64")


def load_new(path: Path = NEW_CSV) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"Missing {path}. See data/README.md — run download or "
            "python player_data.py --download"
        )
    df = pd.read_csv(path, low_memory=False)
    # Big-six pack uses short codes (pac/sho/...). Detailed "dribbling" sub-stat
    # would collide with renaming dri -> dribbling — park the sub-stat first.
    if "dribbling" in df.columns and "dri" in df.columns:
        df = df.rename(columns={"dribbling": "dribbling_detail"})
    df = df.rename(columns={k: v for k, v in RENAME_NEW.items() if k in df.columns})
    if "player_id" not in df.columns and "id" in df.columns:
        df = df.rename(columns={"id": "player_id"})
    # drop duplicate column names if any remain (keep first)
    df = df.loc[:, ~df.columns.duplicated()]
    df["player_id"] = _to_int_id(df["player_id"])
    df = df.dropna(subset=["player_id"]).copy()
    df["player_id"] = df["player_id"].astype(int)
    # numeric stats
    for col in (
        "overall", "pace", "shooting", "passing", "dribbling", "defending",
        "physical", "age", "height", "weight", "acceleration", "sprint_speed",
        "potential", "rank", "skill_moves", "weak_foot",
    ):
        if col in df.columns and isinstance(df[col], pd.Series):
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "play_styles" in df.columns:
        df["play_styles"] = df["play_styles"].fillna("").astype(str)
    return df


def load_old(path: Path = OLD_CSV) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}. See data/README.md")
    df = pd.read_csv(path, low_memory=False)
    if "player_id" not in df.columns:
        raise ValueError(f"{path} has no player_id column")
    df["player_id"] = _to_int_id(df["player_id"])
    df = df.dropna(subset=["player_id"]).copy()
    df["player_id"] = df["player_id"].astype(int)
    keep = ["player_id"]
    for c in ("value_eur", "wage_eur", "potential", "short_name", "long_name"):
        if c in df.columns:
            keep.append(c)
    out = df[keep].drop_duplicates(subset=["player_id"], keep="first")
    for c in ("value_eur", "wage_eur", "potential"):
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")
    return out


def merge_players(new: pd.DataFrame | None = None, old: pd.DataFrame | None = None) -> pd.DataFrame:
    """Left-join flynn28 attrs with wage/value from older SoFIFA dump."""
    if new is None:
        new = load_new()
    if old is None:
        old = load_old()

    # avoid clobbering flynn28 potential if both have it — only take old potential if new lacks it
    old_cols = [c for c in old.columns if c != "player_id"]
    if "potential" in new.columns and "potential" in old.columns:
        old = old.drop(columns=["potential"])
        old_cols = [c for c in old.columns if c != "player_id"]

    merged = new.merge(old, on="player_id", how="left", suffixes=("", "_old"))
    # prefer flynn28 name; keep short_name as alias
    if "name" not in merged.columns and "long_name" in merged.columns:
        merged["name"] = merged["long_name"]
    return merged


def merge_report(merged: pd.DataFrame, new: pd.DataFrame, old: pd.DataFrame) -> str:
    n_new = len(new)
    n_old = len(old)
    has_wage = merged["wage_eur"].notna().sum() if "wage_eur" in merged.columns else 0
    has_value = merged["value_eur"].notna().sum() if "value_eur" in merged.columns else 0
    intersect = len(set(new["player_id"]) & set(old["player_id"]))
    lines = [
        f"new (attrs):     {n_new} players",
        f"old (wage/val):  {n_old} players",
        f"ID intersect:    {intersect} ({100 * intersect / max(n_new, 1):.1f}% of new)",
        f"merged rows:     {len(merged)}",
        f"with wage_eur:   {has_wage} ({100 * has_wage / max(len(merged), 1):.1f}%)",
        f"with value_eur:  {has_value} ({100 * has_value / max(len(merged), 1):.1f}%)",
    ]
    for pid, label in ((158023, "Messi"), (209331, "Salah"), (192505, "Lukaku")):
        row = merged[merged["player_id"] == pid]
        if row.empty:
            lines.append(f"  {label} ({pid}): MISSING")
        else:
            r = row.iloc[0]
            wage = r.get("wage_eur", float("nan"))
            val = r.get("value_eur", float("nan"))
            lines.append(
                f"  {label} ({pid}): OVR={r.get('overall')} "
                f"wage={wage} value={val} team={r.get('team')}"
            )
    return "\n".join(lines)


def save_merged(merged: pd.DataFrame, csv_path: Path = MERGED_CSV, json_path: Path = MERGED_JSON) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    merged.to_csv(csv_path, index=False)
    # compact JSON for tooling: player_id -> useful fields
    cols = [
        c for c in (
            "player_id", "name", "overall", "pace", "shooting", "passing",
            "dribbling", "defending", "physical", "position", "age", "height",
            "nation", "league", "team", "play_styles", "wage_eur", "value_eur",
            "potential", "preferred_foot", "skill_moves", "weak_foot",
        ) if c in merged.columns
    ]
    slim = merged[cols].copy()
    # play_styles as list in JSON
    records = []
    for rec in slim.to_dict(orient="records"):
        ps = rec.get("play_styles") or ""
        if isinstance(ps, str) and ps:
            rec["play_styles"] = [x for x in ps.split("|") if x]
        else:
            rec["play_styles"] = []
        # JSON-friendly NaN
        for k, v in list(rec.items()):
            if v is not None and isinstance(v, float) and pd.isna(v):
                rec[k] = None
        records.append(rec)
    import json
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False)
    print(f"wrote {csv_path} ({csv_path.stat().st_size} bytes)")
    print(f"wrote {json_path} ({json_path.stat().st_size} bytes)")


ICON_NAMES_JSON = DATA_DIR / "icon_names.json"
ICON_POSITIONS = {
    1088: "RM", 1075: "LW", 1397: "CAM", 1380: "CAM", 28130: "LW", 190042: "ST",
    190045: "ST", 190048: "CAM", 237067: "CF", 37576: "GK", 1625: "ST", 54050: "ST",
    488: "RW", 1179: "CAM", 5003: "RB", 1114: "CB", 166906: "CDM", 10535: "LB",
    238380: "GK", 168473: "ST", 156616: "LM", 166691: "ST", 254642: "ST", 238439: "ST",
    230025: "CF", 238382: "ST", 214100: "CM", 7763: "CB", 161840: "CDM", 167680: "CAM",
    5589: "CB", 204963: "ST", 1668: "ST", 182521: "RW", 45661: "ST", 259780: "ST",
    76145: "CM", 253602: "CM", 213311: "CM", 265446: "CM", 223842: "GK", 261970: "ST",
    256184: "CB", 241189: "RB", 232514: "RB", 215356: "CM", 232517: "CF", 254184: "CAM",
    253874: "CM", 254185: "LM", 259944: "CM", 224161: "CB", 225590: "CB", 276044: "CB",
    279075: "CM", 83068: "CDM", 75412: "LM", 71876: "CB", 278788: "ST", 570: "RM",
    1201: "CAM", 27: "ST", 246: "CAM",
}

ICON_SIGNATURE_PLAYSTYLES = {
    1088: "Whipped Pass+|Dead Ball|Incisive Pass|Finesse Shot|Long Ball",
    37576: "Far Reach+|Cross Claim|Deflector|Footwork|Rush Out",
    238380: "Cross Claim+|Far Reach|Deflector|Footwork|Rush Out",
    223842: "Deflector+|Far Reach|Cross Claim|Footwork|Rush Out",
    190042: "Finesse Shot+|Technical|Rapid|First Touch|Gamechanger",
    1397: "Incisive Pass+|Technical|First Touch|Tiki Taka|Finesse Shot",
    28130: "Trickster+|Technical|Finesse Shot|Rapid|First Touch",
    1625: "Rapid+|Finesse Shot|Quick Step|First Touch|Technical",
    214100: "Incisive Pass+|Intercept|Power Shot|Relentless|Aerial",
    1114: "Anticipate+|Intercept|Jockey|Bruiser|Aerial",
    10535: "Power Shot+|Whipped Pass|Rapid|Relentless|Trivela",
    161840: "Intercept+|Bruiser|Press Proven|Relentless|Aerial",
    54050: "Power Shot+|Bruiser|Relentless|First Touch|Finesse Shot",
    76145: "Power Shot+|Long Ball|Incisive Pass|Relentless|Bruiser",
    253602: "Power Shot+|Incisive Pass|First Touch|Relentless|Finesse Shot",
    570: "Relentless+|Whipped Pass|Finesse Shot|Press Proven|Rapid",
    1201: "Power Header+|First Touch|Relentless|Finesse Shot|Jockey",
    276044: "Bruiser+|Anticipate|Intercept|Jockey|Aerial",
    279075: "Power Shot+|Press Proven|Incisive Pass|Relentless|Bruiser",
    83068: "Intercept+|Bruiser|Relentless|Jockey|Press Proven",
    246: "Relentless+|Press Proven|High Energy|Tiki Taka|Intercept",
}


def _get_icon_playstyles(pid: int, name: str, pos: str) -> str:
    if pid in ICON_SIGNATURE_PLAYSTYLES:
        return ICON_SIGNATURE_PLAYSTYLES[pid]
    if pos in ("ST", "CF"):
        return "Power Shot+|Finesse Shot|Rapid|First Touch|Aerial"
    elif pos in ("CAM", "CM"):
        return "Incisive Pass+|Tiki Taka|First Touch|Technical|Relentless"
    elif pos in ("CB", "SW"):
        return "Anticipate+|Bruiser|Intercept|Aerial|Block"
    elif pos in ("RB", "LB", "RWB", "LWB"):
        return "Whipped Pass+|Relentless|Rapid|Intercept|Anticipate"
    elif pos in ("CDM", "RDM", "LDM"):
        return "Intercept+|Bruiser|Relentless|Anticipate|Tiki Taka"
    elif pos in ("LW", "RW", "LM", "RM"):
        return "Trickster+|Technical|Rapid|Quick Step|Finesse Shot"
    elif pos == "GK":
        return "Cross Claim+|Far Reach|Deflector|Footwork|Rush Out"
    return "Relentless+|Technical|First Touch"


def load_icon_players() -> pd.DataFrame:
    import json
    from icon_database import build_icon_database, ICON_DB_JSON

    records = []
    if ICON_DB_JSON.exists():
        try:
            with open(ICON_DB_JSON, encoding="utf-8") as f:
                raw_records = json.load(f)
        except Exception:
            raw_records = build_icon_database()
    else:
        raw_records = build_icon_database()

    for r in raw_records:
        pid = r["player_id"]
        name = r["name"]
        ovr = r["overall"]
        pos = r["position"]
        cat = r.get("category", "Prime Icon / Hero")
        team = r.get("team_names", ["Icons Pool"])[0] if r.get("team_names") else "Icons Pool"
        ps = _get_icon_playstyles(pid, name, pos)

        alt_pos = r.get("alt_positions", "")

        records.append({
            "player_id": pid,
            "name": name,
            "overall": ovr,
            "position": pos,
            "alt_positions": alt_pos,
            "team": team,
            "league": "Legends",
            "nation": "Legend",
            "gender": "M",
            "is_icon": True,
            "pace": r.get("pace") or (88 if pos in ("ST", "LW", "RW", "RM", "LM", "RB", "LB") else 80),
            "shooting": r.get("shooting") or (ovr - 5 if pos in ("ST", "LW", "RW", "CAM") else 60),
            "passing": r.get("passing") or (ovr - 2 if pos in ("CM", "CAM", "RM", "LM") else 75),
            "dribbling": r.get("dribbling") or (ovr - 2 if pos in ("LW", "RW", "CAM", "ST") else 75),
            "defending": r.get("defending") or (ovr if pos in ("CB", "LB", "RB", "CDM") else 45),
            "physical": r.get("physical") or (ovr - 5),
            "stamina": 85,
            "acceleration": r.get("acceleration") or r.get("pace") or 85,
            "agility": r.get("agility") or 82,
            "short_passing": r.get("short_passing") or r.get("passing") or 80,
            "long_passing": r.get("long_passing") or r.get("passing") or 78,
            "standing_tackle": r.get("standing_tackle") or r.get("defending") or 50,
            "sliding_tackle": r.get("sliding_tackle") or r.get("defending") or 45,
            "def_awareness": r.get("def_awareness") or r.get("defending") or 50,
            "vision": r.get("vision") or r.get("passing") or 80,
            "strength": r.get("strength") or r.get("physical") or 75,
            "play_styles": ps,
        })

    df_icons = (
        pd.DataFrame(records)
        .sort_values("overall", ascending=False)
        .drop_duplicates(subset=["name"], keep="first")
    )
    return df_icons


def load_players(path: Path | None = None) -> pd.DataFrame:
    """Load merged CSV if present, else merge from raw on the fly, plus local Icons."""
    path = path or MERGED_CSV
    if path.exists():
        df = pd.read_csv(path, low_memory=False)
        df["player_id"] = _to_int_id(df["player_id"]).astype(int)
    else:
        df = merge_players()
        save_merged(df)

    icons_df = load_icon_players()
    if not icons_df.empty:
        icons_df = icons_df[~icons_df["player_id"].isin(df["player_id"])]
        df = pd.concat([df, icons_df], ignore_index=True)

    df["is_icon"] = df["team"].astype(str).str.contains("Icons|Soccer Aid|Heroes", case=False, na=False) | df["league"].astype(str).str.contains("Legends", case=False, na=False)

    if "name" in df.columns and "name_norm" not in df.columns:
        df["name_norm"] = df["name"].astype(str).apply(strip_accents).str.lower()
    if "short_name" in df.columns and "short_name_norm" not in df.columns:
        df["short_name_norm"] = df["short_name"].astype(str).apply(strip_accents).str.lower()
    if "team" in df.columns and "team_norm" not in df.columns:
        df["team_norm"] = df["team"].astype(str).apply(strip_accents).str.lower()
    if "league" in df.columns and "league_norm" not in df.columns:
        df["league_norm"] = df["league"].astype(str).apply(strip_accents).str.lower()
    if "nation" in df.columns and "nation_norm" not in df.columns:
        df["nation_norm"] = df["nation"].astype(str).apply(strip_accents).str.lower()
    return df


def search_by_name(df: pd.DataFrame, query: str, limit: int = 50) -> pd.DataFrame:
    if not query or not str(query).strip():
        return df.head(0)
    q = strip_accents(str(query).strip()).lower()
    if "name_norm" in df.columns:
        mask = df["name_norm"].astype(str).str.contains(q, na=False)
    else:
        mask = df["name"].astype(str).apply(strip_accents).str.lower().str.contains(q, na=False)

    if "short_name_norm" in df.columns:
        mask = mask | df["short_name_norm"].astype(str).str.contains(q, na=False)
    elif "short_name" in df.columns:
        mask = mask | df["short_name"].astype(str).apply(strip_accents).str.lower().str.contains(q, na=False)

    out = df.loc[mask]
    if "overall" in out.columns:
        out = out.sort_values("overall", ascending=False)
    return out.head(limit)


def search_by_team(df: pd.DataFrame, query: str, limit: int = 50) -> pd.DataFrame:
    if not query or not str(query).strip():
        return df.head(0)
    q = strip_accents(str(query).strip()).lower()
    if "team_norm" in df.columns:
        mask = df["team_norm"].astype(str).str.contains(q, na=False)
    else:
        mask = df["team"].astype(str).apply(strip_accents).str.lower().str.contains(q, na=False)
    out = df.loc[mask]
    if "overall" in out.columns:
        out = out.sort_values("overall", ascending=False)
    return out.head(limit)


def search_by_league(df: pd.DataFrame, query: str, limit: int = 50) -> pd.DataFrame:
    if not query or not str(query).strip():
        return df.head(0)
    q = strip_accents(str(query).strip()).lower()
    if "league_norm" in df.columns:
        mask = df["league_norm"].astype(str).str.contains(q, na=False)
    else:
        mask = df["league"].astype(str).apply(strip_accents).str.lower().str.contains(q, na=False)
    out = df.loc[mask]
    if "overall" in out.columns:
        out = out.sort_values("overall", ascending=False)
    return out.head(limit)


def search_by_nation(df: pd.DataFrame, query: str, limit: int = 50) -> pd.DataFrame:
    if not query or not str(query).strip():
        return df.head(0)
    q = strip_accents(str(query).strip()).lower()
    if "nation_norm" in df.columns:
        mask = df["nation_norm"].astype(str).str.contains(q, na=False)
    else:
        mask = df["nation"].astype(str).apply(strip_accents).str.lower().str.contains(q, na=False)
    out = df.loc[mask]
    if "overall" in out.columns:
        out = out.sort_values("overall", ascending=False)
    return out.head(limit)


def filter_players(
    df: pd.DataFrame,
    *,
    name: str | None = None,
    position: str | None = None,
    club: str | None = None,
    team: str | None = None,
    league: str | None = None,
    nationality: str | None = None,
    nation: str | None = None,
    icons_only: bool = False,
    min_ovr: int | None = None,
    max_ovr: int | None = None,
    min_pace: int | None = None,
    max_pace: int | None = None,
    playstyle: str | None = None,
    min_playstyles: int | None = None,
    max_wage: float | None = None,
    max_value: float | None = None,
    min_height: int | None = None,
    max_height: int | None = None,
    min_age: int | None = None,
    max_age: int | None = None,
    gender: str | None = "M",
    limit: int = 100,
) -> pd.DataFrame:
    out = df
    if gender and "gender" in out.columns:
        out = out[out["gender"].astype(str).str.upper().str.startswith(gender.upper())]
    if icons_only:
        mask_icon = (
            (out["is_icon"].fillna(False).astype(bool))
            if "is_icon" in out.columns
            else False
        ) | out["team"].astype(str).str.contains("Icons|Soccer Aid|Heroes", case=False, na=False) | out["league"].astype(str).str.contains("Legends", case=False, na=False)
        out = out[mask_icon]
    if name:
        out = search_by_name(out, name, limit=10_000)

    club_q = (club or team or "").strip()
    if club_q and "team" in out.columns:
        cq = strip_accents(club_q).lower()
        if "team_norm" in out.columns:
            out = out[out["team_norm"].astype(str).str.contains(cq, na=False)]
        else:
            out = out[out["team"].astype(str).apply(strip_accents).str.lower().str.contains(cq, na=False)]

    league_q = (league or "").strip()
    if league_q and "league" in out.columns:
        lq = strip_accents(league_q).lower()
        if "league_norm" in out.columns:
            out = out[out["league_norm"].astype(str).str.contains(lq, na=False)]
        else:
            out = out[out["league"].astype(str).apply(strip_accents).str.lower().str.contains(lq, na=False)]

    nation_q = (nationality or nation or "").strip()
    if nation_q and "nation" in out.columns:
        nq = strip_accents(nation_q).lower()
        if "nation_norm" in out.columns:
            out = out[out["nation_norm"].astype(str).str.contains(nq, na=False)]
        else:
            out = out[out["nation"].astype(str).apply(strip_accents).str.lower().str.contains(nq, na=False)]

    if position and "position" in out.columns:
        p = position.strip().upper()
        pos = out["position"].astype(str).str.upper()
        alt = out["alt_positions"].astype(str).str.upper() if "alt_positions" in out.columns else ""
        out = out[pos.str.contains(p, na=False) | (alt.str.contains(p, na=False) if len(alt) else False)]
    if min_ovr is not None and "overall" in out.columns:
        out = out[out["overall"] >= min_ovr]
    if max_ovr is not None and "overall" in out.columns:
        out = out[out["overall"] <= max_ovr]
    if min_pace is not None and "pace" in out.columns:
        out = out[out["pace"] >= min_pace]
    if max_pace is not None and "pace" in out.columns:
        out = out[out["pace"] <= max_pace]
    if playstyle and "play_styles" in out.columns:
        ps = playstyle.strip().lower()
        out = out[out["play_styles"].astype(str).str.lower().str.contains(ps, na=False)]
    if min_playstyles is not None and "play_styles" in out.columns:
        out = out[
            out["play_styles"].astype(str).apply(lambda x: len([p for p in x.split("|") if p and p.lower() != "nan"])) >= min_playstyles
        ]
    if max_wage is not None and "wage_eur" in out.columns:
        out = out[out["wage_eur"].notna() & (out["wage_eur"] <= max_wage)]
    if max_value is not None and "value_eur" in out.columns:
        out = out[out["value_eur"].notna() & (out["value_eur"] <= max_value)]
    if min_height is not None and "height" in out.columns:
        out = out[out["height"] >= min_height]
    if max_height is not None and "height" in out.columns:
        out = out[out["height"] <= max_height]
    if min_age is not None and "age" in out.columns:
        out = out[out["age"].notna() & (out["age"] >= min_age)]
    if max_age is not None and "age" in out.columns:
        out = out[out["age"].notna() & (out["age"] <= max_age)]
    if "overall" in out.columns:
        out = out.sort_values("overall", ascending=False)
    return out.head(limit)


def download_raw() -> None:
    """Fetch both raw sources (stdlib urllib)."""
    import csv
    import json
    import urllib.request

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    api_url = "https://api.msmc.cc/api/eafc/players?game=fc26&update=2"
    print(f"Downloading {api_url} ...")
    req = urllib.request.Request(api_url, headers={"User-Agent": "ea-fc26-tool/1.0"})
    with urllib.request.urlopen(req, timeout=180) as r:
        players = json.loads(r.read())
    json_path = RAW_DIR / "flynn28_fc26_update2.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(players, f)
    keys: list[str] = []
    seen: set[str] = set()
    for p in players:
        for k in p:
            if k not in seen:
                seen.add(k)
                keys.append(k)
    with open(NEW_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        for p in players:
            row = dict(p)
            if isinstance(row.get("play style"), list):
                row["play style"] = "|".join(row["play style"])
            w.writerow(row)
    print(f"  wrote {NEW_CSV} ({len(players)} players)")

    so_url = (
        "https://raw.githubusercontent.com/ismailoksuz/EAFC26-DataHub/"
        "main/data/players.csv"
    )
    print(f"Downloading {so_url} ...")
    req2 = urllib.request.Request(so_url, headers={"User-Agent": "ea-fc26-tool/1.0"})
    with urllib.request.urlopen(req2, timeout=180) as r:
        OLD_CSV.write_bytes(r.read())
    print(f"  wrote {OLD_CSV}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Merge FC 26 player CSVs")
    ap.add_argument("--download", action="store_true", help="re-download raw sources")
    ap.add_argument("--report", action="store_true", help="print merge quality only")
    args = ap.parse_args()
    if args.download:
        download_raw()
    new = load_new()
    old = load_old()
    merged = merge_players(new, old)
    print(merge_report(merged, new, old))
    if not args.report:
        save_merged(merged)


if __name__ == "__main__":
    main()
