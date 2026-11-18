"""IBIA → FUJCON Learnings — conversion by tier, objections, and recommendations for the FUJCON list."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from db.database import query, scalar
from services import data, llm, ui

ev = ui.current_event()
ui.demo_banner(ev)
ui.header("IBIA → FUJCON Learnings", "What New York taught us, and who to prioritise in Fujairah. "
                                     "Always based on IBIA debriefs, whichever event is selected.")

ibia_id = scalar("SELECT id FROM events WHERE code='IBIA2026'")
fuj_id = scalar("SELECT id FROM events WHERE code='FUJCON2027'")
deb = data.debriefs(ibia_id)
if deb.empty:
    st.info("No IBIA debriefs yet — learnings appear once meetings are debriefed.")
    st.stop()

# ----------------------------------------------------------------------------- stats
conv = (deb.groupby("tier").agg(held=("id", "count"), signups=("app_signup", "sum"), trials=("trial_started", "sum"),
                                dm=("decision_maker_present", "sum"),
                                high=("interest_level", lambda s: (s == "high").sum()))
        .reindex([1, 2, 3], fill_value=0).reset_index())
conv["signup_rate"] = (conv["signups"] / conv["held"].where(conv["held"] > 0) * 100).fillna(0)
conv["trial_rate"] = (conv["trials"] / conv["held"].where(conv["held"] > 0) * 100).fillna(0)
objections = llm.objection_counts(deb["objections"].fillna("").tolist())

with_dm = deb[deb["decision_maker_present"] == 1]
without_dm = deb[deb["decision_maker_present"] == 0]
dm_effect = {"with": with_dm["app_signup"].mean() * 100 if len(with_dm) else 0,
             "without": without_dm["app_signup"].mean() * 100 if len(without_dm) else 0}

k1, k2, k3, k4 = st.columns(4)
k1.metric("IBIA meetings debriefed", len(deb))
k2.metric("Sign-up rate", f"{deb['app_signup'].mean() * 100:.0f}%")
k3.metric("Trial rate", f"{deb['trial_started'].mean() * 100:.0f}%")
k4.metric("Sign-ups: DM present vs not", f"{dm_effect['with']:.0f}% vs {dm_effect['without']:.0f}%")

c1, c2 = st.columns(2)
with c1:
    tiers = [data.TIER_LABEL[t].split(" · ")[0] for t in conv["tier"]]
    fig = go.Figure()
    fig.add_trace(go.Bar(name="Sign-up rate", x=tiers, y=conv["signup_rate"], marker=dict(color=ui.AMBER, cornerradius=4,
                         line=dict(color=ui.CHARCOAL, width=2)),
                         text=[f"{v:.0f}%" for v in conv["signup_rate"]], textposition="outside",
                         customdata=conv[["signups", "held"]].values,
                         hovertemplate="%{x} sign-ups: %{customdata[0]} of %{customdata[1]} (%{y:.0f}%)<extra></extra>"))
    fig.add_trace(go.Bar(name="Trial rate", x=tiers, y=conv["trial_rate"], marker=dict(color="#14A3A8", cornerradius=4,
                         line=dict(color=ui.CHARCOAL, width=2)),
                         text=[f"{v:.0f}%" for v in conv["trial_rate"]], textposition="outside",
                         customdata=conv[["trials", "held"]].values,
                         hovertemplate="%{x} trials: %{customdata[0]} of %{customdata[1]} (%{y:.0f}%)<extra></extra>"))
    ui.plotly_layout(fig, height=340, title=dict(text="Conversion by tier", font=dict(size=15)), barmode="group",
                     bargap=0.35, bargroupgap=0.08)
    fig.update_layout(legend=dict(y=1.0, yanchor="bottom", x=1, xanchor="right"))
    fig.update_yaxes(ticksuffix="%", range=[0, 115])
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
with c2:
    if objections:
        names = [o for o, _ in objections][::-1]
        counts = [n for _, n in objections][::-1]
        fig = go.Figure(go.Bar(y=names, x=counts, orientation="h", marker=dict(color=ui.AMBER, cornerradius=4),
                               text=counts, textposition="outside", hovertemplate="%{y}: %{x} meetings<extra></extra>"))
        ui.plotly_layout(fig, height=340, title=dict(text="Most common objections", font=dict(size=15)),
                         showlegend=False, bargap=0.35)
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    else:
        st.caption("No objections recorded.")

with st.expander("Conversion table"):
    st.dataframe(conv.assign(tier=[data.TIER_LABEL[t] for t in conv["tier"]]).rename(columns={
        "tier": "Tier", "held": "Held", "signups": "Sign-ups", "trials": "Trials", "dm": "DM present",
        "high": "High interest", "signup_rate": "Sign-up %", "trial_rate": "Trial %"}).round(0),
        hide_index=True, width="stretch")

# ----------------------------------------------------------------------------- FUJCON target list
st.markdown("## FUJCON target list")
cands = query("""
    SELECT a.id, a.name, a.tier, a.type, a.region, a.ports, a.health_status,
           EXISTS(SELECT 1 FROM meetings m WHERE m.account_id=a.id AND m.event_id=? AND m.status!='cancelled') AS booked,
           (SELECT d.interest_level FROM debriefs d JOIN meetings m ON m.id=d.meeting_id
              WHERE m.account_id=a.id AND m.event_id=? ORDER BY d.id DESC LIMIT 1) AS ibia_interest,
           (SELECT d.objections FROM debriefs d JOIN meetings m ON m.id=d.meeting_id
              WHERE m.account_id=a.id AND m.event_id=? ORDER BY d.id DESC LIMIT 1) AS ibia_objections
    FROM accounts a
    WHERE a.region='Middle East Gulf' OR a.ports LIKE '%Fujairah%'
