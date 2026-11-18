"""LLM service: template fallback, citation guard-rails, failure handling (Groq is mocked)."""
import pytest

from db.database import scalar
from services import data, llm


def _meeting_id(account: str, event_code: str = "IBIA2026") -> int:
    return scalar("SELECT m.id FROM meetings m JOIN accounts a ON a.id=m.account_id JOIN events e ON e.id=m.event_id "
                  "WHERE a.name=? AND e.code=? ORDER BY m.start_at LIMIT 1", [account, event_code])


def test_template_brief_without_key(fresh_db, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    ctx = data.meeting_context(_meeting_id("Halcyon Reef Tankers"))
    res = llm.generate_brief(ctx)
    assert res.generator == "template"
    assert "No GROQ_API_KEY" in res.note
    fields = llm.brief_fields(ctx)
    assert res.sources and all(s in fields for s in res.sources)
    assert "Halcyon Reef Tankers" in res.content["markdown"]
    assert "[meeting.the_ask]" in res.content["markdown"]


def test_unverified_flags(fresh_db):
    # Dhow Point meeting uses two materials that are not approved.
    ctx = data.meeting_context(_meeting_id("Dhow Point Marine Services"))
    flags = llm.deterministic_unverified(ctx)
    assert any("Pricing sheet" in f and "not approved" in f for f in flags)
    assert any("Fujairah launch deck" in f for f in flags)


def test_stale_note_flagged(fresh_db):
    ctx = data.meeting_context(_meeting_id("Marrowstone Bulk"))   # note from Feb 2026, meeting Dec 2026
    assert any("months old" in f for f in llm.deterministic_unverified(ctx))


def test_groq_citations_are_sanitised(fresh_db, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test")
    fake = {"brief_markdown": "Tier 1 client [account.tier]. They have 400 ships [account.fleet_size].",
            "fields_used": ["account.tier", "account.fleet_size", "made.up"],
            "unverified": ["Fleet size unknown"]}
    monkeypatch.setattr(llm, "_groq_json", lambda *a, **k: fake)
    ctx = data.meeting_context(_meeting_id("Harrowgate Tankers"))
    res = llm.generate_brief(ctx)
    assert res.generator.startswith("groq:")
    assert "[account.fleet_size]" not in res.content["markdown"]
    assert "[unverified]" in res.content["markdown"]
    assert res.sources == ["account.tier"]
    assert any("unknown field" in u for u in res.unverified)
    assert "Fleet size unknown" in res.unverified


def test_groq_failure_falls_back(fresh_db, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test")

    def boom(*a, **k):
        raise TimeoutError("network")
    monkeypatch.setattr(llm, "_groq_json", boom)
    res = llm.generate_brief(data.meeting_context(_meeting_id("Harrowgate Tankers")))
    assert res.generator == "template" and "TimeoutError" in res.note


FORM = {"what_happened": "Good chat with the MD.", "interest_level": "high", "objections": "Price / fees; Credit terms",
        "next_step": "Send pricing", "next_step_date": "2026-12-09", "decision_maker_present": False,
        "app_signup": True, "trial_started": False}


def test_debrief_template(fresh_db, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    m = data.meeting(_meeting_id("Orrin Petroleum Marine"))
    res = llm.structure_debrief(m, FORM, data.person(m["owner_id"]), "Helen Brask")
    assert res.generator == "template"
    assert "Send pricing" in res.content["email_body"] and "2026-12-09" in res.content["email_body"]
    assert res.content["email_body"].startswith("Dear Helen")
    assert "No decision-maker present" in res.content["notes_markdown"]


def test_debrief_form_overrides_model(fresh_db, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test")
    monkeypatch.setattr(llm, "_groq_json", lambda *a, **k: {
        "summary": "s", "interest": "low", "objections": ["x"], "risks": [], "open_questions": [],
        "email_subject": "subj", "email_body": "body"})
    m = data.meeting(_meeting_id("Orrin Petroleum Marine"))
    res = llm.structure_debrief(m, FORM, data.person(m["owner_id"]), "Helen Brask")
    assert res.content["parts"]["interest"] == "high"
    assert "Send pricing (by 2026-12-09)" in res.content["notes_markdown"]


def test_learnings_template():
    stats = {"conversion_by_tier": [{"tier": 1, "held": 4, "signups": 3, "trials": 2, "signup_rate": 75.0, "trial_rate": 50.0},
                                    {"tier": 3, "held": 2, "signups": 0, "trials": 0, "signup_rate": 0.0, "trial_rate": 0.0}],
             "top_objections": [("Price / fees", 4), ("Port coverage", 3)],
             "dm_effect": {"with": 80.0, "without": 20.0},
             "candidates": [{"name": "Qamar Sea Logistics"}]}
    md = llm.template_learnings(stats)
    assert "tier 1" in md.lower() and "pricing sheet" in md.lower() and "Qamar Sea Logistics" in md
