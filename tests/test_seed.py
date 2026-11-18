from db.database import query, scalar


def test_seed_counts(fresh_db):
    assert scalar("SELECT COUNT(*) FROM events") == 2
    assert 18 <= scalar("SELECT COUNT(*) FROM accounts") <= 26
    ibia = scalar("SELECT id FROM events WHERE code='IBIA2026'")
    fuj = scalar("SELECT id FROM events WHERE code='FUJCON2027'")
    assert 23 <= scalar("SELECT COUNT(*) FROM meetings WHERE event_id=?", [ibia]) <= 28
    assert scalar("SELECT COUNT(*) FROM meetings WHERE event_id=? AND status='cancelled'", [ibia]) == 2
    assert scalar("SELECT COUNT(*) FROM meetings WHERE event_id=? AND status='moved'", [ibia]) == 1
    assert scalar("SELECT COUNT(*) FROM meetings WHERE event_id=? AND status='proposed'", [fuj]) == 10


def test_targets(fresh_db):
    rows = {r["code"]: r for r in query(
        "SELECT e.code, t.* FROM targets t JOIN events e ON e.id=t.event_id")}
    assert (rows["IBIA2026"]["meetings"], rows["IBIA2026"]["app_signups"], rows["IBIA2026"]["trials"]) == (25, 15, 5)
    assert (rows["FUJCON2027"]["meetings"], rows["FUJCON2027"]["app_signups"], rows["FUJCON2027"]["trials"]) == (40, 25, 10)


def test_done_meetings_have_next_step_date(fresh_db):
    assert scalar("SELECT COUNT(*) FROM meetings WHERE status='done' AND (next_step_date IS NULL OR next_step_date='')") == 0


def test_every_meeting_has_an_attendee(fresh_db):
    assert scalar("SELECT COUNT(*) FROM meetings m WHERE NOT EXISTS "
                  "(SELECT 1 FROM meeting_people mp WHERE mp.meeting_id=m.id)") == 0


def test_some_materials_unapproved(fresh_db):
    assert scalar("SELECT COUNT(*) FROM materials WHERE approval_status != 'approved'") >= 2


def test_fujcon_conference_days_tbc(fresh_db):
    rows = query("SELECT s.start_at, s.tbc FROM sessions s JOIN events e ON e.id=s.event_id WHERE e.code='FUJCON2027'")
    assert all(r["tbc"] == 1 for r in rows if not r["start_at"].startswith("2027-04-12"))
    assert all(r["tbc"] == 0 for r in rows if r["start_at"].startswith("2027-04-12"))
