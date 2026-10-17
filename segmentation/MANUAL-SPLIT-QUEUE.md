# Manual-split queue — verb-deferred ayahs

Ayahs where Maulana Jalandhari's Urdu places the **verb / verdict at the end of a long
enumeration** (object-first order). These cannot be split by the normal rule
("a segment must contain the predicate that completes its own meaning") without leaving
a dangling fragment, so they are left long for **manual review**.

Rule being applied everywhere else: never cut between a list/object and its verb, and never
cut before a deferred verdict such as `حرام ہیں` / `نشانیاں ہیں` / `بیحرمتی نہ کرنا`.

---

## 1. Unsplittable blocks created by verb placement

| Ayah | Segment(s) | Words | Why it cannot be split |
|---|---|---|---|
| 2:136 | seg1 | 28 | Chain `اس پر … ان پر … ان پر …`; verdict `سب پر ایمان لائے` only at the end |
| 2:164 | seg1 (whole ayah) | 43 | Six evidentials `… میں`; verdict `نشانیاں ہیں` only at the end |
| 5:2 | seg1 | 23 | `اور نہ … کی` prohibitions list; verb `بیحرمتی نہ کرنا` is at the start, list follows |
| 5:3 | seg1 | 18 | `حُرِّمَتْ` opens the ayah but Urdu verdict `یہ سب حرام ہیں` arrives after the whole list |
| 4:23 | seg1–seg2 | 19 | Maḥram list `تم پر تمہاری مائیں …`; verdict `حرام کر دی گئی ہیں` at the end |
| 4:36 | seg2 | 18 | Relatives list; verb `سب کے ساتھ حسن سلوک کرو` at the end |
| 5:44 | seg2 | 17 | `اور مشائخ اور علماء بھی` borrows its verb from the previous clause |

---

## 2. Other blocks ≥ 15 Arabic words (candidates for manual splitting)

These are not necessarily wrong — each ends on a verb — but they are long enough that you
may want to hand-tune them.

| Ayah | Segment | Words |
|---|---|---|
| 2:22 | seg1 | 17 |
| 2:75 | seg2 | 15 |
| 2:76 | seg2 | 15 |
| 2:79 | seg1 | 15 |
| 2:90 | seg2 | 16 |
| 2:105 | seg1 | 16 |
| 2:109 | seg1 | 21 |
| 2:120 | seg3 | 16 |
| 2:126 | seg1 | 18 |
| 2:143 | seg2 | 15 |
| 2:159 | seg1 | 15 |
| 2:165 | seg3 | 15 |
| 2:196 | seg4 | 16 |
| 2:213 | seg2 | 15 |
| 2:228 | seg2 | 16 |
| 2:229 | seg2 | 15 |
| 2:247 | seg2 | 15 |
| 2:249 | seg3 | 15 |
| 2:249 | seg6 | 15 |
| 2:253 | seg4 | 21 |
| 2:260 | seg4 | 18 |
| 2:261 | seg1 | 17 |
| 2:264 | seg1 | 18 |
| 2:265 | seg1 | 18 |
| 2:266 | seg1 | 18 |
| 2:282 | seg5 | 17 |
| 2:282 | seg7 | 16 |
| 3:14 | seg1 | 16 |
| 3:15 | seg2 | 16 |
| 3:21 | seg1 | 15 |
| 3:30 | seg1 | 20 |
| 3:64 | seg2 | 16 |
| 3:79 | seg1 | 18 |
| 3:81 | seg1 | 19 |
| 3:93 | seg1 | 17 |
| 3:117 | seg1 | 17 |
| 3:154 | seg2 | 17 |
| 3:156 | seg2 | 15 |
| 3:167 | seg1 | 17 |
| 3:195 | seg1 | 16 |
| 3:195 | seg2 | 19 |
| 4:43 | seg3 | 15 |
| 4:47 | seg2 | 20 |
| 4:102 | seg6 | 15 |
| 4:136 | seg1 | 16 |
| 5:57 | seg2 | 15 |

---

## 3. How to regenerate this list

```sql
SELECT s.surah_id, s.ayah_number, s.segment_index,
       ws.word_index, we.word_index,
       we.word_index - ws.word_index + 1 AS words
FROM translation_segments s
JOIN ayah_words ws ON ws.id = s.word_start
JOIN ayah_words we ON we.id = s.word_end
WHERE s.translation_id = 2
  AND we.word_index - ws.word_index + 1 >= 15
ORDER BY s.surah_id, s.ayah_number, s.segment_index;
```

After you hand-edit an ayah (via `app/static/editor.html` or a re-split spec), remove its
row above.
