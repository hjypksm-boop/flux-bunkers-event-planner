-- Flux Bunkers Event Planner — SQLite schema
-- All meeting/session times are stored as naive ISO strings in the EVENT'S LOCAL timezone
-- (events.timezone). Audit timestamps (change_log, generated_at, ...) are stored in UTC.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY,
    code        TEXT NOT NULL UNIQUE,          -- 'IBIA2026', 'FUJCON2027'
    name        TEXT NOT NULL,
    city        TEXT NOT NULL,
    timezone    TEXT NOT NULL,                 -- IANA name, e.g. America/New_York
    start_date  TEXT NOT NULL,                 -- YYYY-MM-DD
    end_date    TEXT NOT NULL,
    venue       TEXT,
    agenda_note TEXT
);

CREATE TABLE IF NOT EXISTS people (
    id          INTEGER PRIMARY KEY,
    key         TEXT NOT NULL UNIQUE,          -- 'ceo', 'cco', 'ssm', 'ops'
    name        TEXT NOT NULL,
    role        TEXT NOT NULL,                 -- 'CEO', 'CCO', 'Senior Sales Manager', 'London Ops'
    colour      TEXT NOT NULL,
    is_attendee INTEGER NOT NULL DEFAULT 1,
    can_edit    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sessions (
    id          INTEGER PRIMARY KEY,
    event_id    INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    title       TEXT NOT NULL,
    kind        TEXT NOT NULL DEFAULT 'session'
                CHECK (kind IN ('session','keynote','panel','workshop','break','social','registration','visit','training')),
    start_at    TEXT NOT NULL,
    end_at      TEXT NOT NULL,
    location    TEXT,
    tbc         INTEGER NOT NULL DEFAULT 0
);

-- Sessions a given person is expected to attend (used by the clash checker).
CREATE TABLE IF NOT EXISTS session_attendees (
    session_id  INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    person_id   INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    PRIMARY KEY (session_id, person_id)
);

CREATE TABLE IF NOT EXISTS accounts (
    id              INTEGER PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    type            TEXT NOT NULL CHECK (type IN ('bunker supplier','shipping client')),
    ports           TEXT,
    region          TEXT NOT NULL,
    tier            INTEGER NOT NULL CHECK (tier IN (1,2,3)),  -- 1 existing client, 2 warm intro, 3 cold
    usage_trend     TEXT CHECK (usage_trend IN ('growing','flat','declining','n/a')),
    monthly_spend   REAL,                                      -- USD, NULL if not a client
    renewal_date    TEXT,
    health_status   TEXT CHECK (health_status IN ('healthy','watch','at risk','prospect'))
);

CREATE TABLE IF NOT EXISTS contacts (
    id              INTEGER PRIMARY KEY,
    account_id      INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    role            TEXT,
    decision_maker  INTEGER NOT NULL DEFAULT 0,
    email           TEXT
);

CREATE TABLE IF NOT EXISTS meetings (
    id              INTEGER PRIMARY KEY,
    event_id        INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    account_id      INTEGER NOT NULL REFERENCES accounts(id),
    owner_id        INTEGER NOT NULL REFERENCES people(id),    -- also the follow-up owner
    start_at        TEXT NOT NULL,
    end_at          TEXT NOT NULL,
    location        TEXT,
    status          TEXT NOT NULL DEFAULT 'proposed'
                    CHECK (status IN ('proposed','confirmed','moved','cancelled','done')),
    objective       TEXT,
    the_ask         TEXT,
    next_step       TEXT,
    next_step_date  TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

-- Internal attendees (our people) for a meeting.
CREATE TABLE IF NOT EXISTS meeting_people (
    meeting_id  INTEGER NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    person_id   INTEGER NOT NULL REFERENCES people(id),
    PRIMARY KEY (meeting_id, person_id)
);

-- Client-side contacts expected at a meeting.
CREATE TABLE IF NOT EXISTS meeting_contacts (
    meeting_id  INTEGER NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    contact_id  INTEGER NOT NULL REFERENCES contacts(id),
    PRIMARY KEY (meeting_id, contact_id)
);

CREATE TABLE IF NOT EXISTS notes (
    id          INTEGER PRIMARY KEY,
    account_id  INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    author_id   INTEGER REFERENCES people(id),
    note_date   TEXT NOT NULL,
    body        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS materials (
    id              INTEGER PRIMARY KEY,
    name            TEXT NOT NULL,
    type            TEXT NOT NULL,          -- deck, one-pager, pricing, case study, video, legal
    link            TEXT,
    approval_status TEXT NOT NULL DEFAULT 'draft' CHECK (approval_status IN ('draft','pending','approved')),
    approved_by     TEXT
);

CREATE TABLE IF NOT EXISTS meeting_materials (
    meeting_id  INTEGER NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    material_id INTEGER NOT NULL REFERENCES materials(id),
    PRIMARY KEY (meeting_id, material_id)
);

CREATE TABLE IF NOT EXISTS briefs (
    id            INTEGER PRIMARY KEY,
    meeting_id    INTEGER NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    content       TEXT NOT NULL,
    sources       TEXT NOT NULL,            -- JSON list of database field keys used
    unverified    TEXT NOT NULL DEFAULT '[]', -- JSON list of items flagged unverified
    generator     TEXT NOT NULL,            -- 'groq:<model>' or 'template'
    generated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS debriefs (
    id                      INTEGER PRIMARY KEY,
    meeting_id              INTEGER NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    author_id               INTEGER REFERENCES people(id),
    what_happened           TEXT NOT NULL,
    interest_level          TEXT NOT NULL CHECK (interest_level IN ('low','medium','high')),
    objections              TEXT,           -- semicolon separated
    next_step               TEXT NOT NULL,
    next_step_date          TEXT NOT NULL,
    decision_maker_present  INTEGER NOT NULL DEFAULT 0,
    app_signup              INTEGER NOT NULL DEFAULT 0,
    trial_started           INTEGER NOT NULL DEFAULT 0,
    structured_notes        TEXT,           -- markdown produced by AI/template
    generator               TEXT,
    created_at              TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS follow_ups (
    id           INTEGER PRIMARY KEY,
    meeting_id   INTEGER NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    debrief_id   INTEGER REFERENCES debriefs(id) ON DELETE SET NULL,
    subject      TEXT NOT NULL,
    body         TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','approved','sent')),
    approved_by  TEXT,
    approved_at  TEXT,
    sent_at      TEXT,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS change_log (
    id          INTEGER PRIMARY KEY,
    ts          TEXT NOT NULL,             -- UTC ISO timestamp
    who         TEXT NOT NULL,
    event_id    INTEGER REFERENCES events(id),
    entity      TEXT NOT NULL,             -- 'meeting', 'follow_up', ...
    entity_id   INTEGER,
    action      TEXT NOT NULL,             -- create / update / move / cancel / status / approve
    field       TEXT,
    old_value   TEXT,
    new_value   TEXT,
    summary     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS targets (
    event_id        INTEGER PRIMARY KEY REFERENCES events(id) ON DELETE CASCADE,
    meetings        INTEGER NOT NULL,
    app_signups     INTEGER NOT NULL,
    trials          INTEGER NOT NULL,
    dm_pct          INTEGER NOT NULL DEFAULT 60,   -- % of held meetings with a decision-maker
    followup_24h_pct INTEGER NOT NULL DEFAULT 90   -- % of follow-ups sent within 24h
);

CREATE TABLE IF NOT EXISTS reserve_list (
    id                  INTEGER PRIMARY KEY,
    event_id            INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    account_id          INTEGER NOT NULL REFERENCES accounts(id),
    priority            INTEGER NOT NULL DEFAULT 3,      -- 1 = call first
    preferred_owner_id  INTEGER REFERENCES people(id),
    min_minutes         INTEGER NOT NULL DEFAULT 30,
    note                TEXT,
    UNIQUE (event_id, account_id)
);

-- Last change_log id each viewer has acknowledged (drives "changes since you last looked").
CREATE TABLE IF NOT EXISTS viewer_state (
    person_id       INTEGER PRIMARY KEY REFERENCES people(id),
    last_seen_id    INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_meetings_event ON meetings(event_id, start_at);
CREATE INDEX IF NOT EXISTS idx_change_log_event ON change_log(event_id, id);
CREATE INDEX IF NOT EXISTS idx_notes_account ON notes(account_id);

-- ============================================================================ travel logistics
-- Travel times are stored as naive local ISO strings PLUS the IANA timezone of that place
-- (a flight has one zone per end). Convert with zoneinfo for event-local or London display.
-- PRIVACY: no passport, ID, card or bank columns exist anywhere, by design.

CREATE TABLE IF NOT EXISTS trips (
    id              INTEGER PRIMARY KEY,
    person_id       INTEGER NOT NULL REFERENCES people(id),
    event_id        INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    outbound_date   TEXT NOT NULL,             -- YYYY-MM-DD (departure from London)
    return_date     TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'planned'
                    CHECK (status IN ('planned','booked','confirmed','travelling','done')),
    budget_gbp      REAL NOT NULL DEFAULT 0,   -- actual cost = sum of item costs (computed, never stored)
    notes           TEXT,
    UNIQUE (person_id, event_id)
);

CREATE TABLE IF NOT EXISTS flights (
    id              INTEGER PRIMARY KEY,
    trip_id         INTEGER NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
    direction       TEXT NOT NULL CHECK (direction IN ('outbound','return','internal')),
    airline         TEXT NOT NULL,
    flight_no       TEXT NOT NULL,
    dep_airport     TEXT NOT NULL,
    dep_at          TEXT NOT NULL,             -- scheduled, local to dep_tz
    dep_tz          TEXT NOT NULL,
    dep_terminal    TEXT,
    arr_airport     TEXT NOT NULL,
    arr_at          TEXT NOT NULL,             -- scheduled, local to arr_tz
    arr_tz          TEXT NOT NULL,
    arr_terminal    TEXT,
    booking_ref     TEXT,
    seat            TEXT,
    cost_gbp        REAL NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'booked'
                    CHECK (status IN ('booked','checked in','delayed','cancelled','landed')),
    delay_minutes   INTEGER NOT NULL DEFAULT 0 -- shifts departure and arrival; schedule kept
);

CREATE TABLE IF NOT EXISTS hotels (
    id                  INTEGER PRIMARY KEY,
    trip_id             INTEGER NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
    name                TEXT NOT NULL,
    address             TEXT,
    tz                  TEXT NOT NULL,
    check_in_at         TEXT NOT NULL,
    check_out_at        TEXT NOT NULL,
    booking_ref         TEXT,
    distance_km         REAL,                  -- to venue; NULL while venue is TBC
    travel_min_to_venue INTEGER,
    phone               TEXT,
    cost_gbp            REAL NOT NULL DEFAULT 0,
    status              TEXT NOT NULL DEFAULT 'booked' CHECK (status IN ('not booked','booked','confirmed'))
);

CREATE TABLE IF NOT EXISTS transfers (
    id              INTEGER PRIMARY KEY,
    trip_id         INTEGER NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
    type            TEXT NOT NULL CHECK (type IN ('airport pickup','airport drop-off','venue shuttle',
                                                  'car to Fujairah','car from Fujairah')),
    pickup_at       TEXT NOT NULL,
    tz              TEXT NOT NULL,
    pickup_place    TEXT NOT NULL,
    dropoff_place   TEXT NOT NULL,
    provider        TEXT,
    driver_contact  TEXT,
    est_minutes     INTEGER NOT NULL,
    booking_ref     TEXT,
    cost_gbp        REAL NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'booked' CHECK (status IN ('not booked','booked','confirmed'))
);

-- Checklist status ONLY. Never store document numbers.
CREATE TABLE IF NOT EXISTS travel_docs (
    id          INTEGER PRIMARY KEY,
    person_id   INTEGER NOT NULL REFERENCES people(id),
    event_id    INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    item        TEXT NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('done','pending','not needed')),
    UNIQUE (person_id, event_id, item)
);

CREATE INDEX IF NOT EXISTS idx_trips_event ON trips(event_id, person_id);
CREATE INDEX IF NOT EXISTS idx_flights_trip ON flights(trip_id);
CREATE INDEX IF NOT EXISTS idx_hotels_trip ON hotels(trip_id);
CREATE INDEX IF NOT EXISTS idx_transfers_trip ON transfers(trip_id);
