import pandas as pd
import gridstatus

# kWh per 1000 tokens — rough empirical estimates by model family.
# Keys are substrings matched against lowercased model_id; the longest
# matching key wins, so "gpt-4o-mini" beats "gpt-4o" beats "gpt-4".
_ENERGY_PER_1K_TOKENS = {
    # OpenAI
    "gpt-4o-mini": 0.0008,
    "gpt-4o": 0.0020,
    "gpt-4-turbo": 0.0030,
    "gpt-4": 0.0035,
    "gpt-3.5-turbo-16k": 0.0010,
    "gpt-3.5": 0.0008,
    "o1-preview": 0.0080,
    "o1-mini": 0.0030,
    "o3-mini": 0.0025,
    # Anthropic
    "claude-3-5-sonnet": 0.0018,
    "claude-3-5-haiku": 0.0007,
    "claude-3-opus": 0.0030,
    "claude-3-sonnet": 0.0015,
    "claude-3-haiku": 0.0005,
    "claude-sonnet-4": 0.0020,
    "claude-haiku-4": 0.0006,
    # Google
    "gemini-1.5-pro": 0.0025,
    "gemini-1.5-flash": 0.0008,
    "gemini-2.0-flash": 0.0007,
    "gemini-ultra": 0.0035,
    # Mistral
    "mistral-large": 0.0025,
    "mistral-medium": 0.0015,
    "mistral-small": 0.0008,
    "mixtral-8x7b": 0.0018,
    # Meta
    "llama-3.1-405b": 0.0050,
    "llama-3.1-70b": 0.0020,
    "llama-3-70b": 0.0020,
    "llama-3-8b": 0.0006,
    "llama-2-70b": 0.0022,
    # Cohere
    "cohere-command-r-plus": 0.0025,
    "cohere-command-r": 0.0015,
    "cohere-command": 0.0015,
    # Others
    "falcon-180b": 0.0045,
    "falcon-40b": 0.0018,
    "phi-3-medium": 0.0010,
    "phi-3-mini": 0.0004,
    "qwen-72b": 0.0022,
    "qwen-7b": 0.0005,
    "deepseek-v2": 0.0020,
    "deepseek-coder": 0.0018,
    "yi-34b": 0.0014,
    "solar-10.7b": 0.0008,
    "vicuna-33b": 0.0014,
    "default": 0.0020,
}

# kg CO2 per kWh by fuel type (lifecycle median estimates)
_FUEL_INTENSITY_KG_PER_KWH = {
    "Coal": 0.820,
    "Natural Gas": 0.490,
    "Nuclear": 0.012,
    "Solar": 0.020,
    "Wind": 0.011,
    "Battery Storage": 0.0,
    "Imports": 0.386,
    "Other": 0.300,
}

_FUEL_COLS = list(_FUEL_INTENSITY_KG_PER_KWH.keys())


def get_miso_fuel_mix() -> tuple[pd.DataFrame, float]:
    """Return (fuel_mix_df, grid_intensity_kg_per_kwh) from live MISO data."""
    try:
        miso = gridstatus.MISO()
        raw = miso.get_fuel_mix("latest")

        fuel_cols = [c for c in _FUEL_COLS if c in raw.columns]
        clean = raw.copy()
        clean[fuel_cols] = clean[fuel_cols].fillna(0).astype("float64")

        mw_series = clean.iloc[0][fuel_cols].astype("float64").clip(lower=0)
        total_mw = float(mw_series.sum())

        fuel_df = pd.DataFrame({
            "Fuel": mw_series.index,
            "MW": mw_series.values,
            "Pct": (mw_series.values / total_mw * 100).round(2) if total_mw > 0 else 0.0,
        })

        if total_mw > 0:
            intensity = float(sum(
                (mw / total_mw) * _FUEL_INTENSITY_KG_PER_KWH.get(fuel, 0.3)
                for fuel, mw in zip(mw_series.index, mw_series.values)
            ))
        else:
            intensity = 0.386

        return fuel_df, intensity

    except Exception:
        fallback = pd.DataFrame([
            {"Fuel": f, "MW": 0.0, "Pct": 0.0} for f in _FUEL_COLS
        ])
        return fallback, 0.386


def _energy_per_token(model_id: str) -> float:
    """Longest-substring-prefix match → kWh per single token."""
    m = model_id.lower()
    best_rate = _ENERGY_PER_1K_TOKENS["default"]
    best_len = 0
    for prefix, rate in _ENERGY_PER_1K_TOKENS.items():
        if prefix == "default":
            continue
        if prefix in m and len(prefix) > best_len:
            best_rate = rate
            best_len = len(prefix)
    return best_rate / 1000


def add_carbon_columns(df: pd.DataFrame, grid_intensity_kg_per_kwh: float) -> pd.DataFrame:
    """Add energy_kwh and carbon_g_co2 — vectorized for large datasets."""
    df = df.copy()
    rate_map = {m: _energy_per_token(m) for m in df["model_id"].unique()}
    df["energy_kwh"] = df["total_tokens"] * df["model_id"].map(rate_map)
    df["carbon_g_co2"] = df["energy_kwh"] * grid_intensity_kg_per_kwh * 1000
    return df
