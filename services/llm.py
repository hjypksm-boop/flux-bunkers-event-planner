"""AI features via Groq, with deterministic template fallbacks.

Guard-rails:
  * The model only ever sees a flat dictionary of database fields (`FIELDS`), and is told to cite
    the field keys it uses in [square.brackets].
  * Citations to keys that don't exist are replaced by [unverified]; `fields_used` is intersected
    with the real keys — so the "sources" list can never contain an invented field.
  * Deterministic 'unverified' checks (stale notes, no decision-maker attending, missing health data)
    are always added, whatever the model says.
  * Any API error, missing key or bad JSON falls back to the template — the app never breaks.
"""
from __future__ import annotations

import json
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime

DEFAULT_MODEL = "openai/gpt-oss-120b"
CITE_RE = re.compile(r"\[([a-z_]+(?:\.[a-z0-9_]+)*)\]")


@dataclass
class LLMResult:
    content: dict
    generator: str                       # "groq:<model>" or "template"
    note: str | None = None              # why the template was used, if it was
    sources: list[str] = field(default_factory=list)
    unverified: list[str] = field(default_factory=list)


# ----------------------------------------------------------------------------- Groq plumbing
def _setting(name: str, default: str | None = None) -> str | None:
    try:
        import streamlit as st
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        pass
    return os.environ.get(name, default)


def model_name() -> str:
    return _setting("GROQ_MODEL") or DEFAULT_MODEL


def ai_available() -> bool:
    return bool(_setting("GROQ_API_KEY"))


def _groq_json(system: str, user: str, max_tokens: int = 4000) -> dict:
    from groq import Groq  # imported lazily so the app runs without the package configured

    client = Groq(api_key=_setting("GROQ_API_KEY"), timeout=30.0, max_retries=1)
    resp = client.chat.completions.create(
        model=model_name(),
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.2,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
    )
    return json.loads(resp.choices[0].message.content)


# ----------------------------------------------------------------------------- brief: fields
def brief_fields(ctx: dict) -> dict[str, str]:
    """Flatten the meeting context into labelled database fields (the ONLY facts the AI may use)."""
    m, a = ctx["meeting"], ctx["account"]
    f: dict[str, str] = {
        "meeting.start": f"{m['start']:%a %d %b %Y %H:%M} ({ctx['event']['timezone']})",
        "meeting.end": f"{m['end']:%H:%M}",
        "meeting.location": m.get("location") or "",
        "meeting.status": m["status"],
        "meeting.objective": m.get("objective") or "",
        "meeting.the_ask": m.get("the_ask") or "",
        "meeting.attendees": "OUR TEAM (internal, not the client): "
                             + ", ".join(f"our {p['role']} {p['name']}" for p in ctx["attendees"]),
        "meeting.follow_up_owner": f"our {ctx['owner']['role']} {ctx['owner']['name']} (internal)",
        "event.name": ctx["event"]["name"],
        "account.name": a["name"],
        "account.type": a["type"],
        "account.ports": a.get("ports") or "",
        "account.region": a["region"],
        "account.tier": {1: "1 (existing client)", 2: "2 (warm intro)", 3: "3 (cold)"}[a["tier"]],
        "account.usage_trend": a.get("usage_trend") or "",
        "account.monthly_spend": f"USD {a['monthly_spend']:,.0f}" if a.get("monthly_spend") else "",
        "account.renewal_date": a.get("renewal_date") or "",
        "account.health_status": a.get("health_status") or "",
    }
    for i, c in enumerate(ctx["contacts"], 1):
        f[f"contacts.{i}"] = (f"CLIENT CONTACT at {a['name']}: {c['name']}, job title '{c['role'] or 'unknown'}'; "
                              "client decision-maker: "
                              f"{'yes' if c['decision_maker'] else 'no'}; attending: {'yes' if c['attending'] else 'no'}")
    for i, n in enumerate(ctx["notes"], 1):
        f[f"notes.{i}"] = f"{n['note_date']} ({n['author'] or 'unknown'}): {n['body']}"
    for i, mt in enumerate(ctx["materials"], 1):
        appr = f"approved by {mt['approved_by']}" if mt["approval_status"] == "approved" else mt["approval_status"].upper()
        f[f"materials.{i}"] = f"{mt['name']} ({mt['type']}) — {appr}"
    for i, d in enumerate(ctx.get("prior_debriefs", []), 1):
        f[f"prior_debriefs.{i}"] = (f"{d['event_code']} {d['start_at'][:10]}: interest {d['interest_level']}; "
                                    f"objections: {d['objections'] or 'none'}; next step: {d['next_step']} by {d['next_step_date']}")
    return {k: v for k, v in f.items() if v not in (None, "")} | {
        k: "NOT IN DATABASE" for k, v in f.items() if v in (None, "")}


