# -*- coding: utf-8 -*-
"""DNA Digital Security Assistant - multi-turn conversation adapter.

One job: implement `sim/PROTOCOL.md` over the same single-turn engine.

    from turns import step
    reply = step(event, state)   # one reply per harness event

The model proposes one JSON object per turn: a question, a consent request or
a final answer. Everything the user reads passes `dna.normalise()` first, and
nothing that failed validation ever leaves the adapter. Consent bookkeeping is
deterministic: a consent-gated signal is masked until the moment it is granted,
refused signals are stripped from `signals_used`, and refusals are never
re-requested.

The adapter is intentionally thin. Language, extraction and the decisive
question belong to the model; the safety floor (schema, action vocabulary,
consent accounting, fallback) belongs to `dna.py`.

Standard library only.
"""

import copy
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import dna  # noqa: E402  (also puts the SimSet root on sys.path)
from dsakit import textcheck  # noqa: E402

AVAILABLE = dna.GATED_PLACEHOLDER
DEFAULT_TURNS = 6
MAX_TOPICS = 2
# The simulator answers "one thing at a time" when the text trips more than
# three topic patterns; stay inside that line.
MAX_TEXT_TOPICS = 3
# A rejected question still becomes a final written by the model: the rules
# baseline cannot weigh what the user said in the conversation. Both reasons
# mean the proposal cannot be asked as it stands.
REJECTED_QUESTION_PREFIXES = ("question touches more than",
                              "no useful question topic left")
MAX_QUESTION_CHARS = 300
MAX_CONSENT_CHARS = 240
# The model's reasoning counts against the cap too. One cap for every turn:
# a question or consent reply must have the same room to finish its JSON as a
# final answer, or a runaway thought truncates it before the question.
FINAL_TOKENS = dna.MAX_TOKENS
# A live user waits for a reply, so a stuck call must turn into the rules
# answer instead of hanging. Thinking off measures p50 ~8 s; thinking on needs
# the room its reasoning takes. A timeout already spent the budget, so it is
# never retried inside the turn.
DEADLINE_S = {False: 20, True: 90}

ACTION_MENU = dna._action_menu()
TOPIC_MENU = dna._topic_menu()
TARGET_MENU = "\n".join("- %s: %s" % (k, v) for k, v in dna.ESCALATION_TARGETS.items())

# A last-resort answer needs no model, no rules import and no case beyond its id.
LAST_RESORT = {
    "fi": "Tämä tilanne kannattaa käydä läpi asiakaspalvelumme kanssa. Älä jaa koodeja äläkä maksa ennen kuin asia on varmistettu.",
    "en": "This situation is best handled with our customer service. Do not share codes and do not pay anything before it is confirmed.",
    "sv": "Den här situationen hanteras bäst med vår kundtjänst. Dela inga koder och betala inget innan det är bekräftat.",
}

# Said only after a refused signal was actually removed from signals_used.
UNUSED_LINE = {
    "fi": "En käyttänyt tietoja, joihin et antanut lupaa.",
    "en": "I did not use the information you did not allow.",
    "sv": "Jag använde inte uppgifterna som du inte tillät.",
}
_UNUSED_SAID = re.compile(
    r"(en käyttänyt|et antanut lupaa|did not use|didn't use|not allowed|använde inte|inte tillät)", re.I
)

