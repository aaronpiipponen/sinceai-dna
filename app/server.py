#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Web demo and lab server for the DNA Digital Security Assistant.

    python3 app/server.py --port 8000

Two pages, one API:

* `/`     the demo judges see (`app/web/demo/`), mobile first;
* `/lab`  our workbench (`app/web/lab/`).

Everything the end user reads is built in `app/present.py` from the validated
protocol reply and the conversation state, so the browser only renders. The
demo never receives a trace; pass `?lab=1` to get `lab.trace` and `lab.turn`.

Conversation responses are `{conversation_id, language, thinking, reply,
display, lab?}`. A start may send `thinking: true|false` (default DNA_THINKING);
it holds for the whole conversation and the reasoning is never returned.
`GET /api/conversations/<id>/handoff` returns `{conversation_id, pending, status,
handoff, answer}`; poll it while `pending` is true. Polling never calls the
model. The answer snapshot carries the model-written `priority` when the brief
is ready; otherwise it is null. The strict scored answer has no such field.
A start response also carries `opening`, the user's first bubble (the case's
opening message, or the free text the browser sent); later messages do not
repeat it. Consent answers travel by opaque token (`display.consent.fields`,
e.g. `s1`) because a signal path must never reach the demo; `/consent` accepts
those tokens and, for old clients, the raw paths.

Safety boundaries live in the engine, not here:

* A case reaches turns.step only as dsakit.simulator.visible_case(), so no
  ground truth, simulation facts, family ids or titles can leak into a prompt.
* Consent replies carry values for granted paths only, read from the full case
  in memory with dsakit.simulator.reveal_signals().
* Every reply shown to the browser is whatever turns.step/dna.normalise()
  produced. This file never streams model text and never re-writes advice.
* The API key stays in this process. /api/health reports a boolean only.

Lab runs are pre-scored files (`results/runs/*.scored.json`); this server never
scores on request. `DNA_RUNS_DIR` overrides the directory (tests use it).

Conversations are in memory only; restarting the server drops them. Each
request is handled by its own thread (ThreadingHTTPServer) and the model call
runs inside it, so a slow answer does not block the rest of the UI. Requests
for the same conversation are serialised with a per-conversation lock.