def deterministic_unverified(ctx: dict) -> list[str]:
    """Rule-based flags that are always shown, independent of the AI."""
    out: list[str] = []
    m, a = ctx["meeting"], ctx["account"]
    mdate = m["start"].date()
    attending = [c for c in ctx["contacts"] if c["attending"]]
    if not attending:
        out.append("No client attendees recorded — who will be in the room is unverified")
    elif not any(c["decision_maker"] for c in attending):
        out.append("No decision-maker recorded as attending — authority to agree 'the one ask' is unverified")
    if not ctx["notes"]:
        out.append("No previous conversation notes on record")
    for n in ctx["notes"]:
        age = (mdate - date.fromisoformat(n["note_date"])).days
        if age > 180:
            out.append(f"Note from {n['note_date']} is {age // 30} months old — may be out of date")
    if a["tier"] == 1:
        for fld in ("monthly_spend", "renewal_date", "usage_trend"):
            if not a.get(fld) or a.get(fld) == "n/a":
                out.append(f"Existing client but {fld.replace('_', ' ')} is missing from the database")
    for mt in ctx["materials"]:
        if mt["approval_status"] != "approved":
            out.append(f"'{mt['name']}' is {mt['approval_status']} — not approved for client use")
    if not (m.get("the_ask") or "").strip():
        out.append("'The one ask' is not set for this meeting")
    return out


def _clean_citations(markdown: str, valid: set[str]) -> tuple[str, list[str], list[str]]:
    used, bad = [], []

    def repl(mt: re.Match) -> str:
        key = mt.group(1)
        # allow citing a whole group, e.g. [notes] or [materials]
        if key in valid or any(v.startswith(key + ".") for v in valid):
            used.append(key)
            return mt.group(0)
        bad.append(key)
        return "[unverified]"

    return CITE_RE.sub(repl, markdown), used, bad


# ----------------------------------------------------------------------------- brief: template
def template_brief(ctx: dict, fields: dict[str, str]) -> tuple[str, list[str]]:
    m, a = ctx["meeting"], ctx["account"]
    used: list[str] = []

    def cite(*keys: str) -> str:
        used.extend(keys)
        return " [" + "] [".join(keys) + "]"

    lines = [
        "#### Snapshot",
        f"**{a['name']}** — {a['type']}, {fields['account.tier']}, {a['region']}; ports: {a.get('ports') or 'n/a'}."
        + cite("account.name", "account.type", "account.tier", "account.ports"),
        f"Objective: {m.get('objective') or 'not set'}." + cite("meeting.objective"),
        "", "#### Account health",
    ]
    if a.get("monthly_spend"):
        lines.append(f"Usage **{a['usage_trend']}**, spend {fields['account.monthly_spend']}/month, renewal "
                     f"**{a.get('renewal_date') or 'not recorded'}**, health **{a['health_status']}**."
                     + cite("account.usage_trend", "account.monthly_spend", "account.renewal_date", "account.health_status"))
    else:
        lines.append(f"Not a current client — health status **{a['health_status']}**; no spend on record."
                     + cite("account.health_status"))
    lines += ["", "#### Who's in the room"]
    for i, c in enumerate(ctx["contacts"], 1):
        if c["attending"]:
            lines.append(f"- {c['name']}, {c['role']}" + (" — **decision-maker**" if c["decision_maker"] else "")
                         + cite(f"contacts.{i}"))
    lines.append(f"- Ours: {fields['meeting.attendees']}" + cite("meeting.attendees"))
    if ctx["notes"]:
        lines += ["", "#### What we already know"]
        for i, n in enumerate(ctx["notes"][:3], 1):
            lines.append(f"- {n['note_date']}: {n['body']}" + cite(f"notes.{i}"))
    if ctx.get("prior_debriefs"):
        lines += ["", "#### Earlier meetings"]
        for i, d in enumerate(ctx["prior_debriefs"][:2], 1):
            lines.append(f"- {d['start_at'][:10]}: interest {d['interest_level']}; objections: {d['objections'] or 'none'}; "
                         f"next step: {d['next_step']}" + cite(f"prior_debriefs.{i}"))
    if ctx["materials"]:
        lines += ["", "#### Materials"]
        for i, mt in enumerate(ctx["materials"], 1):
            ok = mt["approval_status"] == "approved"
            lines.append(f"- {'✅' if ok else '⚠️'} {mt['name']} — {'approved' if ok else mt['approval_status'] + ', do not share'}"
                         + cite(f"materials.{i}"))
    lines += ["", "#### The one ask",
              f"**{m.get('the_ask') or 'Not set — agree before the meeting'}**" + cite("meeting.the_ask"),
              f"Follow-up owner: {fields['meeting.follow_up_owner']}." + cite("meeting.follow_up_owner")]
    return "\n".join(lines), list(dict.fromkeys(used))


