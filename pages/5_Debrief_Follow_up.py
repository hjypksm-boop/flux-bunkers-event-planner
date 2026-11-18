"""Debrief & Follow-up — quick post-meeting form → structured notes + draft email → London Ops approval."""
from __future__ import annotations

from datetime import date, datetime, timedelta

import streamlit as st

from services import auth, clock, data, llm, ui

OBJECTIONS = ["Price / fees", "Integration with existing systems", "Locked into current supplier contract",
              "Credit terms", "Port coverage", "Data security", "Needs internal sign-off"]

user = auth.current_user()
editor = auth.is_editor()
ev = ui.current_event()
ui.demo_banner(ev)
ui.header("Debrief & Follow-up", "Two minutes after each meeting: capture it, get structured notes and a draft email. "
                                 "London Ops approves before anything is sent.")

if flash := st.session_state.pop("debrief_flash", None):
    st.success(flash)

meetings = data.meetings(ev["id"])
now_local = clock.now_in(ev["timezone"])
fus = data.follow_ups(ev["id"])
n_draft = sum(1 for f in fus if f["status"] == "draft")
tab_form, tab_fu, tab_notes = st.tabs(["✍️ File a debrief", f"✉️ Follow-ups ({n_draft} awaiting approval)",
                                       "🗒️ Debrief notes"])

# ----------------------------------------------------------------------------- debrief form
with tab_form:
    debriefed = {m["id"] for m in meetings if data.debrief_for(m["id"])}
    pending = [m for m in meetings if m["status"] in ("confirmed", "moved", "proposed") and m["id"] not in debriefed]
    show_all = st.toggle("Include meetings that haven't happened yet", value=False)
    options = pending if show_all else [m for m in pending if m["start"] <= now_local]
    if not options:
        st.success("All held meetings are debriefed ✓")
    else:
        if not show_all:
            st.caption(f"{len(options)} held meeting{'s' if len(options) != 1 else ''} awaiting a debrief.")
        mid = st.selectbox("Meeting", [m["id"] for m in options], key="db_pick",
                           format_func=lambda i: data.meeting_label(next(m for m in options if m["id"] == i)))
        m = next(x for x in options if x["id"] == mid)
        ctx = data.meeting_context(mid)
        st.markdown(f"<div class='fb-ask'>🎯 <b>The ask was:</b> {ui.esc(m['the_ask'] or '—')}</div>",
                    unsafe_allow_html=True)
        with st.form(f"debrief_{mid}", clear_on_submit=False):
            what = st.text_area("What happened?", placeholder="Who was there, what they said, what was agreed…",
                                height=110)
            c1, c2 = st.columns(2)
            interest = c1.radio("Interest level", ["low", "medium", "high"], index=1, horizontal=True)
            dm_present = c2.toggle("Decision-maker present?",
                                   value=any(c["attending"] and c["decision_maker"] for c in ctx["contacts"]))
            objections = st.multiselect("Objections raised", OBJECTIONS)
            other_obj = st.text_input("Other objection (optional)")
            c3, c4 = st.columns([2, 1])
            next_step = c3.text_input("Next step *")
            next_date = c4.date_input("Next step date *", value=None, format="YYYY-MM-DD",
                                      min_value=m["start"].date() - timedelta(days=1))
            c5, c6 = st.columns(2)
            signup = c5.toggle("Signed up to the Flux Bunkers app")
            trial = c6.toggle("Trial started")
            submitted = st.form_submit_button("Submit debrief & draft follow-up", type="primary")
        if submitted:
            problems = []
            if not what.strip():
                problems.append("Describe what happened.")
            if not next_step.strip():
                problems.append("A next step is required.")
            if not next_date:
                problems.append("A meeting can't be marked done without a next step date.")
            if problems:
                for p in problems:
                    st.error(p)
            else:
                objs = objections + ([other_obj.strip()] if other_obj.strip() else [])
                form = {"what_happened": what.strip(), "interest_level": interest, "objections": "; ".join(objs),
                        "next_step": next_step.strip(), "next_step_date": next_date.isoformat(),
                        "decision_maker_present": bool(dm_present), "app_signup": bool(signup),
                        "trial_started": bool(trial)}
                primary = next((c for c in ctx["contacts"] if c["attending"]), ctx["contacts"][0] if ctx["contacts"] else None)
                with st.spinner("Structuring notes and drafting the follow-up…"):
                    res = llm.structure_debrief(m, form, ctx["owner"], primary["name"] if primary else "")
                data.save_debrief(mid, user["id"], user["role"], form, res.content["notes_markdown"], res.generator,
                                  res.content["email_subject"], res.content["email_body"])
                st.session_state["debrief_flash"] = (
                    f"Debrief saved for {m['account']} — meeting marked done; follow-up draft is waiting for London Ops "
                    f"approval ({res.generator}{' · ' + res.note if res.note else ''}).")
                st.session_state["db_last"] = mid
                st.rerun()

    if (last := st.session_state.get("db_last")) and (d := data.debrief_for(last)):
        lm = data.meeting(last)
        with st.container(border=True):
            st.markdown(f"#### Structured notes — {ui.esc(lm['account'])}")
            st.markdown(d["structured_notes"])
            st.caption(f"Generated by {d['generator']}")

