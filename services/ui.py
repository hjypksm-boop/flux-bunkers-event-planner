"""Shared look & feel: palette, CSS, banner, chips, small helpers used by every page."""
from __future__ import annotations

import html
from datetime import datetime

import streamlit as st

from services import clock

CHARCOAL = "#15171C"
SURFACE = "#1F232B"
SURFACE_2 = "#272C35"
AMBER = "#E3A008"
TEAL = "#0E6E73"
TEXT = "#E8E6E3"
MUTED = "#9AA0A8"

# Status colours always ship with a text label / icon (never colour alone).
STATUS_COLOURS = {
    "proposed": "#8A8F98",
    "confirmed": "#4C9BE8",
    "moved": "#F97316",
    "cancelled": "#E5534B",
    "done": "#4CAF7A",
}
STATUS_ICONS = {"proposed": "◌", "confirmed": "●", "moved": "↻", "cancelled": "✕", "done": "✓"}
RAG = {"off track": ("#E5534B", "🔴"), "at risk": ("#F97316", "🟠"), "on track": ("#4CAF7A", "🟢"),
       "not started": ("#8A8F98", "⚪")}
# Travel: outlined/hatched blocks so they never read as meetings.
TRAVEL_COLOURS = {"flight": "#C9A3FF", "hotel": "#7FB7BE", "transfer": "#D4B483"}
TRAVEL_STATUS_COLOURS = {"booked": "#4C9BE8", "confirmed": "#4CAF7A", "checked in": "#4CAF7A", "landed": "#4CAF7A",
                         "delayed": "#F97316", "cancelled": "#E5534B", "not booked": "#E5534B",
                         "planned": "#8A8F98", "travelling": "#E3A008", "done": "#4CAF7A",
                         "pending": "#F97316", "not needed": "#8A8F98"}
TZ_MODES = ["Event local", "London"]
FOLLOWUP_COLOURS = {"draft": "#8A8F98", "approved": "#4C9BE8", "sent": "#4CAF7A"}