Standard library only.
"""

import argparse
import copy
import csv
import datetime
import importlib
import json
import os
import re
import sys
import threading
import time
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
SIMSET = os.path.join(PROJECT, "DNA_Digital_Security_Assistant_SimSet_v2.0.1")
WEB = os.path.join(HERE, "web")
PROFILE_PATH = os.path.join(HERE, "demo_profile.json")
RESULTS = os.path.join(PROJECT, "results")
SPLIT_PATH = os.path.join(PROJECT, "data", "splits", "split.json")
SAMPLE_PATH = os.path.join(SIMSET, "data", "samples", "five_journeys.jsonl")
DEV_PATH = os.path.join(SIMSET, "data", "dev", "cases.jsonl")

sys.path.insert(0, HERE)
sys.path.insert(0, SIMSET)

import dna  # noqa: E402
import gating  # noqa: E402
import present  # noqa: E402
from dsakit import textcheck  # noqa: E402
from dsakit.simulator import UserSimulator, reveal_signals, visible_case  # noqa: E402

MAX_BODY = 2 * 1024 * 1024
MAX_FREE_TEXT = 4000
MAX_ATTACHMENT = 4000
MAX_ATTACHMENT_SENDER = 200
# Autoplay safety bound only: a lab loop must stop eventually. It is not a
# product chat limit; server conversations start with max_assistant_turns=None.
MAX_RUN_TO_END = 14
MAX_PAGE = 200
LANGS = ("fi", "en", "sv")
AUDIENCES = ("consumer", "small_business")
ATTACHMENT_KINDS = ("sms", "email", "call", "letter")
CONSENT_TEXT = {
    "fi": ("Kyllä, saat katsoa.", "En halua, että katsot näitä tietoja."),
    "en": ("Yes, you may look at that.", "No, I do not want you to look at that."),
    "sv": ("Ja, du får titta på det.", "Nej, jag vill inte att du tittar på det."),
}

PLACEHOLDER = """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>DNA security assistant</title></head>
<body><h1>DNA security assistant</h1><p>building</p></body>
</html>
"""


# --- optional modules -------------------------------------------------------

_turns_error = None
try:
    turns = importlib.import_module("turns")
except Exception as exc:  # ImportError while the module is being written, or a real error
    turns = None
    _turns_error = "%s: %s" % (type(exc).__name__, str(exc)[:200])

_handoff_error = None
try:
    handoff = importlib.import_module("handoff")
except Exception as exc:  # the demo still works without the brief
    handoff = None
    _handoff_error = "%s: %s" % (type(exc).__name__, str(exc)[:200])


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


# --- data -------------------------------------------------------------------

_data_lock = threading.Lock()
_dev_cases = None
_dev_by_id = None
_sample_cases = None
_sample_by_id = None
_profiles = None
_split = None


def _read_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def dev_cases():
    global _dev_cases, _dev_by_id
    with _data_lock:
        if _dev_cases is None:
            _dev_cases = _read_jsonl(DEV_PATH)
            _dev_by_id = {c["case_id"]: c for c in _dev_cases}
        return _dev_cases, _dev_by_id


def sample_cases():
    global _sample_cases, _sample_by_id
    with _data_lock:
        if _sample_cases is None:
            _sample_cases = _read_jsonl(SAMPLE_PATH)
            _sample_by_id = {c["case_id"]: c for c in _sample_cases}
        return _sample_cases, _sample_by_id


def profiles():
    global _profiles
    with _data_lock:
        if _profiles is None:
            with open(PROFILE_PATH, encoding="utf-8") as fh:
                _profiles = json.load(fh)
        return _profiles


def holdout_families():
    """Families locked in data/splits/split.json. Cached until the file changes."""
    global _split
    try:
        mtime = os.stat(SPLIT_PATH).st_mtime
    except OSError:
        return set()
    with _data_lock:
        if _split is None or _split[0] != mtime:
            try:
                with open(SPLIT_PATH, encoding="utf-8") as fh:
                    data = json.load(fh)
                families = {f for f in data.get("holdout_families") or [] if isinstance(f, str)}
            except (OSError, ValueError):
                families = set()
            _split = (mtime, families)
        return _split[1]


def _split_of(case):
    return "holdout" if case.get("scenario_family") in holdout_families() else "tune"


# --- small helpers ----------------------------------------------------------


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _s(value):
    return value.strip() if isinstance(value, str) else ""


def _bool_param(value):
    if value is None or value == "":
        return None
    return value.strip().lower() in ("1", "true", "yes", "on")


# Public mode: the tunnel publishes the demo only. Lab pages, lab APIs and dev
# cases are gated here, not in the tunnel, so they stay unreachable even if the
# hostname is guessed.
PUBLIC = _bool_param(os.environ.get("DNA_PUBLIC")) is True


def _lab_path(path):
    return (path == "/lab" or path.startswith("/lab/")
            or path.startswith("/api/lab/")
            or path == "/api/review")


def _int_param(query, key, default, low, high):
    try:
        value = int((query.get(key, [""])[0] or "").strip())
    except ValueError:
        return default
    return max(low, min(high, value))


def _reference(case):
    """Ground truth for the inspector. Never call this from a step path."""
    gt = case["ground_truth"]
    lang = case.get("language") or "en"
    text = gt.get("reference_answer_" + lang) or gt.get("reference_answer_en") or ""
    used_lang = lang if gt.get("reference_answer_" + lang) else "en"
    out = {
        "case_id": case["case_id"],
        "journey": case["journey"],
        "language": case.get("language"),
        "audience": case.get("audience"),
        "primary_action": gt.get("primary_action"),
        "acceptable_actions": gt.get("acceptable_actions") or [],
        "risk_level": gt.get("risk_level"),
        "urgency": gt.get("urgency"),
        "escalation": gt.get("escalation") or {},
        "must_ask_topics": gt.get("must_ask_topics") or [],
        "should_ask_topics": gt.get("should_ask_topics") or [],
        "relevant_topics": gt.get("relevant_topics") or [],
        "required_steps": gt.get("required_steps") or [],
        "optional_steps": gt.get("optional_steps") or [],
        "must_not": gt.get("must_not") or [],
        "necessary_signals": gt.get("necessary_signals") or [],
        "guidance_refs": gt.get("guidance_refs") or [],
        "rationale_en": gt.get("rationale_en") or "",
        "single_turn": gt.get("single_turn") or {},
        "benign": bool(gt.get("is_benign_control")),
        "twin": bool(gt.get("twin_group")),
        "reference_answer": text,
        "reference_answer_language": used_lang,
    }
    out["reference_answer_" + used_lang] = text
    return out


def _guess_journey(text, audience="consumer"):
    """Route a free-text opener to a journey for the adapter.

    This is presentation plumbing, not safety logic: the engine still decides
    the action. The demo profile's own journey is the fallback.
    """
    t = (text or "").lower()
    if re.search(r"\b(call|called|phone|rang|puhelu|soitti|samtal|ringde)\b", t):
        return "suspicious_call"
    if re.search(r"\b(clicked|opened the link|installed|downloaded|entered|typed|klikkasin|avasin|asensin|syötin|klickade|installerade|angav)\b", t):
        return "clicked_link"
    if re.search(r"\b(breach|leak|leaked|vuoto|tietovuoto|läcka|sim|esim|number stopped|liittymä)\b", t):
        return "breach_notice"
    if audience == "small_business" and re.search(r"\b(invoice|payment|pay|bank account|maksu|lasku|tilisiirto|betalning|faktura)\b", t):
        return "smb_incident"
    return "suspicious_message"


def _attachment_case(body, language):
    """Validate the demo's attachment sheet and build signals.artifact."""
    raw = body.get("attachment")
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ApiError(400, "attachment must be an object")
    kind = _s(raw.get("kind")).lower()
    if kind not in ATTACHMENT_KINDS:
        raise ApiError(400, "attachment kind must be sms, email, call or letter")
    sender = _s(raw.get("sender"))
    if len(sender) > MAX_ATTACHMENT_SENDER:
        raise ApiError(400, "attachment sender is longer than %d characters" % MAX_ATTACHMENT_SENDER)
    text = _s(raw.get("body"))
    if not text:
        raise ApiError(400, "attachment body is required")
    if len(text) > MAX_ATTACHMENT:
        raise ApiError(400, "attachment body is longer than %d characters" % MAX_ATTACHMENT)
    return present.artifact_from_attachment(kind, sender, text, language)


def _free_case(body):
    text = _s(body.get("text"))
    if not text:
        raise ApiError(400, "text is required for a free conversation")
    if len(text) > MAX_FREE_TEXT:
        raise ApiError(400, "text is longer than %d characters" % MAX_FREE_TEXT)
    audience = _s(body.get("audience")) or "consumer"
    if audience not in AUDIENCES:
        raise ApiError(400, "audience must be consumer or small_business")
    config = profiles().get("profiles", profiles())
    profile = config.get(audience)
    if not profile:
        raise ApiError(500, "demo profile for %s is missing" % audience)
    language = _s(body.get("language")) or profile.get("language") or "fi"
    if language not in LANGS:
        raise ApiError(400, "language must be one of fi, en, sv")

    journey = _guess_journey(text, audience) if body.get("guess_journey", True) is not False else profile.get("journey", "suspicious_message")
    persona = dict(profile.get("persona") or {})
    persona["language"] = language
    case = {
        "case_id": "DEMO-%s-%s" % (audience[:3].upper(), uuid.uuid4().hex[:6]),
        "split": "demo",
        "version": "2.0.1",
        "journey": journey,
        "audience": audience,
        "locale": {"fi": "fi-FI", "en": "en-GB", "sv": "sv-SE"}[language],
        "language": language,
        "persona": persona,
        "entry_point": profile.get("entry_point", "consumer_app_chat"),
        "user_identified": True,
        "opening_message": text,
        "signals": json.loads(json.dumps(profile.get("signals") or {})),
        "signal_availability": dict(profile.get("signal_availability") or {}),
        "consent": json.loads(json.dumps(profile.get("consent") or {"requires_consent": [], "pre_granted": []})),
    }
    artifact = _attachment_case(body, language)
    if artifact:
        # We do not run real link checks: link_check stays null.
        case["signals"]["artifact"] = artifact
        case["signals"]["link_check"] = None
        case["signals"]["call_warning"] = None
    return case


