#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the demo and lab server. No model calls, no network.

    python3 -m unittest app/test_server.py

turns.step is replaced with canned replies so the tests exercise the HTTP,
consent and display plumbing, not the engine. Lab runs read a tiny fixture in
a temporary directory through DNA_RUNS_DIR.
"""

import csv
import json
import os
import re
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import present  # noqa: E402
import server  # noqa: E402
from dsakit import minischema  # noqa: E402

QUESTION = {
    "fi": "Syötitkö korttitietosi sille sivulle?",
    "en": "Did you type your card details on that page?",
    "sv": "Angav du dina kortuppgifter på den sidan?",
}
ADVICE = {
    "fi": "Älä käytä viestin linkkiä uudelleen. Tarkista asia pankin omasta sovelluksesta. "
          "Jos huomaat outoja maksuja, soita pankkiin.",
    "en": "Don't use the link in the message again. Check the matter in the bank's own app. "
          "If you see payments you don't recognise, call the bank.",
    "sv": "Använd inte länken i meddelandet igen. Kontrollera saken i bankens egen app. "
          "Om du ser betalningar du inte känner igen, ring banken.",
}
STEPS = {
    "fi": ["Älä avaa linkkiä uudelleen", "Tarkista asia pankin sovelluksesta"],
    "en": ["Don't open the link again", "Check the matter in the bank's app"],
    "sv": ["Öppna inte länken igen", "Kontrollera saken i bankens app"],
}


class FakeTurns:
    """Canned protocol replies; records every event the server sends."""

    def __init__(self):
        self.events = []
        self.thinking = []
        self.final_on_reply = False
        self.gate = None
        self.entered = threading.Event()
        self.trace = {"raw_text": '{"primary_action": "verify_via_official_channel"}',
                      "rules": [{"rule": "risk", "from": "medium", "to": "high"}],
                      "meta": {"latency_s": 0.01, "cached": False, "prompt_chars": 900},
                      "fallback": False, "error": None}

    def _lang(self, state):
        lang = (state.get("case") or {}).get("language")
        return lang if lang in present.LANGUAGES else "fi"

    def _final(self, state):
        lang = self._lang(state)
        answer = {
            "case_id": state["case"]["case_id"],
            "risk_level": "high",
            "urgency": "today",
            "primary_action": "verify_via_official_channel",
            "advice_text": ADVICE[lang],
            "steps": list(STEPS[lang]),
            "escalation_required": True,
            "escalation_target": "security_specialist",
            "questions_asked": [],
            "question_topics": [],
            "signals_used": ["artifact"] + list(state.get("granted") or []),
            "consent_requested_for": [],
            "citations": ["guidance_bank_verification"],
            "confidence": 0.7,
            "abstained": False,
        }
        return {"type": "final", "answer": answer, "trace": dict(self.trace)}

    def _available(self, state):
        consent = (state.get("case") or {}).get("consent") or {}
        used = set(state.get("granted") or []) | set(state.get("refused") or [])
        return [p for p in consent.get("requires_consent") or []
                if isinstance(p, str) and p not in consent.get("pre_granted", []) and p not in used]

    def step(self, event, state, thinking=None):
        self.events.append(json.loads(json.dumps(event, ensure_ascii=False)))
        self.thinking.append(thinking)
        self.entered.set()
        if self.gate is not None:
            self.gate.wait(5)
        etype = event["type"]
        if etype == "start":
            state.update({"case": event["case"], "facts": {}, "granted": [], "refused": [],
                          "turns": 0})
            return {"type": "question", "text": QUESTION[self._lang(state)],
                    "topics": ["card_details_entered"], "trace": dict(self.trace)}
        if etype == "user_reply":
            state.setdefault("facts", {})["card_details_entered"] = event.get("text", "")
            available = self._available(state)
            if self.final_on_reply:
                return self._final(state)
            if available:
                return {"type": "consent_request", "fields": available[:1],
                        "text": "Saanko katsoa tämän?", "trace": dict(self.trace)}
            return self._final(state)
        if etype == "consent_reply":
            state["granted"] = list(state.get("granted") or []) + list(event.get("granted") or [])
            state["refused"] = list(state.get("refused") or []) + list(event.get("refused") or [])
            return self._final(state)
        return self._final(state)


class FakeHandoff:
    """Canned briefs; the tests set `reply` and inspect `calls`.

    `gate` holds a brief in flight, so a test can see the pending state.
    """

    def __init__(self):
        self.reply = (None, {"error": "test"})
        self.calls = []
        self.gate = None

    def write_brief(self, state, transcript, answer, lang):
        self.calls.append((state, transcript, answer, lang))
        if self.gate is not None:
            self.gate.wait(5)
        return self.reply


def walk(obj, path=""):
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield path + "/" + str(key), value
            yield from walk(value, path + "/" + str(key))
    elif isinstance(obj, list):
        for i, value in enumerate(obj):
            yield "%s/%d" % (path, i), value


SCORED = {
    "label": "fixture",
    "generated_at": "2026-11-06T10:00:00Z",
    "summary": {"cases": 3, "passed": 1, "pass_pct": 33.3,
                "failure_counts": {"wrong_action": 2}},
    "rows": [
        {"case_id": "DSA-D-0001", "journey": "clicked_link", "language": "fi",
         "audience": "consumer", "benign": False, "twin": True, "split": "tune",
         "passed": True, "failures": [], "ours": "verify_via_official_channel",
         "expected": "verify_via_official_channel", "advice": "…", "steps": []},
        {"case_id": "DSA-D-0002", "journey": "clicked_link", "language": "sv",
         "audience": "consumer", "benign": True, "twin": False, "split": "holdout",
         "passed": False, "failures": ["wrong_action"], "ours": "report_to_authority",
         "expected": "no_action_needed", "advice": "…", "steps": []},
        {"case_id": "DSA-D-0003", "journey": "smb_incident", "language": "en",
         "audience": "small_business", "benign": False, "twin": False, "split": "holdout",
         "passed": False, "failures": [{"type": "wrong_action"}, {"type": "unsafe_statement"}],
         "ours": "do_not_interact_and_delete", "expected": "contact_bank_and_block_cards",
         "advice": "…", "steps": []},
    ],
}


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fake = FakeTurns()
        cls.old_turns = server.turns
        server.turns = cls.fake
        cls.fake_handoff = FakeHandoff()
        cls.old_handoff = server.handoff
        server.handoff = cls.fake_handoff
        cls.web = tempfile.TemporaryDirectory()
        os.makedirs(os.path.join(cls.web.name, "demo"))
        os.makedirs(os.path.join(cls.web.name, "lab"))
        os.makedirs(os.path.join(cls.web.name, "shared"))
        for rel in ("demo/index.html", "lab/index.html"):
            with open(os.path.join(cls.web.name, rel), "w", encoding="utf-8") as fh:
                fh.write("<!doctype html><title>%s</title><body>page</body>" % rel)
        with open(os.path.join(cls.web.name, "shared", "tokens.css"), "w", encoding="utf-8") as fh:
            fh.write(":root{--x:1}")
        cls.httpd = server.make_server("127.0.0.1", 0, cls.web.name)
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        server.turns = cls.old_turns
        server.handoff = cls.old_handoff
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=5)
        cls.web.cleanup()

    def setUp(self):
        self.fake.events.clear()
        self.fake.thinking.clear()
        self.fake.final_on_reply = False
        self.fake.gate = None
        self.fake.entered.clear()
        self.fake_handoff.reply = (None, {"error": "test"})
        self.fake_handoff.calls.clear()
        self.fake_handoff.gate = None
        server._runs_cache.clear()

    def request(self, method, path, body=None):
        data = None if body is None else json.dumps(body).encode("utf-8")
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                raw = response.read()
                if method == "HEAD":
                    return response.status, raw, response.headers
                return response.status, json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                raw = exc.read()
                if method == "HEAD":
                    return exc.code, raw, exc.headers
                try:
                    return exc.code, json.loads(raw.decode("utf-8"))
                except ValueError:
                    return exc.code, raw
            finally:
                exc.close()

    def start(self, body):
        status, data = self.request("POST", "/api/conversations", body)
        self.assertEqual(status, 200, data)
        return data

    def start_sample(self, **extra):
        return self.start(dict({"source": "sample"}, **extra))

    def handoff_until_done(self, cid, timeout=3.0):
        """Poll the handoff endpoint until the brief is written."""
        deadline = time.time() + timeout
        while True:
            status, data = self.request("GET", "/api/conversations/%s/handoff?lab=1" % cid)
            self.assertEqual(status, 200, data)
            if not data["pending"] or time.time() >= deadline:
                return data
            time.sleep(0.02)

    # -- static and health --------------------------------------------------

    def test_health(self):
        status, data = self.request("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertIsInstance(data["model"], str)
        self.assertTrue(data["model"])
        self.assertIsInstance(data["key_configured"], bool)
        self.assertNotIn("api_key", data)

    def test_static_pages_and_assets(self):
        with urllib.request.urlopen(self.base + "/", timeout=10) as response:
            body = response.read().decode("utf-8")
            self.assertEqual(response.status, 200)
            self.assertIn("demo/index.html", body)
            self.assertIn("default-src 'self'", response.headers["Content-Security-Policy"])
        with urllib.request.urlopen(self.base + "/lab", timeout=10) as response:
            self.assertEqual(response.status, 200)
            self.assertIn("lab/index.html", response.read().decode("utf-8"))
        with urllib.request.urlopen(self.base + "/shared/tokens.css", timeout=10) as response:
            self.assertEqual(response.headers["Content-Type"], "text/css; charset=utf-8")
        status, data = self.request("GET", "/shared/missing.css")
        self.assertEqual(status, 404)
        self.assertIn("error", data)

    def test_placeholder_while_pages_are_building(self):
        with tempfile.TemporaryDirectory() as empty:
            httpd = server.make_server("127.0.0.1", 0, empty)
            base = "http://127.0.0.1:%d" % httpd.server_address[1]
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                for path in ("/", "/lab"):
                    with urllib.request.urlopen(base + path, timeout=10) as response:
                        self.assertEqual(response.status, 200)
                        self.assertIn("building", response.read().decode("utf-8"))
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=5)

    def test_head_is_handled(self):
        status, raw, headers = self.request("HEAD", "/")
        self.assertEqual(status, 200)
        self.assertEqual(raw, b"")
        self.assertGreater(int(headers["Content-Length"]), 0)
        status, raw, _ = self.request("HEAD", "/api/nope")
        self.assertEqual(status, 404)
        self.assertEqual(raw, b"")

    def test_path_traversal_is_refused(self):
        status, data = self.request("GET", "/shared/../../server.py")
        self.assertEqual(status, 404)
        self.assertIn("error", data)

    def test_public_mode_hides_lab_and_dev(self):
        old = server.PUBLIC
        server.PUBLIC = True
        self.addCleanup(setattr, server, "PUBLIC", old)

        for method, path in (("GET", "/lab"), ("PUT", "/lab"),
                             ("GET", "/lab/index.html"),
                             ("GET", "/api/lab/cases"), ("GET", "/api/lab/runs"),
                             ("POST", "/api/review")):
            status, data = self.request(method, path, {} if method == "POST" else None)
            self.assertEqual(status, 404, (method, path, data))
            self.assertIn("error", data)

        with urllib.request.urlopen(self.base + "/", timeout=10) as response:
            self.assertEqual(response.status, 200)
        status, health = self.request("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertTrue(health["public"])

        status, data = self.request("POST", "/api/conversations?lab=1", {"source": "sample"})
        self.assertEqual(status, 200, data)
        self.assertNotIn("lab", data)
        cid = data["conversation_id"]

        status, data = self.request("POST", "/api/conversations",
                                    {"source": "dev", "case_id": "DSA-D-0002"})
        self.assertEqual(status, 404, data)

        # The handoff endpoint is demo data and stays reachable; its lab part
        # is dropped like every other lab trace.
        status, data = self.request("GET", "/api/conversations/%s/handoff?lab=1" % cid)
        self.assertEqual(status, 200, data)
        self.assertNotIn("lab", data)
        self.assertEqual(data["status"], "none")
        self.assertIsNone(data["text"])
        self.assertEqual(data["answer"], {"priority": None})

    # -- conversation contract ----------------------------------------------

    def test_start_returns_the_section_5_shape(self):
        data = self.start_sample()
        self.assertEqual(set(data), {"conversation_id", "language", "thinking", "reply", "display", "opening"})
        self.assertEqual(data["language"], "fi")
        self.assertEqual(data["reply"]["type"], "question")
        self.assertNotIn("trace", data["reply"])
        self.assertEqual(set(data["display"]),
                         {"attachment", "question", "quick_replies", "consent", "answer",
                          "handoff", "handoff_status", "visibility"})
        self.assertEqual(data["display"]["attachment"]["kind"], "sms")
        self.assertEqual(data["display"]["question"]["text"], QUESTION["fi"])
        self.assertEqual(data["display"]["quick_replies"][0], "Kyllä, syötin korttitiedot")
        self.assertIsNone(data["display"]["answer"])
        self.assertIsNone(data["display"]["consent"])
        self.assertTrue(data["display"]["visibility"]["never"])

    def test_start_by_journey_for_the_demo_chips(self):
        data = self.start_sample(journey="clicked_link")
        self.assertEqual(data["language"], "fi")
        start = [e for e in self.fake.events if e["type"] == "start"][0]
        self.assertEqual(start["case"]["journey"], "clicked_link")
        # the chip's case is the sample clicked_link case
        _, sample_by_id = server.sample_cases()
        found = [c for c in sample_by_id.values() if c["journey"] == "clicked_link"][0]
        self.assertEqual(start["case"]["case_id"], found["case_id"])

    def test_question_then_consent_then_final_with_tokens(self):
        data = self.start_sample()
        cid = data["conversation_id"]
        status, q = self.request("POST", "/api/conversations/%s/message" % cid,
                                 {"text": "Kyllä, syötin korttitiedot"})
        self.assertEqual(status, 200, q)
        self.assertEqual(q["reply"]["type"], "consent_request")
        consent = q["display"]["consent"]
        self.assertTrue(consent["fields"])
        token = consent["fields"][0]
        self.assertRegex(token, r"^s\d+$")
        self.assertNotIn(".", token)
        self.assertEqual([i["field"] for i in consent["items"]], consent["fields"])
        self.assertIn("purpose", consent)
        self.assertIn("fine", consent)

        status, final = self.request("POST", "/api/conversations/%s/consent" % cid,
                                     {"granted": [token], "refused": []})
        self.assertEqual(status, 200, final)
        self.assertEqual(final["reply"]["type"], "final")
        answer = final["display"]["answer"]
        self.assertEqual(answer["headline"], present.ACTIONS["verify_via_official_channel"]["fi"])
        self.assertTrue(answer["reason"])
        self.assertTrue(answer["steps"])
        self.assertEqual(answer["why"]["note"], present.WHY_NOTE["fi"])
        # No model brief yet: a status, never a deterministic card.
        self.assertIsNone(final["display"]["handoff"])
        self.assertIn(final["display"]["handoff_status"]["status"], ("pending", "failed"))
        self.assertTrue(final["display"]["visibility"]["granted"])

        event = [e for e in self.fake.events if e["type"] == "consent_reply"][0]
        self.assertTrue(event["granted"])
        self.assertTrue(all("." in path for path in event["granted"]))
        self.assertIsInstance(event["signals"][event["granted"][0]], (dict, list))

    def test_handoff_brief_is_model_only_and_has_explicit_status(self):
        def escalate(text):
            data = self.start_sample()
            cid = data["conversation_id"]
            status, q = self.request("POST", "/api/conversations/%s/message" % cid,
                                     {"text": text})
            self.assertEqual(status, 200, q)
            self.assertEqual(q["reply"]["type"], "consent_request")
            token = q["display"]["consent"]["fields"][0]
            status, final = self.request("POST", "/api/conversations/%s/consent?lab=1" % cid,
                                         {"granted": [token]})
            self.assertEqual(status, 200, final)
            self.assertEqual(final["reply"]["type"], "final")
            return final

        brief = {
            "situation": "Korttitiedot syötettiin huijaussivulle.",
            "user_actions": ["Syötit korttitiedot", "Vastasit viestiin"],
            "open_questions": ["Onko kortilla tehty maksuja?"],
            "evidence": ["Linkkitarkistus: epäilyttävä linkki"],
            "consent": {"granted": [], "refused": []},
            "advice_given": ["Tarkista pankin sovelluksesta"],
            "risk": "high", "priority": "today", "escalation_priority": 5,
            "first_action": "Varmista, lähtikö maksu",
            "language": "fi",
        }
        gate = threading.Event()
        self.addCleanup(gate.set)
        self.fake_handoff.gate = gate
        self.fake_handoff.reply = (brief, {"error": None})
        final = escalate("Kyllä, syötin korttitiedot")
        # The reply is answered at once with a status; the brief is written
        # behind it and the UI shows no invented summary meanwhile.
        self.assertIsNone(final["display"]["handoff"])
        self.assertEqual(final["display"]["handoff_status"]["status"], "pending")
        self.assertIsNone(final["reply"]["answer"]["priority"])
        self.assertEqual(final["lab"]["trace"]["handoff"], {"status": "pending"})

        status, waiting = self.request(
            "GET", "/api/conversations/%s/handoff" % final["conversation_id"])
        self.assertEqual(status, 200, waiting)
        self.assertEqual(waiting["status"], "pending")
        self.assertTrue(waiting["text"])
        self.assertIsNone(waiting["handoff"])

        gate.set()
        done = self.handoff_until_done(final["conversation_id"])
        self.assertFalse(done["pending"])
        self.assertEqual(done["status"], "ready")
        self.assertIsNone(done["text"])
        handoff = done["handoff"]
        self.assertEqual(handoff["brief"], brief)
        self.assertIn(brief["situation"], handoff["situation"])
        # The structured actions stay in the brief for the expert; the card's
        # situation is the model's one summary.
        self.assertNotIn(brief["user_actions"][0], handoff["situation"])
        self.assertEqual(handoff["brief"]["user_actions"], brief["user_actions"])
        self.assertIn(brief["open_questions"][0], handoff["situation"])
        self.assertIn(brief["first_action"], handoff["advice"])
        self.assertIn(brief["advice_given"][0], handoff["advice"])
        self.assertEqual(done["answer"]["priority"], 5)
        self.assertTrue(done["lab"]["handoff"]["used"])

        # No brief: the endpoint is honest about the failure and returns no
        # deterministic summary or invented score.
        self.fake_handoff.gate = None
        self.fake_handoff.reply = (None, {"error": "test"})
        final = escalate("Kyllä, syötin korttitiedot")
        done = self.handoff_until_done(final["conversation_id"])
        self.assertFalse(done["pending"])
        self.assertEqual(done["status"], "failed")
        self.assertTrue(done["text"])
        self.assertIsNone(done["handoff"])
        self.assertIsNone(done["answer"]["priority"])
        self.assertFalse(done["lab"]["handoff"]["used"])

    def test_a_stale_brief_never_lands_on_a_later_final(self):
        brief = {
            "situation": "Korttitiedot syötettiin huijaussivulle.",
            "user_actions": ["Syötit korttitiedot"],
            "open_questions": [], "evidence": [], "advice_given": [],
            "consent": {"granted": [], "refused": []},
            "risk": "high", "priority": "today", "escalation_priority": 4,
            "first_action": "Varmista, lähtikö maksu", "language": "fi",
        }
        data = self.start_sample()
        cid = data["conversation_id"]
        entry = server._conversations[cid]
        gate = threading.Event()
        self.addCleanup(gate.set)
        self.fake_handoff.gate = gate
        self.fake_handoff.reply = (brief, {"error": None})
        status, q = self.request("POST", "/api/conversations/%s/message" % cid,
                                 {"text": "Kyllä, syötin korttitiedot"})
        self.assertEqual(status, 200, q)
        token = q["display"]["consent"]["fields"][0]
        status, final = self.request("POST", "/api/conversations/%s/consent?lab=1" % cid,
                                     {"granted": [token]})
        self.assertEqual(status, 200, final)
        self.assertEqual(entry["state"].get("handoff_status"), "pending")

        # A later final arrives while the first brief is still in flight.
        later = {"type": "final", "answer": dict(entry["final"], escalation_required=False)}
        with entry["lock"]:
            server._record_reply(entry, later)
        gate.set()
        deadline = time.time() + 3
        while any(t.name == "handoff-%s" % cid for t in threading.enumerate()):
            if time.time() >= deadline:
                self.fail("the stale brief thread did not finish")
            time.sleep(0.01)

        status, done = self.request("GET", "/api/conversations/%s/handoff" % cid)
        self.assertEqual(status, 200, done)
        self.assertFalse(done["pending"])
        self.assertEqual(done["status"], "none")
        self.assertIsNone(done["handoff"])
        self.assertIsNone(done["answer"]["priority"])
        self.assertNotIn("handoff_brief", entry["state"])
        self.assertNotIn("handoff_status", entry["state"])

    def test_ready_priority_is_model_only_and_strict_answer_unchanged(self):
        brief = {
            "situation": "Korttitiedot syötettiin huijaussivulle.",
            "user_actions": ["Syötit korttitiedot"], "open_questions": [],
            "evidence": [], "advice_given": [],
            "consent": {"granted": [], "refused": []},
            "risk": "high", "priority": "today", "escalation_priority": 5,
            "first_action": "Varmista, lähtikö maksu", "language": "fi",
        }
        self.fake_handoff.reply = (brief, {"error": None})
        data = self.start_sample()
        cid = data["conversation_id"]
        status, q = self.request("POST", "/api/conversations/%s/message" % cid,
                                 {"text": "Kyllä, syötin korttitiedot"})
        self.assertEqual(status, 200, q)
        token = q["display"]["consent"]["fields"][0]
        status, final = self.request("POST", "/api/conversations/%s/consent" % cid,
                                     {"granted": [token]})
        self.assertEqual(status, 200, final)
        done = self.handoff_until_done(cid)
        self.assertEqual(done["status"], "ready")
        self.assertEqual(done["answer"]["priority"], 5)

        entry = server._conversations[cid]
        self.assertNotIn("priority", entry["final"])
        with open(os.path.join(server.SIMSET, "schema", "submission.schema.json"),
                  encoding="utf-8") as fh:
            strict = json.load(fh)
        self.assertEqual(minischema.validate(entry["final"], strict), [])

        # The later final does not escalate: the old number must not survive.
        later = {"type": "final", "answer": dict(entry["final"], escalation_required=False)}
        with entry["lock"]:
            server._record_reply(entry, later)
        status, cleared = self.request("GET", "/api/conversations/%s/handoff" % cid)
        self.assertEqual(status, 200, cleared)
        self.assertEqual(cleared["status"], "none")
        self.assertIsNone(cleared["answer"]["priority"])
        self.assertIsNone(cleared["handoff"])
        self.assertNotIn("handoff_brief", entry["state"])

    def test_handoff_polling_never_starts_a_model_call(self):
        brief = {
            "situation": "Korttitiedot syötettiin huijaussivulle.",
            "user_actions": ["Syötit korttitiedot"], "open_questions": [],
            "evidence": [], "advice_given": [],
            "consent": {"granted": [], "refused": []},
            "risk": "high", "priority": "today", "escalation_priority": 4,
            "first_action": "Varmista, lähtikö maksu", "language": "fi",
        }
        self.fake_handoff.reply = (brief, {"error": None})
        data = self.start_sample()
        cid = data["conversation_id"]
        self.request("POST", "/api/conversations/%s/message" % cid,
                     {"text": "Kyllä, syötin korttitiedot"})
        status, final = self.request("POST", "/api/conversations/%s/finish" % cid, {})
        self.assertEqual(status, 200, final)
        self.handoff_until_done(cid)
        calls = len(self.fake_handoff.calls)
        for _ in range(5):
            status, polled = self.request("GET", "/api/conversations/%s/handoff" % cid)
            self.assertEqual(status, 200, polled)
            self.assertEqual(polled["status"], "ready")
        self.assertEqual(len(self.fake_handoff.calls), calls)

    def test_consent_refusal_is_listed_as_not_used(self):
        data = self.start_sample()
        cid = data["conversation_id"]
        status, q = self.request("POST", "/api/conversations/%s/message" % cid, {"text": "Kyllä"})
        self.assertEqual(status, 200, q)
        self.assertEqual(q["reply"]["type"], "consent_request")
        consent = q["display"]["consent"]
        token = consent["fields"][0]
        label = consent["items"][0]["label"]

        status, final = self.request("POST", "/api/conversations/%s/consent" % cid,
                                     {"granted": [], "refused": [token]})
        self.assertEqual(status, 200, final)
        visibility = final["display"]["visibility"]
        self.assertEqual(visibility["granted"], [])
        self.assertEqual(visibility["refused"], [label])
        self.assertNotIn(label, " ".join(final["display"]["answer"]["why"]["bullets"]))

    def test_consent_accepts_paths_for_backwards_compatibility(self):
        data = self.start_sample()
        cid = data["conversation_id"]
        self.request("POST", "/api/conversations/%s/message" % cid, {"text": "Kyllä"})
        path = "operator_account.recent_logins"
        status, final = self.request("POST", "/api/conversations/%s/consent" % cid,
                                     {"granted": [path], "refused": []})
        self.assertEqual(status, 200, final)
        event = [e for e in self.fake.events if e["type"] == "consent_reply"][0]
        self.assertEqual(event["granted"], [path])

    def test_finish_produces_a_final(self):
        data = self.start_sample()
        cid = data["conversation_id"]
        status, out = self.request("POST", "/api/conversations/%s/finish" % cid, {})
        self.assertEqual(status, 200, out)
        self.assertEqual(out["reply"]["type"], "final")

    def test_thinking_flag_holds_for_the_whole_conversation(self):
        data = self.start_sample(thinking=True)
        self.assertIs(data["thinking"], True)
        cid = data["conversation_id"]
        self.request("POST", "/api/conversations/%s/message" % cid, {"text": "kyllä"})
        self.request("POST", "/api/conversations/%s/finish" % cid, {})
        self.assertEqual(self.fake.thinking, [True, True, True])
        self.assertNotIn("reasoning", json.dumps(data))
        status, _ = self.request("POST", "/api/conversations",
                                 {"source": "sample", "thinking": "yes"})
        self.assertEqual(status, 400)

    def test_lab_flag_adds_trace_only_there(self):
        data = self.start_sample()
        cid = data["conversation_id"]
        status, lab = self.request("POST", "/api/conversations/%s/message?lab=1" % cid,
                                   {"text": "Kyllä"})
        self.assertEqual(status, 200, lab)
        self.assertEqual(set(lab["lab"]), {"trace", "turn"})
        self.assertIn("rules", lab["lab"]["trace"])
        self.assertEqual(lab["lab"]["turn"], 2)
        self.assertNotIn("trace", lab["reply"])

        data = self.start_sample()
        cid = data["conversation_id"]
        status, plain = self.request("POST", "/api/conversations/%s/message" % cid,
                                     {"text": "Kyllä"})
        self.assertNotIn("lab", plain)
        self.assertNotIn("trace", json.dumps(plain))

    def test_free_start_with_attachment(self):
        text = "Jag fick det här meddelandet och vet inte vad jag ska göra."
        data = self.start({"source": "free", "text": text, "language": "sv",
                           "audience": "consumer",
                           "attachment": {"kind": "sms", "sender": "LUMIPANKKI",
                                          "body": "Ditt konto är låst: https://example.invalid/login"}})
        self.assertEqual(data["language"], "sv")
        att = data["display"]["attachment"]
        self.assertEqual(att["kind"], "sms")
        self.assertEqual(att["kind_label"], "Sms")
        self.assertEqual(att["sender"], "LUMIPANKKI")
        self.assertIn("example.invalid", att["body"])
        self.assertEqual(att["checks"], [])
        self.assertEqual(data["display"]["question"]["text"], QUESTION["sv"])

        start = [e for e in self.fake.events if e["type"] == "start"][0]
        case = start["case"]
        self.assertEqual(case["signals"]["artifact"]["type"], "sms")
        self.assertIsNone(case["signals"]["link_check"])
        self.assertIsNone(case["signals"]["call_warning"])
        self.assertEqual(case["opening_message"], text)
        self.assertNotIn("ground_truth", case)

    def test_free_start_without_attachment(self):
        data = self.start({"source": "free", "text": "Mitä teen tämän viestin kanssa?",
                           "language": "fi"})
        self.assertIsNone(data["display"]["attachment"])
        self.assertEqual(data["display"]["visibility"]["shared"],
                         [present._SHARED_DESCRIPTION["fi"]])

    def test_attachment_validation(self):
        base = {"source": "free", "text": "Hei"}
        for attachment, why in (
            ({"kind": "fax", "sender": "x", "body": "y"}, "kind"),
            ({"kind": "sms", "sender": "x", "body": ""}, "body"),
            ({"kind": "sms", "sender": "x", "body": "a" * 4001}, "long"),
            ({"kind": "sms", "sender": "x" * 201, "body": "y"}, "sender"),
        ):
            status, data = self.request("POST", "/api/conversations",
                                        dict(base, attachment=attachment))
            self.assertEqual(status, 400, (why, data))
            self.assertIn("error", data)
        status, data = self.request("POST", "/api/conversations",
                                    {"source": "sample", "attachment": {"kind": "sms",
                                                                        "sender": "x", "body": "y"}})
        self.assertEqual(status, 400)

    def test_start_never_leaks_the_case_or_its_ground_truth(self):
        data = self.start_sample()
        blob = json.dumps(data, ensure_ascii=False)
        for forbidden in ("ground_truth", "simulation", "scenario_family", "holdout_family",
                          "reference_answer", "must_ask_topics", "rationale_en", "DSA-D-"):
            self.assertNotIn(forbidden, blob)

    def test_reference_never_reaches_a_step(self):
        status, reference = self.request("GET", "/api/lab/cases/DSA-D-0056/reference")
        self.assertEqual(status, 200, reference)
        self.assertTrue(reference["reference_answer"])
        self.start_sample()

        blob = json.dumps(self.fake.events, ensure_ascii=False)
        for forbidden in ("ground_truth", "simulation", "scenario_family", "holdout_family",
                          "difficulty", "reference_answer", "rationale_en", "title", "tags"):
            self.assertNotIn(forbidden, blob)
        self.assertNotIn(reference["reference_answer"], blob)

    def test_stop_closes_the_chat_and_closed_routes_do_not_call_the_model(self):
        data = self.start_sample()
        cid = data["conversation_id"]
        entry = server._conversations[cid]
        for text in ("stop the transfer", "Can I stop this chat?", "stop?", '"stop"'):
            before = len(self.fake.events)
            status, out = self.request("POST", "/api/conversations/%s/message" % cid,
                                       {"text": text})
            self.assertEqual(status, 200, out)
            self.assertFalse(entry["closed"], text)
            self.assertNotEqual(out["reply"]["type"], "notice", text)
            self.assertEqual(len(self.fake.events), before + 1, text)

        before = len(self.fake.events)
        status, stopped = self.request("POST", "/api/conversations/%s/message?lab=1" % cid,
                                       {"text": "stop"})
        self.assertEqual(status, 200, stopped)
        self.assertTrue(stopped["closed"])
        self.assertEqual(stopped["reply"]["type"], "notice")
        self.assertTrue(stopped["reply"]["text"])
        self.assertEqual(stopped["display"]["notice"], {"text": stopped["reply"]["text"]})
        self.assertIsNone(stopped["display"]["answer"])
        self.assertIsNone(stopped["display"]["handoff"])
        self.assertEqual(stopped["lab"]["trace"]["gating"], {"disposition": "stop"})
        self.assertEqual(len(self.fake.events), before, "a stop called the model")

        granted, refused = set(entry["granted"]), set(entry["refused"])
        before = len(self.fake.events)
        for action, body in (("message", {"text": "resume"}),
                             ("consent", {"granted": ["s1"], "refused": []}),
                             ("finish", {})):
            status, out = self.request("POST", "/api/conversations/%s/%s?lab=1" % (cid, action),
                                       body)
            self.assertEqual(status, 200, out)
            self.assertTrue(out["closed"], action)
            self.assertEqual(out["reply"]["type"], "notice", action)
            self.assertIsNone(out["display"]["answer"], action)
            self.assertIsNone(out["display"]["handoff"], action)
            self.assertEqual(out["lab"]["trace"]["gating"], {"disposition": "closed"}, action)
            self.assertEqual(len(self.fake.events), before, action)
        self.assertEqual(set(entry["granted"]), granted)
        self.assertEqual(set(entry["refused"]), refused)
        self.assertTrue(entry["closed"])

        # The start of a free chat is the same explicit request; attachment
        # text is never read as an instruction.
        before = len(self.fake.events)
        started = self.start({"source": "free", "text": "lopeta", "language": "fi"})
        self.assertTrue(started["closed"])
        self.assertEqual(started["reply"]["type"], "notice")
        self.assertEqual(len(self.fake.events), before)
        before = len(self.fake.events)
        attached = self.start({"source": "free", "text": "What happened?", "language": "en",
                               "attachment": {"kind": "sms", "sender": "x", "body": "stop"}})
        self.assertFalse(server._conversations[attached["conversation_id"]]["closed"])
        self.assertNotEqual(attached["reply"]["type"], "notice")
        self.assertEqual(len(self.fake.events), before + 1)

        for body in ({"source": "sample"}, {"source": "free", "text": "Hei"},
                     {"source": "dev", "case_id": "DSA-D-0056"}):
            data = self.start(body)
            cid = data["conversation_id"]
            entry = server._conversations[cid]
            before = len(self.fake.events)
            status, out = self.request("POST", "/api/conversations/%s/message" % cid,
                                       {"text": "stop"})
            self.assertEqual(status, 200, out)
            self.assertTrue(entry["closed"], body)
            self.assertEqual(out["reply"]["type"], "notice", body)
            self.assertEqual(len(self.fake.events), before, body)

    def test_duplicate_after_final_reuses_it_and_new_context_invalidates_reuse(self):
        self.fake.final_on_reply = True
        data = self.start({"source": "free", "text": "Hei", "language": "fi"})
        cid = data["conversation_id"]
        entry = server._conversations[cid]
        self.assertIsNone(self.fake.events[0]["max_assistant_turns"],
                          "a server chat kept the six-question budget")
        self.fake.events.clear()
        self.fake.entered.clear()

        gate = threading.Event()
        self.addCleanup(gate.set)
        self.fake.gate = gate
        results = []

        def send():
            results.append(self.request("POST", "/api/conversations/%s/message" % cid,
                                        {"text": "Kyllä"}))

        first = threading.Thread(target=send)
        first.start()
        self.assertTrue(self.fake.entered.wait(2), "the first request never reached the assistant")
        second = threading.Thread(target=send)
        second.start()
        time.sleep(0.05)
        gate.set()
        first.join(5)
        second.join(5)
        self.fake.gate = None
        self.assertFalse(first.is_alive() or second.is_alive())
        self.assertEqual(len(results), 2)
        for status, out in results:
            self.assertEqual(status, 200, out)
            self.assertEqual(out["reply"]["type"], "final")
        self.assertEqual(len(self.fake.events), 1,
                         "concurrent duplicate messages made more than one model call")
        self.assertEqual(entry["turn"], 2)
        self.assertEqual(sum(1 for row in entry["transcript"]
                             if row.get("role") == "assistant" and row.get("type") == "final"), 1)
        self.handoff_until_done(cid)
        self.assertEqual(len(self.fake_handoff.calls), 1,
                         "a duplicate message started another brief writer")

        before_events = len(self.fake.events)
        before_turn = entry["turn"]
        status, again = self.request("POST", "/api/conversations/%s/message?lab=1" % cid,
                                     {"text": "Kyllä"})
        self.assertEqual(status, 200, again)
        self.assertEqual(again["reply"]["type"], "final")
        self.assertEqual(again["lab"]["trace"]["gating"], {"disposition": "already_answered"})
        self.assertEqual(len(self.fake.events), before_events)
        self.assertEqual(entry["turn"], before_turn)
        self.assertEqual(len(self.fake_handoff.calls), 1)

        before_events = len(self.fake.events)
        status, follow = self.request("POST", "/api/conversations/%s/message" % cid,
                                      {"text": "Annoin koodin."})
        self.assertEqual(status, 200, follow)
        self.assertEqual(follow["reply"]["type"], "final")
        self.assertEqual(len(self.fake.events), before_events + 1)

        before_events = len(self.fake.events)
        status, old = self.request("POST", "/api/conversations/%s/message" % cid,
                                   {"text": "Kyllä"})
        self.assertEqual(status, 200, old)
        self.assertEqual(len(self.fake.events), before_events + 1,
                         "a repeated word after new facts reused the old final")

        # Consent is part of the context key: the same words with a new grant
        # are answered, not served from the old final.
        path = next(iter(server._allowed_fields(entry)))
        with entry["lock"]:
            entry["granted"].add(path)
        before_events = len(self.fake.events)
        status, changed = self.request("POST", "/api/conversations/%s/message" % cid,
                                       {"text": "Kyllä"})
        self.assertEqual(status, 200, changed)
        self.assertEqual(len(self.fake.events), before_events + 1,
                         "a consent change reused the old final")

    # -- lab ----------------------------------------------------------------

    def test_lab_cases_include_split_and_metadata_only(self):
        status, data = self.request("GET", "/api/lab/cases?limit=200")
        self.assertEqual(status, 200)
        self.assertEqual(data["source"], "dev")
        self.assertEqual(data["total"], len(server.dev_cases()[0]))
        row = data["cases"][0]
        self.assertEqual(set(row), {"case_id", "journey", "language", "audience",
                                    "benign", "twin", "split"})
        splits = {r["split"] for r in data["cases"]}
        self.assertTrue(splits <= {"tune", "holdout"})
        self.assertIn("holdout", splits)

    def test_lab_cases_filter_and_paginate(self):
        status, data = self.request("GET", "/api/lab/cases?journey=clicked_link&language=sv&limit=5")
        self.assertEqual(status, 200)
        self.assertTrue(all(r["journey"] == "clicked_link" for r in data["cases"]))
        self.assertTrue(all(r["language"] == "sv" for r in data["cases"]))
        self.assertLessEqual(len(data["cases"]), 5)
        status, data = self.request("GET", "/api/lab/cases?split=holdout&benign=1&limit=200")
        self.assertTrue(all(r["split"] == "holdout" and r["benign"] for r in data["cases"]))
        status, page = self.request("GET", "/api/lab/cases?limit=2&offset=2")
        self.assertEqual(page["offset"], 2)
        self.assertEqual(len(page["cases"]), 2)

    def test_lab_sample_cases_have_titles(self):
        status, data = self.request("GET", "/api/lab/cases?source=sample")
        self.assertEqual(status, 200)
        self.assertEqual(data["total"], 5)
        self.assertTrue(all(r.get("title") for r in data["cases"]))

    def test_lab_reference_unknown_case(self):
        status, data = self.request("GET", "/api/lab/cases/NOPE/reference")
        self.assertEqual(status, 404)
        self.assertIn("error", data)

    def test_lab_simulate_and_run_to_end(self):
        data = self.start_sample()
        cid = data["conversation_id"]
        status, one = self.request("POST", "/api/lab/conversations/%s/simulate" % cid, {})
        self.assertEqual(status, 200, one)
        self.assertIn("message", one)
        self.assertIn("lab", one)
        self.assertNotIn("lab", self.request("POST", "/api/conversations/%s/message" % cid,
                                             {"text": "Kyllä"})[1])

        data = self.start_sample()
        cid = data["conversation_id"]
        status, done = self.request("POST", "/api/lab/conversations/%s/run-to-end" % cid, {})
        self.assertEqual(status, 200, done)
        self.assertEqual(done["reply"]["type"], "final")
        self.assertTrue(done["finished"])
        self.assertTrue(done["messages"])
        self.assertIn("answer", done["display"])

    def test_lab_evaluate_uses_the_reference(self):
        data = self.start_sample()
        cid = data["conversation_id"]
        status, early = self.request("POST", "/api/lab/conversations/%s/evaluate" % cid, {})
        self.assertEqual(status, 400)
        self.request("POST", "/api/lab/conversations/%s/run-to-end" % cid, {})
        status, result = self.request("POST", "/api/lab/conversations/%s/evaluate" % cid, {})
        self.assertEqual(status, 200, result)
        self.assertEqual(result["case_id"], "DSA-D-0056")
        self.assertIn("result", result)
        self.assertIn("reference", result)
        self.assertIn("summary", result)

    def test_lab_evaluate_rejects_free_conversations(self):
        data = self.start({"source": "free", "text": "Hei"})
        status, result = self.request("POST", "/api/lab/conversations/%s/evaluate" % data["conversation_id"], {})
        self.assertEqual(status, 400)

    def test_lab_runs_list_and_filter_from_fixture(self):
        with tempfile.TemporaryDirectory() as runs:
            with open(os.path.join(runs, "fixture.scored.json"), "w", encoding="utf-8") as fh:
                json.dump(SCORED, fh)
            old = os.environ.get("DNA_RUNS_DIR")
            os.environ["DNA_RUNS_DIR"] = runs
            try:
                status, data = self.request("GET", "/api/lab/runs")
                self.assertEqual(status, 200, data)
                self.assertEqual([r["name"] for r in data["runs"]], ["fixture.scored.json"])
                self.assertEqual(data["runs"][0]["summary"]["cases"], 3)

                status, detail = self.request("GET", "/api/lab/runs/fixture.scored.json")
                self.assertEqual(status, 200, detail)
                self.assertEqual(detail["total"], 3)
                self.assertEqual(detail["filtered"], 3)
                self.assertEqual(detail["summary"]["passed"], 1)

                status, detail = self.request("GET", "/api/lab/runs/fixture.scored.json?failure=wrong_action")
                self.assertEqual(detail["filtered"], 2)
                status, detail = self.request("GET", "/api/lab/runs/fixture.scored.json?failure=unsafe_statement")
                self.assertEqual(detail["filtered"], 1)
                status, detail = self.request("GET", "/api/lab/runs/fixture.scored.json?benign=1")
                self.assertEqual([r["case_id"] for r in detail["rows"]], ["DSA-D-0002"])
                status, detail = self.request("GET", "/api/lab/runs/fixture.scored.json?split=holdout&language=en")
                self.assertEqual([r["case_id"] for r in detail["rows"]], ["DSA-D-0003"])
                status, detail = self.request("GET", "/api/lab/runs/fixture.scored.json?twin=1")
                self.assertEqual([r["case_id"] for r in detail["rows"]], ["DSA-D-0001"])

                for bad in ("nope.json", "../fixture.scored.json"):
                    status, data = self.request("GET", "/api/lab/runs/" + bad)
                    self.assertIn(status, (400, 404))
                    self.assertIn("error", data)
            finally:
                if old is None:
                    os.environ.pop("DNA_RUNS_DIR", None)
                else:
                    os.environ["DNA_RUNS_DIR"] = old

    def test_lab_runs_never_scores_on_request(self):
        def boom(*args, **kwargs):
            raise AssertionError("the lab must not score on request")

        old = server._score_one
        server._score_one = boom
        with tempfile.TemporaryDirectory() as runs:
            with open(os.path.join(runs, "fixture.scored.json"), "w", encoding="utf-8") as fh:
                json.dump(SCORED, fh)
            old_env = os.environ.get("DNA_RUNS_DIR")
            os.environ["DNA_RUNS_DIR"] = runs
            try:
                status, _ = self.request("GET", "/api/lab/runs")
                self.assertEqual(status, 200)
                status, _ = self.request("GET", "/api/lab/runs/fixture.scored.json?failure=wrong_action")
                self.assertEqual(status, 200)
            finally:
                server._score_one = old
                if old_env is None:
                    os.environ.pop("DNA_RUNS_DIR", None)
                else:
                    os.environ["DNA_RUNS_DIR"] = old_env

    def test_review_writes_csv(self):
        old = os.environ.get("DNA_REVIEW_CSV")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "review.csv")
            os.environ["DNA_REVIEW_CSV"] = path
            try:
                status, data = self.request("POST", "/api/lab/review", {
                    "case_id": "DSA-D-0056", "run": "", "verdict": "ok",
                    "note": "checked by hand, fine",
                })
                self.assertEqual(status, 200, data)
                with open(path, encoding="utf-8", newline="") as fh:
                    rows = list(csv.reader(fh))
                self.assertEqual(rows[0], ["timestamp", "case_id", "run", "verdict", "note"])
                self.assertEqual(rows[1][1:], ["DSA-D-0056", "", "ok", "checked by hand, fine"])
            finally:
                if old is None:
                    os.environ.pop("DNA_REVIEW_CSV", None)
                else:
                    os.environ["DNA_REVIEW_CSV"] = old

    # -- errors -------------------------------------------------------------

    def test_bad_requests_are_json(self):
        status, data = self.request("POST", "/api/conversations", {"source": "nope"})
        self.assertEqual(status, 400)
        self.assertIn("error", data)
        status, data = self.request("POST", "/api/conversations", {"source": "dev", "case_id": "NOPE"})
        self.assertEqual(status, 404)
        status, data = self.request("GET", "/api/nope")
        self.assertEqual(status, 404)
        self.assertIn("error", data)
        status, data = self.request("POST", "/api/nope", {})
        self.assertEqual(status, 404)
        self.assertIn("error", data)
        status, data = self.request("GET", "/api/conversations/doesnotexist")
        self.assertEqual(status, 404)
        self.assertIn("error", data)
        status, data = self.request("POST", "/api/conversations/doesnotexist/message", {"text": "x"})
        self.assertEqual(status, 404)

    def test_display_never_contains_signal_paths_or_ids(self):
        data = self.start_sample()
        cid = data["conversation_id"]
        _, q = self.request("POST", "/api/conversations/%s/message" % cid, {"text": "Kyllä"})
        token = q["display"]["consent"]["fields"][0]
        _, final = self.request("POST", "/api/conversations/%s/consent" % cid,
                                {"granted": [token]})
        path_shape = re.compile(r"^[a-z_]+(\.[a-z_]+)+$")
        for body in (data, q, final):
            for path, value in walk(body["display"]):
                if not isinstance(value, str):
                    continue
                self.assertIsNone(path_shape.match(value), "%s looks like a signal path" % path)
                for ident in ("operator_account.recent_logins", "device.recent_app_installs",
                              "verify_via_official_channel", "guidance_", "DSA-D-"):
                    self.assertNotIn(ident, value, path)


if __name__ == "__main__":
    unittest.main()