# ----------------------------------------------------------------------------- follow-ups
with tab_fu:
    if not editor:
        st.info("Read-only: London Ops approves and sends follow-ups.")
    order = {"draft": 0, "approved": 1, "sent": 2}
    status_filter = st.segmented_control("Show", ["draft", "approved", "sent"], selection_mode="multi",
                                         default=["draft", "approved"], key="fu_filter")
    shown = sorted([f for f in fus if f["status"] in (status_filter or [])],
                   key=lambda f: (order[f["status"]], f["end_at"]))
    if not shown:
        st.caption("Nothing to show.")
    for f in shown:
        end = datetime.fromisoformat(f["end_at"])
        deadline = end + timedelta(hours=24)
        if f["sent_at"]:
            sent_local = clock.utc_iso_to_local(f["sent_at"], ev["timezone"])
            hrs = (sent_local - end).total_seconds() / 3600
            timing = ui.pill(f"sent after {hrs:.0f}h" + (" ✓" if hrs <= 24 else " — late"),
                             "#4CAF7A" if hrs <= 24 else "#E5534B")
        else:
            left = (deadline - now_local).total_seconds() / 3600
            timing = ui.pill(f"{left:.0f}h left in 24h window" if left > 0 else f"overdue by {-left:.0f}h",
                             "#F97316" if left > 0 else "#E5534B")
        with st.expander(f"{f['status'].upper()} · {f['account']} · {f['owner_role']} · meeting {end:%a %H:%M}"):
            st.markdown(f"{ui.pill(f['status'], ui.FOLLOWUP_COLOURS[f['status']])} {timing} "
                        + (f"<span class='fb-small'>approved by {ui.esc(f['approved_by'])}</span>" if f["approved_by"] else ""),
                        unsafe_allow_html=True)
            if editor and f["status"] == "draft":
                subj = st.text_input("Subject", f["subject"], key=f"fs_{f['id']}")
                body = st.text_area("Body", f["body"], height=220, key=f"fb_{f['id']}")
                a, b = st.columns(2)
                if a.button("💾 Save edits", key=f"fsave_{f['id']}", width="stretch"):
                    data.update_follow_up(f["id"], subj, body, user["role"])
                    st.session_state["debrief_flash"] = "Draft saved."
                    st.rerun()
                if b.button("✅ Approve", key=f"fapp_{f['id']}", type="primary", width="stretch"):
                    if subj != f["subject"] or body != f["body"]:
                        data.update_follow_up(f["id"], subj, body, user["role"])
                    data.set_follow_up_status(f["id"], "approved", user["role"])
                    st.session_state["debrief_flash"] = f"Follow-up to {f['account']} approved."
                    st.rerun()
            else:
                st.markdown(f"**Subject:** {ui.esc(f['subject'])}", unsafe_allow_html=True)
                st.text(f["body"])
                if editor and f["status"] == "approved":
                    a, b = st.columns(2)
                    if a.button("📤 Mark as sent", key=f"fsent_{f['id']}", type="primary", width="stretch"):
                        data.set_follow_up_status(f["id"], "sent", user["role"])
                        st.session_state["debrief_flash"] = f"Follow-up to {f['account']} marked as sent."
                        st.rerun()
                    if b.button("↩︎ Back to draft", key=f"fback_{f['id']}", width="stretch"):
                        data.set_follow_up_status(f["id"], "draft", user["role"])
                        st.rerun()

# ----------------------------------------------------------------------------- notes
with tab_notes:
    df = data.debriefs(ev["id"])
    if df.empty:
        st.caption("No debriefs yet.")
    else:
        for _, r in df.sort_values("start_at", ascending=False).iterrows():
            with st.expander(f"{r['start_at'][:16].replace('T', ' ')} · {r['account']} · interest {r['interest_level']}"
                             f"{' · ✓ sign-up' if r['app_signup'] else ''}{' · ✓ trial' if r['trial_started'] else ''}"):
                st.markdown(r["structured_notes"] or r["what_happened"])
                st.caption(f"Filed by {r['author']} · {r['generator']}")
