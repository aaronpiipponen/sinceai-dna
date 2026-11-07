# Expert handoff API

The handoff card for an escalated chat is written once by the existing expert
brief writer: the same fixed DeepSeek model, one existing call, thinking off.
There is no second priority model, no chat-model priority assignment and no
deterministic brief or provisional pickup score.

The strict scored submission is unchanged. `priority` is a demo API field
only: it is added to the returned `reply.answer` after the strict answer has
been copied, and it never appears in the stored final answer or in an
evaluator submission.

## Priority rubric

The brief writer's schema and system prompt carry `escalation_priority`, an
integer from 1 to 5. Experts take the highest number first; the scale is
separate from `risk_level`.

| Level | Meaning |
|---|---|
| 5 | immediate danger, money already moving, or an active account/device takeover |
| 4 | active compromise likely, human action needed now |
| 3 | credible threat, same-day human review |
| 2 | suspicious but contained, routine review |
| 1 | not urgent, informational or already handled |

Missing, non-integer, boolean or out-of-range values are a schema failure:
the brief is not published. The existing readable `display.handoff.priority`
urgency label is kept separately and is not replaced by the number.

## Writer budget

One call, `max_tokens` 1600, `timeout` 20 s, temperature 0, thinking off. The
cap has to fit a realistic multi-turn brief: a live reply was cut at 700
completion tokens inside `first_action`, before `language` and the closing
brace, and the writer rejected it. A reply whose reported `completion_tokens`
reach the cap is rejected as truncated even when the surviving prefix is valid
JSON; it never produces a card or a priority. There is no retry and no schema
rewrite.

`timeout` is the transport's budget for the whole `_post` call, not a hard
wall-clock deadline. Attempts share one monotonic deadline and each gets the
remaining time as `urllib`'s socket timeout, which applies per blocking socket
operation; an in-flight read is not cancelled exactly at the deadline. Twenty
seconds stays inside the demo page's roughly 40 s handoff polling window.

## Conversation response

A final answer returns immediately, before the writer finishes. If the final
escalates, the response contains no handoff card yet:

```json
{
  "reply": {
    "type": "final",
    "answer": {
      "primary_action": "change_password_and_enable_mfa",
      "escalation_required": true,
      "priority": null
    }
  },
  "display": {
    "handoff": null,
    "handoff_status": {
      "status": "pending",
      "text": "Preparing the brief…"
    }
  }
}
```

`display.handoff_status` is `pending`, `ready` or `failed` for an escalated
final. A ready card has no status message (`text: null`). A non-escalated
final has `display.handoff: null` and `display.handoff_status: null`.

When the validated brief is ready, `reply.answer.priority` is the model's
integer and `display.handoff` has the usual ready shape:
`target_label`, `situation`, `checked`, `consent`, `advice`, `priority`
(label), `labels`, `confirm` and `brief`. `checked` is the model's own
`evidence` list; when that list is empty the field stays empty rather than
being filled from the case. `situation` is the model-written summary (up to
400 characters) with the open questions appended; the structured
`user_actions` are not stitched into it. They remain in
`handoff.brief.user_actions` for the expert.

If generation fails, times out or the module/schema fails, the status is
`failed` with a short localised message. No deterministic summary is shown.

## Polling endpoint

```
GET /api/conversations/<conversation_id>/handoff
```

Returns the state of the last final:

```json
{
  "conversation_id": "…",
  "pending": false,
  "status": "ready",
  "text": null,
  "handoff": {
    "target_label": "Tietoturva-asiantuntija",
    "situation": "…",
    "checked": "…",
    "consent": "…",
    "advice": "…",
    "priority": "Toimi tänään",
    "labels": {},
    "confirm": "…",
    "brief": {
      "situation": "…",
      "first_action": "…",
      "risk": "high",
      "priority": "today",
      "escalation_priority": 5,
      "language": "fi"
    }
  },
  "answer": {"priority": 5}
}
```

`status` is one of:

- `pending` — the writer is running; `pending` is `true`, `handoff` is `null`.
- `ready` — a validated brief exists; `handoff` is present and
  `answer.priority` is 1–5.
- `failed` — generation or validation failed; `handoff` is `null` and
  `answer.priority` is `null`.
- `none` — the last final did not escalate; `handoff` is `null` and
  `answer.priority` is `null`.

`text` is the same localised pending/failed line as
`display.handoff_status.text`, so a poll can update the status item without a
second string source. It is `null` for `ready` and `none`.

The endpoint only reads conversation state. Polling never starts a model call,
so a client may poll while `pending` is true. Under `DNA_PUBLIC` the optional
`lab` object is omitted, as on every other demo endpoint. No retry endpoint is
defined: a failed brief stays failed until a later final escalates again and
starts a new writer call.

## Timing and staleness

The writer runs off the request thread; the chat final is never blocked. A
later final clears the previous brief, status and priority and bumps a
generation counter. A writer from an older final cannot publish its result
over the newer final, even if it finishes later. A non-escalated later final
leaves `answer.priority` null even when an earlier final had a ready brief.
