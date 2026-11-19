"""My Day — a mobile-friendly running order for one person, with offline HTML/PDF download."""
from __future__ import annotations

from datetime import datetime

import streamlit as st

from services import auth, clock, data, export, travel, ui

user = auth.current_user()
ev = ui.current_event()
ui.demo_banner(ev)
ui.header("My Day", "Your running order — built for a phone. Download it for offline use before you head out.")

attendees = data.people(attendees_only=True)
default_person = next((i for i, p in enumerate(attendees) if p["id"] == user["id"]), 0)
days = travel.diary_days(ev)          # includes travel days
now_local = clock.now_in(ev["timezone"])
today = now_local.date().isoformat()

c1, c2 = st.columns([1, 1])
person = c1.selectbox("Person", attendees, index=default_person, format_func=lambda p: f"{p['role']} — {p['name']}",
                      key="myday_person")
day_opts = days + ["All days"]
day = c2.selectbox("Day", day_opts, index=days.index(today) if today in days else 0, key=f"myday_day_{ev['id']}",
                   format_func=lambda d: d if d == "All days" else datetime.fromisoformat(d).strftime("%a %d %b"))
hide_cancelled = st.toggle("Hide cancelled", value=True)

meetings = data.meetings(ev["id"])
if hide_cancelled:
    meetings = [m for m in meetings if m["status"] != "cancelled"]
items = export.day_items(person["id"], meetings, data.sessions(ev["id"]), None if day == "All days" else day)
contexts = {it["id"]: data.meeting_context(it["id"]) for it in items if it["item_type"] == "meeting"}
title_day = "All days" if day == "All days" else datetime.fromisoformat(day).strftime("%A %d %B %Y")

# ---- today's travel (top card)
if day != "All days":
    see_ref = travel.can_see_ref(user, person["id"])
    blocks = travel.day_blocks(ev["id"], ev, day, person["id"])
    stay = [h for h in travel.hotels(ev["id"], ev) if h["person_id"] == person["id"]
            and h["check_in_ev"].date().isoformat() <= day <= h["check_out_ev"].date().isoformat()]
    lines = []
    for b in blocks:
        r = b["raw"]
        if b["kind"] == "flight":
            delay = (f" <span class='fb-pill' style='color:#F97316'>DELAYED {r['delay_minutes']} min</span>"
                     if r["status"] == "delayed" else "")
            lines.append(
                f"<div style='margin:.25rem 0'>✈️ <b>{ui.esc(r['airline'])} {ui.esc(r['flight_no'])}</b>{delay} "
                f"{ui.travel_pill(r['status'])}<br>"
                f"Departs <b>{r['dep_eff']:%a %H:%M}</b> {ui.esc(r['dep_airport'])} terminal {ui.esc(r['dep_terminal'] or 'TBC')}"
                f" → lands <b>{r['arr_eff']:%a %H:%M}</b> {ui.esc(r['arr_airport'])} terminal "
                f"{ui.esc(r['arr_terminal'] or 'TBC')} <span class='fb-small'>(airport local times · London "
                f"{clock.local_to_tz(r['arr_eff'], r['arr_tz'], clock.LONDON):%H:%M} landing)</span>"
                f"<br><span class='fb-small'>Seat {ui.esc(r['seat'] or '—')} · ref "
                f"{ui.esc(travel.mask(r['booking_ref'], see_ref))}</span></div>")
        elif b["kind"] == "transfer":
            lines.append(
                f"<div style='margin:.25rem 0'>🚗 <b>{ui.esc(travel.transfer_label(r))}</b> {ui.travel_pill(r['status'])}"
                f"<br>Pickup <b>{r['start_ev']:%H:%M}</b> at {ui.esc(r['pickup_place'])} → {ui.esc(r['dropoff_place'])}"
                f" · ~{r['est_minutes']} min<br><span class='fb-small'>{ui.esc(r['provider'] or 'Provider TBC')} · "
                f"driver: {ui.esc(r['driver_contact'] or 'not assigned yet')}</span></div>")
        elif b["kind"] == "hotel":
            lines.append(f"<div style='margin:.25rem 0'>🏨 <b>{ui.esc(b['label'][2:])}</b> {b['start']:%H:%M} · "
                         f"{ui.esc(r['name'])}</div>")
    for h in stay[:1]:
        link = travel.map_link(h["address"])
        venue = (f"{h['travel_min_to_venue']} min to venue" if h["travel_min_to_venue"] else "venue TBC")
        lines.append(
            f"<div style='margin:.25rem 0'>🛏️ Staying at <b>{ui.esc(h['name'])}</b> {ui.travel_pill(h['status'])}"
            f"<br><span class='fb-small'>{ui.esc(h['address'])}"
            + (f" · <a href='{link}' target='_blank'>open map</a>" if link else "")
            + f" · ☎ {ui.esc(h['phone'] or '—')} · {ui.esc(venue)} · ref {ui.esc(travel.mask(h['booking_ref'], see_ref))}"
              f"</span></div>")
    day_abbr = datetime.fromisoformat(day).strftime("%a ")          # flag messages carry "Mon 09:05"-style times
    unbooked_today = any(b["status"] == "not booked" for b in blocks)
    alerts = [f for f in travel.red_flags(ev["id"], ev) if f["person_id"] == person["id"]
              and (day_abbr in f["message"] or (f["kind"] == "not_booked" and unbooked_today))]
    if lines:
        warn = "".join(f"<div class='fb-small' style='color:{'#E5534B' if a['severity'] == 'error' else '#F97316'}'>"
                       f"⚠️ {ui.esc(a['message'])}</div>" for a in alerts[:4])
        st.markdown(f"<div class='fb-card accent'><h4>🧳 Today's travel</h4>{''.join(lines)}{warn}</div>",
                    unsafe_allow_html=True)

