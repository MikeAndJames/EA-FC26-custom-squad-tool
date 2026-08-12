"""
nl_query.py
===========
Natural language → pandas filter for the player DataFrame.

Pattern lifted from footballmanager/groq.py (idea only): the model returns
executable Python that filters `df`; we run it in a restricted namespace.

Providers: Groq (primary), optional Gemini if GOOGLE_API_KEY / GEMINI_API_KEY set.

Environment variables:
    GROQ_API_KEY    Groq API key.
    GROQ_MODEL      Groq model id to use (default: qwen/qwen3.6-27b).
                      The previous default, llama-3.3-70b-versatile, was deprecated.
    GEMINI_API_KEY  Google Gemini API key (fallback provider).

Usage (library):
    code, err = ask_nl("tall slow CBs under wage 20000", df, api_key=...)
    result_df, err = run_filter_code(code, df)
"""

from __future__ import annotations

import os
import re
from typing import Any

import pandas as pd

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore


FORBIDDEN = re.compile(
    r"\b(import|open|exec|eval|compile|__|os\.|sys\.|subprocess|pathlib|"
    r"shutil|socket|requests|urllib|write|remove|unlink|rmtree)\b",
    re.I,
)

# Groq deprecated this model; the error hint uses it to detect stale configs.
_DEPRECATED_GROQ_MODEL = "llama-3.3-70b-versatile"


