"""Snowflake data source for the dashboard with a graceful local fallback.

Authentication uses key-pair (RSA). The private key can be supplied two ways:

  1. As a PEM-encoded string via the `SNOWFLAKE_PRIVATE_KEY` secret/env var
     (used on Streamlit Cloud, where filesystems are ephemeral and secrets
     are stored in `st.secrets` / injected as env vars).
  2. As a path to a `.p8` file via `SNOWFLAKE_PRIVATE_KEY_PATH`
     (used for local development).

If the key is encrypted, also set `SNOWFLAKE_PRIVATE_KEY_PASSPHRASE`.
"""

import os
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

_FALLBACK_PATH = Path(__file__).parent.parent / "data" / "raw" / "logs.json"


def _get_secret(key: str) -> str | None:
    """Resolve `key` from st.secrets first, then environment. Returns None if absent."""
    try:
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        # st.secrets raises when no secrets.toml exists or outside a Streamlit run
        pass
    return os.environ.get(key)


def _resolve_private_key_pem() -> bytes:
    """Return the PEM-encoded private key bytes from secret string or file."""
    inline = _get_secret("SNOWFLAKE_PRIVATE_KEY")
    if inline:
        return inline.encode() if isinstance(inline, str) else inline

    path = _get_secret("SNOWFLAKE_PRIVATE_KEY_PATH")
    if path:
        with open(path, "rb") as f:
            return f.read()

    raise RuntimeError(
        "No Snowflake private key available — set SNOWFLAKE_PRIVATE_KEY "
        "(PEM string) or SNOWFLAKE_PRIVATE_KEY_PATH (file path)."
    )


def _load_private_key_bytes() -> bytes:
    """Load the PKCS#8 private key and return its DER-encoded bytes for the connector."""
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import serialization

    pem = _resolve_private_key_pem()
    passphrase = _get_secret("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE") or None
    password_bytes = passphrase.encode() if passphrase else None

    pk = serialization.load_pem_private_key(
        pem,
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
            account=_get_secret("SNOWFLAKE_ACCOUNT"),
            user=_get_secret("SNOWFLAKE_USER"),
            private_key=_load_private_key_bytes(),
            database=_get_secret("SNOWFLAKE_DATABASE"),
            schema=_get_secret("SNOWFLAKE_SCHEMA"),
            warehouse=_get_secret("SNOWFLAKE_WAREHOUSE"),
            login_timeout=15,
        )
        table = _get_secret("SNOWFLAKE_TABLE") or "AI_API_LOGS"
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
