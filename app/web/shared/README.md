# `app/web/shared/` — the two pages' common layer

Used by the demo (`/`) and the lab (`/lab`). Nothing here calls the API or
knows a case; both pages render the server's `display` block through it.

| File | What it is |
|---|---|
| `tokens.css` | Design tokens from `mockups/demo.html`, the bundled `@font-face`, element base (font, focus ring, `svg.icon` sizing) and `.visually-hidden`. |
| `thread.css` | Every conversation component: bubbles, attachment, quick replies, consent card and receipt, checking indicator, answer card, why expander, handoff, error. |
| `thread.js` | `Thread.render(container, items, handlers, labels)` — the documented API is at the top of the file, and `Thread.DEFAULT_LABELS` lists the chrome strings the page has to pass. |
| `icons.js` | `Icons.svg(name, cls)` / `Icons.el(name, cls)` / `Icons.forKind(kind)`. Inline SVG only: the server has no emoji font, so an emoji is a tofu box. |
| `fonts/InterVariable.woff2`, `fonts/LICENSE.txt` | Inter 4.1 (variable), SIL Open Font License 1.1, from the official `rsms/inter` release. Bundled, no CDN. |

Load order:

```html
<link rel="stylesheet" href="/shared/tokens.css">
<link rel="stylesheet" href="/shared/thread.css">
<script src="/shared/icons.js" defer></script>
<script src="/shared/thread.js" defer></script>
```

## Rules the shared layer keeps for both pages

- **Page assets.** The pages load scripts and styles from repository assets.
  Classes define the base appearance. Transitions use browser animations and
  measured element heights and positions.
- **No content decisions.** Headline, reason, steps, consent text, why lines,
  handoff summary and visibility lines all arrive in `display`; `thread.js`
  only lays them out. The `labels` argument carries UI chrome (e.g. "Why this
  advice?", "Try again", "You allowed: %s") and is the page's i18n table.
- **Untrusted text stays text.** The attachment body is drawn with
  `textContent` and `white-space: pre-wrap`; no link in it becomes clickable.
- **Reconcile, don't re-render.** `Thread.render` diffs on `item.key`, so the
  checking timer and an open "why" survive unrelated updates.

## Item types (the short version)

`greeting`, `user`, `attachment`, `checking`, `question` (+ `quick` chips),
`consent` (open → collapses to its own receipt), `receipt`, `answer`,
`handoff`, `handoff-status`, `notice`, `error`. Full field lists are in the
header of `thread.js`.

```js
Thread.render(threadEl, items, {
  onQuickReply(text, key) {},
  onConsent(key, granted) {},
  onExpert(key) {},
  onNewChat() {},
  onRetry(key) {}
}, i18n.thread);
```