def _columns_blurb(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    # keep prompt small
    priority = [
        "player_id", "name", "overall", "pace", "shooting", "passing",
        "dribbling", "defending", "physical", "position", "alt_positions",
        "age", "height", "weight", "nation", "league", "team",
        "play_styles", "wage_eur", "value_eur", "preferred_foot",
        "skill_moves", "weak_foot", "gender",
    ]
    shown = [c for c in priority if c in cols]
    rest = [c for c in cols if c not in shown][:30]
    return f"Priority columns: {shown}\nOther columns: {rest}"


def _data_preview(df: pd.DataFrame) -> str:
    """Compact schema + sample row for the LLM (kept small for tokens)."""
    key_cols = [
        "player_id", "name", "overall", "position", "alt_positions",
        "age", "height", "weight", "nation", "league", "team",
        "play_styles", "wage_eur", "value_eur", "preferred_foot",
        "skill_moves", "weak_foot", "gender",
    ]
    sample_cols = [c for c in key_cols if c in df.columns]
    sample = df[sample_cols].head(1).to_dict(orient="records")
    sample_str = str(sample[0]) if sample else "(no rows)"
    return f"""Columns ({len(df.columns)} total): {list(df.columns)}
Key columns sample row: {sample_str}"""


def build_system_prompt(df: pd.DataFrame) -> str:
    return f"""You are a pandas code generator for an EA FC 26 player dataset.
The DataFrame `df` is already loaded in scope. Generate ONLY valid, executable
Python code that filters/sorts `df` based on the user's natural language query.
Assign the final DataFrame to a variable named `result`. Do NOT include
markdown code fences or explanations.

{_data_preview(df)}

Key columns and units:
- Identity (strings): `name`, `name_norm` (accent-free lowercased name for matching e.g. "munoz" or "nunez"), `short_name`, `team`, `league`, `nation`
- Core stats (0-99): `overall`, `pace`, `shooting`, `passing`, `dribbling`, `defending`, `physical`
- Physical: `age` (years), `height` (cm), `weight` (kg)
- Roles (strings): `position` (e.g. "ST", "CM"), `alt_positions`
- Traits: `play_styles` (pipe-separated string, e.g. "Rapid|Finesse Shot+")
- Market: `wage_eur`, `value_eur` (numeric EUR; missing values are NaN)
- Gender: `gender` is "M" or "F"

Rules:
- Return ONLY executable Python code, no markdown fences, no explanation.
- Filter/sort `df` into a variable named `result` (a DataFrame).
- Use only pandas (`pd` is available) and `df`.
- Do NOT import anything. Do NOT read/write files. Do NOT call network APIs.
- Default to men's players unless the query explicitly asks for women:
  `df = df[df['gender'] == 'M']`.
- For player name matching, prefer `name_norm` or `name` (case-insensitive, na=False):
  `df['name_norm'].str.contains('...', case=False, na=False)` or `df['name'].str.contains('...', case=False, na=False)`.
- `play_styles` is pipe-separated; use case-insensitive contains for styles.
- For wage/value comparisons, drop NaNs first: `df['wage_eur'].notna()`.
- Map vague adjectives to safe numeric thresholds:
  - tall -> height >= 190, short -> height <= 170
  - fast -> pace >= 85, slow -> pace <= 60
  - young -> age <= 21, old -> age >= 32
  - cheap -> value_eur <= 1000000
- Superlatives use `.sort_values(..., ascending=...).head(...)`:
  - tallest -> sort height descending
  - youngest -> sort age ascending
  - fastest -> sort pace descending
  - best -> sort overall descending
- Limit result to at most 80 rows: `result = result.head(80)`.
- Optionally set `display_cols` to a list of column names from `result` that the UI should show.
  If omitted, the UI shows its default columns: position, name, overall, play_styles.
  Example:
  ```
  result = df[df['position'] == 'ST'].sort_values('overall', ascending=False).head(20)
  display_cols = ['position', 'name', 'overall', 'pace', 'vision', 'stamina', 'play_styles']
  ```
  Keep `display_cols` to at most 10 columns.
- Always assign `result` at the end.
"""


def strip_code_fences(code: str) -> str:
    code = code.strip()
    code = re.sub(r"^```(?:python)?\s*", "", code)
    code = re.sub(r"\s*```$", "", code)
    return code.strip()


def is_safe_code(code: str) -> tuple[bool, str]:
    if FORBIDDEN.search(code):
        return False, "code rejected: forbidden token (imports/files/network)"
    if "result" not in code:
        return False, "code must assign a `result` DataFrame"
    return True, ""


def ask_groq(
    question: str,
    df: pd.DataFrame,
    api_key: str,
    model: str | None = None,
    history: list[dict[str, str]] | None = None,
) -> tuple[str | None, str | None]:
    if not api_key:
        return None, "No Groq API key (set GROQ_API_KEY or pass key)"
    if requests is None:
        return None, "requests package not installed"
    # Groq deprecated llama-3.3-70b-versatile. Recommended free-tier
    # replacements: openai/gpt-oss-120b or qwen/qwen3.6-27b.
    model = model or os.environ.get("GROQ_MODEL") or "qwen/qwen3.6-27b"
    messages: list[dict[str, str]] = [
        {"role": "system", "content": build_system_prompt(df)},
    ]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": question})
    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": messages,
                "temperature": 0.1,
                "max_tokens": 1200,
            },
            timeout=45,
        )
        data = r.json()
        if "error" in data:
            msg = str(data["error"].get("message", data["error"]))
            err_code = str(data["error"].get("code", "")).lower()
            is_model_err = (
                "deprecated" in msg.lower()
                or "model" in err_code
                or err_code == "not_found"
                or _DEPRECATED_GROQ_MODEL in msg
            )
            if is_model_err:
                msg += (
                    "\nTip: set GROQ_MODEL to a current model id "
                    "(e.g. qwen/qwen3.6-27b or openai/gpt-oss-120b)."
                )
            return None, f"Groq API: {msg}"
        code = data["choices"][0]["message"]["content"]
        return strip_code_fences(code), None
    except Exception as e:
        return None, str(e)


def ask_gemini(
    question: str,
    df: pd.DataFrame,
    api_key: str,
    model: str = "gemini-2.0-flash",
    history: list[dict[str, str]] | None = None,
) -> tuple[str | None, str | None]:
    if not api_key:
        return None, "No Gemini API key"
    if requests is None:
        return None, "requests package not installed"
    # Gemini uses a single text prompt, so flatten history into the prompt.
    parts: list[str] = [build_system_prompt(df)]
    if history:
        for h in history:
            role = h.get("role", "user")
            content = h.get("content", "")
            parts.append(f"{role.upper()}: {content}")
    parts.append(f"USER: {question}")
    prompt = "\n\n".join(parts)
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    try:
        r = requests.post(
            url,
            headers={"Content-Type": "application/json"},
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=45,
        )
        data = r.json()
        if "error" in data:
            return None, f"Gemini API: {data['error'].get('message', data['error'])}"
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        return strip_code_fences(text), None
    except Exception as e:
        return None, str(e)


