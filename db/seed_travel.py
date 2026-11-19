"""FICTIONAL travel logistics for the three executives (IBIA 2026 and FUJCON 2027).

Airlines, hotels, providers, phone numbers (555 ranges) and booking references are all invented.
No passport, ID, card or bank details are stored anywhere.

Seeded on a fresh database by `db.seed.seed`, and by the migration in `db.database.init_db`
when an existing database has no trips yet (existing data is left untouched).
"""
from __future__ import annotations

import sqlite3

LDN, NY, DXB = "Europe/London", "America/New_York", "Asia/Dubai"

NY_HOTEL = dict(name="Harbourline Hotel Downtown", address="120 Greenwich Quay, Lower Manhattan, New York, NY 10006",
                tz=NY, distance_km=0.3, travel_min_to_venue=5, phone="+1 212 555 0140")
FUJ_HOTEL = dict(name="Corniche Pearl Hotel", address="Corniche Road, Fujairah, United Arab Emirates",
                 tz=DXB, distance_km=None, travel_min_to_venue=None, phone="+971 9 555 0182")

# person key -> per-event plan
TRIPS = {
    "IBIA2026": {
        "ceo": dict(out="2026-11-30", ret="2026-12-03", status="travelling", budget=5000,
                    notes="Business class. Prefers aisle seats.",
                    flights=[("outbound", "Northstar Atlantic", "NS 114", "LHR", "2026-11-30T11:15", LDN, "T3",
                              "JFK", "2026-11-30T14:25", NY, "T7", "NSQ4KD", "2A", 1650, "landed", 0),
                             ("return", "Northstar Atlantic", "NS 117", "JFK", "2026-12-03T18:30", NY, "T7",
                              "LHR", "2026-12-04T06:35", LDN, "T3", "NSQ4KD", "2A", 1650, "booked", 0)],
                    hotel=("2026-11-30T16:30", "2026-12-03T14:30", "HL-58213", 1280, "confirmed"),
                    transfers=[("airport pickup", "2026-11-30T15:15", NY, "JFK Terminal 7 arrivals", NY_HOTEL["name"],
                                "Liberty Line Cars", "Marco D. +1 917 555 0123", 60, "LL-2207", 95, "confirmed"),
                               ("airport drop-off", "2026-12-03T14:30", NY, NY_HOTEL["name"], "JFK Terminal 7",
                                "Liberty Line Cars", "Driver assigned 24h before", 60, "LL-2231", 95, "booked")]),
        "cco": dict(out="2026-11-30", ret="2026-12-04", status="travelling", budget=5000,
                    notes="Staying Thursday night for the Friday client breakfast follow-ups.",
                    flights=[("outbound", "Northstar Atlantic", "NS 112", "LHR", "2026-11-30T09:00", LDN, "T3",
                              "JFK", "2026-11-30T12:10", NY, "T7", "NSR8PL", "3K", 1600, "landed", 0),
                             ("return", "Northstar Atlantic", "NS 111", "JFK", "2026-12-04T08:30", NY, "T7",
                              "LHR", "2026-12-04T20:35", LDN, "T3", "NSR8PL", "3K", 1600, "booked", 0)],
                    hotel=("2026-11-30T14:00", "2026-12-04T04:30", "HL-58214", 1600, "confirmed"),
                    transfers=[("airport pickup", "2026-11-30T13:00", NY, "JFK Terminal 7 arrivals", NY_HOTEL["name"],
                                "Liberty Line Cars", "Ana R. +1 917 555 0188", 60, "LL-2208", 95, "confirmed"),
                               ("airport drop-off", "2026-12-04T04:30", NY, NY_HOTEL["name"], "JFK Terminal 7",
                                "Liberty Line Cars", "Driver assigned 24h before", 60, "LL-2240", 95, "booked")]),
        "ssm": dict(out="2026-11-30", ret="2026-12-03", status="travelling", budget=3000,
                    notes="Premium economy per travel policy.",
                    flights=[("outbound", "Northstar Atlantic", "NS 120", "LHR", "2026-11-30T13:40", LDN, "T3",
                              "JFK", "2026-11-30T16:50", NY, "T7", "NSB2TW", "21C", 750, "landed", 0),
                             ("return", "Northstar Atlantic", "NS 125", "JFK", "2026-12-03T21:15", NY, "T7",
                              "LHR", "2026-12-04T09:20", LDN, "T3", "NSB2TW", "21C", 750, "booked", 0)],
                    hotel=("2026-11-30T18:30", "2026-12-03T17:15", "HL-58215", 960, "confirmed"),
                    transfers=[("airport pickup", "2026-11-30T17:40", NY, "JFK Terminal 7 arrivals", NY_HOTEL["name"],
                                "Liberty Line Cars", "Sam K. +1 917 555 0161", 60, "LL-2209", 95, "confirmed"),
                               ("airport drop-off", "2026-12-03T17:15", NY, NY_HOTEL["name"], "JFK Terminal 7",
                                "Liberty Line Cars", "Driver assigned 24h before", 60, "LL-2236", 95, "booked")]),
    },
    "FUJCON2027": {
        # CEO: about 6% over budget.
        "ceo": dict(out="2027-04-11", ret="2027-04-14", status="booked", budget=4500,
                    notes="Over budget: fare rose after the launch date was confirmed.",
                    flights=[("outbound", "Gulfwind Airways", "GW 30", "LHR", "2027-04-11T09:40", LDN, "T4",
                              "DXB", "2027-04-11T19:50", DXB, "T1", "GWA7HM", "4F", 1850, "booked", 0),
                             ("return", "Gulfwind Airways", "GW 39", "DXB", "2027-04-14T23:55", DXB, "T1",
                              "LHR", "2027-04-15T04:15", LDN, "T4", "GWA7HM", "4F", 1850, "booked", 0)],
                    hotel=("2027-04-11T22:30", "2027-04-14T18:30", "CP-1104", 720, "booked"),
                    transfers=[("car to Fujairah", "2027-04-11T20:45", DXB, "DXB Terminal 1 arrivals", FUJ_HOTEL["name"],
                                "Emirates Coast Chauffeurs", "Driver assigned 24h before", 105, "EC-7781", 180, "booked"),
                               ("car from Fujairah", "2027-04-14T18:30", DXB, FUJ_HOTEL["name"], "DXB Terminal 1",
                                "Emirates Coast Chauffeurs", "Driver assigned 24h before", 120, "EC-7782", 180, "booked")]),
        # CCO: overnight flight, delayed 90 min -> lands 09:05 and now clashes with Sunday meetings.
        "cco": dict(out="2027-04-11", ret="2027-04-15", status="confirmed", budget=5000,
                    notes="Overnight Sunday flight so the weekend stays free in London.",
                    flights=[("outbound", "Gulfwind Airways", "GW 32", "LHR", "2027-04-11T21:30", LDN, "T4",
                              "DXB", "2027-04-12T07:35", DXB, "T1", "GWB3QE", "2A", 1800, "delayed", 90),
                             ("return", "Gulfwind Airways", "GW 31", "DXB", "2027-04-15T08:45", DXB, "T1",
                              "LHR", "2027-04-15T13:05", LDN, "T4", "GWB3QE", "2A", 1800, "booked", 0)],
                    hotel=("2027-04-12T10:30", "2027-04-15T03:45", "CP-1105", 720, "confirmed"),
                    transfers=[("car to Fujairah", "2027-04-12T08:30", DXB, "DXB Terminal 1 arrivals", FUJ_HOTEL["name"],
                                "Emirates Coast Chauffeurs", "Yousef A. +971 50 555 0147", 105, "EC-7790", 180, "confirmed"),
                               ("car from Fujairah", "2027-04-15T03:45", DXB, FUJ_HOTEL["name"], "DXB Terminal 1",
                                "Emirates Coast Chauffeurs", "Driver assigned 24h before", 120, "EC-7791", 180, "booked")]),
        # SSM: return car not yet booked.
        "ssm": dict(out="2027-04-11", ret="2027-04-14", status="booked", budget=3000,
                    notes="Return car to Dubai still to book.",
                    flights=[("outbound", "Gulfwind Airways", "GW 28", "LHR", "2027-04-11T07:55", LDN, "T4",
                              "DXB", "2027-04-11T18:00", DXB, "T1", "GWC9LN", "31D", 690, "booked", 0),
                             ("return", "Gulfwind Airways", "GW 37", "DXB", "2027-04-14T22:45", DXB, "T1",
                              "LHR", "2027-04-15T02:55", LDN, "T4", "GWC9LN", "31D", 690, "booked", 0)],
                    hotel=("2027-04-11T21:00", "2027-04-14T17:30", "CP-1106", 600, "booked"),
                    transfers=[("car to Fujairah", "2027-04-11T18:55", DXB, "DXB Terminal 1 arrivals", FUJ_HOTEL["name"],
                                "Emirates Coast Chauffeurs", "Driver assigned 24h before", 105, "EC-7795", 170, "booked"),
                               ("car from Fujairah", "2027-04-14T17:30", DXB, FUJ_HOTEL["name"], "DXB Terminal 1",
                                "Emirates Coast Chauffeurs", None, 120, None, 170, "not booked")]),
    },
}

