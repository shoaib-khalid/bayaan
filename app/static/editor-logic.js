/*
 * BayaanEditor — pure segmentation logic (no DOM, no network).
 *
 * Single source of truth for the segmentation "math" used by the editor page
 * (app/static/editor.html) AND exercised by unit tests (tests/editor-logic.test.js).
 *
 * Works with a minimal model:
 *   allWords : [{ id, word_index, text }]      real Arabic words only (no ornaments)
 *   segs     : [{ startId, endId, text }]      segments, sorted by startId
 *   wholeText: remaining/full translation string ("" once fully segmented)
 *
 * A token is an end-of-ayah ornament (NOT a word) when it contains no Arabic
 * letter — see ReadMe.md §2.2.
 *
 * UMD-ish so it loads as <script> (window.BayaanEditor) and via require() in node.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.BayaanEditor = factory();
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const AR_LETTER = /[\u0621-\u064a\u0671-\u06d3]/;
  const isWord = (t) => AR_LETTER.test(t || "");
  const isOrn = (t) => !isWord(t);

  const byStart = (a, b) => a.startId - b.startId;
  const cloneSegs = (segs) => segs.map((s) => ({ startId: s.startId, endId: s.endId, text: s.text }));

  /** Real words whose id lies inside [startId, endId] (inclusive). */
  function wordsOfRange(allWords, seg) {
    return allWords.filter((w) => seg.startId <= w.id && w.id <= seg.endId);
  }

  /** Real words not covered by any segment, in ayah order. */
  function leftoverWords(allWords, segs) {
    const covered = new Set();
    for (const s of segs) for (const w of wordsOfRange(allWords, s)) covered.add(w.id);
    return allWords.filter((w) => !covered.has(w.id));
  }

  /**
   * Is a stored set of segments just the "whole ayah, un-segmented" state?
   * True only when there is exactly one segment that starts at the first real
   * word and reaches at least the last real word (some rows also end on the
   * trailing ornament id — still whole).
   */
  function isWholeSegment(segs, allWords) {
    if (!segs || segs.length !== 1 || !allWords.length) return false;
    const s = segs[0];
    return s.startId === allWords[0].id && s.endId >= allWords[allWords.length - 1].id;
  }

  /**
   * Turn one ayah from the API into an editor model.
   * A stored single whole-ayah segment becomes an empty segment list with the
   * full text as wholeText (so the user can split it). Anything else keeps its
   * segments as-is and wholeText = "" (user works on the table).
   */
  function buildModel(apiWords, apiSegments) {
    const allWords = (apiWords || [])
      .filter((w) => isWord(w.text))
      .map((w) => ({ id: w.id, word_index: w.word_index, text: w.text }));
    const orn = (apiWords || []).filter((w) => !isWord(w.text));
    let segs = (apiSegments || [])
      .filter((s) => s.word_start && s.word_end)
      .map((s) => ({ startId: s.word_start, endId: s.word_end, text: s.translation_text }))
      .sort(byStart);
    if (isWholeSegment(segs, allWords)) {
      const wholeText = segs[0].text || "";
      segs = [];
      return { allWords, orn, segs, wholeText };
    }
    return { allWords, orn, segs, wholeText: "" };
  }

  /**
   * Add a segment from a selection.
   * o = { lo, hi, trStart, trEnd } where lo..hi are indices into the CURRENT
   * leftoverWords(allWords, segs) list, and trStart..trEnd are a substring of
   * wholeText. Returns a NEW segs + wholeText (never mutates inputs).
   */
  function addSegment(allWords, segsIn, wholeText, o) {
    const segs = cloneSegs(segsIn);
    const leftover = leftoverWords(allWords, segs);
    const lo = o.lo, hi = o.hi;
    if (!(Number.isInteger(lo) && Number.isInteger(hi) && lo >= 0 && hi >= lo && hi < leftover.length)) {
      return { ok: false, msg: "Select some script words first." };
    }
    const selWords = leftover.slice(lo, hi + 1);
    const s = o.trStart, e = o.trEnd;
    const text = e > s ? wholeText.slice(s, e) : "";
    if (!text.trim()) {
      return { ok: false, needTr: true, msg: "Now select the matching translation text." };
    }
    segs.push({ startId: selWords[0].id, endId: selWords[selWords.length - 1].id, text });
    segs.sort(byStart);
    return { ok: true, segs, wholeText: wholeText.slice(0, s) + wholeText.slice(e) };
  }

  /** Validate: ordered, non-overlapping, no gaps, cover every real word exactly once. */
  function validate(allWords, segs) {
    if (!segs.length) return { ok: false, msg: "There are no segments to save." };
    const srt = cloneSegs(segs).sort(byStart);
    let prevEnd = null;
    for (const s of srt) {
      if (!(s.text || "").trim()) return { ok: false, msg: "Every segment needs translation text." };
      if (!wordsOfRange(allWords, s).length) return { ok: false, msg: "A segment contains no words." };
      if (prevEnd !== null && s.startId !== prevEnd + 1) {
        return { ok: false, msg: "Gap or overlap between segments (missing/duplicated words). Fix with merge/delete or use Start over." };
      }
      prevEnd = s.endId;
    }
    if (allWords.length && prevEnd !== allWords[allWords.length - 1].id) {
      return { ok: false, msg: "Segments do not reach the end of the ayah." };
    }
    return { ok: true, segs: srt };
  }

  /**
   * Finalize for Save: auto-add any remaining un-assigned words + remaining
   * translation as the final segment, then validate. Returns { ok, msg, segs }.
   * Never mutates inputs; on failure the caller keeps its previous state.
   */
  function finalize(allWords, segsIn, remText) {
    const segs = cloneSegs(segsIn);
    const leftover = leftoverWords(allWords, segs);
    if (leftover.length) {
      const text = (remText || "").trim();
      if (!text) {
        return {
          ok: false,
          msg: "Some script words are still un-assigned and there is no remaining translation text for them. Select them + their translation and Add, or type the translation, before saving.",
        };
      }
      segs.push({ startId: leftover[0].id, endId: leftover[leftover.length - 1].id, text });
      segs.sort(byStart);
    }
    return validate(allWords, segs);
  }

  /** Merge segment i with segment i+1 (i must not be last). */
  function mergeAt(segsIn, i) {
    if (i < 0 || i >= segsIn.length) return { ok: false, msg: "Bad segment index." };
    if (i >= segsIn.length - 1) return { ok: false, msg: "Last segment has no next one to merge with." };
    const segs = cloneSegs(segsIn);
    const a = segs[i], b = segs[i + 1];
    a.endId = b.endId;
    a.text = [a.text, b.text].filter(Boolean).join(" ");
    segs.splice(i + 1, 1);
    return { ok: true, segs };
  }

  /** Delete segment i by merging it into the next (or the previous if it is last). */
  function deleteAt(segsIn, i) {
    if (i < 0 || i >= segsIn.length) return { ok: false, msg: "Bad segment index." };
    if (segsIn.length <= 1) return { ok: false, msg: "Deleting the only segment would empty the ayah — use “Start over” instead." };
    if (i < segsIn.length - 1) return mergeAt(segsIn, i);
    const segs = cloneSegs(segsIn);
    const p = segs[i - 1], b = segs[i];
    p.endId = b.endId;
    p.text = [p.text, b.text].filter(Boolean).join(" ");
    segs.splice(i, 1);
    return { ok: true, segs };
  }

  /**
   * Split segment i into two at a boundary.
   * boundaryWordId = last real word of the FIRST part; caret = offset in the
   * segment text where the first part ends. New segment is inserted in place.
   */
  function splitAt(allWords, segsIn, i, boundaryWordId, caret) {
    const segs = cloneSegs(segsIn);
    if (i < 0 || i >= segs.length) return { ok: false, msg: "Bad segment index." };
    const seg = segs[i];
    const ws = wordsOfRange(allWords, seg);
    const bi = ws.findIndex((w) => w.id === boundaryWordId);
    if (bi < 0) return { ok: false, msg: "The chosen word is not in this segment." };
    if (bi >= ws.length - 1) return { ok: false, msg: "Click an Arabic word that is NOT the very last one (it becomes the last word of the first part)." };
    const text = seg.text || "";
    if (!(Number.isInteger(caret) && caret > 0 && caret < text.length)) {
      return { ok: false, msg: "In the translation, put the caret (or selection end) at the end of the FIRST part’s text." };
    }
    const t1 = text.slice(0, caret).trim();
    const t2 = text.slice(caret).trim();
    if (!t1 || !t2) return { ok: false, msg: "Both parts need non-empty translation text." };
    const a = { startId: seg.startId, endId: ws[bi].id, text: t1 };
    const b = { startId: ws[bi + 1].id, endId: seg.endId, text: t2 };
    segs.splice(i, 1, a, b);
    return { ok: true, segs };
  }

  /** Convert editor segs to the API payload shape ({start,end,text}). */
  function serialize(segs) {
    return cloneSegs(segs)
      .sort(byStart)
      .map((s) => ({ start: s.startId, end: s.endId, text: (s.text || "").trim() }));
  }

  return {
    isWord, isOrn, isWholeSegment, wordsOfRange, leftoverWords,
    buildModel, addSegment, finalize, validate,
    mergeAt, deleteAt, splitAt, serialize,
  };
});
