# Bayaan

Quran reading app: renders the Arabic text of the Qur'an with **Urdu translations that are aligned to word ranges within each ayah** (segment-based alignment), instead of dumping one whole translation under the whole ayah.

> **Handoff note (2026‑09‑05):** This file is the single source of truth / handoff document. If you are a new agent starting here, read this whole file plus `TODO.md`. The live MySQL database `bayaan` (127.0.0.1:3212, root/root) is **fully loaded** and the minimal renderer works — see **[HowToRun.md](HowToRun.md)** for the exact commands to start the server and open the UI.

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

### 2.5 `translation_originals` (immutable whole-ayah reference)

- A pristine copy of each ayah's **original (pre-editing) whole-ayah translation**, independent of how `translation_segments` later gets split.
- Columns: `id`, `translation_id`, `surah_id`, `ayah_number`, `translation_text`; `UNIQUE(translation_id, surah_id, ayah_number)`.
- Created by `data/002_translation_originals.sql` (migration 002) with a **check**: it copies only ayahs that currently have **exactly one** segment (`HAVING COUNT(*) = 1`) — 6,236 rows for translation 2, 0 groups skipped. If a translation is later added, run the same copy to snapshot its originals **before** segmenting it.
- Served by `GET /original/{translation_id}/{surah_id}/{ayah_number}` and shown (read-only) by the editor's **“Show original translation”** button.

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

> Full prerequisites, UI URLs, restart/troubleshooting steps: **[HowToRun.md](HowToRun.md)**.