# Checklist status only (done / pending / not needed). No document numbers, ever.
DOCS = {
    "IBIA2026": {"US travel authorisation (ESTA)": {"ceo": "done", "cco": "done", "ssm": "done"},
                 "Travel insurance": {"ceo": "done", "cco": "done", "ssm": "done"},
                 "Emergency contact on file": {"ceo": "done", "cco": "done", "ssm": "done"}},
    "FUJCON2027": {"UAE entry requirements checked": {"ceo": "done", "cco": "done", "ssm": "pending"},
                   "Travel insurance": {"ceo": "done", "cco": "pending", "ssm": "done"},
                   "Emergency contact on file": {"ceo": "done", "cco": "done", "ssm": "done"},
                   "US travel authorisation (ESTA)": {"ceo": "not needed", "cco": "not needed", "ssm": "not needed"}},
}


def seed_travel(conn: sqlite3.Connection) -> None:
    """Insert travel data. Expects people and events to exist; does nothing if trips already exist."""
    if conn.execute("SELECT COUNT(*) FROM trips").fetchone()[0]:
        return
    pid = {r[0]: r[1] for r in conn.execute("SELECT key, id FROM people")}
    eid = {r[0]: r[1] for r in conn.execute("SELECT code, id FROM events")}
    for code, plans in TRIPS.items():
        if code not in eid:
            continue
        hotel_info = NY_HOTEL if code == "IBIA2026" else FUJ_HOTEL
        for key, t in plans.items():
            cur = conn.execute(
                "INSERT INTO trips (person_id, event_id, outbound_date, return_date, status, budget_gbp, notes)"
                " VALUES (?,?,?,?,?,?,?)", (pid[key], eid[code], t["out"], t["ret"], t["status"], t["budget"], t["notes"]))
            trip_id = cur.lastrowid
            for f in t["flights"]:
                (direction, airline, no, da, dt, dtz, dterm, aa, at, atz, aterm, ref, seat, cost, status, delay) = f
                conn.execute(
                    "INSERT INTO flights (trip_id, direction, airline, flight_no, dep_airport, dep_at, dep_tz, dep_terminal,"
                    " arr_airport, arr_at, arr_tz, arr_terminal, booking_ref, seat, cost_gbp, status, delay_minutes)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (trip_id, direction, airline, no, da, dt + ":00", dtz, dterm, aa, at + ":00", atz, aterm, ref, seat,
                     cost, status, delay))
            cin, cout, ref, cost, status = t["hotel"]
            conn.execute(
                "INSERT INTO hotels (trip_id, name, address, tz, check_in_at, check_out_at, booking_ref, distance_km,"
                " travel_min_to_venue, phone, cost_gbp, status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (trip_id, hotel_info["name"], hotel_info["address"], hotel_info["tz"], cin + ":00", cout + ":00", ref,
                 hotel_info["distance_km"], hotel_info["travel_min_to_venue"], hotel_info["phone"], cost, status))
            for (ttype, at, tz, frm, to, provider, driver, mins, ref, cost, status) in t["transfers"]:
                conn.execute(
                    "INSERT INTO transfers (trip_id, type, pickup_at, tz, pickup_place, dropoff_place, provider,"
                    " driver_contact, est_minutes, booking_ref, cost_gbp, status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (trip_id, ttype, at + ":00", tz, frm, to, provider, driver, mins, ref, cost, status))
    for code, items in DOCS.items():
        if code not in eid:
            continue
        for item, by_person in items.items():
            for key, status in by_person.items():
                conn.execute("INSERT INTO travel_docs (person_id, event_id, item, status) VALUES (?,?,?,?)",
                             (pid[key], eid[code], item, status))