BRIEF_SYSTEM = """You write pre-meeting briefs for senior executives at a commodities trading firm launching
"Flux Bunkers" (a digital bunker-fuel ordering product) at new ports.

STRICT RULES
1. Use ONLY facts present in the FIELDS JSON. Never add companies, people, numbers, dates, history or
   market facts that are not in FIELDS. If you are unsure, leave it out.
2. After every factual sentence or bullet, cite the field keys used in square brackets, e.g. [account.tier] [notes.2].
3. Fields whose value is "NOT IN DATABASE" are unknown: say so, and list them in "unverified".
4. Anything inferred rather than stated (e.g. likely objections) must be labelled "(unverified)" in the text
   and listed in "unverified".
5. Materials that are not approved must be flagged "do not share".
6. Keep the two sides separate. "meeting.attendees" and "meeting.follow_up_owner" are OUR internal team;
   "contacts.*" are the CLIENT's people. The decision-maker flag applies only to client contacts — never call
   our own people decision-makers. Write client contacts' job titles in full (e.g. "Chief Commercial Officer",
   never "CCO", which would be confused with our CCO). In "Who's in the room" use two sub-lists:
   "Client:" and "Ours:".

Return JSON only: {"brief_markdown": string, "fields_used": [field keys], "unverified": [short strings]}.
brief_markdown uses these #### headings in order: Snapshot, Account health, Who's in the room,
What we already know, Materials, The one ask (include the follow-up owner). Max ~250 words, crisp, scannable."""

LEARNINGS_TIERS = """Tier definitions (a fixed relationship status, not a score that meetings can raise):
tier 1 = existing client, tier 2 = warm introduction, tier 3 = cold prospect."""


def generate_brief(ctx: dict) -> LLMResult:
    fields = brief_fields(ctx)
    valid = set(fields)
    rules = deterministic_unverified(ctx)
    note = None
    if ai_available():
        try:
            out = _groq_json(BRIEF_SYSTEM, "FIELDS:\n" + json.dumps(fields, indent=1, ensure_ascii=False))
            md, cited, bad = _clean_citations(str(out.get("brief_markdown", "")), valid)
            if not md.strip():
                raise ValueError("empty brief")
            used = [k for k in out.get("fields_used", []) if isinstance(k, str) and k in valid]
            used = list(dict.fromkeys(used + [c for c in cited if c in valid]))
            unv = [str(u) for u in out.get("unverified", []) if str(u).strip()]
            if bad:
                unv.append(f"AI cited unknown field(s) {', '.join(sorted(set(bad)))} — replaced with [unverified]")
            return LLMResult({"markdown": md}, f"groq:{model_name()}", None, used,
                             list(dict.fromkeys(rules + unv)))
        except Exception as exc:  # noqa: BLE001 — any failure falls back
            note = f"AI unavailable ({type(exc).__name__}); template used"
    else:
        note = "No GROQ_API_KEY set; template used"
    md, used = template_brief(ctx, fields)
    return LLMResult({"markdown": md}, "template", note, used, rules)


