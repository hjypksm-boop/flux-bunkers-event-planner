"""Meeting Brief — everything known about the account, plus an AI brief grounded only in DB fields."""
from __future__ import annotations

from datetime import date

import streamlit as st

from services import auth, clock, data, llm, ui

user = auth.current_user()
ev = ui.current_event()
ui.demo_banner(ev)

meetings = data.meetings(ev["id"])
if not meetings:
    st.info("No meetings for this event yet.")
    st.stop()

ids = [m["id"] for m in meetings]
wanted = st.session_state.get("brief_meeting_id")
if wanted not in ids:
    # the requested meeting belongs to another event, or nothing chosen yet: pick the next upcoming one
    now_local = clock.now_in(ev["timezone"])
    upcoming = [m for m in meetings if m["end"] >= now_local and m["status"] != "cancelled"]
    wanted = (upcoming[0] if upcoming else meetings[0])["id"]
    st.session_state["brief_meeting_id"] = wanted


def _on_pick():
    st.session_state["brief_meeting_id"] = st.session_state["brief_pick"]


st.session_state["brief_pick"] = wanted
st.selectbox("Meeting", ids, key="brief_pick", on_change=_on_pick,
             format_func=lambda i: data.meeting_label(next(m for m in meetings if m["id"] == i)))

ctx = data.meeting_context(wanted)
m, acc = ctx["meeting"], ctx["account"]
ldn = clock.local_to_tz(m["start"], ev["timezone"], clock.LONDON)

st.markdown(f"# {ui.esc(acc['name'])}")
st.markdown(
    f"{ui.status_pill(m['status'])} &nbsp; <b>{m['start']:%a %d %b %H:%M}–{m['end']:%H:%M}</b> {ui.esc(ev['city'])} "
    f"<span class='fb-small'>(London {ldn:%H:%M})</span> &nbsp;·&nbsp; 📍 {ui.esc(m['location'])} &nbsp;·&nbsp; "
    + " ".join(ui.person_dot(p["colour"], p["role"]) for p in ctx["attendees"]),
    unsafe_allow_html=True)

st.markdown(f"<div class='fb-ask' style='font-size:1.05rem'>🎯 <b>The one ask:</b> {ui.esc(m['the_ask'] or 'Not set')}"
            f"<div class='fb-small' style='margin-top:.2rem'>Objective: {ui.esc(m['objective'] or '—')} · "
            f"Follow-up owner: <b>{ui.esc(ctx['owner']['name'])} ({ui.esc(ctx['owner']['role'])})</b></div></div>",
            unsafe_allow_html=True)
st.write("")

left, right = st.columns([1.05, 1], gap="large")

