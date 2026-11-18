"""Shared queries and writes. Every change to a meeting is written to change_log."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from db.database import connect, execute, query, query_one, scalar
from services import clock
from services.scheduling import Item, ReserveCandidate, SessionItem

STATUS_ORDER = ["proposed", "confirmed", "moved", "done", "cancelled"]
TIER_LABEL = {1: "Tier 1 · existing client", 2: "Tier 2 · warm intro", 3: "Tier 3 · cold"}
TRACKED_FIELDS = ["account_id", "owner_id", "start_at", "end_at", "location", "status", "objective",
                  "the_ask", "next_step", "next_step_date"]


def parse(ts: str | None) -> datetime | None:
    return datetime.fromisoformat(ts) if ts else None


# ----------------------------------------------------------------------------- reference data
def events() -> list[dict]:
    return query("SELECT * FROM events ORDER BY start_date")


def event(event_id: int) -> dict:
    return query_one("SELECT * FROM events WHERE id=?", [event_id])


def event_days(ev: dict) -> list[str]:
    start, end = datetime.fromisoformat(ev["start_date"]), datetime.fromisoformat(ev["end_date"])
    return [(start + timedelta(days=i)).date().isoformat() for i in range((end - start).days + 1)]


def people(attendees_only: bool = False) -> list[dict]:
    sql = "SELECT * FROM people" + (" WHERE is_attendee=1" if attendees_only else "") + " ORDER BY id"
    return query(sql)


def person(person_id: int) -> dict | None:
    return query_one("SELECT * FROM people WHERE id=?", [person_id])


def person_by_key(key: str) -> dict | None:
    return query_one("SELECT * FROM people WHERE key=?", [key])


def accounts() -> list[dict]:
    return query("SELECT * FROM accounts ORDER BY name")


def contacts_for(account_id: int) -> list[dict]:
    return query("SELECT * FROM contacts WHERE account_id=? ORDER BY decision_maker DESC, name", [account_id])


def materials() -> list[dict]:
    return query("SELECT * FROM materials ORDER BY name")


def targets(event_id: int) -> dict:
    return query_one("SELECT * FROM targets WHERE event_id=?", [event_id]) or {
        "meetings": 0, "app_signups": 0, "trials": 0, "dm_pct": 60, "followup_24h_pct": 90}


# ----------------------------------------------------------------------------- meetings
MEETINGS_SQL = """
SELECT m.*, a.name AS account, a.tier, a.type AS account_type, a.region,
       o.role AS owner_role, o.name AS owner_name,
       (SELECT GROUP_CONCAT(mp.person_id) FROM meeting_people mp WHERE mp.meeting_id=m.id) AS people_ids,
       (SELECT GROUP_CONCAT(p.role, ', ') FROM meeting_people mp JOIN people p ON p.id=mp.person_id
          WHERE mp.meeting_id=m.id) AS people_roles,
       (SELECT COUNT(*) FROM meeting_contacts mc JOIN contacts c ON c.id=mc.contact_id
          WHERE mc.meeting_id=m.id AND c.decision_maker=1) AS dm_planned
