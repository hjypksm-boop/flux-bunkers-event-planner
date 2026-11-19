"""Offline exports for My Day: a self-contained HTML page and a PDF (fpdf2, core fonts)."""
from __future__ import annotations

import html
from datetime import datetime

from fpdf import FPDF

from services import clock


def _e(x) -> str:
    return html.escape("" if x is None else str(x))


def day_items(person_id: int, meetings: list[dict], sessions: list[dict], day: str | None) -> list[dict]:
    """Merge a person's meetings and must-attend sessions for one day (or all days if day is None)."""
    items = []
    for m in meetings:
        if person_id in m["people"] and (day is None or m["start_at"][:10] == day):
            items.append({**m, "item_type": "meeting"})
    for s in sessions:
        if person_id in s["attendees"] and (day is None or s["start_at"][:10] == day):
            items.append({**s, "item_type": "session"})
    return sorted(items, key=lambda x: x["start_at"])


def build_html(person: dict, ev: dict, items: list[dict], contexts: dict[int, dict], title_day: str) -> str:
    rows = []
    last_day = None
    for it in items:
        d = it["start"].strftime("%A %d %B %Y")
        if d != last_day:
            rows.append(f'<h2>{_e(d)}</h2>')
            last_day = d
        ldn = f"{clock.local_to_tz(it['start'], ev['timezone'], clock.LONDON):%H:%M}"
        t = f"{it['start']:%H:%M}–{it['end']:%H:%M}"
        if it["item_type"] == "session":
            rows.append(f'<div class="card session"><div class="time">{t} <span class="ldn">London {ldn}</span></div>'
                        f'<div><b>★ {_e(it["title"])}</b> — must attend{" (TBC)" if it["tbc"] else ""}'
                        f'<div class="meta">{_e(it["location"])}</div></div></div>')
            continue
        ctx = contexts.get(it["id"], {})
        contacts = ", ".join(f"{c['name']} ({c['role']}{', DM' if c['decision_maker'] else ''})"
                             for c in ctx.get("contacts", []) if c["attending"]) or "Not recorded"
        mats = "".join(f"<li>{'✔' if m['approval_status'] == 'approved' else '⚠ ' + m['approval_status'].upper() + ' – do not share:'} "
                       f"{_e(m['name'])}</li>" for m in ctx.get("materials", []))
        acc = ctx.get("account", {})
        health = (f"{acc.get('health_status')} · usage {acc.get('usage_trend')} · renewal {acc.get('renewal_date') or 'n/a'}"
                  if acc else "")
        cls = "card cancelled" if it["status"] == "cancelled" else "card"
        rows.append(
            f'<div class="{cls}"><div class="time">{t} <span class="ldn">London {ldn}</span></div><div>'
            f'<b>{_e(it["account"])}</b> <span class="pill">{_e(it["status"])}</span> <span class="tier">Tier {it["tier"]}</span>'
            f'<div class="meta">📍 {_e(it["location"])} · with {_e(it["people_roles"])}</div>'
            f'<div><b>Objective:</b> {_e(it["objective"])}</div>'
            f'<div class="ask"><b>The one ask:</b> {_e(it["the_ask"])}</div>'
            f'<div class="meta"><b>Client side:</b> {_e(contacts)}</div>'
            f'<div class="meta"><b>Account:</b> {_e(health)}</div>'
            + (f'<ul class="mats">{mats}</ul>' if mats else "") + "</div></div>")
    body = "\n".join(rows) or "<p>No meetings.</p>"
    generated = datetime.now().strftime("%d %b %Y %H:%M")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>My Day – {_e(person['role'])} – {_e(ev['name'])}</title>
