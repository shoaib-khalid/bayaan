/* Records where the reader is, when the page changes URL without reloading.
 *
 * The server already stores a position whenever a page is *loaded* with
 * parameters. This covers movement inside a page — next page, next surah,
 * zooming — which the readers do with history.pushState and never send to the
 * server.
 *
 * Usage: <script src="/static/position-tracker.js" defer data-context="reader"></script>
 *
 * Deliberately quiet: no failures are surfaced, because losing a bookmark is
 * not worth an error dialog. Nothing is sent when the URL has no parameters,
 * since a bare URL means "resume", and saving it would overwrite the position
 * it is about to resume.
 */
(function () {
  "use strict";

  var script = document.currentScript;
  var context = script && script.getAttribute("data-context");
  if (!context) { return; }

  var pending = null;
  var lastSent = null;

  function translationId() {
    var value = new URLSearchParams(location.search).get("translation_id");
    return value || "2";
  }

  function send() {
    clearTimeout(pending);
    pending = null;

    var location_ = location.search;
    if (!location_ || location_ === lastSent) { return; }
    lastSent = location_;

    var body = new URLSearchParams();
    body.set("context", context);
    body.set("translation_id", translationId());
    body.set("location", location_);

    // keepalive lets the request survive the page being navigated away from.
    fetch("/api/position", {
      method: "POST",
      credentials: "same-origin",
      keepalive: true,
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: body.toString()
    }).catch(function () { /* a lost bookmark is not worth interrupting reading */ });
  }

  function schedule() {
    clearTimeout(pending);
    pending = setTimeout(send, 700);
  }

  // The readers navigate with pushState/replaceState, which fire no event, so
  // the two functions are wrapped and the original behaviour kept.
  ["pushState", "replaceState"].forEach(function (name) {
    var original = history[name];
    if (typeof original !== "function") { return; }
    history[name] = function () {
      var result = original.apply(this, arguments);
      schedule();
      return result;
    };
  });

  // Also catch back/forward, and the moment the tab is hidden or closed —
  // the last chance to record a page the reader reached by keyboard.
  window.addEventListener("popstate", schedule);
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden") { send(); }
  });
  window.addEventListener("pagehide", send);
})();
