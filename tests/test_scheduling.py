from datetime import datetime

import pytest

from services.scheduling import (
    Item, ReserveCandidate, SessionItem, Slot, check_diary, check_meeting, free_slots,
    merge_slots, slot_freed_by, suggest_reserves, validate_meeting,
)

CEO, CCO, SSM = 1, 2, 3


def t(hm: str, day: int = 2) -> datetime:
    h, m = map(int, hm.split(":"))
    return datetime(2026, 12, day, h, m)


def mtg(id, start, end, people=(CEO,), loc="Room 1", status="confirmed", day=2):
    return Item(id, t(start, day), t(end, day), frozenset(people), loc, f"M{id}", status)


# ----------------------------------------------------------------------------- clash checker
class TestClashChecker:
    def test_overlap_same_person_is_error(self):
        clashes = check_meeting(mtg(1, "10:00", "11:00"), [mtg(2, "10:30", "11:30")])
        assert [c.kind for c in clashes] == ["overlap"]
        assert clashes[0].severity == "error"
        assert clashes[0].other_id == 2

    def test_no_clash_for_different_people(self):
        assert check_meeting(mtg(1, "10:00", "11:00", [CEO]), [mtg(2, "10:30", "11:30", [CCO])]) == []

    def test_shared_attendee_detected(self):
        clashes = check_meeting(mtg(1, "10:00", "11:00", [CEO, CCO]), [mtg(2, "10:30", "11:30", [CCO])])
        assert len(clashes) == 1 and clashes[0].person_id == CCO

    def test_cancelled_meetings_never_clash(self):
        assert check_meeting(mtg(1, "10:00", "11:00"), [mtg(2, "10:30", "11:30", status="cancelled")]) == []
        assert check_meeting(mtg(1, "10:00", "11:00", status="cancelled"), [mtg(2, "10:30", "11:30")]) == []

    def test_touching_meetings_same_place_trigger_buffer_warning(self):
        clashes = check_meeting(mtg(1, "10:00", "11:00"), [mtg(2, "11:00", "11:30")])
        assert [c.kind for c in clashes] == ["buffer"]
        assert clashes[0].severity == "warning" and clashes[0].gap_minutes == 0

    @pytest.mark.parametrize("gap_start,expect", [("11:14", ["buffer"]), ("11:15", [])])
    def test_buffer_threshold_is_15_minutes(self, gap_start, expect):
        clashes = check_meeting(mtg(1, "10:00", "11:00"), [mtg(2, gap_start, "12:00")])
        assert [c.kind for c in clashes] == expect

    @pytest.mark.parametrize("gap_start,expect", [("11:29", ["travel"]), ("11:30", [])])
    def test_different_locations_need_30_minutes(self, gap_start, expect):
        clashes = check_meeting(mtg(1, "10:00", "11:00", loc="Midtown office"),
                                [mtg(2, gap_start, "12:00", loc="Venue Room 4")])
        assert [c.kind for c in clashes] == expect

    def test_travel_rule_works_when_other_meeting_is_earlier(self):
        clashes = check_meeting(mtg(1, "11:10", "12:00", loc="A"), [mtg(2, "10:00", "11:00", loc="B")])
        assert [c.kind for c in clashes] == ["travel"] and clashes[0].gap_minutes == 10

    def test_location_comparison_ignores_case_and_whitespace(self):
        clashes = check_meeting(mtg(1, "10:00", "11:00", loc="Room 1 "), [mtg(2, "11:20", "12:00", loc="room 1")])
        assert clashes == []

    def test_unknown_location_falls_back_to_buffer_rule(self):
        clashes = check_meeting(mtg(1, "10:00", "11:00", loc=None), [mtg(2, "11:20", "12:00", loc="B")])
        assert clashes == []

    def test_meeting_during_mandatory_session_is_error(self):
        panel = SessionItem(9, t("10:00"), t("11:00"), "Leadership panel", frozenset({CEO}))
        clashes = check_meeting(mtg(1, "09:45", "10:30"), [], [panel])
        assert [(c.kind, c.severity) for c in clashes] == [("session", "error")]
        assert "Leadership panel" in clashes[0].message

    def test_session_for_someone_else_is_ignored(self):
        panel = SessionItem(9, t("10:00"), t("11:00"), "Panel", frozenset({CCO}))
        assert check_meeting(mtg(1, "10:00", "10:30", [CEO]), [], [panel]) == []

    def test_check_diary_reports_each_pair_once(self):
        items = [mtg(1, "10:00", "11:00"), mtg(2, "10:30", "11:30"), mtg(3, "14:00", "15:00")]
        clashes = check_diary(items)
        assert len(clashes) == 1 and {clashes[0].meeting_id, clashes[0].other_id} == {1, 2}


