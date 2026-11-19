"""Travel logistics: queries, timezone conversion, privacy masking, readiness, budget, red flags and
logged writes. Every change to a travel item is written to change_log (so it shows in the
"changes since you last looked" banner), exactly like meeting changes.

Storage convention: naive local ISO time + IANA timezone per place (see db/schema.sql).
Scheduling works in event-local naive time, so everything is converted to the event timezone here.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from db.database import connect, query, query_one
from services import clock
from services.scheduling import (ACTIVE_STATUSES, Clash, Rebook, Slot, TravelFlag, TravelItem, check_travel,
                                 suggest_rebook, travel_flags, LONG_HAUL_MIN)

TRIP_STATUSES = ("planned", "booked", "confirmed", "travelling", "done")
FLIGHT_STATUSES = ("booked", "checked in", "delayed", "cancelled", "landed")
BOOKING_STATUSES = ("not booked", "booked", "confirmed")
DOC_STATUSES = ("done", "pending", "not needed")
DIRECTIONS = ("outbound", "return", "internal")
TRANSFER_TYPES = ("airport pickup", "airport drop-off", "venue shuttle", "car to Fujairah", "car from Fujairah")
TRAVEL_CLASH_KINDS = frozenset({"landing", "departure", "transfer", "jetlag"})
KIND_ICON = {"flight": "✈", "hotel": "🏨", "transfer": "🚗"}

# Editable fields per table (whitelist: anything else is ignored). Keys are column names.
FIELDS = {
    "trip": ["outbound_date", "return_date", "status", "budget_gbp", "notes"],
    "flight": ["direction", "airline", "flight_no", "dep_airport", "dep_at", "dep_tz", "dep_terminal", "arr_airport",
               "arr_at", "arr_tz", "arr_terminal", "booking_ref", "seat", "cost_gbp", "status", "delay_minutes"],
    "hotel": ["name", "address", "tz", "check_in_at", "check_out_at", "booking_ref", "distance_km",
              "travel_min_to_venue", "phone", "cost_gbp", "status"],
    "transfer": ["type", "pickup_at", "tz", "pickup_place", "dropoff_place", "provider", "driver_contact",
                 "est_minutes", "booking_ref", "cost_gbp", "status"],
    "travel_doc": ["status"],
}
TABLE = {"trip": "trips", "flight": "flights", "hotel": "hotels", "transfer": "transfers", "travel_doc": "travel_docs"}
REQUIRED = {
    "flight": ["direction", "airline", "flight_no", "dep_airport", "dep_at", "dep_tz", "arr_airport", "arr_at", "arr_tz"],
    "hotel": ["name", "tz", "check_in_at", "check_out_at"],
    "transfer": ["type", "pickup_at", "tz", "pickup_place", "dropoff_place", "est_minutes"],
}
SENSITIVE = {"booking_ref"}           # never written in clear to change_log (it's visible to everyone)


def parse(ts: str | None) -> datetime | None:
    return datetime.fromisoformat(ts) if ts else None


def to_tz(naive: datetime, from_tz: str, to_tz: str) -> datetime:
    return clock.local_to_tz(naive, from_tz, to_tz) if from_tz != to_tz else naive


# ----------------------------------------------------------------------------- privacy
def can_see_ref(viewer: dict | None, person_id: int) -> bool:
    """Booking references: visible to the traveller and London Ops only."""
    return bool(viewer) and (bool(viewer.get("can_edit")) or viewer.get("id") == person_id)


def mask(ref: str | None, visible: bool) -> str:
    if not ref:
        return "—"
    return ref if visible else "•" * max(len(ref) - 2, 3) + ref[-2:]


# ----------------------------------------------------------------------------- reads
def trips(event_id: int) -> list[dict]:
    return query("""SELECT t.*, p.name AS person_name, p.role, p.colour, p.key AS person_key
                    FROM trips t JOIN people p ON p.id=t.person_id WHERE t.event_id=? ORDER BY p.id""", [event_id])


def trip_for(person_id: int, event_id: int) -> dict | None:
    return query_one("SELECT * FROM trips WHERE person_id=? AND event_id=?", [person_id, event_id])


def _rows(table: str, event_id: int, order: str) -> list[dict]:
    return query(f"""SELECT x.*, t.person_id, t.event_id, p.role FROM {table} x JOIN trips t ON t.id=x.trip_id
                     JOIN people p ON p.id=t.person_id WHERE t.event_id=? ORDER BY {order}""", [event_id])


def flights(event_id: int, ev: dict | None = None) -> list[dict]:
    rows = _rows("flights", event_id, "t.person_id, x.dep_at")
    for r in rows:
        _flight_times(r, ev)
    return rows


def hotels(event_id: int, ev: dict | None = None) -> list[dict]:
    rows = _rows("hotels", event_id, "t.person_id, x.check_in_at")
    for r in rows:
        r["check_in"], r["check_out"] = parse(r["check_in_at"]), parse(r["check_out_at"])
        if ev:
            r["check_in_ev"] = to_tz(r["check_in"], r["tz"], ev["timezone"])
            r["check_out_ev"] = to_tz(r["check_out"], r["tz"], ev["timezone"])
    return rows


def transfers(event_id: int, ev: dict | None = None) -> list[dict]:
    rows = _rows("transfers", event_id, "t.person_id, x.pickup_at")
    for r in rows:
        r["pickup"] = parse(r["pickup_at"])
        r["end"] = r["pickup"] + timedelta(minutes=r["est_minutes"])
        if ev:
            r["start_ev"] = to_tz(r["pickup"], r["tz"], ev["timezone"])
            r["end_ev"] = r["start_ev"] + timedelta(minutes=r["est_minutes"])
    return rows


def docs(event_id: int) -> list[dict]:
    return query("""SELECT d.*, p.role FROM travel_docs d JOIN people p ON p.id=d.person_id
                    WHERE d.event_id=? ORDER BY d.person_id, d.item""", [event_id])


def _flight_times(r: dict, ev: dict | None) -> None:
    """Scheduled and effective (delayed) times, local to each airport and in the event timezone."""
    delay = timedelta(minutes=r.get("delay_minutes") or 0)
    r["dep"], r["arr"] = parse(r["dep_at"]), parse(r["arr_at"])
    r["dep_eff"], r["arr_eff"] = r["dep"] + delay, r["arr"] + delay
    dep_utc = r["dep"].replace(tzinfo=ZoneInfo(r["dep_tz"]))
    arr_utc = r["arr"].replace(tzinfo=ZoneInfo(r["arr_tz"]))
    r["duration_min"] = int((arr_utc - dep_utc).total_seconds() // 60)
    r["long_haul"] = r["duration_min"] >= LONG_HAUL_MIN
    if ev:
        r["dep_ev"] = to_tz(r["dep_eff"], r["dep_tz"], ev["timezone"])
        r["arr_ev"] = to_tz(r["arr_eff"], r["arr_tz"], ev["timezone"])


def flight_label(f: dict) -> str:
    return f"{f['flight_no']} {f['dep_airport']}→{f['arr_airport']}"


def transfer_label(t: dict) -> str:
    return t["type"][0].upper() + t["type"][1:]


def travel_items(event_id: int, ev: dict) -> list[TravelItem]:
    """All travel for an event as scheduler items, in event-local time."""
    out: list[TravelItem] = []
    for f in flights(event_id, ev):
        out.append(TravelItem(f["id"], "flight", f["person_id"], f["dep_ev"], f["arr_ev"], flight_label(f),
                              f["status"], f["direction"], f["long_haul"]))
    for h in hotels(event_id, ev):
        out.append(TravelItem(h["id"], "hotel", h["person_id"], h["check_in_ev"], h["check_out_ev"], h["name"],
                              h["status"]))
    for t in transfers(event_id, ev):
        out.append(TravelItem(t["id"], "transfer", t["person_id"], t["start_ev"], t["end_ev"], transfer_label(t),
                              t["status"], t["type"]))
    return out


def diary_days(ev: dict) -> list[str]:
    """Event days plus travel days (arrivals before, departures after), in event-local dates."""
    start, end = date.fromisoformat(ev["start_date"]), date.fromisoformat(ev["end_date"])
    for t in travel_items(ev["id"], ev):
        if t.kind == "hotel":
            continue
        start, end = min(start, t.start.date(), t.end.date()), max(end, t.start.date())
    # Return flights land the next day in London; only include days with something on them in event time.
    return [(start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]


# ----------------------------------------------------------------------------- per-day blocks (diary, My Day)
def day_blocks(event_id: int, ev: dict, day: str, person_id: int | None = None) -> list[dict]:
    """Travel blocks touching an event-local day: flights, hotel check-in / check-out, transfers.

    Each block: kind, person_id, start, end (event-local), label, status, detail, id.
    """
    d = date.fromisoformat(day)
    lo, hi = datetime.combine(d, datetime.min.time()), datetime.combine(d + timedelta(days=1), datetime.min.time())
    out: list[dict] = []
    for f in flights(event_id, ev):
        if f["dep_ev"] < hi and f["arr_ev"] > lo:
            delayed = f" · delayed {f['delay_minutes']} min" if f["delay_minutes"] else ""
            out.append(dict(kind="flight", id=f["id"], person_id=f["person_id"], start=max(f["dep_ev"], lo),
                            end=min(f["arr_ev"], hi), label=f"✈ {flight_label(f)}", status=f["status"],
                            detail=f"{f['airline']} · dep {f['dep_eff']:%H:%M} {f['dep_airport']} "
                                   f"→ arr {f['arr_eff']:%H:%M} {f['arr_airport']} (local){delayed}", raw=f))
    for h in hotels(event_id, ev):
        for what, t in (("Check-in", h["check_in_ev"]), ("Check-out", h["check_out_ev"])):
            if lo <= t < hi:
                out.append(dict(kind="hotel", id=h["id"], person_id=h["person_id"], start=t,
                                end=t + timedelta(minutes=30), label=f"🏨 {what}", status=h["status"],
                                detail=f"{what} · {h['name']}", raw=h))
    for t in transfers(event_id, ev):
        if t["start_ev"] < hi and t["end_ev"] > lo:
            out.append(dict(kind="transfer", id=t["id"], person_id=t["person_id"], start=t["start_ev"],
                            end=t["end_ev"], label=f"🚗 {transfer_label(t)}", status=t["status"],
                            detail=f"{t['pickup_place']} → {t['dropoff_place']} · {t['est_minutes']} min · "
                                   f"{t['provider'] or 'provider TBC'}", raw=t))
    if person_id is not None:
        out = [b for b in out if b["person_id"] == person_id]
    return sorted(out, key=lambda b: (b["start"], b["kind"]))


# ----------------------------------------------------------------------------- costs, readiness, flags
def trip_cost(trip_id: int) -> float:
    total = 0.0
    with connect() as conn:
        for table, cond in (("flights", "status != 'cancelled'"), ("hotels", "1=1"), ("transfers", "1=1")):
            total += conn.execute(f"SELECT COALESCE(SUM(cost_gbp),0) FROM {table} WHERE trip_id=? AND {cond}",
                                  [trip_id]).fetchone()[0]
    return float(total)


def budget_rows(event_id: int | None = None) -> list[dict]:
    """Budget vs actual per trip (one event, or all events when event_id is None)."""
    sql = """SELECT t.id, t.person_id, t.event_id, t.budget_gbp, p.role, p.name, p.colour, e.name AS event_name, e.code
             FROM trips t JOIN people p ON p.id=t.person_id JOIN events e ON e.id=t.event_id"""
    rows = query(sql + (" WHERE t.event_id=?" if event_id else "") + " ORDER BY e.start_date, p.id",
                 [event_id] if event_id else [])
    for r in rows:
        r["actual_gbp"] = trip_cost(r["id"])
        r["variance_gbp"] = r["actual_gbp"] - r["budget_gbp"]
        r["pct"] = (r["actual_gbp"] / r["budget_gbp"] * 100) if r["budget_gbp"] else 0.0
        r["over"] = r["variance_gbp"] > 0
    return rows


def readiness(event_id: int, person_id: int) -> tuple[int, int]:
    """(ready, total) items: flights booked or later (not cancelled), hotels/transfers booked or confirmed,
    documents done ('not needed' doesn't count)."""
    ready = total = 0
    for f in flights(event_id):
        if f["person_id"] == person_id:
            total += 1
            ready += f["status"] != "cancelled"
    for rows in (hotels(event_id), transfers(event_id)):
        for r in rows:
            if r["person_id"] == person_id:
                total += 1
                ready += r["status"] in ("booked", "confirmed")
    for d in docs(event_id):
        if d["person_id"] == person_id and d["status"] != "not needed":
            total += 1
            ready += d["status"] == "done"
    return ready, total


def meeting_travel_clashes(event_id: int, ev: dict) -> list[Clash]:
    """Travel-rule clashes for every active meeting at the event."""
    from services import data
    travel = travel_items(event_id, ev)
    out: list[Clash] = []
    for item in data.to_items(data.meetings(event_id)):
        out.extend(check_travel(item, travel))
    return out


def red_flags(event_id: int, ev: dict) -> list[dict]:
    """Everything wrong with travel for this event, worst first.

    Each flag: severity (error/warning), person_id, role, kind, message.
    """
    from services import data
    roles = {p["id"]: p["role"] for p in data.people()}
    travel = travel_items(event_id, ev)
    flags: list[dict] = []

    def add(sev, pid, kind, msg):
        flags.append(dict(severity=sev, person_id=pid, role=roles.get(pid, "?"), kind=kind, message=msg))

    for tr in trips(event_id):
        for f in travel_flags(tr["person_id"], travel):
            add(f.severity, f.person_id, f.kind, f.message)
    for f in flights(event_id, ev):
        if f["status"] == "delayed":
            add("error", f["person_id"], "delayed",
                f"{flight_label(f)} delayed {f['delay_minutes']} min: now lands {f['arr_eff']:%a %H:%M} local")
        elif f["status"] == "cancelled":
            add("error", f["person_id"], "cancelled", f"{flight_label(f)} is cancelled: rebook")
    for b in budget_rows(event_id):
        if b["over"]:
            add("warning", b["person_id"], "over budget",
                f"Over budget by £{b['variance_gbp']:,.0f} (£{b['actual_gbp']:,.0f} vs £{b['budget_gbp']:,.0f}, "
                f"{b['pct']:.0f}%)")
    for d in docs(event_id):
        if d["status"] == "pending":
            add("warning", d["person_id"], "document", f"Document check pending: {d['item']}")
    meetings = {m["id"]: m for m in data.meetings(event_id)}
    for c in meeting_travel_clashes(event_id, ev):
        m = meetings.get(c.meeting_id)
        if m:
            add(c.severity, c.person_id, f"meeting · {c.kind}", f"{m['account']} ({m['start']:%a %H:%M}): {c.message}")
    order = {"error": 0, "warning": 1}
    return sorted(flags, key=lambda f: (order.get(f["severity"], 2), f["person_id"]))


# ----------------------------------------------------------------------------- delay impact
def delay_impact(event_id: int, ev: dict, flight_id: int) -> list[Rebook]:
    """Meetings the given flight now clashes with, each with a move and a reassignment suggestion."""
    from services import data
    f = next((x for x in flights(event_id, ev) if x["id"] == flight_id), None)
    if not f:
        return []
    travel = travel_items(event_id, ev)
    rows = data.meetings(event_id)
    items = data.to_items(rows)
    sessions = data.to_session_items(data.sessions(event_id))
    colleagues = [p["id"] for p in data.people(attendees_only=True)]
    out: list[Rebook] = []
    for it in items:
        if f["person_id"] not in it.people or it.status not in ACTIVE_STATUSES or it.status == "done":
            continue
        hits = [c for c in check_travel(it, travel)
                if c.other_id == flight_id and c.kind in ("landing", "departure") and c.person_id == f["person_id"]]
        if not hits:
            continue
        day = it.start.date()
        window = Slot(datetime.combine(day, datetime.min.time()).replace(hour=8),
                      datetime.combine(day, datetime.min.time()).replace(hour=20))
        out.append(suggest_rebook(it, items, sessions, travel, colleagues, window))
    return out


# ----------------------------------------------------------------------------- writes (all logged)
def _event_of(kind: str, item_id: int) -> tuple[int | None, dict | None]:
    if kind == "trip":
        row = query_one("SELECT t.*, p.role FROM trips t JOIN people p ON p.id=t.person_id WHERE t.id=?", [item_id])
        return (row["event_id"] if row else None), row
    if kind == "travel_doc":
        row = query_one("SELECT d.*, p.role FROM travel_docs d JOIN people p ON p.id=d.person_id WHERE d.id=?", [item_id])
        return (row["event_id"] if row else None), row
    row = query_one(f"""SELECT x.*, t.event_id, t.person_id, p.role FROM {TABLE[kind]} x
                        JOIN trips t ON t.id=x.trip_id JOIN people p ON p.id=t.person_id WHERE x.id=?""", [item_id])
    return (row["event_id"] if row else None), row


def describe(kind: str, row: dict) -> str:
    """Short human name for a travel item, used in change_log summaries."""
    who = row.get("role", "")
    if kind == "flight":
        return f"{who} flight {row['flight_no']} {row['dep_airport']}→{row['arr_airport']}"
    if kind == "hotel":
        return f"{who} hotel {row['name']}"
    if kind == "transfer":
        return f"{who} {row['type']}"
    if kind == "travel_doc":
        return f"{who} document check '{row['item']}'"
    return f"{who} trip"


def _log_value(field: str, value: Any) -> str | None:
    if value in (None, ""):
        return None
    return "(hidden)" if field in SENSITIVE else str(value)


def update_item(kind: str, item_id: int, changes: dict, who: str) -> list[str]:
    """Apply whitelisted changes to a travel item; one change_log row per changed field."""
    from services.data import log_change
    event_id, before = _event_of(kind, item_id)
    if not before:
        raise ValueError(f"{kind} {item_id} not found")
    changes = {k: (None if v == "" else v) for k, v in changes.items() if k in FIELDS[kind]}
    _validate(kind, {**before, **changes})
    diff = {k: v for k, v in changes.items() if str(before.get(k) if before.get(k) is not None else "")
            != str(v if v is not None else "")}
    if not diff:
        return []
    name = describe(kind, before)
    out: list[str] = []
    with connect() as conn:
        conn.execute(f"UPDATE {TABLE[kind]} SET {', '.join(f'{k}=?' for k in diff)} WHERE id=?",
                     [*diff.values(), item_id])
        for field, new in diff.items():
            old = before.get(field)
            label = field.replace("_at", "").replace("_", " ")
            if field in SENSITIVE:
                summary = f"{name}: {label} updated"
            elif field in ("dep_at", "arr_at", "check_in_at", "check_out_at", "pickup_at") and old and new:
                summary = f"{name}: {label} {parse(str(old)):%a %d %b %H:%M} → {parse(str(new)):%a %d %b %H:%M}"
            else:
                summary = f"{name}: {label} {old if old not in (None, '') else '—'} → {new if new not in (None, '') else '—'}"
            action = "status" if field == "status" else ("move" if field.endswith("_at") else "update")
            log_change(who, event_id, kind, item_id, action, summary, field,
                       _log_value(field, old), _log_value(field, new), conn=conn)
            out.append(summary)
    return out


def set_flight_delay(flight_id: int, minutes: int, who: str) -> list[str]:
    """Mark a flight delayed by N minutes (0 clears the delay and sets it back to booked)."""
    status = "delayed" if minutes > 0 else "booked"
    return update_item("flight", flight_id, {"status": status, "delay_minutes": int(minutes)}, who)


def create_item(kind: str, trip_id: int, values: dict, who: str) -> int:
    from services.data import log_change
    if kind not in ("flight", "hotel", "transfer"):
        raise ValueError(kind)
    values = {k: (None if v == "" else v) for k, v in values.items() if k in FIELDS[kind]}
    missing = [k for k in REQUIRED[kind] if values.get(k) in (None, "")]
    if missing:
        raise ValueError("Missing: " + ", ".join(k.replace("_", " ") for k in missing))
    _validate(kind, values)
    trip = query_one("SELECT t.*, p.role FROM trips t JOIN people p ON p.id=t.person_id WHERE t.id=?", [trip_id])
    if not trip:
        raise ValueError(f"trip {trip_id} not found")
    cols = ["trip_id", *values]
    with connect() as conn:
        cur = conn.execute(f"INSERT INTO {TABLE[kind]} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                           [trip_id, *values.values()])
        new_id = cur.lastrowid
        name = describe(kind, {**values, "role": trip["role"]})
        log_change(who, trip["event_id"], kind, new_id, "create", f"Added {name}", None, None,
                   values.get("status"), conn=conn)
    return new_id


def _validate(kind: str, row: dict) -> None:
    """Raise ValueError for impossible values (keeps bad data out of the clash checker)."""
    status = row.get("status")
    allowed = {"trip": TRIP_STATUSES, "flight": FLIGHT_STATUSES, "hotel": BOOKING_STATUSES,
               "transfer": BOOKING_STATUSES, "travel_doc": DOC_STATUSES}[kind]
    if status is not None and status not in allowed:
        raise ValueError(f"Unknown status '{status}' for {kind}")
    if kind == "flight":
        for tzf in ("dep_tz", "arr_tz"):
            if row.get(tzf):
                ZoneInfo(row[tzf])
        if row.get("dep_at") and row.get("arr_at") and row.get("dep_tz") and row.get("arr_tz"):
            dep = parse(row["dep_at"]).replace(tzinfo=ZoneInfo(row["dep_tz"]))
            arr = parse(row["arr_at"]).replace(tzinfo=ZoneInfo(row["arr_tz"]))
            if arr <= dep:
                raise ValueError("Arrival must be after departure")
        if (row.get("delay_minutes") or 0) < 0:
            raise ValueError("Delay can't be negative")
    if kind == "hotel" and row.get("check_in_at") and row.get("check_out_at"):
        if parse(row["check_out_at"]) <= parse(row["check_in_at"]):
            raise ValueError("Check-out must be after check-in")
    if kind == "transfer" and row.get("est_minutes") is not None and int(row["est_minutes"]) <= 0:
        raise ValueError("Estimated duration must be positive")
    if kind == "transfer" and row.get("type") and row["type"] not in TRANSFER_TYPES:
        raise ValueError(f"Unknown transfer type '{row['type']}'")
    if kind == "flight" and row.get("direction") and row["direction"] not in DIRECTIONS:
        raise ValueError(f"Unknown direction '{row['direction']}'")


def map_link(address: str | None) -> str | None:
    if not address:
        return None
    from urllib.parse import quote_plus
    return f"https://www.google.com/maps/search/?api=1&query={quote_plus(address)}"


# ----------------------------------------------------------------------------- AI summary inputs
def summary_fields(ev: dict, person: dict) -> dict[str, str]:
    """Flat, labelled database fields for one person's trip (the ONLY facts the travel summary may use).

    Booking references are deliberately excluded. Times are event-local with London in brackets.
    """
    from services import data
    tz = ev["timezone"]

    def both(dt: datetime) -> str:
        return f"{dt:%a %d %b %H:%M} {ev['city']} time (London {clock.local_to_tz(dt, tz, clock.LONDON):%H:%M})"

    pid = person["id"]
    f: dict[str, str] = {"traveller": f"{person['role']} {person['name']}", "event.name": ev["name"],
                         "event.city": ev["city"], "event.venue": ev.get("venue") or "TBC"}
    tr = trip_for(pid, ev["id"])
    if tr:
        f["trip.status"] = tr["status"]
    for fl in [x for x in flights(ev["id"], ev) if x["person_id"] == pid]:
        k = fl["direction"]
        f[f"{k}.flight"] = f"{fl['airline']} {fl['flight_no']} {fl['dep_airport']}→{fl['arr_airport']}"
        f[f"{k}.departs"] = (f"{fl['dep_eff']:%a %d %b %H:%M} local at {fl['dep_airport']}"
                             f" terminal {fl['dep_terminal'] or 'TBC'}")
        f[f"{k}.lands"] = (f"{fl['arr_eff']:%a %d %b %H:%M} local at {fl['arr_airport']}"
                           f" terminal {fl['arr_terminal'] or 'TBC'}")
        f[f"{k}.status"] = fl["status"] + (f" by {fl['delay_minutes']} min" if fl["delay_minutes"] else "")
        if fl["seat"]:
            f[f"{k}.seat"] = fl["seat"]
    for h in [x for x in hotels(ev["id"], ev) if x["person_id"] == pid]:
        f["hotel.name"] = h["name"]
        f["hotel.address"] = h["address"] or ""
        f["hotel.check_in"] = both(h["check_in_ev"])
        f["hotel.check_out"] = both(h["check_out_ev"])
        f["hotel.to_venue"] = (f"{h['travel_min_to_venue']} min ({h['distance_km']} km)"
                               if h["travel_min_to_venue"] else "venue TBC, travel time unknown")
        f["hotel.status"] = h["status"]
    for t in [x for x in transfers(ev["id"], ev) if x["person_id"] == pid]:
        k = "arrival_transfer" if t["type"] in ("airport pickup", "car to Fujairah") else (
            "departure_transfer" if t["type"] in ("airport drop-off", "car from Fujairah") else "shuttle")
        f[f"{k}.pickup"] = f"{both(t['start_ev'])} at {t['pickup_place']}"
        f[f"{k}.to"] = t["dropoff_place"]
        f[f"{k}.duration"] = f"{t['est_minutes']} min (estimate)"
        f[f"{k}.provider"] = t["provider"] or "not recorded"
        f[f"{k}.driver"] = t["driver_contact"] or "not recorded"
        f[f"{k}.status"] = t["status"]
    mine = [m for m in data.meetings(ev["id"]) if pid in m["people"] and m["status"] != "cancelled"]
    for i, m in enumerate(mine[:4]):
        f[f"meetings.m{i + 1}"] = f"{both(m['start'])}: {m['account']} at {m['location']} ({m['status']})"
    f["meetings.count"] = str(len(mine))
    flags = [x for x in red_flags(ev["id"], ev) if x["person_id"] == pid]
    for i, x in enumerate(flags[:6]):
        f[f"alerts.a{i + 1}"] = f"{x['severity']}: {x['message']}"
    if not flags:
        f["alerts.none"] = "No travel alerts"
    return f
