# -*- coding: utf-8 -*-
"""Conversation lifecycle gate for the demo server.

Pure and deterministic. It never calls a model, never judges tone, never
blocks gibberish and never flags a person: the only close it recognises is an
unambiguous, whole-message request to end the chat. Everything else answers.

    disposition(text, closed=entry.get("closed"), repeated=is_repeat(...))
    notice_reply(entry["language"], "stop" | "closed")

Standard library only.
"""

import re

DISPOSITIONS = ("answer", "stop", "already_answered", "closed")
# Exact whole-message requests. Matching the whole text keeps "stop the
# transfer", "can I stop this?" and "how do I close the chat?" answered.
_STOP = {
    "stop", "stop now", "please stop", "stop please", "stop talking",
    "stop chat", "stop the chat", "stop this chat", "stop this conversation",
    "end now", "end chat", "end the chat", "end this chat",
    "end this conversation", "close chat", "close the chat", "close this chat",
    "close this conversation", "quit", "exit chat", "exit the chat",
    "lopeta", "lopeta nyt", "lopeta heti", "lopeta kiitos", "kiitos lopeta",
    "lopeta chat", "lopeta keskustelu", "lopeta tämä keskustelu",
    "sulje chat", "sulje keskustelu", "sulje tämä keskustelu", "lopetetaan",
    "sluta", "sluta nu", "stopp", "sluta prata", "sluta chatta", "avsluta",
    "avsluta nu", "avsluta chatten", "avsluta konversationen",
    "stäng chatten", "stäng konversationen",
}

_QUOTES = "\"'“”‘’«»"

_NOTICE = {
    "stop": {
        "fi": "Kiitos yhteydenotosta. Keskustelu on nyt suljettu. Jos tarvitset "
              "apua myöhemmin, aloita uusi keskustelu.",
        "en": "Thank you for getting in touch. This chat is now closed. If you "
              "need help later, start a new chat.",
        "sv": "Tack för att du hörde av dig. Chatten är nu stängd. Om du behöver "
              "hjälp senare kan du starta en ny chatt.",
    },
    "closed": {
        "fi": "Tämä keskustelu on suljettu. Aloita uusi keskustelu, jos haluat jatkaa.",
        "en": "This chat is closed. Start a new chat if you want to continue.",
        "sv": "Den här chatten är stängd. Starta en ny chatt om du vill fortsätta.",
    },
}

def _s(value):
    return value.strip() if isinstance(value, str) else ""


def _plain(text):
    """Casefold and collapse punctuation so "Stop!" equals "stop"."""
    return " ".join(re.sub(r"[\W_]+", " ", _s(text), flags=re.UNICODE).casefold().split())

def _quoted(text):
    """True for a whole quoted command such as '"stop"' or "'lopeta'." """
    plain = _s(text).rstrip(" .!?…")
    return len(plain) >= 2 and plain[0] in _QUOTES and plain[-1] in _QUOTES


def stop_requested(text):
    """Only an explicit, unquoted, whole-message request to end the chat."""
    raw = _s(text)
    return bool(raw) and "?" not in raw and not _quoted(raw) and _plain(raw) in _STOP


def is_repeat(text, last_text=None, last_reply_type=None, context=None,
              final_context=None):
    """The exact same user message immediately after the final it produced."""
    return bool(
        _s(text)
        and _s(text) == _s(last_text)
        and last_reply_type == "final"
        and context is not None
        and context == final_context
    )

def disposition(text, closed=False, repeated=False):
    if closed:
        return "closed"
    if stop_requested(text):
        return "stop"
    if repeated:
        return "already_answered"
    return "answer"


def notice_text(language, reason="closed"):
    table = _NOTICE.get(reason) or _NOTICE["closed"]
    return table.get(language) or table["en"]


def notice_reply(language, reason="closed"):
    """A deterministic courtesy notice. Never advice, never a verdict."""
    return {"type": "notice", "text": notice_text(language, reason)}
