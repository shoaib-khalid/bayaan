#!/usr/bin/env python
"""Create and maintain Bayaan accounts.

Passwords are never emailed: an administrator sets one here and passes it on
by hand, and a forgotten password is reset the same way. There is no delete —
`disable` is the off switch, so the segments a person wrote keep their author.

    python scripts/manage_users.py list
    python scripts/manage_users.py create alice --role editor --name "Alice"
    python scripts/manage_users.py reset-password alice
    python scripts/manage_users.py disable alice
    python scripts/manage_users.py enable alice
    python scripts/manage_users.py roles
    python scripts/manage_users.py permissions

Omit --password and you are prompted twice with the input hidden, which keeps
the value out of your shell history and out of `ps` output.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

# Running `python scripts/manage_users.py` puts scripts/ on sys.path, not the
# repo root, so `app` would not import without this.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import auth  # noqa: E402  (path setup must come first)


def _read_password(args, prompt: str) -> str:
    if args.password:
        print(
            "note: --password is recorded in your shell history; "
            "omit it to be prompted instead.",
            file=sys.stderr,
        )
        return args.password
    while True:
        first = getpass.getpass(prompt)
        if not first:
            print("  the password must not be empty", file=sys.stderr)
            continue
        if first != getpass.getpass("Repeat: "):
            print("  the two entries did not match, try again", file=sys.stderr)
            continue
        return first


def _role_exists(role: str) -> bool:
    return any(row["name"] == role for row in auth.list_roles())


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_list(args) -> int:
    users = auth.list_users()
    if not users:
        print("no accounts yet — create one with:")
        print("  python scripts/manage_users.py create <username> --role admin")
        return 0
    # The header must be able to widen the column too, otherwise a short
    # username runs it into the role column ("usernamerole").
    width = max([len("username")] + [len(u["username"]) for u in users]) + 2
    print(f"{'id':>3}  {'username':<{width}}{'role':<8}{'active':<8}{'last sign-in'}")
    for u in users:
        last = u["last_login_at"].strftime("%Y-%m-%d %H:%M") if u["last_login_at"] else "never"
        print(
            f"{u['id']:>3}  {u['username']:<{width}}{u['role']:<8}"
            f"{'yes' if u['is_active'] else 'no':<8}{last}"
        )
    return 0


def cmd_create(args) -> int:
    username = args.username.strip()
    if not username:
        print("error: the username must not be empty", file=sys.stderr)
        return 1
    if not _role_exists(args.role):
        available = ", ".join(r["name"] for r in auth.list_roles())
        print(f"error: no such role '{args.role}' — choose from: {available}", file=sys.stderr)
        return 1
    if auth.get_user_by_username(username):
        print(f"error: '{username}' already exists", file=sys.stderr)
        return 1

    password = _read_password(args, f"Password for {username}: ")
    try:
        user_id = auth.create_user(
            username, password, role=args.role, display_name=args.name
        )
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"created '{username}' (id {user_id}, role {args.role})")
    print("pass the password on by hand; there is no email step.")
    return 0


def cmd_reset_password(args) -> int:
    user = auth.get_user_by_username(args.username)
    if not user:
        print(f"error: no account named '{args.username}'", file=sys.stderr)
        return 1
    password = _read_password(args, f"New password for {args.username}: ")
    auth.set_password(user["id"], password)
    # Any session opened with the old password must not survive the reset.
    auth.delete_user_sessions(user["id"])
    print(f"password changed for '{args.username}'; existing sessions were ended")
    return 0


def cmd_set_active(args, active: bool) -> int:
    user = auth.get_user_by_username(args.username)
    if not user:
        print(f"error: no account named '{args.username}'", file=sys.stderr)
        return 1
    auth.set_active(user["id"], active)
    if active:
        print(f"'{args.username}' can sign in again")
    else:
        print(f"'{args.username}' is disabled and any open session was ended")
    return 0


def cmd_roles(args) -> int:
    width = max(len(r["name"]) for r in auth.list_roles()) + 2
    for r in auth.list_roles():
        perms = sorted(auth.role_permissions(r["id"]))
        print(f"{r['name']:<{width}}{len(perms):>2} capabilities")
        print(f"{'':<{width}}{', '.join(perms)}")
    return 0


def cmd_permissions(args) -> int:
    rows = auth.list_permission_paths()
    width = max(len(r["path_prefix"]) for r in rows) + 2
    print(f"{'path':<{width}}{'methods':<10}{'access':<9}capability")
    for r in rows:
        access = "public" if r["is_public"] else "sign-in"
        print(f"{r['path_prefix']:<{width}}{r['http_methods']:<10}{access:<9}{r['perm_key']}")

    # Audit: anything the app serves without a row here is unguarded. A path
    # with no row is allowed through, which is how /static and the sign-in page
    # work — but it is also how a forgotten page would leak.
    from app.app import app as fastapi_app

    missing = []
    for route in fastapi_app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None) or set()
        if not path:
            continue
        for method in methods:
            if method in {"HEAD", "OPTIONS"}:
                continue
            if auth.resolve_rule(path, method) is None:
                missing.append((method, path))

    print()
    if missing:
        print("UNGUARDED — no permission_paths row covers these:")
        for method, path in sorted(missing, key=lambda item: (item[1], item[0])):
            print(f"  {method:<7}{path}")
        return 1
    print("every route is covered by a permission_paths row")
    return 0


# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Manage Bayaan accounts.", formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="show every account").set_defaults(func=cmd_list)
    sub.add_parser("roles", help="show roles and their capabilities").set_defaults(func=cmd_roles)
    sub.add_parser(
        "permissions", help="show protected paths, and report any unguarded route"
    ).set_defaults(func=cmd_permissions)

    create = sub.add_parser("create", help="add an account")
    create.add_argument("username")
    create.add_argument("--role", default="viewer", help="admin, editor or viewer (default: viewer)")
    create.add_argument("--name", default=None, help="display name shown in the sign-out strip")
    create.add_argument("--password", default=None, help="skip the prompt (honours shell history)")
    create.set_defaults(func=cmd_create)

    reset = sub.add_parser("reset-password", help="set a new password and end open sessions")
    reset.add_argument("username")
    reset.add_argument("--password", default=None)
    reset.set_defaults(func=cmd_reset_password)

    disable = sub.add_parser("disable", help="stop an account signing in and end its sessions")
    disable.add_argument("username")
    disable.set_defaults(func=lambda a: cmd_set_active(a, False))

    enable = sub.add_parser("enable", help="allow a disabled account to sign in again")
    enable.add_argument("username")
    enable.set_defaults(func=lambda a: cmd_set_active(a, True))

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
