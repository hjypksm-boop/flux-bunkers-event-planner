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

# Travel rules
LANDING_BUFFER_MIN = 120     # immigration + transfer after landing before the first meeting
AIRPORT_CHECKIN_MIN = 180    # be at the airport this long before an international departure
DEFAULT_GROUND_MIN = 60      # hotel -> airport when no drop-off transfer is recorded
JETLAG_HOUR = 9              # first-morning warning: meetings before 09:00 local ...
LONG_HAUL_MIN = 360          # ... on the day after a flight of 6 h or more
ARRIVAL_TRANSFERS = frozenset({"airport pickup", "car to Fujairah"})
DEPARTURE_TRANSFERS = frozenset({"airport drop-off", "car from Fujairah"})


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
class TravelItem:
    """A flight, hotel stay or transfer for one person, in event-local naive time.

    For flights, start/end are the *effective* times (schedule + delay).
    `sub` is the flight direction (outbound/return/internal) or the transfer type.
    """
    id: int
    kind: str                 # flight | hotel | transfer
    person_id: int
    start: datetime
    end: datetime
    label: str
    status: str = "booked"
    sub: str = ""
    long_haul: bool = False

    @property
    def slot(self) -> Slot:
        return Slot(self.start, self.end)

    @property
    def active(self) -> bool:
        return self.status != "cancelled"

    @property
    def booked(self) -> bool:
        return self.status not in ("cancelled", "not booked")


@dataclass(frozen=True)
class TravelFlag:
    """A logistics gap that isn't tied to a meeting (missing hotel night, unbooked car, ...)."""
    kind: str                 # no_hotel | no_transfer | not_booked | pickup_early
    severity: str             # error | warning
    person_id: int
    message: str
    ref_kind: str | None = None
    ref_id: int | None = None


