"""Seed FICTIONAL demo data. Run directly to rebuild the database:

    python -m db.seed            # recreates data/flux_bunkers.db

Every company, person and email address below is invented for demo purposes.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

# ----------------------------------------------------------------------------- people
PEOPLE = [
    # key, name, role, colour, is_attendee, can_edit
    ("ceo", "Daniel Hart", "CEO", "#E3A008", 1, 0),
    ("cco", "Priya Raman", "CCO", "#2BB3B1", 1, 0),
    ("ssm", "Tom Okafor", "Senior Sales Manager", "#A78BFA", 1, 0),
    ("ops", "London Ops", "London Ops", "#8A8F98", 0, 1),
]
P = {"ceo": 1, "cco": 2, "ssm": 3, "ops": 4}

# ----------------------------------------------------------------------------- events
EVENTS = [
    dict(code="IBIA2026", name="IBIA Annual Convention 2026", city="New York",
         timezone="America/New_York", start_date="2026-12-01", end_date="2026-12-03",
         venue="Convention venue, Manhattan",
         agenda_note="Agenda based on the published IBIA 2026 programme; times are indicative."),
    dict(code="FUJCON2027", name="FUJCON 2027", city="Fujairah",
         timezone="Asia/Dubai", start_date="2027-04-12", end_date="2027-04-14",
         venue="Fujairah (venue TBC)",
         agenda_note="Day 1 pre-conference programme confirmed; Days 2–3 conference agenda TBC."),
]

# (title, kind, date, start, end, location, tbc, [mandatory people keys])
IBIA_SESSIONS = [
    ("Ethanol as a marine fuel workshop", "workshop", "2026-12-01", "12:00", "17:45", "Workshop room", 0, []),
    ("Welcome reception", "social", "2026-12-01", "19:30", "21:30", "Venue terrace", 0, ["ceo", "cco", "ssm"]),
    ("Registration", "registration", "2026-12-02", "08:30", "09:30", "Main foyer", 0, []),
    ("Opening", "keynote", "2026-12-02", "09:30", "09:45", "Main hall", 0, ["ceo"]),
    ("Keynote: US maritime", "keynote", "2026-12-02", "09:45", "10:15", "Main hall", 0, []),
    ("Keynote: Market outlook", "keynote", "2026-12-02", "10:15", "10:45", "Main hall", 0, ["ceo"]),
    ("Coffee break", "break", "2026-12-02", "10:45", "11:15", "Exhibition area", 0, []),
    ("Regional and global associations", "panel", "2026-12-02", "11:15", "12:15", "Main hall", 0, []),
    ("Lunch", "break", "2026-12-02", "12:15", "13:30", "Exhibition area", 0, []),
    ("Bunker sellers", "panel", "2026-12-02", "13:30", "14:30", "Main hall", 0, ["ssm"]),
    ("Bunker buyers", "panel", "2026-12-02", "14:30", "15:30", "Main hall", 0, ["cco"]),
    ("Coffee break", "break", "2026-12-02", "15:30", "16:00", "Exhibition area", 0, []),
    ("Alternative fuels", "session", "2026-12-02", "16:00", "17:00", "Main hall", 0, ["cco"]),
    ("Fuel quality and quantity", "session", "2026-12-02", "17:00", "18:00", "Main hall", 0, []),
    ("Convention dinner (skyline cruise)", "social", "2026-12-02", "19:30", "23:00", "Pier departure", 0, ["ceo", "cco", "ssm"]),
    ("Digitalisation and AI in marine energy", "session", "2026-12-03", "09:00", "10:00", "Main hall", 0, ["ssm"]),
    ("Leadership panel", "panel", "2026-12-03", "10:00", "11:00", "Main hall", 0, ["ceo"]),
    ("Coffee break", "break", "2026-12-03", "11:00", "11:30", "Exhibition area", 0, []),
    ("Regulatory and policy", "session", "2026-12-03", "11:30", "12:30", "Main hall", 0, []),
    ("North America", "session", "2026-12-03", "12:30", "13:15", "Main hall", 0, ["ssm"]),
    ("Latin America", "session", "2026-12-03", "13:15", "14:00", "Main hall", 0, []),
    ("Closing networking lunch", "social", "2026-12-03", "14:00", "15:30", "Exhibition area", 0, []),
]

FUJ_SESSIONS = [
    ("Pre-conference training course", "training", "2027-04-12", "09:00", "13:00", "Training suite", 0, ["ssm"]),
    ("Port of Fujairah visit", "visit", "2027-04-12", "14:00", "17:00", "Port of Fujairah", 0, ["ceo", "cco"]),
    ("Welcome reception", "social", "2027-04-12", "19:00", "21:30", "Venue garden", 0, ["ceo", "cco", "ssm"]),
    ("Registration", "registration", "2027-04-13", "08:00", "09:00", "Main foyer", 1, []),
    ("Opening and keynotes", "keynote", "2027-04-13", "09:00", "10:30", "Main hall", 1, ["ceo"]),
    ("Conference sessions", "session", "2027-04-13", "11:00", "13:00", "Main hall", 1, []),
    ("Lunch", "break", "2027-04-13", "13:00", "14:00", "Exhibition area", 1, []),
    ("Conference sessions", "session", "2027-04-13", "14:00", "17:00", "Main hall", 1, []),
    ("Conference sessions", "session", "2027-04-14", "09:00", "12:30", "Main hall", 1, []),
    ("Closing lunch", "social", "2027-04-14", "12:30", "14:00", "Exhibition area", 1, []),
]

# ----------------------------------------------------------------------------- accounts
# name, type, ports, region, tier, usage_trend, monthly_spend, renewal_date, health
ACCOUNTS = [
    ("Harrowgate Tankers", "shipping client", "New York/New Jersey; Philadelphia", "New York / East Coast", 1, "growing", 182000, "2027-03-31", "healthy"),
    ("Kestrel Bay Shipping", "shipping client", "New York/New Jersey; Boston", "New York / East Coast", 1, "declining", 96000, "2027-01-15", "at risk"),
    ("Ironwood Bulk Carriers", "shipping client", "Baltimore; New York/New Jersey", "New York / East Coast", 2, "n/a", None, None, "prospect"),
    ("Larkspur Marine Fuels", "bunker supplier", "New York/New Jersey", "New York / East Coast", 1, "flat", 64000, "2027-06-30", "watch"),
    ("Tidewell Bunkering", "bunker supplier", "Philadelphia; Delaware Bay", "New York / East Coast", 3, "n/a", None, None, "prospect"),
    ("Pemberly Line", "shipping client", "Savannah; New York/New Jersey", "New York / East Coast", 2, "n/a", None, None, "prospect"),
    ("Bluewake Container Lines", "shipping client", "New York/New Jersey; Houston; Fujairah", "New York / East Coast", 1, "growing", 240000, "2027-09-30", "healthy"),
    ("Northgate Reefer Lines", "shipping client", "New York/New Jersey", "New York / East Coast", 3, "n/a", None, None, "prospect"),
    ("Brazos Point Bunkers", "bunker supplier", "Houston; Galveston", "Houston / US Gulf", 2, "n/a", None, None, "prospect"),
    ("Velasco Gulf Fuels", "bunker supplier", "Houston; Corpus Christi", "Houston / US Gulf", 1, "growing", 71000, "2027-02-28", "healthy"),
    ("Saltreach Shipping", "shipping client", "Houston; New Orleans", "Houston / US Gulf", 2, "n/a", None, None, "prospect"),
    ("Marrowstone Bulk", "shipping client", "Houston; Corpus Christi", "Houston / US Gulf", 3, "n/a", None, None, "prospect"),
    ("Halcyon Reef Tankers", "shipping client", "Houston; Fujairah", "Houston / US Gulf", 1, "flat", 128000, "2026-12-31", "watch"),
    ("Dunmore Seaways", "shipping client", "New Orleans; Mobile", "Houston / US Gulf", 3, "n/a", None, None, "prospect"),
    ("Coralline Shipping", "shipping client", "Fujairah; Jebel Ali", "Middle East Gulf", 2, "n/a", None, None, "prospect"),
    ("Dhow Point Marine Services", "bunker supplier", "Fujairah; Khor Fakkan", "Middle East Gulf", 2, "n/a", None, None, "prospect"),
    ("Sandglass Tankers", "shipping client", "Fujairah; Ras Tanura", "Middle East Gulf", 1, "growing", 155000, "2027-05-31", "healthy"),
    ("Falconcrest Bulk", "shipping client", "Fujairah; Sohar", "Middle East Gulf", 3, "n/a", None, None, "prospect"),
    ("Ember Strait Energy", "bunker supplier", "Fujairah", "Middle East Gulf", 3, "n/a", None, None, "prospect"),
    ("Orrin Petroleum Marine", "bunker supplier", "New York/New Jersey; Houston", "Houston / US Gulf", 2, "n/a", None, None, "prospect"),
    ("Qamar Sea Logistics", "shipping client", "Fujairah; Jebel Ali", "Middle East Gulf", 2, "n/a", None, None, "prospect"),
    ("Westerly Freight Tankers", "shipping client", "New York/New Jersey; Boston", "New York / East Coast", 2, "n/a", None, None, "prospect"),
    ("Cypress Sound Shipping", "shipping client", "Houston; Mobile", "Houston / US Gulf", 3, "n/a", None, None, "prospect"),
    ("Granite Harbour Marine Fuels", "bunker supplier", "New York/New Jersey; Baltimore", "New York / East Coast", 2, "n/a", None, None, "prospect"),
]
A = {row[0]: i + 1 for i, row in enumerate(ACCOUNTS)}

# account name -> [(contact name, role, decision maker)]
CONTACTS = {
    "Harrowgate Tankers": [("Margaret Ellison", "Chief Operating Officer", 1), ("Luis Ferreira", "Head of Bunker Procurement", 0)],
    "Kestrel Bay Shipping": [("Owen Pritchard", "Fuel Manager", 0), ("Hannah Voss", "Chief Financial Officer", 1)],
    "Ironwood Bulk Carriers": [("Samuel Achebe", "VP Operations", 1), ("Clara Lindqvist", "Fleet Fuel Analyst", 0)],
    "Larkspur Marine Fuels": [("Rafael Ortiz", "Managing Director", 1), ("Jenna Cole", "Trading Desk Lead", 0)],
    "Tidewell Bunkering": [("Victor Haines", "Sales Director", 0)],
    "Pemberly Line": [("Grace Whitfield", "Procurement Manager", 0), ("Arjun Mehta", "Chief Technical Officer", 1)],
    "Bluewake Container Lines": [("Ingrid Solberg", "Global Head of Fuel", 1), ("Marcus Reyes", "Digital Transformation Lead", 0)],
    "Northgate Reefer Lines": [("Peter Novak", "Operations Manager", 0)],
    "Brazos Point Bunkers": [("Dana Whitaker", "General Manager", 1), ("Eli Brooks", "Credit Manager", 0)],
    "Velasco Gulf Fuels": [("Carmen Salazar", "Chief Executive", 1), ("Nate Underwood", "Scheduling Lead", 0)],
    "Saltreach Shipping": [("Fiona Gallagher", "Head of Chartering", 1), ("Ben Osei", "Fuel Buyer", 0)],
    "Marrowstone Bulk": [("Gregor Malik", "Fleet Manager", 0)],
    "Halcyon Reef Tankers": [("Yusuf Karim", "Chief Commercial Officer", 1), ("Leah Brandt", "Bunker Buyer", 0)],
    "Dunmore Seaways": [("Patrick Doyle", "Technical Superintendent", 0)],
    "Coralline Shipping": [("Layla Haddad", "Managing Director", 1), ("Omar Rahman", "Bunker Coordinator", 0)],
    "Dhow Point Marine Services": [("Khalid Mansour", "Commercial Director", 1)],
    "Sandglass Tankers": [("Noura Al Amiri", "Head of Fuel Procurement", 1), ("Daniel Pereira", "Data & Systems Lead", 0)],
    "Falconcrest Bulk": [("Rashid Qureshi", "Operations Manager", 0)],
    "Ember Strait Energy": [("Sofia Marchetti", "Business Development Manager", 0)],
    "Orrin Petroleum Marine": [("Helen Brask", "Chief Executive", 1), ("Tariq Bello", "Sales Manager", 0)],
    "Qamar Sea Logistics": [("Amira Saleh", "Chief Operating Officer", 1)],
    "Westerly Freight Tankers": [("Colin Barrett", "Fuel Procurement Director", 1)],
    "Cypress Sound Shipping": [("Mia Lorenzo", "Fleet Fuel Manager", 0)],
    "Granite Harbour Marine Fuels": [("Isaac Turner", "Managing Partner", 1)],
}

# account name -> [(date, author key, body)]
NOTES = {
    "Harrowgate Tankers": [("2026-09-14", "cco", "Quarterly review: happy with pricing desk; asked whether Flux Bunkers will cover NY/NJ barge deliveries."),
                           ("2026-03-02", "ceo", "Renewal signed for 12 months. COO keen on digital ordering but IT integration is a gating item.")],
    "Kestrel Bay Shipping": [("2026-10-21", "ssm", "Volumes down ~30% QoQ; fuel manager mentioned a competitor offering lower fees."),
                             ("2026-06-11", "cco", "CFO wants a single consolidated invoice across ports.")],
    "Ironwood Bulk Carriers": [("2026-10-05", "ssm", "Warm intro via Harrowgate COO. Interested in price transparency for Baltimore stems.")],
    "Larkspur Marine Fuels": [("2026-08-30", "cco", "Supplier wants better visibility of buyer demand; open to listing on Flux Bunkers if fees are fair.")],
    "Tidewell Bunkering": [("2026-04-18", "ssm", "Cold outreach at regional event; polite but tied into existing broker arrangements.")],
    "Pemberly Line": [("2026-10-12", "ssm", "Intro from industry association. CTO leads all digital procurement decisions.")],
    "Bluewake Container Lines": [("2026-11-02", "ceo", "Strong relationship. Wants Flux Bunkers live in Fujairah before their Q2 network change."),
                                 ("2026-07-20", "cco", "Digital lead asked for API access to order status.")],
    "Northgate Reefer Lines": [("2026-09-09", "ssm", "Small fleet; responsive by email but no confirmed budget.")],
    "Brazos Point Bunkers": [("2026-10-28", "cco", "Warm intro via Velasco. Credit terms will be the main discussion point.")],
    "Velasco Gulf Fuels": [("2026-11-06", "cco", "Excited about Houston launch; volunteered as reference customer for the Gulf Coast pilot.")],
    "Saltreach Shipping": [("2026-09-25", "ssm", "Head of chartering asked about credit lines for New Orleans stems.")],
    "Marrowstone Bulk": [("2026-02-10", "ssm", "Met briefly at a port event; no follow-up since.")],
    "Halcyon Reef Tankers": [("2026-10-30", "ceo", "Renewal due 31 Dec. CCO-level contact asked for a bundled offer including Flux Bunkers."),
                             ("2026-05-15", "cco", "Usage flat; they are trialling a rival platform in Fujairah.")],
    "Dunmore Seaways": [("2026-06-01", "ssm", "Asked whether New Orleans is on the roadmap.")],
    "Coralline Shipping": [("2026-10-19", "cco", "Intro from Sandglass. MD travelling to New York for IBIA; prefers short meetings.")],
    "Dhow Point Marine Services": [("2026-09-03", "cco", "Fujairah supplier; wants to understand how buyer demand is routed on the platform.")],
    "Sandglass Tankers": [("2026-11-10", "ceo", "Expanding Fujairah liftings. Data & systems lead has security questions."),
                          ("2026-04-22", "cco", "Renewal closed early with expanded scope.")],
    "Falconcrest Bulk": [("2026-03-30", "ssm", "Cold contact from Sohar port day.")],
    "Ember Strait Energy": [("2026-05-05", "cco", "New supplier licence in Fujairah; exploring digital channels.")],
    "Orrin Petroleum Marine": [("2026-10-01", "cco", "Warm intro via association board. CEO attends IBIA every year.")],
    "Qamar Sea Logistics": [("2026-08-12", "ceo", "Met at a Dubai shipping dinner; COO open to a call before FUJCON.")],
    "Westerly Freight Tankers": [("2026-10-15", "ssm", "Asked to be kept in mind if a slot opens at IBIA.")],
    "Cypress Sound Shipping": [("2026-07-07", "ssm", "Cold lead; fleet fuel manager downloaded the product sheet.")],
    "Granite Harbour Marine Fuels": [("2026-10-22", "cco", "Supplier wants to understand listing fees; available at short notice in NY.")],
}

MATERIALS = [
    ("Flux Bunkers one-pager", "one-pager", "https://example.com/flux/one-pager.pdf", "approved", "CCO"),
    ("NY/NJ launch deck", "deck", "https://example.com/flux/ny-launch-deck", "approved", "CEO"),
    ("Houston launch deck", "deck", "https://example.com/flux/houston-launch-deck", "approved", "CCO"),
    ("Fujairah launch deck", "deck", "https://example.com/flux/fujairah-launch-deck", "pending", None),
    ("Pricing sheet – launch tiers", "pricing", "https://example.com/flux/pricing-launch", "pending", None),
    ("Case study: Gulf Coast pilot", "case study", "https://example.com/flux/case-gulf-pilot", "approved", "CCO"),
    ("Product demo video (3 min)", "video", "https://example.com/flux/demo-video", "approved", "CCO"),
    ("Trial terms & conditions", "legal", "https://example.com/flux/trial-terms", "draft", None),
    ("API integration pack", "technical", "https://example.com/flux/api-pack", "approved", "CCO"),
    ("Security & data FAQ", "technical", "https://example.com/flux/security-faq", "pending", None),
]
MAT = {row[0]: i + 1 for i, row in enumerate(MATERIALS)}

# ----------------------------------------------------------------------------- IBIA meetings
# key, account, owner, [attendees], date, start, end, location, status, objective, the ask,
# [materials], next_step, next_step_date
IBIA_MEETINGS = [
    # ---- Day 1 — Tue 1 Dec
    ("M1", "Harrowgate Tankers", "ceo", ["ceo", "cco"], "2026-12-01", "08:30", "09:15", "Hotel restaurant", "done",
     "Preview Flux Bunkers NY/NJ launch with an existing client", "Commit to a Flux Bunkers pilot on NY/NJ stems from January",
     ["NY/NJ launch deck", "API integration pack"], "Send API integration pack and pilot plan", "2026-12-08"),
    ("M2", "Larkspur Marine Fuels", "cco", ["cco"], "2026-12-01", "10:00", "10:45", "Client office – Lower Manhattan", "done",
     "Recruit Larkspur as a launch supplier in NY/NJ", "Agree to list supply on Flux Bunkers at launch",
     ["Flux Bunkers one-pager", "Pricing sheet – launch tiers"], "Share supplier-side pricing tiers", "2026-12-09"),
    ("M3", "Kestrel Bay Shipping", "ceo", ["ceo"], "2026-12-01", "11:00", "11:45", "Client office – Midtown", "done",
     "Stabilise an at-risk account ahead of renewal", "Agree a CFO-level call on renewal terms this week",
     ["Flux Bunkers one-pager"], "CFO call to discuss renewal terms", "2026-12-03"),
    ("M4", "Ironwood Bulk Carriers", "ssm", ["ssm"], "2026-12-01", "09:30", "10:15", "Coffee bar, Level 2", "done",
     "Convert warm intro into an app sign-up", "Sign up two fleet users to the Flux Bunkers app",
     ["Flux Bunkers one-pager", "Product demo video (3 min)"], "Live demo for ops team", "2026-12-03"),
    ("M5", "Pemberly Line", "ssm", ["ssm"], "2026-12-01", "10:30", "11:15", "Hotel lobby lounge", "done",
     "Introduce Flux Bunkers to the CTO's team", "Get CTO into a technical deep-dive",
     ["Flux Bunkers one-pager", "Security & data FAQ"], "Send security questionnaire responses", "2026-12-10"),
    ("M6", "Velasco Gulf Fuels", "cco", ["cco"], "2026-12-01", "13:00", "13:45", "Convention venue – Meeting Room 2", "done",
     "Lock in Velasco as Houston launch supplier and reference", "Start a 60-day trial on the Houston desk",
     ["Houston launch deck", "Case study: Gulf Coast pilot"], "Onboard Houston desk to trial", "2026-12-07"),
    ("M7", "Tidewell Bunkering", "ssm", ["ssm"], "2026-12-01", "18:00", "18:45", "Hotel lobby lounge", "done",
     "Qualify a cold supplier lead", "Agree to a follow-up call with their sales director",
     ["Flux Bunkers one-pager"], "Re-contact in Q2 2027", "2027-04-01"),
    ("M8", "Bluewake Container Lines", "ceo", ["ceo"], "2026-12-01", "16:00", "17:00", "Client office – Midtown", "done",
     "Secure Fujairah go-live commitment from a top client", "Name a Fujairah go-live date for Flux Bunkers",
     ["NY/NJ launch deck", "Fujairah launch deck"], "Confirm Fujairah go-live date", "2026-12-11"),
    # ---- Day 2 — Wed 2 Dec
    ("M9", "Saltreach Shipping", "ssm", ["ssm"], "2026-12-02", "07:45", "08:25", "Hotel restaurant", "done",
     "Explore credit-backed ordering for New Orleans stems", "Introduce our credit team to their head of chartering",
     ["Flux Bunkers one-pager"], "Credit team intro", "2026-12-09"),
    ("M10", "Halcyon Reef Tankers", "ceo", ["ceo", "cco"], "2026-12-02", "11:15", "12:00", "Convention venue – Meeting Room 4", "done",
     "Protect renewal (due 31 Dec) with a Flux Bunkers bundle", "Agree to receive a bundled renewal proposal by Friday",
     ["Pricing sheet – launch tiers", "Houston launch deck"], "Renewal proposal with Flux bundle", "2026-12-04"),
    ("M11", "Brazos Point Bunkers", "cco", ["cco"], "2026-12-02", "12:15", "13:00", "Convention venue – Meeting Room 2", "done",
     "Bring a second Houston supplier onto the platform", "Submit a credit application this month",
     ["Houston launch deck"], "Credit application", "2026-12-10"),
    ("M12", "Orrin Petroleum Marine", "ssm", ["ssm"], "2026-12-02", "11:15", "12:00", "Coffee bar, Level 2", "confirmed",
     "Introduce Flux Bunkers to a dual-port supplier", "Agree a demo with their trading team",
     ["Flux Bunkers one-pager", "Product demo video (3 min)"], None, None),
    ("M13", "Northgate Reefer Lines", "ssm", ["ssm"], "2026-12-02", "16:00", "16:45", "Hotel lobby lounge", "cancelled",
     "Qualify a cold shipping lead", "Agree a 20-minute product call", ["Flux Bunkers one-pager"], None, None),
    ("M14", "Marrowstone Bulk", "ssm", ["ssm"], "2026-12-02", "17:00", "17:30", "Convention venue – Meeting Room 4", "confirmed",
     "Re-open a dormant cold lead", "Sign up one fleet manager to the app", ["Flux Bunkers one-pager"], None, None),
    ("M15", "Coralline Shipping", "cco", ["cco"], "2026-12-02", "17:15", "18:00", "Hotel lobby lounge", "confirmed",
     "Warm up a Gulf prospect before FUJCON", "Agree a meeting slot at FUJCON",
     ["Fujairah launch deck"], None, None),
    ("M16", "Dunmore Seaways", "cco", ["cco"], "2026-12-02", "13:30", "14:15", "Convention venue – Meeting Room 2", "done",
     "Test appetite for New Orleans coverage", "Share their 2027 port plan", ["Flux Bunkers one-pager"],
     "Send New Orleans coverage roadmap", "2026-12-15"),
    ("M17", "Sandglass Tankers", "ceo", ["ceo"], "2026-12-02", "14:00", "14:45", "Client office – Midtown", "done",
     "Expand an existing Gulf client into Flux Bunkers", "Scope a Fujairah trial to start at FUJCON",
     ["Fujairah launch deck", "Security & data FAQ"], "Fujairah trial scoping at FUJCON", "2027-04-12"),
    ("M18", "Dhow Point Marine Services", "ceo", ["ceo"], "2026-12-02", "15:00", "15:45", "Convention venue – Meeting Room 4", "confirmed",
     "Recruit a Fujairah supplier ahead of launch", "Agree to list Fujairah supply from day one",
     ["Fujairah launch deck", "Pricing sheet – launch tiers"], None, None),
    # ---- Day 3 — Thu 3 Dec
    ("M19", "Falconcrest Bulk", "ssm", ["ssm"], "2026-12-03", "08:00", "08:45", "Hotel restaurant", "confirmed",
     "Qualify a cold Gulf lead", "Agree a call with their operations manager in January", ["Flux Bunkers one-pager"], None, None),
    ("M20", "Ember Strait Energy", "cco", ["cco"], "2026-12-03", "09:00", "09:45", "Convention venue – Meeting Room 2", "confirmed",
     "Introduce platform to a new Fujairah supplier", "Agree an onboarding call before FUJCON", ["Fujairah launch deck"], None, None),
    ("M21", "Kestrel Bay Shipping", "ceo", ["ceo"], "2026-12-03", "09:45", "10:30", "Convention venue – Meeting Room 4", "moved",
     "CFO follow-up on renewal terms", "Agree renewal terms in principle with the CFO",
     ["Pricing sheet – launch tiers"], None, None),
    ("M22", "Ironwood Bulk Carriers", "ssm", ["ssm"], "2026-12-03", "10:15", "10:45", "Coffee bar, Level 2", "confirmed",
     "Live demo for Ironwood ops team", "Start a 30-day trial on Baltimore stems",
     ["Product demo video (3 min)", "Trial terms & conditions"], None, None),
    ("M23", "Saltreach Shipping", "cco", ["cco"], "2026-12-03", "11:30", "12:15", "Convention venue – Meeting Room 2", "proposed",
     "Credit team intro (CCO-led)", "Agree credit limit range for a trial", ["Flux Bunkers one-pager"], None, None),
    ("M24", "Bluewake Container Lines", "ceo", ["ceo", "cco"], "2026-12-03", "12:00", "12:45", "Client office – Midtown", "confirmed",
     "Confirm Fujairah go-live and API access", "Sign the Fujairah go-live letter",
     ["API integration pack", "Fujairah launch deck"], None, None),
    ("M25", "Brazos Point Bunkers", "ssm", ["ssm"], "2026-12-03", "13:15", "14:00", "Convention venue – Meeting Room 4", "confirmed",
     "Help Brazos complete the credit application", "Submit credit application before leaving NY", ["Houston launch deck"], None, None),
    ("M26", "Tidewell Bunkering", "cco", ["cco"], "2026-12-03", "14:30", "15:00", "Hotel lobby lounge", "cancelled",
     "Second attempt with Tidewell sales director", "Agree to a pilot listing", ["Flux Bunkers one-pager"], None, None),
    ("M27", "Larkspur Marine Fuels", "ssm", ["ssm"], "2026-12-03", "15:30", "16:15", "Hotel lobby lounge", "proposed",
     "Walk Larkspur trading desk through pricing tiers", "Confirm listing fee tier", ["Pricing sheet – launch tiers"], None, None),
]

# meeting key -> (interest, objections, dm present, signup, trial, what happened)
IBIA_DEBRIEFS = {
    "M1": ("high", "Integration with existing systems", 1, 1, 1, "COO and procurement head attended. Strong interest in NY/NJ barge ordering; IT integration is the only blocker. Agreed to a January pilot subject to API review."),
    "M2": ("medium", "Price / fees; Port coverage", 1, 1, 0, "MD likes the demand visibility. Concerned that listing fees are higher than broker commission and that only NY/NJ is covered at launch."),
    "M3": ("medium", "Price / fees; Locked into current supplier contract", 0, 0, 0, "Fuel manager only; CFO could not attend. Competitor is offering lower fees. Booked a CFO follow-up for Thursday."),
    "M4": ("high", "Needs internal sign-off", 1, 1, 0, "VP Ops signed up on the spot. Needs sign-off from finance before a trial. Wants a live demo for the ops team on Thursday."),
    "M5": ("medium", "Integration with existing systems; Data security", 0, 1, 0, "Procurement manager signed up; CTO did not attend. Security questionnaire requested before any trial."),
    "M6": ("high", "", 1, 1, 1, "CEO agreed to a 60-day trial on the Houston desk and to act as a reference customer."),
    "M7": ("low", "Locked into current supplier contract; Price / fees", 0, 0, 0, "Sales director polite but tied into broker contracts until Q2 2027."),
    "M8": ("high", "Port coverage", 1, 1, 0, "Global head of fuel wants Fujairah live before Q2. Will confirm go-live date once the Fujairah deck is approved."),
    "M9": ("medium", "Credit terms", 1, 0, 0, "Head of chartering interested but needs credit lines for New Orleans stems before signing up."),
    "M10": ("medium", "Price / fees; Needs internal sign-off", 1, 0, 0, "CCO-level contact open to a bundle but needs board sign-off on pricing. Proposal promised by Friday."),
    "M11": ("medium", "Credit terms; Integration with existing systems", 0, 1, 0, "Credit manager signed up; GM absent. Credit application is the gating step."),
    "M16": ("low", "Port coverage", 0, 0, 0, "Technical superintendent only; New Orleans not on launch roadmap, which limits interest."),
    "M17": ("high", "Data security", 1, 1, 0, "Head of fuel procurement signed up. Data & systems lead needs security FAQ before a Fujairah trial."),
}

# meeting key -> (status, hours after meeting end it was approved/sent or None)
IBIA_FOLLOWUPS = {
    "M1": ("sent", 5.5), "M2": ("sent", 26.0), "M3": ("sent", 23.0), "M4": ("sent", 9.5),
    "M5": ("approved", None), "M6": ("sent", 5.0), "M7": ("draft", None), "M8": ("sent", 15.0),
    "M9": ("sent", 3.5), "M10": ("approved", None), "M11": ("draft", None), "M16": ("draft", None),
    "M17": ("sent", 0.4),
}

FUJ_MEETINGS = [
    ("F1", "Sandglass Tankers", "ceo", ["ceo"], "2027-04-12", "10:00", "10:45", "Hotel lobby lounge", "proposed",
     "Kick off Fujairah trial", "Sign trial order form", ["Fujairah launch deck", "Trial terms & conditions"]),
    ("F2", "Coralline Shipping", "cco", ["cco"], "2027-04-12", "11:00", "11:45", "Client office – Fujairah", "proposed",
     "Convert IBIA warm-up into sign-ups", "Sign up the bunker coordinator", ["Fujairah launch deck"]),
    ("F3", "Dhow Point Marine Services", "cco", ["cco"], "2027-04-13", "13:00", "13:45", "Exhibition area – Meeting pod 1", "proposed",
     "Supplier onboarding", "List Fujairah supply from launch day", ["Pricing sheet – launch tiers"]),
    ("F4", "Bluewake Container Lines", "ceo", ["ceo", "cco"], "2027-04-13", "11:00", "11:45", "Hotel restaurant", "proposed",
     "Fujairah go-live review", "Expand to Khor Fakkan", ["Fujairah launch deck"]),
    ("F5", "Falconcrest Bulk", "ssm", ["ssm"], "2027-04-13", "09:00", "09:45", "Exhibition area – Meeting pod 2", "proposed",
     "Qualify cold Gulf lead", "Book a product demo", ["Flux Bunkers one-pager"]),
    ("F6", "Ember Strait Energy", "ssm", ["ssm"], "2027-04-13", "14:00", "14:45", "Exhibition area – Meeting pod 2", "proposed",
     "Supplier onboarding follow-up", "Complete onboarding checklist", ["Fujairah launch deck"]),
    ("F7", "Halcyon Reef Tankers", "ceo", ["ceo"], "2027-04-14", "09:00", "09:45", "Hotel lobby lounge", "proposed",
     "Win back Fujairah volumes from rival platform", "Move Fujairah stems onto Flux Bunkers", ["Pricing sheet – launch tiers"]),
    ("F8", "Qamar Sea Logistics", "cco", ["cco"], "2027-04-14", "10:00", "10:45", "Exhibition area – Meeting pod 1", "proposed",
     "First meeting with warm Gulf prospect", "Sign up two operators", ["Fujairah launch deck"]),
    ("F9", "Harrowgate Tankers", "ssm", ["ssm"], "2027-04-14", "11:00", "11:30", "Exhibition area – Meeting pod 2", "proposed",
     "Extend NY pilot to Fujairah", "Add Fujairah to pilot scope", ["API integration pack"]),
    ("F10", "Velasco Gulf Fuels", "cco", ["cco"], "2027-04-12", "08:00", "08:45", "Hotel restaurant", "proposed",
     "Reference-customer breakfast with Gulf suppliers", "Co-present Houston results on stage", ["Case study: Gulf Coast pilot"]),
]

# (event code, account, priority, preferred owner, min minutes, note)
RESERVES = [
    ("IBIA2026", "Westerly Freight Tankers", 1, "ssm", 30, "Asked to be called if a slot opens; staying near Midtown."),
    ("IBIA2026", "Granite Harbour Marine Fuels", 2, "cco", 45, "Supplier; available at short notice in NY."),
    ("IBIA2026", "Cypress Sound Shipping", 3, "ssm", 30, "Cold lead; fleet fuel manager attending IBIA."),
    ("IBIA2026", "Qamar Sea Logistics", 3, "ceo", 30, "Gulf-based COO visiting NY — useful warm-up for FUJCON."),
    ("FUJCON2027", "Granite Harbour Marine Fuels", 3, "cco", 30, "Expanding to Gulf supply in 2027."),
    ("FUJCON2027", "Westerly Freight Tankers", 2, "ssm", 30, "Fujairah liftings rising in 2027."),
    ("FUJCON2027", "Ember Strait Energy", 2, "cco", 30, "If the Day 2 slot moves."),
]

TARGETS = {"IBIA2026": (25, 15, 5, 60, 90), "FUJCON2027": (40, 25, 10, 60, 90)}


# ============================================================================= helpers
def _iso(date: str, hm: str) -> str:
    return f"{date}T{hm}:00"


def _utc_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _first_name(person_key: str) -> str:
    return next(p[1] for p in PEOPLE if p[0] == person_key).split()[0]


def _email_text(account: str, contact: str, next_step: str, next_date: str, sender_key: str) -> tuple[str, str]:
    sender = next(p for p in PEOPLE if p[0] == sender_key)
    subject = f"Flux Bunkers – next steps from IBIA ({account})"
    body = (
        f"Dear {contact.split()[0]},\n\n"
        f"Thank you for making time to meet at IBIA in New York. As discussed, our next step is: "
        f"{next_step.lower()}, which we will aim to complete by {next_date}.\n\n"
        "Please let me know if anything changes on your side.\n\n"
        f"Kind regards,\n{sender[1]}\n{sender[2]}"
    )
    return subject, body


def seed(conn: sqlite3.Connection) -> None:
    """Insert all demo data into an empty, schema-initialised connection."""
    now = datetime.now(timezone.utc)
    cur = conn.cursor()

    cur.executemany(
        "INSERT INTO people (key, name, role, colour, is_attendee, can_edit) VALUES (?,?,?,?,?,?)", PEOPLE)
    for ev in EVENTS:
        cur.execute(
            "INSERT INTO events (code, name, city, timezone, start_date, end_date, venue, agenda_note)"
            " VALUES (:code,:name,:city,:timezone,:start_date,:end_date,:venue,:agenda_note)", ev)
    ev_id = {r[0]: r[1] for r in cur.execute("SELECT code, id FROM events")}

    for code, sessions in (("IBIA2026", IBIA_SESSIONS), ("FUJCON2027", FUJ_SESSIONS)):
        for title, kind, d, s, e, loc, tbc, must in sessions:
            cur.execute(
                "INSERT INTO sessions (event_id, title, kind, start_at, end_at, location, tbc) VALUES (?,?,?,?,?,?,?)",
                (ev_id[code], title, kind, _iso(d, s), _iso(d, e), loc, tbc))
            sid = cur.lastrowid
            for k in must:
                cur.execute("INSERT INTO session_attendees VALUES (?,?)", (sid, P[k]))

    cur.executemany(
        "INSERT INTO accounts (name, type, ports, region, tier, usage_trend, monthly_spend, renewal_date, health_status)"
        " VALUES (?,?,?,?,?,?,?,?,?)", ACCOUNTS)

    contact_ids: dict[str, list[tuple[int, str, int]]] = {}
    for acc, people in CONTACTS.items():
        for name, role, dm in people:
            email = name.lower().replace(" ", ".") + "@example.com"
            cur.execute("INSERT INTO contacts (account_id, name, role, decision_maker, email) VALUES (?,?,?,?,?)",
                        (A[acc], name, role, dm, email))
            contact_ids.setdefault(acc, []).append((cur.lastrowid, name, dm))

    for acc, notes in NOTES.items():
        for d, author, body in notes:
            cur.execute("INSERT INTO notes (account_id, author_id, note_date, body) VALUES (?,?,?,?)",
                        (A[acc], P[author], d, body))

    cur.executemany("INSERT INTO materials (name, type, link, approval_status, approved_by) VALUES (?,?,?,?,?)",
                    MATERIALS)

    created = _utc_iso(now - timedelta(days=10))
    mid: dict[str, int] = {}

    def add_meeting(code, key, acc, owner, attendees, d, s, e, loc, status, obj, ask, mats, ns=None, nsd=None):
        cur.execute(
            "INSERT INTO meetings (event_id, account_id, owner_id, start_at, end_at, location, status, objective,"
            " the_ask, next_step, next_step_date, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (ev_id[code], A[acc], P[owner], _iso(d, s), _iso(d, e), loc, status, obj, ask, ns, nsd, created, created))
        m = cur.lastrowid
        mid[key] = m
        for p in attendees:
            cur.execute("INSERT INTO meeting_people VALUES (?,?)", (m, P[p]))
        # invite the decision-maker for tier 1, otherwise first contact (+ DM for some tier 2)
        cs = contact_ids.get(acc, [])
        chosen = [c for c in cs if c[2]] if any(c[2] for c in cs) else cs[:1]
        if len(cs) > 1 and int(m) % 2 == 0:
            chosen = cs[:2]
        for c in chosen or cs[:1]:
            cur.execute("INSERT OR IGNORE INTO meeting_contacts VALUES (?,?)", (m, c[0]))
        for mat in mats:
            cur.execute("INSERT INTO meeting_materials VALUES (?,?)", (m, MAT[mat]))
        return m

    for row in IBIA_MEETINGS:
        add_meeting("IBIA2026", *row)
    for row in FUJ_MEETINGS:
        add_meeting("FUJCON2027", *row)

    # ---- debriefs + follow-ups for completed IBIA meetings
    ny = ZoneInfo("America/New_York")
    meeting_rows = {k: v for k, v in ((r[0], r) for r in IBIA_MEETINGS)}
    for key, (interest, objections, dm, signup, trial, what) in IBIA_DEBRIEFS.items():
        r = meeting_rows[key]
        acc, owner, d, end, ns, nsd = r[1], r[2], r[4], r[6], r[12], r[13]
        end_local = datetime.fromisoformat(_iso(d, end)).replace(tzinfo=ny)
        structured = (
            f"**Summary:** {what}\n\n**Interest:** {interest}\n\n"
            f"**Objections:** {objections or 'None raised'}\n\n**Next step:** {ns} (by {nsd})\n\n"
            f"**Decision-maker present:** {'Yes' if dm else 'No'}"
        )
        cur.execute(
            "INSERT INTO debriefs (meeting_id, author_id, what_happened, interest_level, objections, next_step,"
            " next_step_date, decision_maker_present, app_signup, trial_started, structured_notes, generator, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (mid[key], P[owner], what, interest, objections, ns, nsd, dm, signup, trial, structured, "template",
             _utc_iso(end_local + timedelta(minutes=30))))
        did = cur.lastrowid
        status, hours = IBIA_FOLLOWUPS[key]
        contact = contact_ids[acc][0][1]
        subject, body = _email_text(acc, contact, ns, nsd, owner)
        approved_at = sent_at = None
        if status in ("approved", "sent"):
            t = end_local + timedelta(hours=hours if hours else 2)
            approved_at = _utc_iso(t - timedelta(minutes=20))
            sent_at = _utc_iso(t) if status == "sent" else None
        cur.execute(
            "INSERT INTO follow_ups (meeting_id, debrief_id, subject, body, status, approved_by, approved_at, sent_at, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (mid[key], did, subject, body, status, "London Ops" if approved_at else None, approved_at, sent_at,
             _utc_iso(end_local + timedelta(minutes=35))))

    # ---- reserves and targets
    for code, acc, prio, owner, mins, note in RESERVES:
        cur.execute("INSERT INTO reserve_list (event_id, account_id, priority, preferred_owner_id, min_minutes, note)"
                    " VALUES (?,?,?,?,?,?)", (ev_id[code], A[acc], prio, P[owner], mins, note))
    for code, (m, s, t, dm, f) in TARGETS.items():
        cur.execute("INSERT INTO targets VALUES (?,?,?,?,?,?)", (ev_id[code], m, s, t, dm, f))

    # ---- change log history (timestamps relative to seeding time, so "x min ago" reads naturally)
    ibia = ev_id["IBIA2026"]
    history = [
        (300, "London Ops", mid["M21"], "move", "start_at", "2026-12-02T17:30:00", "2026-12-03T09:45:00",
         "Kestrel Bay Shipping (CEO) moved from Wed 17:30 to Thu 09:45 at the CFO's request"),
        (240, "London Ops", mid["M21"], "status", "status", "confirmed", "moved",
         "Kestrel Bay Shipping status set to moved"),
        (180, "London Ops", mid["M26"], "cancel", "status", "confirmed", "cancelled",
         "Tidewell Bunkering (CCO, Thu 14:30) cancelled – deprioritised cold lead"),
        (55, "London Ops", mid["M24"], "update", "location", "Convention venue – Meeting Room 4", "Client office – Midtown",
         "Bluewake Container Lines (Thu 12:00) location changed to client office"),
        (40, "London Ops", mid["M23"], "create", None, None, "proposed",
         "New proposed meeting: Saltreach Shipping with CCO, Thu 11:30"),
        (12, "London Ops", mid["M13"], "cancel", "status", "confirmed", "cancelled",
         "Northgate Reefer Lines (SSM, Wed 16:00) cancelled – vessel issue at port"),
    ]
    for mins_ago, who, ent_id, action, field, old, new, summary in history:
        cur.execute(
            "INSERT INTO change_log (ts, who, event_id, entity, entity_id, action, field, old_value, new_value, summary)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (_utc_iso(now - timedelta(minutes=mins_ago)), who, ibia, "meeting", ent_id, action, field, old, new, summary))

    # Attendees have seen everything except the last three changes.
    seen_upto = cur.execute("SELECT MAX(id) - 3 FROM change_log").fetchone()[0]
    for key, pid in P.items():
        cur.execute("INSERT INTO viewer_state VALUES (?,?)", (pid, seen_upto if key != "ops" else 10**9))

    # One pre-generated brief so the brief page has an example straight away.
    cur.execute(
        "INSERT INTO briefs (meeting_id, content, sources, unverified, generator, generated_at) VALUES (?,?,?,?,?,?)",
        (mid["M18"],
         "**Dhow Point Marine Services** is a tier 2 (warm intro) bunker supplier in Fujairah and Khor Fakkan "
         "[account.name, account.tier, account.ports]. It is a prospect with no spend on record [account.health_status]. "
         "Last note (2026-09-03): wants to understand how buyer demand is routed on the platform [notes.1]. "
         "**The one ask:** agree to list Fujairah supply from day one [meeting.the_ask].\n\n"
         "⚠️ The Fujairah launch deck and pricing sheet are *pending approval* — do not hand out [materials].",
         json.dumps(["account.name", "account.tier", "account.ports", "account.health_status", "notes.1",
                     "meeting.the_ask", "materials"]),
         json.dumps(["Commercial Director's authority to commit volumes is unverified (not recorded in database)"]),
         "template", _utc_iso(now - timedelta(hours=3))))
    conn.commit()


if __name__ == "__main__":
    from db.database import init_db, db_path

    init_db(force_reseed=True)
    print(f"Seeded demo database at {db_path()}")
