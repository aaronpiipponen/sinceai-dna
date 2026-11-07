# -*- coding: utf-8 -*-
"""Offline tests for the multi-turn adapter.

No network: `dna.call_model` is monkeypatched with canned replies, so these
tests exercise the protocol, the validators and the consent bookkeeping only.

    python3 -m unittest app/test_turns.py
"""

import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import dna  # noqa: E402
import present  # noqa: E402
import turns  # noqa: E402
from dsakit import minischema  # noqa: E402

with open(os.path.join(dna.SIMSET, "schema", "submission.schema.json"), encoding="utf-8") as fh:
    SCHEMA = json.load(fh)

CASE = {
    "case_id": "TEST-MT-1",
    "journey": "clicked_link",
    "audience": "consumer",
    "locale": "en-GB",
    "language": "en",
    "persona": {"segment": "adult", "age_band": "30-49", "tech_confidence": "medium",
                "emotional_state": "worried", "language": "en"},
    "entry_point": "operator_app_chat",
    "user_identified": True,
    "opening_message": "I clicked a link in a text message and now I am worried.",
    "signals": {
        "artifact": {"type": "sms", "channel_language": "en", "sender": "+358 40 123 4567",
                     "body": "Your parcel is waiting: https://parcel.example.net/track",
                     "links": ["https://parcel.example.net/track"],
                     "received_at": "2026-11-08T08:00:00+02:00"},
        "link_check": {"url": "https://parcel.example.net/track", "verdict": "suspicious",
                       "confidence": 0.8, "categories": ["phishing"], "domain_age_days": 2,
                       "checked_at": "2026-11-08T09:00:00+02:00"},
        "call_warning": None,
        "subscription": {"products": [{"type": "mobile", "esim": False}],
                         "recent_events": [], "network_status": "available_with_consent"},
        "device": {"summary": {"platform": "android"},
                   "recent_app_installs": [],
                   "security_findings": {"unknown_profiles": [], "remote_access_apps": [],
                                         "accessibility_services": []}},
        "operator_account": {"recent_logins": "available_with_consent"},
        "credential_exposure": None,
    },
    "signal_availability": {"link_check": "available", "call_warning": "not_applicable"},
    "consent": {
        "requires_consent": ["subscription.network_status", "device.security_findings",
                             "operator_account.recent_logins"],
        "pre_granted": ["device.security_findings"],
    },
}

START = {"type": "start", "conversation_id": "conv-1", "case": CASE, "max_assistant_turns": 6}

QUESTION = {"type": "question", "text": "Did you enter your card details on that page?",
            "topics": ["card_details_entered"]}
WHO_STARTED = {"type": "question", "text": "Did you start this change yourself?",
               "topics": ["self_initiated"]}

ANSWER = {
    "case_id": CASE["case_id"],
    "risk_level": "high",
    "urgency": "today",
    "primary_action": "change_password_and_enable_mfa",
    "advice_text": "Change your password now from a trusted device and sign out of all sessions. "
                   "Turn on two-step verification. Check that nobody else is signed in to your account.",
    "steps": ["Change the password", "Sign out of all sessions", "Turn on two-step verification"],
    "escalation_required": False,
    "escalation_target": None,
    "questions_asked": [],
    "question_topics": [],
    "signals_used": ["artifact", "link_check"],
    "consent_requested_for": [],
    "citations": ["guidance_parcel_scam"],
    "confidence": 0.7,
}
FINAL = {"type": "final", "answer": ANSWER}

LOGINS = "operator_account.recent_logins"
CONSENT = {"type": "consent_request", "fields": [LOGINS],
           "text": "May I check your recent sign-ins to see whether anyone else accessed your account?"}


def schema_errors(answer):
    """Validate against the submission schema, ignoring non-schema inspector keys."""
    clean = {k: v for k, v in answer.items() if k in SCHEMA["properties"]}
    return minischema.validate(clean, SCHEMA)


