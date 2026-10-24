"""Word classification shared by the API and the admin review page.

The end-of-ayah ornament tokens (e.g. `۟ۙ\uf500`) carry NO Arabic letter — they
are Private-Use glyphs the Quran Foundation IndoPak font turns into the numbered
ayah-end ornament. Treating them as ornaments (not words) lets a renderer show
the ayah marker once, at the ayah end, instead of inside a word range.

The DB `is_symbol` column was filled with a crude `len(text) <= 2` heuristic, so
the flag is re-derived from the text everywhere it matters. See TODO.md.
"""

from __future__ import annotations

import re

_ARABIC_LETTER = re.compile(r"[\u0621-\u064a\u0671-\u06d3]")


def is_word(text: str | None) -> bool:
    """True for a real Arabic word, False for an ornament or pause token.

    Two complete Quran words are encoded in the IndoPak font as ligatures and
    carry no separate letters, so they are recognised explicitly:
    U+F658 = wa-l-yatalattaf (18:19), U+F666 = thuluthayi (73:20).
    """
    value = text or ""
    return bool(_ARABIC_LETTER.search(value)) or any(
        glyph in value for glyph in ("\uf658", "\uf666")
    )