# --- conversations ----------------------------------------------------------

_conversations = {}
_conversations_lock = threading.Lock()


def _stub_trace(text=None):
    return {"raw_text": text, "rules": [], "meta": {}, "fallback": False, "error": None}


def _engine_safe(case):
    """Drop ungranted consent-gated signals for the single-turn stub.

    Kept as a named adapter hook; the boundary itself is dna.authorised(), so
    the stub, batch, replay and the multi-turn adapter cannot drift apart.
    """
    return dna.authorised(case)


def _stub_step(event, state, thinking=None):
    """Development fallback when turns.py is not importable.

    It answers a start or turn_limit event from the single-turn engine, so the
    UI and the live model path still work. It never invents advice.
    """
    etype = event.get("type")
    case = state.get("case") or event.get("case")
    if etype == "start":
        case = _engine_safe(event["case"])
        state["case"] = case
        state.setdefault("facts", {})
        state.setdefault("granted", [])
        state.setdefault("refused", [])
        answer, trace = dna.run(case, thinking=thinking)
        state["answer"] = answer
        state["trace"] = trace
        return {"type": "final", "answer": answer, "trace": trace}
    if state.get("answer"):
        answer = state["answer"]
        return {"type": "final", "answer": answer, "trace": state.get("trace") or _stub_trace()}
    if case:
        answer, trace = dna.run(_engine_safe(case), thinking=thinking)
        state["answer"] = answer
        state["trace"] = trace
        return {"type": "final", "answer": answer, "trace": trace}
    return {"type": "final", "answer": {"advice_text": "", "abstained": True}, "trace": _stub_trace()}


def assistant_step(event, state, thinking):
    """Call turns.step when available, otherwise the stub.

    Resolved at call time so tests can monkeypatch this module's `turns`.
    `thinking` is the conversation's own flag, fixed when it started.
    """
    module = globals().get("turns")
    fn = getattr(module, "step", None) if module is not None else None
    if fn is None:
        return _stub_step(event, state, thinking)
    return fn(event, state, thinking=thinking)


def _ensure_trace(reply):
    if not isinstance(reply, dict):
        raise ApiError(502, "assistant returned a non-object reply")
    trace = reply.get("trace")
    if not isinstance(trace, dict):
        trace = {}
    base = {"raw_text": None, "rules": [], "meta": {}, "fallback": False, "error": None}
    base.update(trace)
    if not isinstance(base.get("rules"), list):
        base["rules"] = []
    if not isinstance(base.get("meta"), dict):
        base["meta"] = {}
    reply["trace"] = base
    if not reply.get("type"):
        reply["type"] = "final" if isinstance(reply.get("answer"), dict) else "unknown"
    if reply["type"] == "final" and not isinstance(reply.get("answer"), dict):
        raise ApiError(502, "assistant returned a final reply without an answer object")
    return reply


def _write_brief_async(entry, gen, state, transcript, answer, language):
    """Write the brief off the request thread, then store it if still current.

    The copies are taken under the conversation lock by `_record_reply`; the
    model call itself holds no lock, so a slow brief never delays a reply. A
    later final bumps the generation and the stale result is dropped.
    """
    module = globals().get("handoff")
    if module is None:
        brief = None
        info = {"error": "handoff module unavailable: %s" % (
            _handoff_error or "not imported"), "used": False}
    else:
        brief, info = module.write_brief(state, transcript, answer, language)
        info = dict(info)
        info["used"] = brief is not None
    if brief is not None and not present.valid_brief(brief):
        # A writer that breaks its own schema is a failure, not a card. The
        # numeric priority comes only from a validated model brief.
        brief = None
        info["used"] = False
        info["error"] = "brief has no valid escalation_priority"
    with entry["lock"]:
        if entry.get("handoff_gen") != gen:
            return
        entry["handoff_info"] = info
        if brief is not None:
            entry["state"]["handoff_brief"] = brief
            entry["state"]["handoff_status"] = "ready"
        else:
            entry["state"].pop("handoff_brief", None)
            entry["state"]["handoff_status"] = "failed"


def _append_user(entry, row):
    """Record one user row and remember it for duplicate detection."""
    entry["transcript"].append(row)
    kind = "message" if row.get("type") == "reply" else row.get("type")
    entry["last_user"] = {"kind": kind, "text": row.get("text") or ""}
    return row


def _consent_context(entry):
    return (tuple(sorted(entry.get("granted") or [])),
            tuple(sorted(entry.get("refused") or [])))


def _repeated_final(entry, text):
    """The exact message just answered by the current final, same consent."""
    key = entry.get("final_key") or {}
    last = entry.get("last_reply") or {}
    context = _consent_context(entry)
    return (key.get("kind") == "message"
            and gating.is_repeat(text, key.get("text"), last.get("type"), context,
                                 (key.get("granted"), key.get("refused"))))


def _notice(entry, reason):
    """A deterministic courtesy reply; never advice and never a model call."""
    reply = gating.notice_reply(entry["language"], reason)
    _ensure_trace(reply)
    reply["trace"]["gating"] = {"disposition": reason}
    return reply


