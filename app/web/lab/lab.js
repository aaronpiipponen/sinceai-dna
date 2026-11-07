/* DNA lab — Workbench and Runs.
 *
 * The centre column is the shared app/web/shared/thread.js renderer: this page
 * owns the item list and handlers, it owns the DOM. It renders the server's
 * `display` block and never invents content. Lab requests carry ?lab=1 so the
 * inspector gets a trace; the Runs view only reads files the server has
 * already scored (results/runs/*.scored.json).
 *
 * Security: case artifacts and model text are untrusted. Every dynamic value
 * below goes through textContent (or an attribute), never innerHTML.
 */
(function () {
  "use strict";

  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.prototype.slice.call((root || document).querySelectorAll(sel));

  function node(tag, cls, txt) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (txt !== undefined && txt !== null) n.textContent = String(txt);
    return n;
  }

  function add(parent) {
    for (let i = 1; i < arguments.length; i++) {
      const kid = arguments[i];
      if (kid === null || kid === undefined || kid === false) continue;
      parent.appendChild(typeof kid === "string" ? document.createTextNode(kid) : kid);
    }
    return parent;
  }

  function clear(n) {
    while (n.firstChild) n.removeChild(n.firstChild);
    return n;
  }

  function badge(text, cls) {
    return node("span", "badge " + (cls || ""), text);
  }

  function pct(a, b) {
    if (!b) return null;
    return Math.round(1000 * a / b) / 10;
  }

  function pctText(value) {
    return value === null || value === undefined ? "—" : value.toFixed(1) + "%";
  }

  function num(value) {
    return value === null || value === undefined ? "—" : String(value);
  }

  function str(value) {
    return value === null || value === undefined ? "" : String(value);
  }

  function humanize(id) {
    return str(id).replace(/_/g, " ");
  }

  async function api(path, options) {
    const opts = Object.assign({}, options || {});
    opts.headers = Object.assign({ "Content-Type": "application/json" }, opts.headers || {});
    if (opts.body && typeof opts.body !== "string") opts.body = JSON.stringify(opts.body);
    const res = await fetch(path, opts);
    let data = null;
    try {
      data = await res.json();
    } catch (err) {
      data = null;
    }
    if (!res.ok) {
      const message = (data && data.error) ? data.error : "request failed (HTTP " + res.status + ")";
      const e = new Error(message);
      e.status = res.status;
      throw e;
    }
    return data;
  }

  let toastTimer = null;
  let toastHideTimer = null;
  function toast(message, tone) {
    const box = $("#toast");
    box.textContent = message;
    box.className = "toast" + (tone ? " " + tone : "");
    box.hidden = false;
    if (toastTimer) window.clearTimeout(toastTimer);
    if (toastHideTimer) window.clearTimeout(toastHideTimer);
    toastTimer = window.setTimeout(function () {
      if (reduced()) { box.hidden = true; return; }
      box.classList.add("toast-leaving");
      toastHideTimer = window.setTimeout(function () {
        box.hidden = true;
        box.classList.remove("toast-leaving");
      }, 180);
    }, 3000);
  }

  function reduced() {
    return !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  }

  // Re-run a one-shot CSS entrance animation on a panel that was just shown.
  function replay(el, cls, ms) {
    if (!el || reduced()) return;
    el.classList.remove(cls);
    void el.offsetWidth;
    el.classList.add(cls);
    window.setTimeout(function () { el.classList.remove(cls); }, ms);
  }

  function animateDetails(details) {
    if (!details || details.dataset.busy === "1") return;
    const open = !details.open;
    if (reduced()) { details.open = open; return; }
    details.dataset.busy = "1";
    const start = details.getBoundingClientRect().height;
    details.style.overflow = "hidden";
    let closed = 0;
    if (!open) {
      details.open = false;
      closed = details.getBoundingClientRect().height;
      details.open = true;
    } else {
      details.open = true;
    }
    const end = open ? details.getBoundingClientRect().height : closed;
    const grow = details.animate([
      { height: start + "px" }, { height: end + "px" }
    ], { duration: 230, easing: "cubic-bezier(.16, 1, .3, 1)" });
    grow.finished.then(function () {
      details.style.overflow = "";
      details.open = open;
      delete details.dataset.busy;
    }, function () {
      details.style.overflow = "";
      delete details.dataset.busy;
    });
  }

  // ---------------------------------------------------------------- state

  const state = {
    view: "workbench",
    picker: "dev",
    dev: { offset: 0, limit: 50, total: 0, filters: { q: "", journey: "", language: "", benign: "", twin: "", split: "" } },
    samples: null,
    conv: null,
    readonly: null,
    busy: false,
    busyNote: "",
    reviewKey: null,
    reviewVerdict: null,
    runs: { loaded: false, loading: false, list: [], current: null, data: null, rows: [], failure: null }
  };

  // ---------------------------------------------------------------- health

  async function loadHealth() {
    const el = $("#health");
    try {
      const data = await api("/api/health");
      const turns = data.assistant_mode === "turns";
      el.textContent = turns ? "turns · key set" : "stub mode · no key";
      el.className = "health" + (turns ? "" : " stub");
      el.title = data.model + (data.key_configured ? " · API key configured" : " · API key missing");
    } catch (err) {
      el.textContent = "server unreachable";
      el.className = "health bad";
      el.title = err.message;
    }
  }

  // ---------------------------------------------------------------- picker

  function setPicker(name) {
    state.picker = name;
    $$(".picker-tab").forEach(function (tab) {
      tab.setAttribute("aria-selected", tab.getAttribute("data-picker") === name ? "true" : "false");
    });
    $("#picker-dev").hidden = name !== "dev";
    $("#picker-samples").hidden = name !== "samples";
    $("#picker-free").hidden = name !== "free";
    replay($("#picker-" + name), "panel-in", 220);
    if (name === "dev" && !$("#dev-list").childNodes.length) loadDev();
    if (name === "samples" && state.samples === null) loadSamples();
    if (name === "free") $("#free-text").focus();
  }

  let devSeq = 0;
  async function loadDev() {
    const seq = ++devSeq;
    const params = new URLSearchParams();
    params.set("source", "dev");
    params.set("limit", String(state.dev.limit));
    params.set("offset", String(state.dev.offset));
    Object.keys(state.dev.filters).forEach(function (key) {
      const value = state.dev.filters[key];
      if (value !== "" && value !== null && value !== undefined) params.set(key, value);
    });
    try {
      const data = await api("/api/lab/cases?" + params.toString());
      if (seq !== devSeq) return;
      state.dev.total = data.total || 0;
      renderDev(data.cases || []);
    } catch (err) {
      if (seq !== devSeq) return;
      const list = clear($("#dev-list"));
      add(list, node("div", "empty", "Could not load dev cases: " + err.message));
      $("#dev-count").textContent = "—";
    }
  }

  function caseBadges(row, showSplit) {
    const wrap = node("span", "rowmeta");
    add(wrap, badge("lang " + str(row.language), "neutral"));
    if (row.journey) add(wrap, node("span", "", str(row.journey)));
    if (showSplit || row.split) {
      const split = str(row.split);
      add(wrap, badge(split === "holdout" ? "holdout · gate only" : split, split === "holdout" ? "holdout" : "tune"));
    }
    add(wrap, badge(row.benign ? "benign" : "risky", row.benign ? "benign" : "risky"));
    if (row.twin) add(wrap, badge("twin", "twin"));
    if (row.audience) add(wrap, node("span", "", str(row.audience)));
    return wrap;
  }

  function renderDev(rows) {
    const list = clear($("#dev-list"));
    if (!rows.length) {
      add(list, node("div", "empty", "No dev cases match these filters."));
    }
    rows.forEach(function (row) {
      const isGate = row.split === "holdout";
      const item = node("button", "case-row" + (isGate ? " gate" : ""));
      item.type = "button";
      item.setAttribute("role", "option");
      item.setAttribute("aria-selected", "false");
      if (isGate) {
        item.disabled = true;
        item.title = "Held-out family — gate only. Never tune on it.";
      }
      if (state.conv && state.conv.caseId === row.case_id) item.setAttribute("aria-current", "true");
      add(item, node("span", "id", str(row.case_id)), caseBadges(row, true));
      if (!isGate) {
        item.addEventListener("click", function () {
          if (state.busy) return;
          startCase("dev", row);
        });
      }
      list.appendChild(item);
    });
    const start = state.dev.total ? state.dev.offset + 1 : 0;
    const end = Math.min(state.dev.offset + rows.length, state.dev.total);
    $("#dev-count").textContent = start + "–" + end + " of " + state.dev.total;
    $("#dev-prev").disabled = state.dev.offset <= 0;
    $("#dev-next").disabled = state.dev.offset + state.dev.limit >= state.dev.total;
  }

  async function loadSamples() {
    try {
      const data = await api("/api/lab/cases?source=sample&limit=50");
      state.samples = data.cases || [];
      renderSamples();
    } catch (err) {
      const list = clear($("#sample-list"));
      add(list, node("div", "empty", "Could not load samples: " + err.message));
    }
  }

  function renderSamples() {
    const list = clear($("#sample-list"));
    (state.samples || []).forEach(function (row) {
      const item = node("button", "case-row");
      item.type = "button";
      item.setAttribute("role", "option");
      if (state.conv && state.conv.caseId === row.case_id) item.setAttribute("aria-current", "true");
      add(item, node("span", "title", row.title || row.case_id), node("span", "id", str(row.case_id)));
      const meta = node("span", "rowmeta");
      add(meta, node("span", "", str(row.journey)), badge("lang " + str(row.language), "neutral"));
      if (row.benign) add(meta, badge("benign", "benign"));
      if (row.twin) add(meta, badge("twin", "twin"));
      add(item, meta);
      item.addEventListener("click", function () {
        if (state.busy) return;
        startCase("sample", row);
      });
      list.appendChild(item);
    });
  }

  // ---------------------------------------------------------------- conversation start

  function startCase(source, row) {
    const payload = { source: source, case_id: row.case_id };
    const meta = {
      source: source,
      caseId: row.case_id,
      title: row.title || row.case_id,
      language: row.language,
      journey: row.journey,
      audience: row.audience,
      benign: !!row.benign,
      twin: !!row.twin,
      split: source === "sample" ? "sample" : (row.split || "")
    };
    start(payload, meta);
  }

  function startFree() {
    const text = $("#free-text").value.trim();
    if (!text) {
      toast("Write the message first.", "warn");
      $("#free-text").focus();
      return;
    }
    const payload = {
      source: "free",
      text: text,
      language: $("#free-language").value,
      audience: $("#free-audience").value
    };
    const meta = {
      source: "free",
      caseId: null,
      title: "Free conversation",
      language: payload.language,
      journey: "",
      audience: payload.audience,
      benign: false,
      twin: false,
      split: "free"
    };
    start(payload, meta);
  }

  async function start(payload, meta) {
    if (state.busy) return;
    state.readonly = null;
    state.conv = null;
    renderHeader();
    renderCentreMode();
    renderControls();
    renderInspector();
    thread.startItems = null;
    showEmpty("Starting conversation…");
    resetReview();
    setBusy(true, "Starting…");
    try {
      const body = await api("/api/conversations?lab=1", { method: "POST", body: payload });
      beginConversation(body, payload, meta);
    } catch (err) {
      thread.startItems = [];
      addError("Could not start the conversation: " + err.message, function () {
        start(payload, meta);
      });
      renderHeader();
      renderInspector();
    } finally {
      setBusy(false);
    }
  }

  function beginConversation(body, payload, meta) {
    thread.seq = 0;
    thread.retries.clear();
    state.conv = {
      id: body.conversation_id,
      source: meta.source,
      caseId: meta.caseId,
      meta: meta,
      payload: payload,
      language: body.language || meta.language || "fi",
      reference: null,
      final: null,
      lastType: null,
      items: [],
      pendingKey: null,
      turns: [],
      eval: null,
      evaluating: false,
      evalError: null,
      evaluatedTurn: null,
      frame: null
    };
    window.Thread.clear($("#thread"));
    if (body.opening) pushUser(body.opening, meta.source === "free" ? null : "Simulated user");
    if (body.display && body.display.attachment) pushAttachment(body.display.attachment);
    appendReply(body);
    renderHeader();
    renderCentreMode();
    renderControls();
    renderInspector();
    resetReview();
    if (meta.source !== "free" && meta.caseId) loadReference(meta.caseId);
    $("#composer-input").focus();
  }

  async function loadReference(caseId) {
    try {
      const ref = await api("/api/lab/cases/" + encodeURIComponent(caseId) + "/reference");
      if (state.conv && state.conv.caseId === caseId) {
        state.conv.reference = ref;
        renderHeader();
        renderInspector();
      }
    } catch (err) {
      if (state.conv && state.conv.caseId === caseId) {
        state.conv.referenceError = err.message;
        renderInspector();
      }
    }
  }

  function resetReview() {
    state.reviewKey = null;
    state.reviewVerdict = null;
    const note = $("#review-note");
    if (note) note.value = "";
    const status = $("#review-status");
    if (status) status.textContent = "";
    updateReviewSeg();
  }

  // ---------------------------------------------------------------- thread

  // The centre column is app/web/shared/thread.js: we own the item list and
  // the handlers, it owns the DOM. Keys must be stable for its reconcile.
  const thread = { seq: 0, retries: new Map(), startItems: null };

  function nextKey(prefix) {
    thread.seq += 1;
    return prefix + "-" + thread.seq;
  }

  function items() {
    if (state.conv) return state.conv.items;
    return thread.startItems || [];
  }

  function findItem(key) {
    return items().filter(function (item) { return item.key === key; })[0] || null;
  }

  function showEmpty(text) {
    window.Thread.clear($("#thread"));
    add($("#thread"), node("div", "empty", text));
  }

  function renderThread() {
    const list = items();
    const first = $("#thread").firstElementChild;
    if (list.length && first && first.classList.contains("empty")) {
      window.Thread.clear($("#thread"));
    }
    window.Thread.render($("#thread"), list, {
      onQuickReply: onQuickReply,
      onConsent: onConsent,
      onExpert: onExpert,
      onRetry: onRetry
    }, {});
    if (list.length) window.Thread.scrollToEnd($("#thread"));
  }

  function push(item) {
    items().push(item);
  }

  function pushUser(text, speaker) {
    if (!text) return;
    const item = { key: nextKey("user"), type: "user", text: text };
    if (speaker) item.who = speaker;
    push(item);
  }

  function pushAssistant(text) {
    if (!text) return;
    push({ key: nextKey("bot"), type: "greeting", text: text });
  }

  function addChecking() {
    if (!state.conv || state.conv.pendingKey) return;
    const key = nextKey("checking");
    state.conv.pendingKey = key;
    push({ key: key, type: "checking", startedAt: Date.now() });
  }

  function dropChecking() {
    if (!state.conv || !state.conv.pendingKey) return;
    const key = state.conv.pendingKey;
    state.conv.pendingKey = null;
    state.conv.items = state.conv.items.filter(function (item) { return item.key !== key; });
  }

  function addError(text, retry) {
    const key = nextKey("error");
    push({ key: key, type: "error", text: text });
    if (retry) thread.retries.set(key, retry);
    renderThread();
  }

  function onRetry(key) {
    const retry = thread.retries.get(key);
    if (!retry) return;
    thread.retries.delete(key);
    const list = items();
    const at = list.findIndex(function (item) { return item.key === key; });
    if (at !== -1) list.splice(at, 1);
    renderThread();
    retry();
  }

  function onQuickReply(text, key) {
    if (state.busy) return;
    const item = findItem(key);
    if (item) item.answered = true;
    renderThread();
    sendMessage(text);
  }

  function pushAttachment(attachment) {
    if (!attachment) return;
    push({ key: nextKey("attachment"), type: "attachment", attachment: attachment });
  }

  function pushQuestion(display) {
    const question = display && display.question;
    if (!question || !question.text) return;
    push({
      key: nextKey("question"),
      type: "question",
      text: question.text,
      quick: (display && display.quick_replies) || [],
      answered: false
    });
  }

  function receiptText(consent, granted, refused) {
    const list = (consent && consent.items) || [];
    const label = function (token) {
      const row = list.filter(function (item) { return item.field === token; })[0];
      return row ? row.label : token;
    };
    const patterns = window.Thread.DEFAULT_LABELS;
    const parts = [];
    if (granted.length) parts.push(patterns.receiptAllowed.replace("%s", granted.map(label).join(", ")));
    if (refused.length) parts.push(patterns.receiptRefused.replace("%s", refused.map(label).join(", ")));
    return parts.join(" · ") || "Permission answered";
  }

  function pushConsent(display, reply) {
    const consent = display && display.consent;
    if (!consent) {
      pushAssistant(reply && reply.text ? reply.text : "Permission request");
      return;
    }
    push({ key: nextKey("consent"), type: "consent", consent: consent, state: "open", receipt: "" });
  }

  function onConsent(key, granted) {
    if (!state.conv || state.busy) return;
    const item = findItem(key);
    if (!item || item.type !== "consent" || item.state !== "open") return;
    const tokens = (item.consent.fields || []).slice();
    const allowed = granted ? tokens : [];
    const refused = granted ? [] : tokens;
    item.state = granted ? "allowed" : "refused";
    item.receipt = receiptText(item.consent, allowed, refused);
    renderThread();
    answerConsent(tokens, allowed, refused);
  }

  function pushAnswer(display) {
    const answer = display && display.answer;
    if (!answer) {
      pushAssistant("The final reply had no displayable answer.");
      return;
    }
    push({
      key: nextKey("answer"),
      type: "answer",
      answer: answer,
      expertSent: false,
      handoff: display.handoff || null
    });
  }

  function onExpert(key) {
    if (!state.conv) return;
    const list = state.conv.items;
    const at = list.findIndex(function (item) { return item.key === key; });
    const item = at === -1 ? null : list[at];
    if (!item || item.type !== "answer" || item.expertSent) return;
    item.expertSent = true;
    if (item.handoff) {
      list.splice(at + 1, 0, { key: nextKey("handoff"), type: "handoff", handoff: item.handoff });
    }
    renderThread();
  }

  function appendReply(body) {
    if (!body || !state.conv) return;
    const reply = body.reply || {};
    const display = body.display || {};
    const conv = state.conv;
    conv.lastType = reply.type || "unknown";
    if (reply.type === "final" && reply.answer) conv.final = reply.answer;
    recordTurn(reply, body.lab);
    dropChecking();
    if (reply.type === "question") pushQuestion(display);
    else if (reply.type === "consent_request") pushConsent(display, reply);
    else if (reply.type === "final") pushAnswer(display);
    else pushAssistant(reply.text || ("Assistant reply: " + (reply.type || "unknown")));
    renderThread();
    renderControls();
    renderInspector();
    if (reply.type === "final") autoEvaluate();
  }

  function recordTurn(reply, lab) {
    if (!state.conv) return;
    const trace = lab && lab.trace ? lab.trace : null;
    const meta = trace && trace.meta ? trace.meta : {};
    state.conv.turns.push({
      n: state.conv.turns.length + 1,
      type: reply.type || "unknown",
      latency: typeof meta.latency_s === "number" ? meta.latency_s : null,
      cached: typeof meta.cached === "boolean" ? meta.cached : null,
      prompt_chars: typeof meta.prompt_chars === "number" ? meta.prompt_chars : null,
      rules: trace && Array.isArray(trace.rules) ? trace.rules : [],
      raw: trace ? trace.raw_text : null,
      fallback: trace ? !!trace.fallback : false,
      error: trace ? trace.error : null
    });
  }

  // ---------------------------------------------------------------- actions

  function setBusy(flag, note) {
    state.busy = !!flag;
    state.busyNote = note || "";
    renderControls();
  }

  async function sendMessage(text) {
    const clean = str(text).trim();
    if (!state.conv || state.busy || !clean) return;
    pushUser(clean);
    $("#composer-input").value = "";
    addChecking();
    setBusy(true, "Waiting for the assistant…");
    renderThread();
    const conv = state.conv;
    try {
      const body = await api("/api/conversations/" + conv.id + "/message?lab=1",
        { method: "POST", body: { text: clean } });
      if (state.conv === conv) appendReply(body);
    } catch (err) {
      if (state.conv === conv) {
        dropChecking();
        addError("The assistant did not reply: " + err.message, function () { sendMessage(clean); });
      }
    } finally {
      if (state.conv === conv) {
        dropChecking();
        renderThread();
      }
      setBusy(false);
    }
  }

  async function answerConsent(tokens, granted, refused) {
    if (!state.conv || state.busy) return;
    const conv = state.conv;
    setBusy(true, "Waiting for the assistant…");
    addChecking();
    renderThread();
    try {
      const body = await api("/api/conversations/" + conv.id + "/consent?lab=1",
        { method: "POST", body: { granted: granted, refused: refused, fields: tokens } });
      if (state.conv === conv) appendReply(body);
    } catch (err) {
      if (state.conv === conv) {
        dropChecking();
        addError("The permission answer was not accepted: " + err.message, function () {
          answerConsent(tokens, granted, refused);
        });
      }
    } finally {
      if (state.conv === conv) {
        dropChecking();
        renderThread();
      }
      setBusy(false);
    }
  }

  async function simulateRequest() {
    const conv = state.conv;
    if (!conv) return null;
    addChecking();
    renderThread();
    try {
      const body = await api("/api/lab/conversations/" + conv.id + "/simulate",
        { method: "POST", body: {} });
      if (state.conv !== conv) return null;
      dropChecking();
      if (body.message) pushUser(body.message.text, "Simulated user");
      appendReply(body);
      return body.reply || null;
    } catch (err) {
      if (state.conv === conv) {
        dropChecking();
        addError("Simulated user stopped: " + err.message, onSimulate);
      }
      return null;
    }
  }

  async function onSimulate() {
    if (!state.conv || state.busy) return;
    setBusy(true, "Simulated user turn…");
    try {
      await simulateRequest();
    } finally {
      setBusy(false);
    }
  }

  async function onRunToEnd() {
    if (!state.conv || state.busy) return;
    setBusy(true, "Running with the simulated user…");
    try {
      for (let i = 0; i < 14; i++) {
        if (!state.conv || state.conv.lastType === "final") break;
        state.busyNote = "Simulated turn " + (i + 1) + "…";
        renderControls();
        const reply = await simulateRequest();
        if (!reply) break;
      }
    } finally {
      setBusy(false);
    }
  }

  async function onFinish() {
    if (!state.conv || state.busy) return;
    const conv = state.conv;
    toast("Finish now — turn limit");
    setBusy(true, "Finishing…");
    addChecking();
    renderThread();
    try {
      const body = await api("/api/conversations/" + conv.id + "/finish?lab=1",
        { method: "POST", body: {} });
      if (state.conv === conv) appendReply(body);
    } catch (err) {
      if (state.conv === conv) {
        dropChecking();
        addError("Could not finish: " + err.message, onFinish);
      }
    } finally {
      if (state.conv === conv) {
        dropChecking();
        renderThread();
      }
      setBusy(false);
    }
  }

  function onRestart() {
    if (!state.conv || state.busy) return;
    start(state.conv.payload, state.conv.meta);
  }

  async function autoEvaluate() {
    const conv = state.conv;
    if (!conv || !conv.final || conv.source === "free") return;
    const turn = conv.turns.length;
    if (conv.evaluatedTurn === turn) return;
    conv.evaluatedTurn = turn;
    conv.evaluating = true;
    conv.evalError = null;
    renderInspector();
    try {
      const data = await api("/api/lab/conversations/" + conv.id + "/evaluate",
        { method: "POST", body: {} });
      if (state.conv !== conv) return;
      conv.eval = data;
      if (data.reference) conv.reference = data.reference;
    } catch (err) {
      if (state.conv !== conv) return;
      conv.evalError = err.message;
    } finally {
      if (state.conv === conv) {
        conv.evaluating = false;
        renderInspector();
      }
    }
  }

  // ---------------------------------------------------------------- header / controls

  function renderHeader() {
    const title = $("#conv-case");
    const meta = $("#conv-meta");
    const badges = clear($("#conv-badges"));
    if (state.readonly) {
      const row = state.readonly.row;
      title.textContent = str(row.case_id);
      meta.textContent = "Read-only · " + state.readonly.run + " · stored answer, no conversation";
      add(badges, badge(str(row.journey), "neutral"), badge("lang " + str(row.language), "neutral"),
        badge(row.benign ? "benign" : "risky", row.benign ? "benign" : "risky"));
      if (row.twin) add(badges, badge("twin", "twin"));
      add(badges, badge(str(row.split), row.split === "holdout" ? "holdout" : "tune"));
      return;
    }
    const conv = state.conv;
    if (!conv) {
      title.textContent = "No case selected";
      meta.textContent = "Pick a case to start.";
      return;
    }
    const m = conv.meta || {};
    title.textContent = conv.caseId || m.title || "Free conversation";
    meta.textContent = [m.source, "lang " + conv.language, "turn " + conv.turns.length]
      .filter(Boolean).join(" · ");
    if (m.journey) add(badges, badge(m.journey, "neutral"));
    add(badges, badge("lang " + conv.language, "neutral"));
    if (m.source !== "free") {
      add(badges, badge(m.benign ? "benign" : "risky", m.benign ? "benign" : "risky"));
      if (m.twin) add(badges, badge("twin", "twin"));
    }
    if (m.split) add(badges, badge(m.split === "holdout" ? "holdout · gate only" : m.split,
      m.split === "holdout" ? "holdout" : "tune"));
    if (conv.final) add(badges, badge("final", "pass"));
  }

  function renderCentreMode() {
    const ro = !!state.readonly;
    $("#readonly-banner").hidden = !ro;
    $("#thread-scroll").hidden = ro;
    $("#readonly-panel").hidden = !ro;
    $("#lab-controls").hidden = ro;
    $("#composer").hidden = ro;
    if (ro) {
      $("#readonly-label").textContent = state.readonly.run + " · " + state.readonly.row.case_id;
      renderReadonlyPanel();
    }
  }

  function renderControls() {
    const conv = state.conv;
    const on = !!conv && !state.busy && !state.readonly;
    const last = conv ? conv.lastType : null;
    $("#btn-simulate").disabled = !(on && (last === "question" || last === "consent_request"));
    $("#btn-run").disabled = !(on && last && last !== "final");
    $("#btn-finish").disabled = !(on && last && last !== "final");
    $("#btn-restart").disabled = !(on && conv);
    $("#composer-input").disabled = !on;
    $("#composer .send").disabled = !on;
    const note = $("#busy-note");
    if (state.busy) note.textContent = state.busyNote || "Working…";
    else if (conv) note.textContent = "turn " + conv.turns.length + (last ? " · " + last : "");
    else note.textContent = "";
  }

  function renderReadonlyPanel() {
    const host = clear($("#readonly-panel"));
    const row = state.readonly.row;
    const card = node("div", "readonly-card");
    add(card, node("h2", "", str(row.case_id)));
    add(card, node("p", "", "This row comes from a pre-scored file. The conversation and its trace were not stored; the inspector shows the stored answer next to the reference."));
    const dl = node("dl");
    const ours = row.ours && typeof row.ours === "object" ? row.ours : {};
    [["Action", ours.action || (typeof row.ours === "string" ? row.ours : "—")],
      ["Risk", ours.risk || "—"],
      ["Escalation", ours.escalation ? "true" : "false"],
      ["Run", state.readonly.run],
      ["Split", str(row.split)]].forEach(function (pair) {
      add(dl, node("dt", "", pair[0]), node("dd", "", str(pair[1])));
    });
    add(card, dl);
    add(host, card);
  }

  // ---------------------------------------------------------------- inspector

  function renderInspector(preserveScroll) {
    const scroll = $("#inspector-scroll");
    const at = scroll.scrollTop;
    const host = clear($("#inspector"));
    replay(host, "panel-in", 240);
    inspectorMeta();
    if (state.readonly) renderReadonlyInspector(host);
    else if (!state.conv) add(host, node("div", "empty", "No case selected. Pick a case to start."));
    else renderLiveInspector(host);
    renderReview();
    scroll.scrollTop = preserveScroll === false ? 0 : at;
  }

  function inspectorMeta() {
    const el = $("#inspector-meta");
    if (state.readonly) {
      el.textContent = state.readonly.row.case_id;
      return;
    }
    if (state.conv) {
      el.textContent = (state.conv.caseId || "free") + " · " + state.conv.turns.length + " turns";
      return;
    }
    el.textContent = "No case";
  }

  function renderLiveInspector(host) {
    const conv = state.conv;
    inspectorMeta();
    if (!conv) return;
    if (conv.source === "free") {
      add(host, node("div", "empty", "Free conversation: no ground truth, so there is no verdict or reference. Turns and traces below."));
      if (conv.turns.length) renderTurns(host, conv.turns);
      return;
    }
    if (!conv.final) {
      const pending = node("div", "verdict");
      const top = node("div", "verdict-top");
      add(top, node("span", "verdict-badge pending", "NO FINAL"),
        node("span", "verdict-note", conv.evaluating ? "Evaluating…" : "The verdict appears when a final answer exists."));
      add(pending, top);
      add(host, pending);
    } else if (conv.evaluating) {
      const pending = node("div", "verdict");
      const top = node("div", "verdict-top");
      add(top, node("span", "verdict-badge pending", "EVALUATING"),
        node("span", "verdict-note", "Scoring against the reference in memory…"));
      add(pending, top);
      add(host, pending);
    } else if (conv.evalError) {
      const box = node("div", "verdict");
      const top = node("div", "verdict-top");
      add(top, node("span", "verdict-badge fail", "ERROR"),
        node("span", "verdict-note bad", "Evaluation failed: " + conv.evalError));
      add(box, top);
      add(host, box);
    } else if (conv.eval) {
      renderVerdict(host, conv.eval.result || {}, conv.eval.reference || conv.reference || {}, conv.final);
      if (conv.eval.summary) {
        const s = conv.eval.summary;
        const bits = [
          "questions " + num(s.questions),
          "must-ask " + (s.must_ask_satisfied ? "satisfied" : "not satisfied"),
          "consent asked " + (s.consent_asked || []).length,
          "granted " + (s.consent_granted || []).length,
          "refused " + (s.consent_refused || []).length
        ];
        add(host, node("div", "eval-note", bits.join(" · ")));
      }
    }
    renderCompare(host, conv.final, conv.reference, conv.eval ? conv.eval.result : null, false);
    if (conv.turns.length) renderTurns(host, conv.turns);
    else add(host, node("div", "turn-empty", "No assistant turns yet."));
  }

  function renderReadonlyInspector(host) {
    inspectorMeta();
    const row = state.readonly.row;
    const checks = row.checks || {};
    const pseudo = {
      passed: !!row.passed,
      failures: row.failures || [],
      action_ok: checks.action_ok,
      risk_within_one: checks.risk_within_one,
      asked_ok: checks.asked_ok,
      esc_expected: checks.esc_expected,
      esc_given: checks.esc_given,
      steps_missing: checks.steps_missing || []
    };
    const reference = referenceFromRow(row);
    const answer = answerFromRow(row);
    renderVerdict(host, pseudo, reference, answer);
    renderCompare(host, answer, reference, pseudo, true);
    add(host, node("div", "turn-empty",
      "Pre-scored row: no trace or conversation was stored. Turn traces come from a live Workbench conversation."));
  }

  function answerFromRow(row) {
    const ours = row.ours;
    if (!ours || typeof ours !== "object") return { primary_action: ours || null };
    return {
      primary_action: ours.action,
      risk_level: ours.risk,
      escalation_required: !!ours.escalation,
      escalation_target: ours.escalation_target,
      advice_text: ours.advice_text || "",
      steps: ours.steps || [],
      question_topics: ours.question_topics || []
    };
  }

  function referenceFromRow(row) {
    const expected = row.expected;
    if (!expected || typeof expected !== "object") {
      return { primary_action: expected || null, reference_answer: (row.reference && row.reference.text) || "" };
    }
    return {
      primary_action: expected.primary_action,
      acceptable_actions: expected.acceptable || [],
      risk_level: expected.risk,
      escalation: expected.escalation || { required: false },
      required_steps: expected.required_steps || [],
      must_ask_topics: expected.must_ask || [],
      reference_answer: (row.reference && row.reference.text) || "",
      reference_answer_language: (row.reference && row.reference.language) || row.language
    };
  }

  function renderVerdict(host, result, reference, answer) {
    const failures = result.failures || [];
    const box = node("div", "verdict");
    const top = node("div", "verdict-top");
    add(top, node("span", "verdict-badge " + (result.passed ? "pass" : "fail"),
      result.passed ? "PASS" : "FAIL"));
    const note = result.passed
      ? "Safe-action pass against the reference."
      : (failures.length
        ? failures.length + " failure" + (failures.length === 1 ? "" : "s") + " against the reference."
        : "Did not pass against the reference.");
    add(top, node("span", "verdict-note", note));
    add(box, top);

    if (failures.length) {
      const chips = node("div", "failchips");
      failures.forEach(function (failure) {
        const type = typeof failure === "string" ? failure : (failure && failure.type) || "failure";
        const chip = node("span", "failchip", type);
        const detail = failureDetail(failure);
        if (detail) chip.title = type + " · " + detail;
        add(chips, chip);
      });
      add(box, chips);
    }

    const grid = node("div", "vgrid");
    const ours = answer || {};
    const exp = reference || {};
    const expectedEsc = !!(exp.escalation && exp.escalation.required);
    const givenEsc = !!ours.escalation_required;

    gridRow(grid, "Action", str(ours.primary_action), expectedActionLabel(exp),
      result.action_ok, null);
    gridRow(grid, "Risk", str(ours.risk_level), str(exp.risk_level), result.risk_within_one,
      result.risk_exact === false && result.risk_within_one ? "within one" : null);

    const escOk = expectedEsc ? givenEsc : true;
    gridRow(grid, "Escalation", givenEsc ? "escalated" : "no handoff",
      expectedEsc ? "required" : "not required", escOk, !expectedEsc && givenEsc ? "extra" : null);

    const asked = result.asked_ok;
    let askedText = "n/a";
    if (asked === true) askedText = "yes";
    else if (asked === false) askedText = "no";
    const mustAsk = (exp.must_ask_topics || []).join(", ");
    gridRow(grid, "Decisive q.", askedText, mustAsk || "no must-ask topic",
      asked === null || asked === undefined ? null : asked,
      null);
    add(box, grid);
    add(host, box);
  }

  function expectedActionLabel(reference) {
    const primary = str(reference.primary_action);
    const acceptable = reference.acceptable_actions || [];
    const extras = acceptable.filter(function (action) { return action !== reference.primary_action; }).length;
    if (extras > 0) return primary + " (+" + extras + ")";
    return primary || "—";
  }

  function gridRow(grid, key, oursText, expectedText, ok, note) {
    const row = node("div", "vrow");
    add(row, node("span", "k", key));
    const ours = node("span", "v", oursText || "—");
    const arrow = node("span", "arrow", "→");
    const expected = node("span", "v", expectedText || "—");
    if (ok === true) {
      ours.classList.add("ok");
      expected.classList.add("ok");
    } else if (ok === false) {
      ours.classList.add("bad");
      expected.classList.add("bad");
    }
    if (note) expected.title = note;
    add(row, ours, arrow, expected);
    grid.appendChild(row);
  }

  function failureDetail(failure) {
    if (!failure || typeof failure === "string") return "";
    const bits = [];
    if (failure.expected !== undefined) {
      bits.push("expected " + (Array.isArray(failure.expected) ? failure.expected.join(" / ") : failure.expected));
    }
    if (failure.got !== undefined && failure.got !== null) bits.push("got " + failure.got);
    if (failure.claim) bits.push('claim "' + failure.claim + '"');
    if (failure.topics && failure.topics.length) bits.push("topics " + failure.topics.join(", "));
    if (failure.expected_target) bits.push("target " + failure.expected_target);
    if (failure.signals && failure.signals.length) bits.push("signals " + failure.signals.join(", "));
    if (failure.words !== undefined) bits.push(failure.words + " words");
    if (failure.asked_too_many) bits.push("asked too many topics");
    if (failure.risk) bits.push("risk " + failure.risk);
    if (failure.value !== undefined) bits.push("value " + failure.value);
    if (failure.error) bits.push(failure.error);
    return bits.join(" · ");
  }

  function renderCompare(host, answer, reference, result, readonly) {
    const section = node("section");
    const head = node("div", "section-head");
    add(head, node("h3", "", "Ours vs reference"));
    if (reference && reference.reference_answer_language) {
      add(head, node("span", "meta", "reference " + reference.reference_answer_language));
    }
    add(section, head);

    const grid = node("div", "compare");
    const oursCol = node("div", "compare-col");
    add(oursCol, node("h3", "", "Ours"));
    const oursCard = node("div", "card-mini");
    if (answer && (answer.advice_text || (answer.steps || []).length)) {
      if (answer.advice_text) add(oursCard, node("p", "", answer.advice_text));
      if ((answer.steps || []).length) {
        const ol = node("ol");
        answer.steps.forEach(function (step) { add(ol, node("li", "", step)); });
        add(oursCard, ol);
      }
      const topics = answer.question_topics || [];
      if (topics.length) add(oursCard, node("p", "muted", "Question topics: " + topics.join(", ")));
    } else {
      add(oursCard, node("p", "muted", readonly ? "No stored answer." : "No final answer yet."));
    }
    add(oursCol, oursCard);

    const refCol = node("div", "compare-col");
    const refHead = node("h3");
    add(refHead, "Reference");
    if (reference && reference.reference_answer_language) {
      add(refHead, node("span", "lang", reference.reference_answer_language));
    }
    add(refCol, refHead);
    const refCard = node("div", "card-mini");
    if (reference && reference.reference_answer) {
      add(refCard, node("p", "", reference.reference_answer));
    } else if (state.conv && state.conv.referenceError) {
      add(refCard, node("p", "muted", "Reference unavailable: " + state.conv.referenceError));
    } else {
      add(refCard, node("p", "muted", "Loading reference…"));
    }
    const required = (reference && reference.required_steps) || [];
    if (required.length) {
      const missing = (result && result.steps_missing) || [];
      const hasEval = !!result && (result.steps_missing !== undefined || result.steps_found !== undefined);
      const found = required.filter(function (s) { return missing.indexOf(s) === -1; });
      add(refCard, node("p", "stepchips-label",
        "Required steps " + (hasEval ? found.length + "/" + required.length : "(" + required.length + ")")));
      const chips = node("div", "stepchips");
      required.forEach(function (step) {
        const isMissing = missing.indexOf(step) !== -1;
        const cls = hasEval ? (isMissing ? "missing" : "found") : "neutral";
        const chip = node("span", "stepchip " + cls, humanize(step));
        chip.title = step + (hasEval ? (isMissing ? " · missing" : " · found") : "");
        chips.appendChild(chip);
      });
      add(refCard, chips);
    }
    add(refCol, refCard);
    add(grid, oursCol, refCol);
    add(section, grid);
    add(host, section);
  }

  // ---------------------------------------------------------------- turns and rules

  function renderTurns(host, turns) {
    const section = node("section");
    const head = node("div", "section-head");
    add(head, node("h3", "", "Turns"), node("span", "meta", turns.length + " assistant"));
    add(section, head);
    const list = node("div", "turns");
    let openIndex = -1;
    for (let i = turns.length - 1; i >= 0; i--) {
      if (turns[i].rules && turns[i].rules.length) { openIndex = i; break; }
    }
    if (openIndex === -1) openIndex = turns.length - 1;
    turns.forEach(function (turn, i) {
      const details = node("details", "turn");
      details.open = i === openIndex;
      const summary = node("summary");
      summary.addEventListener("click", function (event) {
        event.preventDefault();
        animateDetails(details);
      });
      add(summary,
        node("span", "tno", "#" + turn.n),
        node("span", "ttype", turn.type));
      const meta = node("span", "tmeta");
      add(meta,
        node("span", "", turn.latency === null ? "lat —" : "lat " + turn.latency.toFixed(2) + "s"),
        node("span", "", turn.cached === null ? "cache —" : (turn.cached ? "cache hit" : "live")),
        node("span", "", turn.prompt_chars === null ? "prompt —" : "prompt " + turn.prompt_chars + " ch"));
      if (turn.fallback) add(meta, node("span", "", "fallback"));
      add(summary, meta);
      add(details, summary);

      const body = node("div", "turn-body");
      if (turn.error) add(body, node("div", "turn-empty", "trace error: " + turn.error));
      if (turn.rules && turn.rules.length) {
        const rules = node("ul", "rules");
        turn.rules.forEach(function (rule) { add(rules, renderRule(rule)); });
        add(body, rules);
      } else {
        add(body, node("div", "turn-empty", "No rules fired on this turn."));
      }
      const raw = node("details", "raw");
      const rawSummary = node("summary", "", "Raw model reply");
      rawSummary.addEventListener("click", function (event) {
        event.preventDefault();
        animateDetails(raw);
      });
      add(raw, rawSummary);
      add(raw, node("pre", "raw-json", prettyRaw(turn.raw)));
      add(body, raw);
      add(details, body);
      list.appendChild(details);
    });
    add(section, list);
    add(host, section);
  }

  function ruleValue(value) {
    if (value === null || value === undefined) return "";
    if (Array.isArray(value)) {
      return value.map(function (item) {
        return typeof item === "string" ? item : JSON.stringify(item);
      }).join(" · ");
    }
    if (typeof value === "object") return JSON.stringify(value);
    return String(value);
  }

  function renderRule(rule) {
    const li = node("li", "rule");
    add(li, node("span", "rname", str(rule && rule.rule) + ":"));
    const values = node("div", "rvals");
    const from = ruleValue(rule && rule.from);
    const to = ruleValue(rule && rule.to);
    if (from.length > 80 || to.length > 80) {
      values.classList.add("diff");
      renderDiff(values, from, to);
    } else {
      add(values, node("span", "rfrom", from || "null"), " → ", node("span", "rto", to || "null"));
    }
    add(li, values);
    return li;
  }

  function renderDiff(host, from, to) {
    const a = from ? from.split(/\s+/).filter(Boolean) : [];
    const b = to ? to.split(/\s+/).filter(Boolean) : [];
    const ops = wordOps(a, b);
    let current = null;
    let buffer = [];
    function flush() {
      if (!buffer.length) return;
      const text = buffer.join(" ");
      if (current === "same") add(host, text);
      else {
        const el = document.createElement(current === "ins" ? "ins" : "del");
        el.textContent = text;
        host.appendChild(el);
      }
      buffer = [];
      host.appendChild(document.createTextNode(" "));
    }
    ops.forEach(function (op) {
      if (op.type !== current) {
        flush();
        current = op.type;
      }
      buffer.push(op.word);
    });
    flush();
  }

  function wordOps(a, b) {
    const n = a.length;
    const m = b.length;
    if (n * m > 250000) return coarseOps(a, b);
    const dp = [];
    for (let i = 0; i <= n; i++) dp.push(new Uint32Array(m + 1));
    for (let i = n - 1; i >= 0; i--) {
      for (let j = m - 1; j >= 0; j--) {
        dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
      }
    }
    const ops = [];
    let i = 0;
    let j = 0;
    while (i < n && j < m) {
      if (a[i] === b[j]) {
        ops.push({ type: "same", word: a[i] });
        i++;
        j++;
      } else if (dp[i + 1][j] >= dp[i][j + 1]) {
        ops.push({ type: "del", word: a[i] });
        i++;
      } else {
        ops.push({ type: "ins", word: b[j] });
        j++;
      }
    }
    while (i < n) { ops.push({ type: "del", word: a[i] }); i++; }
    while (j < m) { ops.push({ type: "ins", word: b[j] }); j++; }
    return ops;
  }

  function coarseOps(a, b) {
    let start = 0;
    while (start < a.length && start < b.length && a[start] === b[start]) start++;
    let endA = a.length - 1;
    let endB = b.length - 1;
    while (endA >= start && endB >= start && a[endA] === b[endB]) { endA--; endB--; }
    const ops = [];
    for (let i = 0; i < start; i++) ops.push({ type: "same", word: a[i] });
    for (let i = start; i <= endA; i++) ops.push({ type: "del", word: a[i] });
    for (let i = start; i <= endB; i++) ops.push({ type: "ins", word: b[i] });
    for (let i = endA + 1; i < a.length; i++) ops.push({ type: "same", word: a[i] });
    return ops;
  }

  function prettyRaw(raw) {
    if (raw === null || raw === undefined || raw === "") return "No raw reply recorded.";
    if (typeof raw !== "string") {
      try { return JSON.stringify(raw, null, 2); } catch (err) { return String(raw); }
    }
    try { return JSON.stringify(JSON.parse(raw), null, 2); } catch (err) { return raw; }
  }

  // ---------------------------------------------------------------- review

  function reviewTarget() {
    if (state.readonly) {
      return { case_id: state.readonly.row.case_id, run: state.readonly.run };
    }
    if (state.conv && state.conv.source !== "free" && state.conv.caseId) {
      return { case_id: state.conv.caseId, run: "" };
    }
    return null;
  }

  function renderReview() {
    const target = reviewTarget();
    const box = $("#review");
    box.hidden = !target;
    if (!target) return;
    const key = target.case_id + "|" + target.run;
    if (state.reviewKey !== key) {
      state.reviewKey = key;
      state.reviewVerdict = null;
      $("#review-note").value = "";
      $("#review-status").textContent = "";
    }
    $("#review-case").textContent = target.case_id + (target.run ? " · " + target.run : "");
    updateReviewSeg();
  }

  function updateReviewSeg() {
    $$(".segbtn").forEach(function (b) {
      b.setAttribute("aria-pressed", b.getAttribute("data-verdict") === state.reviewVerdict ? "true" : "false");
    });
    $("#review-save").disabled = !state.reviewVerdict || !reviewTarget();
  }

  async function saveReview() {
    const target = reviewTarget();
    if (!target || !state.reviewVerdict) return;
    const status = $("#review-status");
    status.textContent = "Saving…";
    $("#review-save").disabled = true;
    try {
      await api("/api/lab/review", {
        method: "POST",
        body: {
          case_id: target.case_id,
          run: target.run,
          verdict: state.reviewVerdict,
          note: $("#review-note").value.trim()
        }
      });
      status.textContent = "Saved to human_review.csv";
      toast("Review saved for " + target.case_id);
    } catch (err) {
      status.textContent = "Not saved: " + err.message;
    } finally {
      updateReviewSeg();
    }
  }

  // ---------------------------------------------------------------- runs

  function rowFailures(row) {
    const raw = row && row.failures;
    const out = [];
    (Array.isArray(raw) ? raw : []).forEach(function (failure) {
      const type = typeof failure === "string" ? failure : (failure && failure.type);
      if (type && out.indexOf(type) === -1) out.push(type);
    });
    return out;
  }

  function rowOursAction(row) {
    const ours = row && row.ours;
    if (typeof ours === "string") return ours;
    return ours && ours.action ? ours.action : "—";
  }

  function rowExpectedAction(row) {
    const expected = row && row.expected;
    if (typeof expected === "string") return expected;
    return expected && expected.primary_action ? expected.primary_action : "—";
  }

  function escExpected(row) {
    const checks = row && row.checks;
    if (checks && typeof checks.esc_expected === "boolean") return checks.esc_expected;
    const expected = row && row.expected;
    return !!(expected && expected.escalation && expected.escalation.required);
  }

  function escGiven(row) {
    const checks = row && row.checks;
    if (checks && typeof checks.esc_given === "boolean") return checks.esc_given;
    const ours = row && row.ours;
    return !!(ours && ours.escalation);
  }

  function askedOk(row) {
    const checks = row && row.checks;
    if (checks && Object.prototype.hasOwnProperty.call(checks, "asked_ok")) {
      return checks.asked_ok === undefined ? null : checks.asked_ok;
    }
    const expected = row && row.expected;
    const ours = row && row.ours;
    const must = (expected && expected.must_ask) || [];
    if (!must.length) return null;
    const topics = (ours && ours.question_topics) || [];
    return must.some(function (topic) { return topics.indexOf(topic) !== -1; });
  }

  function isFalseAlarm(row) {
    if (row.checks && row.checks.false_alarm === true) return true;
    if (row.checks && row.checks.false_alarm === false) return false;
    return rowFailures(row).indexOf("false_alarm") !== -1;
  }

  function stats(rows) {
    const total = rows.length;
    const passed = rows.filter(function (r) { return r.passed; }).length;
    const benign = rows.filter(function (r) { return r.benign; });
    const falseAlarms = benign.filter(isFalseAlarm).length;
    const escRows = rows.filter(function (r) { return escExpected(r) === true; });
    const escHit = escRows.filter(function (r) { return escGiven(r) === true; }).length;
    const escFp = rows.filter(function (r) { return escExpected(r) === false && escGiven(r) === true; }).length;
    const twins = rows.filter(function (r) { return r.twin; });
    const twinsPassed = twins.filter(function (r) { return r.passed; }).length;
    const askedRows = rows.filter(function (r) { return askedOk(r) !== null && askedOk(r) !== undefined; });
    const askedYes = askedRows.filter(function (r) { return askedOk(r) === true; }).length;
    return {
      total: total,
      pass: pct(passed, total),
      passed: passed,
      benign: benign.length,
      falseAlarms: falseAlarms,
      falseAlarmPct: pct(falseAlarms, benign.length),
      escExpected: escRows.length,
      escRecall: pct(escHit, escRows.length),
      escFp: escFp,
      twins: twins.length,
      twinPass: pct(twinsPassed, twins.length),
      asked: askedRows.length,
      askedPct: pct(askedYes, askedRows.length)
    };
  }

  function failureCounts(rows) {
    const counts = {};
    rows.forEach(function (row) {
      rowFailures(row).forEach(function (type) {
        counts[type] = (counts[type] || 0) + 1;
      });
    });
    return counts;
  }

  async function loadRuns() {
    if (state.runs.loading) return;
    state.runs.loading = true;
    const head = clear($("#run-head"));
    add(head, node("div", "empty", "Loading scored runs…"));
    try {
      const data = await api("/api/lab/runs");
      const list = (data.runs || []).slice();
      list.sort(function (a, b) { return str(b.modified).localeCompare(str(a.modified)); });
      state.runs.list = list;
      state.runs.loaded = true;
      renderRunsList();
      if (!list.length) {
        const empty = clear($("#run-head"));
        add(empty, node("div", "empty", "No results/runs/*.scored.json yet. Run app/score.py --per-case."));
        $("#run-content").hidden = true;
        return;
      }
      const wanted = state.runs.current && list.some(function (r) { return r.name === state.runs.current; })
        ? state.runs.current : list[0].name;
      await selectRun(wanted);
    } catch (err) {
      const failed = clear($("#run-head"));
      add(failed, node("div", "empty", "Could not list runs: " + err.message));
    } finally {
      state.runs.loading = false;
    }
  }

  function renderRunsList() {
    const list = clear($("#runs-list"));
    if (!state.runs.list.length) {
      add(list, node("div", "empty", "No scored runs."));
      return;
    }
    state.runs.list.forEach(function (run) {
      const summary = run.summary || {};
      const item = node("button", "run-item");
      item.type = "button";
      if (run.name === state.runs.current) item.setAttribute("aria-current", "true");
      add(item, node("span", "rname", run.name));
      const meta = node("span", "rmeta");
      add(meta, node("span", "", pctText(summary.pass_pct) + " pass"),
        node("span", "", num(summary.cases) + " cases"));
      add(item, meta);
      item.addEventListener("click", function () {
        if (state.runs.loading) return;
        selectRun(run.name);
      });
      list.appendChild(item);
    });
  }

  async function selectRun(name) {
    state.runs.current = name;
    state.runs.failure = null;
    renderRunsList();
    const head = clear($("#run-head"));
    add(head, node("div", "empty", "Reading " + name + "…"));
    $("#run-content").hidden = true;
    try {
      const data = await api("/api/lab/runs/" + encodeURIComponent(name));
      state.runs.data = data;
      state.runs.rows = (data.rows || []).filter(function (r) { return r && r.case_id; });
      renderRun();
    } catch (err) {
      const failed = clear($("#run-head"));
      add(failed, node("div", "empty", "Could not read " + name + ": " + err.message));
    }
  }

  function renderRun() {
    const data = state.runs.data || {};
    const rows = state.runs.rows || [];
    const all = stats(rows);
    const tune = stats(rows.filter(function (r) { return r.split === "tune"; }));
    const holdout = stats(rows.filter(function (r) { return r.split === "holdout"; }));

    const head = clear($("#run-head"));
    add(head, node("h2", "", data.name || state.runs.current));
    const meta = node("div", "run-meta");
    const prov = data.provenance || {};
    [
      ["label", data.label],
      ["generated", data.generated_at],
      ["predictions", prov.predictions],
      ["model", prov.model],
      ["commit", prov.git_commit],
      ["cases", rows.length],
      ["tune", tune.total],
      ["holdout", holdout.total]
    ].forEach(function (pair) {
      if (pair[1] === null || pair[1] === undefined || pair[1] === "") return;
      const span = node("span");
      add(span, pair[0] + " ", node("span", "mono", pair[1]));
      add(meta, span);
    });
    add(head, meta);
    $("#run-content").hidden = false;

    renderMetrics(all, tune, holdout);
    renderFailureChart();
    renderRunTable();
  }

  function metricCard(name, value, splits) {
    const card = node("div", "metric");
    add(card, node("div", "mname", name), node("div", "mval", value));
    const line = node("div", "msplit");
    splits.forEach(function (pair) {
      const span = node("span");
      add(span, pair[0] + " ", node("b", "", pair[1]));
      add(line, span);
    });
    add(card, line);
    return card;
  }

  function renderMetrics(all, tune, holdout) {
    const host = clear($("#run-metrics"));
    host.classList.add("metrics-grid");
    add(host,
      metricCard("Safe-action pass", pctText(all.pass), [
        ["Tune", pctText(tune.pass)], ["Holdout", pctText(holdout.pass)]
      ]),
      metricCard("False alarms", all.falseAlarms + "/" + all.benign,
        [["Tune", tune.falseAlarms + "/" + tune.benign], ["Holdout", holdout.falseAlarms + "/" + holdout.benign]]),
      metricCard("Escalation recall", pctText(all.escRecall),
        [["Tune", pctText(tune.escRecall)], ["Holdout", pctText(holdout.escRecall)]]),
      metricCard("Escalation FP", num(all.escFp),
        [["Tune", num(tune.escFp)], ["Holdout", num(holdout.escFp)]]),
      metricCard("Twin pass", pctText(all.twinPass),
        [["Tune", pctText(tune.twinPass)], ["Holdout", pctText(holdout.twinPass)]]),
      metricCard("Decisive question", pctText(all.askedPct),
        [["Tune", pctText(tune.askedPct)], ["Holdout", pctText(holdout.askedPct)]])
    );
  }

  function renderFailureChart() {
    const host = clear($("#failure-chart"));
    const counts = failureCounts(state.runs.rows);
    const entries = Object.keys(counts).map(function (type) { return [type, counts[type]]; });
    entries.sort(function (a, b) { return b[1] - a[1] || a[0].localeCompare(b[0]); });
    if (!entries.length) {
      add(host, node("div", "empty", "This run recorded no failure types."));
      $("#failure-clear").hidden = true;
      return;
    }
    const max = entries[0][1];
    entries.forEach(function (pair) {
      const type = pair[0];
      const count = pair[1];
      const b = node("button", "bar");
      b.type = "button";
      b.setAttribute("aria-pressed", state.runs.failure === type ? "true" : "false");
      b.title = "Filter the table by " + type;
      if (type === "unsafe_statement") b.classList.add("tone-fail");
      else if (type === "false_alarm") b.classList.add("tone-warn");
      else if (type.indexOf("reaction") !== -1 || type === "missed_escalation" ||
        type === "did_not_ask_decisive" || type === "no_substantive_advice") b.classList.add("tone-act");
      const name = node("span", "bname", type);
      const fill = document.createElement("progress");
      fill.className = "bfill";
      fill.max = 100;
      fill.value = max ? (100 * count / max) : 0;
      fill.setAttribute("aria-label", type + ": " + count);
      add(b, name, fill, node("span", "bcount", String(count)));
      b.addEventListener("click", function () {
        state.runs.failure = state.runs.failure === type ? null : type;
        renderFailureChart();
        renderRunTable();
      });
      add(host, b);
    });
    $("#failure-clear").hidden = !state.runs.failure;
  }

  function renderRunTable() {
    const body = clear($("#run-tbody"));
    const all = state.runs.rows || [];
    const filter = state.runs.failure;
    const rows = filter
      ? all.filter(function (r) { return rowFailures(r).indexOf(filter) !== -1; })
      : all;
    const count = $("#table-count");
    count.textContent = rows.length + " of " + all.length + " rows" + (filter ? " · failure " + filter : "");
    $("#failure-clear").hidden = !filter;
    if (!rows.length) {
      const tr = node("tr");
      const td = node("td");
      td.colSpan = 10;
      add(td, node("div", "empty", "No rows match this filter."));
      add(tr, td);
      add(body, tr);
      return;
    }
    const frag = document.createDocumentFragment();
    rows.forEach(function (row) {
      const tr = node("tr");
      tr.tabIndex = 0;
      tr.setAttribute("title", "Open " + row.case_id + " in the read-only inspector");
      function open() { openReadonly(row); }
      tr.addEventListener("click", open);
      tr.addEventListener("keydown", function (ev) {
        if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); open(); }
      });
      add(tr,
        cell(row.case_id, "casecell"),
        cell(row.journey, "journeycell"),
        cell(row.language, "langcell"),
        cell(row.benign ? "yes" : "—", "truecell" + (row.benign ? " yes" : "")),
        cell(row.twin ? "yes" : "—", "truecell" + (row.twin ? " yes" : "")),
        splitCell(row.split),
        cell(rowOursAction(row), "actioncell"),
        cell(rowExpectedAction(row), "actioncell"),
        passCell(row.passed),
        failuresCell(row)
      );
      frag.appendChild(tr);
    });
    body.appendChild(frag);
  }

  function cell(value, cls) {
    const td = node("td", cls || "", str(value));
    return td;
  }

  function splitCell(split) {
    const td = node("td");
    add(td, badge(str(split), split === "holdout" ? "holdout" : "tune"));
    return td;
  }

  function passCell(passed) {
    const td = node("td");
    add(td, badge(passed ? "pass" : "fail", passed ? "pass" : "fail"));
    return td;
  }

  function failuresCell(row) {
    const td = node("td");
    const box = node("div", "failcell");
    const types = rowFailures(row);
    if (!types.length) add(box, node("span", "", "—"));
    types.forEach(function (type) {
      const hot = type === "unsafe_statement" || type === "false_alarm" || type === "missed_escalation";
      add(box, node("span", "fchip" + (hot ? " hot" : ""), type));
    });
    add(td, box);
    return td;
  }

  function openReadonly(row) {
    state.readonly = { row: row, run: state.runs.current || "" };
    switchView("workbench");
    renderHeader();
    renderCentreMode();
    renderControls();
    renderInspector(false);
    resetReview();
    toast("Read-only row · " + row.case_id);
  }

  function closeReadonly() {
    state.readonly = null;
    renderHeader();
    renderCentreMode();
    renderControls();
    renderInspector();
  }

  // ---------------------------------------------------------------- views

  // One view leaves before the next arrives: fade the outgoing panel out,
  // then show and fade in the incoming one, so the two never overlap.
  let viewTimer = null;

  function showView(view) {
    const els = { workbench: $("#view-workbench"), runs: $("#view-runs") };
    Object.keys(els).forEach(function (key) {
      els[key].classList.remove("view-out");
      els[key].hidden = key !== view;
    });
    replay(els[view], "view-in", 240);
  }

  function switchView(view) {
    state.view = view;
    $$(".viewtab").forEach(function (tab) {
      tab.setAttribute("aria-selected", tab.getAttribute("data-view") === view ? "true" : "false");
    });
    if (view === "runs" && !state.runs.loaded) loadRuns();
    if (viewTimer) { window.clearTimeout(viewTimer); viewTimer = null; }
    const outgoing = $("#view-workbench").hidden ? $("#view-runs") : $("#view-workbench");
    if (reduced() || outgoing.hidden || outgoing === $("#view-" + view)) {
      showView(view);
      return;
    }
    outgoing.classList.add("view-out");
    viewTimer = window.setTimeout(function () {
      viewTimer = null;
      showView(view);
    }, 120);
  }

  // ---------------------------------------------------------------- wiring

  function initPicker() {
    $$(".picker-tab").forEach(function (tab) {
      tab.addEventListener("click", function () { setPicker(tab.getAttribute("data-picker")); });
    });

    let timer = null;
    $("#dev-q").addEventListener("input", function (ev) {
      if (timer) window.clearTimeout(timer);
      const value = ev.target.value.trim();
      timer = window.setTimeout(function () {
        state.dev.filters.q = value;
        state.dev.offset = 0;
        loadDev();
      }, 220);
    });
    ["journey", "language", "benign", "twin", "split"].forEach(function (key) {
      $("#dev-" + key).addEventListener("change", function (ev) {
        state.dev.filters[key] = ev.target.value;
        state.dev.offset = 0;
        loadDev();
      });
    });
    $("#dev-prev").addEventListener("click", function () {
      state.dev.offset = Math.max(0, state.dev.offset - state.dev.limit);
      loadDev();
    });
    $("#dev-next").addEventListener("click", function () {
      state.dev.offset += state.dev.limit;
      loadDev();
    });
    $("#free-start").addEventListener("click", startFree);
    $("#free-text").addEventListener("keydown", function (ev) {
      if ((ev.ctrlKey || ev.metaKey) && ev.key === "Enter") startFree();
    });
  }

  function initControls() {
    $("#btn-simulate").addEventListener("click", onSimulate);
    $("#btn-run").addEventListener("click", onRunToEnd);
    $("#btn-finish").addEventListener("click", onFinish);
    $("#btn-restart").addEventListener("click", onRestart);
    $("#readonly-close").addEventListener("click", closeReadonly);
    $("#composer").addEventListener("submit", function (ev) {
      ev.preventDefault();
      sendMessage($("#composer-input").value);
    });
    $("#review-save").addEventListener("click", saveReview);
    $$(".segbtn").forEach(function (b) {
      b.addEventListener("click", function () {
        state.reviewVerdict = b.getAttribute("data-verdict");
        updateReviewSeg();
      });
    });
    $("#failure-clear").addEventListener("click", function () {
      state.runs.failure = null;
      renderFailureChart();
      renderRunTable();
    });
    $$(".viewtab").forEach(function (tab) {
      tab.addEventListener("click", function () { switchView(tab.getAttribute("data-view")); });
    });
  }

  function init() {
    initPicker();
    initControls();
    loadHealth();
    setPicker("dev");
    renderControls();
    renderInspector();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
