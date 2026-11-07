/* Inline SVG icons for the demo and the lab.
 *
 * The server has no font with symbol glyphs and no emoji font: an emoji is a
 * tofu box there. So every icon in the UI is an inline SVG from this table,
 * drawn with currentColor, no external requests and no emoji.
 *
 *   Icons.svg("shield", "lg")   -> SVG markup string (fixed table, no input)
 *   Icons.el("shield", "lg")    -> SVGElement, ready to append
 *
 * A class is added next to the base "icon" class; sizes come from
 * tokens.css (svg.icon, .sm, .lg) so nothing needs a style attribute.
 */
(function () {
  "use strict";

  var PATHS = {
    message: '<path d="M21 11.6a8.1 8.1 0 0 1-8.4 8.1 8.9 8.9 0 0 1-3.3-.7L4 21l1.7-4.2A8 8 0 0 1 4 11.8 8.1 8.1 0 0 1 12.4 4 8.1 8.1 0 0 1 21 11.6Z"/>',
    mail: '<rect x="3" y="5" width="18" height="14" rx="2.5"/><path d="m3.8 7 8.2 6 8.2-6"/>',
    phone: '<path d="M6.3 3.5h3l1.6 4-2 1.4a12.4 12.4 0 0 0 6.2 6.2l1.4-2 4 1.6v3a2.5 2.5 0 0 1-2.7 2.5A16.8 16.8 0 0 1 3.8 6.2 2.5 2.5 0 0 1 6.3 3.5Z"/>',
    letter: '<path d="M6 3.5h7.2L19 9.3v11.2H6Z"/><path d="M13 3.5V9.5h6"/><path d="M9 13.5h6M9 17h4"/>',
    bell: '<path d="M18.3 8.4a6.3 6.3 0 1 0-12.6 0c0 6.4-2.6 7.6-2.6 7.6h17.8s-2.6-1.2-2.6-7.6Z"/><path d="M13.8 19.7a2.1 2.1 0 0 1-3.6 0"/>',
    shield: '<path d="m12 3.2 7.2 2.9v5.1c0 4.3-2.9 7.7-7.2 9.6-4.3-1.9-7.2-5.3-7.2-9.6V6.1Z"/><path d="m8.9 11.9 2.1 2.2 4.1-4.4"/>',
    alert: '<path d="M10.5 4.2 2.9 17.4A1.8 1.8 0 0 0 4.5 20h15a1.8 1.8 0 0 0 1.6-2.6L13.5 4.2a1.7 1.7 0 0 0-3 0Z"/><path d="M12 9.5v4"/><circle cx="12" cy="16.7" r=".9" fill="currentColor" stroke="none"/>',
    check: '<circle cx="12" cy="12" r="8.6"/><path d="m8.2 12.2 2.6 2.6 5-5.4"/>',
    help: '<circle cx="12" cy="12" r="8.6"/><path d="M9.6 9.4a2.5 2.5 0 1 1 3.7 2.2c-.9.5-1.3 1-1.3 1.9v.3"/><circle cx="12" cy="16.7" r=".9" fill="currentColor" stroke="none"/>',
    x: '<path d="M6 6l12 12M18 6 6 18"/>',
    "chevron-down": '<path d="m6 9.5 6 6 6-6"/>',
    "chevron-right": '<path d="m9.5 6 6 6-6 6"/>',
    "arrow-up": '<path d="M12 19.5V5"/><path d="m5.5 11.5 6.5-6.5 6.5 6.5"/>',
    paperclip: '<path d="M20 11.3 12.4 19a4.8 4.8 0 0 1-6.8-6.8l7.7-7.6a3.2 3.2 0 0 1 4.5 4.5l-7.6 7.6a1.6 1.6 0 0 1-2.3-2.3l6.9-6.8"/>',
    globe: '<circle cx="12" cy="12" r="8.6"/><path d="M3.6 12h16.8"/><path d="M12 3.4c2.3 2.4 3.5 5.4 3.5 8.6s-1.2 6.2-3.5 8.6c-2.3-2.4-3.5-5.4-3.5-8.6S9.7 5.8 12 3.4Z"/>',
    "new-chat": '<path d="M12.2 4.5H6.8A2.8 2.8 0 0 0 4 7.3v9.9A2.8 2.8 0 0 0 6.8 20h9.9a2.8 2.8 0 0 0 2.8-2.8v-5.4"/><path d="m10.1 14 .5-2.9 6.5-6.5a2 2 0 0 1 2.8 2.8l-6.5 6.5Z"/>',
    info: '<circle cx="12" cy="12" r="8.6"/><path d="M12 11v5.2"/><circle cx="12" cy="8" r=".95" fill="currentColor" stroke="none"/>',
    user: '<circle cx="12" cy="8.4" r="3.7"/><path d="M4.8 20.2a7.4 7.4 0 0 1 14.4 0"/>',
    briefcase: '<rect x="3" y="7.4" width="18" height="12.2" rx="2.2"/><path d="M8.8 7.4V5.6A1.6 1.6 0 0 1 10.4 4h3.2a1.6 1.6 0 0 1 1.6 1.6v1.8"/><path d="M3 12.6h18"/>',
    lock: '<rect x="4.4" y="10.2" width="15.2" height="10.4" rx="2.2"/><path d="M8 10.2V7.6a4 4 0 0 1 8 0v2.6"/>',
    refresh: '<path d="M20.2 12a8.2 8.2 0 1 1-2.4-5.8"/><path d="M20.4 3.8v5.1h-5.1"/>',
    send: '<path d="M4 11.8 20 4.4l-3.4 15.4-4.2-5.6-5.6-2.4Z"/><path d="m20 4.4-7.6 9.8"/>'
  };

  var DEFAULTS = {
    sms: "message", email: "mail", call: "phone", letter: "letter", notification: "bell"
  };

  function svg(name, cls) {
    var body = PATHS[name];
    if (!body) { body = PATHS.info; }
    var klass = "icon" + (cls ? " " + cls : "");
    return '<svg class="' + klass + '" viewBox="0 0 24 24" aria-hidden="true" focusable="false" xmlns="http://www.w3.org/2000/svg">' + body + "</svg>";
  }

  function el(name, cls) {
    var wrap = document.createElement("span");
    wrap.innerHTML = svg(name, cls); // fixed table above, never user text
    return wrap.firstChild;
  }

  window.Icons = {
    svg: svg,
    el: el,
    /* kind is one of display.attachment.kind: sms|email|call|letter|notification|null */
    forKind: function (kind) { return DEFAULTS[kind] || "message"; },
    names: Object.keys(PATHS)
  };
})();
