/* Thread — the shared conversation renderer for the demo (`/`) and the lab.
 *
 * The server sends a `display` block (docs/UI_SPEC.md section 5) with every
 * reply; this module renders it. Nothing here decides content, language or
 * risk: it lays out the items it is given, in order, and reports taps back.
 *
 * ---------------------------------------------------------------------------
 * API
 * ---------------------------------------------------------------------------
 *
 *   Thread.render(container, items, handlers, labels)
 *
 *     container  the scrolling element (the page sets aria-live="polite")
 *     items      array of item objects, oldest first, each with a unique
 *                string `key`. `render` reconciles by key: unchanged items are
 *                left alone (so `open` state and the checking timer survive),
 *                changed items are rebuilt in place, missing ones are removed.
 *     handlers   { onQuickReply(text, key), onConsent(key, granted),
 *                  onExpert(key), onRetry(key), onNewChat(key) } — all optional
 *     labels     UI chrome strings in the conversation language. Content
 *                strings (headline, consent title, handoff fields...) always
 *                come from `display`, never from here. See DEFAULT_LABELS for
 *                the keys and the %s / %d placeholders.
 *
 *   Thread.clear(container)      empty the thread and forget its state
 *   Thread.scrollToEnd(container)  scroll the thread to the newest item
 *   Thread.DEFAULT_LABELS        the English fallbacks, for reference
 *
 * ---------------------------------------------------------------------------
 * Item types
 * ---------------------------------------------------------------------------
 *
 *   {key, type:"greeting", text}
 *       Assistant bubble used once, before the conversation starts.
 *
 *   {key, type:"user", text, who?}
 *       The user's own message, right aligned in the accent colour. `who`
 *       overrides the speaker label ("You" by default); the lab uses it for
 *       simulated-user bubbles.
 *
 *   {key, type:"attachment", attachment}
 *       `attachment` is display.attachment: {kind, kind_label, sender, time,
 *       body, checks:[{tone:"warn"|"ok"|"unknown", text}]}. The body is
 *       untrusted text written by the sender: it is drawn as plain text, line
 *       breaks kept, and no link in it is made clickable.
 *
 *   {key, type:"checking", startedAt}
 *       Three-dot indicator; after 3 s it adds the elapsed seconds
 *       ("Checking… 6 s"). `startedAt` is Date.now() in ms. The page adds one
 *       per pending request and removes it when the reply arrives.
 *
 *   {key, type:"question", text, quick:[string], answered:boolean}
 *       Assistant question plus, while `answered` is false, one chip per
 *       quick reply. A tap calls handlers.onQuickReply(text, key).
 *
 *   {key, type:"consent", consent, state, receipt}
 *       `consent` is display.consent: {title, purpose, items:[{field,label}],
 *       allow, deny, fine}. While state is "open": title, purpose, Allow /
 *       Don't allow, fine print; a tap calls handlers.onConsent(key, granted)
 *       with the field tokens left for the page to send. When the page sets
 *       state to "allowed" or "refused" the card collapses to a one-line
 *       receipt built from `receipt`.
 *
 *   {key, type:"receipt", tone:"allowed"|"refused", text}
 *       A standalone receipt line, for a consent answered elsewhere.
 *
 *   {key, type:"answer", answer, expertSent}
 *       `answer` is display.answer: {urgency, urgency_label, headline, reason,
 *       steps, more, escalate, expert_label, why:{bullets, sources, note}}.
 *       `more` holds advice sentences the card would otherwise drop; the
 *       first three are always visible and the rest sit behind a "Show more"
 *       button, unless one of them carries an emergency instruction. The
 *       expert button appears when escalate is true and calls
 *       handlers.onExpert(key); set expertSent once the request is sent and
 *       the button is replaced by a confirmation line.
 *
 *   {key, type:"handoff", handoff, priority?}
 *       `handoff` is display.handoff: {target_label, situation, checked,
 *       consent, advice, priority, labels, confirm}. Marked "(demo)". An
 *       optional integer `priority` (1-5) adds one row after the readable
 *       priority label; absent or null means no row.
 *
 *   {key, type:"handoff-status", text, pending}
 *       Placeholder in the handoff card's place while the brief is still
 *       pending (the server's text plus three animated dots) or failed (the
 *       server's text, no dots). The page swaps it, under the same key, for a
 *       "handoff" item when the brief becomes ready.
 *
 *   {key, type:"notice", text}
 *       A neutral assistant bubble for a courtesy notice on a closed chat,
 *       with a "Start a new chat" button (handlers.onNewChat(key)). Never an
 *       answer card and never an error.
 *
 *   {key, type:"error", text}
 *       Friendly error line with a "Try again" button (handlers.onRetry(key)).
 *       Never a stack trace: the page passes its own sentence.
 *
 * Both pages must load tokens.css (tokens, font, svg.icon base) before
 * thread.css. Classic script, no modules: sets window.Thread.
 */