CSS = f"""
<style>
:root {{ --amber:{AMBER}; --teal:{TEAL}; --surface:{SURFACE}; --surface2:{SURFACE_2}; --muted:{MUTED}; }}
.block-container {{ padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1400px; }}
h1, h2, h3, h4 {{ letter-spacing: -0.01em; }}
h1 {{ font-weight: 700; }}
[data-testid="stSidebar"] {{ border-right: 1px solid #2A2F38; }}
.fb-banner {{ display:flex; gap:.75rem; align-items:center; flex-wrap:wrap;
  background: linear-gradient(90deg, rgba(227,160,8,.14), rgba(14,110,115,.14));
  border:1px solid rgba(227,160,8,.35); border-radius:10px; padding:.45rem .8rem; margin-bottom: .9rem;
  font-size:.85rem; color:{TEXT}; }}
.fb-banner b {{ color:{AMBER}; }}
.fb-pill {{ display:inline-block; padding:.08rem .5rem; border-radius:999px; font-size:.75rem; font-weight:600;
  border:1px solid currentColor; line-height:1.4; white-space:nowrap; }}
.fb-card {{ background:{SURFACE}; border:1px solid #2A2F38; border-radius:12px; padding:.9rem 1rem; margin-bottom:.7rem; }}
.fb-card.accent {{ border-left:4px solid var(--amber); }}
.fb-card h4 {{ margin:.1rem 0 .35rem 0; font-size:1.05rem; }}
.fb-meta {{ color:{MUTED}; font-size:.85rem; }}
.fb-ask {{ background: rgba(227,160,8,.10); border-left:3px solid {AMBER}; padding:.4rem .6rem; border-radius:6px;
  margin-top:.45rem; font-size:.92rem; }}
.fb-kpi {{ background:{SURFACE}; border:1px solid #2A2F38; border-radius:12px; padding:.8rem 1rem; height:100%; }}
.fb-kpi .lbl {{ color:{MUTED}; font-size:.8rem; text-transform:uppercase; letter-spacing:.04em; }}
.fb-kpi .val {{ font-size:1.9rem; font-weight:700; line-height:1.15; margin:.15rem 0; }}
.fb-kpi .sub {{ color:{MUTED}; font-size:.8rem; }}
.fb-bar {{ height:6px; background:#2A2F38; border-radius:4px; overflow:hidden; margin:.35rem 0 .3rem; }}
.fb-bar > span {{ display:block; height:100%; border-radius:4px; }}
.fb-change {{ font-size:.88rem; padding:.15rem 0; }}
.fb-small {{ font-size:.8rem; color:{MUTED}; }}
.fb-lane {{ display:inline-flex; align-items:center; gap:.35rem; margin-right:1rem; font-size:.85rem; }}
.fb-dot {{ width:.7rem; height:.7rem; border-radius:50%; display:inline-block; }}
@media (max-width: 640px) {{
  .block-container {{ padding-left: .8rem; padding-right: .8rem; padding-top: 1.2rem; }}
  .fb-card {{ padding:.75rem .8rem; }}
  .fb-kpi .val {{ font-size:1.5rem; }}
  h1 {{ font-size: 1.6rem; }}
}}
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def esc(x) -> str:
    return html.escape("" if x is None else str(x))


def pill(text: str, colour: str) -> str:
    return f'<span class="fb-pill" style="color:{colour}">{esc(text)}</span>'


def status_pill(status: str) -> str:
    return pill(f"{STATUS_ICONS.get(status, '')} {status}", STATUS_COLOURS.get(status, MUTED))


def person_dot(colour: str, label: str) -> str:
    return f'<span class="fb-lane"><span class="fb-dot" style="background:{colour}"></span>{esc(label)}</span>'


def demo_banner(ev: dict | None) -> None:
    clock_txt = ""
    if ev:
        if clock.demo_enabled():
            now_local = clock.now_in(ev["timezone"])
            clock_txt = f" · Demo clock: <b>{now_local:%a %d %b %Y %H:%M}</b> {esc(ev['city'])} time"
        else:
            clock_txt = " · Real clock"
    st.markdown(f'<div class="fb-banner">🧪 <b>Demo data – fictitious.</b> All companies, people and figures are '
                f'invented for demonstration.{clock_txt}</div>', unsafe_allow_html=True)


def header(title: str, subtitle: str | None = None) -> None:
    st.markdown(f"# {title}")
    if subtitle:
        st.caption(subtitle)


def current_event() -> dict:
    from services import data
    evs = {e["id"]: e for e in data.events()}
    eid = st.session_state.get("event_id")
    return evs.get(eid) or next(iter(evs.values()))


def fmt_time(dt: datetime, ev: dict, london: bool = False) -> str:
    if london:
        return f"{clock.local_to_tz(dt, ev['timezone'], clock.LONDON):%H:%M}"
    return f"{dt:%H:%M}"


def tz_toggle(key: str) -> bool:
    """Event-local / London switch shared across pages (remembers the last choice). Returns True for London."""
    current = st.session_state.get("tz_mode", TZ_MODES[0])
    val = st.segmented_control("Times shown in", TZ_MODES, default=current, key=key) or current
    st.session_state["tz_mode"] = val
    return val == "London"


def show_time(dt: datetime, ev: dict, london: bool, fmt: str = "%H:%M", from_tz: str | None = None) -> str:
    """Format a naive local time (in `from_tz`, default the event zone) in event-local or London time."""
    src = from_tz or ev["timezone"]
    target = clock.LONDON if london else ev["timezone"]
    return f"{clock.local_to_tz(dt, src, target) if src != target else dt:{fmt}}"


def travel_pill(status: str) -> str:
    return pill(status, TRAVEL_STATUS_COLOURS.get(status, MUTED))


def open_brief(meeting_id: int) -> None:
    st.session_state["brief_meeting_id"] = int(meeting_id)
    st.switch_page("pages/3_Meeting_Brief.py")


def ago(iso: str) -> str:
    from datetime import timezone
    then = datetime.fromisoformat(iso)
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    secs = (datetime.now(timezone.utc) - then).total_seconds()
    if secs < 90:
        return "just now"
    if secs < 3600:
        return f"{int(secs // 60)} min ago"
    if secs < 86400:
        return f"{int(secs // 3600)} h ago"
    return f"{int(secs // 86400)} d ago"


def plotly_layout(fig, height: int = 360, **kw):
    fig.update_layout(
        template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=TEXT, size=13), height=height, margin=dict(l=10, r=10, t=40, b=10),
        hoverlabel=dict(bgcolor=SURFACE_2, font_color=TEXT, bordercolor="#3A404B"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, title=None), **kw)
    fig.update_xaxes(gridcolor="#2A2F38", zerolinecolor="#2A2F38", linecolor="#3A404B")
    fig.update_yaxes(gridcolor="#2A2F38", zerolinecolor="#2A2F38", linecolor="#3A404B")
    return fig
