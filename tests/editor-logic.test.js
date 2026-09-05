/*
 * Unit tests for the pure segmentation logic in app/static/editor-logic.js.
 * Run with:  node --test tests/       (or:  npm test)
 * No external dependencies — uses Node's built-in node:test runner.
 */
"use strict";
const { describe, it } = require("node:test");
const assert = require("node:assert/strict");
const E = require("../app/static/editor-logic.js");

// ---- helpers -------------------------------------------------------------
// Build a real-words list with sequential ids (Arabic letters so isWord()=true).
function W(ids, startWordIndex = 1) {
  return ids.map((id, i) => ({ id, word_index: startWordIndex + i, text: "كلمة" }));
}

describe("token classification", () => {
  it("treats Arabic-letter tokens as words", () => {
    assert.equal(E.isWord("بِسْمِ"), true);
    assert.equal(E.isWord("اَلْحَمْدُ"), true);
    assert.equal(E.isWord(""), false);
  });
  it("treats ornament/pause tokens (no Arabic letter) as ornaments", () => {
    assert.equal(E.isOrn("۟ۙ\uf500"), true);
    assert.equal(E.isOrn("۟\uf61e"), true);
    assert.equal(E.isOrn("كلمة"), false);
  });
});

describe("isWholeSegment", () => {
  const allWords = W([10, 11, 12, 13, 14, 15]);
  // NOTE: isWholeSegment consumes NORMALIZED segments ({startId,endId}).
  it("true for a single segment spanning first..last real word", () => {
    assert.equal(E.isWholeSegment([{ startId: 10, endId: 15 }], allWords), true);
  });
  it("true when the segment also ends on the trailing ornament id", () => {
    assert.equal(E.isWholeSegment([{ startId: 10, endId: 16 }], allWords), true);
  });
  it("false for a partial segment", () => {
    assert.equal(E.isWholeSegment([{ startId: 10, endId: 14 }], allWords), false);
  });
  it("false for multiple segments or empty", () => {
    assert.equal(E.isWholeSegment([{ startId: 10, endId: 12 }, { startId: 13, endId: 15 }], allWords), false);
    assert.equal(E.isWholeSegment([], allWords), false);
  });
});

describe("buildModel", () => {
  const apiWords = [
    ...W([10, 11, 12, 13, 14, 15]).map((w) => ({ ...w })),
    { id: 16, word_index: 7, text: "۟ۙ\uf500" }, // ornament
  ];
  it("un-segments a stored whole-ayah segment (incl. ornament-ended) into a work area", () => {
    const m = E.buildModel(apiWords, [{ word_start: 10, word_end: 16, translation_text: "پورا ترجمہ۔" }]);
    assert.equal(m.allWords.length, 6);
    assert.equal(m.orn.length, 1);
    assert.equal(m.segs.length, 0);
    assert.equal(m.wholeText, "پورا ترجمہ۔");
  });
  it("keeps real multi-segment state as-is", () => {
    const m = E.buildModel(apiWords, [
      { word_start: 10, word_end: 12, translation_text: "حصہ ۱" },
      { word_start: 13, word_end: 15, translation_text: "حصہ ۲" },
    ]);
    assert.equal(m.segs.length, 2);
    assert.equal(m.wholeText, "");
    assert.equal(m.segs[0].startId, 10);
    assert.equal(m.segs[1].startId, 13);
  });
});

describe("leftoverWords / addSegment", () => {
  const allWords = W([1, 2, 3, 4, 5]);
  it("reports uncovered words", () => {
    const segs = [{ startId: 1, endId: 2, text: "a" }];
    assert.deepEqual(E.leftoverWords(allWords, segs).map((w) => w.id), [3, 4, 5]);
  });
  it("adds a segment from a word-range selection + a translation substring", () => {
    const res = E.addSegment(allWords, [], "ABCDEFG", { lo: 0, hi: 1, trStart: 0, trEnd: 4 });
    assert.equal(res.ok, true);
    assert.deepEqual(res.segs.map((s) => [s.startId, s.endId, s.text]), [[1, 2, "ABCD"]]);
    assert.equal(res.wholeText, "EFG");
    assert.deepEqual(E.leftoverWords(allWords, res.segs).map((w) => w.id), [3, 4, 5]);
  });
  it("rejects when no script selection or no translation selection", () => {
    assert.equal(E.addSegment(allWords, [], "ABCDEFG", { lo: null, hi: null, trStart: 0, trEnd: 4 }).ok, false);
    assert.equal(E.addSegment(allWords, [], "ABCDEFG", { lo: 0, hi: 2, trStart: 0, trEnd: 0 }).ok, false);
    assert.equal(E.addSegment(allWords, [], "ABCDEFG", { lo: 0, hi: 99, trStart: 0, trEnd: 3 }).ok, false);
  });
  it("does not mutate its inputs", () => {
    const segsIn = [{ startId: 1, endId: 2, text: "a" }];
    const res = E.addSegment(allWords, segsIn, "XYZ", { lo: 0, hi: 0, trStart: 0, trEnd: 2 });
    assert.equal(segsIn.length, 1);
    assert.equal(res.segs.length, 2);
  });
});

