"""Travel logistics: schema privacy, seed + migration, travel clash rules, logged writes, masking."""
from datetime import datetime, timedelta

import pytest

from db.database import connect, query, scalar
from services import data, travel
from services.scheduling import (Item, TravelItem, check_diary, check_meeting, check_travel, travel_flags,
                                 latest_hotel_departure)

D = datetime(2026, 12, 1)


def at(h, m=0, day=0):
    return D + timedelta(days=day, hours=h, minutes=m)


def meeting(start, end, people=(1,), mid=1):
    return Item(mid, start, end, frozenset(people), "Room", f"M{mid}", "confirmed")


def outbound(arr, dep=None, long_haul=True, pid=1, status="landed"):
    return TravelItem(10, "flight", pid, dep or arr - timedelta(hours=8), arr, "NS 1 LHR→JFK", status, "outbound",
                      long_haul)


def ret(dep, pid=1):
    return TravelItem(11, "flight", pid, dep, dep + timedelta(hours=7), "NS 2 JFK→LHR", "booked", "return", True)


def transfer(start, minutes, sub="airport pickup", status="booked", pid=1, tid=20):
    return TravelItem(tid, "transfer", pid, start, start + timedelta(minutes=minutes), sub.capitalize(), status, sub)


def hotel(cin, cout, status="booked", pid=1):
    return TravelItem(30, "hotel", pid, cin, cout, "Hotel", status)


# ----------------------------------------------------------------------------- privacy
def test_schema_has_no_sensitive_columns(fresh_db):
    banned = ("passport", "id_number", "national_id", "card", "iban", "account_number", "sort_code", "cvv", "bank")
    with connect() as conn:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        cols = [(t, r[1].lower()) for t in tables for r in conn.execute(f"PRAGMA table_info({t})")]
    assert not [c for c in cols if any(b in c[1] for b in banned)]


def test_docs_are_status_only(fresh_db):
    assert {r["status"] for r in query("SELECT status FROM travel_docs")} <= {"done", "pending", "not needed"}


def test_booking_ref_masking():
    ops, ceo, cco = {"id": 4, "can_edit": 1}, {"id": 1, "can_edit": 0}, {"id": 2, "can_edit": 0}
    assert travel.can_see_ref(ops, 1) and travel.can_see_ref(ceo, 1) and not travel.can_see_ref(cco, 1)
    assert travel.mask("NSQ4KD", True) == "NSQ4KD"
    masked = travel.mask("NSQ4KD", False)
    assert masked.endswith("KD") and "NSQ4" not in masked


# ----------------------------------------------------------------------------- seed + migration
def test_seed_travel(fresh_db):
    assert scalar("SELECT COUNT(*) FROM trips") == 6
    assert scalar("SELECT COUNT(*) FROM flights WHERE status='delayed'") == 1
    assert scalar("SELECT COUNT(*) FROM transfers WHERE status='not booked'") == 1
    over = [b for b in travel.budget_rows() if b["over"]]
    assert len(over) == 1 and 0 < over[0]["pct"] - 100 < 10            # one trip slightly over budget


def test_migration_adds_travel_and_keeps_existing_data(fresh_db):
    from db.database import init_db
    with connect() as conn:
        for t in ("travel_docs", "transfers", "hotels", "flights", "trips"):
            conn.execute(f"DELETE FROM {t}")
        conn.execute("UPDATE meetings SET objective='kept by migration' WHERE id=1")
    before = [scalar(f"SELECT COUNT(*) FROM {t}") for t in ("meetings", "change_log", "debriefs")]
    init_db()                                                          # not a reseed
    assert [scalar(f"SELECT COUNT(*) FROM {t}") for t in ("meetings", "change_log", "debriefs")] == before
    assert scalar("SELECT objective FROM meetings WHERE id=1") == "kept by migration"
    assert scalar("SELECT COUNT(*) FROM trips") == 6
    init_db()
    assert scalar("SELECT COUNT(*) FROM trips") == 6                  # idempotent


