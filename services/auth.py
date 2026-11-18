"""Simple role login. Passwords come from st.secrets first, then environment (.env).

PASSWORD_CEO / PASSWORD_CCO / PASSWORD_SSM / PASSWORD_OPS. If none are configured the demo
defaults below are used and shown on the login screen so assessors can get in.
"""
from __future__ import annotations

import hmac
import os

import streamlit as st

DEMO_DEFAULTS = {"ceo": "flux-ceo", "cco": "flux-cco", "ssm": "flux-ssm", "ops": "flux-ops"}


def get_secret(name: str, default: str | None = None) -> str | None:
    try:
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:  # no secrets.toml — fine
        pass
    return os.environ.get(name, default)


def password_for(key: str) -> tuple[str, bool]:
    """(password, is_demo_default)."""
    configured = get_secret(f"PASSWORD_{key.upper()}")
    return (configured, False) if configured else (DEMO_DEFAULTS[key], True)


def check_password(key: str, attempt: str) -> bool:
    expected, _ = password_for(key)
    return hmac.compare_digest(expected.encode(), (attempt or "").encode())


def using_demo_passwords() -> bool:
    return any(password_for(k)[1] for k in DEMO_DEFAULTS)


def current_user() -> dict | None:
    return st.session_state.get("user")


def is_editor() -> bool:
    u = current_user()
    return bool(u and u.get("can_edit"))


def login(user: dict) -> None:
    st.session_state["user"] = user


def logout() -> None:
    for k in ("user", "brief_meeting_id"):
        st.session_state.pop(k, None)