# ----------------------------------------------------------------------------- left: facts from the DB
with left:
    st.markdown("### Account")
    st.markdown(f"{ui.esc(acc['type']).capitalize()} · **{data.TIER_LABEL[acc['tier']]}** · {ui.esc(acc['region'])}  \n"
                f"Ports: {ui.esc(acc['ports'])}")
    h1, h2, h3, h4 = st.columns(4)
    trend_icon = {"growing": "↗", "flat": "→", "declining": "↘"}.get(acc["usage_trend"], "–")
    h1.metric("Usage trend", f"{trend_icon} {acc['usage_trend']}")
    h2.metric("Monthly spend", f"${acc['monthly_spend'] / 1000:,.0f}k" if acc["monthly_spend"] else "—")
    if acc["renewal_date"]:
        days_left = (date.fromisoformat(acc["renewal_date"]) - m["start"].date()).days
        h3.metric("Renewal", acc["renewal_date"], f"{days_left} days", delta_color="off")
    else:
        h3.metric("Renewal", "—")
    hcol = {"healthy": "#4CAF7A", "watch": "#F97316", "at risk": "#E5534B", "prospect": "#8A8F98"}[acc["health_status"]]
    h4.markdown(f"<div class='fb-small'>Health</div>{ui.pill(acc['health_status'], hcol)}", unsafe_allow_html=True)

    st.markdown("### Contacts")
    for c in ctx["contacts"]:
        tags = []
        if c["decision_maker"]:
            tags.append(ui.pill("decision-maker", "#E3A008"))
        tags.append(ui.pill("attending", "#4C9BE8") if c["attending"] else ui.pill("not invited", "#8A8F98"))
        st.markdown(f"**{ui.esc(c['name'])}** — {ui.esc(c['role'])} &nbsp; {' '.join(tags)}", unsafe_allow_html=True)

    st.markdown("### Previous notes")
    if not ctx["notes"]:
        st.caption("No previous conversation notes.")
    for n in ctx["notes"]:
        st.markdown(f"<div class='fb-card' style='padding:.6rem .8rem'><span class='fb-small'>{n['note_date']} · "
                    f"{ui.esc(n['author'] or 'unknown')}</span><br>{ui.esc(n['body'])}</div>", unsafe_allow_html=True)
    if ctx["prior_debriefs"]:
        st.markdown("### Earlier meetings (debriefs)")
        for d in ctx["prior_debriefs"]:
            st.markdown(f"<div class='fb-card' style='padding:.6rem .8rem'><span class='fb-small'>{d['event_code']} · "
                        f"{d['start_at'][:10]} · interest {d['interest_level']}</span><br>{ui.esc(d['what_happened'])}"
                        f"<br><span class='fb-small'>Next step: {ui.esc(d['next_step'])} by {d['next_step_date']}</span></div>",
                        unsafe_allow_html=True)

    st.markdown("### Materials")
    if not ctx["materials"]:
        st.caption("No materials attached.")
    for mt in ctx["materials"]:
        ok = mt["approval_status"] == "approved"
        status = ui.pill(f"✓ approved · {mt['approved_by']}", "#4CAF7A") if ok else \
            ui.pill(f"⚠ {mt['approval_status']} — do not share", "#F97316")
        st.markdown(f"[{ui.esc(mt['name'])}]({mt['link']}) <span class='fb-small'>({ui.esc(mt['type'])})</span> {status}",
                    unsafe_allow_html=True)

# ----------------------------------------------------------------------------- right: AI brief
with right:
    st.markdown("### Brief")
    brief = data.latest_brief(m["id"])
    b1, b2 = st.columns([1, 1.4])
    gen = b1.button("✨ Generate brief", type="primary", width="stretch")
    b2.caption(("Groq · " + llm.model_name()) if llm.ai_available() else
               "Template mode — add GROQ_API_KEY for AI briefs")
    if gen:
        with st.spinner("Summarising database fields…"):
            res = llm.generate_brief(ctx)
        data.save_brief(m["id"], res.content["markdown"], res.sources, res.unverified, res.generator)
        if res.note:
            st.toast(res.note, icon="ℹ️")
        brief = data.latest_brief(m["id"])

    if not brief:
        st.info("No brief yet. Click **Generate brief** — it summarises only what is in the database and "
                "cites the fields it used.")
    else:
        with st.container(border=True):
            st.markdown(brief["content"])
            st.caption(f"Generated {ui.ago(brief['generated_at'])} · {brief['generator']}")
        current_flags = llm.deterministic_unverified(ctx)
        flags = list(dict.fromkeys(brief["unverified"] + current_flags))
        if flags:
            st.markdown("**⚠️ Unverified / check before the meeting**")
            for f in flags:
                st.markdown(f"- {ui.esc(f)}", unsafe_allow_html=True)
        with st.expander(f"Sources — {len(brief['sources'])} database fields used"):
            fields = llm.brief_fields(ctx)
            for k in brief["sources"]:
                val = fields.get(k) or "; ".join(v for kk, v in fields.items() if kk.startswith(k + "."))
                st.markdown(f"- `{k}` — {ui.esc(val or '(group)')}", unsafe_allow_html=True)
        st.caption("Rule: the brief may only use the fields listed above. Citations to unknown fields are replaced "
                   "with [unverified].")
