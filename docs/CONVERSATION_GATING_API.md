# Conversation gating API

Every server chat (`source=free`, `source=sample`, `source=dev`) is gated per
message. The gate is deterministic: no model classifier, no profanity filter,
no gibberish check, no per-user flag and no IP rate limit. Its dispositions are
internal (`answer`, `stop`, `already_answered`, `closed`) and never appear in a
user-facing string.

## Normal answers

An ordinary message, consent answer or explicit `finish` produces a
`reply.type` of `question`, `consent_request` or `final`. A `finish` asks for a
final and does not close the conversation.

Server chats use no six-question budget. A start emits
`max_assistant_turns: null`, which the shared turn loop treats as unbounded.
Consent and new facts after a final are accepted, may produce further
questions, and update the advice, risk and escalation. The external simulator
uses a six-turn default: without an explicit `max_assistant_turns`,
`turns.step` applies that default, and an explicit finite limit forces a
final.

## Notice: explicit stop or a closed chat

When the user unambiguously asks the whole message to end the chat, or sends
anything to a closed conversation, the response is a courtesy notice:

```json
{
  "conversation_id": "…",
  "language": "fi",
  "thinking": false,
  "closed": true,
  "reply": {
    "type": "notice",
    "text": "Kiitos yhteydenotosta. Keskustelu on nyt suljettu. …"
  },
  "display": {
    "attachment": null,
    "question": null,
    "quick_replies": null,
    "consent": null,
    "answer": null,
    "handoff": null,
    "visibility": { "…": "…" },
    "notice": { "text": "Kiitos yhteydenotosta. Keskustelu on nyt suljettu. …" }
  }
}
```

Contract:

- `reply.type` is `"notice"`; `reply.text` is a deterministic line in the
  conversation language (`fi`, `en` or `sv`).
- `body.closed` is `true`. The key is omitted while the chat is open; treat an
  absent key as `false`.
- `display.notice` carries `{ "text": <same localised text> }`. It is present
  only for a notice.
- `display.answer` and `display.handoff` are `null`. A notice is never a
  `no_action_needed` answer and never a safety verdict. Do not render it as an
  answer card or an escalation.
- Do not treat it as `question` or `error` to fit another component.
  The demo renders it as a neutral assistant bubble with a "Start a new chat"
  button, disables the composer, and starts a new conversation from that
  button. `app/web/shared/thread.js` holds the `notice` item and
  `app/web/demo/demo.js` handles the reply type.

`POST /api/conversations/<id>/message`, `/consent` and `/finish` all return this
shape once the chat is closed. A stopped conversation cannot be reopened:
even `"resume"` gets the closed notice. Continuing requires a new
`POST /api/conversations`.

On a stop or closed request the server does not change consent and does not
call the chat model or the expert-brief writer. An expert brief already in
flight for an earlier final may finish, but its result is not shown on a
notice.

### What counts as a stop

Only an exact, unquoted, whole-message request such as `stop`, `please stop`,
`stop the chat`, `lopeta`, `lopeta keskustelu`, `sluta` or `avsluta chatten`.
Everything ambiguous answers normally. In particular these do **not** close:
`stop the transfer`, `can I stop this chat?`, `"stop"` (a quoted command), and
any text inside `attachment` (the assistant never treats attachment text as an
instruction).

## Repeated message after a final

An exact repeat of the user message that produced the final in effect, with no
new user text and the same consent, returns that final without a new
chat-model call, a new transcript row or a new brief writer. This also holds
for concurrent duplicate HTTP requests: one model call, one recorded final,
one brief. A repeated word after a new fact or a consent change is answered
normally instead of reusing the final.

## Lab trace

`?lab=1` adds the usual `lab.trace`. A gated reply sets the internal
disposition there only:

```json
"lab": { "trace": { "gating": { "disposition": "stop" } }, "turn": 2 }
```

`already_answered` and `closed` are reported the same way. These enum values
are lab data, never display text.
