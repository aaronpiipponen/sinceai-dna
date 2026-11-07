#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for app/present.py. No model calls, no network.

    python3 -m unittest app/test_present.py

Real dev and sample cases are run through the rules baseline (`dna.fallback`)
so the advice text, cites and steps are realistic, then the display block is
walked for shape, language and leaks.
"""

import copy
import json
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
SIMSET = os.path.join(PROJECT, "DNA_Digital_Security_Assistant_SimSet_v2.0.1")
sys.path.insert(0, HERE)
sys.path.insert(0, SIMSET)

import dna  # noqa: E402
import present  # noqa: E402
import turns  # noqa: E402

DEV = os.path.join(SIMSET, "data", "dev", "cases.jsonl")
TEST_INPUTS = os.path.join(SIMSET, "data", "test", "inputs.jsonl")
SAMPLES = os.path.join(SIMSET, "data", "samples", "five_journeys.jsonl")


def read_jsonl(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


DEV_CASES = read_jsonl(DEV)
TEST_CASES = read_jsonl(TEST_INPUTS)
SAMPLE_CASES = read_jsonl(SAMPLES)


def visible(case):
    """The case as turns.step sees it: visible fields, gated signals masked."""
    return turns._initial_case(case)


def engine_case(case):
    """The same case with ungranted gated signals removed, for dna.fallback()."""
    c = copy.deepcopy(visible(case))
    consent = c.get("consent") or {}
    keep = set(consent.get("pre_granted") or [])
    for path in consent.get("requires_consent") or []:
        if path in keep or not isinstance(path, str):
            continue
        parts = path.split(".")
        cur = c.get("signals") or {}
        for part in parts[:-1]:
            cur = cur.get(part) if isinstance(cur, dict) else None
        if isinstance(cur, dict):
            cur.pop(parts[-1], None)
    return c


def rules_answer(case):
    """A real, schema-shaped final answer without touching the model."""
    try:
        return dna.fallback(engine_case(case))
    except Exception:  # the baseline cannot always read a case; pick another
        return None


def get_case(predicate):
    for case in DEV_CASES + SAMPLE_CASES:
        if predicate(case) and rules_answer(case):
            return case
    raise unittest.SkipTest("no matching case")


def walk(obj, path=""):
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield path + "/" + str(key), value
            yield from walk(value, path + "/" + str(key))
    elif isinstance(obj, list):
        for i, value in enumerate(obj):
            yield "%s/%d" % (path, i), value


def strings(obj, skip=()):
    for path, value in walk(obj):
        if isinstance(value, str) and not any(s in path for s in skip):
            yield path, value


def state_for(case, facts=None, granted=None, refused=None):
    return {"case": visible(case), "facts": facts or {},
            "granted": list(granted or []), "refused": list(refused or [])}


class ConsentCoverageTest(unittest.TestCase):
    """A gated path without wording would crash or show a raw path."""

    def test_consent_table_covers_every_gated_path_in_dev_test_and_samples(self):
        seen = set()
        for case in DEV_CASES + TEST_CASES + SAMPLE_CASES:
            for path in (case.get("consent") or {}).get("requires_consent") or []:
                if isinstance(path, str):
                    seen.add(path)
        self.assertTrue(seen, "no consent-gated paths found")
        missing = seen - set(present.CONSENT)
        self.assertFalse(missing, "no consent wording for %s" % sorted(missing))
        for path in seen:
            self.assertIn(path, present.SIGNALS)

class DisplayShapeTest(unittest.TestCase):
    def setUp(self):
        self.case = get_case(lambda c: c.get("language") == "fi" and c.get("journey") == "clicked_link")
        self.answer = rules_answer(self.case)
        self.reply = {"type": "final", "answer": self.answer}

    def test_keys_are_always_present(self):
        block = present.display(visible(self.case), state_for(self.case), self.reply, "fi")
        self.assertEqual(set(block), {"attachment", "question", "quick_replies", "consent",
                                      "answer", "handoff", "handoff_status", "visibility"})
        self.assertIsNotNone(block["attachment"])
        self.assertIsNotNone(block["visibility"])
        self.assertIsNotNone(block["answer"])
        self.assertIsNone(block["question"])
        self.assertIsNone(block["quick_replies"])
        self.assertIsNone(block["consent"])

    def test_attachment_is_plain_text_with_checks(self):
        block = present.display(visible(self.case), state_for(self.case), self.reply, "fi")
        att = block["attachment"]
        self.assertIn(att["kind"], present.ATTACHMENT_KINDS)
        self.assertTrue(att["kind_label"])
        self.assertNotIn("<a", att["body"].lower())
        self.assertTrue(att["checks"])
        for row in att["checks"]:
            self.assertIn(row["tone"], ("warn", "ok", "unknown"))
            self.assertTrue(row["text"])

    def test_reason_and_steps_are_short(self):
        block = present.display(visible(self.case), state_for(self.case), self.reply, "fi")
        answer = block["answer"]
        self.assertLessEqual(len(answer["reason"]), 201)
        self.assertTrue(answer["reason"])
        self.assertLessEqual(len(answer["steps"]), 5)
        for step in answer["steps"]:
            self.assertIsInstance(step, str)
            self.assertTrue(step.strip())

    def test_steps_fall_back_to_advice_sentences(self):
        answer = dict(self.answer, steps=[])
        answer["advice_text"] = ("Älä avaa linkkiä uudelleen. Poista viesti. "
                                 "Tarkista asia pankin omasta sovelluksesta. Soita pankkiin, jos huomaat outoja maksuja.")
        block = present.answer_block(visible(self.case), state_for(self.case), answer, "fi")
        self.assertEqual(block["steps"], ["Poista viesti.",
                                          "Tarkista asia pankin omasta sovelluksesta.",
                                          "Soita pankkiin, jos huomaat outoja maksuja."])

    def test_advice_sentence_missing_from_reason_and_steps_appears_in_more(self):
        answer = dict(self.answer, steps=["Älä avaa linkkiä uudelleen."])
        answer["advice_text"] = ("Viesti on huijaus. Älä avaa linkkiä uudelleen. "
                                 "Älä soita viestissä annettuun numeroon. "
                                 "Soita 112, jos olet vaarassa.")
        block = present.answer_block(visible(self.case), state_for(self.case), answer, "fi")
        self.assertEqual(block["reason"], "Viesti on huijaus.")
        self.assertNotIn("Älä avaa linkkiä uudelleen.", block["more"])
        self.assertIn("Älä soita viestissä annettuun numeroon.", block["more"])
        self.assertIn("Soita 112, jos olet vaarassa.", block["more"])

    def test_long_first_sentence_is_cut_at_a_word(self):
        answer = dict(self.answer, steps=["x"])
        answer["advice_text"] = " ".join(["sana"] * 80) + "."
        reason = present.answer_block(visible(self.case), state_for(self.case), answer, "fi")["reason"]
        self.assertLessEqual(len(reason), 201)
        self.assertTrue(reason.endswith("…"))
        self.assertNotIn("… ", reason)

    def test_question_gets_localised_quick_replies(self):
        case = visible(self.case)
        asked = {
            "fi": ("Syötitkö korttitietosi sivulle?", "korttitiedot"),
            "en": ("Did you enter your card details on the page?", "card details"),
            "sv": ("Skrev du in dina kortuppgifter på sidan?", "kortuppgifter"),
        }
        for lang, (text, word) in asked.items():
            reply = {"type": "question", "text": text, "topics": ["card_details_entered"]}
            block = present.display(case, state_for(self.case), reply, lang)
            self.assertEqual(block["question"], {"text": text})
            self.assertEqual(len(block["quick_replies"]), 3)
            self.assertTrue(all(isinstance(q, str) and q for q in block["quick_replies"]))
            self.assertIn(word, block["quick_replies"][0])

    def test_open_question_gets_no_topic_chips(self):
        case = visible(self.case)
        asked = {
            "fi": "Mitä viestissä sanottiin?",
            "en": "What did the text say?",
            "sv": "Vad stod det i meddelandet?",
        }
        for lang, text in asked.items():
            reply = {"type": "question", "text": text, "topics": ["card_details_entered"]}
            block = present.display(case, state_for(self.case), reply, lang)
            self.assertEqual(block["quick_replies"], [present.NOT_SURE[lang]])

    def test_consent_uses_tokens_not_paths(self):
        case = visible(self.case)
        fields = (case.get("consent") or {}).get("requires_consent") or []
        reply = {"type": "consent_request", "fields": fields[:2], "text": "Saanko?"}
        block = present.display(case, state_for(self.case), reply, "fi")
        consent = block["consent"]
        self.assertEqual(consent["fields"], ["s1", "s2"])
        self.assertEqual([i["field"] for i in consent["items"]], ["s1", "s2"])
        self.assertTrue(consent["title"])
        self.assertTrue(consent["purpose"])
        self.assertEqual(present.resolve_fields(case, ["s1"]), [fields[0]])
        self.assertEqual(present.resolve_fields(case, [fields[1]]), [fields[1]])

    def test_free_attachment_has_no_link_check(self):
        case = copy.deepcopy(visible(self.case))
        case["signals"]["artifact"] = present.artifact_from_attachment(
            "sms", "LUMIPANKKI", "Vahvista tietosi: https://example.invalid/x", "sv")
        case["signals"]["link_check"] = None
        case["signals"]["call_warning"] = None
        block = present.display(case, state_for(case), {"type": "question", "text": "Hej?"}, "sv")
        self.assertEqual(block["attachment"]["kind"], "sms")
        self.assertEqual(block["attachment"]["checks"], [])
        self.assertEqual(block["attachment"]["kind_label"], "Sms")

    def test_handoff_only_when_escalated(self):
        case = visible(self.case)
        answer = dict(self.answer, escalation_required=True, escalation_target="security_specialist")
        brief = {
            "situation": "Korttitiedot syötettiin huijaussivulle.",
            "user_actions": ["SENTINEL-ACTION: Syötit korttitiedot"],
            "open_questions": ["Onko kortilla tehty maksuja?"],
            "evidence": ["Linkkitarkistus: epäilyttävä linkki"],
            "consent": {"granted": [], "refused": []},
            "advice_given": ["Tarkista pankin sovelluksesta"],
            "risk": "high", "priority": "today", "escalation_priority": 4,
            "first_action": "Varmista, lähtikö maksu", "language": "fi",
        }
        state = state_for(self.case)
        state["handoff_status"] = "ready"
        state["handoff_brief"] = brief
        block = present.display(case, state, {"type": "final", "answer": answer}, "fi")
        handoff = block["handoff"]
        self.assertEqual(handoff["target_label"], "Tietoturva-asiantuntija")
        for key in ("situation", "checked", "consent", "advice", "priority"):
            self.assertTrue(handoff[key])
            self.assertIn(key, handoff["labels"])
        self.assertEqual(handoff["priority"], present.URGENCY_LABELS["today"]["fi"])
        self.assertEqual(handoff["brief"], brief)
        # The card shows the model's one summary plus open questions. The
        # structured actions are for the expert and are not stitched in.
        self.assertNotIn("SENTINEL-ACTION", handoff["situation"])
        self.assertEqual(handoff["brief"]["user_actions"], brief["user_actions"])
        self.assertIn(brief["open_questions"][0], handoff["situation"])
        self.assertEqual(block["handoff_status"], {"status": "ready", "text": None})

        empty_evidence = dict(brief, evidence=[])
        state["handoff_brief"] = empty_evidence
        block = present.display(case, state, {"type": "final", "answer": answer}, "fi")
        self.assertEqual(block["handoff"]["checked"], "")

        quiet = dict(answer, escalation_required=False, escalation_target=None)
        block = present.display(case, state, {"type": "final", "answer": quiet}, "fi")
        self.assertIsNone(block["handoff"])
        self.assertIsNone(block["handoff_status"])

    def test_handoff_status_never_invents_a_brief(self):
        case = visible(self.case)
        answer = dict(self.answer, escalation_required=True, escalation_target="security_specialist")
        for status in ("pending", "failed"):
            state = state_for(self.case)
            state["handoff_status"] = status
            block = present.display(case, state, {"type": "final", "answer": answer}, "fi")
            self.assertIsNone(block["handoff"])
            self.assertEqual(block["handoff_status"]["status"], status)
            self.assertTrue(block["handoff_status"]["text"])
            self.assertEqual(present.handoff_status(state, "fi")["status"], status)

        # A brief without a valid numeric level is not a card either.
        bad = {"situation": "Jotain tapahtui.", "first_action": "Soita.",
               "priority": "today", "escalation_priority": True}
        state = state_for(self.case)
        state["handoff_status"] = "ready"
        state["handoff_brief"] = bad
        block = present.display(case, state, {"type": "final", "answer": answer}, "fi")
        self.assertIsNone(block["handoff"])
        self.assertEqual(block["handoff_status"]["status"], "failed")

class WhyTest(unittest.TestCase):
    def test_facts_checks_and_consent_are_explained(self):
        case = get_case(lambda c: c.get("language") == "fi" and c.get("journey") == "clicked_link")
        case = visible(case)
        path = ((case.get("consent") or {}).get("requires_consent") or [None])[0]
        self.assertIn(path, present.CONSENT)
        label = present.CONSENT[path]["label"]["fi"]
        answer = dict(rules_answer(case))
        answer["signals_used"] = ["artifact", "link_check", path]
        state = state_for(case, facts={"app_installed": "Asensin sovelluksen linkistä"},
                          granted=[path])
        why = present.answer_block(case, state, answer, "fi")["why"]
        joined = " ".join(why["bullets"])
        self.assertIn("Asensin sovelluksen linkistä", joined)
        self.assertIn(label.lower(), joined.lower())
        self.assertTrue(2 <= len(why["bullets"]) <= 4)
        self.assertTrue(why["sources"])

    def test_refused_signal_is_not_claimed_as_used(self):
        case = get_case(lambda c: c.get("language") == "en" and c.get("journey") == "clicked_link")
        path = "operator_account.recent_logins"
        answer = dict(rules_answer(case))
        answer["signals_used"] = [path]
        state = state_for(case, granted=[], refused=[path])
        why = present.answer_block(visible(case), state, answer, "en")["why"]
        self.assertNotIn("Recent sign-ins", " ".join(why["bullets"]))
        visibility = present.visibility(visible(case), state, "en")
        self.assertIn("Recent sign-ins", visibility["refused"])

class NoLeakTest(unittest.TestCase):
    """Nothing the demo must hide may appear in a display string."""

    FORBIDDEN_IDS = (set(dna.ACTION_NAMES) | set(dna.TOPIC_NAMES) | set(dna.SIGNAL_NAMES)
                     | set(dna.GUIDANCE_IDS))
    RISK = set(dna.RISK_LEVELS)

    def cases(self):
        picked = []
        for journey in ("suspicious_message", "clicked_link", "suspicious_call",
                        "breach_notice", "smb_incident"):
            for lang in present.LANGUAGES:
                for case in DEV_CASES + SAMPLE_CASES:
                    if case.get("journey") == journey and case.get("language") == lang and rules_answer(case):
                        picked.append(case)
                        break
        return picked

    def blocks(self):
        for case in self.cases():
            answer = rules_answer(case)
            reply = {"type": "final", "answer": answer}
            state = state_for(case, facts={"card_details_entered": "Kyllä"},
                              granted=["operator_account.recent_logins"])
            yield case, present.display(visible(case), state, reply, case["language"])
            fields = (visible(case).get("consent") or {}).get("requires_consent") or []
            consent = {"type": "consent_request", "fields": fields[:2], "text": "Saanko?"}
            yield case, present.display(visible(case), state, consent, case["language"])
            yield case, present.display(visible(case), state,
                                        {"type": "question", "text": "Kysymys?",
                                         "topics": ["credentials_entered"]}, case["language"])

    def test_no_vocabulary_ids_or_case_ids(self):
        checked = 0
        for case, block in self.blocks():
            checked += 1
            for path, value in strings(block):
                self.assertNotIn(case["case_id"], value, path)
                self.assertNotIn("confidence", value.lower(), path)
                for ident in self.FORBIDDEN_IDS:
                    if len(ident) < 4:
                        continue
                    self.assertNotIn(ident, value, "%s leaks %s" % (path, ident))
                for token in ("available_with_consent", "ground_truth", "scenario_family"):
                    self.assertNotIn(token, value, path)
        self.assertGreaterEqual(checked, 10)

    def test_no_risk_enums_in_server_written_text(self):
        # Prose the user or the model wrote is not ours to police here; labels,
        # headlines, bullets, checks and handoff lines are.
        skip = ("/attachment/body", "/answer/reason", "/answer/steps",
                "/answer/more", "/why/bullets")
        for case, block in self.blocks():
            for path, value in strings(block, skip=skip):
                if path.endswith("/answer/urgency") or path.endswith("/attachment/kind"):
                    continue  # the two enums the contract asks for
                for word in self.RISK:
                    self.assertIsNone(re.search(r"\b%s\b" % word, value, re.I),
                                      "%s leaks risk enum %s" % (path, word))


if __name__ == "__main__":
    unittest.main()
