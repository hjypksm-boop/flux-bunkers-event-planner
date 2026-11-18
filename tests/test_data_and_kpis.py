"""Writes go to change_log; business rules enforced; KPI maths on seed data."""
from datetime import datetime

import pytest

from db.database import query, scalar
from services import data, kpis


def _mid(account, status=None):
    sql = "SELECT m.id FROM meetings m JOIN accounts a ON a.id=m.account_id WHERE a.name=? AND m.event_id=1"
    params = [account]
    if status:
        sql += " AND m.status=?"
        params.append(status)
    return scalar(sql + " ORDER BY m.start_at LIMIT 1", params)


def test_moving_confirmed_meeting_logs_and_sets_moved(fresh_db):
    mid = _mid("Ironwood Bulk Carriers", "confirmed")
    before = scalar("SELECT COUNT(*) FROM change_log")
    out = data.update_meeting(mid, {"start_at": "2026-12-03T10:20:00", "end_at": "2026-12-03T10:50:00"}, "London Ops")
    m = data.meeting(mid)
    assert m["status"] == "moved"
    assert scalar("SELECT COUNT(*) FROM change_log") - before == 3      # start, end, status
    actions = {r["action"] for r in query("SELECT action FROM change_log WHERE entity_id=? ORDER BY id DESC LIMIT 3", [mid])}
    assert "move" in actions and "status" in actions
    assert any("→" in s for s in out)


def test_no_op_update_logs_nothing(fresh_db):
    mid = _mid("Ironwood Bulk Carriers", "confirmed")
    m = data.meeting(mid)
    before = scalar("SELECT COUNT(*) FROM change_log")
    assert data.update_meeting(mid, {"location": m["location"]}, "London Ops") == []
    assert scalar("SELECT COUNT(*) FROM change_log") == before


def test_cancel_logs_old_and_new(fresh_db):
    mid = _mid("Marrowstone Bulk")
    data.cancel_meeting(mid, "London Ops", "client unwell")
    row = query("SELECT * FROM change_log ORDER BY id DESC LIMIT 1")[0]
    assert (row["action"], row["old_value"], row["new_value"]) == ("cancel", "confirmed", "cancelled")
    assert "client unwell" in row["summary"]


def test_save_debrief_requires_next_step_date(fresh_db):
    mid = _mid("Orrin Petroleum Marine")
    form = {"what_happened": "x", "interest_level": "low", "next_step": "Call", "next_step_date": "",
            "decision_maker_present": False}
    with pytest.raises(ValueError, match="next step"):
        data.save_debrief(mid, 3, "SSM", form, "notes", "template", "s", "b")
    assert data.meeting(mid)["status"] == "confirmed"


def test_save_debrief_marks_done_and_drafts_follow_up(fresh_db):
    mid = _mid("Orrin Petroleum Marine")
    form = {"what_happened": "x", "interest_level": "high", "next_step": "Demo", "next_step_date": "2026-12-10",
            "decision_maker_present": True, "app_signup": True, "trial_started": False}
    data.save_debrief(mid, 3, "SSM", form, "notes", "template", "subj", "body")
    assert data.meeting(mid)["status"] == "done"
    fu = query("SELECT * FROM follow_ups WHERE meeting_id=?", [mid])
    assert len(fu) == 1 and fu[0]["status"] == "draft"


def test_follow_up_approval_flow(fresh_db):
    fid = scalar("SELECT id FROM follow_ups WHERE status='draft' LIMIT 1")
    data.set_follow_up_status(fid, "approved", "London Ops")
    row = query("SELECT * FROM follow_ups WHERE id=?", [fid])[0]
    assert row["status"] == "approved" and row["approved_by"] == "London Ops" and row["approved_at"]
    data.set_follow_up_status(fid, "sent", "London Ops")
    assert query("SELECT status, sent_at FROM follow_ups WHERE id=?", [fid])[0]["sent_at"]


def test_unseen_changes_and_mark_seen(fresh_db):
    assert len(data.unseen_changes(1, 1)) == 3
    data.mark_seen(1)
    assert data.unseen_changes(1, 1) == []
    data.cancel_meeting(_mid("Marrowstone Bulk"), "London Ops")
    assert len(data.unseen_changes(1, 1)) == 1


def test_kpis_on_seed(fresh_db):
    ms = data.meetings(1)
    deb = data.debriefs(1).to_dict("records")
    res = kpis.compute(ms, deb, data.follow_ups(1), data.targets(1), datetime(2026, 12, 2, 15, 30), "America/New_York")
    c = res["counts"]
    assert (c["cancelled"], c["proposed"], c["done"]) == (2, 2, 13)
    assert c["booked"] == 23 and c["signups"] == 8 and c["trials"] == 2
    by_key = {m.key: m for m in res["metrics"]}
    assert by_key["meetings"].status == "at risk"          # 23/25 = 92%
    assert by_key["trials"].status == "off track"          # pace ~3.5 vs 5
    summary = kpis.weekly_summary("IBIA", res, "now")
    assert summary.index("Off track") < summary.index("On track")


def test_followup_timeliness():
    m = [{"id": 1, "end": datetime(2026, 12, 1, 10, 0)}, {"id": 2, "end": datetime(2026, 12, 1, 10, 0)},
         {"id": 3, "end": datetime(2026, 12, 2, 15, 0)}]
    f = [{"meeting_id": 1, "sent_at": "2026-12-01T20:00:00+00:00"},       # 15:00 NY → 5h
         {"meeting_id": 2, "sent_at": "2026-12-02T17:00:00+00:00"}]       # 12:00 NY next day → 26h
    within, due = kpis.followup_timeliness(m, f, datetime(2026, 12, 2, 15, 30), "America/New_York")
    assert (within, due) == (1, 2)    # meeting 3 not yet due
