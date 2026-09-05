# Bayaan — TODO / Deferred work

Backlog captured 2026‑09‑05. See `ReadMe.md` (handoff doc) for full context.

## 1. Re-classify ornament tokens properly (deferred — see note below)

**Why it matters:** `ayah_words.is_symbol` was populated with a crude heuristic
(`is_symbol = 1 if len(text.strip()) <= 2`) in `data/import-quran-aya-words.py`.
End-of-ayah ornament tokens (e.g. `۟ۙ\uf500`) are usually 3 code points, so they
were stored with `is_symbol = 0`. As a result **2,798 of the 6,236** Jalandhri
segments have `word_end` pointing at an ornament token instead of the last real
word.

**Impact today:** low — the API + renderer already re-derive "is this a real
word?" from the Arabic-letter rule, so ornaments are never highlighted and are
rendered only once at the ayah end. We intentionally deferred this fix.

**Recommended fix (when we do it):**

1. A token is an ornament ⇔ it contains **no Arabic letter**. Use a regex like
   `[\u0621-\u064a\u0671-\u06d3]` (letters). Ornament tokens are only pause
   marks/diacritics + a Private-Use glyph (e.g. `۟ۙ\uf500`).
2. Backfill the flag, e.g. (after verifying on a copy / with a dry SELECT first):

   ```sql
   UPDATE ayah_words
   SET is_symbol = (text NOT REGEXP '[\\u0621-\\u064a\\u0671-\\u06d3]');
   ```

3. Rebuild `translation_segments` ranges so `word_start` = first real word and
   `word_end` = **last real word** (letter-bearing token) of the ayah. Re-run
   the import path used for Jalandhri (`deen_jalandhri_scraper/scripts/import_to_bayaan.py`)
   after updating its `word_end` rule, or write a one-off UPDATE that re-points
   `word_end` to the last letter-bearing `ayah_words.id` per ayah.
4. Add a verification query: count segments whose `word_end` token has no Arabic
   letter → should be **0**.

**Do NOT** simply delete the ornament rows: the Quran Foundation IndoPak font
turns those PUA tokens into the visible numbered ayah-end markers, so they must
still be rendered at the end of the ayah.

## 2. Sentence-level segmentation of Jalandhri (translation_id=2)

Current data is 1 segment per ayah (whole-ayah translation). Long ayahs should
be split into sentence/phrase segments so Layout A (interlinear) can show each
sentence's Arabic words on one line with its Urdu directly beneath. This is
**editorial work** — needs a segment editor (UI) or a carefully reviewed import.
Each new segment needs `translation_text` and exact `word_start`/`word_end`
(as `ayah_words.id`, contiguous, covering every real word exactly once,
non-overlapping, no gaps).

## 3. Populate bayan-ul-quran (translation_id=1) segments

`translations.id = 1` is registered but has zero segments.

## 4. Legacy API inconsistency

`POST /segments` accepts `Segment.start/end` described as word indices, but the
table stores `word_start`/`word_end` as FKs to `ayah_words.id`. Any writer must
pass global `ayah_words.id` values (the FK enforces it). Align the docs/API or
the schema comment when convenient.

## 5. Reader polish (quran-reader / static reader)

- Highlight only word tokens, never ornament tokens.
- Per-line `unicode-bidi: isolate` for RTL safety.
- Words that embed pause marks internally (e.g. `عَلَیْهِمْ ۙ۬ۦ`) render as-is.
- Mushaf pagination for Layout A; surah navigation; zoom (deen.pk has a
  `data-zoom` cookie pattern worth copying for font-size controls).