# ----------------------------------------------------------------------------- rules
def test_landing_buffer_threshold():
    f = outbound(at(14, 0, day=-1) + timedelta(hours=20))           # lands Tue 10:00
    assert [c.kind for c in check_travel(meeting(at(11, 59), at(12, 30)), [f])] == ["landing"]
    assert check_travel(meeting(at(12, 0), at(12, 30)), [f]) == []


def test_delay_moves_the_landing_rule():
    sched = outbound(at(9, 0))
    delayed = TravelItem(10, "flight", 1, sched.start + timedelta(minutes=90), at(10, 30), sched.label,
                         "delayed", "outbound", True)
    m = meeting(at(11, 30), at(12, 0))
    assert check_travel(m, [sched]) == []
    assert [c.kind for c in check_travel(m, [delayed])] == ["landing"]


def test_departure_uses_dropoff_duration():
    f = ret(at(18, 30))                                            # leave by 18:30 − 3h − ground
    assert latest_hotel_departure(f, [f]) == at(14, 30)            # default 60 min ground
    drop = transfer(at(13, 45), 105, "airport drop-off")
    assert latest_hotel_departure(f, [f, drop]) == at(13, 45)
    assert [c.kind for c in check_travel(meeting(at(13, 0), at(13, 50)), [f, drop])] == ["departure", "transfer"]
    assert check_travel(meeting(at(13, 0), at(13, 45)), [f, drop]) == []


def test_meeting_during_transfer():
    t = transfer(at(15, 0), 60)
    assert [c.kind for c in check_travel(meeting(at(15, 30), at(16, 30)), [t])] == ["transfer"]
    assert check_travel(meeting(at(16, 0), at(16, 30)), [t]) == []


def test_jetlag_first_morning_only_after_long_haul():
    f = outbound(at(14, 25, day=-1))                                # Mon 14:25
    early, nine = meeting(at(8, 30), at(8, 59)), meeting(at(9, 0), at(9, 30))
    assert [(c.kind, c.severity) for c in check_travel(early, [f])] == [("jetlag", "warning")]
    assert check_travel(nine, [f]) == []
    short = outbound(at(14, 25, day=-1), long_haul=False)
    assert check_travel(early, [short]) == []
    later = meeting(at(8, 0, day=1), at(8, 30, day=1))              # two days after
    assert check_travel(later, [f]) == []


def test_travel_only_affects_that_person():
    f = outbound(at(10, 0), pid=2)
    assert check_travel(meeting(at(10, 30), at(11, 0), people=(1,)), [f]) == []


def test_cancelled_meeting_never_clashes_with_travel():
    m = Item(1, at(10, 0), at(10, 30), frozenset({1}), "Room", "M1", "cancelled")
    assert check_travel(m, [outbound(at(10, 0))]) == []


def test_check_meeting_and_diary_include_travel_rules():
    t = transfer(at(15, 0), 60)
    assert any(c.kind == "transfer" for c in check_meeting(meeting(at(15, 0), at(15, 30)), [], travel=[t]))
    assert any(c.kind == "transfer" for c in check_diary([meeting(at(15, 0), at(15, 30))], travel=[t]))
    assert check_meeting(meeting(at(15, 0), at(15, 30)), []) == []        # old callers unchanged


def test_flags_missing_hotel_night_and_unbooked_transfer():
    out_f, ret_f = outbound(at(14, 0, day=-1)), ret(at(18, 0, day=2))      # Mon arrive, Thu leave
    pick = transfer(at(15, 0, day=-1), 60)
    drop = transfer(at(14, 0, day=2), 60, "airport drop-off", status="not booked", tid=21)
    h = hotel(at(16, 0, day=-1), at(12, 0, day=1))                         # Mon–Wed only: Wed night missing
    flags = travel_flags(1, [out_f, ret_f, pick, drop, h])
    kinds = sorted(f.kind for f in flags)
    assert kinds == ["no_hotel", "not_booked"]
    assert "Wed 02 Dec" in next(f.message for f in flags if f.kind == "no_hotel")


