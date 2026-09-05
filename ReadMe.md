# Bayaan

Quran reading app: renders the Arabic text of the Qur'an with **Urdu translations that are aligned to word ranges within each ayah** (segment-based alignment), instead of dumping one whole translation under the whole ayah.

> **Handoff note (2026‑09‑05):** This file is the single source of truth / handoff document. If you are a new agent starting here, read this whole file plus `TODO.md`. The live MySQL database `bayaan` (127.0.0.1:3212, root/root) is **fully loaded** and the minimal renderer works — see [Quick start](#quick-start).

---

## 1. Repositories involved

| Repo | Role |
|------|------|
| `D:\Personal_repos\bayaan` (this repo) | MySQL schema + data, FastAPI backend, minimal HTML reader |
| `D:\Personal_repos\deen_jalandhri_scraper` | Scraper that produced the **Urdu translation of Maulana Fateh Muhammad Jalandhari** from deen.pk (data in `data/raw/extracted/surah_*.json`) |
| `D:\Personal_repos\quran-reader` | Older Next.js **visual prototype** (fonts, mushaf look). Keep only as a style reference; the working renderer now lives in this repo under `app/static/reader.html`. |

---

## 2. Data model & where the data came from

### 2.1 Arabic text — `ayah_words` (authoritative)

`ayah_words` was populated from the **Quran Foundation IndoPak Nastaleeq word dataset** (`data/indopak-nastaleeq.json`, 83,668 keys). It is the same word-level corpus the Quran Foundation font is designed to render (the Pakistani / "Indopak" printed-mushaf look).

- Rows: `id` (global, sequential, referenced by segments), `surah_id`, `ayah_number`, `word_index` (1..N within an ayah), `location` (`surah:ayah:word`), `text`, `is_symbol`.
- Counts: 114 surahs, 6,236 ayahs, 83,668 word rows.
- **The full ayah is reconstructed by joining the rows of an ayah in `word_index` order with spaces** and rendering RTL with the Quran Foundation IndoPak font. No separate `ayah_text` column is stored (avoiding drift).

### 2.2 Words vs. end-of-ayah ornament tokens ⚠️

The last token of (almost) every ayah is **not a word** — it is the end-of-ayah ornament, e.g. `۟ۙ\uf500`. It contains **no Arabic letter**; its Private-Use character (`\uf500…\uf61e`) is a glyph selector the **Quran Foundation IndoPak font** turns into the numbered ayah-end ornament. Such tokens must:

- be rendered (they produce the ayah marker), but **only once, at the very end of the ayah**;
- **never** sit inside a segment's word range or be highlighted as a word.

**Reliable rule (used by the API):** a token is a real word ⇔ it contains an Arabic letter (regex `[\u0621-\u064a\u0671-\u06d3]`).

**Known flaw:** the DB column `ayah_words.is_symbol` was filled with a crude heuristic (`is_symbol = 1 if len(text) <= 2`), which mis-classifies many ornament tokens (`len == 3`). Consequence: **2,798 of 6,236 segments currently have `word_end` pointing at an ornament token.** This is *harmless for rendering* (the renderer filters by the Arabic-letter rule), but should be fixed properly. See `TODO.md`.

### 2.3 Translations — `translations` + `translation_segments`

- `translations`: `1 = bayan-ul-quran (urdu)`, `2 = fateh-muhammad-jalandhry (urdu)`.
- `translation_segments`: one row per (translation, surah, ayah, segment). Columns:
  - `word_start`, `word_end` → **foreign keys to `ayah_words.id`** (global ids — NOT `word_index`). ⚠️ The legacy `POST /segments` body used *word_index* semantics, which contradicts the FK; anything writing segments must pass `ayah_words.id`.
  - `segment_index` = segment order (1-based) within the ayah for that translation.
  - `translation_text` = the Urdu for that word range.
- **Current state:** `translation_id = 2` (Jalandhri) loaded as **1 segment per ayah** → 6,236 rows. `translation_id = 1` is registered but has **no segments** yet.

### 2.4 Jalandhri import mapping (deen.pk → DB)

The scraper (`deen_jalandhri_scraper`) captured deen.pk's **Urdu translation only** (not deen.pk's Arabic). Import logic lives in `D:\Personal_repos\deen_jalandhri_scraper\scripts\import_to_bayaan.py` and maps:

