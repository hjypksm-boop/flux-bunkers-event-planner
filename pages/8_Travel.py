"""Travel — readiness, red flags first, per-person flights / hotel / transfers / documents, budget, itinerary."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from services import auth, export, llm, travel, ui

user = auth.current_user()
ev = ui.current_event()
ui.demo_banner(ev)
ui.header("Travel", f"{ev['name']} · flights, hotels, transfers and document checks for the leadership team")

london = ui.tz_toggle("travel_tz")
tz_label = "London" if london else f"{ev['city']} local"
trips = travel.trips(ev["id"])
if not trips:
    st.info("No travel recorded for this event yet.")
    st.stop()

flags = travel.red_flags(ev["id"], ev)
budget = {b["person_id"]: b for b in travel.budget_rows(ev["id"])}

# ----------------------------------------------------------------------------- readiness tiles
cols = st.columns(len(trips) + 1)
for col, tr in zip(cols, trips):
    ready, total = travel.readiness(ev["id"], tr["person_id"])
    pct = round(100 * ready / total) if total else 0
    n_err = sum(1 for f in flags if f["person_id"] == tr["person_id"] and f["severity"] == "error")
    colour = "#4CAF7A" if pct == 100 and not n_err else ("#F97316" if pct >= 75 else "#E5534B")
    state = "ready" if pct == 100 and not n_err else (f"{n_err} issue{'s' if n_err != 1 else ''}" if n_err
                                                      else "items outstanding")
    col.markdown(
        f"<div class='fb-kpi'><div class='lbl'>{ui.esc(tr['role'])} readiness</div>"
        f"<div class='val'>{pct}%</div><div class='fb-bar'><span style='width:{pct}%;background:{colour}'></span></div>"
        f"<div class='sub'>{ready}/{total} booked, confirmed or done · {ui.esc(state)}</div></div>",
        unsafe_allow_html=True)
tot_b = sum(b["budget_gbp"] for b in budget.values())
tot_a = sum(b["actual_gbp"] for b in budget.values())
cols[-1].markdown(
    f"<div class='fb-kpi'><div class='lbl'>Event travel cost</div><div class='val'>£{tot_a:,.0f}</div>"
    f"<div class='sub'>of £{tot_b:,.0f} budget · "
    f"{'over' if tot_a > tot_b else 'under'} by £{abs(tot_a - tot_b):,.0f}</div></div>", unsafe_allow_html=True)

# ----------------------------------------------------------------------------- red flags first
st.markdown("### 🚩 Red flags")
if not flags:
    st.success("No travel issues for this event.")
else:
    with st.container(border=True):
        for f in flags:
            icon = "🔴" if f["severity"] == "error" else "🟠"
            st.markdown(f"{icon} **{ui.esc(f['role'])}** · <span class='fb-small'>{ui.esc(f['kind'])}</span> — "
                        f"{ui.esc(f['message'])}", unsafe_allow_html=True)
    if auth.is_editor():
        st.caption("Fix these in **Ops Console → Travel**. Delayed flights there show the meetings to move or reassign.")

# ----------------------------------------------------------------------------- per person
st.markdown("### Itineraries")
st.caption(f"Times in {tz_label} (switch above). Booking references are visible only to the traveller and London Ops.")
all_flights, all_hotels = travel.flights(ev["id"], ev), travel.hotels(ev["id"], ev)
all_transfers, all_docs = travel.transfers(ev["id"], ev), travel.docs(ev["id"])
default_tab = next((i for i, t in enumerate(trips) if t["person_id"] == user["id"]), 0)
tabs = st.tabs([f"{t['role']}" for t in trips], default=f"{trips[default_tab]['role']}")


def t_show(dt, src_tz=None) -> str:
    return ui.show_time(dt, ev, london, "%a %d %b %H:%M", from_tz=src_tz)


for tab, tr in zip(tabs, trips):
    pid = tr["person_id"]
    see = travel.can_see_ref(user, pid)
    with tab:
        b = budget.get(pid)
        st.markdown(
            f"{ui.person_dot(tr['colour'], tr['role'] + ' · ' + tr['person_name'])} {ui.travel_pill(tr['status'])} "
            f"<span class='fb-small'>· {tr['outbound_date']} → {tr['return_date']}"
            + (f" · £{b['actual_gbp']:,.0f} of £{b['budget_gbp']:,.0f}" if b else "") + "</span>",
            unsafe_allow_html=True)
        if tr["notes"]:
            st.caption(tr["notes"])

        st.markdown("**✈ Flights**")
        fl = [f for f in all_flights if f["person_id"] == pid]
        st.dataframe(pd.DataFrame([{
            "Direction": f["direction"], "Flight": f"{f['airline']} {f['flight_no']}",
            "From": f"{f['dep_airport']} {f['dep_terminal'] or ''}".strip(),
            "Departs": t_show(f["dep_ev"]),
            "To": f"{f['arr_airport']} {f['arr_terminal'] or ''}".strip(),
            "Arrives": t_show(f["arr_ev"]),
            "Airport-local": f"{f['dep_eff']:%H:%M} → {f['arr_eff']:%H:%M}",
            "Status": f["status"] + (f" (+{f['delay_minutes']} min)" if f["delay_minutes"] else ""),
            "Seat": f["seat"] or "—", "Booking ref": travel.mask(f["booking_ref"], see), "Cost £": f["cost_gbp"],
        } for f in fl]), hide_index=True, width="stretch")

        st.markdown("**🏨 Hotel**")
        for h in [h for h in all_hotels if h["person_id"] == pid]:
            link = travel.map_link(h["address"])
            venue = (f"{h['distance_km']} km · {h['travel_min_to_venue']} min to venue" if h["travel_min_to_venue"]
                     else "Venue TBC: travel time to be confirmed")
            st.markdown(
                f"<div class='fb-card'><h4>{ui.esc(h['name'])} {ui.travel_pill(h['status'])}</h4>"
                f"<div class='fb-meta'>📍 {ui.esc(h['address'])}"
                + (f" · <a href='{link}' target='_blank'>map</a>" if link else "") +
                f"<br>Check-in {t_show(h['check_in_ev'])} · check-out {t_show(h['check_out_ev'])}"
                f"<br>{ui.esc(venue)} · ☎ {ui.esc(h['phone'] or '—')} · ref {ui.esc(travel.mask(h['booking_ref'], see))}"
                f" · £{h['cost_gbp']:,.0f}</div></div>", unsafe_allow_html=True)

        st.markdown("**🚗 Transfers**")
        st.dataframe(pd.DataFrame([{
            "Type": t["type"], "Pickup": t_show(t["start_ev"]), "From": t["pickup_place"], "To": t["dropoff_place"],
            "Est.": f"{t['est_minutes']} min", "Provider": t["provider"] or "—", "Driver": t["driver_contact"] or "—",
            "Status": t["status"], "Booking ref": travel.mask(t["booking_ref"], see), "Cost £": t["cost_gbp"],
        } for t in all_transfers if t["person_id"] == pid]), hide_index=True, width="stretch")

        st.markdown("**🛂 Document checklist** <span class='fb-small'>(status only: no document numbers are stored)</span>",
                    unsafe_allow_html=True)
        st.markdown(" &nbsp; ".join(f"{ui.esc(d['item'])} {ui.travel_pill(d['status'])}"
                                    for d in all_docs if d["person_id"] == pid) or "—", unsafe_allow_html=True)

        person = {"id": pid, "role": tr["role"], "name": tr["person_name"], "key": tr["person_key"],
                  "colour": tr["colour"]}
        st.markdown("")
        c1, c2, c3 = st.columns(3)
        it = export.itinerary(ev, person, user)
        fname = f"itinerary_{tr['person_key']}_{ev['code']}"
        c1.download_button("⬇️ Itinerary (HTML)", export.build_itinerary_html(person, ev, it),
                           file_name=f"{fname}.html", mime="text/html", width="stretch", key=f"ith_{pid}")
        c2.download_button("⬇️ Itinerary (PDF)", export.build_itinerary_pdf(person, ev, it),
                           file_name=f"{fname}.pdf", mime="application/pdf", width="stretch", key=f"itp_{pid}")
        skey = f"travel_summary_{ev['id']}_{pid}"
        if c3.button("🤖 Travel summary", width="stretch", key=f"ts_{pid}", type="primary"):
            with st.spinner("Writing the briefing from the database…"):
                st.session_state[skey] = llm.travel_summary(travel.summary_fields(ev, person))
        res = st.session_state.get(skey)
        if res:
            with st.container(border=True):
                st.markdown(res.content["markdown"])
                gen = "Groq · " + res.generator.split(":", 1)[1] if res.generator.startswith("groq:") else "Template"
                st.caption(f"{gen}{' · ' + res.note if res.note else ''} · built only from database fields: "
                           f"{', '.join(res.sources) or '—'}. Booking references are never sent to the AI.")
                for u in res.unverified:
                    st.warning(u)

# ----------------------------------------------------------------------------- budget panel
st.markdown("### 💷 Budget")
rows = list(budget.values())
fig = go.Figure()
fig.add_trace(go.Bar(
    orientation="h", y=[r["role"] for r in rows], x=[r["actual_gbp"] for r in rows], name="Actual",
    marker=dict(color=["#F97316" if r["over"] else "#0E6E73" for r in rows], cornerradius=4),
    text=[f"£{r['actual_gbp']:,.0f}" + (f" · over by £{r['variance_gbp']:,.0f}" if r["over"] else "") for r in rows],
    textposition="inside", insidetextanchor="start", textfont=dict(color="#F2F2F2"),
    hovertemplate="%{y}: £%{x:,.0f}<extra>Actual</extra>"))
fig.add_trace(go.Scatter(
    y=[r["role"] for r in rows], x=[r["budget_gbp"] for r in rows], mode="markers", name="Budget",
    marker=dict(symbol="line-ns", size=26, line=dict(width=3, color="#E3A008")),
    hovertemplate="%{y}: budget £%{x:,.0f}<extra></extra>"))
ui.plotly_layout(fig, height=90 + 55 * len(rows), barmode="overlay")
fig.update_xaxes(tickprefix="£", separatethousands=True, title=None)
fig.update_yaxes(autorange="reversed", title=None)
st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

all_rows = travel.budget_rows()
by_event = (pd.DataFrame(all_rows).groupby("event_name", sort=False)
            .agg(Budget=("budget_gbp", "sum"), Actual=("actual_gbp", "sum")).reset_index()
            .rename(columns={"event_name": "Event"}))
by_event["Variance"] = by_event["Actual"] - by_event["Budget"]
by_event["% used"] = (by_event["Actual"] / by_event["Budget"] * 100).round(0)
c1, c2 = st.columns(2)
c1.markdown("**Per event**")
c1.dataframe(by_event, hide_index=True, width="stretch",
             column_config={k: st.column_config.NumberColumn(format="£%.0f") for k in ("Budget", "Actual", "Variance")})
c2.markdown("**Per person, all events**")
per_person = (pd.DataFrame(all_rows).groupby("role", sort=False)
              .agg(Budget=("budget_gbp", "sum"), Actual=("actual_gbp", "sum")).reset_index()
              .rename(columns={"role": "Person"}))
per_person["Variance"] = per_person["Actual"] - per_person["Budget"]
c2.dataframe(per_person, hide_index=True, width="stretch",
             column_config={k: st.column_config.NumberColumn(format="£%.0f") for k in ("Budget", "Actual", "Variance")})
st.caption("Actual = sum of flight (excluding cancelled), hotel and transfer costs, in GBP.")
