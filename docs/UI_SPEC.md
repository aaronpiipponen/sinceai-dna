# UI spec: demo (`/`) and lab (`/lab`)

Two pages are served by `app/server.py`: the customer demo at `/` and the
workbench at `/lab`. The reference look is `/mockups/demo.html`, with its
captures `/mockups/demo_mobile.png` and `/mockups/demo_desktop.png`. Match the
mockup's tokens, spacing and components, and improve on it where this spec
says so.

---

## 1. Two pages, two audiences

| Page | Audience | Purpose |
|---|---|---|
| `/` demo | DNA judges, end users | Looks like a feature inside the operator app. Mobile first, usable on desktop. |
| `/lab` | operator | Pick cases, run conversations, compare with the reference, read traces, browse scored runs, record human review. |

No link from `/` to `/lab` in the UI. Both are served by `app/server.py`.

## 2. Global rules

- **Font:** bundle Inter (OFL) as woff2 in `app/web/shared/fonts/` with
  `@font-face`; fallback `system-ui, sans-serif`. No CDN.
- **Icons:** inline SVG only, no emoji (the server has no emoji font).
- **Language:** every string the end user sees is in the conversation language
  (fi / en / sv). UI chrome strings live in one i18n table in the frontend;
  content labels (action headline, urgency, signal names, consent texts,
  "why" lines, handoff summary) come from the server's `display` block (§5).
  The demo never shows: case ids, journey ids, signal paths, guidance ids,
  topic ids, risk enums, confidence numbers.
- **Accessibility:** tap targets ≥ 44 px, visible focus, `aria-live` on the
  thread, colour is never the only signal (urgency also has text).
- **No inline styles or scripts** (CSP `default-src 'self'`).
- **Scrollbars:** one shared style from `shared/tokens.css`: a 12 px rounded
  neutral thumb on a transparent track, accent colour on hover, and Firefox's
  thin `scrollbar-color` equivalent. It applies to every scroll container in
  the demo and the lab, including growing textareas.
- **Static assets:** `app/web/shared/` (fonts, tokens.css, icons.js),
  `app/web/demo/` (index.html, demo.css, demo.js), `app/web/lab/`
  (index.html, lab.css, lab.js).

## 3. Demo page `/`

### Layout

- **Mobile (< 1024 px):** app bar (wordmark "DNA", title, prototype label,
  language menu, and, once a conversation has started, the "New chat" button)
  · thread · fixed composer at the bottom (respects
  `env(safe-area-inset-bottom)`). Single column, max width 720 px.
- **Desktop (≥ 1024 px):** same thread centred (max 720 px) plus a sticky
  right card **"What I can see"** (340 px). Composer aligned to the thread
  column, not the viewport.
- Title: fi "Tietoturva-avustaja", en "Security assistant", sv
  "Säkerhetsassistent". Prototype label: fi "Prototyyppi", en "Prototype", sv
  "Prototyp" — the word only, no "not official advice" suffix in the chrome.

### Start screen (before the first message)

Top to bottom: audience switch with the Examples button, the careful-check
toggle, the assistant greeting bubble, the collapsed attachment disclosure,
and the composer pinned at the bottom. The controls sit above the greeting so
the first thing a new chat shows is how to shape the answer, not an empty
thread.

Settings, chat and composer share one white rounded panel, inset from the
grey page with a strong border on all four sides. On the start screen the
settings are the panel header, separated from the thread by a thin divider;
the attachment disclosure is docked at the bottom of the thread and the
composer sits inside the panel's bottom edge. Until the first message the
thread is docked against the bottom of the scroll area, just above the
attachment disclosure; after the first message the controls and the
disclosure collapse, the divider disappears, and the thread starts at the top
and scrolls normally. A forwarded artifact is rendered as an attachment
bubble directly under the user's first bubble, with the normal item gap
removed, so it reads as part of that message.

- Greeting bubble from the assistant in the selected language: what it helps
  with, in one sentence.
- **Audience switch:** "Personal" / "Business" (segmented control). Business
  uses the SMB demo profile and business wording.
