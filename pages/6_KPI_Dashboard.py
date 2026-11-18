"""KPI Dashboard — progress vs target, RAG status, and a weekly summary that leads with what's off track."""
from __future__ import annotations

from collections import Counter

import plotly.graph_objects as go
import streamlit as st

from services import clock, data, kpis, ui

ev = ui.current_event()
ui.demo_banner(ev)
ui.header("KPI Dashboard", f"{ev['name']} — targets vs actuals")

meetings = data.meetings(ev["id"])
deb = data.debriefs(ev["id"])
fus = data.follow_ups(ev["id"])
tgt = data.targets(ev["id"])
now_local = clock.now_in(ev["timezone"])
res = kpis.compute(meetings, deb.to_dict("records") if not deb.empty else [], fus, tgt, now_local, ev["timezone"])

# ----------------------------------------------------------------------------- KPI tiles
order = sorted(res["metrics"], key=lambda m: kpis.RAG_ORDER[m.status])
cols = st.columns(3)
for i, m in enumerate(order):
    colour, icon = ui.RAG[m.status]
    if m.key == "cancellations":
        val, tgt_txt, pct = f"{m.actual:.0f}%", f"limit {m.target:.0f}%", min(100, m.actual / max(m.target, 1) * 100)
    elif m.unit == "%":
        val, tgt_txt, pct = f"{m.actual:.0f}%", f"target {m.target:.0f}%", min(100, m.pct_of_target)
    else:
        val, tgt_txt, pct = f"{m.actual:.0f}", f"of {m.target:.0f}", min(100, m.pct_of_target)
    with cols[i % 3]:
        st.markdown(
            f"<div class='fb-kpi'><div class='lbl'>{ui.esc(m.label)}</div>"
            f"<div class='val'>{val} <span class='fb-small'>{tgt_txt}</span></div>"
            f"<div class='fb-bar'><span style='width:{pct:.0f}%;background:{colour}'></span></div>"
            f"{ui.pill(f'{icon} {m.status}', colour)}<div class='sub' style='margin-top:.35rem'>{ui.esc(m.detail)}</div></div>",
            unsafe_allow_html=True)
        st.write("")

# ----------------------------------------------------------------------------- charts
c1, c2 = st.columns(2)
with c1:
    tm = res["tier_mix"]
    fig = go.Figure(go.Bar(
        x=[data.TIER_LABEL[t] for t in (1, 2, 3)], y=[tm[t] for t in (1, 2, 3)],
        marker=dict(color=ui.AMBER, cornerradius=4), text=[tm[t] for t in (1, 2, 3)], textposition="outside",
        hovertemplate="%{x}: %{y} booked meetings<extra></extra>"))
    ui.plotly_layout(fig, height=320, title=dict(text="Tier mix of booked meetings", font=dict(size=15)),
                     showlegend=False, bargap=0.45)
    fig.update_yaxes(title=None, rangemode="tozero")
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
with c2:
    sm = res["status_mix"]
    statuses = [s for s in data.STATUS_ORDER if sm.get(s)]
    fig = go.Figure(go.Bar(
        y=[f"{ui.STATUS_ICONS[s]} {s}" for s in statuses], x=[sm[s] for s in statuses], orientation="h",
        marker=dict(color=[ui.STATUS_COLOURS[s] for s in statuses], cornerradius=4),
        text=[sm[s] for s in statuses], textposition="outside",
        hovertemplate="%{y}: %{x} meetings<extra></extra>"))
    ui.plotly_layout(fig, height=320, title=dict(text="Meetings by status", font=dict(size=15)), showlegend=False,
                     bargap=0.4)
    fig.update_yaxes(autorange="reversed", title=None)
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

# meetings per person per day (attendee colours, legend + direct value labels)
attendees = data.people(attendees_only=True)
days = data.event_days(ev)
per = Counter((p, m["start_at"][:10]) for m in meetings if m["status"] != "cancelled" for p in m["people"])
fig = go.Figure()
for p in attendees:
    ys = [per.get((p["id"], d), 0) for d in days]
    fig.add_trace(go.Bar(name=p["role"], x=[f"{d[5:]}" for d in days], y=ys, marker=dict(color=p["colour"], cornerradius=4,
                         line=dict(color=ui.CHARCOAL, width=2)), text=ys, textposition="outside",
                         hovertemplate=f"{p['role']} · %{{x}}: %{{y}} meetings<extra></extra>"))
ui.plotly_layout(fig, height=320, title=dict(text="Active meetings per person per day", font=dict(size=15)),
                 barmode="group", bargap=0.3, bargroupgap=0.08)
fig.update_layout(legend=dict(y=1.0, yanchor="bottom", x=1, xanchor="right"))
st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

# ----------------------------------------------------------------------------- weekly summary
st.markdown("## Weekly summary")
summary = kpis.weekly_summary(ev["name"], res, f"{now_local:%a %d %b %Y %H:%M} {ev['city']} time")
with st.container(border=True):
    st.markdown(summary)
st.download_button("⬇️ Download summary (Markdown)", summary, file_name=f"weekly-summary_{ev['code']}.md",
                   mime="text/markdown")
with st.expander("Data table"):
    st.dataframe([{"Metric": m.label, "Actual": m.actual, "Target": m.target, "Status": m.status, "Detail": m.detail}
                  for m in order], hide_index=True, width="stretch")
