# Bayaan — Technical Overview & Architecture

This document explains the **technical architecture, design decisions, and core challenges** behind Bayaan.

It is intended for developers working on the system or extending it.

---

## 🧠 Problem Definition

Bayaan is not a typical text-rendering application.

It solves a **text alignment problem**, specifically:

> Mapping semantically segmented translation units to precise positions within a structured source text (Qur’anic Arabic), and rendering them in a responsive UI.

---

## 🔬 Closest Existing Domains

Bayaan’s architecture overlaps with:

### 1. Bilingual Text Alignment Systems
- Used in translation research
- Aligns source and target language segments
- Usually sentence-based or phrase-based

**Difference:**
- Bayaan requires **manual, semantic segmentation**
- Not automatic or statistical alignment

---

### 2. Linguistic Annotation Tools
Examples:
- Treebanks
- Corpus annotation systems

**Similarity:**
- Text is tokenized (word-level)
- Metadata is attached to spans

**Difference:**
- Bayaan focuses on **UI rendering alignment**, not just annotation

---

### 3. Interlinear Scripture Systems
- Used in Bible study tools

**Similarity:**
- Mapping between source and translation

**Difference:**
- Bayaan allows **variable segmentation per translation**
- Not strictly word-to-word mapping

---

## 🏗️ Core Architectural Decision

### ❗ Word-Based Segmentation (Critical)

We explicitly **do NOT use character-based indexing**.

### Why character-based fails:

- Arabic includes:
  - Diacritics (harakat)
  - Ligatures
  - Unicode normalization issues
- Same visible text can have multiple underlying representations
- Substring matching becomes unreliable

---

### ✅ Word-Based Model

Each ayah is tokenized into:
surah : ayah : word_index
Example:

4:1:1 → یٰۤاَیُّهَا
4:1:2 → النَّاسُ


---

### Advantages:

- Deterministic indexing
- Stable across systems
- Easy segmentation
- Perfect for highlighting
- Avoids Unicode pitfalls

---

## 📦 Data Model Philosophy

### Separation of Concerns

| Concept | Stored Where |
|--------|-------------|
| Arabic text | `ayah_words` |
| Translation metadata | `translations` |
| Segmentation logic | `translation_segments` |

---

### Key Insight

> **Segmentation is translation-dependent, not ayah-dependent**

This is fundamental.

---

## 🔀 Segmentation Model

Each translation defines its own segmentation:

Ayah → [Segment 1, Segment 2, Segment 3...]


Each segment maps to:
[word_start, word_end]


---

### Implications

- Same ayah can have:
  - 2 segments in Urdu translation A
  - 3 segments in Urdu translation B
- No conflict in schema
- Fully flexible

---

## 🎨 Rendering Challenges

This is the most complex part of the system.

---

### 1. Alignment Problem

Goal:

> Translation must appear directly under the corresponding Arabic segment

---

### Problem:

- Arabic and Urdu lengths differ
- Line wrapping is unpredictable
- Fonts render differently
- Browser layout engines are not alignment-aware

---

### Solution Strategy (Implemented)

The mushaf reader lays the Arabic and its translation out **together**, unit by
unit, so a new ayah begins at the same x on both tracks. A unit is as much of one
ayah as fits on one row; it is as wide as whichever track needs more room, and the
narrower one is spread to match.

Arabic   [ayah 3 .......................][medallion]
Urdu     [ترجمہ .......................]

Both tracks therefore advance by the same width for every ayah, which is what
keeps a translation starting under its own Arabic. See **Layout Invariants**
below for the rules that make it hold and the traps that break it.


---

### Alternative (Rejected)

Letting the Arabic flow freely and floating the translation beneath it. Much
simpler to write, but the two tracks then drift: a translation needs roughly 1.5x
the width its Arabic occupies, so it slips a little further behind on every line,
and only about a tenth of ayah starts end up level.


---

### Why it's hard:

- Requires measuring rendered text width
- Requires layout synchronization
- Becomes a custom layout engine problem

---

## 🧱 Mushaf Reader — Layout Invariants

The mushaf reader (`app/static/reader-mushaf.html`) is a small hand-written layout
engine. It rests on a few invariants, and breaking one degrades the page in ways
that look like unrelated bugs. Read this before changing the layout.

---

### 1. The two tracks are STACKED, not side by side

A row holds the Arabic above and the translation below. Both start at the same x,
and both are entitled to the **whole measure** (540px here).

> Anything that divides a row *between* the two tracks — by their combined width,
> say — hands each barely a third of the line. The rest comes out as slack:
> enormous gaps between words, and a page count inflated by hundreds.

This one mistake cost roughly 1.5x the page count (1,195 rows / 200 pages against
719 / 120) until it was found. The share of a row is of the **whole row**, divided
by the wider track, not by their sum.

---

### 2. A row is as wide as the wider of its two tracks

So the narrower track always has **slack** to place somewhere. Where it goes:

