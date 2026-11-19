"""Ops Console (London Ops only) — add/edit/move/cancel, live clash checks, free-slot finder, change log."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pandas as pd
import streamlit as st

from services import auth, clock, data, travel, ui
from services.scheduling import (
    BUFFER_MIN, LANDING_BUFFER_MIN, MEETING_STATUSES, Item, Slot, check_diary, check_meeting, free_slots,
    busy_for_person, slot_freed_by, suggest_reserves, travel_flags, validate_meeting,
)

user = auth.current_user()
if not auth.is_editor():
    st.error("The Ops Console is for London Ops only.")
    st.stop()

ev = ui.current_event()
ui.demo_banner(ev)
ui.header("Ops Console", "Every change (meetings and travel) is written to the change log and appears on attendees' "
                        "diaries within 30 seconds.")

WHO = f"{user['role']}"
attendees = data.people(attendees_only=True)
pmap = {p["id"]: p for p in attendees}
accounts = data.accounts()
amap = {a["id"]: a for a in accounts}
all_materials = data.materials()
days = travel.diary_days(ev)          # event days + travel days
DAY_START, DAY_END = time(7, 30), time(19, 0)


def load():
    ms = data.meetings(ev["id"])
    ss = data.sessions(ev["id"])
    return ms, ss, data.to_items(ms), data.to_session_items(ss)


meetings, sessions, items, session_items = load()
travel_items = travel.travel_items(ev["id"], ev)


def show_clashes(clashes, empty_msg="No clashes ✓"):
    if not clashes:
        st.success(empty_msg)
        return
    for c in sorted(clashes, key=lambda c: c.severity != "error"):
        who = pmap.get(c.person_id, {}).get("role", "?")
        icon = "⛔" if c.severity == "error" else "⚠️"
        (st.error if c.severity == "error" else st.warning)(f"{icon} **{who}** — {c.message}")


# ----------------------------------------------------------------------------- shared form
def meeting_form(prefix: str, m: dict | None) -> dict:
    """Live widgets (not st.form) so the clash check updates as you type."""
    c1, c2, c3 = st.columns([2, 1, 1.4])
    acc_ids = [a["id"] for a in accounts]
    account_id = c1.selectbox("Account", acc_ids, key=f"{prefix}_acc",
                              index=acc_ids.index(m["account_id"]) if m else 0,
                              format_func=lambda i: f"{amap[i]['name']} · T{amap[i]['tier']}")
    status = c2.selectbox("Status", MEETING_STATUSES, key=f"{prefix}_status",
                          index=MEETING_STATUSES.index(m["status"]) if m else 0)
    att_ids = [p["id"] for p in attendees]
    people_ids = c3.multiselect("Our attendees", att_ids, key=f"{prefix}_people",
                                default=[p for p in (m["people"] if m else [att_ids[0]]) if p in att_ids],
                                format_func=lambda i: pmap[i]["role"])
    c4, c5, c6, c7 = st.columns([1.3, 1, 1, 1.4])
    d0 = m["start_at"][:10] if m else days[0]
    day = c4.selectbox("Day", days, key=f"{prefix}_day", index=days.index(d0) if d0 in days else 0,
                       format_func=lambda d: datetime.fromisoformat(d).strftime("%a %d %b"))
    start_t = c5.time_input("Start", value=m["start"].time() if m else time(10, 0), step=300, key=f"{prefix}_start")
    end_t = c6.time_input("End", value=m["end"].time() if m else time(10, 45), step=300, key=f"{prefix}_end")
    owner_opts = people_ids or att_ids
    owner_default = m["owner_id"] if m and m["owner_id"] in owner_opts else owner_opts[0]
    owner_id = c7.selectbox("Owner / follow-up owner", owner_opts, key=f"{prefix}_owner_{','.join(map(str, owner_opts))}",
                            index=owner_opts.index(owner_default), format_func=lambda i: pmap[i]["role"])
    location = st.text_input("Location", value=(m["location"] if m else "Convention venue – Meeting Room 2") or "",
                             key=f"{prefix}_loc")
    c8, c9 = st.columns(2)
    objective = c8.text_input("Objective", value=(m["objective"] if m else "") or "", key=f"{prefix}_obj")
    the_ask = c9.text_input("The one ask", value=(m["the_ask"] if m else "") or "", key=f"{prefix}_ask")
    c10, c11 = st.columns([2, 1])
    next_step = c10.text_input("Next step", value=(m["next_step"] if m else "") or "", key=f"{prefix}_ns")
    nsd_val = date.fromisoformat(m["next_step_date"]) if m and m["next_step_date"] else None
    nsd = c11.date_input("Next step date", value=nsd_val, key=f"{prefix}_nsd", format="YYYY-MM-DD")
    contacts = data.contacts_for(account_id)
    cur_contacts = []
    cur_mats = []
    if m:
        ctx = data.meeting_context(m["id"])
        cur_contacts = [c["id"] for c in ctx["contacts"] if c["attending"]]
        cur_mats = [x["id"] for x in ctx["materials"]]
    c12, c13 = st.columns(2)
    contact_ids = c12.multiselect(
        "Client attendees", [c["id"] for c in contacts], key=f"{prefix}_contacts_{account_id}",
        default=[c for c in cur_contacts if c in {x["id"] for x in contacts}],
        format_func=lambda i: next(f"{c['name']} — {c['role']}{' (DM)' if c['decision_maker'] else ''}"
                                   for c in contacts if c["id"] == i))
    mat_ids = c13.multiselect(
        "Materials", [x["id"] for x in all_materials], default=cur_mats, key=f"{prefix}_mats",
        format_func=lambda i: next(f"{x['name']}{'' if x['approval_status'] == 'approved' else ' ⚠ ' + x['approval_status']}"
                                   for x in all_materials if x["id"] == i))
    start = datetime.combine(date.fromisoformat(day), start_t)
    end = datetime.combine(date.fromisoformat(day), end_t)
    return {
        "account_id": account_id, "status": status, "people_ids": people_ids, "owner_id": owner_id,
        "start": start, "end": end, "start_at": start.isoformat(timespec="seconds"),
        "end_at": end.isoformat(timespec="seconds"), "location": location.strip(), "objective": objective.strip(),
        "the_ask": the_ask.strip(), "next_step": next_step.strip(), "next_step_date": nsd.isoformat() if nsd else None,
        "contact_ids": contact_ids, "material_ids": mat_ids,
    }


def check_form(vals: dict, meeting_id: int) -> tuple[list[str], list]:
    errors = validate_meeting(vals["status"], vals["start"], vals["end"], vals["next_step"], vals["next_step_date"])
    if not vals["people_ids"]:
        errors.append("Pick at least one attendee")
    cand = Item(meeting_id, vals["start"], vals["end"], frozenset(vals["people_ids"]), vals["location"],
                "this meeting", vals["status"])
    return errors, check_meeting(cand, items, session_items, travel=travel_items)


def window_for(day: str, from_now: bool = False) -> Slot:
    """Working window for a day; with from_now, never earlier than the current time (rounded up to 5 min)."""
    d = date.fromisoformat(day)
    start, end = datetime.combine(d, DAY_START), datetime.combine(d, DAY_END)
    if from_now:
        now = clock.now_in(ev["timezone"])
        now = now.replace(second=0, microsecond=0) + timedelta(minutes=(-now.minute) % 5)
        start = min(max(start, now), end)
    return Slot(start, end)


def render_freed(meeting_id: int) -> None:
    """Free-slot finder for a cancelled meeting + reserve-list suggestions with one-click booking."""
    m = data.meeting(meeting_id)
    if not m:
        return
    st.markdown(f"#### 🔓 Slot freed by {ui.esc(m['account'])} ({m['start']:%a %H:%M}–{m['end']:%H:%M})",
                unsafe_allow_html=True)
    ms, ss, its, sits = load()
    cancelled = next(i for i in its if i.id == meeting_id)
    freed = slot_freed_by(cancelled, its, sits, window_for(m["start_at"][:10], from_now=True), buffer_min=BUFFER_MIN,
                          travel=travel_items)
    booked = data.booked_account_ids(ev["id"])
    cands = data.reserve_candidates(ev["id"])
    any_slot = False
    for pid, slot in freed.items():
        role = pmap[pid]["role"] if pid in pmap else str(pid)
        if slot is None:
            st.caption(f"{role}: no usable free window (the time has passed or been re-used).")
            continue
        any_slot = True
        st.markdown(f"**{role}** is free **{slot.start:%H:%M}–{slot.end:%H:%M}** ({slot.minutes} min, "
                    f"{BUFFER_MIN}-min buffers applied)")
        sugg = suggest_reserves(cands, slot, pid, booked)
        if not sugg:
            st.caption("No reserve-list accounts fit this slot.")
        for s in sugg:
            c = s.candidate
            col1, col2 = st.columns([4, 1])
            col1.markdown(f"• **{ui.esc(c.account_name)}** — {' · '.join(s.reasons)}  \n"
                          f"<span class='fb-small'>{ui.esc(c.note)}</span>", unsafe_allow_html=True)
            if col2.button("Book", key=f"book_{meeting_id}_{pid}_{c.account_id}", width="stretch"):
                start = max(slot.start, cancelled.start)
                minutes = max(c.min_minutes, 30)
                if start + timedelta(minutes=minutes) > slot.end:
                    start = slot.end - timedelta(minutes=minutes)
                end = start + timedelta(minutes=minutes)
                new_id = data.create_meeting(ev["id"], {
                    "account_id": c.account_id, "owner_id": pid, "start_at": start.isoformat(timespec="seconds"),
                    "end_at": end.isoformat(timespec="seconds"), "location": m["location"], "status": "proposed",
                    "objective": f"Reserve-list call-in: {c.note}", "the_ask": "", "next_step": None,
                    "next_step_date": None}, [pid], [x["id"] for x in data.contacts_for(c.account_id) if x["decision_maker"]][:1],
                    [], WHO)
                st.session_state.pop("freed_meeting", None)
                st.session_state["ops_flash"] = (f"Booked {c.account_name} as a proposed meeting "
                                                 f"({start:%H:%M}–{end:%H:%M}) — confirm with the client, then set status.")
                st.session_state["ops_edit_request"] = new_id
                st.rerun()
    if not any_slot:
        st.info("Nothing to back-fill.")


# ----------------------------------------------------------------------------- page
if flash := st.session_state.pop("ops_flash", None):
    st.success(flash)

tab_edit, tab_add, tab_clash, tab_free, tab_travel, tab_log = st.tabs(
    ["✏️ Edit / move / cancel", "➕ Add meeting", "🚦 Clash check", "🔓 Free slots & reserves", "✈️ Travel",
     "🧾 Change log"])

# ---- edit
with tab_edit:
    ids = [m["id"] for m in meetings]
    if (req := st.session_state.pop("ops_edit_request", None)) in ids:
        st.session_state["ops_edit_pick"] = req
    if st.session_state.get("ops_edit_pick") not in ids:
        st.session_state["ops_edit_pick"] = ids[0] if ids else None
    if not ids:
        st.info("No meetings yet.")
    else:
        mid = st.selectbox("Meeting", ids, key="ops_edit_pick",
                           format_func=lambda i: data.meeting_label(next(m for m in meetings if m["id"] == i)))
        m = next(x for x in meetings if x["id"] == mid)
        with st.container(border=True):
            vals = meeting_form(f"ed{mid}", m)
        errors, clashes = check_form(vals, mid)
        st.markdown("##### Live checks")
        for e in errors:
            st.error(e)
        show_clashes(clashes)
        has_hard = any(c.severity == "error" for c in clashes)
        override = st.checkbox("Save anyway (I've checked the clash)", key=f"ovr_{mid}") if has_hard else True
        a, b = st.columns([1, 1])
        if a.button("💾 Save changes", type="primary", disabled=bool(errors) or not override, width="stretch",
                    key=f"save_{mid}"):
            changed = data.update_meeting(mid, {k: vals[k] for k in data.TRACKED_FIELDS}, WHO,
                                          people_ids=vals["people_ids"], contact_ids=vals["contact_ids"],
                                          material_ids=vals["material_ids"])
            st.session_state["ops_flash"] = ("Saved: " + "; ".join(changed)) if changed else "No changes to save."
            st.rerun()
        with b.popover("✕ Cancel meeting", width="stretch", disabled=m["status"] == "cancelled"):
            reason = st.text_input("Reason (goes to the change log)", key=f"reason_{mid}")
            if st.button("Confirm cancellation", type="primary", key=f"cancel_{mid}"):
                data.cancel_meeting(mid, WHO, reason.strip())
                st.session_state["freed_meeting"] = mid
                st.session_state["ops_flash"] = f"Cancelled {m['account']}. See the freed slot below."
                st.rerun()
        if st.session_state.get("freed_meeting") == mid or m["status"] == "cancelled":
            with st.container(border=True):
                render_freed(mid)

# ---- add
with tab_add:
    with st.container(border=True):
        vals = meeting_form("add", None)
    errors, clashes = check_form(vals, -1)
    st.markdown("##### Live checks")
    for e in errors:
        st.error(e)
    show_clashes(clashes)
    has_hard = any(c.severity == "error" for c in clashes)
    override = st.checkbox("Book anyway (I've checked the clash)", key="ovr_add") if has_hard else True
    if st.button("➕ Add meeting", type="primary", disabled=bool(errors) or not override):
        new_id = data.create_meeting(ev["id"], vals, vals["people_ids"], vals["contact_ids"], vals["material_ids"], WHO)
        st.session_state["ops_flash"] = f"Added meeting with {amap[vals['account_id']]['name']}."
        st.session_state["ops_edit_request"] = new_id
        for k in [k for k in st.session_state if str(k).startswith("add_")]:
            del st.session_state[k]
        st.rerun()

# ---- whole-diary clash check
with tab_clash:
    all_clashes = check_diary(items, session_items, travel=travel_items)
    errs = [c for c in all_clashes if c.severity == "error"]
    warns = [c for c in all_clashes if c.severity == "warning"]
    k1, k2, k3 = st.columns(3)
    k1.metric("Hard clashes", len(errs))
    k2.metric("Warnings", len(warns))
    k3.metric("Active meetings checked", sum(1 for i in items if i.active))
    st.caption(f"Rules: same-person overlap · <{BUFFER_MIN} min buffer · <30 min between different locations · "
               "meeting during a session that person must attend · before landing + 2 h · after the latest hotel "
               "departure for the return flight · during a transfer · before 09:00 the morning after a long-haul "
               "arrival (warning). Cancelled meetings are ignored.")
    gaps_found = [f for p in attendees for f in travel_flags(p["id"], travel_items)]
    if gaps_found:
        st.markdown("##### Travel logistics gaps")
        for f in sorted(gaps_found, key=lambda f: f.severity != "error"):
            (st.error if f.severity == "error" else st.warning)(
                f"{'⛔' if f.severity == 'error' else '⚠️'} **{pmap[f.person_id]['role']}** — {f.message}")
    if all_clashes:
        mlookup = {m["id"]: m for m in meetings}
        rows = [{
            "Severity": "⛔ error" if c.severity == "error" else "⚠️ warning",
            "Rule": c.kind, "Person": pmap.get(c.person_id, {}).get("role", "?"),
            "Meeting": f"{mlookup[c.meeting_id]['start']:%a %H:%M} {mlookup[c.meeting_id]['account']}",
            "Clashes with": c.other_label, "Detail": c.message,
        } for c in sorted(all_clashes, key=lambda c: (c.severity != "error", mlookup[c.meeting_id]["start_at"]))]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        fix = st.selectbox("Fix a clash", sorted({c.meeting_id for c in all_clashes}),
                           format_func=lambda i: data.meeting_label(mlookup[i]))
        if st.button("Open in editor"):
            st.session_state["ops_edit_request"] = fix
            st.session_state["ops_flash"] = "Opened in the Edit tab ↑"
            st.rerun()
    else:
        st.success("Diary is clash-free ✓")

# ---- free slots & reserves
with tab_free:
    st.markdown("##### Recent cancellations")
    cancelled = [m for m in meetings if m["status"] == "cancelled"]
    if cancelled:
        pick = st.selectbox("Cancelled meeting", [m["id"] for m in cancelled],
                            format_func=lambda i: data.meeting_label(next(m for m in cancelled if m["id"] == i)))
        with st.container(border=True):
            render_freed(pick)
    else:
        st.caption("No cancellations.")
    st.markdown("##### Free-slot finder")
    f1, f2, f3 = st.columns(3)
    who = f1.selectbox("Person", [p["id"] for p in attendees], format_func=lambda i: pmap[i]["role"], key="fs_person")
    fday = f2.selectbox("Day", days, format_func=lambda d: datetime.fromisoformat(d).strftime("%a %d %b"), key="fs_day")
    min_len = f3.select_slider("Minimum slot", [15, 30, 45, 60, 90], value=30, key="fs_min")
    busy = busy_for_person(who, items, session_items, travel=travel_items)
    gaps = free_slots(busy, window_for(fday), min_minutes=min_len, buffer_min=BUFFER_MIN)
    now_local = clock.now_in(ev["timezone"])
    if not gaps:
        st.info("No free slots that long.")
    for g in gaps:
        past = g.end <= now_local
        st.markdown(f"- **{g.start:%H:%M}–{g.end:%H:%M}** ({g.minutes} min){' · _in the past_' if past else ''}")
    if gaps:
        st.markdown("##### Reserve list")
        st.dataframe(pd.DataFrame([{"Priority": c.priority, "Account": c.account_name, "Tier": c.tier,
                                    "Preferred owner": pmap.get(c.preferred_owner_id, {}).get("role", "—"),
                                    "Min mins": c.min_minutes, "Note": c.note}
                                   for c in data.reserve_candidates(ev["id"])]), hide_index=True, width="stretch")

# ---- travel
TZS = ["Europe/London", "America/New_York", "Asia/Dubai"]
SPECS = {
    "trip": [("outbound_date", "date"), ("return_date", "date"), ("status", travel.TRIP_STATUSES),
             ("budget_gbp", "money"), ("notes", "text")],
    "flight": [("direction", travel.DIRECTIONS), ("status", travel.FLIGHT_STATUSES), ("delay_minutes", "int"),
               ("airline", "text"), ("flight_no", "text"), ("seat", "text"),
               ("dep_airport", "text"), ("dep_at", "dt"), ("dep_tz", TZS), ("dep_terminal", "text"),
               ("arr_airport", "text"), ("arr_at", "dt"), ("arr_tz", TZS), ("arr_terminal", "text"),
               ("booking_ref", "text"), ("cost_gbp", "money")],
    "hotel": [("name", "text"), ("status", travel.BOOKING_STATUSES), ("address", "text"), ("tz", TZS),
              ("check_in_at", "dt"), ("check_out_at", "dt"), ("phone", "text"), ("distance_km", "float"),
              ("travel_min_to_venue", "int"), ("booking_ref", "text"), ("cost_gbp", "money")],
    "transfer": [("type", travel.TRANSFER_TYPES), ("status", travel.BOOKING_STATUSES), ("pickup_at", "dt"),
                 ("tz", TZS), ("est_minutes", "int"), ("pickup_place", "text"), ("dropoff_place", "text"),
                 ("provider", "text"), ("driver_contact", "text"), ("booking_ref", "text"), ("cost_gbp", "money")],
    "travel_doc": [("status", travel.DOC_STATUSES)],
}
LABELS = {"dep_at": "Departs (local)", "arr_at": "Arrives (local)", "check_in_at": "Check-in", "check_out_at": "Check-out",
          "pickup_at": "Pickup (local)", "budget_gbp": "Budget £", "cost_gbp": "Cost £", "delay_minutes": "Delay (min)",
          "distance_km": "Distance to venue (km, blank if TBC)", "travel_min_to_venue": "Minutes to venue (blank if TBC)",
          "est_minutes": "Est. duration (min)", "tz": "Timezone", "dep_tz": "Departure timezone",
          "arr_tz": "Arrival timezone", "flight_no": "Flight number"}


def travel_fields(prefix: str, kind: str, row: dict | None) -> dict:
    """Widgets for a travel item; returns column -> value (ISO strings for date/times)."""
    out: dict = {}
    spec = SPECS[kind]
    cols = st.columns(3)
    for i, (field, typ) in enumerate(spec):
        col = cols[i % 3]
        label = LABELS.get(field, field.replace("_", " ").capitalize())
        cur = (row or {}).get(field)
        key = f"{prefix}_{field}"
        if isinstance(typ, (list, tuple)):
            opts = list(typ) + ([cur] if cur and cur not in typ else [])
            out[field] = col.selectbox(label, opts, index=opts.index(cur) if cur in opts else 0, key=key)
        elif typ == "dt":
            dt = travel.parse(cur) if cur else datetime.combine(date.fromisoformat(ev["start_date"]), time(9, 0))
            c1, c2 = col.columns(2)
            d = c1.date_input(label, value=dt.date(), key=key + "_d", format="YYYY-MM-DD")
            t = c2.time_input("time", value=dt.time(), step=300, key=key + "_t")
            out[field] = datetime.combine(d, t).isoformat(timespec="seconds")
        elif typ == "date":
            d = col.date_input(label, value=date.fromisoformat(cur) if cur else date.fromisoformat(ev["start_date"]),
                               key=key, format="YYYY-MM-DD")
            out[field] = d.isoformat()
        elif typ == "money":
            out[field] = float(col.number_input(label, value=float(cur or 0), min_value=0.0, step=10.0, key=key))
        elif typ == "int":
            v = col.number_input(label, value=int(cur) if cur is not None else None, min_value=0, step=5, key=key)
            out[field] = int(v) if v is not None else None
        elif typ == "float":
            v = col.number_input(label, value=float(cur) if cur is not None else None, min_value=0.0, step=0.1,
                                 key=key)
            out[field] = float(v) if v is not None else None
        else:
            out[field] = col.text_input(label, value=cur or "", key=key).strip()
    return out


def render_delay_impact(f: dict) -> None:
    """Meetings a delayed flight now clashes with, each with move / reassign suggestions."""
    impact = travel.delay_impact(ev["id"], ev, f["id"])
    st.markdown(f"**{ui.esc(f['role'])} · {ui.esc(travel.flight_label(f))}** delayed **{f['delay_minutes']} min**: "
                f"now lands {f['arr_eff']:%a %H:%M} local (ready for meetings from "
                f"{f['arr_ev'] + timedelta(minutes=LANDING_BUFFER_MIN):%H:%M} {ev['city']} time)",
                unsafe_allow_html=True)
    if not impact:
        st.success("No meetings clash with the new times ✓")
        return
    mlookup = {m["id"]: m for m in meetings}
    for r in impact:
        m = mlookup[r.meeting.id]
        with st.container(border=True):
            st.markdown(f"⛔ **{ui.esc(m['account'])}** {m['start']:%a %H:%M}–{m['end']:%H:%M} · "
                        f"{ui.esc(m['people_roles'])} · {ui.status_pill(m['status'])}", unsafe_allow_html=True)
            for c in r.clashes:
                st.caption(f"{pmap.get(c.person_id, {}).get('role', '?')}: {c.message}")
            btns = st.columns(1 + len(r.reassign))
            if r.move_to:
                if btns[0].button(f"↻ Move to {r.move_to.start:%H:%M}–{r.move_to.end:%H:%M}",
                                  key=f"mv_{f['id']}_{m['id']}", width="stretch"):
                    changed = data.update_meeting(m["id"], {"start_at": r.move_to.start.isoformat(timespec="seconds"),
                                                            "end_at": r.move_to.end.isoformat(timespec="seconds")}, WHO)
                    st.session_state["ops_flash"] = "Moved: " + "; ".join(changed)
                    st.rerun()
            else:
                btns[0].caption("No free slot left that day for everyone on it.")
            for i, (blocked, alt) in enumerate(r.reassign, start=1):
                if btns[i].button(f"⇄ {pmap[blocked]['role']} → {pmap[alt]['role']}", key=f"ra_{f['id']}_{m['id']}_{alt}",
                                  width="stretch"):
                    new_people = sorted((set(m["people"]) - {blocked}) | {alt})
                    owner = alt if m["owner_id"] == blocked else m["owner_id"]
                    changed = data.update_meeting(m["id"], {"owner_id": owner}, WHO, people_ids=new_people)
                    st.session_state["ops_flash"] = "Reassigned: " + "; ".join(changed)
                    st.rerun()


with tab_travel:
    all_fl = travel.flights(ev["id"], ev)
    delayed = [f for f in all_fl if f["status"] == "delayed"]
    st.markdown("##### ✈️ Delayed flights → meetings to move or reassign")
    if delayed:
        for f in delayed:
            render_delay_impact(f)
    else:
        st.caption("No delayed flights. Mark one below to see which meetings it hits.")

    st.markdown("##### Edit travel")
    trips = travel.trips(ev["id"])
    if not trips:
        st.info("No trips for this event.")
    else:
        t1, t2 = st.columns([1, 2])
        trip = t1.selectbox("Traveller", trips, format_func=lambda t: f"{t['role']} · {t['person_name']}",
                            key="tr_trip")
        pid = trip["person_id"]
        options = [("trip", trip["id"], f"🧳 Trip · {trip['status']} · budget £{trip['budget_gbp']:,.0f}")]
        options += [("flight", f["id"], f"✈ {travel.flight_label(f)} · {f['direction']} · {f['status']}")
                    for f in all_fl if f["person_id"] == pid]
        options += [("hotel", h["id"], f"🏨 {h['name']} · {h['status']}")
                    for h in travel.hotels(ev["id"]) if h["person_id"] == pid]
        options += [("transfer", x["id"], f"🚗 {x['type']} {x['pickup_at'][5:16].replace('T', ' ')} · {x['status']}")
                    for x in travel.transfers(ev["id"]) if x["person_id"] == pid]
        options += [("travel_doc", d["id"], f"🛂 {d['item']} · {d['status']}")
                    for d in travel.docs(ev["id"]) if d["person_id"] == pid]
        pick = t2.selectbox("Item", options, format_func=lambda o: o[2], key=f"tr_item_{pid}")
        kind, item_id, _ = pick
        table = travel.TABLE[kind]
        row = data.query_one(f"SELECT * FROM {table} WHERE id=?", [item_id])
        with st.container(border=True):
            vals = travel_fields(f"tr_{kind}_{item_id}", kind, row)
            c1, c2 = st.columns([1, 2])
            if c1.button("💾 Save travel changes", type="primary", key=f"tr_save_{kind}_{item_id}", width="stretch"):
                try:
                    changed = travel.update_item(kind, item_id, vals, WHO)
                    msg = ("Saved: " + "; ".join(changed)) if changed else "No changes to save."
                    if kind == "flight" and vals.get("status") == "delayed":
                        n = len(travel.delay_impact(ev["id"], ev, item_id))
                        msg += f" · {n} meeting{'s' if n != 1 else ''} now clash (see Delayed flights above)."
                    st.session_state["ops_flash"] = msg
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
            if kind == "flight":
                with c2.popover("⏱ Quick delay", width="stretch"):
                    mins = st.number_input("Delay (minutes, 0 clears it)", min_value=0, step=15,
                                           value=int(row["delay_minutes"] or 0), key=f"qd_{item_id}")
                    if st.button("Apply delay", type="primary", key=f"qd_btn_{item_id}"):
                        changed = travel.set_flight_delay(item_id, int(mins), WHO)
                        n = len(travel.delay_impact(ev["id"], ev, item_id))
                        st.session_state["ops_flash"] = (("; ".join(changed) or "No change") +
                                                         f" · {n} meeting{'s' if n != 1 else ''} affected.")
                        st.rerun()

        with st.expander("➕ Add a flight, hotel or transfer for this traveller"):
            new_kind = st.segmented_control("Type", ["flight", "hotel", "transfer"], default="transfer",
                                            key="tr_new_kind") or "transfer"
            new_vals = travel_fields(f"trnew_{new_kind}_{pid}", new_kind, None)
            if st.button("➕ Add", key=f"tr_add_{new_kind}_{pid}"):
                try:
                    travel.create_item(new_kind, trip["id"], new_vals, WHO)
                    st.session_state["ops_flash"] = f"Added {new_kind} for {trip['role']}."
                    st.rerun()
                except (ValueError, KeyError) as exc:
                    st.error(f"Couldn't add: {exc}")

# ---- change log
with tab_log:
    log = data.change_log(ev["id"])
    if not log:
        st.caption("No changes recorded yet.")
    else:
        df = pd.DataFrame(log)
        df["When (London)"] = df["ts"].map(lambda t: f"{clock.utc_iso_to_local(t, clock.LONDON):%d %b %H:%M:%S}")
        df = df.rename(columns={"who": "Who", "action": "Action", "field": "Field", "old_value": "Old value",
                                "new_value": "New value", "summary": "Summary"})
        st.dataframe(df[["When (London)", "Who", "Action", "Summary", "Field", "Old value", "New value"]],
                     hide_index=True, width="stretch")
        st.download_button("⬇️ Export change log (CSV)", df.to_csv(index=False), "change_log.csv", "text/csv")
