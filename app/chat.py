#!/usr/bin/env python3
"""Minimal chat loop against a Featherless (OpenAI-compatible) endpoint.

Setup: copy app/.env.example to app/.env and put your key on the
FEATHERLESS_API_KEY line. Nothing else is required.

    python3 app/chat.py              # interactive: type, get a reply, repeat
    python3 app/chat.py "hello"      # one-shot

Standard library only, so it runs next to the rest of this repo.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))

DEFAULT_BASE_URL = "https://api.featherless.ai/v1"
DEFAULT_MODEL = "deepseek-ai/DeepSeek-V4.1-Flash-1017"


def load_env(path):
    """Read a .env file into os.environ without overwriting real env vars."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


load_env(os.path.join(HERE, ".env"))

BASE_URL = os.environ.get("FEATHERLESS_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
API_KEY = os.environ.get("FEATHERLESS_API_KEY", "").strip()
MODEL = os.environ.get("FEATHERLESS_MODEL", DEFAULT_MODEL)
SYSTEM_PROMPT = os.environ.get(
    "CHAT_SYSTEM_PROMPT",
    "You are a concise, helpful assistant. Keep replies short unless asked for detail.",
)
TEMPERATURE = float(os.environ.get("CHAT_TEMPERATURE", "0.7"))
MAX_HISTORY = int(os.environ.get("CHAT_MAX_MESSAGES", "40"))


TRANSIENT_CODES = frozenset((429, 500, 502, 503, 504))
RETRY_DELAYS = (1, 3)


def _post(payload, timeout):
    """POST one chat-completions payload and return the decoded response.

    `timeout` is a budget for the whole call, not a per-attempt limit: each
    attempt gets whatever is left and a transient failure is retried only if
    its backoff still fits. This bounds the time spent between attempts;
    urllib applies the value per socket operation, so an in-flight read is
    not cancelled exactly at the deadline. A timeout is never retried: it
    already spent the budget.
    """
    request = urllib.request.Request(
        BASE_URL + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + API_KEY,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    deadline = time.monotonic() + timeout
    for attempt in range(len(RETRY_DELAYS) + 1):
        last = attempt == len(RETRY_DELAYS)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError(
                "%ss timeout budget exhausted before contacting %s" % (timeout, BASE_URL))
        try:
            with urllib.request.urlopen(request, timeout=remaining) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8", "replace")[:800]
            finally:
                exc.close()
            if exc.code not in TRANSIENT_CODES or last:
                raise RuntimeError("HTTP %s from %s\n%s" % (exc.code, BASE_URL, detail))
            delay = RETRY_DELAYS[attempt]
            if exc.code == 429:
                try:
                    delay = min(5.0, max(0.0, float(exc.headers.get("Retry-After"))))
                except (AttributeError, TypeError, ValueError):
                    pass
        except (urllib.error.URLError, TimeoutError) as exc:
            reason = getattr(exc, "reason", exc)
            if isinstance(reason, TimeoutError) or last:
                raise RuntimeError("cannot reach %s: %s" % (BASE_URL, reason))
            delay = RETRY_DELAYS[attempt]
        if time.monotonic() + delay >= deadline:
            raise RuntimeError(
                "%ss timeout budget exhausted while retrying %s" % (timeout, BASE_URL))
        time.sleep(delay)


def _usage(reply):
    """The token counts the API reported, as a JSON-safe dict."""
    raw = reply.get("usage") if isinstance(reply, dict) else None
    raw = raw if isinstance(raw, dict) else {}
    out = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = raw.get(key)
        out[key] = int(value) if isinstance(value, (int, float)) else 0
    # Featherless reports its own price; keep it as a cross-check on the
    # token-rate estimate.
    if isinstance(raw.get("cost"), (int, float)):
        out["cost"] = round(float(raw["cost"]), 6)
    return out


def chat_full(messages, timeout=60, model=None, temperature=None, max_tokens=None, extra=None):
    """Send the full message list, return (assistant text, token usage).

    `max_tokens` is optional: when given it caps the completion length. Usage
    is the API's own accounting, with missing counts as 0 so callers need no
    special case. `extra` is merged into the request body for provider options
    (the engine uses it for `chat_template_kwargs`).
    """
    payload = {
        "model": model or MODEL,
        "messages": messages,
        "temperature": TEMPERATURE if temperature is None else temperature,
    }
    if max_tokens:
        payload["max_tokens"] = int(max_tokens)
    if extra:
        payload.update(extra)
    data = _post(payload, timeout)
    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise RuntimeError("unexpected response: %s" % json.dumps(data)[:800])
    return text, _usage(data)


def chat(messages, timeout=60, model=None, temperature=None, max_tokens=None, extra=None):
    """Send the full message list, return the assistant's text."""
    return chat_full(messages, timeout, model, temperature, max_tokens, extra)[0]


def trim(history):
    """Keep the system prompt plus the most recent messages."""
    if len(history) <= MAX_HISTORY + 1:
        return history
    return [history[0]] + history[-(MAX_HISTORY):]


def missing_key_hint():
    return (
        "\nNo API key found.\n"
        "Add it to %s, line 1:\n\n"
        "    FEATHERLESS_API_KEY=your-key-here\n"
        "    FEATHERLESS_MODEL=%s\n\n"
        "or export FEATHERLESS_API_KEY in your shell before running.\n"
        % (os.path.join(HERE, ".env"), DEFAULT_MODEL)
    )


def main(argv):
    if not API_KEY:
        print(missing_key_hint(), file=sys.stderr)
        return 2

    history = [{"role": "system", "content": SYSTEM_PROMPT}]

    if len(argv) > 1:
        prompt = " ".join(argv[1:])
        history.append({"role": "user", "content": prompt})
        reply = chat(history)
        print(reply)
        return 0

    print("model: %s  endpoint: %s" % (MODEL, BASE_URL))
    print("type your message; /reset clears context, /quit exits.\n")
    while True:
        try:
            line = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not line:
            continue
        if line in ("/quit", "/exit", "/q"):
            return 0
        if line == "/reset":
            history = [{"role": "system", "content": SYSTEM_PROMPT}]
            print("(context cleared)\n")
            continue

        history.append({"role": "user", "content": line})
        try:
            reply = chat(trim(history))
        except RuntimeError as exc:
            history.pop()
            print("error: %s\n" % exc, file=sys.stderr)
            continue
        history.append({"role": "assistant", "content": reply})
        print("\nassistant> " + reply + "\n")


if __name__ == "__main__":
    sys.exit(main(sys.argv))