SYSTEM_TURNS = (
    "You are a digital security assistant inside a telecom operator's app. The user is already "
    "identified. This is a live conversation: give one clear, proportionate next step, and ask "
    "only what changes that step.\n\n"
    "Return exactly ONE compact JSON object, no markdown, in one of these shapes:\n"
    '{{"type":"question","text":"<one question in {language}, ending with ?>","topics":["<topic id>"]}}\n'
    '{{"type":"consent_request","fields":["<consent path>"],"text":"<one line in {language}: what you will look at and why>"}}\n'
    '{{"type":"final","answer":{{"risk_level":"none|low|medium|high|critical",'
    '"urgency":"none|routine|today|immediate","primary_action":"<action id>","advice_text":"<what the user reads>",'
    '"steps":["<short imperative step>"],"escalation_required":true|false,"escalation_target":"<target id or null>",'
    '"questions_asked":["<the questions you asked>"],"question_topics":["<topic ids you asked about>"],'
    '"signals_used":["<signal path>"],"consent_requested_for":["<consent path>"],"citations":["<guidance id>"],'
    '"confidence":0.0}}}}\n\n'
    "Rules:\n"
    "1. Ask at most one thing per turn, and only if the answer changes the advice. If you already "
    "know enough, reply with final.\n"
    "2. Never ask about a topic the user has already answered or a consent that was refused. Never "
    "ask the same question twice.\n"
    "3. A question asks one thing, in {language}, and uses at most 2 topics from QUESTION TOPICS.\n"
    "4. A consent_request may list only paths from AVAILABLE WITH CONSENT. Its text is one line "
    "saying what you will look at and why.\n"
    "5. advice_text is in {language}, 20-200 words, short sentences; the primary action is clear "
    "in the first two sentences. " + dna.PLAIN_WORDS + " No questions inside advice_text.\n"
    "6. " + dna.CONSENT_RULE + " signals_used must be honest: a gated path may appear only "
    "if it is PRE-GRANTED or GRANTED. If the user refused, give useful advice without that "
    "data and never say you looked at it.\n"
    "7. " + dna.ESCALATION_RULE + "\n"
    "8. " + dna.UNTRUSTED_ARTIFACT + "\n"
    "9. " + dna.EVIDENCE_ONLY + " confidence is 0-1 and reflects how sure you are that this advice "
    "is right.\n"
    "10. " + dna.SAFE_PHRASING + "\n"
    "11. " + dna.OPERATOR_VOICE + "\n"
    "12. " + dna.AUDIENCE_STEPS + "\n"
    "13. " + dna.ARTIFACT_ONLY + "\n"
    "14. " + dna.UNCERTAIN_ANSWER + "\n"
    "15. " + dna.OUT_OF_SCOPE + "\n"
    "16. " + dna.WEIGH_GENUINE + "\n"
    "17. " + dna.SAFETY_FIRST_RULE + "\n"
    "18. " + dna.CONSENT_ABSENCE + "\n"
    "19. Stay in the user's language. When the conversation is over, reply with final now.\n"
    "20. Permission to inspect records is not evidence of who initiated an activity. If that "
    "is unknown and changes the security assessment or next step, ask it; a conditional "
    "final is not a substitute for the unanswered deciding question. " + dna.BANK_AFTER_REMOTE + "\n"
    "21. If the user has not described a concrete security situation, ask what happened "
    "instead of inventing a message or a benign verdict.\n"
    "22. Sender identity and an existing message thread cannot authenticate the current "
    "message; assess its current evidence without vouching for earlier messages.\n"
)


# --- small helpers ----------------------------------------------------------

def _lang(case):
    lang = case.get("language") if isinstance(case, dict) else None
    return lang if lang in ("fi", "en", "sv") else "fi"


def _s(value):
    return value.strip() if isinstance(value, str) else ""


def _as_list(value):
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [v.strip() for v in value if isinstance(v, str) and v.strip()]


