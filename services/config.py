from __future__ import annotations

import os


def get_config(name: str, default: str = "") -> str:
    """Le configuracoes do ambiente local ou dos Secrets do Streamlit Cloud."""
    value = os.getenv(name)
    if value not in (None, ""):
        return str(value)

    try:
        import streamlit as st

        secret_value = st.secrets.get(name, default)
        return str(secret_value) if secret_value not in (None, "") else default
    except Exception:
        return default
