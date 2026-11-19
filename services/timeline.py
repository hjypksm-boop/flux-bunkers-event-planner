"""Plotly swimlane timeline for the Live Diary."""
from __future__ import annotations

from datetime import datetime, timedelta

import plotly.graph_objects as go

from services import clock
from services.ui import MUTED, STATUS_COLOURS, STATUS_ICONS, TEAL, TRAVEL_COLOURS, TRAVEL_STATUS_COLOURS, plotly_layout

PROGRAMME = "Programme"


def _hex_to_rgba(hex_colour: str, alpha: float) -> str:
    h = hex_colour.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


def build_timeline(meetings: list[dict], sessions: list[dict], attendees: list[dict], ev: dict, day: str,
                   london: bool = False, now_local: datetime | None = None, show_cancelled: bool = True,
                   travel_blocks: list[dict] | None = None) -> go.Figure:
    tz = ev["timezone"]

    def conv(dt: datetime) -> datetime:
        return clock.local_to_tz(dt, tz, clock.LONDON) if london else dt

    day_meetings = [m for m in meetings if m["start_at"][:10] == day and (show_cancelled or m["status"] != "cancelled")]
    day_sessions = [s for s in sessions if s["start_at"][:10] == day]
    lanes = [p["role"] for p in attendees]
    lane_of = {p["id"]: p["role"] for p in attendees}
    y_order = [PROGRAMME] + lanes

    fig = go.Figure()

    # --- programme lane: every session as a teal bar
    if day_sessions:
        fig.add_trace(go.Bar(
            orientation="h", y=[PROGRAMME] * len(day_sessions),
            base=[conv(s["start"]) for s in day_sessions],
            x=[(s["end"] - s["start"]).total_seconds() * 1000 for s in day_sessions],
            marker=dict(color=[_hex_to_rgba("#14A3A8", 0.35 if s["kind"] != "break" else 0.15) for s in day_sessions],
                        line=dict(color="#15171C", width=2), cornerradius=4),
            text=[s["title"] + (" (TBC)" if s["tbc"] else "") for s in day_sessions],
            textposition="inside", insidetextanchor="start", textfont=dict(size=11, color="#D9F2F2"),
            hovertemplate="<b>%{text}</b><br>%{customdata[0]}–%{customdata[1]}<br>%{customdata[2]}<extra>Session</extra>",
            customdata=[[f"{conv(s['start']):%H:%M}", f"{conv(s['end']):%H:%M}", s["location"] or ""] for s in day_sessions],
            name="Event session", showlegend=True, legendgroup="session",
        ))

    # --- must-attend sessions inside each person's lane (hatched, so clashes are visible)
    must = [(s, lane_of[p]) for s in day_sessions for p in s["attendees"] if p in lane_of]
    if must:
        fig.add_trace(go.Bar(
            orientation="h", y=[lane for _, lane in must], base=[conv(s["start"]) for s, _ in must],
            x=[(s["end"] - s["start"]).total_seconds() * 1000 for s, _ in must],
            marker=dict(color=_hex_to_rgba("#14A3A8", 0.18), line=dict(color="#14A3A8", width=1),
                        pattern=dict(shape="/", fgcolor=_hex_to_rgba("#14A3A8", 0.55), size=6), cornerradius=4),
            text=[f"★ {s['title']}" for s, _ in must], textposition="inside", insidetextanchor="start",
            textfont=dict(size=10, color="#BFE9E9"),
            hovertemplate="<b>Must attend: %{text}</b><extra></extra>",
            name="Must-attend session", legendgroup="must", showlegend=True,
        ))

    # --- travel: outlined, dotted, translucent blocks drawn *under* meetings (a clash shows as overlap)
    travel_blocks = [b for b in (travel_blocks or []) if b["person_id"] in lane_of]
    names = {"flight": "✈ Flight", "hotel": "🏨 Hotel check-in/out", "transfer": "🚗 Transfer"}
    for kind in ("flight", "transfer", "hotel"):
        rows = [b for b in travel_blocks if b["kind"] == kind]
        if not rows:
            continue
        base_col = TRAVEL_COLOURS[kind]
        alert = {"delayed", "not booked", "cancelled"}
        line_cols = [TRAVEL_STATUS_COLOURS[b["status"]] if b["status"] in alert else base_col for b in rows]
        fig.add_trace(go.Bar(
            orientation="h", y=[lane_of[b["person_id"]] for b in rows], base=[conv(b["start"]) for b in rows],
            x=[max((b["end"] - b["start"]).total_seconds(), 900) * 1000 for b in rows],
            marker=dict(color=_hex_to_rgba(base_col, 0.10), line=dict(color=line_cols, width=2),
                        pattern=dict(shape=".", fgcolor=_hex_to_rgba(base_col, 0.6), size=5, solidity=0.25),
                        cornerradius=8),
            text=[b["label"] + (f" · {b['status'].upper()}" if b["status"] in alert else "") for b in rows],
            textposition="inside", insidetextanchor="start", textfont=dict(size=11, color=base_col), textangle=0,
            customdata=[["travel", f"{conv(b['start']):%H:%M}", f"{conv(b['end']):%H:%M}", b["status"], b["detail"]]
                        for b in rows],
            hovertemplate="<b>%{text}</b><br>%{customdata[1]}–%{customdata[2]} · %{customdata[3]}"
                          "<br>%{customdata[4]}<extra>Travel</extra>",
            name=names[kind], legendgroup=f"travel_{kind}",
        ))

    # --- meetings, one trace per status for a clickable legend
    for status in ["confirmed", "moved", "proposed", "done", "cancelled"]:
        rows = [(m, lane_of[p]) for m in day_meetings if m["status"] == status for p in m["people"] if p in lane_of]
        if not rows:
            continue
        colour = STATUS_COLOURS[status]
        fig.add_trace(go.Bar(
            orientation="h", y=[lane for _, lane in rows], base=[conv(m["start"]) for m, _ in rows],
            x=[(m["end"] - m["start"]).total_seconds() * 1000 for m, _ in rows],
            marker=dict(color=colour if status != "cancelled" else _hex_to_rgba(colour, 0.25),
                        line=dict(color="#15171C" if status != "cancelled" else colour, width=2),
                        pattern=dict(shape="x" if status == "cancelled" else "", fgcolor=colour, size=5),
                        cornerradius=4),
            text=[f"{STATUS_ICONS[status]} {m['account']}" for m, _ in rows],
            textposition="inside", insidetextanchor="start", textfont=dict(size=12, color="#111" if status in ("moved", "done", "confirmed") else "#F2F2F2"),
            customdata=[[m["id"], f"{conv(m['start']):%H:%M}", f"{conv(m['end']):%H:%M}", m["location"] or "—",
                         m["status"], m["objective"] or "—", m["the_ask"] or "—", m["people_roles"]] for m, _ in rows],
            hovertemplate=("<b>%{text}</b><br>%{customdata[1]}–%{customdata[2]} · %{customdata[3]}"
                           "<br>Status: %{customdata[4]} · With: %{customdata[7]}"
                           "<br>Objective: %{customdata[5]}<br><b>Ask:</b> %{customdata[6]}"
                           "<br><i>Click to open brief</i><extra></extra>"),
            name=f"{STATUS_ICONS[status]} {status}", legendgroup=status,
        ))

    # --- x range
    starts = ([conv(m["start"]) for m in day_meetings] + [conv(s["start"]) for s in day_sessions]
              + [conv(b["start"]) for b in travel_blocks])
    ends = ([conv(m["end"]) for m in day_meetings] + [conv(s["end"]) for s in day_sessions]
            + [conv(b["end"]) for b in travel_blocks])
    base_day = datetime.fromisoformat(day)
    if london:
        base_day = clock.local_to_tz(base_day.replace(hour=12), tz, clock.LONDON).replace(hour=0, minute=0)
    lo = min(starts + [base_day.replace(hour=8)]) - timedelta(minutes=30)
    hi = max(ends + [base_day.replace(hour=18)]) + timedelta(minutes=30)

    # --- background bands for sessions across all lanes + lane tints
    for s in day_sessions:
        if s["kind"] == "break":
            continue
        fig.add_vrect(x0=conv(s["start"]), x1=conv(s["end"]), fillcolor=TEAL, opacity=0.10, line_width=0, layer="below")
    category_array = list(reversed(y_order))     # plotly indexes categories bottom-up
    for p in attendees:
        i = category_array.index(p["role"])
        fig.add_hrect(y0=i - 0.5, y1=i + 0.5, fillcolor=p["colour"], opacity=0.05, line_width=0, layer="below")

    if now_local is not None and now_local.date().isoformat() == day:
        nx = conv(now_local)
        fig.add_shape(type="line", x0=nx, x1=nx, y0=0, y1=1, yref="paper", line=dict(color="#E3A008", width=2, dash="dot"))
        fig.add_annotation(x=nx, y=1.0, yref="paper", text=f"Now {nx:%H:%M}", showarrow=False,
                           font=dict(color="#E3A008", size=11), yanchor="bottom", bgcolor="#15171C")

    tick_text = [PROGRAMME] + [f"<span style='color:{p['colour']}'><b>{p['role']}</b></span>" for p in attendees]
    plotly_layout(fig, height=170 + 95 * len(lanes), barmode="overlay", bargap=0.28, clickmode="event+select",
                  dragmode=False)
    fig.update_xaxes(type="date", range=[lo, hi], tickformat="%H:%M", dtick=3600000, side="top",
                     title=None, showgrid=True, fixedrange=False)
    fig.update_yaxes(categoryorder="array", categoryarray=list(reversed(y_order)), tickvals=y_order,
                     ticktext=tick_text, title=None, showgrid=False, fixedrange=True)
    fig.update_layout(legend=dict(orientation="h", y=-0.08, yanchor="top", x=0, font=dict(size=12, color=MUTED)),
                      margin=dict(l=10, r=10, t=50, b=10), uirevision=day)
    return fig
