# ⚓ Flux Bunkers Event Planner

A live event planner for the **CEO, CCO and Senior Sales Manager** of a commodities trading firm attending
**IBIA Annual Convention 2026 (New York, 1–3 Dec 2026)** and **FUJCON 2027 (Fujairah, 12–14 Apr 2027)** to launch
*Flux Bunkers* at new ports, run by **London Ops**.

> **Demo data – fictitious.** Every company, person, email address and figure in this app is invented.
> The IBIA agenda follows the published 2026 programme; times are indicative. FUJCON Days 2–3 are marked TBC.

Built with **Python · Streamlit (multipage) · SQLite (plain SQL) · Plotly · Groq** (optional; templates otherwise).

---

## What's inside

| Page | What it does |
|---|---|
| 🗓️ **Live Diary** | One timeline, three swimlanes (CEO / CCO / SSM). Event sessions as background bands and a *Programme* lane, must-attend sessions hatched in each person's lane, colour **and icon** by status, "now" line. Day selector, **event-local ↔ London** toggle, auto-refresh every 30 s with "last updated", and a **"changes since you last looked"** banner. Click a meeting to open its brief. |
| 📱 **My Day** | Phone-friendly running order for one person: time (local + London), account, location, objective, *the one ask*, warnings for unapproved materials, link to brief. **Download as HTML or PDF** for offline use. |
| 📋 **Meeting Brief** | Account context, contacts and roles (decision-maker / attending), health (usage trend, spend, renewal countdown), previous notes, earlier debriefs, materials with approval status, the one ask, follow-up owner. **Generate brief** summarises *only* database fields, lists the fields used, and flags anything uncertain as **unverified**. |
| 🛠️ **Ops Console** *(London Ops only)* | Add / edit / move / cancel meetings, all written to `change_log`. **Live clash checker**: same-person overlap, < 15 min buffer, < 30 min between different locations, meeting during a must-attend session. **Free-slot finder**: cancelling shows the freed window and ranks reserve-list accounts, with one-click booking. Whole-diary clash report, change-log export. |
| ✍️ **Debrief & Follow-up** | Short post-meeting form (what happened, interest, objections, next step + date, decision-maker present, sign-up, trial). AI turns it into structured notes and drafts the follow-up email; London Ops edits and **approves** (draft → approved → sent). A meeting **can't be marked done without a next-step date**. |
| 📊 **KPI Dashboard** | Meetings booked vs target, % held with a decision-maker, sign-ups, trials (with pace projection), tier mix, cancellations, follow-ups sent within 24 h. A **weekly summary that leads with what's off track** (downloadable Markdown). |
| 🧭 **IBIA → FUJCON Learnings** | Conversion by tier, most common objections, effect of a decision-maker being present, scored FUJCON target list, and an AI summary with recommendations. |

**Roles:** CEO, CCO and Senior Sales Manager can view everything (and file debriefs). London Ops can edit.

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
streamlit run app.py
```

Streamlit then opens the app in your browser at `http://localhost:8501`. That address only works on the machine
running the app; for a shareable link, see [Deploy to Streamlit Community Cloud](#deploy-to-streamlit-community-cloud).
If no passwords are configured, the login screen shows the demo credentials
(`flux-ceo`, `flux-cco`, `flux-ssm`, `flux-ops`).

The SQLite database (`data/flux_bunkers.db`) is created and seeded automatically on first run.
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

51 tests cover the clash checker (every rule and its threshold), the free-slot finder and reserve ranking,
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
services/
  scheduling.py            # clash checker, free-slot finder, reserve suggestions, validation (pure, tested)
  llm.py                   # Groq + template fallbacks: brief, debrief → notes + email, learnings
  kpis.py                  # KPI maths + "off track first" weekly summary
  data.py                  # queries and writes (every meeting change → change_log)
  timeline.py              # Plotly swimlane figure
  export.py                # My Day HTML / PDF
  auth.py  clock.py  ui.py
pages/                     # one file per page (1 … 7)
tests/                     # pytest suite
```

**Times:** meeting and session times are stored in the **event's local timezone** (`events.timezone`). London
times are computed with `zoneinfo`, so DST is handled. Audit timestamps (`change_log`) are real UTC time.

---

## 60-second demo script

| Time | Do | Say |
|---|---|---|
| 0:00 | Log in as **London Ops** (`flux-ops`). | "This is the planner I run from London for our three executives at IBIA New York and FUJCON Fujairah. All data is fictitious." |
| 0:08 | **Live Diary**, Wed 2 Dec. Point at the swimlanes, the teal session bands and the amber *now* line. Flip **London** time. | "Three diaries in one view, with the convention programme behind them. It refreshes every 30 seconds, and I can switch to London time." |
| 0:18 | Switch to **Thu 3 Dec**. Point at the hatched *Leadership panel* in the CEO lane overlapping the moved Kestrel Bay meeting. | "The clash checker spotted a problem: the CEO's moved meeting runs into a panel the CEO has to attend." |
| 0:25 | Back to Wed. Click **Dhow Point Marine Services** to open the **Meeting Brief**, then press **Generate brief**. | "Each brief is built only from our database. It cites every field it used and flags what's unverified, like the pricing sheet that isn't approved yet." |
| 0:35 | **Ops Console** → Edit → pick *Marrowstone Bulk* → **Cancel meeting**. | "When a meeting falls through, every change is logged, and the free-slot finder ranks who to call in from the reserve list." Click **Book** on the top suggestion. |
| 0:45 | **Debrief & Follow-up** → Follow-ups → approve a draft. | "After each meeting a two-minute debrief becomes structured notes and a draft email. Nothing goes out until I approve it, and a meeting can't be closed without a next-step date." |
| 0:52 | **KPI Dashboard**, then **Learnings**. | "The KPIs lead with what's off track, trials in this case. The learnings page turns IBIA debriefs into a target list for Fujairah." |

Tip: log in as the **CEO** in a second browser window during the demo. After you cancel in the Ops Console,
their Live Diary shows the "1 change since you last looked" banner within 30 seconds.
