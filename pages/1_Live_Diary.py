"""Live Diary — three swimlanes, session bands, local/London toggle, auto-refresh, change banner."""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import streamlit as st

from services import auth, clock, data, ui
from services.timeline import build_timeline

user = auth.current_user()
ev = ui.current_event()
ui.demo_banner(ev)
ui.header("Live Diary", f"{ev['name']} · {ev['city']} · {ev['agenda_note']}")

attendees = data.people(attendees_only=True)
days = data.event_days(ev)
now_local = clock.now_in(ev["timezone"])
default_day = now_local.date().isoformat() if now_local.date().isoformat() in days else days[0]
day_key = f"diary_day_{ev['id']}"
if st.session_state.get(day_key) not in days:
    st.session_state[day_key] = default_day

c1, c2, c3 = st.columns([2.2, 1.4, 1])
with c1:
    day = st.segmented_control(
        "Day", days, key=day_key, format_func=lambda d: datetime.fromisoformat(d).strftime("%a %d %b"),
        selection_mode="single") or default_day
with c2:
    tz_mode = st.segmented_control("Times shown in", ["Event local", "London"], default="Event local",
                                   key="diary_tz") or "Event local"
with c3:
    show_cancelled = st.toggle("Show cancelled", value=True, key="diary_cancelled")
london = tz_mode == "London"


@st.fragment(run_every=30)
def live_panel() -> None:
    # ---- changes since this viewer last looked
    unseen = data.unseen_changes(user["id"], ev["id"])
    if unseen:
        with st.container(border=True):
            top, btn = st.columns([5, 1])
            top.markdown(f"**🔔 {len(unseen)} change{'s' if len(unseen) > 1 else ''} since you last looked**")
            if btn.button("Got it", key="seen_btn", width="stretch"):
                data.mark_seen(user["id"])
                st.rerun(scope="fragment")
            for c in unseen[:8]:
                st.markdown(f'<div class="fb-change">• {ui.esc(c["summary"])} '
                            f'<span class="fb-small">— {ui.esc(c["who"])}, {ui.ago(c["ts"])}</span></div>',
                            unsafe_allow_html=True)
            if len(unseen) > 8:
                st.caption(f"…and {len(unseen) - 8} more (see Ops Console → Change log).")

    meetings = data.meetings(ev["id"])
    sessions = data.sessions(ev["id"])
    fig = build_timeline(meetings, sessions, attendees, ev, day, london=london, now_local=now_local,
                         show_cancelled=show_cancelled)

    legend = " ".join(ui.person_dot(p["colour"], p["role"]) for p in attendees)
    refreshed = datetime.now(timezone.utc).astimezone(ZoneInfo(clock.LONDON))
    st.markdown(f'{legend}<span class="fb-small">Last updated {refreshed:%H:%M:%S} London (auto-refresh every 30s) · '
                f'times in {"London" if london else ev["city"] + " local"} · click a meeting to open its brief</span>',
                unsafe_allow_html=True)

    event = st.plotly_chart(fig, width="stretch", on_select="rerun", selection_mode="points",
                            key=f"timeline_{ev['id']}_{day}_{london}", config={"displayModeBar": False})
    points = (event or {}).get("selection", {}).get("points", []) if event else []
    for p in points:
        cd = p.get("customdata")
        if isinstance(cd, (list, tuple)) and cd and isinstance(cd[0], (int, float)):
            ui.open_brief(int(cd[0]))

    # ---- day list + fallback opener (also works on touch devices)
    day_rows = [m for m in meetings if m["start_at"][:10] == day and (show_cancelled or m["status"] != "cancelled")]
    if day_rows:
        with st.expander(f"Meetings on {datetime.fromisoformat(day):%a %d %b} ({len(day_rows)})", expanded=False):
            for m in day_rows:
                t0, t1 = ui.fmt_time(m["start"], ev, london), ui.fmt_time(m["end"], ev, london)
                st.markdown(f"`{t0}–{t1}` &nbsp; {ui.status_pill(m['status'])} &nbsp; **{ui.esc(m['account'])}** "
                            f"<span class='fb-small'>· {ui.esc(m['people_roles'])} · {ui.esc(m['location'])}</span>",
                            unsafe_allow_html=True)
        pick_col, btn_col = st.columns([4, 1])
        pick = pick_col.selectbox("Open a brief", day_rows, key="diary_pick", label_visibility="collapsed",
                                  format_func=lambda m: f"{ui.fmt_time(m['start'], ev, london)} · {m['account']} · "
                                                        f"{m['people_roles']} · {m['status']}")
        if btn_col.button("Open brief →", width="stretch", type="primary"):
            ui.open_brief(pick["id"])
    else:
        st.info("No meetings on this day.")


live_panel()
