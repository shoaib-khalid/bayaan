"""The user-administration page, rendered on the server.

Kept out of `app.py` because it is mostly markup, and kept server-rendered on
purpose: every action is a plain form POST followed by a redirect back here, so
the page works with JavaScript disabled, the back button behaves, and there is
no second JSON endpoint listing every account that would need its own guard.

Every value that comes from the database is escaped. Usernames are chosen by an
administrator and a display name is free text, so neither is trusted in markup.
"""

from __future__ import annotations

from html import escape
from string import Template

# Messages are keyed by the code in the redirect, so the URL carries `?ok=created`
# rather than the message itself — nothing a user typed is ever reflected back.
OK_MESSAGES = {
    "created": "Account created. Pass the password on by hand.",
    "password": "Password changed, and that account's other sessions were ended.",
    "enabled": "Account enabled.",
    "disabled": "Account disabled, and its open sessions were ended.",
}

ERROR_MESSAGES = {
    "missing": "Fill in every field.",
    "duplicate": "That username is already taken.",
    "role": "That role does not exist.",
    "short": "The password must be at least 8 characters.",
    "mismatch": "The two passwords did not match.",
    "user": "No such account.",
    "self": "You cannot disable your own account.",
    "lastadmin": "That is the last active administrator. Create another one first.",
}

_PAGE = Template("""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Users — Bayaan</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body { margin:0; padding:32px 24px 64px; background:#12100e; color:#f2ece3;
         font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif; }
  .wrap { max-width:940px; margin:0 auto; }
  h1 { margin:0 0 4px; font-size:22px; color:#c8a96a; font-weight:600; }
  h2 { margin:34px 0 12px; font-size:15px; letter-spacing:.06em; text-transform:uppercase; color:#8a7c66; }
  .sub { margin:0 0 26px; font-size:13px; color:#a89b88; }
  .sub a { color:#c8a96a; }
  .msg { margin:0 0 20px; padding:11px 14px; border-radius:6px; font-size:13.5px; }
  .msg.ok { background:#1d2b21; border:1px solid #35543d; color:#c7e6cf; }
  .msg.error { background:#3a1e1c; border:1px solid #6d3330; color:#f0c9c4; }
  table { width:100%; border-collapse:collapse; font-size:14px; }
  th { text-align:left; font-weight:600; font-size:12px; letter-spacing:.05em; text-transform:uppercase;
       color:#8a7c66; padding:0 10px 8px; border-bottom:1px solid #3a332a; }
  td { padding:10px; border-bottom:1px solid #241f18; vertical-align:middle; }
  tr.off td { color:#7d7264; }
  .name { font-weight:600; }
  .role { font-size:12px; padding:2px 8px; border-radius:999px; background:#241f18; color:#cbbfae; }
  .role.admin { background:#3a2c10; color:#e5c88a; }
  .pill { font-size:12px; color:#8a7c66; }
  .pill.on { color:#8fce9f; }
  form.inline { display:flex; gap:6px; align-items:center; }
  input[type=text], input[type=password], select {
    background:#100e0b; color:#f2ece3; border:1px solid #3a332a; border-radius:6px;
    padding:8px 10px; font:inherit; font-size:14px; }
  input[type=text]:focus, input[type=password]:focus, select:focus {
    outline:none; border-color:#c8a96a; box-shadow:0 0 0 3px rgba(200,169,106,.15); }
  button { border:0; border-radius:6px; padding:8px 12px; font:inherit; font-size:13px;
           cursor:pointer; background:#c8a96a; color:#1b1710; font-weight:600; white-space:nowrap; }
  button:hover { background:#d9bb7d; }
  button.ghost { background:#241f18; color:#cbbfae; border:1px solid #3a332a; font-weight:400; }
  button.ghost:hover { background:#2e271e; color:#f2ece3; }
  .create { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px 16px;
            padding:18px; border:1px solid #3a332a; border-radius:10px; background:#191612; }
  .create label { display:block; font-size:12px; color:#cbbfae; margin:0 0 5px; }
  .create .wide { grid-column:1 / -1; }
  .hint { font-size:12px; color:#7d7264; margin:6px 0 0; }
  @media (max-width:640px) { .create { grid-template-columns:1fr; } }
</style>
</head>
<body>
<div class="wrap">
  <h1>Users</h1>
  <p class="sub">Signed in as $who ($role). &nbsp;·&nbsp; <a href="/">Back to Bayaan</a></p>

  $banner

  <h2>Accounts</h2>
  <table>
    <thead>
      <tr><th>Username</th><th>Name</th><th>Role</th><th>Status</th><th>Last sign-in</th><th>Actions</th></tr>
    </thead>
    <tbody>
      $rows
    </tbody>
  </table>
  <p class="hint">Accounts are disabled rather than deleted, so the segments a person wrote keep their author.</p>

  <h2>Create an account</h2>
  <form class="create" method="post" action="/admin/users/create" autocomplete="off">
    <div>
      <label for="username">Username</label>
      <input id="username" name="username" type="text" required autocapitalize="none" spellcheck="false" style="width:100%">
    </div>
    <div>
      <label for="display_name">Display name <span style="color:#7d7264">(optional)</span></label>
      <input id="display_name" name="display_name" type="text" style="width:100%">
    </div>
    <div>
      <label for="role">Role</label>
      <select id="role" name="role" style="width:100%">$role_options</select>
    </div>
    <div>
      <label for="password">Initial password</label>
      <input id="password" name="password" type="password" required style="width:100%">
    </div>
    <div>
      <label for="confirm">Repeat password</label>
      <input id="confirm" name="confirm" type="password" required style="width:100%">
    </div>
    <div class="wide">
      <button type="submit">Create account</button>
      <p class="hint">At least 8 characters. There is no email step — pass it on by hand.</p>
    </div>
  </form>
</div>
</body>
</html>
""")

