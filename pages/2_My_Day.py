"""My Day — a mobile-friendly running order for one person, with offline HTML/PDF download."""
from __future__ import annotations

from datetime import datetime

import streamlit as st

from services import auth, clock, data, export, ui

user = auth.current_user()
ev = ui.current_event()
ui.demo_banner(ev)
ui.header("My Day", "Your running order — built for a phone. Download it for offline use before you head out.")

attendees = data.people(attendees_only=True)
default_person = next((i for i, p in enumerate(attendees) if p["id"] == user["id"]), 0)
days = data.event_days(ev)
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

n_meet = sum(1 for i in items if i["item_type"] == "meeting")
st.markdown(ui.person_dot(person["colour"], f"{person['role']} · {n_meet} meeting{'s' if n_meet != 1 else ''}") +
            f'<span class="fb-small">{title_day} · times in {ui.esc(ev["city"])} local, London beneath</span>',
            unsafe_allow_html=True)

d1, d2 = st.columns(2)
fname = f"my-day_{person['key']}_{ev['code']}_{'all' if day == 'All days' else day}"
d1.download_button("⬇️ Download HTML (offline)", export.build_html(person, ev, items, contexts, title_day),
                   file_name=f"{fname}.html", mime="text/html", width="stretch")
d2.download_button("⬇️ Download PDF", export.build_pdf(person, ev, items, contexts, title_day),
                   file_name=f"{fname}.pdf", mime="application/pdf", width="stretch")

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