# ----------------------------------------------------------------------------- debrief → notes + email
DEBRIEF_SYSTEM = """You turn a salesperson's quick post-meeting debrief into structured CRM notes and a short
follow-up email. Use ONLY information in MEETING and DEBRIEF. Do not invent commitments, prices, dates or
people. The email is from the follow-up owner to the primary client contact, warm and concise (<120 words),
confirming only the agreed next step and date, and must not promise anything not in DEBRIEF.

Return JSON only:
{"summary": string (2-3 sentences), "interest": "low"|"medium"|"high",
 "objections": [string], "risks": [string], "open_questions": [string],
 "email_subject": string, "email_body": string}"""


def _template_debrief(meeting: dict, form: dict, owner: dict, contact_name: str) -> dict:
    objections = [o.strip() for o in (form.get("objections") or "").split(";") if o.strip()]
    return {
        "summary": form["what_happened"].strip(),
        "interest": form["interest_level"],
        "objections": objections,
        "risks": (["No decision-maker present — confirm authority before the next step"]
                  if not form["decision_maker_present"] else []),
        "open_questions": [],
        "email_subject": f"Flux Bunkers – next steps ({meeting['account']})",
        "email_body": (f"Dear {contact_name.split()[0] if contact_name else 'team'},\n\n"
                       f"Thank you for your time today. As agreed, the next step is: {form['next_step'].strip().rstrip('.')}, "
                       f"by {form['next_step_date']}.\n\n"
                       "Please let me know if anything changes on your side.\n\n"
                       f"Kind regards,\n{owner['name']}\n{owner['role']}"),
    }


def structured_notes_markdown(d: dict, form: dict) -> str:
    def bullets(xs):
        return "\n".join(f"- {x}" for x in xs) if xs else "- None"

    return (f"**Summary:** {d['summary']}\n\n**Interest:** {form['interest_level']}\n\n"
            f"**Objections:**\n{bullets(d['objections'])}\n\n"
            f"**Agreed next step:** {form['next_step']} (by {form['next_step_date']})\n\n"
            f"**Decision-maker present:** {'Yes' if form['decision_maker_present'] else 'No'} · "
            f"**App sign-up:** {'Yes' if form.get('app_signup') else 'No'} · "
            f"**Trial started:** {'Yes' if form.get('trial_started') else 'No'}\n\n"
            f"**Risks / open questions:**\n{bullets(d.get('risks', []) + d.get('open_questions', []))}")


def structure_debrief(meeting: dict, form: dict, owner: dict, contact_name: str) -> LLMResult:
    """Returns content with keys: notes_markdown, email_subject, email_body (+ raw parts)."""
    note = None
    d = None
    if ai_available():
        try:
            payload = {
                "MEETING": {"account": meeting["account"], "objective": meeting.get("objective"),
                            "the_ask": meeting.get("the_ask"), "date": f"{meeting['start']:%d %b %Y}",
                            "primary_contact": contact_name, "follow_up_owner": f"{owner['name']}, {owner['role']}"},
                "DEBRIEF": form,
            }
            d = _groq_json(DEBRIEF_SYSTEM, json.dumps(payload, ensure_ascii=False, default=str))
            for k in ("summary", "email_subject", "email_body"):
                if not str(d.get(k, "")).strip():
                    raise ValueError(f"missing {k}")
            d["objections"] = [str(x) for x in d.get("objections") or []]
            d["risks"] = [str(x) for x in d.get("risks") or []]
            d["open_questions"] = [str(x) for x in d.get("open_questions") or []]
            gen = f"groq:{model_name()}"
        except Exception as exc:  # noqa: BLE001
            note = f"AI unavailable ({type(exc).__name__}); template used"
            d = None
    else:
        note = "No GROQ_API_KEY set; template used"
    if d is None:
        d = _template_debrief(meeting, form, owner, contact_name)
        gen = "template"
    # The form is the source of truth for these fields, whatever the model said.
    d["interest"] = form["interest_level"]
    content = {"notes_markdown": structured_notes_markdown(d, form), "email_subject": d["email_subject"],
               "email_body": d["email_body"], "parts": d}
    return LLMResult(content, gen, note)


# ----------------------------------------------------------------------------- IBIA → FUJCON learnings
OBJECTION_PLAYBOOK = {
    "price": "Get the launch pricing sheet approved before FUJCON and lead with total-cost comparison vs broker fees.",
    "integration": "Bring the API integration pack and a technical lead to meetings with IT-heavy accounts.",
    "credit": "Pre-clear indicative credit ranges with the credit team for Gulf prospects before meetings.",
    "port coverage": "Approve the Fujairah launch deck early — coverage was a blocker in New York.",
    "security": "Approve the Security & data FAQ and send it before meetings, not after.",
    "contract": "Target accounts approaching renewal windows; deprioritise those locked into broker contracts.",
    "sign-off": "Insist on a decision-maker in the room — book DMs, not just operators.",
}