n_meet = sum(1 for i in items if i["item_type"] == "meeting")
st.markdown(ui.person_dot(person["colour"], f"{person['role']} · {n_meet} meeting{'s' if n_meet != 1 else ''}") +
            f'<span class="fb-small">{title_day} · times in {ui.esc(ev["city"])} local, London beneath</span>',
            unsafe_allow_html=True)

d1, d2, d3 = st.columns(3)
fname = f"my-day_{person['key']}_{ev['code']}_{'all' if day == 'All days' else day}"
d1.download_button("⬇️ Download HTML (offline)", export.build_html(person, ev, items, contexts, title_day),
                   file_name=f"{fname}.html", mime="text/html", width="stretch")
d2.download_button("⬇️ Download PDF", export.build_pdf(person, ev, items, contexts, title_day),
                   file_name=f"{fname}.pdf", mime="application/pdf", width="stretch")
itin = export.itinerary(ev, person, user)
d3.download_button("🧳 Travel itinerary (PDF)", export.build_itinerary_pdf(person, ev, itin),
                   file_name=f"itinerary_{person['key']}_{ev['code']}.pdf", mime="application/pdf", width="stretch",
                   help="One page: flights, hotel, transfers and meetings for the whole trip.")

if not items:
    st.info("Nothing in the diary for this selection.")

last_day = None
for it in items:
    if day == "All days":
        d = it["start"].strftime("%A %d %B")
        if d != last_day:
            st.markdown(f"#### {d}")
            last_day = d
    ldn = clock.local_to_tz(it["start"], ev["timezone"], clock.LONDON)
    is_now = it["start"] <= now_local < it["end"]
    time_html = (f"<b>{it['start']:%H:%M}–{it['end']:%H:%M}</b> "
                 f"<span class='fb-small'>· London {ldn:%H:%M}</span>"
                 + (" &nbsp;<span class='fb-pill' style='color:#E3A008'>NOW</span>" if is_now else ""))
    if it["item_type"] == "session":
        st.markdown(f"<div class='fb-card' style='border-left:4px solid #14A3A8;background:#18262A'>{time_html}"
                    f"<h4>★ {ui.esc(it['title'])}{' (TBC)' if it['tbc'] else ''}</h4>"
                    f"<div class='fb-meta'>Must attend · {ui.esc(it['location'])}</div></div>",
                    unsafe_allow_html=True)
        continue
    ctx = contexts[it["id"]]
    dm_attending = [c for c in ctx["contacts"] if c["attending"] and c["decision_maker"]]
    unapproved = [m for m in ctx["materials"] if m["approval_status"] != "approved"]
    tier = data.TIER_LABEL[it["tier"]]
    warn = ""
    if unapproved:
        warn = (f"<div class='fb-small' style='color:#F97316'>⚠️ Not approved, don't share: "
                f"{ui.esc(', '.join(m['name'] for m in unapproved))}</div>")
    with st.container():
        st.markdown(
            f"<div class='fb-card' style='border-left:4px solid {person['colour']};"
            f"{'opacity:.55;' if it['status'] == 'cancelled' else ''}'>{time_html}"
            f"<h4>{ui.esc(it['account'])} &nbsp;{ui.status_pill(it['status'])}</h4>"
            f"<div class='fb-meta'>📍 {ui.esc(it['location'])} · {ui.esc(tier)} · with {ui.esc(it['people_roles'])}"
            f"{' · 👤 DM attending' if dm_attending else ''}</div>"
            f"<div style='margin-top:.35rem'><b>Objective:</b> {ui.esc(it['objective'])}</div>"
            f"<div class='fb-ask'>🎯 <b>The one ask:</b> {ui.esc(it['the_ask'])}</div>{warn}</div>",
            unsafe_allow_html=True)
        if st.button("Open brief →", key=f"myday_brief_{it['id']}"):
            ui.open_brief(it["id"])
