# -*- coding: utf-8 -*-
"""Offline tests for the single-turn engine.

No network and no model calls: the tests cover the deterministic layer only -
the safety cue, the consent-placeholder helpers and normalise() over a masked
multi-turn case.

    python3 -m unittest app/test_dna.py
"""

import copy
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import dna  # noqa: E402
from dsakit import textcheck  # noqa: E402

DEV = os.path.join(dna.SIMSET, "data", "dev", "cases.jsonl")
GATED = "available_with_consent"  # dsakit.simulator.SENSITIVE_HIDDEN

LOGINS = "operator_account.recent_logins"
EXPOSURE = "credential_exposure"
LOGIN_SENTINEL = "SENTINEL-LOGIN-7c1"
EXPOSURE_SENTINEL = "SENTINEL-EXPOSURE-9f2"


def _gated_case():
    """A real-shaped case whose gated signals carry distinctive values."""
    return {
        "case_id": "T-CONSENT-1",
        "journey": "breach_notice",
        "audience": "consumer",
        "locale": "en-GB",
        "language": "en",
        "entry_point": "operator_app_chat",
        "user_identified": True,
        "opening_message": "I got a notice about a sign-in I do not recognise.",
        "signals": {
            "artifact": {"type": "email", "body": "A new sign-in was detected."},
            "link_check": None,
            "call_warning": None,
            "operator_account": {"recent_logins": [{
                "days_ago": 0,
                "country": "SENTINELCOUNTRY",
                "device_known": False,
                "result": "success",
                "browser": LOGIN_SENTINEL,
            }]},
            "credential_exposure": {
                "found": True,
                "sources": [{"service_category": EXPOSURE_SENTINEL,
                             "exposed": ["email"], "days_ago": 3}],
            },
        },
        "consent": {"requires_consent": [LOGINS, EXPOSURE], "pre_granted": []},
        "ground_truth": {"secret": "GROUND-TRUTH-SENTINEL"},
        "simulation": {"secret": "SIM-SENTINEL"},
        "scenario_family": "family-sentinel",
        "title": "title-sentinel",
        "tags": ["tag-sentinel"],
        "difficulty": "hard",
        "holdout_family": "holdout-sentinel",
    }


class CaptureRules:
    """Wrap the rules module and remember every case it was asked about."""

    def __init__(self, mod):
        self.mod = mod
        self.seen = []

    def decide(self, case, facts=None):
        self.seen.append(copy.deepcopy(case))
        return self.mod.decide(case, facts)

    def answer_for(self, case, action, used, ask):
        self.seen.append(copy.deepcopy(case))
        return self.mod.answer_for(case, action, used, ask)


SAFE_RAW = {
    "primary_action": "change_password_and_enable_mfa",
    "risk_level": "high",
    "urgency": "today",
    "advice_text": "Change your password now from a trusted device and sign out of all sessions.",
    "steps": [],
    "signals_used": [LOGINS, EXPOSURE, "artifact"],
    "consent_requested_for": [LOGINS, EXPOSURE],
    "confidence": 0.7,
}

SAFETY_POSITIVES = [
    # real dev opening messages (BR-MONITORING-APP, both languages)
    "HELP! My ex seems to know what I write and where I am. Could there be something on my phone?",
    "Tämä huolestuttaa minua. Entinen kumppanini tuntuu tietävän mitä kirjoitan ja missä olen.",
    "Epäilen että ex on laittanut puhelimeeni jonkun seurantasovelluksen. Miten saan sen pois?",
    # wording not in dev: the cue must carry, not the exact template
    "Exäni seuraa puhelintani, mitä teen?",
    "Entinen puolisoni tarkkailee minua koko ajan.",
    "Someone is following me and I think they put an app on my phone.",
    "Min ex-partner vet var jag är och vad jag skriver.",
    "Joku on asentanut puhelimeeni jotain, ex luulee tietävänsä kaiken.",
]

SAFETY_NEGATIVES = [
    # parcel / shipment tracking: the bug this cue used to over-match
    "Klikkasin tilausvahvistuksen seurantalinkkiä ja vasta sitten mietin, olisiko pitänyt.",
    "I clicked the tracking link in an order confirmation and only then wondered.",
    "Missä paketin seurantakoodi syötetään?",
    "Where do I enter the parcel tracking code?",
    "Minun pitää seurata toimitusta, miten se onnistuu?",
    # card / account monitoring, not a person
    "Sain puhelun pankin korttivalvonnasta pysäytetystä maksusta.",
    "The bank's fraud monitoring stopped a payment. What now?",
    # an ex-employee is a business access problem, not a safety situation
    "Entinen työntekijä pääsee yhä yrityksen someen ja sähköpostiin. Onko tämä vakavaa?",
    # generic service monitoring
    "Seuraan verkkopankkini tapahtumia joka viikko.",
]


def _masked(case):
    """A case where every ungranted consent-gated signal is the placeholder,
    exactly as dsakit.simulator.visible_case() hands it to a multi-turn bot."""
    out = copy.deepcopy(case)
    for path in (out.get("consent") or {}).get("requires_consent") or []:
        parts = path.split(".")
        cur = out["signals"]
        for key in parts[:-1]:
            cur = cur.get(key, {})
        if parts[-1] in cur:
            cur[parts[-1]] = GATED
    return out


