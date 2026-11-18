"""Flux Bunkers Event Planner — entry point (login, shared sidebar, role-based navigation)."""
from __future__ import annotations

import streamlit as st
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

st.set_page_config(page_title="Flux Bunkers Event Planner", page_icon="⚓", layout="wide",
                   initial_sidebar_state="expanded")

from db.database import init_db  # noqa: E402
from services import auth, clock, data, llm, ui  # noqa: E402


@st.cache_resource
def _bootstrap() -> bool:
    init_db()          # creates + seeds the SQLite database on first run
    return True


_bootstrap()
ui.inject_css()

if "use_demo_clock" not in st.session_state:
    st.session_state["use_demo_clock"] = clock.demo_enabled()


# ----------------------------------------------------------------------------- login
def login_page() -> None:
    ui.demo_banner(None)
    left, mid, right = st.columns([1, 1.4, 1])
    with mid:
        st.markdown("# ⚓ Flux Bunkers")
        st.markdown("#### Event Planner — IBIA New York · FUJCON Fujairah")
        st.caption("Live diary, briefs and follow-through for the leadership team, run from the London office.")
        people = data.people()
        with st.form("login"):
            who = st.selectbox("Sign in as", people, format_func=lambda p: f"{p['role']} — {p['name']}"
                               if p["is_attendee"] else f"{p['role']} (editor)")
            pw = st.text_input("Password", type="password")
            ok = st.form_submit_button("Sign in", type="primary", width="stretch")
        if ok:
            if auth.check_password(who["key"], pw):
                auth.login(who)
                st.rerun()
            else:
                st.error("Incorrect password.")
        if auth.using_demo_passwords():
            with st.expander("Demo credentials"):
                st.markdown("Passwords are not configured, so demo defaults are active:\n\n"
                            + "\n".join(f"- **{k.upper()}**: `{v}`" for k, v in auth.DEMO_DEFAULTS.items())
                            + "\n\nSet `PASSWORD_CEO`, `PASSWORD_CCO`, `PASSWORD_SSM`, `PASSWORD_OPS` in `.env` "
                              "or Streamlit secrets to override.")
        st.caption("Attendees can view everything. London Ops can edit.")


user = auth.current_user()
if not user:
    st.navigation([st.Page(login_page, title="Sign in", icon="🔐")], position="hidden").run()
    st.stop()

# ----------------------------------------------------------------------------- sidebar
events = data.events()
if st.session_state.get("event_id") not in {e["id"] for e in events}:
    st.session_state["event_id"] = events[0]["id"]

with st.sidebar:
    st.markdown("### ⚓ Flux Bunkers")
    st.markdown(ui.person_dot(user["colour"], f"{user['role']} · {user['name']}"), unsafe_allow_html=True)
    st.selectbox("Event", [e["id"] for e in events], key="event_id",
                 format_func=lambda i: next(f"{e['name']} · {e['city']}" for e in events if e["id"] == i))
    ev = ui.current_event()
    st.caption(f"{ev['start_date']} → {ev['end_date']} · {ev['timezone']}")
    st.toggle("Demo clock (mid-IBIA)", key="use_demo_clock",
              help="IBIA hasn't happened yet, so the demo runs on a clock frozen at Wed 2 Dec 2026 15:30 New York. "
                   "Turn off to use the real time.")
    st.caption(("🤖 AI: Groq · " + llm.model_name()) if llm.ai_available()
               else "🤖 AI: template mode (no GROQ_API_KEY)")
    if st.button("Sign out", width="stretch"):
        auth.logout()
        st.rerun()

# ----------------------------------------------------------------------------- navigation
pages = {
    "Event": [
        st.Page("pages/1_Live_Diary.py", title="Live Diary", icon="🗓️", default=True),
        st.Page("pages/2_My_Day.py", title="My Day", icon="📱"),
        st.Page("pages/3_Meeting_Brief.py", title="Meeting Brief", icon="📋"),
    ],
    "Follow-through": [
        st.Page("pages/5_Debrief_Follow_up.py", title="Debrief & Follow-up", icon="✍️"),
        st.Page("pages/6_KPI_Dashboard.py", title="KPI Dashboard", icon="📊"),
        st.Page("pages/7_Learnings.py", title="IBIA → FUJCON Learnings", icon="🧭"),
    ],
}
if auth.is_editor():
    pages["London Ops"] = [st.Page("pages/4_Ops_Console.py", title="Ops Console", icon="🛠️")]

st.navigation(pages).run()
