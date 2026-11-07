# Demo screenshots — `docs/UI_SPEC.md` §7, items 1–6

Captured 2026-11-06 from the live server (`python3 app/server.py --host
127.0.0.1 --port 8791`) with Playwright Chromium. `01_start_390`,
`01_start_1440` and `03_consent_receipt_allow_390` were re-captured on
2026-11-07 from port 8793 after the UI polish and the "Luvat" heading rename.
`01_start_390`, `01_start_1440` and `06_attachment_form_sv_390` were
re-captured again on 2026-11-07 after the start-screen redesign (inline
attachment form, examples menu), and once more from port 8796 after the
attachment row became a grey button whose hover covers the whole row; the new
`01_start_hover_390` comes from that run. The `10_`–`12_` shots also come from
port 8796 after the model-only expert brief and the closed-chat notice were
wired into the demo; their rows note where a Playwright route was intercepted.
`01_start_390`, `01_start_1440`, `01_start_hover_390` and
`06_attachment_form_sv_390` were re-captured from port 8796 once more after the
app-bar subtitle was shortened to the prototype word, and the `13_*` shots were
taken in the same run after "New conversation" moved out of the overflow menu
into a visible New chat button.
`02_bank_sms_fi_390`, `04_answer_why_handoff_390`,
`06_free_text_sv_attachment_390`, `08_consent_refused_390` and
`09_mobile_scrolled_390` are fixtures: a fixture server replays recorded
replies (no model call), re-captured on 2026-11-07 after the quick-reply
wording, answer-card and mobile-scroll changes. `09_mobile_scrolled_390` is a
touch-enabled 390×844 mobile context (`is_mobile`, `has_touch`), not a desktop
window resized. Not taken from a mockup: every conversation is a real
`/api/conversations` response rendered by `app/web/demo/demo.js` and
`app/web/shared/thread.js`.

