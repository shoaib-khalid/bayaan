/* Sign-out strip, loaded by every page.
 *
 * One script instead of six copies of the same markup: it asks /api/me who is
 * signed in, and renders nothing at all when nobody is. That keeps the
 * sign-in page and any error page safe to include it in.
 *
 * It is a fixed, low-key bar in the bottom-left so it never competes with a
 * page's own toolbar, and it is hidden when printing so it cannot land in a
 * PDF of the mushaf.
 */
(function () {
  "use strict";

  var STYLE_ID = "auth-strip-style";
  var BAR_ID = "auth-strip";

  var CSS = ""
    + "#" + BAR_ID + "{position:fixed;left:14px;bottom:14px;z-index:2147483000;"
    + "display:flex;align-items:center;gap:10px;padding:7px 12px;"
    + "font:12.5px/1.4 system-ui,-apple-system,'Segoe UI',sans-serif;"
    + "color:#3d352b;background:rgba(255,252,245,.94);"
    + "border:1px solid #cdc2ae;border-radius:999px;"
    + "box-shadow:0 4px 16px rgba(0,0,0,.13);backdrop-filter:blur(3px);}"
    + "#" + BAR_ID + " .who{font-weight:600;}"
    + "#" + BAR_ID + " .role{color:#8a7c66;}"
    + "#" + BAR_ID + " .sep{color:#bdb2a0;}"
    + "#" + BAR_ID + " a{color:#7a5a1f;text-decoration:none;border-bottom:1px dotted #b9a273;}"
    + "#" + BAR_ID + " a:hover{color:#4d3a13;border-bottom-color:#7a5a1f;}"
    + "#" + BAR_ID + " button{all:unset;cursor:pointer;color:#7a5a1f;"
    + "border-bottom:1px dotted #b9a273;}"
    + "#" + BAR_ID + " button:hover{color:#4d3a13;}"
    + "@media print{#" + BAR_ID + "{display:none!important;}}"
    + "@media (max-width:520px){#" + BAR_ID + "{left:8px;bottom:8px;padding:6px 10px;font-size:11.5px;gap:7px;}}";

  function el(tag, attrs, text) {
    var node = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (key) { node.setAttribute(key, attrs[key]); });
    }
    if (text) { node.textContent = text; }
    return node;
  }

  function build(user) {
    if (document.getElementById(BAR_ID)) { return; }

    if (!document.getElementById(STYLE_ID)) {
      var style = el("style", { id: STYLE_ID });
      style.textContent = CSS;
      document.head.appendChild(style);
    }

    var bar = el("div", { id: BAR_ID });
    bar.appendChild(el("span", { "class": "who" }, user.display_name || user.username));
    bar.appendChild(el("span", { "class": "role" }, "(" + user.role + ")"));
    bar.appendChild(el("span", { "class": "sep" }, "\u00b7"));
    bar.appendChild(el("a", { href: "/me/password" }, "Change password"));

    if (user.role === "admin") {
      bar.appendChild(el("span", { "class": "sep" }, "\u00b7"));
      bar.appendChild(el("a", { href: "/admin/users" }, "Users"));
      bar.appendChild(el("span", { "class": "sep" }, "\u00b7"));
      bar.appendChild(el("a", { href: "/admin/promotions" }, "Approve"));
    }

    bar.appendChild(el("span", { "class": "sep" }, "\u00b7"));
    bar.appendChild(el("button", { type: "button", id: "auth-strip-out" }, "Sign out"));

    var out = bar.querySelector("#auth-strip-out");
    out.addEventListener("click", function () {
      // A POST keeps a stray prefetch or a link-checker from ending a session.
      var form = el("form", { method: "post", action: "/logout" });
      document.body.appendChild(form);
      form.submit();
    });

    document.body.appendChild(bar);
  }

  function start() {
    fetch("/api/me", { credentials: "same-origin", headers: { "Accept": "application/json" } })
      .then(function (response) { return response.ok ? response.json() : null; })
      .then(function (data) {
        if (!data || !data.user) { return; }
        // Pages that carry an admin-only block keep it hidden in the markup and
        // let this reveal it, so the link never appears for anyone else and no
        // page has to duplicate the role check.
        var adminBlock = document.getElementById("adminLinks");
        if (adminBlock && data.user.role === "admin") { adminBlock.hidden = false; }
        build(data.user);
      })
      .catch(function () { /* no strip is better than a broken page */ });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