def _record_reply(entry, reply):
    reply = _ensure_trace(reply)
    if reply.get("type") == "consent_request":
        reply["fields"] = [f for f in (reply.get("fields") or []) if isinstance(f, str)]
    entry["turn"] += 1
    row = {"role": "assistant", "ts": _now()}
    row.update(reply)
    entry["transcript"].append(row)
    entry["last_reply"] = reply
    if reply.get("type") == "final":
        entry["final"] = reply["answer"]
        context = _consent_context(entry)
        user = entry.get("last_user") or {}
        entry["final_key"] = {
            "kind": user.get("kind"),
            "text": user.get("text") or "",
            "granted": context[0],
            "refused": context[1],
        }
        # A stale brief from an earlier escalation must never survive a
        # follow-up that ends without one.
        entry["state"].pop("handoff_brief", None)
        entry["state"].pop("handoff_status", None)
        entry["handoff_info"] = None
        entry["handoff_gen"] = entry.get("handoff_gen", 0) + 1
        gen = entry["handoff_gen"]
        answer = reply["answer"]
        if answer.get("escalation_required"):
            entry["state"]["handoff_status"] = "pending"
            # Copies taken now, while the caller holds the lock: the thread
            # reads no shared state during the model call.
            threading.Thread(
                target=_write_brief_async,
                args=(entry, gen, copy.deepcopy(entry["state"]),
                      copy.deepcopy(entry["transcript"]), copy.deepcopy(answer),
                      entry["language"]),
                name="handoff-%s" % entry["id"], daemon=True).start()
            reply["trace"]["handoff"] = {"status": "pending"}
    return reply


def _conversation_body(entry, reply, lab=False):
    """The whole body of a conversation endpoint, per UI_SPEC section 5.

    Lock-free so a caller that already holds `entry["lock"]` can snapshot the
    reply, state, priority and display in one critical section. The strict
    answer is copied, never mutated: `reply.answer.priority` is a demo-only
    field taken from the current validated model brief.
    """
    reply = copy.deepcopy(reply)
    trace = reply.pop("trace", None)
    answer = reply.get("answer") if isinstance(reply.get("answer"), dict) else None
    # One snapshot: priority and display must agree about whether the brief
    # was ready. The writer only takes this lock to publish its result.
    priority = None
    if answer is not None and answer.get("escalation_required"):
        if entry["state"].get("handoff_status") == "ready":
            priority = present.brief_priority(entry["state"].get("handoff_brief"))
    if answer is not None:
        answer["priority"] = priority
    display = present.display(entry["visible_case"], entry["state"], reply,
                              entry["language"])
    body = {
        "conversation_id": entry["id"],
        "language": entry["language"],
        "thinking": entry["thinking"],
        "reply": reply,
        "display": display,
    }
    if entry.get("closed"):
        body["closed"] = True
    if lab:
        body["lab"] = {"trace": trace if isinstance(trace, dict) else {}, "turn": entry["turn"]}
    return body


def _conversation_response(entry, reply, lab=False):
    """Snapshot a response under the entry lock; never call while holding it."""
    with entry["lock"]:
        return _conversation_body(entry, reply, lab)


def _new_conversation(body, lab=False):
    source = _s(body.get("source"))
    if source not in ("sample", "dev", "free"):
        raise ApiError(400, "source must be sample, dev or free")
    # Opt-in careful mode: slower (tens of seconds a turn), better answers.
    # The reasoning itself is never returned; omitted means DNA_THINKING.
    thinking = body.get("thinking")
    if thinking is not None and not isinstance(thinking, bool):
        raise ApiError(400, "thinking must be true or false")
    thinking = dna.thinking_flag(thinking)
    if PUBLIC and source == "dev":
        # The demo and its deep links use sample/free; dev cases carry answers.
        raise ApiError(404, "not found")

    if source == "free":
        case = _free_case(body)
    else:
        if body.get("attachment") is not None:
            raise ApiError(400, "attachment is only accepted for source=free")
        case_id = _s(body.get("case_id"))
        journey = _s(body.get("journey"))
        if source == "sample":
            cases, by_id = sample_cases()
            if case_id:
                if case_id not in by_id:
                    raise ApiError(404, "unknown sample case %s" % case_id)
                case = by_id[case_id]
            elif journey:
                match = [c for c in cases if c.get("journey") == journey]
                if not match:
                    raise ApiError(404, "no sample case for journey %s" % journey)
                case = match[0]
            else:
                case = cases[0]
        else:
            if not case_id:
                raise ApiError(400, "case_id is required for source=dev")
            cases, by_id = dev_cases()
            if case_id not in by_id:
                raise ApiError(404, "unknown dev case %s" % case_id)
            case = by_id[case_id]

    vis = visible_case(case, ())
    cid = uuid.uuid4().hex
    simulator = None
    if source in ("dev", "sample") and "simulation" in case:
        try:
            simulator = UserSimulator(case)
        except Exception:
            simulator = None
    entry = {
        "id": cid,
        "state": {},
        "full_case": case,
        "source": source,
        "language": case.get("language") if case.get("language") in LANGS else "fi",
        "visible_case": vis,
        "transcript": [{"role": "user", "type": "opening", "text": case.get("opening_message", ""), "ts": _now()}],
        "final": None,
        "last_reply": None,
        "last_user": {"kind": "opening", "text": case.get("opening_message", "")},
        "closed": False,
        "simulator": simulator,
        "granted": set(),
        "refused": set(),
        "turn": 0,
        "thinking": thinking,
        "handoff_gen": 0,
        "handoff_info": None,
        "lock": threading.Lock(),
        "created": time.time(),
    }
    event = {"type": "start", "conversation_id": cid, "case": vis,
             "max_assistant_turns": None}
    with entry["lock"]:
        if source == "free" and gating.stop_requested(case.get("opening_message")):
            entry["closed"] = True
            reply = _notice(entry, "stop")
            _record_reply(entry, reply)
        else:
            reply = _record_reply(entry, assistant_step(event, entry["state"], entry["thinking"]))
        with _conversations_lock:
            _conversations[cid] = entry
        out = _conversation_body(entry, reply, lab)
    # The demo draws the user's first bubble from this; later messages never
    # repeat it. Case content, not an id.
    out["opening"] = entry["transcript"][0]["text"]
    return out


def _get_entry(cid):
    with _conversations_lock:
        entry = _conversations.get(cid)
    if entry is None:
        raise ApiError(404, "unknown conversation")
    return entry