def test_flags_no_transfer_and_early_pickup():
    late = TravelItem(10, "flight", 1, at(0, 0), at(9, 5), "GW 32", "delayed", "outbound", True)
    pick = transfer(at(8, 30), 105, "car to Fujairah")
    assert [f.kind for f in travel_flags(1, [late, pick])] == ["pickup_early"]
    assert [f.kind for f in travel_flags(1, [late])] == ["no_transfer"]


# ----------------------------------------------------------------------------- seed-level behaviour
def _fuj():
    return next(e for e in data.events() if e["code"] == "FUJCON2027")


def _ibia():
    return next(e for e in data.events() if e["code"] == "IBIA2026")


def test_seeded_delay_flags_meetings_with_suggestions(fresh_db):
    ev = _fuj()
    f = next(x for x in travel.flights(ev["id"], ev) if x["status"] == "delayed")
    impact = travel.delay_impact(ev["id"], ev, f["id"])
    names = sorted(r.meeting.label.split(" Mon")[0] for r in impact)
    assert names == ["Coralline Shipping", "Velasco Gulf Fuels"]
    for r in impact:
        assert r.move_to is not None and r.move_to.start >= f["arr_ev"] + timedelta(hours=2)
        assert r.reassign                                               # someone else can take it


def test_clearing_delay_removes_coralline_clash(fresh_db):
    ev = _fuj()
    f = next(x for x in travel.flights(ev["id"], ev) if x["status"] == "delayed")
    travel.set_flight_delay(f["id"], 0, "London Ops")
    names = [r.meeting.label for r in travel.delay_impact(ev["id"], ev, f["id"])]
    assert not any("Coralline" in n for n in names)                    # 11:00 is fine at 09:35 + 2h
    assert any("Velasco" in n for n in names)                          # 08:00 still too early


def test_ibia_seed_has_jetlag_but_no_errors(fresh_db):
    ev = _ibia()
    clashes = travel.meeting_travel_clashes(ev["id"], ev)
    assert clashes and all(c.kind == "jetlag" and c.severity == "warning" for c in clashes)
    assert not [f for f in travel.red_flags(ev["id"], ev) if f["severity"] == "error"]


def test_red_flags_are_sorted_errors_first(fresh_db):
    ev = _fuj()
    sev = [f["severity"] for f in travel.red_flags(ev["id"], ev)]
    assert sev == sorted(sev, key=lambda s: s != "error") and "error" in sev and "warning" in sev


# ----------------------------------------------------------------------------- writes
def test_update_logs_each_field_and_hides_booking_ref(fresh_db):
    ev = _ibia()
    h = travel.hotels(ev["id"])[0]
    before = scalar("SELECT COUNT(*) FROM change_log")
    out = travel.update_item("hotel", h["id"], {"booking_ref": "NEW123", "phone": "+1 212 555 0199"}, "London Ops")
    assert len(out) == 2 and scalar("SELECT COUNT(*) FROM change_log") - before == 2
    rows = query("SELECT * FROM change_log ORDER BY id DESC LIMIT 2")
    assert all(r["entity"] == "hotel" and r["event_id"] == ev["id"] for r in rows)
    ref_row = next(r for r in rows if r["field"] == "booking_ref")
    assert "NEW123" not in (ref_row["summary"] + (ref_row["new_value"] or "") + (ref_row["old_value"] or ""))


def test_travel_change_shows_in_unseen_banner(fresh_db):
    ev = _ibia()
    data.mark_seen(1)
    f = travel.flights(ev["id"])[1]
    travel.set_flight_delay(f["id"], 45, "London Ops")
    unseen = data.unseen_changes(1, ev["id"])
    assert unseen and all(c["entity"] == "flight" for c in unseen)
    assert any("delayed" in c["summary"] for c in unseen)