@dataclass(frozen=True)
class Clash:
    kind: str            # overlap | buffer | travel | session | landing | departure | transfer | jetlag
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
                  buffer_min: int = BUFFER_MIN, travel_min: int = TRAVEL_MIN,
                  travel: Iterable[TravelItem] = ()) -> list[Clash]:
    """All clashes for one (possibly unsaved) meeting against the rest of the diary.

    Rules (per shared person):
      * overlap  – two active meetings overlap                                 -> error
      * travel   – different locations and gap < travel_min                    -> warning
      * buffer   – same/unknown location and gap < buffer_min                  -> warning
      * session  – meeting overlaps a session that person must attend          -> error
      * travel rules (see check_travel): landing, departure, transfer, jetlag
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
    clashes.extend(check_travel(candidate, travel))
    return clashes


def check_diary(items: Iterable[Item], sessions: Iterable[SessionItem] = (),
                buffer_min: int = BUFFER_MIN, travel_min: int = TRAVEL_MIN,
                travel: Iterable[TravelItem] = ()) -> list[Clash]:
    """Every clash in a diary, each meeting pair reported once."""
    items = [i for i in items if i.active]
    sessions = list(sessions)
    travel = list(travel)
    out: list[Clash] = []
    for idx, item in enumerate(items):
        later = items[idx + 1:]
        out.extend(c for c in check_meeting(item, later, (), buffer_min, travel_min))
        out.extend(check_meeting(item, (), sessions, buffer_min, travel_min, travel))
    return out


# ----------------------------------------------------------------------------- travel rules
def _hm(dt: datetime) -> str:
    return f"{dt:%a %H:%M}"


def ready_after_landing(flight: TravelItem) -> datetime:
    return flight.end + timedelta(minutes=LANDING_BUFFER_MIN)


def latest_hotel_departure(flight: TravelItem, travel: Iterable[TravelItem]) -> datetime:
    """Latest time to leave for a departing flight: departure − airport check-in − ground transfer."""
    ground = DEFAULT_GROUND_MIN
    for t in travel:
        if (t.kind == "transfer" and t.person_id == flight.person_id and t.sub in DEPARTURE_TRANSFERS
                and flight.start - timedelta(hours=12) <= t.start <= flight.start):
            ground = max(1, int((t.end - t.start).total_seconds() // 60))
            break
    return flight.start - timedelta(minutes=AIRPORT_CHECKIN_MIN + ground)


def check_travel(candidate: Item, travel: Iterable[TravelItem]) -> list[Clash]:
    """Travel rules for one meeting, per attending person.

      * landing   – meeting starts before landing + 2 h (uses the delayed landing time)   -> error
      * departure – meeting ends after the latest hotel departure for the return flight  -> error
      * transfer  – meeting overlaps a ground transfer                                    -> error
      * jetlag    – meeting before 09:00 local the day after a long-haul arrival          -> warning
    """
    if not candidate.active:
        return []
    travel = [t for t in travel if t.active]
    out: list[Clash] = []
    for pid in sorted(candidate.people):
        mine = [t for t in travel if t.person_id == pid]
        for t in mine:
            if t.kind == "flight" and t.sub in ("outbound", "internal"):
                ready = ready_after_landing(t)
                if candidate.start < ready and candidate.end > t.start:
                    out.append(Clash("landing", "error", pid, candidate.id, t.id, t.label,
                                     f"Starts before {t.label} lands + 2 h (lands {_hm(t.end)}, "
                                     f"ready from {_hm(ready)})"))
                if (t.long_haul and candidate.start.date() == (t.end + timedelta(days=1)).date()
                        and candidate.start.hour < JETLAG_HOUR):
                    out.append(Clash("jetlag", "warning", pid, candidate.id, t.id, t.label,
                                     f"Before {JETLAG_HOUR:02d}:00 the morning after a long-haul arrival "
                                     f"({t.label}, landed {_hm(t.end)}): jet lag"))
            elif t.kind == "flight" and t.sub == "return":
                latest = latest_hotel_departure(t, mine)
                if candidate.end > latest and candidate.start < t.start:
                    out.append(Clash("departure", "error", pid, candidate.id, t.id, t.label,
                                     f"Ends after the latest hotel departure ({_hm(latest)}) for "
                                     f"{t.label} departing {_hm(t.start)}"))
            elif t.kind == "transfer" and candidate.slot.overlaps(t.slot):
                out.append(Clash("transfer", "error", pid, candidate.id, t.id, t.label,
                                 f"During a transfer: {t.label} ({t.start:%H:%M}–{t.end:%H:%M})"))
    return out


def travel_flags(person_id: int, travel: Iterable[TravelItem]) -> list[TravelFlag]:
    """Logistics gaps for one person's trip: every night between landing and the return flight needs a
    booked hotel, every long-haul arrival/departure needs a booked transfer, and pickups must not be
    before a (delayed) landing."""
    mine = [t for t in travel if t.person_id == person_id and t.active]
    flights = sorted((t for t in mine if t.kind == "flight"), key=lambda t: t.start)
    hotels = [t for t in mine if t.kind == "hotel"]
    transfers = [t for t in mine if t.kind == "transfer"]
    out: list[TravelFlag] = []

    arrivals = [f for f in flights if f.sub == "outbound"]
    departures = [f for f in flights if f.sub == "return"]
    if arrivals and departures:
        night = arrivals[0].end.date()
        last = departures[-1].start.date()
        while night < last:
            covering = [h for h in hotels if h.start.date() <= night < h.end.date()]
            if not covering:
                out.append(TravelFlag("no_hotel", "error", person_id,
                                      f"No hotel for the night of {night:%a %d %b}"))
            elif not any(h.booked for h in covering):
                h = covering[0]
                out.append(TravelFlag("not_booked", "error", person_id,
                                      f"Hotel for {night:%a %d %b} is not booked yet ({h.label})", "hotel", h.id))
            night += timedelta(days=1)

    for f in arrivals:
        match = [t for t in transfers if t.sub in ARRIVAL_TRANSFERS
                 and f.end - timedelta(hours=3) <= t.start <= f.end + timedelta(hours=6)]
        if not match:
            out.append(TravelFlag("no_transfer", "warning", person_id,
                                  f"No transfer arranged after {f.label} lands ({_hm(f.end)})", "flight", f.id))
        for t in match:
            if not t.booked:
                out.append(TravelFlag("not_booked", "error", person_id,
                                      f"{t.label} is not booked yet", "transfer", t.id))
            if t.start < f.end:
                out.append(TravelFlag("pickup_early", "warning", person_id,
                                      f"{t.label} pickup {t.start:%H:%M} is before {f.label} now lands "
                                      f"({f.end:%H:%M}); rebook the car", "transfer", t.id))
    for f in departures:
        match = [t for t in transfers if t.sub in DEPARTURE_TRANSFERS
                 and f.start - timedelta(hours=12) <= t.start <= f.start]
        if not match:
            out.append(TravelFlag("no_transfer", "warning", person_id,
                                  f"No transfer to the airport for {f.label} ({_hm(f.start)})", "flight", f.id))
        for t in match:
            if not t.booked:
                out.append(TravelFlag("not_booked", "error", person_id,
                                      f"{t.label} is not booked yet", "transfer", t.id))
    return out


def travel_busy(person_id: int, travel: Iterable[TravelItem]) -> list[Slot]:
    """Time a person can't be in a meeting because of travel."""
    travel = [t for t in travel if t.active and t.person_id == person_id]
    busy: list[Slot] = []
    for t in travel:
        if t.kind == "flight" and t.sub in ("outbound", "internal"):
            busy.append(Slot(t.start, ready_after_landing(t)))
        elif t.kind == "flight" and t.sub == "return":
            busy.append(Slot(latest_hotel_departure(t, travel), t.end))
        elif t.kind == "transfer":
            busy.append(t.slot)
    return busy


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
                    exclude_ids: Iterable[int] = (), travel: Iterable[TravelItem] = ()) -> list[Slot]:
    excluded = set(exclude_ids)
    busy = [i.slot for i in items if i.active and person_id in i.people and i.id not in excluded]
    busy += [s.slot for s in sessions if person_id in s.attendees]
    busy += travel_busy(person_id, travel)
    return busy