| Endpoint | Purpose |
|----------|---------|
| `GET /` | Tiny index with links |
| `GET /surahs` | List all surahs with `name_arabic`, `name_english`, `ayah_count` (for named dropdowns) |
| `GET /reader?translation_id=2&surah=1` | Minimal HTML renderer (uses the API) |
| `GET /editor?translation_id=2&surah=12&ayah=70` | **Segment editor** (see below) |
| `GET /surah/{surah_id}?translation_id=2` | **Everything a renderer/editor needs**: surah meta, translation meta, and per ayah → `words[]` (`id`, `word_index`, `text`, `is_word`) + `segments[]` (`segment_index`, `word_start`/`word_end` ids, `word_start_index`/`word_end_index`, `translation_text`) |
| `GET /original/{translation_id}/{surah_id}/{ayah_number}` | Pristine whole-ayah translation from `translation_originals` (editor's “Show original”) |
| `GET /ayah/{surah_id}/{ayah_number}` | Legacy: words of one ayah |
| `GET /segments/{translation_id}/{surah_id}/{ayah_number}` | Legacy: segments of one ayah |
| `POST /segments` | Legacy: overwrite segments for an ayah (⚠️ body uses word indices; ensure ids align with the FK) |
| `GET /docs` | Swagger |

Renderer: `app/static/reader.html` — plain HTML/JS, no framework; toggles Layout A / Layout B; surah + translation selectors.

### 6.1 Segment editor (MVP)

`app/static/editor.html` at `GET /editor` — vanilla HTML/JS page for creating/editing word-anchored segments of one ayah.

- **Pick a verse:** Surah dropdown (named), Ayah dropdown (populated per surah), Translation dropdown. Selection is mirrored in the URL (`translation_id`, `surah`, `ayah`) so links are shareable. ◀/▶ Prev/Next move between verses.
- **Work area (top):** an un-segmented ayah (a stored single whole-ayah segment) shows its remaining Arabic as **word chips** + its remaining translation in a read-only (until ✎) box. Select words (click = single, shift+click = range), select the matching translation text, press **+ Add segment** → the pair is appended to the segments table and removed from the work area.
- **Segments table (below):** one row per segment — **script on the right, translation on the left** (deen.pk-like). Per-row actions: **✎ Edit** (translation, read-only until then), **✂ Split** (pick the last Arabic word of part 1 + place the caret in the translation, then ✓ Split here — new segment inserted in sequence), **⇄ Merge next**, **✕ Delete** (merges into next, or previous if last).
- **Save** overwrites all segments of (translation, surah, ayah) via `POST /segments` and **auto-adds any remaining un-assigned words + translation as the final segment** — so a partial edit ends as two segments, never a hole. Before writing it validates that the script words are fully covered (ordered, no gap/overlap, no missing words; the ayah ornament is ignored).
- **Start over** empties the table and merges the whole translation back into the work area (nothing saved until you press Save).
- **AutoSave**: when checked, ◀/▶ save the current ayah first so you don’t have to click Save repeatedly.
- **Show original translation**: button between the script and the translation; it loads the pristine whole-ayah text from `translation_originals` (read-only) for comparison — unaffected by your segmenting/editing.
- The “Segments of this ayah” heading shows a live count (e.g. “0 — none yet”), so it never claims segments exist when it is empty.
- Tooltips on every button plus a full **usage guide** (press `?`) explain each action and the keyboard shortcuts (`Alt+A` add, `Alt+S` save, `Ctrl+Enter` save & next, `N`/`P` next/prev, arrows in the script box with Shift to extend).

### 6.2 Tests (segmentation logic)

The segmentation **math** lives in a pure, DOM-free module **`app/static/editor-logic.js`** (single source of truth — the page and the tests both use it):

```bash
npm test        # runs  node --test tests/editor-logic.test.js   (30 tests)
```

Covers: word vs. ornament classification, whole-ayah detection, `buildModel`, `leftoverWords`, `addSegment`, auto-finalize (partial edit → 2 segments), coverage validation (gap/overlap/missing-word/empty-text), merge/delete, split ordering, serialization, and an end-to-end mirror of the Surah 12:70 split. Add a test here whenever the editor logic changes.

---

## 7. Roadmap / next steps (priority order)

1. **Sentence-level segmentation (the big one, ongoing).** A working **editor MVP shipped at `/editor`** (`app/static/editor.html`) splits each ayah into segments, each with `translation_text` + exact `word_start`/`word_end` (`ayah_words.id`). The remaining work is **editorial**: actually splitting the long continuous Jalandhri ayahs into sentence/phrase segments using the editor (translation_id=2), plus polishing editor UX (keyboard breadth, translation-1 onboarding, undo). A reusable **segmentation kit lives in `segmentation/`** (`PROMPT.md`, `GUIDE.md`, `SAMPLES.md`, `segment_ayahs.py`) so batches and other translations can be done cheaply by a fresh agent with human review every 50 ayahs.
2. **Proper ornament classification + word-range fix** (see `TODO.md`): re-derive `is_symbol` from the Arabic-letter rule and correct the 2,798 segment `word_end`s so ranges contain only real words.
3. Load segments for `translation_id = 1` (`bayan-ul-quran`) the same way.
4. Paginate Layout A into mushaf-like pages; surah navigation; tune line spacing/empty-space behavior.
5. Reader hardening: highlight only word tokens (never ornaments), correct bidi (`unicode-bidi: isolate` per line), handling of words that contain internal pause marks (e.g. `عَلَیْهِمْ ۙ۬ۦ`).
6. Add API/integration tests + import idempotency + seed verification counts. (Unit tests for the **editor logic** already exist: `npm test` → `tests/editor-logic.test.js`.)

---

## 8. DB quick facts (verified 2026‑09‑05)

- `surahs` 114 · `ayahs` 6,236 (Surah 1 has 7 — includes basmala as ayah 1) · `ayah_words` 83,668 (every ayah has words).
- `translations`: 2 rows (as above). `translation_segments`: 6,236 rows for `translation_id = 2`; 0 for `1`.
- `translation_originals`: 6,236 rows for `translation_id = 2` (immutable whole-ayah reference; migration `data/002_translation_originals.sql`).
- Schema/dump: `data/db-schema.sql`; migrations under `data/0*.sql` (e.g. `002_translation_originals.sql`); original word-load script: `data/import-quran-aya-words.py`.