def test_no_op_update_logs_nothing(fresh_db):
    t = travel.transfers(_ibia()["id"])[0]
    before = scalar("SELECT COUNT(*) FROM change_log")
    assert travel.update_item("transfer", t["id"], {"est_minutes": t["est_minutes"]}, "London Ops") == []
    assert scalar("SELECT COUNT(*) FROM change_log") == before


def test_validation_rejects_bad_values(fresh_db):
    ev = _ibia()
    f = travel.flights(ev["id"])[0]
    with pytest.raises(ValueError):
        travel.update_item("flight", f["id"], {"status": "lost"}, "London Ops")
    with pytest.raises(ValueError, match="Arrival"):
        travel.update_item("flight", f["id"], {"arr_at": "2026-11-30T05:00:00"}, "London Ops")
    h = travel.hotels(ev["id"])[0]
    with pytest.raises(ValueError, match="Check-out"):
        travel.update_item("hotel", h["id"], {"check_out_at": "2026-11-29T10:00:00"}, "London Ops")


def test_create_item_is_logged(fresh_db):
    ev = _ibia()
    trip = travel.trips(ev["id"])[0]
    tid = travel.create_item("transfer", trip["id"], dict(
        type="venue shuttle", pickup_at="2026-12-02T08:00:00", tz="America/New_York", pickup_place="Hotel",
        dropoff_place="Venue", est_minutes=10, cost_gbp=0, status="booked"), "London Ops")
    row = query("SELECT * FROM change_log ORDER BY id DESC LIMIT 1")[0]
    assert row["entity"] == "transfer" and row["entity_id"] == tid and row["action"] == "create"


def test_budget_actual_is_sum_of_items(fresh_db):
    ev = _ibia()
    b = next(r for r in travel.budget_rows(ev["id"]) if r["role"] == "CEO")
    assert b["actual_gbp"] == 1650 * 2 + 1280 + 95 * 2


def test_london_conversion_handles_dst(fresh_db):
    ev = _fuj()                                                     # April: London is on BST (UTC+1)
    f = next(x for x in travel.flights(ev["id"], ev) if x["flight_no"] == "GW 30")
    assert f["dep_ev"] == datetime(2027, 4, 11, 12, 40)            # 09:40 BST = 12:40 Dubai
    assert f["duration_min"] == 7 * 60 + 10


def test_create_item_requires_fields(fresh_db):
    trip = travel.trips(_ibia()["id"])[0]
    with pytest.raises(ValueError, match="Missing"):
        travel.create_item("transfer", trip["id"], {"type": "venue shuttle", "tz": "America/New_York"}, "London Ops")


def test_travel_summary_template_and_guardrails(fresh_db, monkeypatch):
    from services import llm
    ev = _fuj()
    fields = travel.summary_fields(ev, data.person(2))
    assert not any("booking" in k or "ref" in k for k in fields)            # refs never reach the AI
    assert not any(v in " ".join(fields.values()) for v in ("GWB3QE", "CP-1105", "EC-7790"))
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    res = llm.travel_summary(fields)
    assert res.generator == "template" and "GW 32" in res.content["markdown"] and "delayed" in res.content["markdown"]
    assert res.sources and all(s in fields for s in res.sources)
    monkeypatch.setenv("GROQ_API_KEY", "test")
    monkeypatch.setattr(llm, "_groq_json", lambda *a, **k: {
        "summary_markdown": "You land at 09:05 [outbound.lands] in seat 99Z [outbound.legroom].",
        "fields_used": ["outbound.lands", "made.up"]})
    res = llm.travel_summary(fields)
    assert "[outbound.legroom]" not in res.content["markdown"] and "[unverified]" in res.content["markdown"]
    assert res.sources == ["outbound.lands"] and res.unverified