def slot_freed_by(cancelled: Item, items: Iterable[Item], sessions: Iterable[SessionItem],
                  window: Slot, buffer_min: int = BUFFER_MIN, min_minutes: int = 15,
                  travel: Iterable[TravelItem] = ()) -> dict[int, Slot | None]:
    """For each person on a cancelled meeting, the free window that now contains its old slot.

    Returns {person_id: Slot or None if nothing usable is free}.
    """
    items = list(items)
    sessions = list(sessions)
    travel = list(travel)
    result: dict[int, Slot | None] = {}
    for pid in sorted(cancelled.people):
        busy = busy_for_person(pid, items, sessions, exclude_ids=[cancelled.id], travel=travel)
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


# ----------------------------------------------------------------------------- travel disruption
@dataclass
class Rebook:
    """What to do with a meeting that a travel change now clashes with."""
    meeting: Item
    clashes: list[Clash]
    move_to: Slot | None                    # earliest same-day slot that works for everyone on it
    reassign: list[tuple[int, int]]         # (blocked person, free colleague) swaps with no errors


def suggest_rebook(meeting: Item, items: Iterable[Item], sessions: Iterable[SessionItem],
                   travel: Iterable[TravelItem], colleagues: Iterable[int], window: Slot,
                   buffer_min: int = BUFFER_MIN) -> Rebook:
    """For a meeting with travel errors: the first slot in `window` free for all its people (travel
    included), and colleagues who could take the place of each blocked person."""
    items, sessions, travel = list(items), list(sessions), list(travel)
    errors = [c for c in check_meeting(meeting, items, sessions, travel=travel) if c.severity == "error"]
    blocked = sorted({c.person_id for c in errors})
    need = int((meeting.end - meeting.start).total_seconds() // 60)

    busy: list[Slot] = []
    for pid in meeting.people:
        busy += busy_for_person(pid, items, sessions, exclude_ids=[meeting.id], travel=travel)
    move_to = None
    for gap in free_slots(busy, window, min_minutes=need, buffer_min=buffer_min):
        move_to = Slot(gap.start, gap.start + timedelta(minutes=need))
        break

    swaps: list[tuple[int, int]] = []
    for pid in blocked:
        for alt in colleagues:
            if alt in meeting.people:
                continue
            trial = Item(meeting.id, meeting.start, meeting.end, (meeting.people - {pid}) | {alt},
                         meeting.location, meeting.label, meeting.status)
            alt_errors = [c for c in check_meeting(trial, items, sessions, travel=travel)
                          if c.severity == "error"]
            if not alt_errors:
                swaps.append((pid, alt))
    return Rebook(meeting, errors, move_to, swaps)


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