| File | Viewport | What it shows |
|---|---|---|
| `01_start_390.png` | 390×844, locale fi-FI | Start screen: app bar with the bare "Prototyyppi" subtitle and no New chat button, then the Personal/Business switch with the Examples menu button and the careful-check toggle as the header of one rounded panel, then the greeting and the collapsed attachment disclosure in the same grey as the careful-check row, with the composer inside the panel and the info button in the app bar. |
| `01_start_hover_390.png` | 390×844, locale fi-FI | The same start screen with the pointer over the collapsed attachment row: the whole row darkens edge to edge inside the card's rounded corners, and the title takes the accent colour. |
| `01_start_1440.png` | 1440×900, locale fi-FI | Same start screen on desktop with the short "Prototype" subtitle, no New chat button, the "What I can help with" card and the sticky "What I can see" card. |
| `02_bank_sms_fi_390.png` | 390×844, fi | Bank-SMS sample (journey `suspicious_message`): the forwarded text as an attachment bubble with the link-check chip, the assistant's closed yes/no question and the three topic chips that answer it ("Kyllä, kirjauduin sivulla" / "En kirjautunut" / "En ole varma"). |
| `03_consent_card_390.png` | 390×844, fi | Consent card from dev case `DSA-D-0002`: title, one-line purpose, Allow / Don't allow, the fine print, after the model actually asked for `operator_account.recent_logins`. |
| `03_consent_receipt_allow_390.png` | 390×844, fi | Same case after Allow: the card collapsed to "Sallit: Viimeaikaiset kirjautumiset" and the final answer followed. |
| `03_consent_receipt_deny_390.png` | 390×844, fi | Same case after Don't allow: "Et sallinut: …" and an advice card that does not claim to have used the refused signal. |
| `04_answer_why_handoff_390.png` | 390×2160, fi | Fixture: final answer card (urgency label, headline, reason, numbered steps, then the extra advice sentences under them), the expert request after it was sent ("Pyyntö lähetetty" instead of a disabled button), expanded "Miksi tämä neuvo?" with bullets and guidance titles, and the handoff card marked "(demo)". The taller viewport is so one shot holds the whole card set; the layout is the mobile one. |
| `04_answer_1440.png` | 1440×900, fi | A final answer on desktop next to the "What I can see" card, which shows the granted item in green. |
| `05_benign_final_390.png` | 390×844, fi | A benign case (dev `DSA-D-0015`) whose answer is `no_action_needed`: green left border, "Ei toimenpiteitä", "Vaikuttaa aidolta – ei toimenpiteitä". |
| `06_attachment_form_sv_390.png` | 390×844, locale sv-SE | The optional attachment disclosure opened on a new chat, with the bare "Prototyp" subtitle and no New chat button — grey toggle row and grey card with type (Sms / E-post / Samtal / Brev), sender and message text, expanded in place without a sheet. |
| `06_checking_indicator_sv_390.png` | 390×844, sv | Checking state with elapsed seconds ("Kontrollerar… 4 s") and the composer disabled. The start request was held 9 s with browser latency emulation so the counter could be photographed; the indicator is the real component, and the capture asserts it is still on screen when the shutter clicks. |
| `06_free_text_sv_attachment_390.png` | 390×844, sv | Fixture: free text in Swedish with the attached message: user bubble, attachment bubble, the recorded Swedish question and the current Swedish quick replies ("Ja, jag skrev in kortuppgifterna" / "Nej, jag skrev inte in några kortuppgifter" / "Vet inte"). |
| `07_info_sheet_390.png` | 390×844, fi | The mobile bottom sheet behind the app bar's info button: "Mitä minä näen" with what was shared, what was checked and what is never asked for. |
| `08_consent_refused_390.png` | 390×1700, fi | Fixture: the consent was refused on its first turn, so the card collapses to "Et sallinut: Viimeaikaiset kirjautumiset, Liittymän viimeisimmät muutokset", the follow-up question and the final advice follow, including the extra advice sentences under the steps. The same run's "Mitä minä näen" sheet lists both requested items as "ei käytetty" under "Luvat"; `report.json` records that text and the "why" bullets (now "Luin lähettämäsi viestin."). |
| `09_mobile_scrolled_390.png` | 390×844, fi, touch | Fixture: the same answer thread, scrolled mid-way by a real touch drag (finger 200 → 620 px): `scrollTop` moved 726 → 227 of a 1442 px thread with 716 px visible. The composer stays pinned; the answer card is partly above and below the fold, so `lastBottom` sits under the composer by design. `report.json` records the drag and the scroll positions. |
| `10_handoff_preparing_fi_390.png` | 390×844, fi | A live `clicked_link` sample: after the escalated final the expert button is tapped and, because the model-written brief is not ready yet, the card's place shows the dashed "Mitä asiantuntija saa (demo)" box with "Valmistelen asiantuntijan yhteenvetoa…" and three animated dots. Intercepted: the first three handoff-poll responses were fulfilled as `pending` so the state stayed on screen; the sentence and markup are the server's. |
| `10_handoff_ready_fi_390.png` | 390×844, fi | The same conversation once the real brief arrives: the pending box has been swapped for the handoff card and the page has scrolled its top edge into view, so the user can see that it arrived. The final and the brief are live model output; only the pending hold above was intercepted. The numeric queue priority row ("Kiireellisyys asiantuntijalle 4/5") sits below the fold here. |
| `10_handoff_ready_fi_390_tall.png` | 390×2160, fi | The same ready handoff card in one tall mobile viewport, as `04_answer_why_handoff_390` was taken: situation, checked, consent, advice, the readable priority and the numeric row "Kiireellisyys asiantuntijalle 4/5", then the confirmation line. |
| `10_handoff_failed_fi_390.png` | 390×844, fi | A real escalated `clicked_link` final after the expert button is tapped, but the poll was intercepted as `failed`: the status box keeps the server's failed sentence, loses the dots and shows no card, so no summary is invented. Intercepted; the sentence is the one `present.py` sends. |
| `11_closed_notice_sv_390.png` | 390×844, sv | A live Swedish free-text chat after the user sends "stop": a neutral assistant notice bubble, "Starta en ny chatt" under it, and the composer disabled with the placeholder "Chatten är avslutad". The stop is deterministic and makes no model call. |
| `11_closed_new_chat_sv_390.png` | 390×844, sv | The same chat after tapping "Starta en ny chatt": a fresh Swedish start screen, the composer enabled again and the attachment row collapsed. |
| `12_clarifying_fi_390.png` | 390×844, fi | A live Finnish free text "asdf qwer" gets a clarifying question and the one honest quick reply "En tiedä" (the server's fallback when the question names no topic). |
| `13_new_chat_button_fi_390.png` | 390×844, fi | A live Finnish chat after the first message. The app bar shows the new-chat button icon-only, 44 px wide, with the label kept as `aria-label` and `title` ("Uusi keskustelu"); the bar stays one 61 px row. |
| `13_new_chat_button_fi_1440.png` | 1440×900, fi | The same live chat at desktop width: the app bar shows the icon plus the "Uusi keskustelu" label (147 px) and grows to 65 px, still one row. |
| `13_new_chat_hover_fi_390.png` | 390×844, fi | The same chat with the pointer over the icon-only button: the neutral-soft hover background fills its round tap target. |
| `13_new_chat_focus_fi_390.png` | 390×844, fi | The same chat with keyboard focus on the button reaching its visible focus ring; `aria-label` and `title` read "Uusi keskustelu". |
| `13_new_chat_button_sv_390.png` | 390×844, sv-SE | A live Swedish chat; the icon-only button carries "Ny chatt" as `aria-label` and `title`. |
| `13_new_chat_after_fi_390.png` | 390×844, fi | The same Finnish chat after tapping the New chat button: the Finnish start screen is back with "Prototyyppi", and the button has disappeared again. |

`anim_item_enter_25/75.png`, `anim_consent_swap_25/75.png` and
`anim_why_open_25/75.png` are motion checks, not part of the UI spec: each
pair pauses the same transition at 25 % and 75 % (Web Animations API) so a
reviewer can see both halves. The consent pair shows the sequenced swap: the
old card is fading out at 25 % with the receipt still invisible, and the
receipt is fading in at 75 % with the old card gone. They come from the
fixture server, not a live model call.

Conditions: live model replies from the fixed DeepSeek V4.1 Flash client
(cached raw replies after the first call), server-side `display` only, no case
ids or enums on screen. `02_bank_sms_fi_390`, `04_answer_why_handoff_390`,
`06_free_text_sv_attachment_390`, `08_consent_refused_390` and
`09_mobile_scrolled_390` are the exceptions: they replay recorded replies
through a fixture server, with no model call. The `10_handoff_*` shots use the
live model final and brief; only the handoff poll was intercepted by a
Playwright route, as each row says. The `13_*` shots are live model replies
with no interception. The app bar was measured at 360, 390 and 1440 px wide:
its height stays 61 px at 360 and 390 and 65 px at 1440, the document width
equals the viewport, and the New chat button never wraps. Case `DSA-D-0002`
and `DSA-D-0015` are started through `/?case=<case_id>`, a screenshot-only
deep link that is not linked from the UI.

`report.json` is the Playwright check output for the same run: per shot it
records console errors, horizontal overflow, the font actually used, whether
the composer covers the last item, app-bar clipping and English words found
inside a fi/sv conversation. It is kept next to the images as evidence; move
it out if the images are the only deliverable wanted.
