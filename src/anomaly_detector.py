import pandas as pd


def flag_anomalies(df: pd.DataFrame, z_threshold: float = 3.0) -> pd.DataFrame:
    """Mark rows as anomalous when any key metric exceeds z_threshold standard deviations."""
    df = df.copy()
    cols = ["latency_ms", "total_tokens", "carbon_g_co2", "cost_usd"]
    existing = [c for c in cols if c in df.columns]

    z_scores = df[existing].apply(lambda s: (s - s.mean()) / s.std(ddof=0))
    df["is_anomaly"] = (z_scores.abs() > z_threshold).any(axis=1)
    df["anomaly_reason"] = z_scores[existing].apply(
        lambda row: ", ".join(
            f"{col} z={row[col]:.1f}" for col in existing if abs(row[col]) > z_threshold
        ),
        axis=1,
    )
    return df