describe("finalize (auto-remainder) + validate", () => {
  const allWords = W([1, 2, 3, 4, 5]);
  it("auto-adds leftover words + remaining text as the final segment (partial edit → 2 segments)", () => {
    const first = E.addSegment(allWords, [], "ABCDEFG", { lo: 0, hi: 1, trStart: 0, trEnd: 4 }); // words 1-2, text ABCD
    assert.equal(first.ok, true);
    const fin = E.finalize(allWords, first.segs, first.wholeText); // remainder EFG
    assert.equal(fin.ok, true);
    assert.equal(fin.segs.length, 2);
    assert.deepEqual(fin.segs.map((s) => [s.startId, s.endId, s.text]), [
      [1, 2, "ABCD"],
      [3, 5, "EFG"],
    ]);
  });
  it("leaves a fully-covered ayah untouched", () => {
    const segs = [{ startId: 1, endId: 3, text: "a" }, { startId: 4, endId: 5, text: "b" }];
    const fin = E.finalize(allWords, segs, "");
    assert.equal(fin.ok, true);
    assert.equal(fin.segs.length, 2);
  });
  it("rejects when leftover words exist but there is no remaining translation", () => {
    const segs = [{ startId: 1, endId: 2, text: "a" }];
    const fin = E.finalize(allWords, segs, "   ");
    assert.equal(fin.ok, false);
  });
  it("validate catches a gap (missing word)", () => {
    const segs = [{ startId: 1, endId: 2, text: "a" }, { startId: 4, endId: 5, text: "b" }];
    assert.equal(E.validate(allWords, segs).ok, false);
  });
  it("validate catches segments that do not reach the end of the ayah", () => {
    const segs = [{ startId: 1, endId: 3, text: "a" }];
    assert.equal(E.validate(allWords, segs).ok, false);
  });
  it("validate requires non-empty text in every segment", () => {
    const segs = [{ startId: 1, endId: 5, text: "  " }];
    assert.equal(E.validate(allWords, segs).ok, false);
  });
  it("validate passes on a clean full cover", () => {
    const segs = [{ startId: 1, endId: 5, text: "a" }];
    assert.equal(E.validate(allWords, segs).ok, true);
  });
});

describe("mergeAt / deleteAt", () => {
  const segs = [
    { startId: 1, endId: 2, text: "a" },
    { startId: 3, endId: 4, text: "b" },
    { startId: 5, endId: 6, text: "c" },
  ];
  it("merges a segment with the next one", () => {
    const r = E.mergeAt(segs, 0);
    assert.equal(r.ok, true);
    assert.deepEqual(r.segs.map((s) => [s.startId, s.endId, s.text]), [
      [1, 4, "a b"],
      [5, 6, "c"],
    ]);
  });
  it("cannot merge the last segment", () => {
    assert.equal(E.mergeAt(segs, 2).ok, false);
  });
  it("delete merges into next when one exists", () => {
    const r = E.deleteAt(segs, 1);
    assert.equal(r.ok, true);
    assert.equal(r.segs.length, 2);
  });
  it("delete on the last segment merges into the previous one", () => {
    const r = E.deleteAt(segs, 2);
    assert.equal(r.ok, true);
    assert.deepEqual(r.segs.map((s) => [s.startId, s.endId, s.text]), [
      [1, 2, "a"],
      [3, 6, "b c"],
    ]);
  });
  it("cannot delete the only segment", () => {
    assert.equal(E.deleteAt([{ startId: 1, endId: 6, text: "a" }], 0).ok, false);
  });
});

