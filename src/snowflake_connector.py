"""Snowflake data source for the dashboard with a graceful local fallback.

Authentication uses key-pair (RSA) — no password is stored in .env.
Set SNOWFLAKE_PRIVATE_KEY_PATH to a PKCS#8 .p8 file. If the key is encrypted,
also set SNOWFLAKE_PRIVATE_KEY_PASSPHRASE.
"""

import os
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

_FALLBACK_PATH = Path(__file__).parent.parent / "data" / "raw" / "logs.json"


def _load_private_key_bytes() -> bytes:
    """Read PKCS#8 private key from disk and return its DER-encoded bytes."""
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import serialization

    key_path = os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"]
    passphrase = os.environ.get("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE") or None
    password_bytes = passphrase.encode() if passphrase else None

    with open(key_path, "rb") as f:
        pk = serialization.load_pem_private_key(
            f.read(),
            password=password_bytes,
            backend=default_backend(),
        )
    return pk.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


@st.cache_data(ttl=300, show_spinner="Loading session logs from Snowflake…")
def load_from_snowflake() -> pd.DataFrame:
    """Load AI_API_LOGS from Snowflake via key-pair auth, fall back to local JSONL on error."""
    try:
        import snowflake.connector

        conn = snowflake.connector.connect(
            account=os.environ["SNOWFLAKE_ACCOUNT"],
            user=os.environ["SNOWFLAKE_USER"],
            private_key=_load_private_key_bytes(),
            database=os.environ["SNOWFLAKE_DATABASE"],
            schema=os.environ["SNOWFLAKE_SCHEMA"],
            warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
            login_timeout=15,
        )
        table = os.environ.get("SNOWFLAKE_TABLE", "AI_API_LOGS")
        try:
            cur = conn.cursor()
            cur.execute(f"SELECT * FROM {table}")
            df = cur.fetch_pandas_all()
            cur.close()
        finally:
            conn.close()

        # Snowflake returns columns UPPERCASE by default — normalize for downstream code.
        df.columns = [c.lower() for c in df.columns]
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df["total_tokens"] = df["prompt_tokens"] + df["completion_tokens"]
        return df

    except Exception as e:
        st.warning(
            f"Snowflake unavailable ({type(e).__name__}: {e}). "
            f"Falling back to local file: {_FALLBACK_PATH.name}"
        )
        from log_parser import load_logs
        return load_logs(_FALLBACK_PATH)
