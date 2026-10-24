"""Segment reads and writes, with the per-user overlay on top.

Two tables hold segments:

    translation_segments       the canonical text — what the readers show when
                               nobody has their own opinion
    user_translation_segments  one person's private copy of particular ayahs

The rule, in one sentence: **for each ayah, if the signed-in user has any rows
of their own, that ayah is served entirely from their rows; otherwise it comes
from the canonical table.** Never a mix — a person's half-finished edit of an
ayah would otherwise interleave with the canonical segments and produce a
translation that matches no one's intent.

Granularity is the ayah, not the surah. Overriding one ayah must not blank out
the other 285 in that surah.

Who writes where: an admin edits the canonical table directly. Everyone else
writes their private rows. An admin can then promote somebody's private copy
into the canonical text with `promote()` — the route into the book that keeps
personal work from being invisible.
"""

from __future__ import annotations

import mysql.connector

from . import auth


def _fetch(sql: str, params: tuple = ()) -> list[dict]:
    conn = auth.connect()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, params)
        return cur.fetchall()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

_SEGMENT_COLUMNS = "ayah_number, segment_index, word_start, word_end, translation_text"


def canonical_for_surah(surah_id: int, translation_id: int) -> list[dict]:
    return _fetch(
        f"""
        SELECT {_SEGMENT_COLUMNS}
          FROM translation_segments
         WHERE surah_id = %s AND translation_id = %s
         ORDER BY ayah_number, segment_index
        """,
        (surah_id, translation_id),
    )


def private_for_surah(user_id: int, surah_id: int, translation_id: int) -> list[dict]:
    return _fetch(
        f"""
        SELECT {_SEGMENT_COLUMNS}
          FROM user_translation_segments
         WHERE user_id = %s AND surah_id = %s AND translation_id = %s
         ORDER BY ayah_number, segment_index
        """,
        (user_id, surah_id, translation_id),
    )


def for_surah(surah_id: int, translation_id: int, user_id: int | None) -> list[dict]:
    """Segments for a whole surah, per-user overlay applied.

    Each row carries `source` ("user" or "canonical") so a page can tell the
    reader that an ayah is their own copy rather than the shared one.
    """
    canonical = canonical_for_surah(surah_id, translation_id)
    private = private_for_surah(user_id, surah_id, translation_id) if user_id else []

    # Any ayah present here wins outright, even a single row.
    overridden = {row["ayah_number"] for row in private}

    merged = []
    for row in canonical:
        if row["ayah_number"] in overridden:
            continue
        merged.append({**row, "source": "canonical"})
    for row in private:
        merged.append({**row, "source": "user"})

    merged.sort(key=lambda r: (r["ayah_number"], r["segment_index"]))
    return merged


def for_ayah(
    surah_id: int, ayah_number: int, translation_id: int, user_id: int | None
) -> list[dict]:
    """Segments of a single ayah, same rule as `for_surah`."""
    if user_id:
        private = _fetch(
            f"""
            SELECT {_SEGMENT_COLUMNS}
              FROM user_translation_segments
             WHERE user_id = %s AND surah_id = %s AND ayah_number = %s
               AND translation_id = %s
             ORDER BY segment_index
            """,
            (user_id, surah_id, ayah_number, translation_id),
        )
        if private:
            return [{**row, "source": "user"} for row in private]

    canonical = _fetch(
        f"""
        SELECT {_SEGMENT_COLUMNS}
          FROM translation_segments
         WHERE surah_id = %s AND ayah_number = %s AND translation_id = %s
         ORDER BY segment_index
        """,
        (surah_id, ayah_number, translation_id),
    )
    return [{**row, "source": "canonical"} for row in canonical]


def has_private(user_id: int, surah_id: int, ayah_number: int, translation_id: int) -> bool:
    rows = _fetch(
        """
        SELECT 1 FROM user_translation_segments
         WHERE user_id = %s AND surah_id = %s AND ayah_number = %s
           AND translation_id = %s LIMIT 1
        """,
        (user_id, surah_id, ayah_number, translation_id),
    )
    return bool(rows)


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------

