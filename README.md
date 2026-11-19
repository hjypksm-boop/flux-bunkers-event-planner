# ⚓ Flux Bunkers Event Planner

A live event planner for the **CEO, CCO and Senior Sales Manager** of a commodities trading firm attending
**IBIA Annual Convention 2026 (New York, 1–3 Dec 2026)** and **FUJCON 2027 (Fujairah, 12–14 Apr 2027)** to launch
*Flux Bunkers* at new ports, run by **London Ops**. It covers meetings and the travel around them: flights,
hotels, ground transfers and document checks.

> **Demo data – fictitious.** Every company, person, email address and figure in this app is invented.
> The IBIA agenda follows the published 2026 programme; times are indicative. FUJCON Days 2–3 are marked TBC.

Built with **Python · Streamlit (multipage) · SQLite (plain SQL) · Plotly · Groq** (optional; templates otherwise).

---

## What's inside

| Page | What it does |
|---|---|
| 🗓️ **Live Diary** | One timeline, three swimlanes (CEO / CCO / SSM). **Flights, hotel check-in/out and transfers** appear as dotted, outlined travel blocks under the meetings (delays and unbooked items outlined in orange/red), and arrival/departure days are selectable. Event sessions as background bands and a *Programme* lane, must-attend sessions hatched in each person's lane, colour **and icon** by status, "now" line. Day selector, **event-local ↔ London** toggle, auto-refresh every 30 s with "last updated", and a **"changes since you last looked"** banner. Click a meeting to open its brief. |
| 📱 **My Day** | Phone-friendly running order for one person, topped by a **Today's travel** card (flight number, times, terminal, hotel + address + map link, pickup time, driver contact, alerts): time (local + London), account, location, objective, *the one ask*, warnings for unapproved materials, link to brief. **Download as HTML or PDF** for offline use, plus a one-page **travel itinerary PDF**. |
| 📋 **Meeting Brief** | Account context, contacts and roles (decision-maker / attending), health (usage trend, spend, renewal countdown), previous notes, earlier debriefs, materials with approval status, the one ask, follow-up owner. **Generate brief** summarises *only* database fields, lists the fields used, and flags anything uncertain as **unverified**. |
| 🛠️ **Ops Console** *(London Ops only)* | Add / edit / move / cancel meetings, all written to `change_log`. **Live clash checker**: same-person overlap, < 15 min buffer, < 30 min between different locations, meeting during a must-attend session, plus the **travel rules** below. **Travel tab**: add / edit / change the status of flights, hotels, transfers, trips and document checks (all logged, so they show in the "changes since you last looked" banner). Mark a flight **delayed** and it lists the meetings it now breaks, with a one-click **move** to the next free slot or **reassign** to a free colleague. **Free-slot finder**: cancelling shows the freed window and ranks reserve-list accounts, with one-click booking. Whole-diary clash report, change-log export. |
| ✍️ **Debrief & Follow-up** | Short post-meeting form (what happened, interest, objections, next step + date, decision-maker present, sign-up, trial). AI turns it into structured notes and drafts the follow-up email; London Ops edits and **approves** (draft → approved → sent). A meeting **can't be marked done without a next-step date**. |
| 📊 **KPI Dashboard** | Meetings booked vs target, % held with a decision-maker, sign-ups, trials (with pace projection), tier mix, cancellations, follow-ups sent within 24 h. A **weekly summary that leads with what's off track** (downloadable Markdown). |
| ✈️ **Travel** | Per event: **readiness score** per person (% of items booked / confirmed / done), **red flags first** (unbooked items, delays, over budget, pending documents, meetings that clash with travel), then per-person flights, hotel, transfers and document checklist. **Budget panel**: cost per person and per event vs budget. Itinerary export (HTML / PDF) and an AI **Travel summary**. |
| 🧭 **IBIA → FUJCON Learnings** | Conversion by tier, most common objections, effect of a decision-maker being present, scored FUJCON target list, and an AI summary with recommendations. |

**Roles:** CEO, CCO and Senior Sales Manager can view everything (and file debriefs). London Ops can edit.

### Travel rules (clash checker)

| Rule | Severity |
|---|---|
| Meeting starts before the flight lands + 2 h (immigration + transfer). Uses the **delayed** landing time. | error |
| Meeting ends after the latest hotel departure for the return flight (departure − 3 h airport − drop-off time) | error |
| Meeting during a ground transfer | error |
| Meeting before 09:00 local on the day after a long-haul (6 h +) arrival: jet lag | warning |
| A night between landing and the return flight with no booked hotel; an arrival or departure with no booked transfer; a pickup before a delayed landing | error / warning |