def _consent_text(lang, granted, refused):
    yes, no = CONSENT_TEXT.get(lang, CONSENT_TEXT["en"])
    parts = []
    if granted:
        parts.append(yes)
    if refused:
        parts.append(no)
    return " ".join(parts) or yes


def _record_step(entry, event):
    """Call the assistant and record its reply. Caller holds entry["lock"]."""
    reply = assistant_step(event, entry["state"], entry["thinking"])
    return _record_reply(entry, reply)


def _allowed_fields(entry):
    return set((entry["full_case"].get("consent") or {}).get("requires_consent") or [])


# --- scoring ----------------------------------------------------------------


def _score_one(case, sub):
    from dsakit import scoring  # already on the path through dna
    return scoring.score_case(case, sub, dna.INTERVENTION)


def _conversation_summary(entry):
    """The same summary shape sim/run_conversation.py records."""
    case = entry["full_case"]
    gt = case.get("ground_truth") or {}
    asked = []
    shotgun = 0
    for row in entry["transcript"]:
        if row.get("role") != "assistant" or row.get("type") != "question":
            continue
        topics = {t for t in (row.get("topics") or []) if isinstance(t, str)}
        topics |= set(textcheck.topics_in(row.get("text") or ""))
        if "__too_many__" in topics:
            shotgun += 1
            topics.discard("__too_many__")
        asked.append(sorted(topics))
    relevant = set(gt.get("relevant_topics") or [])
    flat = sorted(set().union(*asked)) if asked else []
    must = set(gt.get("must_ask_topics") or [])
    consent_asked = []
    for row in entry["transcript"]:
        if row.get("role") == "assistant" and row.get("type") == "consent_request":
            for path in row.get("fields") or []:
                if isinstance(path, str) and path not in consent_asked:
                    consent_asked.append(path)
    return {
        "questions": len(asked),
        "unmatched_questions": sum(1 for ts in asked if not ts),
        "unnecessary_questions": sum(1 for ts in asked if ts and not (set(ts) & relevant)),
        "revealed_topics": flat,
        "must_ask_satisfied": must <= set(flat),
        "shotgun_questions": shotgun,
        "asked_topics_flat": flat,
        "consent_asked": consent_asked,
        "consent_granted": sorted(entry["granted"]),
        "consent_refused": sorted(entry["refused"]),
    }


# --- runs -------------------------------------------------------------------

_runs_cache = {}
_runs_lock = threading.Lock()


def _human_review_path():
    return os.environ.get("DNA_REVIEW_CSV") or os.path.join(RESULTS, "human_review.csv")


def runs_dir():
    return os.environ.get("DNA_RUNS_DIR") or os.path.join(RESULTS, "runs")


def _scored_files():
    try:
        names = os.listdir(runs_dir())
    except OSError:
        return []
    return sorted(n for n in names if n.endswith(".scored.json"))


def _load_scored(name):
    """Read one pre-scored file. Nothing here scores anything."""
    safe = os.path.basename(name)
    if safe != name or not safe.endswith(".scored.json"):
        raise ApiError(400, "invalid run name")
    path = os.path.join(runs_dir(), safe)
    try:
        mtime = os.stat(path).st_mtime
    except OSError:
        raise ApiError(404, "unknown run %s" % safe)
    with _runs_lock:
        cached = _runs_cache.get(path)
        if cached and cached[0] == mtime:
            return cached[1]
    try:
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
    except (OSError, ValueError) as exc:
        raise ApiError(500, "cannot read run %s (%s)" % (safe, type(exc).__name__))
    if isinstance(payload, list):
        payload = {"rows": payload}
    if not isinstance(payload, dict):
        raise ApiError(500, "run %s is not a JSON object" % safe)
    payload.setdefault("name", safe)
    payload.setdefault("rows", [])
    payload["_mtime"] = mtime
    with _runs_lock:
        _runs_cache[path] = (mtime, payload)
    return payload


def _run_summary(payload):
    """Prefer the file's own summary; fill gaps by counting rows."""
    rows = [r for r in payload.get("rows") or [] if isinstance(r, dict)]
    summary = payload.get("summary")
    summary = dict(summary) if isinstance(summary, dict) else {}
    if "cases" not in summary:
        summary["cases"] = len(rows)
    if rows and "passed" not in summary:
        summary["passed"] = sum(1 for r in rows if r.get("passed"))
    if rows and "pass_pct" not in summary:
        summary["pass_pct"] = round(100.0 * summary["passed"] / len(rows), 1)
    return summary


def _list_runs():
    out = []
    for name in _scored_files():
        try:
            payload = _load_scored(name)
        except ApiError:
            continue
        out.append({
            "name": name,
            "modified": datetime.datetime.fromtimestamp(
                payload["_mtime"], datetime.timezone.utc).isoformat(timespec="seconds"),
            "summary": _run_summary(payload),
        })
    return out


def _row_failures(row):
    raw = row.get("failures")
    if raw is None:
        raw = row.get("failure_types")
    if isinstance(raw, dict):
        raw = list(raw)
    out = []
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict) and isinstance(item.get("type"), str):
            out.append(item["type"])
    return out


def _filter_rows(rows, query):
    failure = (query.get("failure", [""])[0] or "").strip()
    journey = (query.get("journey", [""])[0] or "").strip()
    language = (query.get("language", [""])[0] or "").strip()
    split = (query.get("split", [""])[0] or "").strip()
    benign = _bool_param(query.get("benign", [""])[0])
    twin = _bool_param(query.get("twin", [""])[0])
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if failure and failure not in _row_failures(row):
            continue
        if journey and row.get("journey") != journey:
            continue
        if language and row.get("language") != language:
            continue
        if split and row.get("split") != split:
            continue
        if benign is not None and bool(row.get("benign")) is not benign:
            continue
        if twin is not None and bool(row.get("twin")) is not twin:
            continue
        out.append(row)
    return out


