"""Where each person left off, per page and per translation.

Stored in `user_positions` rather than the session cookie for three reasons: it
survives signing out, it follows the person to another browser, and it does not
ride along on every request.

`location` is the page's query string verbatim (`?translation_id=2&surah=5&ayah=3`
or just `?surah=5&page=12`), so a page that later remembers one more thing needs
no migration here — the whole URL is restored as it was.

Resuming rule, enforced by the route rather than here:

  * a URL that carries parameters always wins, so a shared link opens where the
    link says;
  * a URL with no parameters resumes the most recently touched bookmark for
    that page, whatever translation it was in.
"""

from __future__ import annotations

from . import auth

# The pages that get a bookmark. Keeping this list explicit means a typo in a
# page's script cannot invent a context that nothing ever reads.
CONTEXTS = ("reader", "reader-mushaf", "mushaf", "editor")

MAX_LOCATION_LENGTH = 512


def save(user_id: int, context: str, translation_id: int, location: str) -> None:
    """Remember where this user was on this page, for this translation."""
    if context not in CONTEXTS:
        raise ValueError(f"unknown context: {context}")
    location = location or ""
    if not location.startswith("?"):
        location = "?" + location if location else ""
    location = location[:MAX_LOCATION_LENGTH]

    conn = auth.connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO user_positions (user_id, context, translation_id, location)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE location = VALUES(location), updated_at = NOW(6)
            """,
            (user_id, context, translation_id, location),
        )
        conn.commit()
    finally:
        conn.close()


def _query(sql: str, params: tuple) -> dict | None:
    conn = auth.connect()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, params)
        return cur.fetchone()
    finally:
        conn.close()


def get(user_id: int, context: str, translation_id: int | None = None) -> dict | None:
    """A bookmark for a page.

    With `translation_id`, that exact bookmark. Without it, the most recently
    touched one for the page — which is what a bare `/reader` should resume.
    """
    if context not in CONTEXTS:
        return None
    if translation_id is not None:
        return _query(
            """
            SELECT context, translation_id, location, updated_at
              FROM user_positions
             WHERE user_id = %s AND context = %s AND translation_id = %s
            """,
            (user_id, context, translation_id),
        )
    return _query(
        """
        SELECT context, translation_id, location, updated_at
          FROM user_positions
         WHERE user_id = %s AND context = %s
         ORDER BY updated_at DESC
         LIMIT 1
        """,
        (user_id, context),
    )


def all_for_user(user_id: int) -> list[dict]:
    conn = auth.connect()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT context, translation_id, location, updated_at
              FROM user_positions
             WHERE user_id = %s
             ORDER BY context, updated_at DESC
            """,
            (user_id,),
        )
        return cur.fetchall()
    finally:
        conn.close()


def clear(user_id: int, context: str, translation_id: int) -> int:
    conn = auth.connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            DELETE FROM user_positions
             WHERE user_id = %s AND context = %s AND translation_id = %s
            """,
            (user_id, context, translation_id),
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()