### Privacy

* **No passport, ID, card or bank details** exist anywhere: there are no columns for them (a test checks the schema),
  and the document checklist stores status only (`done` / `pending` / `not needed`).
* **Booking references** are shown only to the traveller and London Ops; everyone else sees `••••KD`. They are
  never sent to the AI and are written to the change log as "(hidden)".

**Demo clock:** IBIA hasn't happened yet, so by default the app runs on a clock frozen at
**Wed 2 Dec 2026 15:30 New York**. Day 1 and Wednesday-morning meetings are therefore "done" with debriefs and
follow-ups, and the rest of the diary is live. Toggle it off in the sidebar, or set `DEMO_CLOCK=off`.

---

## Run locally

Requires Python 3.10+ (tested on 3.15).

```bash
# 1. Create a virtual environment
python3 -m venv ~/.venvs/flux-bunkers        # see note below about ':' in folder names
source ~/.venvs/flux-bunkers/bin/activate

# 2. Install
pip install -r requirements.txt

# 3. Configure (optional — everything works without it)
cp .env.example .env        # add GROQ_API_KEY and passwords if you want them

# 4. Run
streamlit run app.py --server.port 8599
```

Streamlit then opens the app in your browser at `http://localhost:8599`. That address only works on the machine
running the app; for a shareable link, see [Deploy to Streamlit Community Cloud](#deploy-to-streamlit-community-cloud).
If no passwords are configured, the login screen shows the demo credentials
(`flux-ceo`, `flux-cco`, `flux-ssm`, `flux-ops`).

The SQLite database (`data/flux_bunkers.db`) is created and seeded automatically on first run. An existing
database is **migrated** on start-up: new tables are added and travel data is seeded only if they are empty, so
your meetings, debriefs and change log are kept.
**Reset the demo data** at any time with:

```bash
python -m db.seed
```

> **Note:** Python refuses to create a venv *inside* a path containing `:` (for example a folder called
> `IBIA:FUJ`). That's why the commands above put the venv in `~/.venvs/`. If your folder has no colon,
> `python3 -m venv .venv` is fine.

### Tests

```bash
python -m pytest -q
```

79 tests cover the travel rules (each threshold, delays, drop-off timing, jet lag, missing hotel nights and
transfers), the migration (adds travel, keeps existing data, idempotent), booking-reference masking, the
no-sensitive-columns schema check, travel change logging, delay → meeting suggestions, budget maths, and the clash checker (every rule and its threshold), the free-slot finder and reserve ranking,
the "no done without a next-step date" rule, change-log writes, the follow-up approval flow, the
"changes since you last looked" tracking, KPI maths on the seed data, and the AI guard-rails (Groq is mocked:
invented citations are stripped, failures fall back to templates).

### AI (Groq)

Set `GROQ_API_KEY` (and optionally `GROQ_MODEL`, default `openai/gpt-oss-120b`; `openai/gpt-oss-20b` is faster) in `.env` or Streamlit
secrets. Guard-rails:

* The model only receives a flat dictionary of **database fields** and must cite field keys like `[account.tier]`.
* Citations to keys that don't exist are replaced with **[unverified]**, and the "sources" list is intersected
  with the real keys, so it can never list an invented field.
* Rule-based **unverified** flags are always added, whatever the model says: no decision-maker attending,
  notes older than 6 months, missing health data on existing clients, unapproved materials, no "one ask".
* For debriefs, the form is the source of truth: interest, next step, date and decision-maker presence
  always come from what the person entered.
* **Travel summary** (Travel page): a short PA-style briefing per person ("You land at 16:50, pickup at 17:40,
  check in at …, first meeting 09:30 tomorrow"), built from flight, hotel, transfer, meeting and alert fields
  only, with the same citation checks. Booking references are excluded from what the model sees.
* Missing key, timeout, API error or bad JSON → deterministic template. The app never breaks.

---

## Deploy to Streamlit Community Cloud

1. Push this folder to a GitHub repository. `.gitignore` already excludes `.env` and `*.db`.
2. Go to **share.streamlit.io → Create app**, then pick the repo, the branch and **`app.py`** as the entry point.
3. Under **Advanced settings → Python version**, choose 3.12 (or newer).
4. Under **Secrets**, paste (TOML):
   ```toml
   GROQ_API_KEY = "gsk_..."
   GROQ_MODEL = "openai/gpt-oss-120b"
   PASSWORD_CEO = "choose-one"
   PASSWORD_CCO = "choose-one"
   PASSWORD_SSM = "choose-one"
   PASSWORD_OPS = "choose-one"
   DEMO_CLOCK = "on"
   ```
5. Deploy. The database seeds itself on first boot.

> Community Cloud storage is **ephemeral**: SQLite resets to the seed data when the app restarts or sleeps.
> That suits a demo. For real use, point `db/database.py` at a hosted database (Postgres, Turso, etc.); the
> SQL is plain and portable.

---

## Project structure

```
app.py                     # login, shared sidebar (event switcher, demo clock), role-based navigation
.streamlit/config.toml     # charcoal #15171C / amber #E3A008 / teal #0E6E73 theme
db/
  schema.sql               # all tables (events … reserve_list, plus session_attendees, meeting_contacts, viewer_state)
  database.py              # tiny plain-SQL helper, auto-create + auto-seed
  seed.py                  # fictional seed data; `python -m db.seed` to reset
  seed_travel.py           # fictional flights, hotels, transfers, document checks (also used by the migration)
services/
  scheduling.py            # clash checker (incl. travel rules), free-slot finder, reserve + rebook suggestions (pure, tested)
  travel.py                # travel queries, tz conversion, masking, readiness, budget, red flags, logged writes
  llm.py                   # Groq + template fallbacks: brief, debrief → notes + email, learnings, travel summary
  kpis.py                  # KPI maths + "off track first" weekly summary
  data.py                  # queries and writes (every meeting change → change_log)
  timeline.py              # Plotly swimlane figure
  export.py                # My Day and travel itinerary HTML / PDF
  auth.py  clock.py  ui.py
pages/                     # one file per page (1 … 8)
tests/                     # pytest suite
```

**Times:** meeting and session times are stored in the **event's local timezone** (`events.timezone`). Travel
times are stored as local time **plus the IANA timezone of that place** (a flight has one per end:
`Europe/London`, `America/New_York`, `Asia/Dubai`). Everything is shown in event-local or London time via the
shared toggle, computed with `zoneinfo`, so DST is handled. Audit timestamps (`change_log`) are real UTC time.

---

## 60-second demo script

| Time | Do | Say |
|---|---|---|
| 0:00 | Log in as **London Ops** (`flux-ops`). | "This is the planner I run from London for our three executives at IBIA New York and FUJCON Fujairah. All data is fictitious." |
| 0:06 | **Live Diary**, Wed 2 Dec: swimlanes, teal session bands, amber *now* line. Flip to **London**. | "Three diaries in one view with the programme behind them. It refreshes every 30 seconds, and I can switch to London time." |
| 0:13 | Switch to **Thu 3 Dec**: the hatched *Leadership panel* in the CEO lane under the moved Kestrel Bay meeting. | "The clash checker spotted that the CEO's moved meeting runs into a panel the CEO has to attend." |
| 0:19 | Back to Wed, click **Dhow Point Marine Services**, press **Generate brief**. | "Briefs are built only from our database, cite every field and flag what's unverified, like the unapproved pricing sheet." |
| 0:26 | **Ops Console** → Edit → *Marrowstone Bulk* → **Cancel meeting** → **Book** the top reserve. | "Every change is logged, and the free-slot finder ranks who to call in from the reserve list." |
| 0:33 | Switch the event to **FUJCON** → **Travel**. | "Travel sits next to the diary: readiness per person, and red flags first. The CCO's overnight flight is 90 minutes late, the SSM's car back to Dubai isn't booked, and the CEO is 6% over budget." |
| 0:41 | **Live Diary**, Mon 12 Apr. | "The flight and car sit in the CCO's lane. Velasco now lands on top of them, and Coralline falls inside the two hours after landing." |
| 0:45 | **Ops Console → Travel**: click **Move to 11:20** on Coralline and **CCO → CEO** on Velasco. | "When a flight slips, it shows which meetings break and fixes them in one click. Every change is logged." |
| 0:51 | **Travel** → CCO tab → **Travel summary**, then **Itinerary (PDF)**. | "Each traveller gets a briefing written from the database, and a one-page itinerary for offline use." |
| 0:56 | **KPI Dashboard**. | "And the KPIs lead with what's off track." |

Tip: log in as the **CEO** in a second browser window during the demo. After you change a meeting or a flight in
the Ops Console, their Live Diary shows the "changes since you last looked" banner within 30 seconds. Booking
references for colleagues are masked in their view.