def _clip(text, limit):
    text = " ".join(_s(text).split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _ok_lang(text, lang):
    """`None` means too short to tell; only a different language is invalid."""
    return textcheck.detect_language(text) in (None, lang)


def _set_path(signals, path, value):
    parts = path.split(".")
    cur = signals
    for part in parts[:-1]:
        nxt = cur.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[part] = nxt
        cur = nxt
    cur[parts[-1]] = value


def engine_case(state):
    """The case as the deterministic engine may see it.

    `dna.normalise()` and the rules baseline assume a gated login list is a
    list, a gated device block is a dict, and so on. The protocol's
    `"available_with_consent"` placeholder is a string, which makes
    `dna._upgrade()` raise on a breach notice and drop the answer to the rules
    fallback. So the engine gets an authorised copy with ungranted gated
    signals removed - absent is exactly what "we were not allowed to look"
    means. The prompt keeps the protocol placeholder, because the model must
    still see that the signal exists and can be asked for.
    """
    sensitive, _, granted, refused, _ = _consent_state(state)
    refused = [p for p in refused if p in sensitive]
    case = dict(state.get("case") or {})
    if refused:
        # The engine cannot see the signal, but it must know that the user
        # refused it: absence of data is not evidence that nothing happened.
        case["refused_signals"] = refused
    case = dna.authorised(case, granted=granted)
    # The user's own answers are evidence about what happened, so the
    # deterministic layer must see them too (never sent to the model here;
    # the prompt already carries FACTS). Facts keep the latest answer per
    # topic; follow-ups made without a question topic (including a fact added
    # after the final) are kept separately so they cannot be dropped.
    replies = [v for v in (state.get("facts") or {}).values()
               if isinstance(v, str) and v.strip()]
    replies += [v for v in (state.get("followups") or [])
                if isinstance(v, str) and v.strip() and v not in replies]
    if replies:
        case["user_replies"] = " ".join(replies)
    return case


def _consent_state(state):
    consent = (state.get("case") or {}).get("consent") or {}
    sensitive = [p for p in consent.get("requires_consent") or [] if isinstance(p, str)]
    pre = [p for p in consent.get("pre_granted") or [] if isinstance(p, str)]
    refused = list(state.get("refused") or [])
    # A refusal beats a grant when a reply carries both.
    granted = [p for p in state.get("granted") or [] if p not in refused]
    available = [p for p in sensitive if p not in pre and p not in granted and p not in refused]
    return sensitive, pre, granted, refused, available


# --- state ------------------------------------------------------------------

def _initial_case(event_case):
    """The visible case, with every ungranted consent-gated signal masked.

    The harness already masks them, but the web demo may hand us a full case.
    `dna.authorised()` is the one consent boundary, shared with the
    single-turn engine, so masking here cannot drift from prompt and rules.
    """
    return dna.visible(dna.authorised(event_case or {}, masked=True))


def _reset(event, state):
    case = _initial_case(event.get("case"))
    # An explicit None is the live, unbounded conversation; an omitted field
    # is the simulator protocol's default budget.
    raw_turns = event.get("max_assistant_turns", DEFAULT_TURNS)
    max_turns = None if raw_turns is None else int(raw_turns)
    state.clear()
    state.update({
        "conversation_id": event.get("conversation_id"),
        "case": case,
        "facts": {},
        "turns": 0,
        "max_turns": max_turns,
        "granted": [],
        "refused": [],
        "asked_topics": [],
        "asked_questions": [],
        "consent_asked": [],
        "last_topics": [],
        "followups": [],
        "history": [{"role": "user", "type": "opening",
                     "content": _s(case.get("opening_message"))}],
        "force_final": False,
    })


def _absorb(event, state):
    """Fold one user or consent reply into the conversation state."""
    etype = event.get("type")
    if etype == "user_reply":
        text = _s(event.get("text"))
        topics = state.get("last_topics") or []
        for topic in topics:
            state["facts"][topic] = text
        if text and not topics:
            # A fact added after the final, or an answer to a topicless
            # clarification: no question topic owns it, but the rules must
            # still see what the user said.
            state["followups"].append(text)
        state["history"].append({"role": "user", "type": "user_reply", "content": text})
        return

    granted = _as_list(event.get("granted"))
    refused = _as_list(event.get("refused"))
    signals = event.get("signals") if isinstance(event.get("signals"), dict) else {}
    target = (state.get("case") or {}).get("signals")
    if isinstance(target, dict):
        for path in granted:
            if path in signals:
                _set_path(target, path, copy.deepcopy(signals[path]))
    state["granted"] = list(dict.fromkeys(list(state.get("granted") or []) + granted))
    state["refused"] = list(dict.fromkeys(list(state.get("refused") or []) + refused))
    state["history"].append({"role": "user", "type": "consent_reply",
                             "content": _s(event.get("text")) or "(consent answer)"})


# --- prompt -----------------------------------------------------------------

def prompt(case, state, force=False, turns_left=None):
    """One compact conversation prompt, built from dna's own menus.

    Order is for the provider's prefix cache: static rules and menus, then the
    retrieved passages, then everything that changes per case or per turn. No
    case id, conversation id or other random value reaches the model.
    """
    lang = _lang(case)
    _, pre, granted, refused, available = _consent_state(state)
    unbounded = state.get("max_turns") is None

    lines = []
    history = state.get("history") or []
    # The simulator's finite budget keeps its short window. A live unbounded
    # chat keeps the real history, and never clips away part of a user reply.
    for msg in (history if unbounded else history[-12:]):
        role = "USER" if msg.get("role") == "user" else "ASSISTANT"
        content = msg.get("content")
        if not (unbounded and role == "USER"):
            content = _clip(content, 400)
        content = content if isinstance(content, str) else ""
        if msg.get("type") == "consent_reply":
            # Permission is not a fact about what happened or who started it.
            lines.append("USER (consent reply — permission only, not evidence "
                         "of what happened): %s" % content)
        else:
            lines.append("%s: %s" % (role, content))
    transcript = "\n".join(lines) if lines else "(the user has only sent the opening message)"

    facts = state.get("facts") or {}
    asked = state.get("asked_topics") or []
    # The model sees the same authorised view as the engine: granted values
    # are present, every other gated signal is only the protocol placeholder.
    view = dna.authorised(case, granted=granted, masked=True)
    body_case = dict(dna.visible(view))
    body_case.pop("case_id", None)
    body = (
        "ACTIONS\n%s\n\nQUESTION TOPICS\n%s\n\nESCALATION TARGETS\n%s\n\n"
        "GUIDANCE (cite only these ids)\n%s\n\n"
        "CASE\n%s\n\nCONVERSATION\n%s\n\n"
        "CONSENT (a grant is permission only: it does not say what happened or who started it; "
        "ask any still-unknown deciding fact before a final)\n"
        "pre-granted: %s\ngranted: %s\nrefused (never re-request, never use): %s\navailable with consent (ask only if it changes the advice): %s\n\n"
        "FACTS THE USER HAS ALREADY GIVEN\n%s\nTOPICS ALREADY ASKED: %s\nTURNS LEFT: %s\n%s" % (
            ACTION_MENU,
            TOPIC_MENU,
            TARGET_MENU,
            dna._guidance_menu(view),
            json.dumps(body_case, ensure_ascii=False),
            transcript,
            json.dumps(pre, ensure_ascii=False),
            json.dumps(granted, ensure_ascii=False),
            json.dumps(refused, ensure_ascii=False),
            json.dumps(available, ensure_ascii=False),
            json.dumps(facts, ensure_ascii=False),
            json.dumps(asked, ensure_ascii=False),
            "unbounded" if turns_left is None else turns_left,
            "Reply with type final now, using what you already know."
            if force else "If you already know enough, reply with type final.",
        )
    )
    return [
        {"role": "system", "content": SYSTEM_TURNS.format(language=lang)},
        {"role": "user", "content": body},
    ]


# --- reply validation -------------------------------------------------------

def _fired(trace, rule, before=None, after=None):
    trace["rules"].append({"rule": rule, "from": before, "to": after})


def _question(case, state, raw, trace):
    """Validate a question reply. Returns the reply or None (-> final)."""
    lang = _lang(case)
    text = _clip(raw.get("text"), MAX_QUESTION_CHARS)
    if not text:
        trace["error"] = "question without text"
        return None
    if not _ok_lang(text, lang):
        trace["error"] = "question in the wrong language"
        return None

    detected = set(textcheck.topics_in(text))
    if len(detected) > MAX_TEXT_TOPICS:
        # The simulated user answers "ask one thing at a time" and reveals
        # nothing, so a shotgun question is worse than going to the final.
        _fired(trace, "shotgun_question", sorted(detected), None)
        trace["error"] = "question touches more than %d topics" % MAX_TEXT_TOPICS
        return None

    proposed = _as_list(raw.get("topics"))
    # An explicit topics:[] is a deliberate generic clarification ("what
    # happened?"). It must not be inferred from trimming unknown or already
    # answered topics down to nothing.
    intentional = raw.get("topics") == [] and not detected
    unknown = [t for t in proposed if t not in dna.TOPICS]
    if unknown:
        _fired(trace, "question_topic_unknown", unknown, None)
    topics = [t for t in proposed if t in dna.TOPICS]
    if len(topics) > MAX_TOPICS:
        _fired(trace, "question_topics_trimmed", topics, topics[:MAX_TOPICS])
        topics = topics[:MAX_TOPICS]
    if not topics:
        topics = sorted(detected)
        if topics:
            _fired(trace, "question_topics_from_text", None, topics)
        elif intentional:
            _fired(trace, "question_topicless_clarification", None, None)

    revealed = [t for t in topics if t in (state.get("facts") or {})]
    if revealed:
        _fired(trace, "reasked_topic_dropped", revealed, None)
        topics = [t for t in topics if t not in revealed]
    topics = list(dict.fromkeys(topics))[:MAX_TOPICS]
    if not topics and not intentional:
        trace["error"] = "no useful question topic left"
        return None

    if not text.endswith("?"):
        text = text + "?"
        _fired(trace, "question_mark_added", None, text)

    state["last_topics"] = topics
    state["asked_topics"] = list(dict.fromkeys(list(state.get("asked_topics") or []) + topics))
    state["asked_questions"].append(text)
    state["history"].append({"role": "assistant", "content": text})
    return {"type": "question", "text": text, "topics": topics, "trace": trace}


def _consent_request(state, raw, trace):
    """Validate a consent reply. Returns the reply or None (-> final)."""
    case = state["case"]
    lang = _lang(case)
    text = _clip(raw.get("text"), MAX_CONSENT_CHARS)
    if not text:
        trace["error"] = "consent request without text"
        return None
    if not _ok_lang(text, lang):
        trace["error"] = "consent request in the wrong language"
        return None

    _, _, _, _, available = _consent_state(state)
    proposed = _as_list(raw.get("fields"))
    unknown = [f for f in proposed if f not in available]
    if unknown:
        _fired(trace, "consent_field_not_available", unknown, None)
    fields = list(dict.fromkeys(f for f in proposed if f in available))
    if not fields:
        trace["error"] = "no available consent field in request"
        return None

    state["consent_asked"] = list(dict.fromkeys(list(state.get("consent_asked") or []) + fields))
    state["history"].append({"role": "assistant", "content": text})
    return {"type": "consent_request", "fields": fields, "text": text, "trace": trace}


# --- final answer -----------------------------------------------------------

def _bookkeep(case, state, answer, trace, raw_answer=None):
    """Attach conversation facts and report signals the user did not allow.

    The answer's signals_used were already filtered by dna.normalise(); the raw
    proposal is only consulted to name what was removed, so a refused signal
    still gets its trace line and the honest "did not use" note.
    """
    sensitive, pre, granted, refused, _ = _consent_state(state)
    answer["case_id"] = case.get("case_id") or answer.get("case_id")
    answer["question_topics"] = list(dict.fromkeys(state.get("asked_topics") or []))
    answer["questions_asked"] = list(state.get("asked_questions") or [])
    answer["consent_requested_for"] = [
        f for f in dict.fromkeys(state.get("consent_asked") or [])
        if f in sensitive and f not in pre
    ]

    allowed = (set(pre) | set(granted)) - set(refused)
    proposed = [s for s in _as_list((raw_answer or {}).get("signals_used"))
                if s in dna.SIGNALS]
    removed_refused, removed_other = [], []
    for path in dict.fromkeys(proposed):
        if path in sensitive and path not in allowed:
            (removed_refused if path in refused else removed_other).append(path)
    for path in removed_refused:
        _fired(trace, "consent_refused_signal_removed", path, None)
    for path in removed_other:
        _fired(trace, "consent_not_granted_signal_removed", path, None)
    answer["signals_used"] = [s for s in _as_list(answer.get("signals_used"))
                              if s in dna.SIGNALS]

    if removed_refused:
        advice = _s(answer.get("advice_text"))
        if len(textcheck.words(advice)) <= 160 and not _UNUSED_SAID.search(advice):
            line = UNUSED_LINE.get(_lang(case), UNUSED_LINE["en"])
            answer["advice_text"] = (advice.rstrip() + " " + line).strip()
            _fired(trace, "consent_note_added", None, line)


def _last_resort(state, trace):
    case = state.get("case") or {}
    answer = {
        "case_id": case.get("case_id") or "unknown",
        "risk_level": "medium",
        "urgency": "today",
        "primary_action": "escalate_to_human",
        "advice_text": LAST_RESORT.get(_lang(case), LAST_RESORT["en"]),
        "steps": [],
        "escalation_required": True,
        "escalation_target": "operator_support_agent",
        "questions_asked": [],
        "question_topics": [],
        "signals_used": [],
        "consent_requested_for": [],
        "citations": [],
        "confidence": 0.3,
        "abstained": False,
    }
    trace["fallback"] = True
    return {"type": "final", "answer": answer, "trace": trace, "fallback": True}


def _final(state, trace, raw_answer, reason):
    """Normalise a final answer (or fall back) and attach the trace."""
    case = engine_case(state)
    _, _, granted, _, _ = _consent_state(state)
    # A follow-up message after the final answer must not overwrite the
    # fact recorded for the previous question's topics.
    state["last_topics"] = []
    if raw_answer is None:
        try:
            answer = dna.fallback(case, reason or "model reply unusable", granted=granted)
        except Exception:
            return _last_resort(state, trace)
        trace["fallback"] = True
        trace["error"] = trace.get("error") or reason
    else:
        answer = dna.normalise(case, raw_answer, trace["rules"], granted=granted)
        reason = dna.fallback_reason(trace["rules"])
        if reason is not None:
            trace["fallback"] = True
            trace["error"] = trace.get("error") or reason
    try:
        _bookkeep(case, state, answer, trace, raw_answer)
    except Exception as exc:  # never return a half-built answer
        trace["error"] = "%s: %s" % (type(exc).__name__, str(exc)[:160])
        return _last_resort(state, trace)
    state["history"].append({"role": "assistant", "content": _s(answer.get("advice_text"))})
    return {"type": "final", "answer": answer, "trace": trace,
            "fallback": bool(trace.get("fallback"))}


# --- turn -------------------------------------------------------------------

def _answer_from(raw):
    """The answer object inside a final reply, or None."""
    if isinstance(raw.get("answer"), dict):
        return raw["answer"]
    if "primary_action" in raw or "advice_text" in raw:
        return raw
    return None


def _safety_first(case, state, trace):
    """A first-turn safety message before any data request or question.

    A consent card on a surveillance case asks for data before the user has a
    safe plan. This replaces such a first reply with the same safety steps the
    final answer carries, in the user's language.
    """
    lang = _lang(case)
    text = dna.SAFETY_FIRST_TEXT.get(lang) or dna.SAFETY_FIRST_TEXT["en"]
    state["last_topics"] = ["user_safety"]
    state["asked_topics"] = list(dict.fromkeys(
        list(state.get("asked_topics") or []) + ["user_safety"]))
    state["asked_questions"].append(text)
    state["history"].append({"role": "assistant", "content": text})
    _fired(trace, "safety_first", None, lang)
    return {"type": "question", "text": text, "topics": ["user_safety"], "trace": trace}


def _nonfinal(case, state, raw, trace):
    rtype = raw.get("type")
    if rtype not in ("question", "consent_request"):
        # Tolerate a model that omits "type" but names the fields.
        if "fields" in raw:
            rtype = "consent_request"
        elif "text" in raw or "topics" in raw:
            rtype = "question"
        else:
            return None
    if rtype == "question":
        return _question(case, state, raw, trace)
    return _consent_request(state, raw, trace)


def _turn(state, trace, thinking=None):
    case = state.get("case") or {}
    max_turns = state.get("max_turns")
    turns_left = (None if max_turns is None
                  else max(0, int(max_turns) - int(state.get("turns") or 0)))
    force = bool(state.get("force_final")) or (turns_left is not None and turns_left <= 0)
    messages = prompt(case, state, force=force, turns_left=turns_left)

    try:
        text, meta = dna.call_model(messages, temperature=0,
                                    timeout=DEADLINE_S[dna.thinking_flag(thinking)],
                                    max_tokens=FINAL_TOKENS,
                                    thinking=thinking)
        trace["raw_text"] = text
        trace["meta"] = meta
    except Exception as exc:  # network, HTTP, timeout, cache miss
        reason = "%s: %s" % (type(exc).__name__, str(exc)[:160])
        return _final(state, trace, None, reason)

    if meta.get("truncated"):
        # Used before thinking-off retry in call_model; still refused here
        # because a cut reply can lose the step the user needs.
        return _final(state, trace, None, "reply hit the output cap")

    raw = dna._parse(text)
    if not isinstance(raw, dict):
        return _final(state, trace, None, "no JSON object in reply")

    if not force:
        # A surveillance case must not open with a consent card or a generic
        # question: the first turn is a safety message instead.
        rtype = raw.get("type")
        if rtype not in ("question", "consent_request"):
            rtype = ("consent_request" if "fields" in raw
                     else "question" if ("text" in raw or "topics" in raw) else None)
        if (rtype in ("question", "consent_request")
                and int(state.get("turns") or 0) == 0
                and dna.safety_cue(case.get("opening_message") or "")):
            state["turns"] = int(state.get("turns") or 0) + 1
            return _safety_first(case, state, trace)
        reply = _nonfinal(case, state, raw, trace)
        if reply is not None:
            state["turns"] = int(state.get("turns") or 0) + 1
            return reply
        error = trace.get("error") or ""
        if error.startswith(REJECTED_QUESTION_PREFIXES):
            # The rule that rejected the question is already in trace["rules"].
            # Ask for a final answer with the facts already given instead of
            # dropping to the rules baseline, which cannot weigh what the user
            # said in the conversation. force_final makes this recursion
            # single-shot: the forced turn cannot propose another question.
            trace["error"] = None
            trace["raw_text"] = None
            state["force_final"] = True
            return _turn(state, trace, thinking=thinking)

    return _final(state, trace, _answer_from(raw), trace.get("error") or "model did not give a final answer")


# --- entry point ------------------------------------------------------------

def step(event, state, thinking=None):
    """One harness event in, one protocol reply out. Never raises.

    `thinking` overrides DNA_THINKING for this conversation; the simulator
    keeps calling step(event, state) and uses the environment default.
    """
    trace = {"raw_text": None, "rules": [], "meta": None, "fallback": False, "error": None}
    if not isinstance(state, dict):
        state = {}
    if not isinstance(event, dict):
        trace["error"] = "event is not a JSON object"
        return _last_resort(state, trace)

    etype = event.get("type")
    try:
        if etype == "start" or "case" not in state:
            if etype != "start":
                trace["error"] = "event before start"
                return _last_resort(state, trace)
            _reset(event, state)
        elif etype == "turn_limit":
            state["force_final"] = True
        elif etype in ("user_reply", "consent_reply"):
            # A real follow-up clears a final forced by a previous turn, so
            # the final answer is not terminal.
            state["force_final"] = False
            _absorb(event, state)
        else:
            state["force_final"] = True
        return _turn(state, trace, thinking=thinking)
    except Exception as exc:  # a bad state must still end with a valid answer
        trace["error"] = "%s: %s" % (type(exc).__name__, str(exc)[:160])
        try:
            return _final(state, trace, None, trace["error"])
        except Exception:
            return _last_resort(state, trace)