# ----------------------------------------------------------------------------- free slots
class TestFreeSlots:
    window = Slot(t("08:00"), t("18:00"))

    def test_merge_overlapping(self):
        merged = merge_slots([Slot(t("09:00"), t("10:00")), Slot(t("09:30"), t("11:00")), Slot(t("12:00"), t("13:00"))])
        assert merged == [Slot(t("09:00"), t("11:00")), Slot(t("12:00"), t("13:00"))]

    def test_gaps_between_busy_slots(self):
        busy = [Slot(t("09:00"), t("10:00")), Slot(t("12:00"), t("13:00"))]
        gaps = free_slots(busy, self.window, min_minutes=30)
        assert gaps == [Slot(t("08:00"), t("09:00")), Slot(t("10:00"), t("12:00")), Slot(t("13:00"), t("18:00"))]

    def test_buffer_shrinks_gaps_and_min_length_filters(self):
        busy = [Slot(t("09:00"), t("10:00")), Slot(t("10:45"), t("12:00"))]
        gaps = free_slots(busy, self.window, min_minutes=30, buffer_min=15)
        # 10:00-10:45 shrinks to 10:15-10:30 (15 min) -> filtered out
        assert Slot(t("10:15"), t("10:30")) not in gaps
        assert gaps[0] == Slot(t("08:00"), t("08:45"))

    def test_busy_outside_window_ignored(self):
        gaps = free_slots([Slot(t("06:00"), t("07:00"))], self.window)
        assert gaps == [self.window]

    def test_slot_freed_by_cancellation(self):
        a = mtg(1, "09:00", "10:00")
        cancelled = mtg(2, "11:00", "12:00", status="cancelled")
        c = mtg(3, "14:00", "15:00")
        lunch = SessionItem(5, t("13:00"), t("13:30"), "Must-attend lunch", frozenset({CEO}))
        freed = slot_freed_by(cancelled, [a, cancelled, c], [lunch], self.window, buffer_min=15)
        assert freed[CEO] == Slot(t("10:15"), t("12:45"))

    def test_slot_freed_none_when_fully_booked(self):
        cancelled = mtg(2, "11:00", "12:00", status="cancelled")
        replacement = mtg(3, "10:30", "12:30")
        freed = slot_freed_by(cancelled, [cancelled, replacement], [], self.window)
        assert freed[CEO] is None


# ----------------------------------------------------------------------------- reserve suggestions
class TestReserveSuggestions:
    slot = Slot(t("10:00"), t("11:00"))

    def cand(self, id, prio, tier=2, owner=None, mins=30):
        return ReserveCandidate(id, f"Acc{id}", prio, tier, owner, mins)

    def test_priority_then_owner_then_tier(self):
        ranked = suggest_reserves([self.cand(1, 2), self.cand(2, 1), self.cand(3, 2, owner=SSM)], self.slot, SSM)
        assert [s.candidate.account_id for s in ranked] == [2, 3, 1]

    def test_excludes_booked_and_too_long(self):
        ranked = suggest_reserves([self.cand(1, 1), self.cand(2, 1, mins=90), self.cand(3, 3)],
                                  self.slot, CEO, booked_account_ids=[1])
        assert [s.candidate.account_id for s in ranked] == [3]

    def test_top_n(self):
        ranked = suggest_reserves([self.cand(i, 2) for i in range(10)], self.slot, None, top_n=3)
        assert len(ranked) == 3


# ----------------------------------------------------------------------------- business rules
class TestValidation:
    def test_done_requires_next_step_date(self):
        errs = validate_meeting("done", t("10:00"), t("11:00"), "Send pack", None)
        assert any("next step date" in e for e in errs)

    def test_done_with_next_step_ok(self):
        assert validate_meeting("done", t("10:00"), t("11:00"), "Send pack", "2026-12-08") == []

    def test_end_before_start(self):
        assert validate_meeting("confirmed", t("11:00"), t("10:00"), None, None)

    def test_confirmed_without_next_step_ok(self):
        assert validate_meeting("confirmed", t("10:00"), t("11:00"), None, None) == []