<style>
body{{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;margin:0;background:#15171C;color:#E8E6E3}}
header{{background:#1F232B;padding:16px;border-bottom:3px solid #E3A008}}
header h1{{margin:0;font-size:20px}} header p{{margin:4px 0 0;color:#9AA0A8;font-size:13px}}
.demo{{background:rgba(227,160,8,.15);color:#E3A008;padding:6px 16px;font-size:12px}}
main{{padding:12px 16px;max-width:720px;margin:auto}}
h2{{font-size:15px;color:#E3A008;margin:18px 0 8px}}
.card{{background:#1F232B;border:1px solid #2A2F38;border-left:4px solid {person['colour']};border-radius:10px;padding:10px 12px;margin:8px 0;display:grid;grid-template-columns:96px 1fr;gap:10px;font-size:14px}}
.card.session{{border-left-color:#14A3A8;background:#18262A}}
.card.cancelled{{opacity:.55;text-decoration:line-through}}
.time{{font-weight:700}} .ldn{{display:block;font-weight:400;color:#9AA0A8;font-size:12px}}
.meta{{color:#9AA0A8;font-size:13px;margin:2px 0}}
.ask{{background:rgba(227,160,8,.12);border-left:3px solid #E3A008;padding:4px 8px;margin:6px 0;border-radius:4px}}
.pill{{font-size:11px;border:1px solid #9AA0A8;border-radius:99px;padding:0 6px;color:#9AA0A8}}
.tier{{font-size:11px;color:#E3A008}}
.mats{{margin:4px 0 0 18px;padding:0;font-size:12px;color:#C9CCD1}}
@media (max-width:480px){{.card{{grid-template-columns:1fr}}}}
@media print{{body{{background:#fff;color:#111}} header,.card{{background:#fff}} .meta,.ldn{{color:#555}}}}
</style></head><body>
<div class="demo">Demo data – fictitious</div>
<header><h1>My Day · {_e(person['role'])} — {_e(person['name'])}</h1>
<p>{_e(ev['name'])} · {_e(title_day)} · times in {_e(ev['city'])} local (London shown beneath) · generated {generated}</p></header>
<main>{body}</main></body></html>"""


# ----------------------------------------------------------------------------- PDF
_REPL = {"–": "-", "—": "-", "→": "->", "’": "'", "‘": "'", "“": '"', "”": '"', "…": "...", "★": "*", "•": "*",
         "✔": "OK", "⚠": "!", "·": "-", "📍": "", " ": " "}


def _latin1(text) -> str:
    s = "" if text is None else str(text)
    for k, v in _REPL.items():
        s = s.replace(k, v)
    return s.encode("latin-1", "replace").decode("latin-1")


def build_pdf(person: dict, ev: dict, items: list[dict], contexts: dict[int, dict], title_day: str) -> bytes:
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.add_page()
    pdf.set_fill_color(227, 160, 8)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 6, _latin1("DEMO DATA - FICTITIOUS"), fill=True, new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 8, _latin1(f"My Day - {person['role']} ({person['name']})"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(90, 90, 90)
    pdf.cell(0, 6, _latin1(f"{ev['name']} - {title_day} - times in {ev['city']} local (London in brackets)"),
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    last_day = None
    w = pdf.w - pdf.l_margin - pdf.r_margin
    for it in items:
        d = it["start"].strftime("%A %d %B %Y")
        if d != last_day:
            pdf.ln(3)
            pdf.set_font("Helvetica", "B", 12)
            pdf.set_text_color(160, 110, 0)
            pdf.cell(0, 7, _latin1(d), new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0, 0, 0)
            last_day = d
        ldn = f"{clock.local_to_tz(it['start'], ev['timezone'], clock.LONDON):%H:%M}"
        t = f"{it['start']:%H:%M}-{it['end']:%H:%M} (London {ldn})"
        pdf.set_font("Helvetica", "B", 10)
        if it["item_type"] == "session":
            pdf.multi_cell(w, 5, _latin1(f"{t}   * {it['title']} - must attend{' (TBC)' if it['tbc'] else ''}"),
                           new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1)
            continue
        pdf.multi_cell(w, 5, _latin1(f"{t}   {it['account']}  [{it['status']}, tier {it['tier']}]"),
                       new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        ctx = contexts.get(it["id"], {})
        contacts = ", ".join(f"{c['name']} ({c['role']}{', DM' if c['decision_maker'] else ''})"
                             for c in ctx.get("contacts", []) if c["attending"]) or "Not recorded"
        lines = [f"Location: {it['location']}   With: {it['people_roles']}",
                 f"Objective: {it['objective']}",
                 f"THE ONE ASK: {it['the_ask']}",
                 f"Client side: {contacts}"]
        for m in ctx.get("materials", []):
            ok = m["approval_status"] == "approved"
            lines.append(f"  {'[approved]' if ok else '[' + m['approval_status'].upper() + ' - do not share]'} {m['name']}")
        for ln in lines:
            pdf.multi_cell(w, 4.6, _latin1(ln), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
    if not items:
        pdf.cell(0, 8, "No meetings.", new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


# ----------------------------------------------------------------------------- travel itinerary
def itinerary(ev: dict, person: dict, viewer: dict | None) -> dict:
    """One person's trip, day by day: flights, hotel, transfers and meetings (event-local times).

    Booking references are masked unless the viewer is the traveller or London Ops.
    """
    from services import data, travel
    show_ref = travel.can_see_ref(viewer, person["id"])
    tz = ev["timezone"]
    days: dict[str, list[dict]] = {}

    def add(dt: datetime, entry: dict) -> None:
        entry["ldn"] = f"{clock.local_to_tz(dt, tz, clock.LONDON):%H:%M}"
        entry["sort"] = dt
        days.setdefault(dt.date().isoformat(), []).append(entry)

    for f in [x for x in travel.flights(ev["id"], ev) if x["person_id"] == person["id"]]:
        delay = f" · DELAYED {f['delay_minutes']} min" if f["status"] == "delayed" else ""
        add(f["dep_ev"], dict(icon="✈", time=f"{f['dep_ev']:%H:%M}",
                              title=f"{f['flight_no']} {f['dep_airport']} → {f['arr_airport']} ({f['airline']})",
                              detail=f"Departs {f['dep_eff']:%a %d %b %H:%M} {f['dep_airport']} T{(f['dep_terminal'] or 'BC').lstrip('T')}"
                                     f" · lands {f['arr_eff']:%a %d %b %H:%M} {f['arr_airport']} "
                                     f"T{(f['arr_terminal'] or 'BC').lstrip('T')} (airport local times)"
                                     f" · seat {f['seat'] or '—'} · ref {travel.mask(f['booking_ref'], show_ref)}{delay}",
                              status=f["status"]))
    for h in [x for x in travel.hotels(ev["id"], ev) if x["person_id"] == person["id"]]:
        venue = (f"{h['travel_min_to_venue']} min to venue" if h["travel_min_to_venue"] else "venue TBC")
        for what, dt in (("Check-in", h["check_in_ev"]), ("Check-out", h["check_out_ev"])):
            add(dt, dict(icon="🏨", time=f"{dt:%H:%M}", title=f"{what}: {h['name']}",
                         detail=f"{h['address'] or ''} · {h['phone'] or ''} · {venue} · ref "
                                f"{travel.mask(h['booking_ref'], show_ref)}", status=h["status"]))
    for t in [x for x in travel.transfers(ev["id"], ev) if x["person_id"] == person["id"]]:
        add(t["start_ev"], dict(icon="🚗", time=f"{t['start_ev']:%H:%M}", title=travel.transfer_label(t),
                                detail=f"{t['pickup_place']} → {t['dropoff_place']} · ~{t['est_minutes']} min · "
                                       f"{t['provider'] or 'provider TBC'} · driver: {t['driver_contact'] or 'TBC'}",
                                status=t["status"]))
    for m in data.meetings(ev["id"]):
        if person["id"] in m["people"] and m["status"] != "cancelled":
            add(m["start"], dict(icon="●", time=f"{m['start']:%H:%M}–{m['end']:%H:%M}", title=m["account"],
                                 detail=f"{m['location'] or ''} · with {m['people_roles']} · ask: {m['the_ask'] or '—'}",
                                 status=m["status"]))
    for v in days.values():
        v.sort(key=lambda e: e["sort"])
    docs = [d for d in travel.docs(ev["id"]) if d["person_id"] == person["id"]]
    return {"days": dict(sorted(days.items())), "docs": docs}


def build_itinerary_html(person: dict, ev: dict, it: dict) -> str:
    blocks = []
    for day, entries in it["days"].items():
        rows = "".join(
            f'<tr class="{_e(e["icon"] != "●" and "travel" or "meeting")}"><td class="t">{_e(e["time"])}'
            f'<span>LDN {_e(e["ldn"])}</span></td><td class="i">{_e(e["icon"])}</td>'
            f'<td><b>{_e(e["title"])}</b> <em>{_e(e["status"])}</em><div>{_e(e["detail"])}</div></td></tr>'
            for e in entries)
        blocks.append(f"<h2>{datetime.fromisoformat(day):%A %d %B}</h2><table>{rows}</table>")
    docs = " · ".join(f"{_e(d['item'])}: <b>{_e(d['status'])}</b>" for d in it["docs"]) or "—"
    generated = datetime.now().strftime("%d %b %Y %H:%M")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Itinerary – {_e(person['role'])} – {_e(ev['name'])}</title>
<style>
body{{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;margin:0;background:#fff;color:#15171C;font-size:12px}}
header{{padding:10px 16px;border-bottom:3px solid #E3A008}} header h1{{margin:0;font-size:17px}}
header p{{margin:2px 0 0;color:#555}} .demo{{background:#E3A008;color:#15171C;text-align:center;font-weight:700;font-size:10px;padding:2px}}
main{{padding:4px 16px;max-width:780px;margin:auto}} h2{{font-size:13px;color:#0E6E73;margin:10px 0 3px;border-bottom:1px solid #ddd}}
table{{width:100%;border-collapse:collapse}} td{{vertical-align:top;padding:2px 4px}}
td.t{{width:78px;font-weight:700;white-space:nowrap}} td.t span{{display:block;font-weight:400;color:#777;font-size:10px}}
td.i{{width:18px}} td div{{color:#555;font-size:11px}} em{{color:#0E6E73;font-size:10px;font-style:normal;border:1px solid #0E6E73;border-radius:8px;padding:0 4px}}
tr.travel td{{background:#F6F3EA}} .docs{{margin-top:8px;font-size:11px;color:#333}}
@media (max-width:480px){{td.t{{width:60px}}}}
</style></head><body><div class="demo">DEMO DATA – FICTITIOUS</div>
<header><h1>Travel itinerary · {_e(person['role'])} — {_e(person['name'])}</h1>
<p>{_e(ev['name'])} · {_e(ev['city'])} · times in {_e(ev['city'])} local (London beneath) · generated {generated}</p></header>
<main>{''.join(blocks) or '<p>No travel or meetings recorded.</p>'}
<div class="docs"><b>Document checklist (status only):</b> {docs}</div></main></body></html>"""


def build_itinerary_pdf(person: dict, ev: dict, it: dict) -> bytes:
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=10)
    pdf.set_margins(12, 10, 12)
    pdf.add_page()
    pdf.set_fill_color(227, 160, 8)
    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(0, 5, "DEMO DATA - FICTITIOUS", fill=True, new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 7, _latin1(f"Travel itinerary - {person['role']} ({person['name']})"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(90, 90, 90)
    pdf.cell(0, 4.5, _latin1(f"{ev['name']} - times in {ev['city']} local (London in brackets)"),
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    w = pdf.w - pdf.l_margin - pdf.r_margin
    icon = {"✈": "FLIGHT", "🏨": "HOTEL", "🚗": "CAR", "●": "MEETING"}
    for day, entries in it["days"].items():
        pdf.ln(1.5)
        pdf.set_font("Helvetica", "B", 9.5)
        pdf.set_text_color(14, 110, 115)
        pdf.cell(0, 5, _latin1(f"{datetime.fromisoformat(day):%A %d %B}"), new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
        for e in entries:
            pdf.set_font("Helvetica", "B", 8.5)
            pdf.multi_cell(w, 4, _latin1(f"{e['time']} (LDN {e['ldn']})  {icon.get(e['icon'], '')}: {e['title']} "
                                         f"[{e['status']}]"), new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", "", 7.5)
            pdf.set_text_color(80, 80, 80)
            pdf.multi_cell(w, 3.6, _latin1("      " + e["detail"]), new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0, 0, 0)
    pdf.ln(2)
    pdf.set_font("Helvetica", "", 8)
    docs = "; ".join(f"{d['item']}: {d['status']}" for d in it["docs"]) or "-"
    pdf.multi_cell(w, 4, _latin1(f"Document checklist (status only): {docs}"), new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())