- **Examples menu:** an "Examples" button next to the audience switch opens a
  menu with the five journey cases, short human titles in the current
  language (e.g. en "Text from my bank", "I clicked a link", "A call from
  'support'", "No signal after an eSIM message", "Supplier changed bank
  details"). Selecting one starts the matching sample case from
  `five_journeys.jsonl`. The case's forwarded artifact appears as the
  attachment bubble and its opening message as the user's first bubble. The
  menu is a disclosure inside the start panel, not an overlay, so it never
  clips against the scrolling thread.
- **Careful-check toggle:** default off. en "Check more carefully", fi
  "Tarkista tarkemmin", sv "Kontrollera noggrannare". Explain that each reply
  can take 25–60 seconds. Available only before starting; a new conversation
  resets it to off. Every start sends the explicit boolean `thinking`, and
  the response echoes it for the whole conversation. Never show reasoning.
- **Inline attachment form (optional, collapsed on every new chat):** a
  disclosure row labelled en "Describe the message or call in more detail",
  fi "Kuvaile viestiä/puhelua tarkemmin", sv "Beskriv meddelandet eller
  samtalet närmare", with an optional hint. It expands smoothly in place to
  type (SMS / email / call / letter), sender and text. The collapsed row and
  the expanded card use the same grey as the careful-check row, and hovering
  highlights the whole row edge to edge, inside the card's rounded corners,
  not just the title. No paperclip button, no sheet,
  no separate "Attach" step. A collapsed form never attaches, even if it
  holds a draft; blank text also means no artifact. The attached item becomes
  `signals.artifact` (untrusted) and shows as an attachment bubble. Without
  it, free text has no artifact.
- **Free text:** the composer sits inside the bottom of the panel. It grows
  with its message up to six lines, then scrolls.
- Language menu: fi / en / sv. Default from `navigator.language`, else en.
  Changing language before starting changes the conversation language;
  after starting it is locked (show the current one).

### Thread components

| Component | Content | Notes |
|---|---|---|
| User bubble | user text | right, accent |
| Attachment bubble | type icon, sender, time if known, body; link text not clickable; chips for link check / call warning | right, under the user's first bubble. Link check: `display.attachment.checks[]` with tone `warn`/`ok`/`unknown`. |
| Assistant question | question text | left |
| Quick replies | `display.quick_replies` (localised "Yes" / "No" / "Not sure") | chips under the question; tapping sends that text. Hidden once answered. |
| Consent card | title, one-line purpose, Allow / Don't allow, fine print "You'll still get advice if you say no" | Fields from `display.consent`. After answering, collapses to a one-line receipt ("✓ You allowed: …" / "You said no to: …"). |
| Checking state | three-dot typing indicator + elapsed seconds after 3 s ("Checking… 6 s"); careful mode uses "Checking carefully…" (fi "Tarkistan tarkemmin…", sv "Kontrollerar noggrannare…") | One per pending request, including follow-ups, consent and retries. Composer disabled while pending. |
| Answer card | urgency label (text + colour), headline = action in user language, one-line reason, numbered steps, expert button if escalated, "Why this advice?" expander | From `display.answer`. Left border colour by urgency: immediate/today = act-now orange, routine = neutral, none = safe green. Benign answers say so plainly in the headline ("This looks genuine – no action needed"). |
| Why expander | 2–4 plain bullets (facts used, checks used, user answers that mattered), guidance title(s), the note "assistant guidance, not official advice" | `display.answer.why` |
| Handoff card | "What the expert receives": the one model-written situation summary, checked, consent, advice given, priority, and the numeric queue priority when the brief has one | Shown when the user taps the expert button, from `display.handoff` once the model brief is ready. The situation is the brief's own summary with the open questions appended; structured `brief.user_actions` stay in the payload for the expert and are not repeated in the prose. While it is pending the same place shows "Preparing the brief…" with a subtle indicator; a failed brief shows the honest status line and no card. No real handoff happens; say "(demo)" in small text. |
| Notice | `display.notice.text` | Closed chat: a neutral assistant bubble, not an answer card, with a "Start a new chat" button. The composer is disabled with "This chat has ended". |
| Follow-up | composer stays active after the final answer | A follow-up continues the same conversation; a new answer card replaces nothing, it appends. |
| Error | friendly line + "Try again" | Never show stack traces. If the server falls back to rules, the user sees a normal answer. |

Once a conversation has started, the app bar shows **"New chat"** (fi "Uusi
keskustelu", en "New chat", sv "Ny chatt"): a new-chat icon plus the short
label. At 420 px and below it is icon-only, with the label as `aria-label` and
`title`, so the app bar never wraps. It fades and scales in while its width
animates from zero, so the other app-bar items do not jump, honours
`prefers-reduced-motion`, and calls the same reset as before. There is no
overflow menu. The closed-chat notice keeps its in-thread "Start a new chat"
button (fi "Aloita uusi keskustelu", sv "Starta en ny chatt").

### "What I can see" (desktop card; on mobile a bottom sheet from an info button in the app bar)

Sections, all in the user's language, from `display.visibility`:
- **You shared** — the attachment, in one line.
- **Checked automatically** — link check, call warning, if present.
- **Permissions** — granted items (green), refused items (grey,
  "not used"), and items not asked about are not listed.
- **Never asked for** — one fixed line: "Passwords, card numbers and codes."

## 4. Lab page `/lab`

Desktop only (≥ 1280 px design, usable at 1024). Three columns:

1. **Case picker** (left, 300 px): tabs Samples / Dev / Free. Dev: search,
   journey, language, benign, twin, split (tune / holdout — holdout greyed with
   a "gate only" label). List is virtualised or paginated (50).
2. **Conversation** (centre): the real demo thread component, same CSS, plus
   lab-only buttons: "Simulated user answers" (one step), "Run to end"
   (simulated user until final), "Finish now", "Restart".
3. **Inspector** (right, 460 px), top to bottom:
   - **Verdict bar** (dev/sample only, auto-evaluated when a final exists):
     PASS / FAIL, failure types as chips, action ours vs expected, risk ours
     vs expected, escalation ours vs expected, decisive question asked?
   - **Ours vs reference**: two columns, our advice + steps vs reference
     answer in the case language; required steps found / missing as chips.
   - **Turns**: one collapsible row per assistant turn: type, latency, cached,
     prompt chars; inside, **rules fired** as a list (`rule`: from → to) with
     long text shown as a word diff (insertions green, deletions red) instead
     of two full copies; raw model reply collapsed (pretty JSON).
   - **Review**: OK / Unsafe / Unclear + note → `results/human_review.csv`.

**Runs tab** (top bar of `/lab`: Workbench | Runs):
- Lists `results/runs/*.scored.json` (pre-scored files, §6). Never scores on
  request.
- Header: pass, false alarms, escalation recall/FP, twin pass, tune vs
  holdout columns.
- Failure-type bar chart (pure CSS) — click to filter.
- Table: case, journey, lang, benign, twin, split, ours, expected, pass,
  failure types. Click a row → opens it in the Workbench inspector in
  "read-only" mode (shows our stored answer vs reference, no conversation).

## 5. Server contract (`app/server.py`, `app/present.py`)

Everything content-related for the demo is computed server-side in
`app/present.py` (pure functions, no model calls, localised fi/en/sv), so the
frontend only renders.

Every reply from conversation endpoints:

```json
{
  "conversation_id": "…",
  "language": "fi",
  "thinking": false,
  "reply": { "type": "question|consent_request|final|notice", "...": "as turns.step" },
  "display": {
    "attachment": { "kind": "sms|email|call|letter|notification|null", "sender": "…", "body": "…",
                    "checks": [ { "tone": "warn|ok|unknown", "text": "Link check: suspicious · site created 4 days ago" } ] },
    "question": { "text": "…" },
    "quick_replies": ["Kyllä", "En", "En ole varma"],
    "consent": { "fields": ["operator_account.recent_logins"], "title": "…", "purpose": "…",
                 "items": [ { "field": "…", "label": "Viimeaikaiset kirjautumiset" } ] },
    "answer": { "urgency": "immediate|today|routine|none", "urgency_label": "Toimi nyt",
                "headline": "…", "reason": "…", "steps": ["…"], "more": ["…"],
                "escalate": true,
                "expert_label": "Puhu tietoturva-asiantuntijan kanssa",
                "why": { "bullets": ["…"], "sources": ["guidance title in language"], "note": "…" } },
    "handoff": { "target_label": "…", "situation": "…", "checked": "…", "consent": "…",
                 "advice": "…", "priority": "…", "labels": { "…": "…" }, "confirm": "…",
                 "brief": { "…": "…" } },
    "handoff_status": { "status": "pending|ready|failed", "text": "…" },
    "visibility": { "shared": ["…"], "checked": ["…"], "granted": ["…"], "refused": ["…"], "never": "…" }
  },
  "lab": { "trace": { "...": "turns trace" }, "turn": 3 }
}
```

- Only the keys relevant to the reply type are non-null. `lab` is included
  only when the request has `?lab=1` (the demo never receives traces).
  `closed: true` is present only after the chat has ended; an absent key means
  open.
- `headline`: localised action label from our own table in `present.py`
  (short imperative, not the vocabulary's long sentence); benign gets
  "Looks genuine – no action needed" style wording.
- `reason`: first sentence of `advice_text` if it is ≤ 200 chars, else the
  rationale sentence the model gave; never the whole paragraph.
- `steps`: `answer.steps`; if empty, split the remaining advice sentences.
- `more`: advice sentences neither the reason nor already covered by a step.
  The card shows the first three under the steps; the rest sit behind a
  "Show more" button, except when one carries an emergency instruction (112,
  "don't call", "heti" and the like), in which case all are visible.
- `why.bullets`: built from facts the user revealed (their answers),
  `signals_used` mapped to plain localised labels, and link/call checks.
- `why.sources`: `title_fi`/`title_en` of cited guidance (sv falls back to
  en).
- Consent labels and purposes: localised table keyed by signal path in
  `present.py` (one line each: what, how far back, why).
- `handoff`: the model-written brief mapped for the card, or `null`.
  `situation` is the brief's one summary (up to 400 characters) with the open
  questions appended; `brief.user_actions` stays structured for the expert and
  is not stitched into the prose.
  On an escalated final the brief is not ready when the reply returns:
  `display.handoff` is `null` and `display.handoff_status` is `pending` with a
  localised `text` ("Preparing the brief…"). A later final supersedes it. When
  the validated brief exists the poll returns `status: "ready"`, the card
  fields and `answer.priority`; a generation failure is `failed` with an
  honest localised line and no card. There is no deterministic summary: the
  page never builds a card from the answer text.
  The demo polls `GET /api/conversations/<id>/handoff` every ~0.5 s for at most
  ~40 s, starting on the final itself, not only when the expert button is
  tapped (polling never calls the model). It stops on `ready`, `failed` or
  `none`, on a newer final, on a new conversation and on a closed chat. The
  endpoint returns `{conversation_id, pending, status, text, handoff,
  answer: {priority}}`. Until ready the tapped button shows the server's status
  line in the card's place, with an animated indicator while `pending`; the
  placeholder is swapped for the card under the same key. The card's readable
  `priority` label is kept, and `answer.priority` (1–5, from the validated
  brief) adds one numeric row; null means no row.
- `notice`: `{text}` for `reply.type: "notice"`, the courtesy line of a closed
  chat (see `docs/CONVERSATION_GATING_API.md`). The key is absent from every
  other reply. It is never an answer card and never an error. The demo renders
  it as a neutral assistant bubble with a "Start a new chat" button, disables
  the composer with the placeholder "This chat has ended", and stops handoff
  polling. A later notice renders the same way; a new conversation clears it.
- Free-text starts accept `{source: "free", text, language, audience,
  attachment?: {kind, sender, body}}`; the attachment becomes
  `signals.artifact` (link_check stays null: we do not run real link checks).

Lab-only endpoints (`/api/lab/...`): case list with split membership (from
`data/splits/split.json`), reference, evaluate, simulate one step, run to end,
runs list, run detail (reads `results/runs/<name>.scored.json`), review.

## 6. Pre-scored runs

`python3 app/score.py <predictions.jsonl> --label X --per-case` writes
`results/runs/<label>.scored.json`: the summary report plus one row per case
(case_id, journey, language, audience, benign, twin, split, ours, expected,
acceptable, passed, failure types, advice, steps, reference answer). Run once
per prediction file. The lab reads only these.

## 7. Acceptance captures

Screenshots are stored in `/docs/screenshots/demo/` and captured with a
Playwright browser from the served app. Each state below is captured at
390×844 or 1440×900 as noted, and the set is reviewed before the change is
complete:

1. `/` start screen at 390×844 and 1440×900.
2. Bank-SMS sample, fi: attachment visible, a question, quick replies.
3. A consent card, then its receipt after Allow; same case after Don't allow.
4. A final answer card with expert button, expanded "why", handoff card.
5. A benign case final ("looks genuine").
6. Free text in sv with an attached message.
7. `/lab` with a dev case finished: verdict bar, ours vs reference, a rules
   diff.
8. `/lab` Runs with a scored file and a failure filter applied.

Checks: no monospace body text, no tofu boxes, no English strings in fi/sv
conversations (except brand), no horizontal scroll at 390 px, composer never
covers the last message, no console errors.