def ask_nl(
    question: str,
    df: pd.DataFrame,
    *,
    provider: str = "groq",
    api_key: str | None = None,
    model: str | None = None,
    history: list[dict[str, str]] | None = None,
) -> tuple[str | None, str | None]:
    provider = (provider or "groq").lower()
    if provider == "gemini":
        key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""
        return ask_gemini(question, df, key, model or "gemini-2.0-flash", history=history)
    key = api_key or os.environ.get("GROQ_API_KEY") or ""
    # Default model is resolved inside ask_groq so GROQ_MODEL env var is honoured.
    return ask_groq(question, df, key, model, history=history)


def run_filter_code(
    code: str, df: pd.DataFrame
) -> tuple[pd.DataFrame | None, list[str] | None, str | None]:
    ok, reason = is_safe_code(code)
    if not ok:
        return None, None, reason
    globs: dict[str, Any] = {"df": df.copy(), "pd": pd}
    locs: dict[str, Any] = {}
    try:
        exec(code, globs, locs)  # noqa: S102 — intentional, sandboxed-ish
        result = locs.get("result", globs.get("result"))
        if result is None:
            return None, None, "code ran but did not set `result`"
        if not isinstance(result, pd.DataFrame):
            return None, None, f"`result` is {type(result).__name__}, expected DataFrame"

        raw_cols = locs.get("display_cols") or globs.get("display_cols")
        display_cols: list[str] | None = None
        if raw_cols is not None:
            if isinstance(raw_cols, str):
                raw_cols = [raw_cols]
            display_cols = [str(c) for c in raw_cols if c in result.columns][:10]
        return result.head(80), display_cols, None
    except Exception as e:
        return None, None, f"execution error: {e}"


def _summarize_result(result: pd.DataFrame) -> str:
    """Compact summary of a result DataFrame for conversation history."""
    n = len(result)
    if n == 0:
        return "Result: 0 rows."
    names = ", ".join(result["name"].head(3).astype(str).tolist()) if "name" in result.columns else ""
    return f"Result: {n} rows. Top: {names}." if names else f"Result: {n} rows."


def run_nl_query(
    question: str,
    df: pd.DataFrame,
    *,
    provider: str = "groq",
    api_key: str | None = None,
    model: str | None = None,
    history: list[dict[str, str]] | None = None,
    max_retries: int = 1,
) -> tuple[pd.DataFrame | None, str | None, str | None, list[dict[str, str]], list[str] | None]:
    """
    Run a natural-language query with optional history and one reflection retry.

    Returns:
        (result_df, code, error, new_history_entries, display_cols)
    """
    history = history or []
    code, err = ask_nl(
        question, df, provider=provider, api_key=api_key, model=model, history=history
    )
    if err:
        return None, None, err, [], None

    result, display_cols, exec_err = run_filter_code(code, df)
    if exec_err and max_retries > 0:
        retry_question = (
            f"Your previous code failed with this error:\n{exec_err}\n"
            f"Please rewrite the code to fix it. Return ONLY valid Python code "
            f"assigning the final DataFrame to `result`."
        )
        retry_history = history + [
            {"role": "assistant", "content": code},
            {"role": "system", "content": f"Execution failed: {exec_err}"},
        ]
        code, err = ask_nl(
            retry_question, df, provider=provider, api_key=api_key, model=model, history=retry_history
        )
        if err:
            return None, None, err, [], None
        result, display_cols, exec_err = run_filter_code(code, df)

    if exec_err:
        return None, code, exec_err, [], None

    new_entries = [
        {"role": "user", "content": question},
        {"role": "assistant", "content": code},
    ]
    if result is not None:
        new_entries.append({"role": "system", "content": _summarize_result(result)})
    return result, code, None, new_entries, display_cols
