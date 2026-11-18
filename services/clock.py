"""Demo-aware clock.

IBIA 2026 hasn't happened yet, so by default the app runs on a *demo clock* frozen at
Wed 2 Dec 2026 15:30 New York time (mid-convention). Set DEMO_CLOCK=off in .env, or untick
the sidebar toggle, to use the real clock. DEMO_NOW overrides the instant (ISO, with offset).
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

DEFAULT_DEMO_NOW = "2026-12-02T15:30:00-05:00"
LONDON = "Europe/London"


def _session_flag() -> bool | None:
    try:
        import streamlit as st
        return st.session_state.get("use_demo_clock")
    except Exception:  # outside a Streamlit run
        return None


def demo_enabled() -> bool:
    flag = _session_flag()
    if flag is not None:
        return bool(flag)
    return os.environ.get("DEMO_CLOCK", "on").lower() not in ("off", "0", "false", "no")


def demo_instant() -> datetime:
    return datetime.fromisoformat(os.environ.get("DEMO_NOW", DEFAULT_DEMO_NOW)).astimezone(timezone.utc)


def now_utc() -> datetime:
    return demo_instant() if demo_enabled() else datetime.now(timezone.utc)


def now_in(tz: str) -> datetime:
    """Current time in `tz` as a naive datetime (matches how meeting times are stored)."""
    return now_utc().astimezone(ZoneInfo(tz)).replace(tzinfo=None)


def real_utc_iso() -> str:
    """Real wall-clock time for audit records (change_log is always truthful)."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def business_utc_iso() -> str:
    """Timestamp for business events (sent/approved/debriefed) — follows the demo clock."""
    return now_utc().replace(microsecond=0).isoformat()


def local_to_tz(naive_local: datetime, from_tz: str, to_tz: str) -> datetime:
    return naive_local.replace(tzinfo=ZoneInfo(from_tz)).astimezone(ZoneInfo(to_tz)).replace(tzinfo=None)


def utc_iso_to_local(iso: str, tz: str) -> datetime:
    dt = datetime.fromisoformat(iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ZoneInfo(tz)).replace(tzinfo=None)
