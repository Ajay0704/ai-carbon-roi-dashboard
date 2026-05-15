import pandas as pd

# Per-1M-token pricing → (prompt_rate_usd, completion_rate_usd)
# Real 2024 published rates for the 5 anchor models; everything else uses default.
_PRICING = {
    "gpt-4o":                       (2.50, 10.00),
    "claude-3-5-sonnet-20241022":   (3.00, 15.00),
    "gemini-1.5-pro":               (1.25,  5.00),
    "llama-3-70b":                  (0.59,  0.79),
    "mistral-large":                (2.00,  6.00),
}
_DEFAULT_PRICING = (0.50, 1.50)


def _pricing(model_id: str) -> tuple[float, float]:
    return _PRICING.get(model_id, _DEFAULT_PRICING)


def add_roi_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add cost_usd, roi_score_per_dollar, tokens_per_ms.

    Cost is computed per-token with split prompt/completion rates, vectorized
    via per-unique-model rate maps so it stays fast on large dataframes.
    """
    df = df.copy()
    unique_models = df["model_id"].unique()
    prompt_rate = {m: _pricing(m)[0] for m in unique_models}
    completion_rate = {m: _pricing(m)[1] for m in unique_models}

    df["cost_usd"] = (
        df["prompt_tokens"] * df["model_id"].map(prompt_rate) / 1_000_000
        + df["completion_tokens"] * df["model_id"].map(completion_rate) / 1_000_000
    )
    df["roi_score_per_dollar"] = df["user_feedback_score"] / df["cost_usd"].clip(lower=1e-9)
    df["tokens_per_ms"] = df["total_tokens"] / df["latency_ms"].clip(lower=1)
    return df