| The unit... | Slack goes |
|---|---|
| closes an ayah (ends with the medallion) | the single gap **in front of the medallion** |
| continues the ayah on the next row | spread as word spacing |

A gap in front of the medallion reads as deliberate: the ayah runs to its
medallion and the medallion sits out at the margin, while the words keep the
spacing the script wants. The same lump at the end of a continuation line instead
reads as the line having broken early, so it is spread.

---

### 3. Measurement and rendering must agree exactly

Every word is positioned from a measured width, so any disagreement between what
was measured and what is drawn shows up as overlapping text. Four traps:

1. **Isolate when measuring.** Adjacent spans of Arabic script join and reshape,
   so a word measured beside another is not the word that renders. Measure in
   `display:inline-block` — **and render the same way**.
2. **A token is not a word.** The source Arabic packs a word, a space and a waqf
   mark into one token (`رَیْبَ ۛۖۚ`). With the row justified by `word-spacing`,
   that embedded space collects justification too, and the token draws wider than
   it was measured — measured at up to 96.5px of error. Split on whitespace first.
3. **Measure with the class it renders with.** `.w` carries 2px of horizontal
   padding, so measuring a bare span leaves every word 2px short of what is drawn.
4. **A webfont can land after the first paint.** `document.fonts.ready` resolves
   immediately when nothing is *pending*, so a stylesheet-supplied face gets
   measured against the fallback — around 12% narrower — and the layout spills
   once the real face swaps in. Fingerprint **both** faces and lay out again when
   either changes.

---

### 4. The tint is the font's content area, not the line box

`.w` is tinted by segment, and its box is the font's content area — which
`line-height` does not affect. Set the line-height to the band's own height: with
`line-height:1` the content box is taller than the line box and is centred, so the
tint spills about 16px past both rules.

---

### Verifying a change

Measure, do not eyeball. Worth asserting after any layout change:

| Check | Expected (al-Baqarah) |
|---|---|
| Words placed | all of them — 15,339 |
| Units past the column margin | 0 |
| Overlapping neighbour pairs | 0, bar sub-pixel rounding |
| Rows / pages | ~719 / ~120 |

---

## ↔️ RTL / LTR Complexity

### Current Scope:

- Arabic (RTL)
- Urdu (RTL)

---

### Future Challenge:

Supporting:
- English (LTR)
- Mixed-direction layouts

---

### Problems:

- Direction switching
- Text alignment inconsistencies
- CSS `direction` and `unicode-bidi` quirks
- Inline vs block rendering conflicts

---

### Example Challenge

Arabic (RTL) + English (LTR):

[Arabic segment →]
[← English translation]


Maintaining visual alignment is non-trivial.

---

## 🎯 Highlighting System Challenges

Bayaan aims to support:

- Segment highlighting
- Word-level highlighting (future)
- Teaching mode

---

### Problems:

1. Mapping hover/click to segment
2. Maintaining highlight across wrapped lines
3. Synchronizing Arabic + translation highlight
4. Performance with many DOM nodes

---

### Why Word-Based Helps

- Each word is a discrete unit
- Easy to assign classes:
  
  seg-1, seg-2, seg-3

  
---

## ⚙️ Performance Considerations

### Potential Issues:

- Large DOM trees (many words)
- Frequent re-renders (React)
- Complex layout recalculations

---

### Mitigations:

- Memoization
- Virtualization (if needed)
- Segment-level rendering instead of word-level (when possible)

---

## 🧩 Data Entry Challenge (Major)

Segmentation is:

- Manual
- Subjective
- Translation-dependent

---

### Implication:

You will need:

- Admin UI OR
- Structured import system

---

### Example Format

```json id="d5u4lm"
{
  "2:177": [
    { "start": 1, "end": 10, "text": "..." },
    { "start": 11, "end": 25, "text": "..." }
  ]
}

🔮 Future Extensions
1. Word-Level Translation
Mapping each Arabic word to meaning
Requires additional tables
2. Audio Synchronization
Align audio timestamps with segments
3. Tafsir Integration
Attach commentary to segments
4. Advanced Layout Engine
Pixel-perfect alignment
Possibly canvas-based rendering
⚠️ Known Limitations
Perfect inline alignment is solved in the mushaf reader, by a hand-written layout engine — it does not generalise for free to other scripts or page geometries (see Layout Invariants)
Manual segmentation is labor-intensive
Rendering complexity increases with features
🧭 Guiding Principles
Correctness over cleverness
Deterministic indexing (word-based)
Separation of data and rendering
Progressive enhancement (start simple, evolve)
📌 Summary

Bayaan is fundamentally:

A structured text alignment system built on top of a word-tokenized Qur’anic corpus.

Its complexity lies not in storage, but in:

Alignment modeling
Rendering logic
Multilingual layout handling

The decision to use word-based segmentation is central to making the system reliable, scalable, and maintainable.