def _dev_cases():
    if not os.path.exists(DEV):
        return []
    with open(DEV, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


class SafetyCueTest(unittest.TestCase):
    def test_person_surveillance_is_detected(self):
        for text in SAFETY_POSITIVES:
            with self.subTest(text=text):
                self.assertTrue(dna.safety_cue(text))

    def test_parcels_and_generic_monitoring_are_not(self):
        for text in SAFETY_NEGATIVES:
            with self.subTest(text=text):
                self.assertFalse(dna.safety_cue(text))

    def test_dev_positives_and_false_positives(self):
        """All BR-MONITORING-APP cases, no parcel-scam answers, on real data."""
        cases = _dev_cases()
        if not cases:
            self.skipTest("dev cases not available")
        positives = {
            c["case_id"] for c in cases
            if set((c.get("ground_truth") or {}).get("required_steps") or [])
            & {"plan_before_removing", "seek_support_org"}
        }
        hits = {c["case_id"] for c in cases if dna.safety_cue(c.get("opening_message") or "")}
        self.assertTrue(positives, "dev data carries no monitoring cases")
        self.assertEqual(positives - hits, set(), "missed monitoring cases")
        self.assertEqual(hits - positives, set(), "parcel/bank cases flagged as unsafe")


class ConsentPlaceholderTest(unittest.TestCase):
    def test_helpers_treat_placeholder_as_absent(self):
        case = {
            "case_id": "T-1",
            "signals": {
                "operator_account": {"recent_logins": GATED},
                "device": {"security_findings": GATED, "recent_app_installs": []},
                "credential_exposure": GATED,
                "link_check": None,
            },
        }
        self.assertEqual(dna._sig(case, "operator_account", "recent_logins"), {})
        self.assertEqual(dna._sig(case, "device", "security_findings"), {})
        self.assertEqual(dna._sig(case, "link_check"), {})
        self.assertEqual(dna._sig_list(case, "operator_account", "recent_logins"), [])
        self.assertEqual(dna._sig_dicts(case, "operator_account", "recent_logins"), [])
        self.assertEqual(dna._sig_list(case, "device", "recent_app_installs"), [])
        self.assertEqual(dna._sig_list(case, "nope"), [])

    def test_masked_signal_is_absent_for_benign_evidence(self):
        case = {
            "case_id": "T-2",
            "journey": "smb_incident",
            "language": "en",
            "opening_message": "I got an order confirmation for mobile broadband. Is it real?",
            "signals": {
                "artifact": {"type": "email", "body": "Order confirmation"},
                "subscription": {"recent_events": [{
                    "type": "new_subscription_order",
                    "delivery": "office_address",
                    "ordered_by": "admin_account",
                    "login_device": "known",
                }]},
            },
            "consent": {"requires_consent": ["subscription.recent_events"], "pre_granted": []},
        }
        self.assertTrue(dna._benign_evidence(case))
        self.assertFalse(dna._benign_evidence(_masked(case)))

    def test_normalise_does_not_raise_on_masked_breach_case(self):
        cases = [c for c in _dev_cases() if c.get("journey") == "breach_notice"]
        if not cases:
            self.skipTest("dev cases not available")
        for case in cases:
            case = _masked(case)
            raw = dna.fallback(case)
            with self.subTest(case_id=case["case_id"]):
                answer = dna.normalise(case, raw)
                self.assertEqual(answer["case_id"], case["case_id"])
                self.assertIn(answer["primary_action"], dna.ACTIONS["actions"])
                # A junk action sends normalise through rules().decide() too.
                broken = dict(raw, primary_action="not_an_action")
                self.assertIn(dna.normalise(case, broken)["primary_action"], dna.ACTIONS["actions"])

    def test_masked_login_list_does_not_trigger_foreign_login_upgrade(self):
        case = {
            "case_id": "T-3",
            "journey": "breach_notice",
            "language": "en",
            "opening_message": "I got a notice about a login.",
            "signals": {
                "artifact": {"type": "email", "body": "A sign-in was detected."},
                "operator_account": {"recent_logins": [{
                    "days_ago": 0, "country": "ES", "device_known": False,
                    "result": "success",
                }]},
            },
            "consent": {"requires_consent": ["operator_account.recent_logins"],
                        "pre_granted": []},
        }
        self.assertEqual(dna._upgrade(case, "verify_via_official_channel"),
                         "change_password_and_enable_mfa")
        self.assertNotEqual(dna._upgrade(_masked(case), "verify_via_official_channel"),
                            "change_password_and_enable_mfa")


class RetrievalTest(unittest.TestCase):
    def test_retrieval_is_deterministic_and_only_valid_ids(self):
        cases = _dev_cases()
        if not cases:
            self.skipTest("dev cases not available")
        # one case per journey and language, so the check is not one family
        seen = set()
        sample = []
        for case in cases:
            key = (case.get("journey"), case.get("language"))
            if key not in seen:
                seen.add(key)
                sample.append(case)
        for case in sample:
            with self.subTest(case_id=case["case_id"]):
                first = [g["id"] for g in dna.retrieve(case)]
                self.assertEqual(first, [g["id"] for g in dna.retrieve(case)])
                self.assertLessEqual(len(first), dna.RETRIEVAL_LIMIT)
                self.assertEqual(len(first), len(set(first)), "duplicate passage")
                self.assertTrue(set(first) <= dna.GUIDANCE_IDS, first)
                menu = dna._guidance_menu(case)
                self.assertEqual(len(menu.splitlines()), len(first))
                self.assertTrue(all(line.startswith("- guidance_") for line in menu.splitlines()))


class UsageCaptureTest(unittest.TestCase):
    def test_usage_survives_chat_and_cache(self):
        messages = [{"role": "user", "content": "hello"}]
        reply = {"choices": [{"message": {"content": "hi"}}],
                 "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}}
        original_post = dna.llm._post
        original_root = dna.cache.ROOT
        tmp = tempfile.mkdtemp()
        dna.llm._post = lambda payload, timeout: reply
        dna.cache.ROOT = tmp
        try:
            self.assertEqual(dna.llm.chat(messages), "hi")
            text, usage = dna.llm.chat_full(messages, max_tokens=100)
            self.assertEqual((text, usage["prompt_tokens"], usage["completion_tokens"]),
                             ("hi", 11, 7))

            _, fresh = dna.call_model(messages)
            self.assertEqual(fresh["usage"]["prompt_tokens"], 11)
            self.assertFalse(fresh["cached"])
            _, cached = dna.call_model(messages)
            self.assertTrue(cached["cached"])
            self.assertEqual(cached["usage"]["completion_tokens"], 7)
        finally:
            dna.llm._post = original_post
            dna.cache.ROOT = original_root
            shutil.rmtree(tmp, ignore_errors=True)


class ThinkingTest(unittest.TestCase):
    def test_thinking_reaches_body_and_cache_key(self):
        messages = [{"role": "user", "content": "hello"}]
        seen = []

        def fake_post(payload, timeout):
            seen.append(payload)
            return {"choices": [{"message": {"content": "{}"}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}

        original_post = dna.llm._post
        original_root = dna.cache.ROOT
        tmp = tempfile.mkdtemp()
        dna.llm._post = fake_post
        dna.cache.ROOT = tmp
        try:
            _, off = dna.call_model(messages, thinking="off")
            _, off_again = dna.call_model(messages, thinking="off")
            _, on = dna.call_model(messages, thinking="on")
            self.assertEqual(seen[0]["chat_template_kwargs"], {"thinking": False})
            self.assertNotIn("chat_template_kwargs", seen[1], "on must keep the model default")
            self.assertEqual((off["thinking"], on["thinking"]), ("off", "on"))
            self.assertTrue(off_again["cached"])
            self.assertFalse(on["cached"])
            self.assertNotEqual(dna.cache.key(messages, dna.llm.MODEL, 0.1, "off"),
                                dna.cache.key(messages, dna.llm.MODEL, 0.1, "on"))

            # A reply cut off by the output cap is retried once without
            # thinking, and the truncated reply is never cached.
            capped_messages = [{"role": "user", "content": "cap"}]
            seen.clear()

            def capped_post(payload, timeout):
                seen.append(payload)
                tokens = 8000 if "chat_template_kwargs" not in payload else 5
                content = "{}" if tokens == 8000 else '{"ok": true}'
                return {"choices": [{"message": {"content": content}}],
                        "usage": {"prompt_tokens": 1, "completion_tokens": tokens,
                                  "total_tokens": tokens + 1}}

            dna.llm._post = capped_post
            text, meta = dna.call_model(capped_messages, thinking="on", max_tokens=8000)
            self.assertEqual(len(seen), 2)
            self.assertNotIn("chat_template_kwargs", seen[0])
            self.assertEqual(seen[1]["chat_template_kwargs"], {"thinking": False})
            self.assertEqual((text, meta["thinking"]), ('{"ok": true}', "off"))
            self.assertIn("output cap", meta["thinking_retry"])
            self.assertEqual(meta["first_usage"]["completion_tokens"], 8000)
            self.assertIsNone(dna.cache.get(
                dna.cache.key(capped_messages, dna.llm.MODEL, 0.1, "on")))
        finally:
            dna.llm._post = original_post
            dna.cache.ROOT = original_root
            shutil.rmtree(tmp, ignore_errors=True)


class ParseRepairTest(unittest.TestCase):
    def test_repairs_trailing_comma_and_truncated_string(self):
        text = '{"risk_level": "low", "steps": ["one",], "advice_text": "Check the app'
        obj = dna._parse(text)
        self.assertIsInstance(obj, dict)
        self.assertEqual(obj["steps"], ["one"])
        self.assertEqual(obj["advice_text"], "Check the app")
        self.assertIsNone(dna._parse("I could not decide what to do."))

        # The id never enters the prompt: it only made every prompt unique.
        case = {"case_id": "T-PROMPT-1", "language": "en", "opening_message": "Hello.",
                "signals": {}, "consent": {"requires_consent": [], "pre_granted": []}}
        self.assertNotIn(case["case_id"], json.dumps(dna.prompt(case), ensure_ascii=False))


class BenignOverrideTest(unittest.TestCase):
    def test_single_cue_does_not_lower_a_cautious_answer(self):
        case = {
            "case_id": "T-9", "journey": "clicked_link", "language": "fi",
            "opening_message": "Tilasin itse tuotteen ja avasin linkin. Onko tämä turvallista?",
            "signals": {"artifact": {"type": "email", "body": "Tilausvahvistus."},
                        "link_check": {"verdict": "clean"}},
        }
        raw = {"primary_action": "contact_operator_support", "risk_level": "medium",
               "urgency": "today", "steps": [],
               "advice_text": "Ota yhteyttä asiakaspalveluumme ja tarkista tilaus rauhassa."}
        self.assertEqual(dna._benign_cues(case), ["clean_link"])
        out = dna.normalise(case, raw)
        self.assertEqual(out["primary_action"], "contact_operator_support")
        self.assertEqual(out["risk_level"], "medium")

        # A model that proposes verify has not agreed the case is harmless,
        # so one cue must not turn it into no_action.
        call = {
            "case_id": "T-13", "journey": "suspicious_call", "language": "en",
            "opening_message": "My bank called about a payment. The number was the one on my card.",
            "signals": {"artifact": {"type": "call",
                                     "body": "They didn't ask for any details or information."}},
        }
        verify = {"primary_action": "verify_via_official_channel", "risk_level": "low",
                  "urgency": "routine", "steps": [],
                  "advice_text": "Check the payment in your bank's own app."}
        self.assertEqual(dna._benign_cues(call), ["call_no_ask"])
        out = dna.normalise(call, verify)
        self.assertEqual(out["primary_action"], "verify_via_official_channel")
        self.assertEqual(out["risk_level"], "low")


class EscalationEvidenceTest(unittest.TestCase):
    def test_handoff_forced_on_compromise_but_not_without_it(self):
        case = {
            "case_id": "T-10", "journey": "breach_notice", "language": "en",
            "opening_message": "I got a notice about a login.",
            "signals": {"artifact": {"type": "email", "body": "A sign-in was detected."},
                        "operator_account": {"recent_logins": [{
                            "days_ago": 0, "country": "ES", "device_known": False,
                            "result": "success"}]}},
        }
        raw = {"primary_action": "change_password_and_enable_mfa", "risk_level": "high",
               "urgency": "today", "steps": [], "escalation_required": False,
               "advice_text": "Change the password now and turn on the extra sign-in step."}
        out = dna.normalise(case, raw)
        self.assertTrue(out["escalation_required"])
        self.assertIn(out["escalation_target"], dna.ESCALATION_TARGETS)
        no_evidence = dict(case, signals={"artifact": {"type": "email", "body": "A notice."}})
        out = dna.normalise(no_evidence, raw)
        self.assertFalse(out["escalation_required"])
        self.assertIsNone(out["escalation_target"])

        # A pending request is not a compromise: a supplier asking to change
        # a bank account does not force a handoff on its own. When the model
        # does ask for one, it still carries a valid target.
        request = {
            "case_id": "T-17", "journey": "smb_incident", "language": "en",
            "opening_message": "Our supplier emailed a new bank account number for an unpaid invoice.",
            "signals": {"artifact": {"type": "email",
                                     "body": "Please pay the invoice to our new account."}},
        }
        asked = dict(raw, primary_action="verify_via_official_channel")
        out = dna.normalise(request, dict(asked, escalation_required=True))
        self.assertTrue(out["escalation_required"])
        self.assertIn(out["escalation_target"], dna.ESCALATION_TARGETS)
        out = dna.normalise(request, asked)
        self.assertFalse(out["escalation_required"])
        self.assertIsNone(out["escalation_target"])


class UncertainAnswerTest(unittest.TestCase):
    def test_uncertain_answer_takes_riskier_branch_and_never_benign(self):
        case = {
            "case_id": "T-11", "journey": "suspicious_message", "language": "fi",
            "opening_message": "Sain viestin paketista.",
            "user_replies": "En ole varma, klikkasinko linkkiin vai en.",
            "signals": {"artifact": {"type": "email",
                                     "body": "Vain sähköposti ja nimet, ei salasanoja eikä maksua."}},
        }
        raw = {"primary_action": "no_action_needed", "risk_level": "none",
               "urgency": "none", "steps": [],
               "advice_text": "Viesti näyttää tavalliselta ilmoitukselta."}
        self.assertTrue(dna._benign_cues(case))
        out = dna.normalise(case, raw)
        self.assertNotEqual(out["primary_action"], "no_action_needed")
        self.assertIn(out["risk_level"], ("low", "medium", "high"))
        self.assertIn(dna.UNCERTAIN_LINE["fi"], out["advice_text"])

        # The same words in the opening message are not an answer to our
        # question, so they never trigger the canned uncertainty line.
        opening = dict(case, user_replies="")
        opening["opening_message"] = "Sain viestin. En ole varma, klikkasinko linkkiin vai en."
        out = dna.normalise(opening, raw)
        self.assertNotIn(dna.UNCERTAIN_LINE["fi"], out["advice_text"])


class UpgradeAdviceTest(unittest.TestCase):
    def test_raised_action_states_its_core_step(self):
        # Credential phishing on a business mailbox raises the action to
        # change credentials. The advice must say so, not keep talking only
        # about deleting the message.
        case = {
            "case_id": "T-19", "journey": "smb_incident", "language": "fi",
            "opening_message": "Työntekijä antoi työsähköpostinsa tunnukset oudolle sivulle.",
            "signals": {"artifact": {"type": "email", "body": "Vahvista tunnuksesi."},
                        "link_check": {"verdict": "malicious",
                                       "categories": ["credential_phishing"]}},
        }
        raw = {"primary_action": "do_not_interact_and_delete", "risk_level": "medium",
               "urgency": "today", "steps": [],
               "advice_text": "Älä vastaa viestiin äläkä avaa siinä olevaa linkkiä ollenkaan."}
        out = dna.normalise(case, raw)
        self.assertEqual(out["primary_action"], "change_password_and_enable_mfa")
        found = textcheck.find_steps(out["advice_text"] + "\n" + "\n".join(out["steps"]))
        self.assertTrue({"change_password", "enable_mfa"} & found)


class NoActionFloorTest(unittest.TestCase):
    def test_no_action_without_benign_evidence_is_raised(self):
        case = {
            "case_id": "T-12", "journey": "suspicious_message", "language": "fi",
            "opening_message": "Sain viestin uudesta ominaisuudesta.",
            "signals": {},
        }
        raw = {"primary_action": "no_action_needed", "risk_level": "none",
               "urgency": "none", "steps": [],
               "advice_text": "Viesti näyttää tavalliselta ilmoitukselta."}
        self.assertEqual(dna._benign_cues(case), [])
        out = dna.normalise(case, raw)
        self.assertEqual(out["primary_action"], "verify_via_official_channel")
        self.assertIn(out["risk_level"], ("low", "medium", "high"))
        self.assertIn(dna.FLOOR_LINE["fi"], out["advice_text"])

        # With an artifact the floor does not apply: the model has evidence,
        # so its judgement and the existing rules stand.
        notice = {
            "case_id": "T-14", "journey": "suspicious_message", "language": "fi",
            "opening_message": "Sain pankilta kirjeen tilini tapahtumista.",
            "signals": {"artifact": {"type": "letter",
                                     "body": "Tiliotteesi on saatavilla verkkopankissa."}},
        }
        self.assertEqual(dna._benign_cues(notice), [])
        out = dna.normalise(notice, raw)
        self.assertEqual(out["primary_action"], "no_action_needed")

    def test_rules_fallback_never_answers_nothing_to_do(self):
        # A free-text demo start carries the profile's signals, so the
        # no-evidence floor cannot fire on its own. A rules fallback has no
        # model judgement either, so it must still never say "nothing to do".
        case = {
            "case_id": "DEMO-CON-abc123", "journey": "suspicious_message",
            "language": "en",
            "opening_message": "I think I've done something really stupid and I "
                               "don't know if it's serious. Can you help?",
            "signals": {
                "artifact": None, "link_check": None, "call_warning": None,
                "subscription": {"products": [{"type": "mobile"}]},
                "device": {"summary": {"platform": "android"}},
            },
        }
        self.assertTrue(dna._has_case_evidence(case))
        out = dna.fallback(case)
        self.assertEqual(out["primary_action"], "verify_via_official_channel")
        self.assertEqual(out["urgency"], "routine")
        self.assertIn(dna.FLOOR_LINE["en"], out["advice_text"])
        self.assertNotIn("looks genuine", out["advice_text"].lower())


class RefusedConsentTest(unittest.TestCase):
    def test_refused_signal_keeps_visible_risk_floor(self):
        case = {
            "case_id": "T-15", "journey": "suspicious_message", "language": "en",
            "opening_message": "Has anyone logged into my subscription from somewhere else?",
            "signals": {"device": {"summary": {"platform": "android"}}},
            "refused_signals": ["operator_account.recent_logins"],
        }
        raw = {"primary_action": "verify_via_official_channel", "risk_level": "low",
               "urgency": "routine", "steps": [],
               "advice_text": "There is no notification, so nothing happened."}
        out = dna.normalise(case, raw)
        self.assertGreaterEqual(dna.RISK_LEVELS.index(out["risk_level"]),
                                dna.RISK_LEVELS.index("medium"))
        self.assertEqual(out["primary_action"], "verify_via_official_channel")


class ConsentBoundaryTest(unittest.TestCase):
    def test_gated_values_need_consent_on_every_public_path(self):
        case = _gated_case()
        before = copy.deepcopy(case)

        # Prompt: no value, no metadata, only the protocol placeholder.
        blob = json.dumps(dna.prompt(case), ensure_ascii=False)
        for value in (LOGIN_SENTINEL, EXPOSURE_SENTINEL, "GROUND-TRUTH-SENTINEL",
                      "SIM-SENTINEL", "family-sentinel", "title-sentinel",
                      "tag-sentinel", "holdout-sentinel"):
            self.assertNotIn(value, blob)
        self.assertIn(dna.GATED_PLACEHOLDER, blob)

        # consent.pre_granted and an explicit grant each open only their path;
        # a refusal beats a grant.
        pre = copy.deepcopy(case)
        pre["consent"]["pre_granted"] = [LOGINS]
        pre_blob = json.dumps(dna.prompt(pre), ensure_ascii=False)
        self.assertIn(LOGIN_SENTINEL, pre_blob)
        self.assertNotIn(EXPOSURE_SENTINEL, pre_blob)
        grant_blob = json.dumps(dna.prompt(case, granted=[EXPOSURE]), ensure_ascii=False)
        self.assertIn(EXPOSURE_SENTINEL, grant_blob)
        self.assertNotIn(LOGIN_SENTINEL, grant_blob)
        refused = copy.deepcopy(case)
        refused["refused_signals"] = [LOGINS]
        refused_blob = json.dumps(dna.prompt(refused, granted=[LOGINS]), ensure_ascii=False)
        self.assertNotIn(LOGIN_SENTINEL, refused_blob)

        # Model messages through run(): the same gate, no API call.
        seen = []
        original_call = dna.call_model

        def fake_call(messages, *args, **kwargs):
            seen.append(messages)
            return json.dumps(dna.fallback(case), ensure_ascii=False), {
                "cached": False, "truncated": False, "usage": {}, "model": "fake"}

        dna.call_model = fake_call
        try:
            dna.run(case)
            dna.run(case, granted=[EXPOSURE])
        finally:
            dna.call_model = original_call
        # run() must send exactly the prompt a caller would build directly,
        # including when an explicit grant is passed.
        self.assertEqual(seen[0], dna.prompt(case))
        self.assertEqual(seen[1], dna.prompt(case, granted=[EXPOSURE]))
        no_grant, granted = (json.dumps(messages, ensure_ascii=False) for messages in seen)
        self.assertNotIn(LOGIN_SENTINEL, no_grant)
        self.assertNotIn(EXPOSURE_SENTINEL, no_grant)
        self.assertIn(EXPOSURE_SENTINEL, granted)
        self.assertNotIn(LOGIN_SENTINEL, granted)

        # Rules see the same withheld case. consent_requested_for in a reply
        # is a request, never permission.
        capture = CaptureRules(dna.rules())
        original_rules = dna._rules
        dna._rules = capture
        try:
            dna.fallback(case)
            dna.normalise(case, SAFE_RAW)
        finally:
            dna._rules = original_rules
        for seen_case in capture.seen:
            seen_blob = json.dumps(seen_case, ensure_ascii=False)
            self.assertNotIn(LOGIN_SENTINEL, seen_blob)
            self.assertNotIn(EXPOSURE_SENTINEL, seen_blob)
        capture.seen.clear()
        dna._rules = capture
        try:
            dna.fallback(case, granted=[LOGINS])
        finally:
            dna._rules = original_rules
        self.assertTrue(any(LOGIN_SENTINEL in json.dumps(c, ensure_ascii=False)
                            for c in capture.seen))

        self.assertEqual(case, before, "authorisation must not mutate the caller's case")


def _login_notice_case(language, opening, body, platform=None):
    """A case with a gated login list and a user-visible notification."""
    signals = {
        "artifact": {"type": "push_notification", "body": body},
        "operator_account": {"recent_logins": [{
            "days_ago": 0, "country": "SENTINELCOUNTRY", "device_known": False,
            "result": "pending_mfa", "browser": LOGIN_SENTINEL}]},
    }
    if platform:
        signals["device"] = {"summary": {"platform": platform}}
    return {
        "case_id": "T-CONSENT-3", "journey": "suspicious_message",
        "language": language, "opening_message": opening, "signals": signals,
        "consent": {"requires_consent": [LOGINS], "pre_granted": []},
    }


def _login_raw(advice, steps=None, **fields):
    raw = {"primary_action": "change_password_and_enable_mfa", "risk_level": "high",
           "urgency": "today", "advice_text": advice, "steps": steps or [],
           "signals_used": ["artifact"], "consent_requested_for": [],
           "confidence": 0.7}
    raw.update(fields)
    return raw


NETWORK = "subscription.network_status"
NETWORK_SENTINEL = "SENTINEL-NETWORK-4a7"


def _network_case(language):
    """A case whose network status is gated and never granted."""
    opening = {
        "fi": "Puhelimestani katosi verkko ja sain viestin liittymän muutoksesta.",
        "en": "My phone lost service and I got a message about a subscription change.",
        "sv": "Min telefon tappade nätet och jag fick ett sms om en abonnemangsändring.",
    }[language]
    return {
        "case_id": "T-NETWORK-1", "journey": "breach_notice",
        "audience": "consumer", "locale": {"fi": "fi-FI", "en": "en-GB",
                                           "sv": "sv-SE"}[language],
        "language": language, "entry_point": "operator_app_chat",
        "user_identified": True, "opening_message": opening,
        "signals": {
            "artifact": {"type": "sms", "body": "Your subscription was changed."},
            "subscription": {"recent_events": [],
                             "network_status": NETWORK_SENTINEL},
        },
        "consent": {"requires_consent": [NETWORK], "pre_granted": []},
    }


def _network_raw(advice, steps=None):
    return {"primary_action": "contact_operator_support", "risk_level": "high",
            "urgency": "today", "advice_text": advice, "steps": steps or [],
            "signals_used": ["artifact"], "consent_requested_for": [],
            "confidence": 0.7}


class ConsentOutputTest(unittest.TestCase):
    def test_normalise_filters_unallowed_use_and_rejects_asserted_fact(self):
        case = _gated_case()
        out = dna.normalise(case, SAFE_RAW)
        self.assertNotIn(LOGINS, out["signals_used"])
        self.assertNotIn(EXPOSURE, out["signals_used"])
        self.assertIn("artifact", out["signals_used"])

        # Listing a gated path as requested does not make it usable.
        requested = dict(SAFE_RAW, signals_used=[], consent_requested_for=[LOGINS, EXPOSURE])
        out = dna.normalise(case, requested)
        self.assertEqual(out["signals_used"], ["artifact"])
        self.assertIn(LOGINS, out["consent_requested_for"])

        # An advice line that states a gated fact is rejected to the rules.
        trace = []
        leaky = dict(SAFE_RAW, signals_used=["artifact"],
                     advice_text="Your login history shows Chrome was used for the sign-in.")
        out = dna.normalise(case, leaky, trace)
        rules = [r["rule"] for r in trace]
        self.assertIn("consent_unsafe_advice", rules)
        self.assertIn("fallback", rules)
        self.assertEqual(dna.fallback_reason(trace),
                         "advice states a consent-gated fact")
        self.assertNotIn("Chrome", out["advice_text"])

        # Steps are end-user advice too: a gated fact only in steps is rejected.
        trace = []
        step_leak = dict(SAFE_RAW, steps=[
            "Your login history shows Chrome was used for the sign-in."])
        out = dna.normalise(case, step_leak, trace)
        self.assertIn("consent_unsafe_advice", [r["rule"] for r in trace])
        self.assertFalse(any("Chrome" in step for step in out["steps"]))

        # Recommending that the user review their own sign-ins is not a
        # statement of a gated fact.
        trace = []
        review = dict(SAFE_RAW, signals_used=["artifact"],
                      advice_text="Change your password, then review your login history in the app.")
        dna.normalise(case, review, trace)
        self.assertNotIn("consent_unsafe_advice", [r["rule"] for r in trace])

        # run() reports the same rejection honestly: the marker sets the
        # fallback flag and reason, and the main-call meta is kept.
        calls = []
        original_call = dna.call_model

        def fake_call(messages, *args, **kwargs):
            calls.append(messages)
            return json.dumps(leaky), {"model": "fake", "temperature": 0,
                                       "prompt_hash": "hash-main", "truncated": False}

        dna.call_model = fake_call
        try:
            answer, trace = dna.run(case)
        finally:
            dna.call_model = original_call
        self.assertEqual(len(calls), 1)
        self.assertEqual(answer, dna.fallback(case, "advice states a consent-gated fact"))
        self.assertTrue(trace["fallback"])
        self.assertEqual(trace["error"], "advice states a consent-gated fact")
        self.assertEqual(trace["meta"]["prompt_hash"], "hash-main")

        # Missing parents and unknown paths are not a crash.
        broken = {
            "case_id": "T-CONSENT-2", "journey": "breach_notice", "language": "en",
            "opening_message": "A notice about a sign-in.",
            "signals": {"operator_account": None},
            "consent": {"requires_consent": [LOGINS, "no.such.path"], "pre_granted": []},
        }
        for masked in (False, True):
            self.assertEqual(dna.authorised(broken, masked=masked)["signals"],
                             {"operator_account": None})
        self.assertEqual(dna.normalise(broken, SAFE_RAW)["case_id"], "T-CONSENT-2")

    def test_source_attributed_login_details_are_not_record_claims(self):
        # The same browser/OS word can come from the notification or from the
        # user. Naming that source is not a claim about our login records.
        attributed = [
            ("fi",
             "Olen kirjautumassa uudella läppärillä. Hyväksyntäpyynnössä näkyy Windows ja Chrome.",
             "Hyväksytkö kirjautumisen? Laite: Windows, Chrome.",
             "Kirjautumispyyntö näyttää kertomasi tiedot: Windows ja Chrome uudella "
             "läppärilläsi. Hyväksy vain itse aloittamasi pyyntö."),
            ("en",
             "I am signing in on my new laptop. The approval request shows macOS and Safari.",
             "Approve the sign-in? Device: macOS, Safari.",
             "The authenticator notification for this login shows macOS and Safari, "
             "exactly as you described. Approve only a request you started yourself."),
            ("sv",
             "Jag loggar in på en ny laptop. I godkännandet syns Android och Chrome.",
             "Godkänn inloggningen? Enhet: Android, Chrome.",
             "Inloggningen du startade stämmer med det du berättade: Android och Chrome "
             "på din nya laptop. Godkänn bara inloggningar du själv startade."),
        ]
        for language, opening, body, advice in attributed:
            case = _login_notice_case(language, opening, body)
            before = copy.deepcopy(case)
            trace = []
            out = dna.normalise(case, _login_raw(advice), trace)
            self.assertIsNone(dna.fallback_reason(trace), (language, out["advice_text"]))
            self.assertEqual(out["advice_text"], advice)
            self.assertEqual(case, before, "normalise must not mutate the case")
            self.assertNotIn(LOGIN_SENTINEL, json.dumps(out, ensure_ascii=False))

        # The user's own report is the source, with no matching notification.
        reports = [
            ("fi", "Olen kirjautumassa uudella läppärillä Windowsilla ja Chromella.",
             "Kerroit aloittaneesi kirjautumisen itse: Windows ja Chrome uudella "
             "läppärilläsi. Hyväksy vain itse aloittamasi pyyntö."),
            ("en", "I am signing in on my new laptop with macOS and Safari.",
             "You said you started this login yourself from macOS and Safari. "
             "Approve only the request you began."),
            ("sv", "Jag loggar in på en ny laptop med Android och Chrome.",
             "Du berättade att du startade inloggningen själv från Android och Chrome. "
             "Godkänn bara inloggningar du själv startade."),
        ]
        for language, opening, advice in reports:
            case = _login_notice_case(language, opening, "Approve the sign-in?")
            before = copy.deepcopy(case)
            trace = []
            out = dna.normalise(case, _login_raw(advice), trace)
            self.assertIsNone(dna.fallback_reason(trace), (language, out["advice_text"]))
            self.assertEqual(out["advice_text"], advice)
            self.assertEqual(case, before, "normalise must not mutate the case")
            self.assertNotIn(LOGIN_SENTINEL, json.dumps(out, ensure_ascii=False))

        # A matching word in device.summary is not a visible source for a login
        # detail: the notification body and the user's words are.
        case = _login_notice_case("en", "I am signing in on my new laptop.",
                                  "Approve the sign-in?", platform="windows")
        trace = []
        out = dna.normalise(case, _login_raw(
            "The notification says your login came from Windows. Approve only if "
            "you started it."), trace)
        self.assertEqual(dna.fallback_reason(trace),
                         "advice states a consent-gated fact")
        self.assertNotIn("Windows", out["advice_text"])

    def test_login_record_assertions_still_require_consent(self):
        fact = "Your login history shows Chrome was used for the sign-in."
        case = _login_notice_case("en", "I am signing in on a new device.",
                                  "Approve the sign-in? Device: Firefox.")

        def rejects(advice, steps=None, source=None, grant=(), requested=None):
            trace = []
            out = dna.normalise(source or case, _login_raw(
                advice, steps, consent_requested_for=requested or []),
                trace, granted=grant)
            self.assertEqual(dna.fallback_reason(trace),
                             "advice states a consent-gated fact", advice)
            self.assertNotEqual(out["advice_text"], advice)
            return out

        # The user's notification is real, but a protected-record source in
        # the same sentence still wins.
        rejects(fact)
        rejects("The notification says Firefox, but your login history shows "
                "Chrome was used.")
        # A legitimate attributed sentence does not exempt another sentence,
        # including an explicit record claim that names no browser or OS.
        rejects("The notification says Firefox was used for the login you started. "
                + fact)
        rejects("The notification says Firefox for this login. We checked your "
                "recent logins and found no unusual activity.")
        # An explicit inspection of the login record is rejected without any
        # browser or OS word, in each language.
        for language, explicit in (
                ("en", "We checked your recent logins and found no unusual "
                       "activity."),
                ("en", "Your recent logins show no unusual activity at all."),
                ("fi", "Tarkistimme kirjautumishistoriasi, eikä siinä ollut mitään "
                       "tavallisuudesta poikkeavaa."),
                ("sv", "Vi kontrollerade dina senaste inloggningar och hittade "
                       "inget ovanligt.")):
            source = _login_notice_case(language, "I am signing in on a new device.",
                                        "Approve the sign-in?")
            rejects(explicit, source=source)
        # Non-login product records are not a gated login fact.
        product = "Our records show your mobile subscription includes a data plan."
        trace = []
        out = dna.normalise(case, _login_raw(product), trace)
        self.assertNotIn("consent_unsafe_advice", [r["rule"] for r in trace])
        self.assertEqual(out["advice_text"], product)
        # Telling the user to review their own sign-ins is not a record claim.
        for language, review in (
                ("fi", "Tarkista viimeisimmät kirjautumisesi ja kirjaudu ulos "
                       "tuntemattomista laitteista."),
                ("sv", "Kontrollera dina senaste inloggningar och logga ut från "
                       "okända enheter.")):
            source = _login_notice_case(language, "I am signing in on a new device.",
                                        "Approve the sign-in?")
            trace = []
            out = dna.normalise(source, _login_raw(review), trace)
            self.assertNotIn("consent_unsafe_advice", [r["rule"] for r in trace])
            self.assertEqual(out["advice_text"], review)
        # Inspecting the user's notification is not inspecting the record, even
        # when the sentence names a browser.
        notice = "I checked the notification about this login and it shows Firefox."
        trace = []
        out = dna.normalise(case, _login_raw(notice), trace)
        self.assertIsNone(dna.fallback_reason(trace))
        self.assertEqual(out["advice_text"], notice)
        # Steps are end-user advice too.
        rejects("Approve only the sign-in you started.", steps=[fact])
        # Requesting the signal, or having refused it, is not consent.
        rejects(fact, requested=[LOGINS])
        refused = copy.deepcopy(case)
        refused["refused_signals"] = [LOGINS]
        rejects(fact, source=refused)
        # The source must really carry the detail the answer names.
        rejects("The login request shows Chrome was used for the sign-in.")
        rejects("We checked your logins and the last one shows Chrome.")

        # A pre-grant or an explicit grant opens the record; then the same
        # statement is no longer a gated reference.
        pre = copy.deepcopy(case)
        pre["consent"]["pre_granted"] = [LOGINS]
        for source, grant in ((pre, ()), (case, (LOGINS,))):
            trace = []
            out = dna.normalise(source, _login_raw(fact), trace, granted=grant)
            self.assertIsNone(dna.fallback_reason(trace))
            self.assertEqual(out["advice_text"], fact)

    def test_network_monitor_instructions_are_not_evidence(self):
        # A request to check or watch the connection is not a report of a
        # measured state. Conditional forms are the same class, in each
        # language; question forms are checked on the helper because
        # _clean_advice removes a dialogue question before the guard.
        monitors = [
            ("fi", "Soita meille ja seuraa, toimiiko verkkoyhteytesi ja "
                   "tekstiviestisi normaalisti."),
            ("fi", "Jos verkkoyhteytesi toimii normaalisti, voit jatkaa rauhassa "
                   "ja odottaa yhteyden palautumista."),
            ("en", "Contact us and check whether your connection works normally "
                   "after the restart."),
            ("sv", "Kontakta oss och kontrollera om anslutningen fungerar normalt "
                   "efter omstarten."),
            ("fi", "Varmista, että verkkoyhteytesi toimii normaalisti ja "
                   "tekstiviestisi tulevat perille."),
        ]
        for language, advice in monitors:
            case = dna.visible(dna.authorised(_network_case(language), masked=True))
            trace = []
            out = dna.normalise(case, _network_raw(advice), trace)
            self.assertIsNone(dna.fallback_reason(trace), (language, advice))
            self.assertEqual(out["advice_text"], advice)
            self.assertNotIn(NETWORK_SENTINEL,
                             json.dumps(out, ensure_ascii=False))

        for question in ("Is your connection working normally?",
                         "Does your connection work normally?",
                         "Fungerar anslutningen normalt?",
                         "Onko verkkoyhteytesi kunnossa?"):
            self.assertFalse(dna._network_fact_asserted(question), question)
        # A bare question mark is not an exemption: unknown forms are claims.
        self.assertTrue(dna._network_fact_asserted(
            "Your connection works normally?"))

        # Steps are end-user advice too, so the same instruction must survive.
        step = "Seuraa, toimiiko verkkoyhteytesi normaalisti."
        case = dna.visible(dna.authorised(_network_case("fi"), masked=True))
        trace = []
        out = dna.normalise(case, _network_raw("Soita meille ja pidä viesti "
                                               "tallessa.", [step]), trace)
        self.assertIsNone(dna.fallback_reason(trace))
        self.assertIn(step, out["steps"])

    def test_network_assertions_still_require_consent(self):
        def rejects(language, advice, steps=None, grant=()):
            case = dna.visible(dna.authorised(_network_case(language), masked=True))
            trace = []
            out = dna.normalise(case, _network_raw(advice, steps), trace,
                                granted=grant)
            self.assertEqual(dna.fallback_reason(trace),
                             "advice states a consent-gated fact", (language, advice))
            self.assertNotIn(NETWORK_SENTINEL,
                             json.dumps(out, ensure_ascii=False))

        # Direct assertions, in each language, with consent denied.
        rejects("en", "Your connection works normally and the subscription "
                      "change is complete.")
        rejects("fi", "Verkkoyhteytesi on kunnossa ja liittymän muutos on valmis.")
        rejects("sv", "Anslutningen fungerar normalt och abonnemangsändringen "
                      "är helt klar.")

        # A check instruction in the same sentence does not cover a record
        # claim, and neither does a second assertive clause.
        rejects("en", "Check your connection; our records show your connection "
                      "is normal.")
        rejects("fi", "Tarkista yhteytesi; tietojemme mukaan verkkoyhteytesi "
                      "toimii nyt normaalisti.")
        rejects("sv", "Kontrollera anslutningen; våra register visar att "
                      "anslutningen fungerar normalt.")
        rejects("en", "Check your connection is normal and the subscription "
                      "change is complete.")
        rejects("en", "Check whether our records show your connection is normal "
                      "and the subscription change is complete.")
        rejects("fi", "Tarkista, että verkko toimii normaalisti ja se on kunnossa.")
        rejects("en", "Your connection works normally; check again tomorrow in "
                      "the app.")
        rejects("en", "Check your connection today and it works normally for now.")
        rejects("fi", "Verkkoyhteytesi toimii normaalisti, tarkista uudelleen "
                      "huomenna itse sovelluksessa.")
        rejects("sv", "Anslutningen fungerar normalt, kontrollera igen i morgon "
                      "i appen.")

        # Steps are scanned too.
        rejects("en", "Contact us and keep the message as evidence.",
                ["Your connection works normally."])

        # The same sentence is allowed when the signal was granted.
        allowed = "Your connection works normally and the subscription change is complete."
        trace = []
        out = dna.normalise(_network_case("en"), _network_raw(allowed), trace,
                            granted=[NETWORK])
        self.assertIsNone(dna.fallback_reason(trace))
        self.assertEqual(out["advice_text"], allowed)


class SwedishStepRepairTest(unittest.TestCase):
    def test_repair_never_duplicates_or_invents_a_link(self):
        # Natural Swedish says "klicka inte på länken"; the published step
        # pattern expects "öppna inte länken". The repair adds the recognised
        # wording of a step the answer already gave, and nothing else.
        case = {
            "case_id": "T-16", "journey": "suspicious_message", "language": "sv",
            "opening_message": "Jag fick ett sms med en länk och en liten avgift.",
            "signals": {"artifact": {"type": "sms", "body": "Betala 2 euro: http://x.invalid",
                                     "links": ["http://x.invalid"]}},
        }
        advice = ("Klicka inte på länken, svara inte och betala ingen avgift. "
                  "Radera meddelandet efteråt.")
        raw = {"primary_action": "do_not_interact_and_delete", "risk_level": "medium",
               "urgency": "today", "citations": ["guidance_smishing_basics"],
               "advice_text": advice, "steps": []}
        out = dna.normalise(case, raw)
        found = textcheck.find_steps(out["advice_text"] + "\n" + "\n".join(out["steps"]))
        self.assertIn("dont_open_link", found)
        self.assertIn("dont_pay_or_transfer", found)

        # A step that already says it is not repeated.
        out = dna.normalise(case, dict(raw, steps=["Klicka inte på länken."]))
        self.assertFalse(any(s.startswith("Öppna inte") for s in out["steps"]))

        # No link in the message, so no link step, however the advice reads.
        no_link = {"case_id": "T-18", "journey": "suspicious_call", "language": "sv",
                   "opening_message": "Någon ringde och ville att jag skulle betala en avgift.",
                   "signals": {"artifact": {"type": "call", "body": "Betala avgiften nu."}}}
        out = dna.normalise(no_link, raw)
        self.assertFalse(any(s.startswith("Öppna inte") for s in out["steps"]))


class AdviceCleaningTest(unittest.TestCase):
    def test_only_dialogue_is_stripped_from_advice(self):
        # Dialogue aimed at the assistant goes; an instruction to tell
        # customer service, the bank or someone else stays.
        kept = [
            ("fi", "Soita meille ja kerro heti, että annoit koodin."),
            ("fi", "Soita pankkiisi ja kerro, että kortti on kadonnut."),
            ("en", "Call your bank and tell them the card was used."),
            ("sv", "Ring oss och berätta att du gav koden."),
        ]
        stripped = [
            ("fi", "Kerro minulle, onko kirjautuminen sinun."),
            ("fi", "Kerro onko tämä sinun."),
            ("fi", "Kerro minulle, mitä viestissä luki."),
            ("fi", "Kerrohan, mitä viestissä luki."),
            ("en", "Tell me whether you entered the code."),
            ("sv", "Berätta om du skrev in koden."),
        ]
        clean = "do_not_interact_and_delete"
        for language, line in kept:
            with self.subTest(line=line):
                self.assertEqual(dna._clean_advice(line, clean, language), line)
                self.assertEqual(dna._clean_steps([line], clean), [line])
        for language, line in stripped:
            with self.subTest(line=line):
                self.assertEqual(dna._clean_advice(line, clean, language), "")
                self.assertEqual(dna._clean_steps([line], clean), [])


if __name__ == "__main__":
    unittest.main()