""", [fuj_id, ibia_id, ibia_id])
best_tier = int(conv.sort_values("signup_rate", ascending=False).iloc[0]["tier"])
for c in cands:
    score = {1: 30, 2: 20, 3: 10}[c["tier"]] + (15 if c["tier"] == best_tier else 0)
    score += {"high": 20, "medium": 10, "low": -5}.get(c["ibia_interest"] or "", 0)
    score += 5 if c["region"] == "Middle East Gulf" else 0
    c["score"] = score
cands.sort(key=lambda c: (-c["score"], c["name"]))
st.dataframe(pd.DataFrame([{
    "Score": c["score"], "Account": c["name"], "Tier": c["tier"], "Type": c["type"], "Ports": c["ports"],
    "IBIA interest": c["ibia_interest"] or "—", "IBIA objections": c["ibia_objections"] or "—",
    "Booked at FUJCON": "✓" if c["booked"] else "—"} for c in cands]), hide_index=True, width="stretch")
st.caption("Score = tier weight + bonus for the best-converting IBIA tier + IBIA interest + Gulf-based. "
           "A simple, transparent heuristic — adjust in pages/7_Learnings.py.")

# ----------------------------------------------------------------------------- AI summary
st.markdown("## Summary & recommendations")
stats = {
    "conversion_by_tier": conv[["tier", "held", "signups", "trials", "signup_rate", "trial_rate"]].round(1).to_dict("records"),
    "top_objections": objections,
    "dm_effect": dm_effect,
    "candidates": [{"name": c["name"], "tier": c["tier"], "ibia_interest": c["ibia_interest"]}
                   for c in cands if not c["booked"]],
}
debrief_lines = deb[["account", "tier", "interest_level", "objections", "decision_maker_present", "app_signup",
                     "trial_started", "next_step", "what_happened"]].to_dict("records")
b1, b2 = st.columns([1, 3])
if b1.button("✨ Generate summary", type="primary", width="stretch") or "learn_md" not in st.session_state:
    with st.spinner("Summarising IBIA debriefs…"):
        r = llm.learnings_summary(stats, debrief_lines)
    st.session_state["learn_md"] = (r.content["markdown"], r.generator, r.note)
md, gen, note = st.session_state["learn_md"]
b2.caption(f"Source: {len(deb)} IBIA debriefs + the stats above · {gen}" + (f" · {note}" if note else ""))
with st.container(border=True):
    st.markdown(md)