describe("splitAt", () => {
  const allWords = W([1, 2, 3, 4, 5, 6]);
  it("splits at a boundary word + caret, inserting the new segment in sequence", () => {
    const segs = [{ startId: 1, endId: 6, text: "ABCDEFGH" }];
    const r = E.splitAt(allWords, segs, 0, 3, 4); // word 3 = last of part 1; caret 4
    assert.equal(r.ok, true);
    assert.deepEqual(r.segs.map((s) => [s.startId, s.endId, s.text]), [
      [1, 3, "ABCD"],
      [4, 6, "EFGH"],
    ]);
  });
  it("keeps later segments' order when splitting a non-last segment", () => {
    const segs = [
      { startId: 1, endId: 6, text: "ABCDEFGH" },
      { startId: 7, endId: 9, text: "xyz" },
    ];
    const r = E.splitAt(allWords, segs, 0, 3, 4);
    assert.equal(r.ok, true);
    assert.deepEqual(r.segs.map((s) => s.startId), [1, 4, 7]);
  });
  it("rejects splitting at the very last word or with a bad caret", () => {
    const segs = [{ startId: 1, endId: 6, text: "ABCDEFGH" }];
    assert.equal(E.splitAt(allWords, segs, 0, 6, 4).ok, false);   // boundary is last word
    assert.equal(E.splitAt(allWords, segs, 0, 3, 0).ok, false);   // caret at 0
    assert.equal(E.splitAt(allWords, segs, 0, 3, 8).ok, false);   // caret at end
    assert.equal(E.splitAt(allWords, segs, 0, 99, 4).ok, false);  // word not in segment
  });
});

describe("serialize", () => {
  it("returns sorted {start,end,text} with trimmed text", () => {
    const out = E.serialize([
      { startId: 5, endId: 6, text: "  b  " },
      { startId: 1, endId: 2, text: "a" },
    ]);
    assert.deepEqual(out, [
      { start: 1, end: 2, text: "a" },
      { start: 5, end: 6, text: "b" },
    ]);
  });
});

describe("end-to-end scenario (mirrors Surah 12:70 split)", () => {
  // Words: ... فَلَمَّا جَهَّزَهُمْ بِجَهَازِهِمْ ... (ids around 32815..)
  const ids = [32815, 32816, 32817, 32818, 32819, 32820, 32821, 32822, 32823, 32824, 32825, 32826, 32827, 32828, 32829];
  const allWords = W(ids);
  const fullText = "پھر جب ان کا اسباب تیار کر دیا تو اپنے بھائی کے تھیلے میں آبخورہ رکھ دیا پھر جب وہ آبادی سے باہر نکل گئے تو ایک پکارنے والے نے آواز دی کہ قافلے والو! تم تو چور ہو۔";
  const phrase = "پھر جب ان کا اسباب تیار کر دیا";

  it("selecting the first 3 words + their phrase then Save yields exactly 2 complete segments", () => {
    const s = E.addSegment(allWords, [], fullText, {
      lo: 0, hi: 2, trStart: fullText.indexOf(phrase), trEnd: fullText.indexOf(phrase) + phrase.length,
    });
    assert.equal(s.ok, true);
    assert.deepEqual(s.segs.map((x) => [x.startId, x.endId]), [[32815, 32817]]);
    const fin = E.finalize(allWords, s.segs, s.wholeText);
    assert.equal(fin.ok, true);
    assert.equal(fin.segs.length, 2);
    assert.equal(fin.segs[0].text.trim(), phrase);
    // The two segments exactly cover the whole word range with no gaps/overlaps.
    assert.equal(E.validate(allWords, fin.segs).ok, true);
    const ser = E.serialize(fin.segs);
    assert.deepEqual(ser.map((x) => x.end), [32817, 32829]);
    assert.equal(ser[1].start, 32818);
  });

  it("auto-finalize still rejects when leftover words are in two separated runs (would overlap)", () => {
    // Only the middle is segmented → leftover sits BOTH before and after it, so a
    // single auto-added "remainder" segment would overlap the middle one.
    const segs = [{ startId: 32818, endId: 32820, text: "درمیانی حصہ" }];
    const fin = E.finalize(allWords, segs, "باقی ترجمہ");
    assert.equal(fin.ok, false);
  });
});
