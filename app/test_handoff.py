# -*- coding: utf-8 -*-
"""Offline tests for the expert handoff brief.

No network: `dna.call_model` is monkeypatched, but the state is built with the
real `turns` helpers, so `turns.engine_case()` is exercised for real.

    python3 -m unittest app/test_handoff.py
"""

import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import dna  # noqa: E402
import grounding  # noqa: E402
import handoff  # noqa: E402
import present  # noqa: E402
import turns  # noqa: E402

LOGINS = "operator_account.recent_logins"

CASE = {
    "case_id": "TEST-HANDOFF-1",
    "journey": "breach_notice",
    "audience": "consumer",
    "locale": "en-GB",
    "language": "en",
    "persona": {"segment": "adult", "age_band": "30-49", "tech_confidence": "medium",
                "emotional_state": "worried", "language": "en"},
    "entry_point": "operator_app_chat",
    "user_identified": True,
    "opening_message": "I got a login alert from a place I have never been.",
    "signals": {
        "artifact": {"type": "email", "channel_language": "en", "sender": "noreply@operator.invalid",
                     "body": "A new sign-in to your account was detected.",
                     "links": [], "received_at": "2026-11-08T08:00:00+02:00"},
        "link_check": None,
        "call_warning": None,
        "subscription": {"products": [{"type": "mobile", "esim": False}],
                         "recent_events": [], "network_status": {"service": "normal"}},
        "device": {"summary": {"platform": "android"},
                   "recent_app_installs": [],
                   "security_findings": {"unknown_profiles": [], "remote_access_apps": [],
                                         "accessibility_services": []}},
        "operator_account": {"recent_logins": [
            {"days_ago": 0, "country": "Lagos", "ip": "203.0.113.77",
             "device_known": False, "result": "success"}]},
        "credential_exposure": None,
    },
    "signal_availability": {"link_check": "not_applicable", "call_warning": "not_applicable"},
    "consent": {"requires_consent": [LOGINS], "pre_granted": []},
}

START = {"type": "start", "conversation_id": "conv-1", "case": CASE,
         "max_assistant_turns": 6}

TRANSCRIPT = [
    {"role": "user", "type": "opening", "text": CASE["opening_message"],
     "ts": "2026-11-08T08:00:00Z"},
    {"role": "assistant", "type": "question",
     "text": "Did you sign in from a hotel?", "topics": ["self_initiated"],
     "ts": "2026-11-08T08:00:05Z"},
    {"role": "user", "type": "reply", "text": "No, I have never been there.",
     "ts": "2026-11-08T08:00:20Z"},
    {"role": "assistant", "type": "consent_request", "fields": [LOGINS],
     "text": "May I check your recent sign-ins?", "ts": "2026-11-08T08:00:25Z"},
    {"role": "user", "type": "consent_reply", "text": "No, you may not look.",
     "granted": [], "refused": [LOGINS], "ts": "2026-11-08T08:00:40Z"},
]

ANSWER = {
    "case_id": CASE["case_id"],
    "risk_level": "high",
    "urgency": "immediate",
    "primary_action": "change_password_and_enable_mfa",
    "advice_text": "Change your password now and turn on two-step verification. "
                   "Sign out of all sessions.",
    "steps": ["Change the password", "Turn on two-step verification"],
    "escalation_required": True,
    "escalation_target": "security_specialist",
    "signals_used": ["artifact"],
    "consent_requested_for": [LOGINS],
    "citations": ["guidance_unknown_login"],
    "confidence": 0.7,
}

QUOTING = {
    "situation": "You got a sign-in alert from an unknown device.",
    "user_actions": ["You said the sign-in was not yours"],
    "open_questions": ["Whether the sign-in was really yours"],
    "evidence": ["The refused login came from Lagos at 203.0.113.77."],
    "consent": {"granted": [], "refused": ["Recent sign-ins"]},
    "advice_given": ["Change your password now"],
    "risk": "high",
    "priority": "today",
    "escalation_priority": 4,
    "first_action": "Confirm whether the sign-in was yours",
    "language": "en",
}

ACCEPTED = {
    "situation": "You got a sign-in alert from an unknown device.",
    "user_actions": ["You said the sign-in was not yours"],
    "open_questions": ["Whether the sign-in was really yours"],
    "evidence": ["The forwarded alert shows a sign-in from a new device."],
    "consent": {"granted": [], "refused": ["Recent sign-ins"]},
    "advice_given": ["Change your password now"],
    "risk": "medium",
    "priority": "routine",
    "escalation_priority": 3,
    "first_action": "Confirm whether the sign-in was yours",
    "language": "en",
}