def _objection_key(text: str) -> str:
    t = text.lower()
    for k in ("price", "integration", "credit", "port coverage", "security", "contract", "sign-off"):
        if k in t:
            return k
    return "other"


def template_learnings(stats: dict) -> str:
    conv = stats["conversion_by_tier"]
    best = max(conv, key=lambda r: r["signup_rate"]) if conv else None
    lines = ["#### What IBIA told us"]
    for r in conv:
        lines.append(f"- Tier {r['tier']}: {r['held']} held → {r['signups']} sign-ups ({r['signup_rate']:.0f}%), "
                     f"{r['trials']} trials ({r['trial_rate']:.0f}%)")
    if stats.get("dm_effect"):
        e = stats["dm_effect"]
        lines.append(f"- With a decision-maker present, sign-up rate was **{e['with']:.0f}%** vs **{e['without']:.0f}%** without.")
    if stats["top_objections"]:
        lines.append("- Most common objections: " + ", ".join(f"{o} ({n})" for o, n in stats["top_objections"][:4]) + ".")
    lines += ["", "#### Recommendations for FUJCON"]
    if best:
        lines.append(f"1. Weight the FUJCON list towards **tier {best['tier']}** accounts — best sign-up conversion at IBIA.")
    n = 2
    seen = set()
    for o, _ in stats["top_objections"][:4]:
        k = _objection_key(o)
        if k in OBJECTION_PLAYBOOK and k not in seen:
            seen.add(k)
            lines.append(f"{n}. {OBJECTION_PLAYBOOK[k]}")
            n += 1
    if stats.get("dm_effect") and stats["dm_effect"]["with"] > stats["dm_effect"]["without"]:
        lines.append(f"{n}. Only confirm FUJCON meetings where a decision-maker is named in the invite.")
        n += 1
    if stats.get("candidates"):
        names = ", ".join(c["name"] for c in stats["candidates"][:5])
        lines.append(f"{n}. Priority Gulf targets not yet booked at FUJCON: {names}.")
    return "\n".join(lines)


LEARNINGS_SYSTEM = """You are a sales-strategy analyst. Using ONLY the STATS and DEBRIEFS JSON provided
(fictional demo data), write a concise markdown summary of what the IBIA convention taught the team and
specific recommendations for the FUJCON (Fujairah) target list. Do not invent numbers, accounts or facts;
only reference accounts listed in STATS.candidates or DEBRIEFS. Mark any inference as "(inference)".
STATS.candidates are Gulf accounts NOT yet booked at FUJCON — recommend which to book first and why.
STATS.dm_effect is the app sign-up rate (%) with vs without a client decision-maker present.

""" + LEARNINGS_TIERS + """

Return JSON only: {"markdown": string} using two #### headings: "What IBIA told us" and
"Recommendations for FUJCON" (numbered list, max 6 items, each actionable). Max ~250 words."""


def learnings_summary(stats: dict, debrief_lines: list[dict]) -> LLMResult:
    note = None
    if ai_available() and debrief_lines:
        try:
            out = _groq_json(LEARNINGS_SYSTEM, json.dumps({"STATS": stats, "DEBRIEFS": debrief_lines},
                                                          ensure_ascii=False, default=str))
            md = str(out.get("markdown", "")).strip()
            if not md:
                raise ValueError("empty")
            return LLMResult({"markdown": md}, f"groq:{model_name()}")
        except Exception as exc:  # noqa: BLE001
            note = f"AI unavailable ({type(exc).__name__}); template used"
    elif not ai_available():
        note = "No GROQ_API_KEY set; template used"
    return LLMResult({"markdown": template_learnings(stats)}, "template", note)


def objection_counts(objection_strings: list[str]) -> list[tuple[str, int]]:
    c = Counter(o.strip() for s in objection_strings for o in (s or "").split(";") if o.strip())
    return c.most_common()