def _run_payload(name, query):
    payload = _load_scored(name)
    rows = payload.get("rows") or []
    rows = [r for r in rows if isinstance(r, dict)]
    kept = _filter_rows(rows, query)
    out = {k: v for k, v in payload.items() if not k.startswith("_")}
    out["rows"] = kept
    out["filtered"] = len(kept)
    out["total"] = len(rows)
    return out


# --- request handling -------------------------------------------------------


class DemoServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, handler, web_dir):
        super().__init__(address, handler)
        self.web_dir = web_dir


class Handler(BaseHTTPRequestHandler):
    server_version = "DNADemo/2.0"
    protocol_version = "HTTP/1.0"
    _status = 500

    # BaseHTTPRequestHandler logs every request to stderr; we log one line with
    # latency ourselves at the end of the dispatch instead.
    def log_message(self, fmt, *args):
        return

    def log_error(self, fmt, *args):
        sys.stderr.write("[server] " + (fmt % args) + "\n")

    # -- plumbing ----------------------------------------------------------

    def _send_bytes(self, body, content_type, status=200, html=False):
        self._status = status
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        if html:
            self.send_header("Content-Security-Policy",
                             "default-src 'self'; script-src 'self'; style-src 'self'; "
                             "img-src 'self' data:; font-src 'self'; connect-src 'self'; "
                             "base-uri 'none'; form-action 'none'")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self._send_bytes(body, "application/json; charset=utf-8", status)

    def _body(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise ApiError(400, "invalid Content-Length")
        if length > MAX_BODY:
            raise ApiError(413, "request body too large")
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return {}
        try:
            obj = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise ApiError(400, "body must be valid JSON")
        if not isinstance(obj, dict):
            raise ApiError(400, "body must be a JSON object")
        return obj

    def _static(self, path):
        if path in ("/", "/index.html"):
            rel = os.path.join("demo", "index.html")
            placeholder = True
        elif path in ("/lab", "/lab/", "/lab/index.html"):
            rel = os.path.join("lab", "index.html")
            placeholder = True
        elif path.startswith("/shared/"):
            rel = unquote(path).lstrip("/")
            placeholder = False
        elif path.startswith("/demo/"):
            rel = unquote(path).lstrip("/")
            placeholder = False
        elif path.startswith("/lab/"):
            rel = unquote(path).lstrip("/")
            placeholder = False
        else:
            raise ApiError(404, "not found")

        root = os.path.realpath(self.server.web_dir)
        full = os.path.realpath(os.path.join(root, rel))
        if full != root and not full.startswith(root + os.sep):
            raise ApiError(404, "not found")
        if not os.path.isfile(full):
            if placeholder:
                # The page builders have not landed yet; the API still works.
                self._send_bytes(PLACEHOLDER.encode("utf-8"), "text/html; charset=utf-8", 200, html=True)
                return
            raise ApiError(404, "not found")
        ext = os.path.splitext(full)[1].lower()
        types = {
            ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml",
            ".json": "application/json; charset=utf-8", ".ico": "image/x-icon",
            ".woff2": "font/woff2", ".woff": "font/woff", ".png": "image/png",
            ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
            ".webmanifest": "application/manifest+json", ".map": "application/json",
            ".txt": "text/plain; charset=utf-8",
        }
        if ext not in types:
            raise ApiError(404, "not found")
        with open(full, "rb") as fh:
            body = fh.read()
        self._send_bytes(body, types[ext], 200, html=(ext == ".html"))

    # -- dispatch ----------------------------------------------------------

    def do_GET(self):
        self._dispatch("GET")

    def do_HEAD(self):
        self._dispatch("HEAD")

    def do_POST(self):
        self._dispatch("POST")

    def do_PUT(self):
        self._dispatch("PUT")

    def do_PATCH(self):
        self._dispatch("PATCH")

    def do_DELETE(self):
        self._dispatch("DELETE")

    def do_OPTIONS(self):
        self._dispatch("OPTIONS")

    def _dispatch(self, method):
        started = time.time()
        path = urlsplit(self.path).path
        try:
            if PUBLIC and _lab_path(path):
                raise ApiError(404, "not found")
            if method in ("GET", "HEAD"):
                self._get(path)
            elif method == "POST":
                self._post(path)
            else:
                raise ApiError(405, "method not allowed")
        except ApiError as exc:
            self._send_json({"error": exc.message}, exc.status)
        except (BrokenPipeError, ConnectionResetError):
            self._status = 499
        except Exception as exc:  # unexpected: log the traceback, hide internals
            traceback.print_exc()
            try:
                self._send_json({"error": "internal error (%s)" % type(exc).__name__}, 500)
            except Exception:
                pass
        finally:
            elapsed = time.time() - started
            print("[server] %s %s %d %.2fs" % (method, path, self._status, elapsed),
                  file=sys.stderr, flush=True)

    def _lab(self):
        if PUBLIC:
            return False
        query = parse_qs(urlsplit(self.path).query)
        return _bool_param((query.get("lab", [""])[0])) is True

    # -- GET ---------------------------------------------------------------

    def _get(self, path):
        query = parse_qs(urlsplit(self.path).query)

        if path == "/api/health":
            self._send_json({
                "model": dna.llm.MODEL,
                "key_configured": bool(dna.llm.API_KEY),
                "assistant_mode": "turns" if turns is not None else "stub",
                "turns_error": _turns_error,
                "public": PUBLIC,
            })
            return

        if path == "/api/lab/cases":
            self._lab_cases(query)
            return

        m = re.match(r"^/api/lab/cases/([^/]+)/reference$", path)
        if m:
            self._lab_reference(unquote(m.group(1)))
            return

        if path == "/api/lab/runs":
            self._send_json({"runs": _list_runs()})
            return

        m = re.match(r"^/api/lab/runs/(.+)$", path)
        if m:
            self._send_json(_run_payload(unquote(m.group(1)), query))
            return

        m = re.match(r"^/api/conversations/([a-zA-Z0-9]+)/handoff$", path)
        if m:
            self._handoff(_get_entry(m.group(1)))
            return

        if path.startswith("/api/"):
            raise ApiError(404, "unknown endpoint")
        self._static(path)

    def _handoff(self, entry):
        """The brief for the last final, read under the entry lock.

        Polling only reads conversation state: it never starts a model call.
        """
        lab = self._lab()
        with entry["lock"]:
            final = entry.get("final")
            escalated = isinstance(final, dict) and bool(final.get("escalation_required"))
            status = "none"
            handoff = None
            priority = None
            if escalated:
                status = entry["state"].get("handoff_status")
                if status not in ("pending", "ready", "failed"):
                    status = ("ready" if present.valid_brief(entry["state"].get("handoff_brief"))
                              else "failed")
                if status == "ready":
                    handoff = present.handoff(entry["visible_case"], entry["state"], final,
                                              entry["language"])
                    if handoff is None:
                        status = "failed"
                    else:
                        priority = present.brief_priority(entry["state"].get("handoff_brief"))
            body = {"conversation_id": entry["id"], "pending": status == "pending",
                    "status": status, "handoff": handoff,
                    "text": present.handoff_status_text(status, entry["language"]),
                    "answer": {"priority": priority}}
            if lab:
                body["lab"] = {"handoff": entry.get("handoff_info")}
        self._send_json(body)

    def _lab_cases(self, query):
        source = (query.get("source", ["dev"])[0] or "dev").strip()
        if source not in ("dev", "sample"):
            raise ApiError(400, "source must be dev or sample")
        journey = (query.get("journey", [""])[0] or "").strip()
        language = (query.get("language", [""])[0] or "").strip()
        split = (query.get("split", [""])[0] or "").strip()
        benign = _bool_param(query.get("benign", [""])[0])
        twin = _bool_param(query.get("twin", [""])[0])
        q = (query.get("q", [""])[0] or "").strip().casefold()
        limit = _int_param(query, "limit", 50, 1, MAX_PAGE)
        offset = _int_param(query, "offset", 0, 0, 10 ** 6)

        cases = sample_cases()[0] if source == "sample" else dev_cases()[0]
        rows = []
        for case in cases:
            gt = case.get("ground_truth") or {}
            row = {
                "case_id": case.get("case_id"),
                "journey": case.get("journey"),
                "language": case.get("language"),
                "audience": case.get("audience"),
                "benign": bool(gt.get("is_benign_control")),
                "twin": bool(gt.get("twin_group")),
                "split": _split_of(case),
            }
            if source == "sample":
                row["title"] = case.get("title", "")
            if journey and row["journey"] != journey:
                continue
            if language and row["language"] != language:
                continue
            if split and row["split"] != split:
                continue
            if benign is not None and row["benign"] is not benign:
                continue
            if twin is not None and row["twin"] is not twin:
                continue
            if q and q not in (row["case_id"] or "").casefold():
                continue
            rows.append(row)
        total = len(rows)
        self._send_json({"cases": rows[offset:offset + limit], "count": len(rows[offset:offset + limit]),
                         "total": total, "limit": limit, "offset": offset, "source": source})

    def _lab_reference(self, case_id):
        _, dev_by_id = dev_cases()
        case = dev_by_id.get(case_id)
        if case is None:
            _, sample_by_id = sample_cases()
            case = sample_by_id.get(case_id)
        if case is None or "ground_truth" not in case:
            raise ApiError(404, "no reference for %s" % case_id)
        self._send_json(_reference(case))

    # -- POST --------------------------------------------------------------

    def _post(self, path):
        body = self._body()

        if path == "/api/conversations":
            self._send_json(_new_conversation(body, self._lab()))
            return

        if path in ("/api/review", "/api/lab/review"):
            self._review(body)
            return

        m = re.match(r"^/api/conversations/([a-zA-Z0-9]+)/(message|consent|finish)$", path)
        if m:
            self._conversation_action(_get_entry(m.group(1)), m.group(2), body)
            return

        m = re.match(r"^/api/lab/conversations/([a-zA-Z0-9]+)/(simulate|run-to-end|evaluate)$", path)
        if m:
            entry = _get_entry(m.group(1))
            action = m.group(2)
            if action == "simulate":
                self._simulate(entry)
            elif action == "run-to-end":
                self._run_to_end(entry)
            else:
                self._evaluate(entry)
            return

        if path.startswith("/api/"):
            raise ApiError(404, "unknown endpoint")
        raise ApiError(405, "method not allowed")

    def _conversation_action(self, entry, action, body):
        lab = self._lab()
        if action == "message":
            text = _s(body.get("text"))
            if not text:
                raise ApiError(400, "text is required")
            if len(text) > MAX_FREE_TEXT:
                raise ApiError(400, "text is longer than %d characters" % MAX_FREE_TEXT)
            with entry["lock"]:
                reason = gating.disposition(text, closed=bool(entry.get("closed")),
                                            repeated=_repeated_final(entry, text))
                if reason == "closed":
                    reply = _notice(entry, "closed")
                elif reason == "already_answered":
                    reply = _ensure_trace(copy.deepcopy(entry.get("last_reply") or {}))
                    reply["trace"]["gating"] = {"disposition": reason}
                else:
                    _append_user(entry, {"role": "user", "type": "reply", "text": text,
                                         "ts": _now()})
                    if reason == "stop":
                        entry["closed"] = True
                        reply = _notice(entry, "stop")
                        _record_reply(entry, reply)
                    else:
                        reply = _record_step(entry, {"type": "user_reply", "text": text})
                response = _conversation_body(entry, reply, lab)
            self._send_json(response)
            return

        if action == "consent":
            granted = body.get("granted") or []
            refused = body.get("refused") or []
            if not isinstance(granted, list) or not isinstance(refused, list):
                raise ApiError(400, "granted and refused must be lists")
            with entry["lock"]:
                if entry.get("closed"):
                    reply = _notice(entry, "closed")
                else:
                    allowed = _allowed_fields(entry)
                    granted = [g for g in present.resolve_fields(entry["full_case"], granted)
                               if g in allowed]
                    refused = [r for r in present.resolve_fields(entry["full_case"], refused)
                               if r in allowed]
                    granted = [g for g in granted if g not in refused]
                    signals = reveal_signals(entry["full_case"], granted)
                    entry["granted"].update(granted)
                    entry["refused"].update(refused)
                    text = body.get("text") or _consent_text(entry["language"], granted, refused)
                    _append_user(entry, {"role": "user", "type": "consent_reply", "text": text,
                                         "granted": granted, "refused": refused, "ts": _now()})
                    event = {"type": "consent_reply", "granted": granted, "refused": refused,
                             "text": text, "signals": signals}
                    reply = _record_step(entry, event)
                response = _conversation_body(entry, reply, lab)
            self._send_json(response)
            return

        if action == "finish":
            with entry["lock"]:
                if entry.get("closed"):
                    reply = _notice(entry, "closed")
                else:
                    # An explicit finish asks for a final; it never closes.
                    reply = _record_step(entry, {"type": "turn_limit"})
                response = _conversation_body(entry, reply, lab)
            self._send_json(response)
            return

        raise ApiError(404, "unknown endpoint")

    def _simulate_step(self, entry):
        """One simulated-user turn. Returns (user row, reply)."""
        if entry["source"] == "free" or entry["simulator"] is None:
            raise ApiError(400, "simulated users are only available for dev and sample cases")
        with entry["lock"]:
            if entry.get("closed"):
                raise ApiError(400, "the conversation is closed")
            last = entry.get("last_reply") or {}
            rtype = last.get("type")
            if rtype == "final":
                raise ApiError(400, "the conversation has already finished")
            if rtype == "question":
                text = entry["simulator"].answer(last.get("text") or "", last.get("topics"))
                user_row = {"role": "user", "type": "simulated", "text": text, "ts": _now()}
                event = {"type": "user_reply", "text": text}
            elif rtype == "consent_request":
                fields = last.get("fields") or []
                result = entry["simulator"].consent(fields)
                granted = result.get("granted") or []
                refused = result.get("refused") or []
                signals = reveal_signals(entry["full_case"], granted)
                entry["granted"].update(granted)
                entry["refused"].update(refused)
                text = result.get("text") or _consent_text(entry["language"], granted, refused)
                user_row = {"role": "user", "type": "consent_reply", "text": text,
                            "granted": granted, "refused": refused, "simulated": True, "ts": _now()}
                event = {"type": "consent_reply", "granted": granted, "refused": refused,
                         "text": text, "signals": signals}
            else:
                raise ApiError(400, "the assistant has not asked a question or requested consent")
            _append_user(entry, user_row)
            reply = _record_step(entry, event)
        return user_row, reply

    def _simulate(self, entry):
        user_row, reply = self._simulate_step(entry)
        body = _conversation_response(entry, reply, True)
        body["message"] = user_row
        self._send_json(body)

    def _run_to_end(self, entry):
        if entry["source"] == "free" or entry["simulator"] is None:
            raise ApiError(400, "simulated users are only available for dev and sample cases")
        messages = []
        reply = entry.get("last_reply") or {}
        for _ in range(MAX_RUN_TO_END):
            if reply.get("type") == "final":
                break
            user_row, reply = self._simulate_step(entry)
            messages.append(user_row)
        body = _conversation_response(entry, reply, True)
        body["messages"] = messages
        body["finished"] = reply.get("type") == "final"
        self._send_json(body)

    def _evaluate(self, entry):
        case = entry["full_case"]
        if "ground_truth" not in case:
            raise ApiError(400, "this conversation has no ground truth to score against")
        with entry["lock"]:
            final = entry.get("final")
            if not isinstance(final, dict):
                raise ApiError(400, "the conversation has no final answer yet")
            summary = _conversation_summary(entry)
            sub = dict(final)
        sub["case_id"] = case["case_id"]
        sub["mode"] = "multi_turn" if (summary["questions"] or summary["consent_asked"] or summary["consent_granted"] or summary["consent_refused"]) else "single_turn"
        if sub["mode"] == "multi_turn":
            sub["conversation"] = summary
        result = _score_one(case, sub)
        self._send_json({"conversation_id": entry["id"], "case_id": case["case_id"], "result": result,
                         "summary": summary, "answer": sub, "reference": _reference(case)})

    def _review(self, body):
        case_id = _s(body.get("case_id"))
        verdict = _s(body.get("verdict")).lower()
        note = _s(body.get("note"))
        run = _s(body.get("run"))
        if not case_id:
            raise ApiError(400, "case_id is required")
        if verdict not in ("ok", "unsafe", "unclear"):
            raise ApiError(400, "verdict must be ok, unsafe or unclear")
        if len(note) > 2000:
            raise ApiError(400, "note is too long")
        path = _human_review_path()
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with _runs_lock:
            exists = os.path.exists(path) and os.path.getsize(path) > 0
            with open(path, "a", encoding="utf-8", newline="") as fh:
                writer = csv.writer(fh)
                if not exists:
                    writer.writerow(["timestamp", "case_id", "run", "verdict", "note"])
                writer.writerow([_now(), case_id, run, verdict, note])
        self._send_json({"ok": True, "case_id": case_id, "verdict": verdict,
                         "review_file": os.path.basename(path)})


# --- entry point ------------------------------------------------------------


def make_server(host="127.0.0.1", port=8000, web_dir=WEB):
    return DemoServer((host, port), Handler, web_dir)


def main(argv=None):
    parser = argparse.ArgumentParser(description="DNA Digital Security Assistant web demo")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--web-dir", default=WEB, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    httpd = make_server(args.host, args.port, args.web_dir)
    url = "http://%s:%d/" % (args.host if args.host != "0.0.0.0" else "127.0.0.1", httpd.server_address[1])
    print("DNA demo: %s" % url, file=sys.stderr, flush=True)
    print("assistant: %s" % ("turns.py" if turns is not None else "stub via dna.run"), file=sys.stderr, flush=True)
    if _turns_error:
        print("turns import: %s" % _turns_error, file=sys.stderr, flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping", file=sys.stderr)
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