FROM meetings m
JOIN accounts a ON a.id=m.account_id
JOIN people o ON o.id=m.owner_id
WHERE m.event_id=?
ORDER BY m.start_at
"""


def meetings(event_id: int) -> list[dict]:
    rows = query(MEETINGS_SQL, [event_id])
    for r in rows:
        r["people"] = [int(x) for x in (r["people_ids"] or "").split(",") if x]
        r["start"] = parse(r["start_at"])
        r["end"] = parse(r["end_at"])
    return rows


def meetings_df(event_id: int) -> pd.DataFrame:
    return pd.DataFrame(meetings(event_id))


def meeting(meeting_id: int) -> dict | None:
    row = query_one(MEETINGS_SQL.replace("WHERE m.event_id=?", "WHERE m.id=?"), [meeting_id])
    if row:
        row["people"] = [int(x) for x in (row["people_ids"] or "").split(",") if x]
        row["start"], row["end"] = parse(row["start_at"]), parse(row["end_at"])
    return row


def meeting_label(m: dict, with_day: bool = True) -> str:
    fmt = "%a %d %b %H:%M" if with_day else "%H:%M"
    return f"{m['start']:{fmt}} · {m['account']} ({m.get('people_roles') or m['owner_role']}) · {m['status']}"


def sessions(event_id: int) -> list[dict]:
    rows = query("""
        SELECT s.*, (SELECT GROUP_CONCAT(sa.person_id) FROM session_attendees sa WHERE sa.session_id=s.id) AS att
        FROM sessions s WHERE s.event_id=? ORDER BY s.start_at""", [event_id])
    for r in rows:
        r["attendees"] = [int(x) for x in (r["att"] or "").split(",") if x]
        r["start"], r["end"] = parse(r["start_at"]), parse(r["end_at"])
    return rows


def to_items(rows: list[dict]) -> list[Item]:
    return [Item(r["id"], r["start"], r["end"], frozenset(r["people"]), r["location"],
                 f"{r['account']} {r['start']:%a %H:%M}", r["status"]) for r in rows]


def to_session_items(rows: list[dict]) -> list[SessionItem]:
    return [SessionItem(r["id"], r["start"], r["end"], r["title"], frozenset(r["attendees"])) for r in rows]


def meeting_context(meeting_id: int) -> dict:
    """Everything the brief page and the LLM need about a meeting — straight from the DB."""
    m = meeting(meeting_id)
    if not m:
        return {}
    acc = query_one("SELECT * FROM accounts WHERE id=?", [m["account_id"]])
    contacts = query("""
        SELECT c.*, EXISTS(SELECT 1 FROM meeting_contacts mc WHERE mc.meeting_id=? AND mc.contact_id=c.id) AS attending
        FROM contacts c WHERE c.account_id=? ORDER BY attending DESC, decision_maker DESC, name""",
                     [meeting_id, m["account_id"]])
    notes = query("""SELECT n.*, p.role AS author FROM notes n LEFT JOIN people p ON p.id=n.author_id
                     WHERE n.account_id=? ORDER BY n.note_date DESC""", [m["account_id"]])
    mats = query("""SELECT mt.* FROM materials mt JOIN meeting_materials mm ON mm.material_id=mt.id
                    WHERE mm.meeting_id=? ORDER BY mt.name""", [meeting_id])
    prior = query("""SELECT d.*, m2.start_at, e.code AS event_code FROM debriefs d
                     JOIN meetings m2 ON m2.id=d.meeting_id JOIN events e ON e.id=m2.event_id
                     WHERE m2.account_id=? AND m2.id != ? ORDER BY m2.start_at DESC""",
                  [m["account_id"], meeting_id])
    attendees = query("""SELECT p.* FROM people p JOIN meeting_people mp ON mp.person_id=p.id
                         WHERE mp.meeting_id=? ORDER BY p.id""", [meeting_id])
    ev = event(m["event_id"])
    return {"meeting": m, "account": acc, "contacts": contacts, "notes": notes, "materials": mats,
            "prior_debriefs": prior, "attendees": attendees, "owner": person(m["owner_id"]), "event": ev}


# ----------------------------------------------------------------------------- change log
def log_change(who: str, event_id: int | None, entity: str, entity_id: int | None, action: str,
               summary: str, field: str | None = None, old: Any = None, new: Any = None, conn=None) -> None:
    sql = ("INSERT INTO change_log (ts, who, event_id, entity, entity_id, action, field, old_value, new_value, summary)"
           " VALUES (?,?,?,?,?,?,?,?,?,?)")
    params = (clock.real_utc_iso(), who, event_id, entity, entity_id, action, field,
              None if old is None else str(old), None if new is None else str(new), summary)
    if conn is not None:
        conn.execute(sql, params)
    else:
        execute(sql, params)


def change_log(event_id: int, limit: int = 200) -> list[dict]:
    return query("SELECT * FROM change_log WHERE event_id=? ORDER BY id DESC LIMIT ?", [event_id, limit])


def latest_change_id() -> int:
    return scalar("SELECT COALESCE(MAX(id),0) FROM change_log") or 0


def unseen_changes(person_id: int, event_id: int) -> list[dict]:
    seen = scalar("SELECT last_seen_id FROM viewer_state WHERE person_id=?", [person_id]) or 0
    return query("SELECT * FROM change_log WHERE event_id=? AND id>? ORDER BY id DESC", [event_id, seen])


def mark_seen(person_id: int) -> None:
    execute("INSERT INTO viewer_state (person_id, last_seen_id) VALUES (?, ?) "
            "ON CONFLICT(person_id) DO UPDATE SET last_seen_id=excluded.last_seen_id",
            [person_id, latest_change_id()])


# ----------------------------------------------------------------------------- meeting writes
def _fmt_value(field: str, value: Any) -> str:
    if value in (None, ""):
        return "—"
    if field in ("start_at", "end_at"):
        return f"{parse(value):%a %d %b %H:%M}"
    if field == "owner_id":
        p = person(int(value))
        return p["role"] if p else str(value)
    if field == "account_id":
        a = query_one("SELECT name FROM accounts WHERE id=?", [value])
        return a["name"] if a else str(value)
    return str(value)


def create_meeting(event_id: int, data: dict, people_ids: list[int], contact_ids: list[int],
                   material_ids: list[int], who: str) -> int:
    ts = clock.real_utc_iso()
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO meetings (event_id, account_id, owner_id, start_at, end_at, location, status, objective,"
            " the_ask, next_step, next_step_date, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (event_id, data["account_id"], data["owner_id"], data["start_at"], data["end_at"], data.get("location"),
             data.get("status", "proposed"), data.get("objective"), data.get("the_ask"), data.get("next_step"),
             data.get("next_step_date"), ts, ts))
        mid = cur.lastrowid
        _replace_links(conn, mid, people_ids, contact_ids, material_ids)
        acc = conn.execute("SELECT name FROM accounts WHERE id=?", [data["account_id"]]).fetchone()[0]
        roles = ", ".join(r[0] for r in conn.execute(
            f"SELECT role FROM people WHERE id IN ({','.join('?' * len(people_ids))})", people_ids)) if people_ids else ""
        log_change(who, event_id, "meeting", mid, "create",
                   f"New {data.get('status', 'proposed')} meeting: {acc} with {roles}, "
                   f"{parse(data['start_at']):%a %d %b %H:%M}", None, None, data.get("status"), conn=conn)
    return mid


def _replace_links(conn, mid: int, people_ids, contact_ids, material_ids) -> None:
    conn.execute("DELETE FROM meeting_people WHERE meeting_id=?", [mid])
    conn.execute("DELETE FROM meeting_contacts WHERE meeting_id=?", [mid])
    conn.execute("DELETE FROM meeting_materials WHERE meeting_id=?", [mid])
    conn.executemany("INSERT INTO meeting_people VALUES (?,?)", [(mid, p) for p in people_ids])
    conn.executemany("INSERT INTO meeting_contacts VALUES (?,?)", [(mid, c) for c in contact_ids])
    conn.executemany("INSERT INTO meeting_materials VALUES (?,?)", [(mid, x) for x in material_ids])


def update_meeting(meeting_id: int, changes: dict, who: str, people_ids: list[int] | None = None,
                   contact_ids: list[int] | None = None, material_ids: list[int] | None = None,
                   auto_moved: bool = True) -> list[str]:
    """Apply changes, log one change_log row per changed field. Returns the human summaries.

    If the time changes on a confirmed meeting and auto_moved is set, status becomes 'moved'.
    """
    before = query_one("SELECT * FROM meetings WHERE id=?", [meeting_id])
    if not before:
        raise ValueError(f"Meeting {meeting_id} not found")
    changes = {k: (v if v != "" else None) for k, v in changes.items() if k in TRACKED_FIELDS}
    diff = {k: v for k, v in changes.items() if str(before.get(k) or "") != str(v or "")}
    time_changed = "start_at" in diff or "end_at" in diff
    if auto_moved and time_changed and before["status"] == "confirmed" and changes.get("status", "confirmed") == "confirmed":
        diff["status"] = "moved"

    acc = _fmt_value("account_id", before["account_id"])
    summaries: list[str] = []
    old_people = {r["person_id"] for r in query("SELECT person_id FROM meeting_people WHERE meeting_id=?", [meeting_id])}
    with connect() as conn:
        if diff:
            sets = ", ".join(f"{k}=?" for k in diff) + ", updated_at=?"
            conn.execute(f"UPDATE meetings SET {sets} WHERE id=?", [*diff.values(), clock.real_utc_iso(), meeting_id])
        for field, new in diff.items():
            old = before.get(field)
            if field == "start_at":
                action = "move"
            elif field == "status" and new == "cancelled":
                action = "cancel"
            elif field == "status":
                action = "status"
            else:
                action = "update"
            label = field.replace("_at", "").replace("_id", "").replace("_", " ")
            summary = f"{acc}: {label} {_fmt_value(field, old)} → {_fmt_value(field, new)}"
            log_change(who, before["event_id"], "meeting", meeting_id, action, summary, field, old, new, conn=conn)
            summaries.append(summary)
        if people_ids is not None or contact_ids is not None or material_ids is not None:
            cur_contacts = [r[0] for r in conn.execute("SELECT contact_id FROM meeting_contacts WHERE meeting_id=?", [meeting_id])]
            cur_mats = [r[0] for r in conn.execute("SELECT material_id FROM meeting_materials WHERE meeting_id=?", [meeting_id])]
            _replace_links(conn, meeting_id,
                           people_ids if people_ids is not None else sorted(old_people),
                           contact_ids if contact_ids is not None else cur_contacts,
                           material_ids if material_ids is not None else cur_mats)
            if people_ids is not None and set(people_ids) != old_people:
                roles = lambda ids: ", ".join(sorted(person(i)["role"] for i in ids)) or "—"
                summary = f"{acc}: attendees {roles(old_people)} → {roles(people_ids)}"
                log_change(who, before["event_id"], "meeting", meeting_id, "update", summary, "attendees",
                           roles(old_people), roles(people_ids), conn=conn)
                summaries.append(summary)
    return summaries


def cancel_meeting(meeting_id: int, who: str, reason: str = "") -> None:
    before = meeting(meeting_id)
    with connect() as conn:
        conn.execute("UPDATE meetings SET status='cancelled', updated_at=? WHERE id=?", [clock.real_utc_iso(), meeting_id])
        summary = f"{before['account']} ({before['people_roles']}, {before['start']:%a %H:%M}) cancelled"
        if reason:
            summary += f" – {reason}"
        log_change(who, before["event_id"], "meeting", meeting_id, "cancel", summary, "status",
                   before["status"], "cancelled", conn=conn)


# ----------------------------------------------------------------------------- reserves
def reserve_candidates(event_id: int) -> list[ReserveCandidate]:
    rows = query("""SELECT r.*, a.name, a.tier FROM reserve_list r JOIN accounts a ON a.id=r.account_id
                    WHERE r.event_id=? ORDER BY r.priority""", [event_id])
    return [ReserveCandidate(r["account_id"], r["name"], r["priority"], r["tier"], r["preferred_owner_id"],
                             r["min_minutes"], r["note"] or "") for r in rows]


def booked_account_ids(event_id: int, after: datetime | None = None) -> set[int]:
    """Accounts with an active meeting still to come (or any active meeting if `after` is None)."""
    rows = meetings(event_id)
    return {r["account_id"] for r in rows
            if r["status"] != "cancelled" and (after is None or r["end"] >= after)}


# ----------------------------------------------------------------------------- briefs
def latest_brief(meeting_id: int) -> dict | None:
    b = query_one("SELECT * FROM briefs WHERE meeting_id=? ORDER BY id DESC LIMIT 1", [meeting_id])
    if b:
        b["sources"] = json.loads(b["sources"] or "[]")
        b["unverified"] = json.loads(b["unverified"] or "[]")
    return b


def save_brief(meeting_id: int, content: str, sources: list[str], unverified: list[str], generator: str) -> None:
    execute("INSERT INTO briefs (meeting_id, content, sources, unverified, generator, generated_at) VALUES (?,?,?,?,?,?)",
            [meeting_id, content, json.dumps(sources), json.dumps(unverified), generator, clock.real_utc_iso()])


# ----------------------------------------------------------------------------- debriefs / follow-ups
def debrief_for(meeting_id: int) -> dict | None:
    return query_one("SELECT * FROM debriefs WHERE meeting_id=? ORDER BY id DESC LIMIT 1", [meeting_id])


def save_debrief(meeting_id: int, author_id: int, who: str, form: dict, structured_notes: str, generator: str,
                 email_subject: str, email_body: str) -> int:
    """Store debrief, mark meeting done (requires next step date), create draft follow-up."""
    if not (form.get("next_step_date") and form.get("next_step")):
        raise ValueError("A meeting can't be marked done without a next step and next step date")
    m = meeting(meeting_id)
    ts = clock.business_utc_iso()
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO debriefs (meeting_id, author_id, what_happened, interest_level, objections, next_step,"
            " next_step_date, decision_maker_present, app_signup, trial_started, structured_notes, generator, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (meeting_id, author_id, form["what_happened"], form["interest_level"], form.get("objections", ""),
             form["next_step"], form["next_step_date"], int(form["decision_maker_present"]),
             int(form.get("app_signup", 0)), int(form.get("trial_started", 0)), structured_notes, generator, ts))
        did = cur.lastrowid
        conn.execute("UPDATE meetings SET status='done', next_step=?, next_step_date=?, updated_at=? WHERE id=?",
                     [form["next_step"], form["next_step_date"], clock.real_utc_iso(), meeting_id])
        conn.execute("INSERT INTO follow_ups (meeting_id, debrief_id, subject, body, status, created_at)"
                     " VALUES (?,?,?,?, 'draft', ?)", [meeting_id, did, email_subject, email_body, ts])
        log_change(who, m["event_id"], "meeting", meeting_id, "status",
                   f"{m['account']}: debrief filed, status {m['status']} → done (next step by {form['next_step_date']})",
                   "status", m["status"], "done", conn=conn)
    return did


def follow_ups(event_id: int) -> list[dict]:
    return query("""
        SELECT f.*, m.start_at, m.end_at, a.name AS account, o.role AS owner_role, m.event_id
        FROM follow_ups f JOIN meetings m ON m.id=f.meeting_id JOIN accounts a ON a.id=m.account_id
        JOIN people o ON o.id=m.owner_id WHERE m.event_id=? ORDER BY f.status, m.start_at""", [event_id])


def update_follow_up(fid: int, subject: str, body: str, who: str) -> None:
    f = query_one("SELECT f.*, m.event_id FROM follow_ups f JOIN meetings m ON m.id=f.meeting_id WHERE f.id=?", [fid])
    with connect() as conn:
        conn.execute("UPDATE follow_ups SET subject=?, body=? WHERE id=?", [subject, body, fid])
        log_change(who, f["event_id"], "follow_up", fid, "update", f"Follow-up #{fid} draft edited", conn=conn)


def set_follow_up_status(fid: int, status: str, who: str) -> None:
    f = query_one("SELECT f.*, m.event_id, a.name AS account FROM follow_ups f JOIN meetings m ON m.id=f.meeting_id"
                  " JOIN accounts a ON a.id=m.account_id WHERE f.id=?", [fid])
    ts = clock.business_utc_iso()
    with connect() as conn:
        if status == "approved":
            conn.execute("UPDATE follow_ups SET status='approved', approved_by=?, approved_at=? WHERE id=?", [who, ts, fid])
        elif status == "sent":
            conn.execute("UPDATE follow_ups SET status='sent', sent_at=?, approved_by=COALESCE(approved_by, ?),"
                         " approved_at=COALESCE(approved_at, ?) WHERE id=?", [ts, who, ts, fid])
        elif status == "draft":
            conn.execute("UPDATE follow_ups SET status='draft', approved_by=NULL, approved_at=NULL WHERE id=?", [fid])
        log_change(who, f["event_id"], "follow_up", fid, "status",
                   f"Follow-up to {f['account']}: {f['status']} → {status}", "status", f["status"], status, conn=conn)


def debriefs(event_id: int | None = None) -> pd.DataFrame:
    sql = """SELECT d.*, m.event_id, m.start_at, m.end_at, a.name AS account, a.tier, a.region, a.type AS account_type,
                    e.code AS event_code, p.role AS author
             FROM debriefs d JOIN meetings m ON m.id=d.meeting_id JOIN accounts a ON a.id=m.account_id
             JOIN events e ON e.id=m.event_id LEFT JOIN people p ON p.id=d.author_id"""
    params: list = []
    if event_id is not None:
        sql += " WHERE m.event_id=?"
        params.append(event_id)
    return pd.DataFrame(query(sql + " ORDER BY m.start_at", params))
