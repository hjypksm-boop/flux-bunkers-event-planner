"""KPI calculations and the 'what's off track first' weekly summary (pure functions)."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

BOOKED = {"confirmed", "moved", "done"}
RAG_ORDER = {"off track": 0, "at risk": 1, "on track": 2, "not started": 3}


@dataclass
class Metric:
    key: str
    label: str
    actual: float
    target: float
    status: str           # on track | at risk | off track | not started
    detail: str
    unit: str = ""

    @property
    def pct_of_target(self) -> float:
        return 0.0 if not self.target else self.actual / self.target * 100


def _rag_ratio(ratio: float) -> str:
    return "on track" if ratio >= 1 else "at risk" if ratio >= 0.9 else "off track"


def _rag_pct(actual: float, target: float) -> str:
    return "on track" if actual >= target else "at risk" if actual >= target - 10 else "off track"


def followup_timeliness(done_meetings: list[dict], follow_ups: list[dict], now_local: datetime, tz: str):
    """(sent_within_24h, due) — a follow-up is 'due' once sent or once 24h have passed since the meeting."""
    by_meeting = {}
    for f in follow_ups:
        by_meeting.setdefault(f["meeting_id"], []).append(f)
    zone = ZoneInfo(tz)
    within = due = 0
    for m in done_meetings:
        end = m["end"]
        sent = [f for f in by_meeting.get(m["id"], []) if f.get("sent_at")]
        if sent:
            sent_local = min(datetime.fromisoformat(f["sent_at"]) for f in sent).astimezone(zone).replace(tzinfo=None)
            due += 1
            within += int(sent_local - end <= timedelta(hours=24))
        elif now_local - end >= timedelta(hours=24):
            due += 1
    return within, due


def compute(meetings: list[dict], debriefs: list[dict], follow_ups: list[dict], targets: dict,
            now_local: datetime, tz: str) -> dict:
    booked = [m for m in meetings if m["status"] in BOOKED]
    proposed = [m for m in meetings if m["status"] == "proposed"]
    cancelled = [m for m in meetings if m["status"] == "cancelled"]
    done = [m for m in meetings if m["status"] == "done"]
    done_ids = {m["id"] for m in done}
    held_debriefs = [d for d in debriefs if d["meeting_id"] in done_ids]

    signups = sum(int(d["app_signup"]) for d in held_debriefs)
    trials = sum(int(d["trial_started"]) for d in held_debriefs)
    dm_held = sum(int(d["decision_maker_present"]) for d in held_debriefs)
    dm_pct = (dm_held / len(held_debriefs) * 100) if held_debriefs else 0.0
    upcoming = [m for m in booked if m["status"] != "done"]
    dm_planned_pct = (sum(1 for m in upcoming if m.get("dm_planned")) / len(upcoming) * 100) if upcoming else 0.0
    within, due = followup_timeliness(done, follow_ups, now_local, tz)
    fu_pct = (within / due * 100) if due else 0.0
    cancel_rate = len(cancelled) / (len(booked) + len(cancelled)) * 100 if (booked or cancelled) else 0.0

    # Pace: project sign-ups / trials over all booked meetings at the current conversion rate.
    held = len(held_debriefs)
    proj = (lambda x: x / held * len(booked)) if held else (lambda x: 0.0)

    t = targets
    metrics = [
        Metric("meetings", "Meetings booked", len(booked), t["meetings"],
               _rag_ratio(len(booked) / t["meetings"]) if t["meetings"] else "on track",
               f"{len(booked)} booked of {t['meetings']} target; {len(proposed)} still proposed"),
        Metric("signups", "App sign-ups", signups, t["app_signups"],
               "not started" if not held else _rag_ratio(proj(signups) / t["app_signups"]),
               f"{signups} so far from {held} meetings held; on pace for ~{proj(signups):.0f}" if held
               else "No meetings held yet"),
        Metric("trials", "Trials started", trials, t["trials"],
               "not started" if not held else _rag_ratio(proj(trials) / t["trials"]),
               f"{trials} so far; on pace for ~{proj(trials):.0f}" if held else "No meetings held yet"),
        Metric("dm", "Held meetings with a decision-maker", round(dm_pct), t["dm_pct"],
               "not started" if not held else _rag_pct(dm_pct, t["dm_pct"]),
               f"{dm_held} of {held} held; {dm_planned_pct:.0f}% of upcoming have a DM invited" if held
               else f"{dm_planned_pct:.0f}% of upcoming meetings have a DM invited", "%"),
        Metric("followups", "Follow-ups sent within 24h", round(fu_pct), t["followup_24h_pct"],
               "not started" if not due else _rag_pct(fu_pct, t["followup_24h_pct"]),
               f"{within} of {due} due follow-ups went out within 24h" if due else "None due yet", "%"),
        Metric("cancellations", "Cancellation rate", round(cancel_rate), 10,
               "on track" if cancel_rate <= 10 else "at risk" if cancel_rate <= 20 else "off track",
               f"{len(cancelled)} cancelled", "%"),
    ]
    tier_mix = Counter(m["tier"] for m in booked)
    return {
        "metrics": metrics,
        "counts": {"booked": len(booked), "proposed": len(proposed), "cancelled": len(cancelled),
                   "done": len(done), "held_debriefed": held, "signups": signups, "trials": trials},
        "tier_mix": {tier: tier_mix.get(tier, 0) for tier in (1, 2, 3)},
        "status_mix": Counter(m["status"] for m in meetings),
    }


def weekly_summary(event_name: str, result: dict, now_label: str) -> str:
    """Markdown summary that leads with what is off track."""
    ordered = sorted(result["metrics"], key=lambda m: RAG_ORDER[m.status])
    off = [m for m in ordered if m.status == "off track"]
    risk = [m for m in ordered if m.status == "at risk"]
    ok = [m for m in ordered if m.status in ("on track", "not started")]

    def line(m: Metric) -> str:
        if m.key == "cancellations":
            return f"- **{m.label}: {m.actual:.0f}%** (limit {m.target:.0f}%) — {m.detail}"
        val = f"{m.actual:.0f}{m.unit}" + ("" if m.unit else f" / {m.target:.0f}")
        tgt = f" (target {m.target:.0f}{m.unit})" if m.unit else ""
        return f"- **{m.label}: {val}**{tgt} — {m.detail}"

    head = (f"### {event_name} — weekly summary\n_As of {now_label}._\n\n")
    if off:
        head += f"**Headline:** {len(off)} metric{'s' if len(off) > 1 else ''} off track — " \
                + ", ".join(m.label.lower() for m in off) + ".\n\n"
    elif risk:
        head += "**Headline:** nothing is off track; " + ", ".join(m.label.lower() for m in risk) + " at risk.\n\n"
    else:
        head += "**Headline:** all tracked metrics are on track.\n\n"
    parts = [head]
    if off:
        parts.append("#### 🔴 Off track\n" + "\n".join(line(m) for m in off))
    if risk:
        parts.append("#### 🟠 At risk\n" + "\n".join(line(m) for m in risk))
    if ok:
        parts.append("#### 🟢 On track / not started\n" + "\n".join(line(m) for m in ok))
    c = result["counts"]
    parts.append(f"#### Diary\n- {c['booked']} booked, {c['proposed']} proposed, {c['cancelled']} cancelled, "
                 f"{c['done']} held")
    return "\n\n".join(parts)
