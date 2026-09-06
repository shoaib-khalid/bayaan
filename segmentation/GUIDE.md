# Bayaan — Segmentation Guide (v1)

This is the **living rulebook** for segmenting a Quran translation into word-anchored
segments. A fresh agent should read this + `SAMPLES.md` and then use `segment_ayahs.py`.
Humans update this file after reviewing each batch — agents must **not** edit it.

---

## 1. What we are building (why segmentation is done this way)

This is for a **lecture / translation-teaching app**:

- The teacher reads (recites) one **segment** of the ayah in Arabic, then reads that
  segment's translation so the audience understands one **complete idea/sentence**.
- The reader (`/reader`) shows each segment's Arabic with the matching translation
  underneath and highlights the exact Arabic words, so the teacher knows **where to
  stop** in the verse before moving to the next segment.

**Consequence:** segmentation is decided by the **translation’s wording**, not by the
Arabic. Two different Urdu/other translations of the same ayah usually segment
**differently** (translators form sentences differently). Segmentation is therefore
**per-translation** (`translation_id`). Never reuse another translation’s segments.

## 2. The segmentation rule (primary)

> Split the ayah’s translation so that **each segment is the smallest complete,
> self-contained sentence/idea** in that translation — a phrase the teacher can recite,
> then explain. Keep the translation’s wording **untouched** (never edit/rewrite text).

Practice guidelines:
- A short ayah that is one complete sentence can stay as **one segment**.
- Longer ayahs → one segment per sentence/clause (usually 2–5 segments). Boundaries
  generally fall at strong punctuation (`۔`, `؟`) or where the Urdu thought is complete.
- Don’t split in the middle of an incomplete thought; don’t over-fragment enumerations
  unless splitting them is natural (`بہرے ہیں گونگے ہیں اندھے ہیں` may be 1 or 3 — human
  preference; default: group unless it reads better split).
- Keep segments **in order** (Arabic word order; translation order follows it).

## 3. Hard constraints (the script enforces these — do not bypass)

1. **Words only:** a segment maps to a contiguous range of **real Arabic words**
   (`ayah_words.id` of letter-bearing tokens). Never include the end-of-ayah ornament
   token (no Arabic letters) in a range — it is drawn automatically at the ayah end.
2. **Full coverage:** across a whole ayah, ranges are ordered, non-overlapping,
   gap-free, and together cover **every real word exactly once** (first real word →
   last real word).
3. **Text fidelity:** every segment’s Urdu must be an **exact, contiguous substring** of
   the original whole-ayah translation. Concatenating the segments must reproduce the
   original exactly (whitespace at boundaries may be trimmed). Copy substrings — do not
   retype or “correct” the Urdu (it may contain quirks like `جھوٹ بو لنے` or `اورانہیں`).
4. **Never touch** `translation_originals` — it stays the pristine baseline.
5. **Only segment ayahs that are not yet segmented** (currently a single whole-ayah
   segment). The script **automatically skips** already-segmented ayahs — never use
   `--force` to overwrite someone’s work unless a human explicitly says so.

## 4. When the translation does not map 1:1 to Arabic

Translators sometimes reorder or merge. Rules to stay safe:

- If the Urdu moves a clause that belongs to later Arabic words **earlier** (or vice
  versa), **merge the affected word groups** into one segment so no word range is left
  without text. Example (Al-Baqarah 2:10): the cause `بِمَا كَانُوْا يَكْذِبُوْنَ`
  (words 10–12) is translated before the punishment, so words 7–12 share one segment.
- Always prefer a valid segmentation over a “cleaner-looking” one that would leave a
  word range textless or out of order.
- If you cannot find a faithful mapping, **stop and ask the human** — do not weaken the
  constraints.

## 5. Workflow (batches of ~50)

1. Confirm the current start point with the human. Target only **unsegmented** ayahs
   (each currently a single whole-ayah segment) in the next **contiguous block** — the
   exact count is “roughly 50”, not strict.
2. Run `segment_ayahs.py plan` for that block → read the generated work file.
3. Write a **spec JSON** (word ranges + end-markers) for the unsegmented ayahs in the
   block. Already-segmented ayahs can be left out or left in the range — the script
   skips them automatically.
4. Run `segment_ayahs.py check` (dry-run). Fix any errors in the spec.
5. Run `segment_ayahs.py commit` — one transaction, with an automatic backup.
6. Verify counts, then **stop and report** for human review.
7. Human confirms; together we update this GUIDE / `SAMPLES.md` with any new guidance;
   then the next ~50.

## 6. Reuse for other translations

Segmentation is per-translation, so to segment a new translation:

1. The translation must first exist as **whole-ayah** rows, and its originals must be
   snapshotted into `translation_originals` (see `data/002_translation_originals.sql` —
   copy while each ayah still has exactly one segment).
2. Then run the same plan → spec → check → commit loop for that `translation_id`.
3. Start a fresh batch only after the human confirms the previous one.

## 7. Safety notes

- The script never writes through the FastAPI `POST /segments` (that endpoint has no
  server-side validation). Use the script, which validates **before** writing.
- The script processes only the ayahs listed in the spec; ayahs that are **already
  segmented** are **skipped** (reported), and only real validation errors abort the
  batch. `--force` exists to overwrite intentionally — do not use it casually.
- A timestamped backup JSON is written before each commit so a batch can be reverted.
