/* Demo page `/`.
 *
 * The page renders; it never decides content. Every content string the end
 * user reads (question, consent purpose, answer headline, steps, handoff
 * summary, visibility lines) comes from the server's `display` block. This
 * file owns only the UI chrome: the i18n table below, the start screen, the
 * composer, the attachment sheet and the "What I can see" card.
 *
 * Language: default from navigator.language, then fi / en / sv. Changing it
 * before the first message changes the conversation language; after the first
 * message it is locked, and the thread's language (the server's `language`)
 * wins so chrome and content never disagree.
 *
 * One dev-only hook: `?case=<case_id>` starts a dev case directly. It is used
 * by the screenshot run in docs/screenshots/demo and is not linked from the
 * UI; no id is ever shown to the user.
 */
(function () {
  "use strict";

  var LANGS = ["fi", "en", "sv"];
  var JOURNEYS = ["suspicious_message", "clicked_link", "suspicious_call", "breach_notice", "smb_incident"];

  var I18N = {
    fi: {
      docTitle: "Tietoturva-avustaja – DNA",
      title: "Tietoturva-avustaja",
      proto: "Prototyyppi",
      language: "Kieli",
      languageLocked: "Kieli on lukittu, koska keskustelu on alkanut.",
      newConversation: "Uusi keskustelu",
      info: "Mitä minä näen",
      greeting: {
        consumer: "Hei! Kerro, mikä viestissä, puhelussa tai linkissä epäilyttää, niin sanon, mitä kannattaa tehdä seuraavaksi.",
        business: "Hei! Kerro yritykseesi tulleesta viestistä, puhelusta tai maksusta, niin sanon, mitä kannattaa tehdä seuraavaksi."
      },
      audience: { label: "Näkökulma", consumer: "Henkilö", business: "Yritys" },
      careful: {
        label: "Tarkista tarkemmin",
        hint: "Vastaus voi kestää 25–60 sekuntia."
      },
      examples: {
        label: "Esimerkkejä",
        suspicious_message: "Viesti pankista",
        clicked_link: "Klikkasin linkkiä",
        suspicious_call: "Soitto ”asiakaspalvelusta”",
        breach_notice: "Ei kenttää eSIM-viestin jälkeen",
        smb_incident: "Toimittaja vaihtoi tilinumeron"
      },
      composer: {
        placeholder: "Kirjoita viesti…",
        followUp: "Kysy jatkokysymys…",
        message: "Viesti",
        send: "Lähetä",
        ended: "Keskustelu on päättynyt"
      },
      attach: {
        summary: "Kuvaile viestiä/puhelua tarkemmin",
        optional: "Valinnainen",
        kind: "Viestin tyyppi",
        kinds: { sms: "Tekstiviesti", email: "Sähköposti", call: "Puhelu", letter: "Kirje" },
        sender: "Lähettäjä",
        senderPlaceholder: "Esim. LUMIPANKKI",
        body: "Viestin sisältö",
        bodyPlaceholder: "Liitä viestin teksti tähän",
        close: "Sulje"
      },
      visibility: {
        title: "Mitä minä näen",
        empty: "Kun aloitat, näet tässä, mitä tietoja käytän.",
        shared: "Jaoit",
        checked: "Tarkistin automaattisesti",
        permission: "Luvat",
        never: "En koskaan pyydä",
        notUsed: "ei käytetty"
      },
      help: {
        title: "Missä voin auttaa",
        messages: "Epäilyttävät viestit",
        links: "Avaamasi linkit",
        calls: "Oudot puhelut",
        account: "Huolet tilistäsi tai liittymästäsi",
        business: "Yrityksille: laskut, tilinumeromuutokset ja työntekijöiden tilit."
      },
      error: "Yhteys katkesi hetkeksi. Yritä uudelleen.",
      thread: {
        you: "Sinä",
        assistant: "Avustaja",
        checking: "Tarkistan…",
        checkingCarefully: "Tarkistan tarkemmin…",
        checkingCarefullyAria: "Vastausta tarkistetaan tarkemmin",
        seconds: "%d s",
        why: "Miksi tämä neuvo?",
        basedOn: "Perustuu ohjeeseen: %s",
        handoffTitle: "Mitä asiantuntija saa",
        demoNote: "(demo)",
        expertPriority: "Kiireellisyys asiantuntijalle",
        expertPriorityValue: "%d/5",
        newChat: "Aloita uusi keskustelu",
        receiptAllowed: "Sallit: %s",
        receiptRefused: "Et sallinut: %s",
        retry: "Yritä uudelleen",
        error: "Jokin meni pieleen.",
        expertSent: "Pyyntö lähetetty",
        attachmentFrom: "%s lähettäjältä %s",
        attachmentAria: "Lähettämäsi viesti",
        quickAria: "Ehdotetut vastaukset",
        consentAria: "Lupapyyntö",
        answerAria: "Mitä tehdä nyt",
        handoffAria: "Mitä asiantuntija saa",
        stepsAria: "Vaiheet",
        showMore: "Näytä lisää",
        showLess: "Näytä vähemmän",
        checkingAria: "Vastausta tarkistetaan"
      }
    },

    en: {
      docTitle: "Security assistant – DNA",
      title: "Security assistant",
      proto: "Prototype",
      language: "Language",
      languageLocked: "The language is locked once the conversation has started.",
      newConversation: "New chat",
      info: "What I can see",
      greeting: {
        consumer: "Hi! Tell me what looks off about a message, a call or a link, and I'll say what to do next.",
        business: "Hi! Tell me about a message, call or payment at your business, and I'll say what to do next."
      },
      audience: { label: "View", consumer: "Personal", business: "Business" },
      careful: {
        label: "Check more carefully",
        hint: "Each reply can take 25–60 seconds."
      },
      examples: {
        label: "Examples",
        suspicious_message: "Text from my bank",
        clicked_link: "I clicked a link",
        suspicious_call: "A call from ‘support’",
        breach_notice: "No signal after an eSIM message",
        smb_incident: "Supplier changed bank details"
      },
      composer: {
        placeholder: "Write a message…",
        followUp: "Ask a follow-up…",
        message: "Message",
        send: "Send",
        ended: "This chat has ended"
      },
      attach: {
        summary: "Describe the message or call in more detail",
        optional: "Optional",
        kind: "Type",
        kinds: { sms: "Text message", email: "Email", call: "Call", letter: "Letter" },
        sender: "Sender",
        senderPlaceholder: "e.g. LUMIPANKKI",
        body: "Message text",
        bodyPlaceholder: "Paste the message here",
        close: "Close"
      },
      visibility: {
        title: "What I can see",
        empty: "When you start, you'll see here which details I use.",
        shared: "You shared",
        checked: "Checked automatically",
        permission: "Permissions",
        never: "Never asked for",
        notUsed: "not used"
      },
      help: {
        title: "What I can help with",
        messages: "Messages that ask you to act",
        links: "Links you opened",
        calls: "Calls that felt off",
        account: "Worries about your account or SIM",
        business: "For businesses: invoices, changed bank details and staff accounts."
      },
      error: "The connection dropped for a moment. Please try again.",
      thread: {
        you: "You",
        assistant: "Assistant",
        checking: "Checking…",
        checkingCarefully: "Checking carefully…",
        checkingCarefullyAria: "The reply is being checked carefully",
        seconds: "%d s",
        why: "Why this advice?",
        basedOn: "Based on: %s",
        handoffTitle: "What the expert receives",
        demoNote: "(demo)",
        expertPriority: "Expert queue priority",
        expertPriorityValue: "%d of 5",
        newChat: "Start a new chat",
        receiptAllowed: "You allowed: %s",
        receiptRefused: "You said no to: %s",
        retry: "Try again",
        error: "Something went wrong.",
        expertSent: "Request sent",
        attachmentFrom: "%s from %s",
        attachmentAria: "The message you sent",
        quickAria: "Suggested answers",
        consentAria: "Permission request",
        answerAria: "What to do now",
        handoffAria: "What the expert receives",
        stepsAria: "Steps",
        showMore: "Show more",
        showLess: "Show less",
        checkingAria: "The reply is being checked"
      }
    },

    sv: {
      docTitle: "Säkerhetsassistent – DNA",
      title: "Säkerhetsassistent",
      proto: "Prototyp",
      language: "Språk",
      languageLocked: "Språket låses när samtalet har börjat.",
      newConversation: "Ny chatt",
      info: "Vad jag kan se",
      greeting: {
        consumer: "Hej! Berätta vad som känns fel med ett sms, ett samtal eller en länk, så säger jag vad du bör göra härnäst.",
        business: "Hej! Berätta om ett meddelande, ett samtal eller en betalning i företaget, så säger jag vad du bör göra härnäst."
      },
      audience: { label: "Vy", consumer: "Privat", business: "Företag" },
      careful: {
        label: "Kontrollera noggrannare",
        hint: "Varje svar kan ta 25–60 sekunder."
      },
      examples: {
        label: "Exempel",
        suspicious_message: "Sms från banken",
        clicked_link: "Jag klickade på en länk",
        suspicious_call: "Ett samtal från ”supporten”",
        breach_notice: "Ingen täckning efter ett eSIM-sms",
        smb_incident: "Leverantören bytte kontonummer"
      },
      composer: {
        placeholder: "Skriv ett meddelande…",
        followUp: "Ställ en följdfråga…",
        message: "Meddelande",
        send: "Skicka",
        ended: "Chatten är avslutad"
      },
      attach: {
        summary: "Beskriv meddelandet eller samtalet närmare",
        optional: "Valfritt",
        kind: "Typ",
        kinds: { sms: "Sms", email: "E-post", call: "Samtal", letter: "Brev" },
        sender: "Avsändare",
        senderPlaceholder: "t.ex. LUMIPANKKI",
        body: "Meddelandets text",
        bodyPlaceholder: "Klistra in meddelandet här",
        close: "Stäng"
      },
      visibility: {
        title: "Vad jag kan se",
        empty: "När du börjar ser du här vilka uppgifter jag använder.",
        shared: "Det du delade",
        checked: "Kontrollerat automatiskt",
        permission: "Behörigheter",
        never: "Frågar aldrig efter",
        notUsed: "användes inte"
      },
      help: {
        title: "Det här kan jag hjälpa dig med",
        messages: "Meddelanden som ber dig göra något",
        links: "Länkar du har öppnat",
        calls: "Samtal som kändes konstiga",
        account: "Oro för ditt konto eller abonnemang",
        business: "För företag: fakturor, ändrade kontonummer och medarbetarnas konton."
      },
      error: "Anslutningen bröts en stund. Försök igen.",
      thread: {
        you: "Du",
        assistant: "Assistenten",
        checking: "Kontrollerar…",
        checkingCarefully: "Kontrollerar noggrannare…",
        checkingCarefullyAria: "Svaret kontrolleras noggrannare",
        seconds: "%d s",
        why: "Varför det här rådet?",
        basedOn: "Bygger på: %s",
        handoffTitle: "Det specialisten får",
        demoNote: "(demo)",
        expertPriority: "Prioritet hos experten",
        expertPriorityValue: "%d av 5",
        newChat: "Starta en ny chatt",
        receiptAllowed: "Du tillät: %s",
        receiptRefused: "Du nekade: %s",
        retry: "Försök igen",
        error: "Något gick fel.",
        expertSent: "Förfrågan skickad",
        attachmentFrom: "%s från %s",
        attachmentAria: "Meddelandet du skickade",
        quickAria: "Förslag på svar",
        consentAria: "Tillståndsförfrågan",
        answerAria: "Vad du ska göra nu",
        handoffAria: "Det specialisten får",
        stepsAria: "Steg",
        showMore: "Visa mer",
        showLess: "Visa mindre",
        checkingAria: "Svaret kontrolleras"
      }
    }
  };

  var state = {
    lang: "en",
    audience: "consumer",
    thinking: false,
    started: false,
    pending: false,
    conversationId: null,
    generation: 0,
    seq: 0,
    items: [],
    display: null,
    closed: false,
    handoff: null,
    handoffTimer: null,
    quickKey: null,
    consentKey: null,
    request: null,
    attachment: null,
    examplesOpen: false
  };

  var dom = {};

  // --- language helpers ----------------------------------------------------

  function dict() { return I18N[state.lang] || I18N.en; }

  function t(path) {
    var node = dict();
    var parts = String(path).split(".");
    for (var i = 0; i < parts.length; i += 1) {
      if (node == null) { return ""; }
      node = node[parts[i]];
    }
    return node == null ? "" : node;
  }

  function fill(pattern, value) {
    return String(pattern == null ? "" : pattern).replace("%s", value == null ? "" : String(value));
  }

  function detectLanguage() {
    var tag = "";
    if (typeof navigator !== "undefined") {
      tag = navigator.language || (navigator.languages && navigator.languages[0]) || "";
    }
    var base = String(tag).toLowerCase().split("-")[0];
    return LANGS.indexOf(base) >= 0 ? base : "en";
  }

  // --- tiny DOM helpers ----------------------------------------------------

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) { node.className = cls; }
    if (text != null) { node.textContent = String(text); }
    return node;
  }

  function icon(name, cls) {
    return window.Icons.el(name, cls);
  }

  function reduced() {
    return !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  }

  function nextKey(prefix) {
    state.seq += 1;
    return prefix + state.seq;
  }

  function findItem(key) {
    for (var i = 0; i < state.items.length; i += 1) {
      if (state.items[i] && state.items[i].key === key) { return state.items[i]; }
    }
    return null;
  }

  // Whether the thread is following its bottom; used so a card that arrives
  // while the user reads further up does not yank the view.
  function nearEnd(slack) {
    var box = dom.scroll;
    var limit = slack == null ? 120 : slack;
    return box.scrollHeight - box.scrollTop - box.clientHeight <= limit;
  }

  // A ready card is taller than the status box it replaces: once the swap
  // animation has settled, bring its top edge into view. The page has no
  // per-item scroll helper, so this mirrors revealAttachCard: measure against
  // the scroll box, then scroll it smoothly (instantly under reduced motion).
  function revealItem(key, follow, fromTop) {
    if (!follow) { return; }
    window.setTimeout(function () {
      // The user scrolled up while the box was changing: leave them there.
      if (dom.scroll.scrollTop < fromTop - 40) { return; }
      var node = dom.thread.querySelector('[data-key="' + key + '"]');
      if (!node) { return; }
      var view = dom.scroll.getBoundingClientRect();
      var box = node.getBoundingClientRect();
      var top = dom.scroll.scrollTop + (box.top - view.top) - 8;
      dom.scroll.scrollTo({ top: top, behavior: reduced() ? "auto" : "smooth" });
    }, reduced() ? 0 : 340);
  }

  // --- rendering -----------------------------------------------------------

  function labels() {
    var strings = t("thread");
    if (!state.thinking) { return strings; }
    return Object.assign({}, strings, {
      checking: strings.checkingCarefully,
      checkingAria: strings.checkingCarefullyAria
    });
  }

  function greetingItem() {
    return { key: "greeting", type: "greeting", text: t("greeting." + state.audience) };
  }

  function checkingItem() {
    return { key: nextKey("c"), type: "checking", startedAt: Date.now() };
  }

  function renderThread() {
    var stamped = state.items.map(function (item) {
      var copy = {};
      Object.keys(item).forEach(function (k) { copy[k] = item[k]; });
      copy.lang = state.lang;
      return copy;
    });
    window.Thread.render(dom.thread, stamped, handlers, labels());
  }

  function placeThumb(group) {
    var active = group.querySelector('.switch-button[aria-pressed="true"]');
    var thumb = group.querySelector(".switch-thumb");
    if (!active || !thumb) { return; }
    var gr = group.getBoundingClientRect();
    var ar = active.getBoundingClientRect();
    var border = parseFloat(getComputedStyle(group).borderLeftWidth) || 0;
    thumb.style.left = (ar.left - gr.left - border) + "px";
    thumb.style.width = ar.width + "px";
  }

  function journeyIcon(journey) {
    var icons = {
      suspicious_message: "message",
      clicked_link: "alert",
      suspicious_call: "phone",
      breach_notice: "bell",
      smb_incident: "briefcase"
    };
    return icons[journey] || "message";
  }

  function setExamplesOpen(open) {
    state.examplesOpen = open;
    if (!dom.examplesButton) { return; }
    dom.examplesButton.setAttribute("aria-expanded", open ? "true" : "false");
    dom.examplesReveal.setAttribute("data-open", open ? "true" : "false");
    dom.examplesMenu.setAttribute("aria-hidden", open ? "false" : "true");
    dom.examplesMenu.inert = !open;
  }

  function closeExamples() { setExamplesOpen(false); }

  function renderStart() {
    if (state.started) {
      closeExamples();
      // leaveStart collapses both blocks first; do not cut its animation short.
      if (!dom.startTop.hasAttribute("data-leaving")) {
        dom.startTop.hidden = true;
        dom.startAttach.hidden = true;
      }
      return;
    }
    dom.startTop.hidden = false;
    dom.startAttach.hidden = false;
    dom.startTop.removeAttribute("data-leaving");
    dom.startAttach.removeAttribute("data-leaving");

    var group = dom.switchGroup;
    group.setAttribute("aria-label", t("audience.label"));
    Array.prototype.forEach.call(group.querySelectorAll(".switch-button"), function (button) {
      var key = button.getAttribute("data-audience");
      button.textContent = t("audience." + key);
      button.setAttribute("aria-pressed", state.audience === key ? "true" : "false");
    });

    dom.examplesLabel.textContent = t("examples.label");
    dom.examplesButton.setAttribute("aria-label", t("examples.label"));
    dom.examplesMenu.textContent = "";
    JOURNEYS.forEach(function (journey) {
      var item = el("button", "menu-item");
      item.type = "button";
      item.setAttribute("role", "menuitem");
      item.appendChild(icon(journeyIcon(journey), "sm"));
      item.appendChild(el("span", null, t("examples." + journey)));
      item.addEventListener("click", function () {
        closeExamples();
        startSample(journey);
      });
      dom.examplesMenu.appendChild(item);
    });
    setExamplesOpen(state.examplesOpen);
    placeThumb(group);
  }

  function fillVisibility(host, visibility) {
    host.textContent = "";
    if (!visibility) {
      host.appendChild(el("p", "vis-empty", t("visibility.empty")));
      return;
    }

    var sections = [
      ["shared", visibility.shared || []],
      ["checked", visibility.checked || []]
    ];
    sections.forEach(function (pair) {
      if (!pair[1].length) { return; }
      var block = el("section", "vis-section");
      block.appendChild(el("h3", "vis-title", t("visibility." + pair[0])));
      var list = el("ul", "vis-list");
      pair[1].forEach(function (line) { list.appendChild(el("li", null, line)); });
      block.appendChild(list);
      host.appendChild(block);
    });

    var granted = visibility.granted || [];
    var refused = visibility.refused || [];
    if (granted.length || refused.length) {
      var perm = el("section", "vis-section");
      perm.appendChild(el("h3", "vis-title", t("visibility.permission")));
      var pills = el("div", "vis-pills");
      granted.forEach(function (line) {
        var pill = el("span", "pill");
        pill.appendChild(icon("check", "sm"));
        pill.appendChild(el("span", null, line));
        pills.appendChild(pill);
      });
      refused.forEach(function (line) {
        var pill = el("span", "pill pill-no");
        pill.appendChild(el("span", null, line + " · " + t("visibility.notUsed")));
        pills.appendChild(pill);
      });
      perm.appendChild(pills);
      host.appendChild(perm);
    }

    if (visibility.never) {
      var never = el("section", "vis-section");
      never.appendChild(el("h3", "vis-title", t("visibility.never")));
      never.appendChild(el("p", "vis-never", visibility.never));
      host.appendChild(never);
    }
  }

  function renderVisibility() {
    var visibility = state.display ? state.display.visibility : null;
    fillVisibility(dom.sideBody, visibility);
    fillVisibility(dom.sheetBody, visibility);
  }

  function renderHelp() {
    // Desktop-only card in the right column; the start screen must not read as
    // an empty page. Hidden once the thread has content of its own.
    dom.helpCard.hidden = state.started;
    if (state.started) { return; }
    dom.helpTitle.textContent = t("help.title");
    dom.helpList.textContent = "";
    ["messages", "links", "calls", "account"].forEach(function (key) {
      dom.helpList.appendChild(el("li", null, t("help." + key)));
    });
    dom.helpBusiness.textContent = t("help.business");
  }

  function syncAttachment() {
    // A collapsed form is not part of the message, even if it holds a draft.
    if (dom.attachCard.getAttribute("data-open") !== "true") {
      state.attachment = null;
      return;
    }
    var body = dom.attachBody.value.trim();
    if (!body) { state.attachment = null; return; }
    var kind = dom.attachKinds.querySelector('input[name="kind"]:checked');
    state.attachment = {
      kind: kind ? kind.value : "sms",
      sender: dom.attachSender.value.trim(),
      body: body
    };
  }

  function setAttachOpen(open) {
    dom.attachCard.setAttribute("data-open", open ? "true" : "false");
    dom.attachToggle.setAttribute("aria-expanded", open ? "true" : "false");
    if (!open) {
      // Keep the draft in the fields, but a collapsed form never attaches.
      state.attachment = null;
      return;
    }
    syncAttachment();
    window.setTimeout(revealAttachCard, 220);
  }

  // The expanded form can be taller than the scroll area: once the height
  // animation has settled, bring its top edge into view.
  function revealAttachCard() {
    if (dom.attachCard.getAttribute("data-open") !== "true") { return; }
    var view = dom.scroll.getBoundingClientRect();
    var card = dom.attachCard.getBoundingClientRect();
    if (card.bottom <= view.bottom - 8) { return; }
    var top = dom.scroll.scrollTop + (card.top - view.top) - 8;
    dom.scroll.scrollTo({ top: top, behavior: reduced() ? "auto" : "smooth" });
  }

  function clearAttachForm() {
    var sms = dom.attachKinds.querySelector('input[name="kind"][value="sms"]');
    if (sms) { sms.checked = true; }
    dom.attachSender.value = "";
    dom.attachBody.value = "";
    state.attachment = null;
    setAttachOpen(false);
  }

  function applyChrome() {
    // Once a conversation has begun the thread is a normal chat log that runs
    // from the top; only the start screen docks it against the composer.
    dom.scroll.classList.toggle("chatting", state.started);
    document.documentElement.lang = state.lang;
    document.title = t("docTitle");

    dom.appTitle.textContent = t("title");
    dom.proto.textContent = t("proto");

    dom.langCode.textContent = state.lang.toUpperCase();
    dom.langButton.setAttribute("aria-label", t("language"));
    dom.langButton.setAttribute("aria-haspopup", "true");
    dom.langButton.setAttribute("aria-expanded",
      dom.langMenu.hidden || dom.langMenu.classList.contains("menu-leaving") ? "false" : "true");
    if (state.started) {
      dom.langButton.setAttribute("aria-disabled", "true");
      dom.langButton.title = t("languageLocked");
    } else {
      dom.langButton.removeAttribute("aria-disabled");
      dom.langButton.removeAttribute("title");
    }
    Array.prototype.forEach.call(dom.langMenu.querySelectorAll("[data-lang]"), function (button) {
      button.setAttribute("aria-checked", button.getAttribute("data-lang") === state.lang ? "true" : "false");
    });

    dom.newChatLabel.textContent = t("newConversation");
    dom.newChat.setAttribute("aria-label", t("newConversation"));
    dom.newChat.title = t("newConversation");
    dom.newChat.classList.toggle("is-visible", state.started);

    dom.infoButton.setAttribute("aria-label", t("info"));
    dom.side.setAttribute("aria-label", t("help.title") + " · " + t("visibility.title"));
    dom.sideTitle.textContent = t("visibility.title");
    dom.infoSheetTitle.textContent = t("visibility.title");
    dom.sheetClose.setAttribute("aria-label", t("attach.close"));

    dom.input.placeholder = state.closed ? t("composer.ended")
      : (state.started ? t("composer.followUp") : t("composer.placeholder"));
    dom.input.setAttribute("aria-label", t("composer.message"));
    dom.sendButton.setAttribute("aria-label", t("composer.send"));

    dom.carefulTitle.textContent = t("careful.label");
    dom.carefulHint.textContent = t("careful.hint");
    dom.thinkingToggle.checked = state.thinking;

    dom.attachTitle.textContent = t("attach.summary");
    dom.attachOptional.textContent = t("attach.optional");
    dom.attachKindLabel.textContent = t("attach.kind");
    Array.prototype.forEach.call(dom.attachKinds.querySelectorAll("[data-kind-label]"), function (node) {
      var kinds = t("attach.kinds");
      var kind = node.getAttribute("data-kind-label");
      node.textContent = (kinds && kinds[kind]) || kind;
    });
    dom.attachSenderLabel.textContent = t("attach.sender");
    dom.attachSender.placeholder = t("attach.senderPlaceholder");
    dom.attachBodyLabel.textContent = t("attach.body");
    dom.attachBody.placeholder = t("attach.bodyPlaceholder");
  }

  function refreshAll() {
    applyChrome();
    renderThread();
    renderStart();
    renderHelp();
    renderVisibility();
  }

  function setPending(pending) {
    state.pending = pending;
    dom.input.disabled = pending || state.closed;
    dom.sendButton.disabled = pending || state.closed;
  }

  function scrollEnd() {
    window.Thread.scrollToEnd(dom.scroll);
  }

  // --- conversation --------------------------------------------------------

  // New conversation: let the old thread fade out, then reset and let the
  // start panel fade in. Nothing is cleared under the user's eyes.
  function startNew() {
    if (dom.thread.classList.contains("thread-leaving")) { return; }
    if (reduced()) { resetConversation(); return; }
    dom.thread.classList.add("thread-leaving");
    window.setTimeout(function () {
      dom.thread.classList.remove("thread-leaving");
      resetConversation();
      dom.thread.classList.add("thread-in");
      window.setTimeout(function () { dom.thread.classList.remove("thread-in"); }, 260);
    }, 130);
  }

  function resetConversation() {
    state.generation += 1;
    stopHandoffPoll();
    state.handoff = null;
    state.closed = false;
    state.started = false;
    state.thinking = false;
    state.pending = false;
    state.conversationId = null;
    state.items = [greetingItem()];
    state.display = null;
    state.quickKey = null;
    state.consentKey = null;
    state.request = null;
    state.attachment = null;
    clearAttachForm();
    closeExamples();
    dom.thinkingToggle.disabled = false;
    setPending(false);
    refreshAll();
    scrollEnd();
    dom.input.focus({ preventScroll: true });
  }

  function startSample(journey) {
    if (state.pending || state.started) { return; }
    clearAttachForm();
    dom.input.value = "";
    resizeComposer();
    begin({ source: "sample", journey: journey }, {});
  }

  function begin(payload, optimistic) {
    payload.thinking = state.thinking;
    state.started = true;
    dom.thinkingToggle.disabled = true;
    state.pending = true;
    state.items = [greetingItem()];
    if (optimistic && optimistic.text) {
      state.items.push({ key: nextKey("u"), type: "user", text: optimistic.text });
    }
    if (state.attachment) {
      state.items.push({ key: nextKey("a"), type: "attachment", attachment: localAttachment(state.attachment) });
    }
    state.items.push(checkingItem());
    leaveStart();
    clearAttachForm();
    setPending(true);
    applyChrome();
    enterThread();
    renderThread();
    scrollEnd();
    request({ kind: "start", payload: payload });
  }

  function leaveStart() {
    if (dom.startTop.hidden && dom.startAttach.hidden) { return; }
    dom.startTop.setAttribute("data-leaving", "true");
    dom.startAttach.setAttribute("data-leaving", "true");
    if (reduced()) { finishLeaveStart(); return; }
    window.setTimeout(finishLeaveStart, 180);
  }

  function finishLeaveStart() {
    // A quick "new conversation" can put the panels back before this fires.
    if (!state.started) {
      dom.startTop.removeAttribute("data-leaving");
      dom.startAttach.removeAttribute("data-leaving");
      return;
    }
    dom.startTop.hidden = true;
    dom.startAttach.hidden = true;
    dom.startTop.removeAttribute("data-leaving");
    dom.startAttach.removeAttribute("data-leaving");
  }

  function enterThread() {
    dom.thread.classList.remove("thread-in");
    void dom.thread.offsetWidth;
    dom.thread.classList.add("thread-in");
    window.setTimeout(function () { dom.thread.classList.remove("thread-in"); }, 260);
  }

  function localAttachment(raw) {
    var kinds = t("attach.kinds");
    return {
      kind: raw.kind,
      kind_label: (kinds && kinds[raw.kind]) || "",
      sender: raw.sender || "",
      time: null,
      body: raw.body || "",
      checks: []
    };
  }

  function sendMessage(text) {
    if (state.pending || state.closed) { return; }
    if (state.quickKey) {
      var question = findItem(state.quickKey);
      if (question) { question.answered = true; }
      state.quickKey = null;
    }
    state.items.push({ key: nextKey("u"), type: "user", text: text });
    state.items.push(checkingItem());
    setPending(true);
    renderThread();
    scrollEnd();
    request({ kind: "message", text: text });
  }

  function onConsent(key, granted) {
    if (state.pending) { return; }
    var item = findItem(key);
    if (!item || item.type !== "consent" || item.state !== "open") { return; }
    var consent = item.consent || {};
    var names = (consent.items || []).map(function (row) { return row && row.label; })
      .filter(Boolean).join(", ");
    var pattern = granted ? t("thread.receiptAllowed") : t("thread.receiptRefused");
    item.state = granted ? "allowed" : "refused";
    item.receipt = fill(pattern, names);
    state.consentKey = null;
    state.items.push(checkingItem());
    setPending(true);
    renderThread();
    scrollEnd();
    request({
      kind: "consent",
      granted: granted ? (consent.fields || []) : [],
      refused: granted ? [] : (consent.fields || [])
    });
  }

  function onExpert(key) {
    var item = findItem(key);
    if (!item || item.type !== "answer" || item.expertSent) { return; }
    item.expertSent = true;
    // The card is the model's brief. The page never builds one from the
    // answer text; until the brief is ready it shows the server's status line.
    var handoff = state.handoff;
    var fromTop = dom.scroll.scrollTop;
    var cardKey = null;
    if (handoff && handoff.answerKey === key) {
      handoff.itemKey = nextKey("h");
      if (handoff.status === "ready" && handoff.handoff) {
        state.items.push({
          key: handoff.itemKey, type: "handoff",
          handoff: handoff.handoff, priority: handoff.priority
        });
        cardKey = handoff.itemKey;
      } else {
        state.items.push({
          key: handoff.itemKey, type: "handoff-status",
          text: handoff.text || "", pending: handoff.status === "pending"
        });
      }
    }
    renderThread();
    if (cardKey) {
      // An explicit tap is a request for the card: show it even when the
      // answer card was being read further up.
      revealItem(cardKey, true, fromTop);
    } else {
      scrollEnd();
    }
  }

  // --- expert handoff ------------------------------------------------------

  // On an escalated final `display.handoff` is null until the model-written
  // brief is ready. A pending brief is polled in the background even before
  // the button is tapped; the endpoint only reads state, it never calls the
  // model. Every newer final supersedes the old poll.
  var HANDOFF_POLL_MS = 500;
  var HANDOFF_POLL_CAP_MS = 40000;

  function stopHandoffPoll() {
    if (state.handoffTimer) {
      window.clearTimeout(state.handoffTimer);
      state.handoffTimer = null;
    }
  }

  function scheduleHandoffPoll() {
    var handoff = state.handoff;
    if (!handoff || handoff.status !== "pending" || !state.conversationId) { return; }
    state.handoffTimer = window.setTimeout(pollHandoff, HANDOFF_POLL_MS);
  }

  function startHandoffPoll() {
    var handoff = state.handoff;
    if (!handoff) { return; }
    handoff.since = Date.now();
    scheduleHandoffPoll();
  }

  function pollHandoff() {
    state.handoffTimer = null;
    var handoff = state.handoff;
    var generation = state.generation;
    var cid = state.conversationId;
    if (!handoff || handoff.status !== "pending" || !cid) { return; }
    if (Date.now() - handoff.since >= HANDOFF_POLL_CAP_MS) {
      stopHandoffPoll();
      return;
    }

    fetch("/api/conversations/" + cid + "/handoff").then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (data) {
        if (!response.ok) { throw new Error("HTTP " + response.status); }
        return data;
      });
    }).then(function (data) {
      if (generation !== state.generation || handoff !== state.handoff) { return; }
      applyHandoff(data);
      if (handoff.status === "pending" && Date.now() - handoff.since < HANDOFF_POLL_CAP_MS) {
        scheduleHandoffPoll();
      } else {
        stopHandoffPoll();
      }
    }, function () {
      // A dropped poll is not a failed brief: keep trying until the cap.
      if (generation !== state.generation || handoff !== state.handoff) { return; }
      if (Date.now() - handoff.since < HANDOFF_POLL_CAP_MS) {
        scheduleHandoffPoll();
      } else {
        stopHandoffPoll();
      }
    });
  }

  function applyHandoff(data) {
    var handoff = state.handoff;
    if (!handoff || !data) { return; }
    var status = data.status;
    if (["pending", "ready", "failed", "none"].indexOf(status) >= 0) {
      handoff.status = status;
    }
    if (typeof data.text === "string") { handoff.text = data.text; }
    if (status === "ready" && data.handoff) {
      handoff.handoff = data.handoff;
    } else if (status !== "pending") {
      handoff.handoff = null;
    }
    handoff.priority = (data.answer && typeof data.answer.priority === "number")
      ? data.answer.priority : null;
    if (!handoff.itemKey) { return; }
    var item = findItem(handoff.itemKey);
    if (!item) { return; }
    // Capture the reading position before the card changes height.
    var follow = nearEnd();
    var fromTop = dom.scroll.scrollTop;
    var readySwap = false;
    if (handoff.status === "ready" && handoff.handoff) {
      // Same key: thread.js animates the placeholder into the card.
      item.type = "handoff";
      item.handoff = handoff.handoff;
      item.priority = handoff.priority;
      delete item.text;
      delete item.pending;
      readySwap = true;
    } else if (handoff.status === "pending" || handoff.status === "failed") {
      item.text = handoff.text || item.text || "";
      item.pending = handoff.status === "pending";
    }
    renderThread();
    if (readySwap) {
      revealItem(handoff.itemKey, follow, fromTop);
    }
    // Pending and failed updates leave the reading position alone: the box is
    // already where the tap put it, and a slow poll must not pull the view.
  }

  // A placeholder still says "preparing" when a newer final or a closed chat
  // means it can never resolve; remove it rather than wait forever.
  function dropPendingHandoffItem() {
    var handoff = state.handoff;
    if (!handoff || !handoff.itemKey) { return; }
    var item = findItem(handoff.itemKey);
    if (item && item.type === "handoff-status" && item.pending) {
      state.items = state.items.filter(function (row) { return row !== item; });
    }
    handoff.itemKey = null;
  }

  function supersedeHandoff() {
    dropPendingHandoffItem();
    stopHandoffPoll();
    state.handoff = null;
  }

  function recordHandoff(answerKey, body) {
    var display = (body && body.display) || {};
    var reply = (body && body.reply) || {};
    var statusBlock = display.handoff_status || null;
    var status = statusBlock && statusBlock.status;
    status = status || (display.handoff ? "ready" : "failed");
    supersedeHandoff();
    state.handoff = {
      answerKey: answerKey,
      itemKey: null,
      status: status,
      text: statusBlock ? statusBlock.text : null,
      handoff: display.handoff || null,
      priority: (reply.answer && typeof reply.answer.priority === "number")
        ? reply.answer.priority : null,
      since: 0
    };
    if (status === "pending") { startHandoffPoll(); }
  }

  function closeChat() {
    stopHandoffPoll();
    dropPendingHandoffItem();
    state.handoff = null;
    state.closed = true;
  }

  function appendReply(body) {
    state.display = body && body.display ? body.display : null;
    var display = state.display || {};
    var reply = (body && body.reply) || {};
    var key = nextKey("r");

    if (reply.type === "notice") {
      var notice = display.notice || {};
      state.items.push({ key: key, type: "notice", text: notice.text || reply.text || "" });
      state.quickKey = null;
      state.consentKey = null;
      if (body && body.closed === true) { closeChat(); }
      return;
    }
    if (reply.type === "question" && display.question) {
      state.items.push({
        key: key, type: "question", text: display.question.text,
        quick: display.quick_replies || [], answered: false
      });
      state.quickKey = key;
      state.consentKey = null;
      return;
    }
    if (reply.type === "consent_request") {
      if (display.consent) {
        state.items.push({ key: key, type: "consent", consent: display.consent, state: "open" });
        state.consentKey = key;
        state.quickKey = null;
        return;
      }
      if (reply.text) {
        // The consent card needs display.consent; if the server could not build
        // one, show the model's one-line request as a plain question so the
        // user is not left without anything to answer.
        state.items.push({ key: key, type: "question", text: reply.text, quick: [], answered: true });
        return;
      }
    }
    if (display.answer) {
      state.items.push({ key: key, type: "answer", answer: display.answer, expertSent: false });
      state.quickKey = null;
      state.consentKey = null;
      if (reply.type === "final") {
        // A newer final supersedes the old brief and its poll.
        if (display.answer.escalate) {
          recordHandoff(key, body);
        } else {
          supersedeHandoff();
        }
      }
      return;
    }
    state.items.push({ key: key, type: "error", text: t("error") });
  }

  function removeChecking() {
    state.items = state.items.filter(function (item) { return item.type !== "checking"; });
  }

  function request(descriptor) {
    state.request = descriptor;
    var generation = state.generation;
    var url = "/api/conversations";
    var body = descriptor.payload || {};

    if (descriptor.kind === "message") {
      url = "/api/conversations/" + state.conversationId + "/message";
      body = { text: descriptor.text };
    } else if (descriptor.kind === "consent") {
      url = "/api/conversations/" + state.conversationId + "/consent";
      body = { granted: descriptor.granted || [], refused: descriptor.refused || [] };
    }

    postJSON(url, body).then(function (data) {
      if (generation !== state.generation) { return; }
      removeChecking();
      if (descriptor.kind === "start") {
        adoptStart(data, descriptor.payload || {});
      } else {
        appendReply(data);
      }
      state.pending = false;
      setPending(false);
      refreshAll();
      scrollEnd();
    }, function () {
      if (generation !== state.generation) { return; }
      removeChecking();
      state.items.push({ key: nextKey("e"), type: "error", text: t("error") });
      state.pending = false;
      setPending(false);
      applyChrome();
      renderThread();
      renderVisibility();
      scrollEnd();
    });
  }

  function adoptStart(body, payload) {
    state.conversationId = body.conversation_id || null;
    state.thinking = body.thinking === true;
    if (LANGS.indexOf(body.language) >= 0 && body.language !== state.lang) {
      state.lang = body.language;
    }
    var items = [greetingItem()];
    var opening = body.opening || (payload && payload.text) || "";
    if (opening) { items.push({ key: nextKey("u"), type: "user", text: opening }); }
    var attachment = body.display && body.display.attachment;
    if (attachment) { items.push({ key: nextKey("a"), type: "attachment", attachment: attachment }); }
    state.items = items;
    state.quickKey = null;
    state.consentKey = null;
    appendReply(body);
  }

  function postJSON(url, body) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    }).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (data) {
        if (!response.ok) {
          throw new Error((data && data.error) || ("HTTP " + response.status));
        }
        return data;
      });
    });
  }

  function retry() {
    if (state.pending || !state.request) { return; }
    state.items = state.items.filter(function (item) { return item.type !== "error"; });
    state.items.push(checkingItem());
    setPending(true);
    renderThread();
    scrollEnd();
    request(state.request);
  }

  var handlers = {
    onQuickReply: function (text) {
      if (state.pending || state.closed) { return; }
      sendMessage(text);
    },
    onConsent: onConsent,
    onExpert: onExpert,
    onRetry: retry,
    onNewChat: function () { startNew(); }
  };

  // --- sheets, menus, composer --------------------------------------------

  function toggleMenu(button, menu) {
    var opening = menu.hidden || menu.classList.contains("menu-leaving");
    closeMenus();
    if (opening) {
      if (menu._hideTimer) { window.clearTimeout(menu._hideTimer); menu._hideTimer = null; }
      menu.classList.remove("menu-leaving");
      menu.hidden = false;
      button.setAttribute("aria-expanded", "true");
    }
  }

  function hideMenu(menu) {
    if (menu.hidden || menu.classList.contains("menu-leaving")) { return; }
    if (reduced()) { menu.hidden = true; return; }
    menu.classList.add("menu-leaving");
    menu._hideTimer = window.setTimeout(function () {
      menu.hidden = true;
      menu.classList.remove("menu-leaving");
      menu._hideTimer = null;
    }, 120);
  }

  function closeMenus() {
    hideMenu(dom.langMenu);
    dom.langButton.setAttribute("aria-expanded", "false");
  }

  // The composer is a textarea: grow it to fit its text, capped by the CSS
  // max-height, after which the browser adds a scrollbar. Measure with the
  // transition off, restore the rendered height, then set the target so the
  // height change itself animates (and shortened messages shrink again).
  function resizeComposer() {
    var style = window.getComputedStyle(dom.input);
    var border = parseFloat(style.borderTopWidth) + parseFloat(style.borderBottomWidth);
    var height = dom.input.getBoundingClientRect().height;
    dom.input.classList.add("no-anim");
    dom.input.style.height = "auto";
    var target = dom.input.scrollHeight + border;
    dom.input.style.height = height + "px";
    void dom.input.offsetHeight;
    dom.input.classList.remove("no-anim");
    dom.input.style.height = target + "px";
  }

  function submitComposer(event) {
    event.preventDefault();
    if (state.pending || state.closed) { return; }
    var text = dom.input.value.trim();
    if (!text) { return; }
    syncAttachment();
    dom.input.value = "";
    resizeComposer();
    if (!state.started) {
      var payload = {
        source: "free",
        text: text,
        language: state.lang,
        audience: state.audience
      };
      if (state.attachment) {
        payload.attachment = {
          kind: state.attachment.kind,
          sender: state.attachment.sender,
          body: state.attachment.body
        };
      }
      begin(payload, { text: text });
      return;
    }
    sendMessage(text);
  }

  function cacheDom() {
    dom.appTitle = document.getElementById("app-title");
    dom.proto = document.getElementById("app-proto");
    dom.infoButton = document.getElementById("info-button");
    dom.langButton = document.getElementById("lang-button");
    dom.langCode = document.getElementById("lang-code");
    dom.langMenu = document.getElementById("lang-menu");
    dom.newChat = document.getElementById("new-chat");
    dom.newChatLabel = document.getElementById("new-chat-label");

    dom.scroll = document.getElementById("scroll");
    dom.thread = document.getElementById("thread");
    dom.startTop = document.getElementById("start-top");
    dom.startAttach = document.getElementById("start-attach");
    dom.switchGroup = document.getElementById("audience-switch");
    dom.examplesButton = document.getElementById("examples-button");
    dom.examplesLabel = document.getElementById("examples-label");
    dom.examplesReveal = document.getElementById("examples-reveal");
    dom.examplesMenu = document.getElementById("examples-menu");
    dom.carefulTitle = document.getElementById("careful-title");
    dom.carefulHint = document.getElementById("careful-hint");
    dom.thinkingToggle = document.getElementById("thinking-toggle");
    dom.attachTitle = document.getElementById("attach-title");
    dom.attachOptional = document.getElementById("attach-optional");
    dom.attachCard = document.getElementById("attach-card");
    dom.attachToggle = document.getElementById("attach-toggle");
    dom.attachKindLabel = document.getElementById("attach-kind-label");
    dom.attachKinds = document.getElementById("attach-kinds");
    dom.attachSenderLabel = document.getElementById("attach-sender-label");
    dom.attachSender = document.getElementById("attach-sender");
    dom.attachBodyLabel = document.getElementById("attach-body-label");
    dom.attachBody = document.getElementById("attach-body");

    dom.composer = document.getElementById("composer");
    dom.input = document.getElementById("message-input");
    dom.sendButton = document.getElementById("send-button");

    dom.sideTitle = document.getElementById("side-title");
    dom.sideBody = document.getElementById("side-body");
    dom.side = document.querySelector(".side");
    dom.helpCard = document.getElementById("help-card");
    dom.helpTitle = document.getElementById("help-title");
    dom.helpList = document.getElementById("help-list");
    dom.helpBusiness = document.getElementById("help-business");
    dom.infoSheet = document.getElementById("info-sheet");
    dom.infoSheetTitle = document.getElementById("info-sheet-title");
    dom.sheetBody = document.getElementById("sheet-body");
    dom.sheetClose = document.querySelector('#info-sheet [data-close]');
  }

  function fillIcons(root) {
    Array.prototype.forEach.call(root.querySelectorAll("[data-icon]"), function (slot) {
      if (slot.firstChild) { return; }
      slot.appendChild(icon(slot.getAttribute("data-icon"), "sm"));
    });
  }

  function wire() {
    dom.langButton.addEventListener("click", function (event) {
      event.stopPropagation();
      if (state.started) { return; }
      toggleMenu(dom.langButton, dom.langMenu);
    });
    dom.langMenu.addEventListener("click", function (event) {
      var button = event.target.closest("[data-lang]");
      if (!button) { return; }
      var lang = button.getAttribute("data-lang");
      if (LANGS.indexOf(lang) < 0 || state.started) { return; }
      state.lang = lang;
      state.items = [greetingItem()];
      closeMenus();
      refreshAll();
    });

    dom.newChat.addEventListener("click", function () {
      if (!state.started) { return; }
      closeMenus();
      startNew();
    });

    document.addEventListener("click", function (event) {
      if (!event.target.closest(".menu-wrap")) { closeMenus(); }
      if (!event.target.closest(".start-tools") && !event.target.closest(".examples-reveal")) {
        closeExamples();
      }
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") {
        closeMenus();
        closeExamples();
      }
    });

    dom.infoButton.addEventListener("click", function () {
      dom.infoSheet.showModal();
    });
    Array.prototype.forEach.call(document.querySelectorAll("[data-close]"), function (button) {
      button.addEventListener("click", function () {
        var dialog = document.getElementById(button.getAttribute("data-close"));
        if (dialog && dialog.open) { dialog.close(); }
      });
    });

    dom.switchGroup.addEventListener("click", function (event) {
      var button = event.target.closest(".switch-button");
      if (!button || state.started) { return; }
      var audience = button.getAttribute("data-audience");
      if (audience === state.audience) { return; }
      state.audience = audience;
      state.items = [greetingItem()];
      renderThread();
      renderStart();
    });
    dom.thinkingToggle.addEventListener("change", function () {
      if (!state.started) { state.thinking = dom.thinkingToggle.checked; }
    });

    dom.examplesButton.addEventListener("click", function () {
      if (state.started) { return; }
      setExamplesOpen(!state.examplesOpen);
    });

    dom.attachKinds.addEventListener("change", syncAttachment);
    dom.attachSender.addEventListener("input", syncAttachment);
    dom.attachBody.addEventListener("input", syncAttachment);
    dom.attachToggle.addEventListener("click", function () {
      setAttachOpen(dom.attachCard.getAttribute("data-open") !== "true");
    });

    dom.composer.addEventListener("submit", submitComposer);
    dom.input.addEventListener("input", resizeComposer);
    // Enter sends; Shift+Enter (or an IME candidate) still inserts a newline.
    dom.input.addEventListener("keydown", function (event) {
      if (event.key !== "Enter" || event.shiftKey || event.isComposing) { return; }
      event.preventDefault();
      dom.composer.requestSubmit();
    });
    window.addEventListener("resize", resizeComposer);
  }

  function deepLink() {
    var params = new URLSearchParams(window.location.search);
    var caseId = params.get("case");
    if (!caseId) { return; }
    // `?case=` is a dev hook. A public server refuses source=dev, so ask the
    // health endpoint first and keep the normal start screen for a stale or
    // shared link instead of showing an error.
    fetch("/api/health").then(function (response) {
      return response.json();
    }).then(function (data) {
      if (state.started || (data && data.public)) { return; }
      begin({ source: "dev", case_id: caseId }, {});
    }).catch(function () {});
  }

  function boot() {
    cacheDom();
    fillIcons(document);
    wire();
    state.lang = detectLanguage();
    state.items = [greetingItem()];
    refreshAll();
    setPending(false);
    resizeComposer();
    if (document.fonts && document.fonts.ready) {
      document.fonts.ready.then(function () {
        if (dom.switchGroup) { placeThumb(dom.switchGroup); }
        resizeComposer();
      });
    }
    deepLink();
  }

  boot();
})();
