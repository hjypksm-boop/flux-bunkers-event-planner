"""Pure scheduling logic: clash checker, free-slot finder, reserve-list suggestions.

Everything here works on plain dataclasses (no database, no Streamlit) so it is easy to test.
All datetimes passed in must share one timezone convention (we use event-local naive datetimes).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Iterable

BUFFER_MIN = 15        # minimum gap between two meetings for the same person
TRAVEL_MIN = 30        # minimum gap when consecutive meetings are in different locations
ACTIVE_STATUSES = frozenset({"proposed", "confirmed", "moved", "done"})


@dataclass(frozen=True)
class Slot:
    start: datetime
    end: datetime

    @property
    def minutes(self) -> int:
        return int((self.end - self.start).total_seconds() // 60)

    def overlaps(self, other: "Slot") -> bool:
        return self.start < other.end and other.start < self.end


@dataclass(frozen=True)
class Item:
    """A meeting as seen by the scheduler."""
    id: int
    start: datetime
    end: datetime
    people: frozenset[int]
    location: str | None = None
    label: str = ""
    status: str = "confirmed"

    @property
    def slot(self) -> Slot:
        return Slot(self.start, self.end)

    @property
    def active(self) -> bool:
        return self.status in ACTIVE_STATUSES


@dataclass(frozen=True)
class SessionItem:
    """An event session; `attendees` are the people who must attend it."""
    id: int
    start: datetime
    end: datetime
    title: str
    attendees: frozenset[int] = frozenset()

    @property
    def slot(self) -> Slot:
        return Slot(self.start, self.end)


@dataclass(frozen=True)
class Clash:
    kind: str            # overlap | buffer | travel | session
    severity: str        # error | warning
    person_id: int
    meeting_id: int
    other_id: int | None
    other_label: str
    message: str
    gap_minutes: int | None = None


@dataclass(frozen=True)
class ReserveCandidate:
    account_id: int
    account_name: str
    priority: int                 # 1 = call first
    tier: int
    preferred_owner_id: int | None = None
    min_minutes: int = 30
    note: str = ""


@dataclass
class Suggestion:
    candidate: ReserveCandidate
    score: float
    reasons: list[str] = field(default_factory=list)


# ----------------------------------------------------------------------------- clash checker
def _same_place(a: str | None, b: str | None) -> bool | None:
    """True/False if both locations are known, None if either is unknown."""
    if not a or not b:
        return None
    return a.strip().lower() == b.strip().lower()


def _gap_minutes(a: Slot, b: Slot) -> int:
    """Minutes between two non-overlapping slots (order-independent)."""
    first, second = (a, b) if a.start <= b.start else (b, a)
    return int((second.start - first.end).total_seconds() // 60)


def check_meeting(candidate: Item, others: Iterable[Item], sessions: Iterable[SessionItem] = (),
                  buffer_min: int = BUFFER_MIN, travel_min: int = TRAVEL_MIN) -> list[Clash]:
    """All clashes for one (possibly unsaved) meeting against the rest of the diary.

    Rules (per shared person):
      * overlap  – two active meetings overlap                                 -> error
      * travel   – different locations and gap < travel_min                    -> warning
      * buffer   – same/unknown location and gap < buffer_min                  -> warning
      * session  – meeting overlaps a session that person must attend          -> error
    Cancelled meetings never clash.
    """
    if not candidate.active:
        return []
    clashes: list[Clash] = []
    for other in others:
        if other.id == candidate.id or not other.active:
            continue
        shared = candidate.people & other.people
        if not shared:
            continue
        for pid in sorted(shared):
            if candidate.slot.overlaps(other.slot):
                clashes.append(Clash("overlap", "error", pid, candidate.id, other.id, other.label,
                                     f"Overlaps with {other.label}"))
                continue
            gap = _gap_minutes(candidate.slot, other.slot)
            same = _same_place(candidate.location, other.location)
            if same is False and gap < travel_min:
                clashes.append(Clash("travel", "warning", pid, candidate.id, other.id, other.label,
                                     f"Only {gap} min to move between '{candidate.location}' and "
                                     f"'{other.location}' ({other.label}); need {travel_min}", gap))
            elif gap < buffer_min:
                clashes.append(Clash("buffer", "warning", pid, candidate.id, other.id, other.label,
                                     f"Only {gap} min buffer next to {other.label}; need {buffer_min}", gap))
    for s in sessions:
        for pid in sorted(candidate.people & s.attendees):
            if candidate.slot.overlaps(s.slot):
                clashes.append(Clash("session", "error", pid, candidate.id, None, s.title,
                                     f"Clashes with session they must attend: {s.title} "
                                     f"({s.start:%H:%M}–{s.end:%H:%M})"))
    return clashes


def check_diary(items: Iterable[Item], sessions: Iterable[SessionItem] = (),
                buffer_min: int = BUFFER_MIN, travel_min: int = TRAVEL_MIN) -> list[Clash]:
    """Every clash in a diary, each meeting pair reported once."""
    items = [i for i in items if i.active]
    sessions = list(sessions)
    out: list[Clash] = []
    for idx, item in enumerate(items):
        later = items[idx + 1:]
        out.extend(c for c in check_meeting(item, later, (), buffer_min, travel_min))
        out.extend(check_meeting(item, (), sessions, buffer_min, travel_min))
    return out


# ----------------------------------------------------------------------------- free slots
def merge_slots(slots: Iterable[Slot]) -> list[Slot]:
    ordered = sorted(slots, key=lambda s: s.start)
    merged: list[Slot] = []
    for s in ordered:
        if merged and s.start <= merged[-1].end:
            merged[-1] = Slot(merged[-1].start, max(merged[-1].end, s.end))
        else:
            merged.append(s)
    return merged


def free_slots(busy: Iterable[Slot], window: Slot, min_minutes: int = 30,
               buffer_min: int = 0) -> list[Slot]:
    """Gaps inside `window` not covered by `busy` (each busy slot padded by buffer_min)."""
    pad = timedelta(minutes=buffer_min)
    padded = [Slot(max(b.start - pad, window.start), min(b.end + pad, window.end))
              for b in busy if b.overlaps(Slot(window.start - pad, window.end + pad))]
    padded = [p for p in padded if p.start < p.end]
    gaps: list[Slot] = []
    cursor = window.start
    for b in merge_slots(padded):
        if b.start > cursor:
            gaps.append(Slot(cursor, b.start))
        cursor = max(cursor, b.end)
    if cursor < window.end:
        gaps.append(Slot(cursor, window.end))
    return [g for g in gaps if g.minutes >= min_minutes]


def busy_for_person(person_id: int, items: Iterable[Item], sessions: Iterable[SessionItem] = (),
                    exclude_ids: Iterable[int] = ()) -> list[Slot]:
    excluded = set(exclude_ids)
    busy = [i.slot for i in items if i.active and person_id in i.people and i.id not in excluded]
    busy += [s.slot for s in sessions if person_id in s.attendees]
    return busy


def slot_freed_by(cancelled: Item, items: Iterable[Item], sessions: Iterable[SessionItem],
                  window: Slot, buffer_min: int = BUFFER_MIN, min_minutes: int = 15) -> dict[int, Slot | None]:
    """For each person on a cancelled meeting, the free window that now contains its old slot.

    Returns {person_id: Slot or None if nothing usable is free}.
    """
    items = list(items)
    sessions = list(sessions)
    result: dict[int, Slot | None] = {}
    for pid in sorted(cancelled.people):
        busy = busy_for_person(pid, items, sessions, exclude_ids=[cancelled.id])
        gaps = free_slots(busy, window, min_minutes=min_minutes, buffer_min=buffer_min)
        best = None
        best_overlap = 0
        for g in gaps:
            ov = (min(g.end, cancelled.end) - max(g.start, cancelled.start)).total_seconds()
            if ov > best_overlap:
                best, best_overlap = g, ov
        result[pid] = best
    return result


def suggest_reserves(candidates: Iterable[ReserveCandidate], slot: Slot, owner_id: int | None,
                     booked_account_ids: Iterable[int] = (), top_n: int = 3) -> list[Suggestion]:
    """Rank reserve-list accounts for a freed slot.

    Excludes accounts already booked (active meeting at this event) and those needing a longer slot.
    Score: priority dominates, then owner match, then tier.
    """
    booked = set(booked_account_ids)
    out: list[Suggestion] = []
    for c in candidates:
        if c.account_id in booked or c.min_minutes > slot.minutes:
            continue
        score = (4 - c.priority) * 10.0
        reasons = [f"Reserve priority {c.priority}"]
        if owner_id is not None and c.preferred_owner_id == owner_id:
            score += 5
            reasons.append("Preferred owner is free")
        score += (3 - c.tier) * 2
        reasons.append(f"Tier {c.tier}")
        reasons.append(f"Needs {c.min_minutes} min, slot has {slot.minutes} min")
        out.append(Suggestion(c, score, reasons))
    out.sort(key=lambda s: (-s.score, s.candidate.account_name))
    return out[:top_n]


# ----------------------------------------------------------------------------- business rules
MEETING_STATUSES = ("proposed", "confirmed", "moved", "cancelled", "done")


def validate_meeting(status: str, start: datetime, end: datetime,
                     next_step: str | None, next_step_date: str | None) -> list[str]:
    """Field-level validation shared by the Ops Console and the debrief flow."""
    errors = []
    if status not in MEETING_STATUSES:
        errors.append(f"Unknown status '{status}'")
    if end <= start:
        errors.append("End time must be after start time")
    if status == "done" and not (next_step_date or "").strip():
        errors.append("A meeting can't be marked done without a next step date")
    if status == "done" and not (next_step or "").strip():
        errors.append("A meeting can't be marked done without a next step")
    return errors