def replace_ayah(
    segments: list[dict],
    translation_id: int,
    surah_id: int,
    ayah_number: int,
    user_id: int | None = None,
) -> None:
    """Overwrite all segments of one ayah.

    `user_id = None` writes the canonical table. Otherwise the rows go to that
    person's private copy, and the canonical table is not touched at all.
    """
    conn = auth.connect()
    try:
        cur = conn.cursor()
        if user_id is None:
            cur.execute(
                """
                DELETE FROM translation_segments
                 WHERE translation_id = %s AND surah_id = %s AND ayah_number = %s
                """,
                (translation_id, surah_id, ayah_number),
            )
            for index, seg in enumerate(segments, start=1):
                if seg["start"] > seg["end"]:
                    raise ValueError("start cannot be greater than end")
                cur.execute(
                    """
                    INSERT INTO translation_segments (
                        surah_id, ayah_number, translation_id,
                        segment_index, word_start, word_end, translation_text
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        surah_id,
                        ayah_number,
                        translation_id,
                        index,
                        seg["start"],
                        seg["end"],
                        seg["text"],
                    ),
                )
        else:
            cur.execute(
                """
                DELETE FROM user_translation_segments
                 WHERE user_id = %s AND translation_id = %s AND surah_id = %s
                   AND ayah_number = %s
                """,
                (user_id, translation_id, surah_id, ayah_number),
            )
            for index, seg in enumerate(segments, start=1):
                if seg["start"] > seg["end"]:
                    raise ValueError("start cannot be greater than end")
                cur.execute(
                    """
                    INSERT INTO user_translation_segments (
                        user_id, surah_id, ayah_number, translation_id,
                        segment_index, word_start, word_end, translation_text
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        user_id,
                        surah_id,
                        ayah_number,
                        translation_id,
                        index,
                        seg["start"],
                        seg["end"],
                        seg["text"],
                    ),
                )
        conn.commit()
    finally:
        conn.close()


def discard_private(
    user_id: int, translation_id: int, surah_id: int, ayah_number: int
) -> int:
    """Drop a private edit, so the ayah falls back to the canonical segments."""
    conn = auth.connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            DELETE FROM user_translation_segments
             WHERE user_id = %s AND translation_id = %s AND surah_id = %s
               AND ayah_number = %s
            """,
            (user_id, translation_id, surah_id, ayah_number),
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Promotion: private copy -> canonical text
# ---------------------------------------------------------------------------

def promote(
    user_id: int, translation_id: int, surah_id: int, ayah_number: int
) -> int:
    """Copy one ayah from a person's private rows into the canonical table.

    Done in a single transaction, so the canonical ayah is never left empty
    between the DELETE and the INSERTs. Returns the number of segments copied.
    """
    rows = _fetch(
        f"""
        SELECT {_SEGMENT_COLUMNS}
          FROM user_translation_segments
         WHERE user_id = %s AND translation_id = %s AND surah_id = %s
           AND ayah_number = %s
         ORDER BY segment_index
        """,
        (user_id, translation_id, surah_id, ayah_number),
    )
    if not rows:
        raise ValueError("that account has no private segments for this ayah")

    conn = auth.connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            DELETE FROM translation_segments
             WHERE translation_id = %s AND surah_id = %s AND ayah_number = %s
            """,
            (translation_id, surah_id, ayah_number),
        )
        for index, row in enumerate(rows, start=1):
            cur.execute(
                """
                INSERT INTO translation_segments (
                    surah_id, ayah_number, translation_id,
                    segment_index, word_start, word_end, translation_text
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    surah_id,
                    ayah_number,
                    translation_id,
                    index,
                    row["word_start"],
                    row["word_end"],
                    row["translation_text"],
                ),
            )
        conn.commit()
        return len(rows)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Browsing private work (for the admin promotion page)
# ---------------------------------------------------------------------------

def list_overrides(limit: int = 300) -> list[dict]:
    """Every ayah somebody has taken over, newest first."""
    return _fetch(
        """
        SELECT s.user_id,
               u.username,
               s.translation_id,
               s.surah_id,
               su.name_english AS surah_name,
               s.ayah_number,
               COUNT(*)                     AS segment_count,
               MAX(s.updated_at)             AS updated_at
          FROM user_translation_segments s
          JOIN users   u  ON u.id = s.user_id
          JOIN surahs  su ON su.id = s.surah_id
         GROUP BY s.user_id, u.username, s.translation_id, s.surah_id,
                  su.name_english, s.ayah_number
         ORDER BY MAX(s.updated_at) DESC
         LIMIT %s
        """,
        (limit,),
    )