class FakeModel:
    def __init__(self, *replies):
        self.replies = [r if isinstance(r, str) else json.dumps(r, ensure_ascii=False) for r in replies]
        self.calls = []

    def __call__(self, messages, **kwargs):
        self.calls.append(messages)
        if not self.replies:
            raise AssertionError("unexpected extra model call")
        text = self.replies.pop(0)
        return text, {"model": "fake", "temperature": kwargs.get("temperature", 0.1),
                      "prompt_hash": "test", "prompt_chars": sum(len(m["content"]) for m in messages),
                      "latency_s": 0.0, "cached": False}


class TurnsTest(unittest.TestCase):
    def run_events(self, replies, events, max_turns=None):
        """Play a canned conversation through step(); return replies, state, fake."""
        canned = list(replies)
        if max_turns is not None:
            events = [dict(e, max_assistant_turns=max_turns) if e["type"] == "start" else e for e in events]
        fake = FakeModel(*canned)
        original = dna.call_model
        dna.call_model = fake
        try:
            state = {}
            out = [turns.step(event, state) for event in events]
        finally:
            dna.call_model = original
        return out, state, fake

    def assert_trace(self, reply):
        self.assertIn("trace", reply)
        trace = reply["trace"]
        for key in ("raw_text", "rules", "meta", "fallback", "error"):
            self.assertIn(key, trace)

    def assert_final(self, reply):
        self.assertEqual(reply["type"], "final")
        self.assert_trace(reply)
        answer = reply["answer"]
        self.assertNotIn("trace", answer)
        self.assertEqual(schema_errors(answer), [], answer)
        self.assertIn(answer["primary_action"], dna.ACTION_NAMES)
        self.assertIn(answer["risk_level"], dna.RISK_LEVELS)
        self.assertTrue(answer["advice_text"].strip())
        return answer

    # --- required flows ----------------------------------------------------

    def test_timeout_returns_marked_rules_fallback(self):
        def timeout(messages, **kwargs):
            self.assertEqual(kwargs.get("timeout"), turns.DEADLINE_S[False])
            raise TimeoutError("timed out")

        original = dna.call_model
        dna.call_model = timeout
        try:
            state = {}
            reply = turns.step(START, state, thinking=False)
        finally:
            dna.call_model = original
        self.assertEqual(reply["type"], "final")
        self.assertTrue(reply["fallback"])
        self.assertTrue(reply["trace"]["fallback"])
        block = present.display(state["case"], state, reply, "en")
        self.assertTrue(block["answer"]["fallback"])

        # A reply cut by the output cap must fall back too, even though the
        # repair could close it: the missing tail may hold a needed step.
        def truncated(messages, **kwargs):
            return ('{"risk_level": "low", "advice_text": "Never share the code',
                    {"truncated": True})

        dna.call_model = truncated
        try:
            state = {}
            reply = turns.step(START, state, thinking=False)
        finally:
            dna.call_model = original
        self.assertEqual(reply["type"], "final")
        self.assertTrue(reply["fallback"], "a truncated reply was used")
        self.assertEqual(reply["trace"]["error"], "reply hit the output cap")
        self.assertNotIn("Never share", reply["answer"]["advice_text"])

        # Neither the case id nor the conversation id reaches the model.
        state = {}
        turns._reset(START, state)
        blob = json.dumps(turns.prompt(state["case"], state), ensure_ascii=False)
        self.assertNotIn(CASE["case_id"], blob)
        self.assertNotIn(START["conversation_id"], blob)

    def test_question_then_final_keeps_fact_after_followup(self):
        out, state, fake = self.run_events(
            [QUESTION, FINAL, FINAL],
            [START, {"type": "user_reply", "text": "No, I closed the page before typing anything."},
             {"type": "user_reply", "text": "What if I already paid?"}],
        )
        self.assertEqual(out[0]["type"], "question")
        self.assert_trace(out[0])
        self.assertEqual(out[0]["topics"], ["card_details_entered"])
        self.assertTrue(out[0]["text"].endswith("?"))

        answer = self.assert_final(out[1])
        self.assertEqual(answer["question_topics"], ["card_details_entered"])
        self.assertEqual(answer["questions_asked"], [QUESTION["text"]])
        self.assertEqual(state["facts"], {"card_details_entered": "No, I closed the page before typing anything."})
        self.assertEqual(state["turns"], 1)
        self.assertEqual(len(fake.calls), 3, "one model call per turn")
        self.assertFalse(out[1]["trace"]["fallback"])
        # The follow-up must not be stored as the answer to the earlier question.
        self.assertEqual(state["last_topics"], [])
        self.assertEqual(state["facts"], {"card_details_entered": "No, I closed the page before typing anything."})

    def test_consent_refusal_strips_refused_signals(self):
        final = {"type": "final", "answer": dict(ANSWER, signals_used=["artifact", LOGINS])}
        out, state, _ = self.run_events(
            [CONSENT, final],
            [START, {"type": "consent_reply", "granted": [], "refused": [LOGINS],
                     "text": "No, I would rather not.", "signals": {}}],
        )
        self.assertEqual(out[0]["type"], "consent_request")
        self.assertEqual(out[0]["fields"], [LOGINS])
        self.assertIn("recent sign-ins", out[0]["text"])

        answer = self.assert_final(out[1])
        self.assertNotIn(LOGINS, answer["signals_used"])
        self.assertEqual(answer["consent_requested_for"], [LOGINS])
        self.assertIn("did not use", answer["advice_text"])
        rules = [r["rule"] for r in out[1]["trace"]["rules"]]
        self.assertIn("consent_refused_signal_removed", rules)
        self.assertEqual(state["refused"], [LOGINS])
        # useful advice: normalise kept the model's action and real advice
        self.assertGreaterEqual(len(answer["advice_text"].split()), 8)

    def test_consent_grant_fills_signal_and_keeps_it(self):
        logins = {"recent_logins": [{"days_ago": 1, "country": "FI", "device_known": False,
                                     "result": "success", "browser": "GRANTED-SENTINEL-1"}]}
        refused_value = {"found": True, "sources": [
            {"service_category": "REFUSED-SENTINEL-2", "exposed": ["email"], "days_ago": 2}]}
        full = json.loads(json.dumps(CASE))
        full["signals"]["credential_exposure"] = refused_value
        full["consent"]["requires_consent"].append("credential_exposure")
        final = {"type": "final", "answer": dict(ANSWER, signals_used=["artifact", LOGINS])}
        out, state, fake = self.run_events(
            [CONSENT, final],
            [dict(START, case=full),
             {"type": "consent_reply", "granted": [LOGINS],
              "refused": ["credential_exposure"], "text": "Yes, go ahead.",
              "signals": {LOGINS: logins}}],
        )
        self.assertEqual(state["case"]["signals"]["operator_account"]["recent_logins"], logins)
        answer = self.assert_final(out[1])
        self.assertIn(LOGINS, answer["signals_used"])
        rules = [r["rule"] for r in out[1]["trace"]["rules"]]
        self.assertNotIn("consent_refused_signal_removed", rules)
        self.assertNotIn("consent_not_granted_signal_removed", rules)

        # Check: the granted value reaches the model and the deterministic
        # engine; the refused value reaches neither.
        final_prompt = json.dumps(fake.calls[-1], ensure_ascii=False)
        self.assertIn("GRANTED-SENTINEL-1", final_prompt)
        self.assertNotIn("REFUSED-SENTINEL-2", final_prompt)
        engine_blob = json.dumps(turns.engine_case(state), ensure_ascii=False)
        self.assertIn("GRANTED-SENTINEL-1", engine_blob)
        self.assertNotIn("REFUSED-SENTINEL-2", engine_blob)

    def test_consent_reply_is_permission_and_does_not_answer_who_started(self):
        # Permission to inspect a record is not a fact about who started the
        # change. The prompt must say so, the state must not store it as a
        # self_initiated answer, and a following question on that topic must
        # still be delivered.
        logins = {"recent_logins": [{"days_ago": 1, "country": "FI",
                                     "device_known": False, "result": "success",
                                     "browser": "GRANTED-SENTINEL-1"}]}
        refused_value = {"found": True, "sources": [
            {"service_category": "REFUSED-SENTINEL-2", "exposed": ["email"], "days_ago": 2}]}
        full = json.loads(json.dumps(CASE))
        full["signals"]["subscription"]["network_status"] = "NETWORK-SENTINEL-3"
        full["signals"]["credential_exposure"] = refused_value
        full["consent"]["requires_consent"].append("credential_exposure")
        out, state, fake = self.run_events(
            [CONSENT, WHO_STARTED],
            [dict(START, case=full),
             {"type": "consent_reply", "granted": [LOGINS],
              "refused": ["credential_exposure"], "text": "Yes, go ahead.",
              "signals": {LOGINS: logins}}],
        )
        self.assertEqual(out[0]["type"], "consent_request")
        self.assertEqual(out[1]["type"], "question", out[1]["trace"].get("error"))
        self.assertEqual(out[1]["topics"], ["self_initiated"])

        consent_row = next(m for m in state["history"]
                           if m.get("content") == "Yes, go ahead.")
        self.assertEqual(consent_row.get("type"), "consent_reply")
        self.assertEqual(state["facts"], {})

        body = fake.calls[-1][1]["content"]
        consent_line = next(line for line in body.splitlines()
                            if "Yes, go ahead." in line)
        self.assertIn("consent reply", consent_line.lower())
        self.assertIn("permission", consent_line.lower())
        self.assertNotIn("USER: Yes, go ahead.", body)
        self.assertIn("GRANTED-SENTINEL-1", body)
        self.assertNotIn("REFUSED-SENTINEL-2", body)
        self.assertNotIn("NETWORK-SENTINEL-3", body)

    def test_more_than_two_topics_trimmed(self):
        question = {"type": "question", "text": "Did you enter your card details on that page?",
                    "topics": ["card_details_entered", "code_shared", "money_transferred"]}
        out, _, _ = self.run_events([question, FINAL], [START])
        self.assertEqual(out[0]["type"], "question")
        self.assertEqual(len(out[0]["topics"]), 2)
        self.assertEqual(out[0]["topics"], ["card_details_entered", "code_shared"])
        self.assertIn("question_topics_trimmed", [r["rule"] for r in out[0]["trace"]["rules"]])

    def test_junk_reply_falls_back_to_rules(self):
        out, _, _ = self.run_events(["I am sorry, I cannot do that."], [START])
        self.assertEqual(out[0]["type"], "final")
        self.assertTrue(out[0]["trace"]["fallback"])
        self.assertEqual(out[0]["trace"]["error"], "no JSON object in reply")
        self.assert_final(out[0])

    def test_turn_limit_event_returns_final(self):
        out, _, _ = self.run_events([QUESTION, FINAL], [START, {"type": "turn_limit"}])
        self.assertEqual(out[0]["type"], "question")
        answer = self.assert_final(out[1])
        self.assertEqual(answer["question_topics"], ["card_details_entered"])

    def test_exhausted_turns_force_final(self):
        # max 1 turn: after the question the next event must produce a final,
        # even though the model (canned) tries to ask again.
        out, _, _ = self.run_events([QUESTION, QUESTION],
                                    [START, {"type": "user_reply", "text": "No."}], max_turns=1)
        self.assertEqual(out[0]["type"], "question")
        self.assertEqual(out[1]["type"], "final")
        self.assertTrue(out[1]["trace"]["fallback"])
        self.assert_final(out[1])

    def test_unbounded_questions_and_follow_up_after_final(self):
        questions = [
            QUESTION,
            {"type": "question", "text": "What day was it?", "topics": []},
            {"type": "question", "text": "How did it start?", "topics": []},
            {"type": "question", "text": "What did you notice first?", "topics": []},
            {"type": "question", "text": "Who was involved?", "topics": []},
            {"type": "question", "text": "What are you most worried about?", "topics": []},
            {"type": "question", "text": "Is there anything else you remember?", "topics": []},
            {"type": "question", "text": "What would you like help with?", "topics": []},
        ]
        revised = {"type": "final", "answer": dict(
            ANSWER, primary_action="verify_via_official_channel",
            risk_level="medium", urgency="routine")}
        long_followup = ("I thought about it for a while. " * 20) + "I gave them the code."
        events = [dict(START, max_assistant_turns=None)]
        events.append({"type": "user_reply", "text": "No, I did not enter card details."})
        events += [{"type": "user_reply", "text": "I am not sure yet."}
                   for _ in questions[1:]]
        events.append({"type": "user_reply", "text": long_followup})

        out, state, fake = self.run_events(questions + [FINAL, revised], events)

        self.assertGreater(len(questions), 6)
        self.assertEqual([r["type"] for r in out[:len(questions)]], ["question"] * len(questions))
        self.assertEqual(out[0]["topics"], ["card_details_entered"])
        self.assertTrue(all(r["topics"] == [] for r in out[1:len(questions)]))
        self.assert_final(out[len(questions)])
        answer = self.assert_final(out[-1])
        self.assertEqual(answer["primary_action"], "change_password_and_enable_mfa")
        self.assertIn("I gave them the code.", json.dumps(fake.calls[-1], ensure_ascii=False),
                      "the live transcript clipped the action-changing part of the reply")
        engine = turns.engine_case(state)
        self.assertIn("No, I did not enter card details.", engine["user_replies"])
        self.assertIn("I gave them the code.", engine["user_replies"])
        self.assertIsNone(state["max_turns"])

        with self.subTest("a turn_limit final is not terminal"):
            more = {"type": "question", "text": "What did you notice first?", "topics": []}
            out, _, _ = self.run_events(
                [QUESTION, FINAL, more],
                [dict(START, max_assistant_turns=None), {"type": "turn_limit"},
                 {"type": "user_reply", "text": "Actually I gave them the code."}],
            )
            self.assertEqual(out[1]["type"], "final")
            self.assertEqual(out[2]["type"], "question")

    def test_final_with_junk_fields_is_normalised(self):
        junk = {"type": "final", "answer": {"risk_level": "banana", "primary_action": "nonsense",
                                            "advice_text": "Do it.", "escalation_required": True,
                                            "citations": ["made_up"], "confidence": 9}}
        out, _, _ = self.run_events([junk], [START])
        answer = self.assert_final(out[0])
        self.assertNotEqual(answer["primary_action"], "nonsense")
        self.assertNotIn("made_up", answer["citations"])

    # --- conversation safety ------------------------------------------------

    def test_revealed_topic_is_not_reasked(self):
        # The model only re-asks an answered topic. The question is not
        # delivered, but the turn must still end in a model final built from
        # the facts already given, not in the rules fallback.
        out, state, fake = self.run_events(
            [QUESTION, QUESTION, FINAL],
            [START, {"type": "user_reply", "text": "No card details."}])
        self.assertEqual(out[0]["type"], "question")
        self.assert_final(out[1])
        self.assertFalse(out[1]["trace"]["fallback"])
        self.assertIsNone(out[1]["trace"]["error"])
        self.assertIn("reasked_topic_dropped",
                      [r["rule"] for r in out[1]["trace"]["rules"]])
        self.assertIn("Change your password", out[1]["trace"]["raw_text"])
        self.assertEqual(len(fake.calls), 3,
                         "the rejected question needs a second, forced model call")
        self.assertEqual(state["asked_questions"], [QUESTION["text"]])

        # A deliberate topics:[] clarification is allowed; the re-asked
        # topic above still is not.
        with self.subTest("topicless clarification"):
            clarify = {"type": "question", "text": "What happened?", "topics": []}
            out, _, _ = self.run_events(
                [clarify, FINAL],
                [START, {"type": "user_reply", "text": "Someone called me."}],
            )
            self.assertEqual(out[0]["type"], "question")
            self.assertEqual(out[0]["topics"], [])
            self.assertIn("question_topicless_clarification",
                          [r["rule"] for r in out[0]["trace"]["rules"]])
            self.assert_final(out[1])

    def test_question_in_wrong_language_falls_through_to_final(self):
        question = {"type": "question", "text": "Sinä olet syöttänyt korttisi tiedot ja nyt sinä olet maksanut?",
                    "topics": ["card_details_entered"]}
        out, _, _ = self.run_events([question], [START])
        self.assertEqual(out[0]["type"], "final")
        self.assertTrue(out[0]["trace"]["fallback"])
        self.assert_final(out[0])

    def test_consent_request_never_reoffers_refused_field(self):
        out, _, _ = self.run_events(
            [CONSENT, CONSENT],
            [START, {"type": "consent_reply", "granted": [], "refused": [LOGINS],
                     "text": "No.", "signals": {}}],
        )
        self.assertEqual(out[0]["type"], "consent_request")
        self.assertEqual(out[1]["type"], "final")
        self.assertTrue(out[1]["trace"]["fallback"])
        self.assert_final(out[1])

    def test_consent_gated_signal_is_masked_before_grant(self):
        # The adapter must not trust the caller to mask a consent-gated signal.
        full = json.loads(json.dumps(CASE))
        full["signals"]["operator_account"]["recent_logins"] = [{"days_ago": 1, "country": "RU"}]
        event = dict(START, case=full)
        out, state, _ = self.run_events([FINAL], [event])
        self.assertEqual(state["case"]["signals"]["operator_account"]["recent_logins"], turns.AVAILABLE)
        self.assert_final(out[0])

        # A final that states an ungranted gated fact is rejected to the rules
        # fallback, and the reply says so instead of reporting a model answer.
        leaky = {"type": "final", "answer": dict(
            ANSWER, signals_used=["artifact"],
            advice_text="Your network connection is working fine, so nothing is wrong.")}
        out, _, fake = self.run_events([leaky], [dict(START, case=json.loads(json.dumps(CASE)))])
        self.assertEqual(len(fake.calls), 1)
        self.assertTrue(out[0]["fallback"])
        self.assertTrue(out[0]["trace"]["fallback"])
        self.assertEqual(out[0]["trace"]["error"], "advice states a consent-gated fact")
        self.assertIn("consent_unsafe_advice",
                      [r["rule"] for r in out[0]["trace"]["rules"]])
        self.assertNotIn("network connection", out[0]["answer"]["advice_text"])
        self.assert_final(out[0])

    def test_normalise_gets_no_placeholder_strings(self):
        # dna.normalise reads operator_account.recent_logins as a list; the
        # protocol placeholder is a string and used to crash it on a breach
        # notice, silently replacing a model answer with the rules fallback.
        case = json.loads(json.dumps(CASE))
        case["case_id"] = "TEST-MT-2"
        case["journey"] = "breach_notice"
        case["opening_message"] = "I got a breach notice saying my details leaked."
        out, state, _ = self.run_events([FINAL], [dict(START, case=case)])

        answer = self.assert_final(out[0])
        self.assertFalse(out[0]["trace"]["fallback"], out[0]["trace"]["error"])
        self.assertEqual(answer["primary_action"], ANSWER["primary_action"])
        self.assertEqual(state["case"]["signals"]["operator_account"]["recent_logins"], turns.AVAILABLE)
        engine_case = turns.engine_case(state)
        self.assertNotIn("recent_logins", engine_case["signals"]["operator_account"])


if __name__ == "__main__":
    unittest.main()
