import json

import pytest

from routecheck import CLARIFY, KeywordRouter, RouteCheck, find_action_cue


@pytest.fixture(scope="module")
def router(tmp_path_factory):
    log = tmp_path_factory.mktemp("logs") / "audit.jsonl"
    return RouteCheck(min_confidence=0.7, min_margin=0.0, cue_weight=0.7, log_path=log)


def test_lenai_case_draft_email_is_not_a_search(router):
    assert router.route("Draft an email").action == "draft_email"


@pytest.mark.parametrize("text, tool", [
    ("Write an email asking for the policy document", "draft_email"),
    ("Find the training deck on writing client emails", "search_documents"),
    ("Summarize this email thread for me", "summarize_document"),
    ("Set a meeting to go over the claim backlog", "schedule_meeting"),
])
def test_action_beats_topic_words(router, text, tool):
    assert router.route(text).action == tool


@pytest.mark.parametrize("text", ["email", "claims", "Monday's meeting", "help"])
def test_bare_topics_get_a_question(router, text):
    d = router.route(text)
    assert d.action == CLARIFY
    assert d.question and len(d.options) == 2


def test_earliest_action_wins():
    tool, phrase = find_action_cue("Write a reply asking them to find the contract")
    assert tool == "draft_email" and phrase.lower() == "write"


def test_claim_status_needs_a_claim():
    assert find_action_cue("Is the meeting approved?")[0] != "claim_status"
    assert find_action_cue("Has my claim been approved?")[0] == "claim_status"


def test_every_decision_is_logged(router):
    router.route("Book a call with Priya on Friday")
    lines = router.log_path.read_text().strip().splitlines()
    rec = json.loads(lines[-1])
    assert rec["request"] == "Book a call with Priya on Friday"
    assert rec["action"] == "schedule_meeting"
    assert set(rec["scores"]) >= {"draft_email", "search_documents"}


def test_baseline_always_routes():
    assert KeywordRouter().route("help").action != CLARIFY
