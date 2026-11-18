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
_REPL = {"–": "-", "—": "-", "→": "->", "’": "'", "‘": "'", "“": '"', "”": '"', "…": "...", "★": "*",
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