# ----------------------------------------------------------------------------- travel summary
TRAVEL_SYSTEM = """You write a short travel briefing for one executive of a commodities trading firm, from
London Ops. Use ONLY the FIELDS JSON provided (database values). Never invent flights, times, names,
phone numbers or addresses. Do not include booking references (they are not provided on purpose).

Rules:
1. Second person, plain and practical, like a PA's message: e.g. "You land at 18:40, pickup at 19:30,
   check in at <hotel>, first meeting 09:30 tomorrow."
2. Keep it under 120 words: a 2–4 sentence paragraph in time order (fly, land, transfer, hotel, first
   meetings, return), then "**Watch out:**" bullets for any alerts.* fields (skip if alerts.none).
3. After each fact, cite the field key(s) in square brackets, e.g. [outbound.lands]. Only cite keys in FIELDS.
4. Use event-local times as given; you may add London time in brackets where the field has it.
5. If something needed is missing or 'not recorded', say so plainly rather than guessing.

Return JSON: {"summary_markdown": str, "fields_used": [field keys]}"""


def template_travel_summary(fields: dict[str, str]) -> tuple[str, list[str]]:
    """Deterministic briefing from the same fields (used without a key or when Groq fails)."""
    used: list[str] = []

    def g(key: str) -> str | None:
        if key in fields and fields[key]:
            used.append(key)
            return f"{fields[key]} [{key}]"
        return None

    parts = []
    if g("outbound.flight"):
        parts.append(f"You fly {fields['outbound.flight']} [outbound.flight], departing {g('outbound.departs')} "
                     f"and landing {g('outbound.lands')}" + (f" (status: {g('outbound.status')})"
                                                             if "delayed" in fields.get("outbound.status", "") else "")
                     + ".")
    if "arrival_transfer.pickup" in fields:
        parts.append(f"Pickup {g('arrival_transfer.pickup')} with {g('arrival_transfer.provider')}; driver "
                     f"{g('arrival_transfer.driver')}; about {fields['arrival_transfer.duration'].split(' (')[0]} "
                     f"[arrival_transfer.duration].")
        used.append("arrival_transfer.duration")
    if "hotel.name" in fields:
        tbc = fields.get("hotel.to_venue", "").startswith("venue TBC")
        venue = g("hotel.to_venue") if tbc else f"{g('hotel.to_venue')} to the venue"
        parts.append(f"Check in at {g('hotel.name')} ({g('hotel.address')}) from {g('hotel.check_in')}; {venue}.")
    if "meetings.m1" in fields:
        parts.append(f"First meeting: {g('meetings.m1')}." + (f" Then {g('meetings.m2')}." if "meetings.m2" in fields else ""))
    if "return.flight" in fields:
        parts.append(f"Home on {fields['return.flight']} [return.flight] departing {g('return.departs')}"
                     + (f"; leave the hotel by {g('departure_transfer.pickup')}" if "departure_transfer.pickup" in fields else "")
                     + ".")
    md = " ".join(parts) or "No travel booked yet."
    alerts = [k for k in fields if k.startswith("alerts.a")]
    if alerts:
        md += "\n\n**Watch out:**\n" + "\n".join(f"- {fields[k]} [{k}]" for k in alerts)
        used += alerts
    return md, list(dict.fromkeys(used))


def travel_summary(fields: dict[str, str]) -> LLMResult:
    valid = set(fields)
    note = None
    if ai_available():
        try:
            out = _groq_json(TRAVEL_SYSTEM, "FIELDS:\n" + json.dumps(fields, indent=1, ensure_ascii=False),
                             max_tokens=2500)
            md, cited, bad = _clean_citations(str(out.get("summary_markdown", "")), valid)
            if not md.strip():
                raise ValueError("empty summary")
            used = [k for k in out.get("fields_used", []) if isinstance(k, str) and k in valid]
            used = list(dict.fromkeys(used + [c for c in cited if c in valid]))
            unv = [f"AI cited unknown field(s) {', '.join(sorted(set(bad)))} — replaced with [unverified]"] if bad else []
            return LLMResult({"markdown": md}, f"groq:{model_name()}", None, used, unv)
        except Exception as exc:  # noqa: BLE001 — any failure falls back
            note = f"AI unavailable ({type(exc).__name__}); template used"
    else:
        note = "No GROQ_API_KEY set; template used"
    md, used = template_travel_summary(fields)
    return LLMResult({"markdown": md}, "template", note, used, [])