(function () {
  "use strict";

  var DEFAULT_LABELS = {
    you: "You",
    assistant: "Assistant",
    checking: "Checking…",
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
  };

  var registry = new WeakMap();

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

  function fmt(pattern) {
    var args = Array.prototype.slice.call(arguments, 1);
    var i = 0;
    return String(pattern == null ? "" : pattern).replace(/%[sd]/g, function () {
      var value = args[i];
      i += 1;
      return value == null ? "" : String(value);
    });
  }

  function label(st, key) {
    var value = st.labels[key];
    return value == null ? (DEFAULT_LABELS[key] || "") : value;
  }

  function reduced() {
    return !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  }

  function ghostAt(container, node, left, top, width) {
    var ghost = node.cloneNode(true);
    ghost.removeAttribute("data-key");
    ghost.classList.remove("enter", "update");
    ghost.classList.add("swap-ghost");
    ghost.setAttribute("data-ghost", "1");
    ghost.setAttribute("aria-hidden", "true");
    ghost.inert = true;
    Array.prototype.forEach.call(ghost.querySelectorAll("[data-checking]"), function (n) {
      n.removeAttribute("data-checking");
    });
    ghost.style.left = left + "px";
    ghost.style.top = top + "px";
    ghost.style.width = width + "px";
    container.appendChild(ghost);
    return ghost;
  }

  // A replaced item never shows two texts at once: the old content fades out
  // while the box animates to its new height, and only then does the new
  // content fade in. Used by consent card -> receipt, expert button -> sent
  // line, and the checking bubble's last frame.
  function swapIn(container, oldNode, fresh) {
    var left = oldNode.offsetLeft;
    var top = oldNode.offsetTop;
    var width = oldNode.offsetWidth;
    var height = oldNode.offsetHeight;
    oldNode.replaceWith(fresh);
    if (reduced() || !height) {
      fresh.classList.add("update");
      return;
    }
    var hold = 120;
    var slide = 180;
    var ghost = ghostAt(container, oldNode, left, top, width);
    var natural = fresh.getBoundingClientRect().height;
    fresh.style.height = height + "px";
    fresh.style.overflow = "hidden";
    fresh.style.opacity = "0";
    void fresh.offsetHeight;
    var grow = fresh.animate([
      { height: height + "px" },
      { height: natural + "px" }
    ], { duration: hold + 40, easing: "cubic-bezier(.16, 1, .3, 1)", fill: "both" });
    var out = ghost.animate([{ opacity: 1 }, { opacity: 0 }],
      { duration: hold, easing: "linear", fill: "forwards" });
    var fadeIn = fresh.animate([{ opacity: 0 }, { opacity: 1 }],
      { duration: slide, delay: hold, easing: "ease", fill: "both" });
    function done() {
      fresh.removeAttribute("style");
      ghost.remove();
      grow.cancel();
      fadeIn.cancel();
    }
    Promise.all([grow.finished, fadeIn.finished]).then(done, done);
    out.finished.catch(function () {});
  }

  function fadeOut(container, node) {
    var left = node.offsetLeft;
    var top = node.offsetTop;
    var width = node.offsetWidth;
    var height = node.offsetHeight;
    if (reduced() || !height) {
      node.remove();
      return;
    }
    var ghost = ghostAt(container, node, left, top, width);
    node.remove();
    var fade = ghost.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 180, easing: "ease" });
    fade.finished.then(function () { ghost.remove(); }, function () { ghost.remove(); });
  }

  // Native <details> opens in one frame. Animate the shell height and the
  // body's fade instead, and keep the open state in thread state so a
  // rebuild of the answer card does not close it.
  function toggleWhy(details, st, key) {
    if (details.getAttribute("data-busy") === "1") { return; }
    var body = details.querySelector(".why-body");
    var open = !details.open;
    if (reduced()) {
      details.open = open;
      st.open.set(key, open);
      return;
    }
    details.setAttribute("data-busy", "1");
    var start = details.getBoundingClientRect().height;
    details.style.overflow = "hidden";
    var closed = 0;
    if (!open) {
      details.open = false;
      closed = details.getBoundingClientRect().height;
      details.open = true;
    } else {
      details.open = true;
    }
    var end = open ? details.getBoundingClientRect().height : closed;
    var grow = details.animate([
      { height: start + "px" },
      { height: end + "px" }
    ], { duration: 230, easing: "cubic-bezier(.16, 1, .3, 1)" });
    var fade = body ? body.animate(open
      ? [{ opacity: 0, transform: "translateY(-4px)" }, { opacity: 1, transform: "none" }]
      : [{ opacity: 1, transform: "none" }, { opacity: 0, transform: "translateY(-4px)" }],
    { duration: 180, easing: "ease", fill: "both" }) : null;
    function done() {
      details.style.overflow = "";
      details.open = open;
      st.open.set(key, open);
      details.removeAttribute("data-busy");
      if (fade) { fade.cancel(); }
    }
    grow.finished.then(done, done);
  }

  // An emergency instruction must not sit behind a second expander. The
  // answer card shows every `more` sentence when one of them matches this;
  // otherwise the first three are visible and the rest are behind the button.
  var URGENT = /(112|911|hätänumero|hätänumer|nödnummer|emergency|ambulance|ambulanssi|ambulans|älä soita|don't call|do not call|ringe inte|\bheti\b|välittömästi|immediately|right away|omedelbart|vaarassa|in danger|i fara)/i;

  function isUrgent(sentences) {
    return sentences.some(function (s) { return URGENT.test(s); });
  }

  function toggleMore(node, button, st, key) {
    if (node.getAttribute("data-busy") === "1") { return; }
    var open = node.hidden;
    function finish() {
      node.hidden = !open;
      button.textContent = label(st, open ? "showLess" : "showMore");
      button.setAttribute("aria-expanded", open ? "true" : "false");
      st.open.set(key, open);
      node.removeAttribute("data-busy");
    }
    if (reduced()) {
      finish();
      return;
    }
    node.setAttribute("data-busy", "1");
    node.hidden = false;
    var height = node.getBoundingClientRect().height;
    node.style.overflow = "hidden";
    var grow = node.animate([
      { height: (open ? 0 : height) + "px", opacity: open ? 0 : 1 },
      { height: (open ? height : 0) + "px", opacity: open ? 1 : 0 }
    ], { duration: 230, easing: "cubic-bezier(.16, 1, .3, 1)", fill: "both" });
    function done() {
      node.style.overflow = "";
      grow.cancel();
      finish();
    }
    grow.finished.then(done, done);
  }

  function itemRoot(cls) {
    return el("div", "item " + cls);
  }

  function who(st, side, text) {
    var value = text == null
      ? (side === "user" ? label(st, "you") : label(st, "assistant"))
      : text;
    return el("div", "who who-" + side, value);
  }

  // --- builders ------------------------------------------------------------

  var BUILD = {
    greeting: function (item, st) {
      var root = itemRoot("item-bot");
      root.appendChild(who(st, "bot"));
      var bubble = el("div", "bubble bubble-bot");
      bubble.appendChild(el("p", null, item.text));
      root.appendChild(bubble);
      return root;
    },

    user: function (item, st) {
      var root = itemRoot("item-user");
      var speaker = item.who || label(st, "you");
      root.appendChild(who(st, "user", speaker));
      var bubble = el("div", "bubble bubble-user");
      bubble.appendChild(el("p", null, item.text));
      root.appendChild(bubble);
      return root;
    },

    attachment: function (item, st) {
      var att = item.attachment || {};
      var root = itemRoot("item-user item-attachment");
      var card = el("section", "attachment");
      card.setAttribute("role", "group");
      card.setAttribute("aria-label", label(st, "attachmentAria"));

      var head = el("div", "att-head");
      head.appendChild(icon(window.Icons.forKind(att.kind), "sm"));
      var headText = el("span", "att-head-text");
      var kind = att.kind_label || "";
      var sender = att.sender || "";
      var line = sender ? fmt(label(st, "attachmentFrom"), kind, sender) : kind;
      headText.appendChild(el("b", null, line));
      if (att.time) { headText.appendChild(el("span", "att-time", " · " + att.time)); }
      head.appendChild(headText);
      card.appendChild(head);

      var body = el("p", "att-body", att.body || "");
      card.appendChild(body);

      (att.checks || []).forEach(function (check) {
        var tone = check && check.tone === "warn" ? "warn" : (check.tone === "ok" ? "ok" : "unknown");
        var row = el("div", "att-check att-check-" + tone);
        row.appendChild(icon(tone === "warn" ? "alert" : (tone === "ok" ? "check" : "help"), "sm"));
        row.appendChild(el("span", null, check.text || ""));
        card.appendChild(row);
      });

      root.appendChild(card);
      return root;
    },

    checking: function (item, st) {
      var root = itemRoot("item-bot");
      root.setAttribute("role", "status");
      root.setAttribute("aria-label", label(st, "checkingAria"));
      root.appendChild(who(st, "bot"));
      var bubble = el("div", "bubble bubble-bot bubble-checking");
      bubble.setAttribute("data-checking", "1");
      bubble.setAttribute("data-started", String(Number(item.startedAt) || Date.now()));
      var dots = el("span", "dots");
      dots.setAttribute("aria-hidden", "true");
      dots.appendChild(el("i", "dot"));
      dots.appendChild(el("i", "dot"));
      dots.appendChild(el("i", "dot"));
      bubble.appendChild(el("span", "checking-label", label(st, "checking")));
      bubble.appendChild(dots);
      var elapsed = el("span", "checking-elapsed");
      elapsed.setAttribute("data-elapsed", "1");
      elapsed.setAttribute("aria-hidden", "true");
      bubble.appendChild(elapsed);
      root.appendChild(bubble);
      return root;
    },

    question: function (item, st) {
      var root = itemRoot("item-bot");
      root.appendChild(who(st, "bot"));
      var bubble = el("div", "bubble bubble-bot");
      bubble.appendChild(el("p", null, item.text));
      root.appendChild(bubble);

      var quick = Array.isArray(item.quick) ? item.quick : [];
      if (quick.length && !item.answered) {
        var chips = el("div", "chips");
        chips.setAttribute("role", "group");
        chips.setAttribute("aria-label", label(st, "quickAria"));
        quick.forEach(function (text) {
          var chip = el("button", "chip", text);
          chip.type = "button";
          chip.addEventListener("click", function () {
            var chips = chip.parentNode;
            var fire = function () {
              st.handlers.onQuickReply && st.handlers.onQuickReply(text, item.key);
            };
            if (!chips || chips.getAttribute("data-leaving") === "1") { return; }
            if (reduced()) { fire(); return; }
            chips.setAttribute("data-leaving", "1");
            var height = chips.offsetHeight;
            if (!height) { fire(); return; }
            // Collapse the row, not just fade it: the bubble that follows
            // must not land under a row of chips.
            chips.style.overflow = "hidden";
            var margin = getComputedStyle(chips).marginTop;
            var out = chips.animate([
              { height: height + "px", marginTop: margin, opacity: 1 },
              { height: "0px", marginTop: "0px", opacity: 0 }
            ], { duration: 140, easing: "cubic-bezier(.16, 1, .3, 1)" });
            function finish() {
              // Keep the collapsed row: the item is rebuilt without chips in
              // the same tick, and a ghost of this node must not carry them.
              chips.style.height = "0px";
              chips.style.marginTop = "0px";
              chips.style.opacity = "0";
              chips.style.overflow = "hidden";
              fire();
            }
            out.finished.then(finish, finish);
          });
          chips.appendChild(chip);
        });
        root.appendChild(chips);
      }
      return root;
    },

    consent: function (item, st) {
      var consent = item.consent || {};
      if (item.state === "allowed" || item.state === "refused") {
        return BUILD.receipt({ tone: item.state, text: item.receipt }, st);
      }
      var root = itemRoot("item-bot");
      root.appendChild(who(st, "bot"));
      var card = el("section", "consent");
      card.setAttribute("role", "group");
      card.setAttribute("aria-label", label(st, "consentAria"));

      var title = el("h3", "consent-title");
      title.appendChild(icon("shield", "sm"));
      title.appendChild(el("span", null, consent.title || ""));
      card.appendChild(title);

      if (consent.purpose) { card.appendChild(el("p", "consent-purpose", consent.purpose)); }

      var items = Array.isArray(consent.items) ? consent.items : [];
      if (items.length > 1) {
        var list = el("ul", "consent-items");
        items.forEach(function (row) {
          list.appendChild(el("li", null, row && row.label ? row.label : ""));
        });
        card.appendChild(list);
      }

      var row = el("div", "row");
      var allow = el("button", "btn btn-primary", consent.allow || "");
      allow.type = "button";
      allow.addEventListener("click", function () {
        st.handlers.onConsent && st.handlers.onConsent(item.key, true);
      });
      var deny = el("button", "btn btn-secondary", consent.deny || "");
      deny.type = "button";
      deny.addEventListener("click", function () {
        st.handlers.onConsent && st.handlers.onConsent(item.key, false);
      });
      row.appendChild(allow);
      row.appendChild(deny);
      card.appendChild(row);
      if (consent.fine) { card.appendChild(el("p", "fine", consent.fine)); }
      root.appendChild(card);
      return root;
    },

    receipt: function (item, st) {
      var tone = item.tone === "refused" ? "refused" : "allowed";
      var root = itemRoot("item-receipt");
      var line = el("div", "receipt receipt-" + tone);
      line.appendChild(icon(tone === "allowed" ? "check" : "x", "sm"));
      line.appendChild(el("span", null, item.text || ""));
      root.appendChild(line);
      return root;
    },

    answer: function (item, st) {
      var answer = item.answer || {};
      var urgency = ["immediate", "today", "routine", "none"].indexOf(answer.urgency) >= 0
        ? answer.urgency : "routine";
      var root = itemRoot("item-stretch");
      var card = el("article", "answer answer-" + urgency);
      card.setAttribute("aria-label", label(st, "answerAria"));

      card.appendChild(el("span", "urgency urgency-" + urgency, answer.urgency_label || ""));
      card.appendChild(el("h2", "answer-headline", answer.headline || ""));
      if (answer.reason) { card.appendChild(el("p", "answer-reason", answer.reason)); }

      var steps = Array.isArray(answer.steps) ? answer.steps : [];
      if (steps.length) {
        var list = el("ol", "answer-steps");
        list.setAttribute("aria-label", label(st, "stepsAria"));
        steps.forEach(function (step) { list.appendChild(el("li", null, step)); });
        card.appendChild(list);
      }

      var more = Array.isArray(answer.more) ? answer.more.filter(Boolean) : [];
      if (more.length) {
        var urgent = isUrgent(more);
        var visible = urgent ? more : more.slice(0, 3);
        var rest = urgent ? [] : more.slice(3);
        card.appendChild(el("p", "answer-more", visible.join(" ")));
        if (rest.length) {
          var moreKey = String(item.key) + ":more";
          var open = st.open.get(moreKey) === true;
          var hidden = el("p", "answer-more answer-more-rest", rest.join(" "));
          hidden.hidden = !open;
          card.appendChild(hidden);
          var toggle = el("button", "more-toggle", label(st, open ? "showLess" : "showMore"));
          toggle.type = "button";
          toggle.setAttribute("aria-expanded", open ? "true" : "false");
          toggle.addEventListener("click", function () {
            toggleMore(hidden, toggle, st, moreKey);
          });
          card.appendChild(toggle);
        }
      }

      if (answer.escalate) {
        if (item.expertSent) {
          var sent = el("p", "expert-sent");
          sent.setAttribute("role", "status");
          sent.appendChild(icon("check", "sm"));
          sent.appendChild(el("span", null, label(st, "expertSent")));
          card.appendChild(sent);
        } else {
          var expert = el("button", "expert");
          expert.type = "button";
          expert.appendChild(icon("user", "sm"));
          expert.appendChild(el("span", null, answer.expert_label || ""));
          expert.addEventListener("click", function () {
            st.handlers.onExpert && st.handlers.onExpert(item.key);
          });
          card.appendChild(expert);
        }
      }

      var why = answer.why || {};
      var details = el("details", "why");
      var whyKey = String(item.key);
      var open = st.open.get(whyKey) === true;
      if (open) { details.open = true; }
      var summary = el("summary", "why-summary");
      summary.appendChild(el("span", null, label(st, "why")));
      summary.appendChild(icon("chevron-down", "sm"));
      summary.addEventListener("click", function (event) {
        event.preventDefault();
        toggleWhy(details, st, whyKey);
      });
      details.appendChild(summary);

      var body = el("div", "why-body");
      var bullets = Array.isArray(why.bullets) ? why.bullets : [];
      if (bullets.length) {
        var ul = el("ul", "why-list");
        bullets.forEach(function (b) { ul.appendChild(el("li", null, b)); });
        body.appendChild(ul);
      }
      var sources = Array.isArray(why.sources) ? why.sources.filter(Boolean) : [];
      if (sources.length) {
        body.appendChild(el("p", "why-sources", fmt(label(st, "basedOn"), sources.join(" · "))));
      }
      if (why.note) { body.appendChild(el("p", "why-note", why.note)); }
      details.appendChild(body);
      card.appendChild(details);

      root.appendChild(card);
      return root;
    },

    handoff: function (item, st) {
      var handoff = item.handoff || {};
      var labels = handoff.labels || {};
      var root = itemRoot("item-stretch");
      var card = el("section", "handoff");
      card.setAttribute("aria-label", label(st, "handoffAria"));

      var head = el("div", "handoff-head");
      head.appendChild(el("h3", "handoff-title", label(st, "handoffTitle")));
      head.appendChild(el("span", "handoff-demo", label(st, "demoNote")));
      card.appendChild(head);
      if (handoff.target_label) { card.appendChild(el("p", "handoff-target", handoff.target_label)); }

      var dl = el("dl", "handoff-fields");
      [["situation", "situation"], ["checked", "checked"], ["consent", "consent"],
        ["advice", "advice"], ["priority", "priority"]].forEach(function (pair) {
        var value = handoff[pair[0]];
        if (!value) { return; }
        dl.appendChild(el("dt", null, labels[pair[1]] || ""));
        dl.appendChild(el("dd", null, value));
      });
      var number = item.priority;
      if (typeof number === "number" && number >= 1 && number <= 5) {
        dl.appendChild(el("dt", null, label(st, "expertPriority")));
        dl.appendChild(el("dd", "handoff-number", fmt(label(st, "expertPriorityValue"), number)));
      }
      card.appendChild(dl);

      if (handoff.confirm) {
        var confirm = el("p", "handoff-confirm");
        confirm.appendChild(icon("check", "sm"));
        confirm.appendChild(el("span", null, handoff.confirm));
        card.appendChild(confirm);
      }
      root.appendChild(card);
      return root;
    },

    "handoff-status": function (item, st) {
      var root = itemRoot("item-stretch");
      var card = el("section", "handoff handoff-wait");
      card.setAttribute("role", "status");
      card.setAttribute("aria-label", label(st, "handoffAria"));

      var head = el("div", "handoff-head");
      head.appendChild(el("h3", "handoff-title", label(st, "handoffTitle")));
      head.appendChild(el("span", "handoff-demo", label(st, "demoNote")));
      card.appendChild(head);

      var line = el("p", "handoff-wait-text");
      line.appendChild(el("span", null, item.text || ""));
      if (item.pending) {
        var dots = el("span", "dots");
        dots.setAttribute("aria-hidden", "true");
        dots.appendChild(el("i", "dot"));
        dots.appendChild(el("i", "dot"));
        dots.appendChild(el("i", "dot"));
        line.appendChild(dots);
      }
      card.appendChild(line);
      root.appendChild(card);
      return root;
    },

    notice: function (item, st) {
      var root = itemRoot("item-bot");
      root.appendChild(who(st, "bot"));
      var bubble = el("div", "bubble bubble-bot");
      bubble.appendChild(el("p", null, item.text || ""));
      root.appendChild(bubble);
      var actions = el("div", "notice-actions");
      var button = el("button", "chip", label(st, "newChat"));
      button.type = "button";
      button.addEventListener("click", function () {
        st.handlers.onNewChat && st.handlers.onNewChat(item.key);
      });
      actions.appendChild(button);
      root.appendChild(actions);
      return root;
    },

    error: function (item, st) {
      var root = itemRoot("item-bot");
      var box = el("div", "thread-error");
      box.setAttribute("role", "alert");
      box.appendChild(icon("alert", "sm"));
      box.appendChild(el("span", null, item.text || label(st, "error")));
      var retry = el("button", "chip chip-retry", label(st, "retry"));
      retry.type = "button";
      retry.addEventListener("click", function () {
        st.handlers.onRetry && st.handlers.onRetry(item.key);
      });
      box.appendChild(retry);
      root.appendChild(box);
      return root;
    }
  };

  // --- checking timer ------------------------------------------------------

  function tick(container, st) {
    var nodes = container.querySelectorAll("[data-checking]");
    var now = Date.now();
    Array.prototype.forEach.call(nodes, function (node) {
      var started = Number(node.getAttribute("data-started")) || now;
      var secs = Math.max(0, Math.floor((now - started) / 1000));
      var out = node.querySelector("[data-elapsed]");
      if (out) { out.textContent = secs >= 3 ? " " + fmt(label(st, "seconds"), secs) : ""; }
    });
    if (!nodes.length && st.timer) {
      clearInterval(st.timer);
      st.timer = null;
    }
    if (nodes.length && !st.timer) {
      st.timer = setInterval(function () { tick(container, st); }, 1000);
    }
  }

  // --- reconcile -----------------------------------------------------------

  function build(item, key, st) {
    var make = BUILD[item.type];
    var node;
    if (make) {
      node = make(item, st);
    } else {
      node = BUILD.error({ key: key, text: "" }, st);
    }
    node.setAttribute("data-key", key);
    return node;
  }

  function syncOrder(container, ordered) {
    var current = Array.prototype.slice.call(container.children).filter(function (node) {
      return !node.hasAttribute("data-ghost");
    });
    var same = current.length === ordered.length;
    if (same) {
      for (var i = 0; i < ordered.length; i += 1) {
        if (current[i] !== ordered[i]) { same = false; break; }
      }
    }
    if (same) { return; }
    // Insert only nodes that are new or out of place. Re-appending an
    // unchanged item restarts its enter animation (the class stays on the
    // node), which made the whole thread blink after every action.
    var cursor = container.firstElementChild;
    ordered.forEach(function (node) {
      while (cursor && cursor !== node && !cursor.hasAttribute("data-ghost") &&
             ordered.indexOf(cursor) === -1) {
        cursor = cursor.nextElementSibling;
      }
      if (cursor === node) {
        cursor = cursor.nextElementSibling;
      } else {
        container.insertBefore(node, cursor);
      }
    });
  }

  function render(container, items, handlers, labels) {
    if (!container) { return; }
    var st = registry.get(container);
    if (!st) {
      st = { nodes: new Map(), open: new Map(), handlers: {}, labels: {}, timer: null };
      registry.set(container, st);
    }
    if (handlers) { st.handlers = handlers; }
    st.labels = Object.assign({}, DEFAULT_LABELS, labels || {});

    var list = Array.isArray(items) ? items : [];
    var alive = new Set();
    var ordered = [];
    var entered = [];

    list.forEach(function (item, index) {
      if (!item || typeof item !== "object") { return; }
      var key = String(item.key == null ? "i" + index : item.key);
      alive.add(key);
      var sig = JSON.stringify(item);
      var rec = st.nodes.get(key);
      if (!rec) {
        rec = { sig: null, el: null };
        st.nodes.set(key, rec);
      }
      if (rec.sig !== sig) {
        var fresh = build(item, key, st);
        if (!rec.el) {
          fresh.classList.add("enter");
          entered.push(fresh);
        } else if (rec.el.parentNode) {
          swapIn(container, rec.el, fresh);
        }
        rec.el = fresh;
        rec.sig = sig;
      }
      ordered.push(rec.el);
    });

    entered.forEach(function (node, index) {
      node.style.setProperty("--enter-delay", Math.min(index * 35, 140) + "ms");
      // The class must not outlive the animation: if the node is ever moved,
      // a lingering `.enter` would replay the fade and blink an old message.
      node.addEventListener("animationend", function clear(event) {
        if (event.target !== node) { return; }
        node.classList.remove("enter");
        node.removeEventListener("animationend", clear);
      });
    });

    st.nodes.forEach(function (rec, key) {
      if (!alive.has(key)) {
        if (rec.el.parentNode) { fadeOut(container, rec.el); }
        st.nodes.delete(key);
      }
    });

    syncOrder(container, ordered);
    tick(container, st);
  }

  function clear(container) {
    if (!container) { return; }
    var st = registry.get(container);
    if (st && st.timer) { clearInterval(st.timer); }
    registry.delete(container);
    container.textContent = "";
  }

  function scrollToEnd(container) {
    if (!container) { return; }
    if (container.scrollTo) {
      container.scrollTo({ top: container.scrollHeight, behavior: reduced() ? "auto" : "smooth" });
    } else {
      container.scrollTop = container.scrollHeight;
    }
  }

  window.Thread = {
    render: render,
    clear: clear,
    scrollToEnd: scrollToEnd,
    DEFAULT_LABELS: DEFAULT_LABELS
  };
})();