- Surahs 2–114: deen.pk ayah `k` → DB ayah `k` (1:1).
- Surah 1: deen.pk **does not count the basmala** as ayah 1, the DB does. So:
  - `meta.basmala_translation` → DB (surah 1, ayah 1)
  - deen.pk records ayah `k` (1..6) → DB ayah `k+1` (2..7)
  - (other surahs' `basmala_translation` is ignored — it is not an ayah in the DB.)
- Total: 6,235 scraped records + 1 basmala = **6,236** segments.

---

## 3. Terminology / why we do NOT mix Arabic sources

deen.pk and the Quran Foundation corpus are the **same printed-IndoPak style** but a **different normalization/orthography**: same recitation, different underlying Unicode code points.

Example (Al-Fatiha ayah 2):

- Quran Foundation / DB: `اَلْحَمْدُ لِلّٰهِ رَبِّ الْعٰلَمِیْنَ`
- deen.pk: `اَلۡحَمۡدُ لِلّٰہِ رَبِّ الۡعٰلَمِیۡنَ`

Differences include: sukun written as `U+0652` (DB) vs `U+06E1` (deen.pk), different heh forms, and deen.pk encodes the ayah marker inline as `﴿۱﴾` text characters while the Quran Foundation data encodes it as a PUA glyph for its font.

**Consequences / decisions:**

- `ayah_words` (Quran Foundation) is the **single source of truth for Arabic** — never scrape/import Arabic from deen.pk.
- Everything word-anchored (segments, highlights) depends on `ayah_words.id`, so Arabic must be rendered word-by-word from `ayah_words`.
- The Quran Foundation IndoPak font must be used for that text (it carries the PUA ornament glyphs). With any other font those PUA characters render as boxes.

---

## 4. Rendering goals (product spec)

Desired UX — **not** deen.pk's side-by-side (Arabic right, Urdu left) layout. Instead:

> The Arabic ("script") of a segment sits on top; its Urdu translation sits **directly below** it. Segment boundaries force a line break. Empty remainder of a line stays empty (no justification).

The user's mental model (mushaf with Urdu translation): if segment 1's Urdu is ~10 words (fills its line) while the matching Arabic is only ~6–7 words, the Arabic line has leftover empty space — fine, leave it empty; segment 2 starts on the next line. **The translation segment is the deciding factor for which words of the ayah are rendered above it.** Only the words in that segment's range are shown on that segment's Arabic line.

### Layout A — Interlinear (primary target)

```
[ayah marker]  <Arabic words of segment 1 … (empty rest of line)>
               <Urdu translation of segment 1>
               <Arabic words of segment 2 … (empty rest of line)>
               <Urdu translation of segment 2>
               …
```

Currently, because we have 1 segment per ayah, Layout A renders one Arabic line + one Urdu line per ayah. When sentence-level segmentation lands, each sentence becomes its own segment → its own line pair.

### Layout B — Flowing mushaf + alternating highlight (secondary / later)

Everything normal: the full ayah's Arabic flows and wraps continuously (justified). Each word is colored by its segment with **alternating colors** (blue → yellow → blue → …) so each segment stands out. The Urdu segments are listed below (in order), each prefixed with a matching color chip.

### Honest technical limitation

With Nastaliq, Arabic wraps unpredictably and a segment's phrase can straddle two visual lines, so you **cannot** guarantee a translation sits pixel-aligned under its exact words. Layout A solves this by making each segment its own *block* (translation under the block). Layout B gives the reading-order highlight instead of geometric under-alignment.

---

## 5. Fonts

- **Arabic:** Quran Foundation IndoPak Nastaleeq — CDN:
  `https://verses.quran.foundation/fonts/quran/hafs/nastaleeq/indopak/indopak-nastaleeq-waqf-lazim-v4.2.1.woff2`
  (family name in the reader: `"IndoPak Quran"`). Bundled font archives also exist under `fonts/` (tarteel.ai variant).
- **Urdu:** Noto Nastaliq Urdu (Google Fonts). For a denser printed feel, Jameel Noori Nastaleeq is the classic but has licensing caveats.
- Local font copies: `D:\Personal_repos\bayaan\fonts\` (ttf/woff/woff2 zip + usage notes).

---

## 6. API (FastAPI, this repo)

Run (from `D:\Personal_repos\bayaan`):

```bash
python -m uvicorn app.app:app --host 127.0.0.1 --port 8000
```

DB connection is read from `app/config.py` ← `app/.env` (defaults already match the live DB: `127.0.0.1:3212`, root/root, db `bayaan`).

| Endpoint | Purpose |
|----------|---------|
| `GET /` | Tiny index with links |
| `GET /reader?translation_id=2&surah=1` | Minimal HTML renderer (uses the API) |
| `GET /surah/{surah_id}?translation_id=2` | **Everything a renderer needs**: surah meta, translation meta, and per ayah → `words[]` (`id`, `word_index`, `text`, `is_word`) + `segments[]` (`segment_index`, `word_start`/`word_end` ids, `word_start_index`/`word_end_index`, `translation_text`) |
| `GET /ayah/{surah_id}/{ayah_number}` | Legacy: words of one ayah |
| `GET /segments/{translation_id}/{surah_id}/{ayah_number}` | Legacy: segments of one ayah |
| `POST /segments` | Legacy: overwrite segments for an ayah (⚠️ body uses word indices; ensure ids align with the FK) |
| `GET /docs` | Swagger |

Renderer: `app/static/reader.html` — plain HTML/JS, no framework; toggles Layout A / Layout B; surah + translation selectors.

---

## 7. Roadmap / next steps (priority order)

1. **Sentence-level segmentation (the big one).** Build a segment editor (or a curated import) that splits each long ayah into sentence/phrase segments, each with `translation_text` + exact `word_start`/`word_end` (`ayah_words.id`). This is editorial work; Jalandhri text is continuous, so it must be split sensibly per sentence.
2. **Proper ornament classification + word-range fix** (see `TODO.md`): re-derive `is_symbol` from the Arabic-letter rule and correct the 2,798 segment `word_end`s so ranges contain only real words.
3. Load segments for `translation_id = 1` (`bayan-ul-quran`) the same way.
4. Paginate Layout A into mushaf-like pages; surah navigation; tune line spacing/empty-space behavior.
5. Reader hardening: highlight only word tokens (never ornaments), correct bidi (`unicode-bidi: isolate` per line), handling of words that contain internal pause marks (e.g. `عَلَیْهِمْ ۙ۬ۦ`).
6. Tests for the API + import idempotency; seed verification counts (6,236 etc.).

---

## 8. DB quick facts (verified 2026‑09‑05)

- `surahs` 114 · `ayahs` 6,236 (Surah 1 has 7 — includes basmala as ayah 1) · `ayah_words` 83,668 (every ayah has words).
- `translations`: 2 rows (as above). `translation_segments`: 6,236 rows for `translation_id = 2`; 0 for `1`.
- Schema dump: `data/db-schema.sql` (also the original data load script: `data/import-quran-aya-words.py`).