def refused_state():
    state = {}
    turns._reset(START, state)
    turns._absorb({"type": "user_reply", "text": "No, I have never been there."}, state)
    turns._absorb({"type": "consent_reply", "granted": [], "refused": [LOGINS],
                   "text": "No, you may not look.", "signals": {}}, state)
    return state


def call_with(state, reply, transcript=None, meta=None):
    """Run write_brief with one canned model reply; return (brief, info, calls)."""
    calls = []

    def fake(messages, **kwargs):
        calls.append(messages)
        return reply, dict({"model": "fake", "latency_s": 0.0, "cached": False},
                           **(meta or {}))

    original = dna.call_model
    dna.call_model = fake
    try:
        brief, info = handoff.write_brief(
            state, TRANSCRIPT if transcript is None else transcript, ANSWER, "en")
    finally:
        dna.call_model = original
    return brief, info, calls


class HandoffTest(unittest.TestCase):
    def test_refused_signal_never_reaches_the_model_and_its_quote_is_rejected(self):
        state = refused_state()
        brief, info, calls = call_with(state, json.dumps(QUOTING, ensure_ascii=False))
        sent = json.dumps(calls[0], ensure_ascii=False)
        for value in ("Lagos", "203.0.113.77"):
            self.assertNotIn(value, sent)
            self.assertTrue(any(value in token for token in info["rejected"]),
                            info["rejected"])
        self.assertIsNone(brief)
        self.assertTrue(info["error"])

        identifier = dict(ACCEPTED, evidence=["Linkin tarkistus: domain_age_days 0"])
        brief, info, _ = call_with(state, json.dumps(identifier, ensure_ascii=False))
        self.assertIsNone(brief)
        self.assertIn("domain_age_days", info["rejected"])

    def test_valid_brief_is_accepted_and_caution_only_raised(self):
        state = refused_state()
        brief, info, _ = call_with(state, json.dumps(ACCEPTED, ensure_ascii=False))
        self.assertEqual(info["error"], None)
        self.assertEqual(brief["priority"], "immediate")  # raised from "routine"
        self.assertEqual(brief["risk"], "high")  # raised from "medium"
        # The numeric pickup priority is the model's own level, never derived
        # from risk or the urgency label.
        self.assertEqual(brief["escalation_priority"], 3)
        self.assertEqual(brief["language"], "en")

        for bad in (None, 0, 6, "3", 3.0, True):
            wrong = dict(ACCEPTED)
            if bad is None:
                wrong.pop("escalation_priority")
            else:
                wrong["escalation_priority"] = bad
            with self.subTest(priority=bad):
                brief, info, _ = call_with(state, json.dumps(wrong, ensure_ascii=False))
                self.assertIsNone(brief)
                self.assertIn("escalation_priority", info["error"])

        brief, info, _ = call_with(state, "not json at all")
        self.assertIsNone(brief)
        self.assertTrue(info["error"])

        wrong_language = dict(ACCEPTED, language="fi")
        brief, info, _ = call_with(state, json.dumps(wrong_language, ensure_ascii=False))
        self.assertIsNone(brief)
        self.assertIn("language", info["error"])

    def test_amounts_dates_and_phone_numbers_match_whole_tokens(self):
        rejected = [
            ({"situation": "Payment was 4800 euros"}, "Payment was 480 euros"),
            ({"situation": "Payment was 480 euros"}, "Payment was 4800 euros"),
            ({"situation": "Call +3584000011119"}, "Call +358400001111"),
            ({"situation": "Call +358400001111"}, "Call +3584000011119"),
            ({"situation": "You paid 290 euros"}, "You paid 2,90 euros"),
            ({"situation": "You paid 2,90 euros"}, "You paid 290 euros"),
            ({"situation": "See 4800"}, "Open https://example.com/4800"),
            ({"situation": "It happened 07.11.2025"}, "It happened 07.11.2026"),
        ]
        for brief, source in rejected:
            with self.subTest(rejected=brief["situation"]):
                self.assertTrue(grounding.unknown_facts(list(grounding.strings(brief)), source))

        accepted = [
            ({"situation": "You paid 2.90 euros"}, "You paid 2,90 euros"),
            ({"situation": "You paid 2,90 euros"}, "You paid 2.90 euros"),
            ({"situation": "It happened 2026-11-07"}, "It happened 07.11.2026"),
            ({"situation": "See https://example.com/4800"},
             "See https://example.com/4800"),
            ({"situation": "Call +358400001111"}, "Call +358400001111"),
            ({"situation": "Payment was 4800 euros"}, "Payment was 4800 euros"),
            ({"situation": "Your phone updates are 30 days behind"},
             '"patch_status": "behind_30d"'),
        ]
        for brief, source in accepted:
            with self.subTest(accepted=brief["situation"]):
                self.assertEqual(
                    grounding.unknown_facts(list(grounding.strings(brief)), source), [])

    def test_acronym_compound_checks_only_the_acronym(self):
        # Finnish and Swedish inflect the tail of an acronym-led compound, so
        # only the acronym has to be a fact INPUT carries.
        source = "Soittaja halusi koodin SIM-päivitystä varten."
        self.assertEqual(grounding.unknown_facts(
            ["Koodi pyydettiin SIM-korttiin tehtävää päivitystä varten."], source), [])
        self.assertEqual(grounding.unknown_facts(
            ["Koodi pyydettiin TV-korttiin tehtävää päivitystä varten."], source),
            ["TV-korttiin"])

    def test_capped_reply_never_publishes_a_brief(self):
        state = refused_state()
        # Schema-valid JSON whose prefix parses, but the transport says it was
        # cut at the output cap: no card and no priority may come from it.
        full = json.dumps(dict(ACCEPTED, advice_given=[
            "One", "Two", "Three", "Four", "Five", "Six"]), ensure_ascii=False)
        brief, info, _ = call_with(
            state, full, meta={"truncated": True,
                               "usage": {"completion_tokens": handoff.BRIEF_TOKENS}})
        self.assertIsNone(brief)
        self.assertTrue(info["error"])
        self.assertTrue(info["meta"]["truncated"])
        self.assertFalse(present.valid_brief(brief))
        self.assertIsNone(present.brief_priority(brief))

        # A partial reply that is not valid JSON is a schema failure too.
        brief, info, _ = call_with(state, full[:40])
        self.assertIsNone(brief)
        self.assertTrue(info["error"])

    def test_previous_final_steps_reach_the_prompt_without_hidden_data(self):
        state = refused_state()
        # Build the state as another caller might: hidden metadata at the top
        # level. The reset normally strips it; the payload must too.
        state["case"].update({
            "ground_truth": {"secret": "SECRET-CASE"},
            "simulation": "SECRET-SIM",
            "scenario_family": "SECRET-FAMILY",
            "title": "SECRET-TITLE",
            "tags": ["SECRET-TAG"],
            "difficulty": "SECRET-DIFFICULTY",
            "holdout_family": "SECRET-HOLDOUT",
        })
        transcript = list(TRANSCRIPT) + [
            {"role": "assistant", "type": "final",
             "answer": {"advice_text": "Freeze the card in our app.",
                        "steps": ["Open our app", "Freeze the card"],
                        "risk_level": "high", "urgency": "immediate",
                        "ground_truth": "SECRET-ANSWER"},
             "trace": {"ground_truth": "SECRET-TRACE"},
             "title": "SECRET-ROW-TITLE", "ts": "2026-11-08T08:01:00Z"},
            {"role": "user", "type": "reply",
             "text": "I froze the card, but the payment still shows.",
             "ts": "2026-11-08T08:01:20Z"},
        ]
        brief, info, calls = call_with(
            state, json.dumps(ACCEPTED, ensure_ascii=False), transcript=transcript)
        self.assertIsNotNone(brief, info)
        sent = json.dumps(calls[0], ensure_ascii=False)
        payload = json.loads(calls[0][1]["content"])
        finals = [row for row in payload["transcript"]
                  if row["role"] == "assistant" and row["type"] == "final"]
        self.assertEqual(finals[-1]["steps"], ["Open our app", "Freeze the card"])
        self.assertEqual(finals[-1]["text"], "Freeze the card in our app.")
        self.assertNotIn("trace", finals[-1])
        self.assertEqual(payload["transcript"][-1]["text"],
                         "I froze the card, but the payment still shows.")
        # Authorised, non-gated evidence stays; refused data and hidden
        # metadata never reach the model.
        self.assertIn("A new sign-in to your account was detected.", sent)
        for hidden in ("SECRET-CASE", "SECRET-SIM", "SECRET-FAMILY",
                       "SECRET-TITLE", "SECRET-TAG", "SECRET-DIFFICULTY",
                       "SECRET-HOLDOUT", "SECRET-ANSWER", "SECRET-TRACE",
                       "SECRET-ROW-TITLE", "ground_truth"):
            self.assertNotIn(hidden, sent)
        self.assertNotIn("Lagos", sent)
        self.assertNotIn("203.0.113.77", sent)


if __name__ == "__main__":
    unittest.main()