_ROW = Template("""<tr class="$rowclass">
  <td class="name">$username</td>
  <td>$display_name</td>
  <td><span class="role $roleclass">$role</span></td>
  <td><span class="pill $statusclass">$status</span></td>
  <td class="pill">$last_login</td>
  <td>
    <form class="inline" method="post" action="/admin/users/password" autocomplete="off">
      <input type="hidden" name="user_id" value="$id">
      <input name="password" type="password" placeholder="New password" required style="width:135px">
      <input name="confirm" type="password" placeholder="Repeat" required style="width:110px">
      <button type="submit" class="ghost">Set</button>
    </form>
    <form class="inline" method="post" action="/admin/users/active" style="margin-top:6px">
      <input type="hidden" name="user_id" value="$id">
      <input type="hidden" name="active" value="$next_active">
      <button type="submit" class="ghost">$toggle_label</button>
    </form>
  </td>
</tr>""")


def _banner(ok: str | None, error: str | None) -> str:
    if ok and ok in OK_MESSAGES:
        return f'<div class="msg ok">{escape(OK_MESSAGES[ok])}</div>'
    if error and error in ERROR_MESSAGES:
        return f'<div class="msg error">{escape(ERROR_MESSAGES[error])}</div>'
    return ""


def _row(user: dict, current_user_id: int) -> str:
    last_login = (
        user["last_login_at"].strftime("%Y-%m-%d %H:%M")
        if user["last_login_at"]
        else "never"
    )
    return _ROW.substitute(
        rowclass="" if user["is_active"] else "off",
        id=user["id"],
        username=escape(user["username"]),
        display_name=escape(user["display_name"] or "—"),
        roleclass="admin" if user["role"] == "admin" else "",
        role=escape(user["role"]),
        statusclass="on" if user["is_active"] else "",
        status="active" if user["is_active"] else "disabled",
        last_login=last_login,
        # The button always offers the opposite of the current state.
        next_active="0" if user["is_active"] else "1",
        toggle_label="Disable" if user["is_active"] else "Enable",
    )


def render_users(
    current_user: dict,
    users: list[dict],
    roles: list[dict],
    ok: str | None = None,
    error: str | None = None,
) -> str:
    role_options = "".join(
        f'<option value="{escape(r["name"])}"'
        f'{" selected" if r["name"] == "viewer" else ""}>'
        f'{escape(r["name"])} — {escape(r["description"] or "")}</option>'
        for r in roles
    )
    return _PAGE.substitute(
        who=escape(current_user.get("display_name") or current_user["username"]),
        role=escape(current_user["role"]),
        banner=_banner(ok, error),
        rows="".join(_row(u, current_user["id"]) for u in users),
        role_options=role_options,
    )
