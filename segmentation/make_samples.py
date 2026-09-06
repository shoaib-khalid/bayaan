#!/usr/bin/env python3
"""
make_samples.py — regenerate segmentation/SAMPLES.md + samples JSON from the DB for
an approved set of ayahs (currently Al-Baqarah translation 2, 1..18).
Run after a human approves a batch to keep SAMPLES.md current.
"""
import json
import os
import re

import mysql.connector

AR = re.compile(r"[\u0621-\u064a\u0671-\u06d3]")
HERE = os.path.dirname(os.path.abspath(__file__))
TRANSLATION, SURAH, AYFROM, AYTO = 2, 2, 1, 18


def main():
    conn = mysql.connector.connect(host="127.0.0.1", port=3212, user="root",
                                   password="root", database="bayaan")
    cur = conn.cursor()

    def real_words(ayah):
        cur.execute("SELECT word_index, text FROM ayah_words WHERE surah_id=%s AND ayah_number=%s ORDER BY word_index", (SURAH, ayah))
        return [(wi, t) for wi, t in cur.fetchall() if AR.search(t)]

    md, data = ["# Bayaan — Approved Segment Samples",
                "",
                "Surah **Al-Baqarah (2)**, translation **fateh-muhammad-jalandhry (2)**, "
                f"ayahs {AYFROM}–{AYTO}. Each line shows: segment word-range, the Arabic words of that segment, and its Urdu.",
                ""], {"surah": SURAH, "translation": TRANSLATION, "ayahs": {}}
    for ayah in range(AYFROM, AYTO + 1):
        words = real_words(ayah)
        wi2txt = dict(words)
        cur.execute("SELECT segment_index, word_start, word_end, translation_text FROM translation_segments "
                    "WHERE translation_id=%s AND surah_id=%s AND ayah_number=%s ORDER BY segment_index",
                    (TRANSLATION, SURAH, ayah))
        segs = cur.fetchall()
        cur.execute("SELECT id, word_index, text FROM ayah_words WHERE surah_id=%s AND ayah_number=%s ORDER BY word_index", (SURAH, ayah))
        id2wi = {}
        for wid, wi, t in cur.fetchall():
            if AR.search(t):
                id2wi[wid] = wi
        md.append(f"### 2:{ayah}")
        data["ayahs"][str(ayah)] = {"segments": []}
        max_real = words[-1][0] if words else 0
        for si, ws, we, text in segs:
            w0 = id2wi.get(ws, 1)
            w1 = id2wi.get(we, max_real)   # stored end may be the ornament token id
            arabic = " ".join(wi2txt[i] for i in range(w0, w1 + 1))
            md.append(f"- seg {si} [w{w0}–{w1}] **{arabic}** — {text}")
            data["ayahs"][str(ayah)]["segments"].append({"from": w0, "to": w1, "arabic": arabic, "urdu": text})
        md.append("")

    os.makedirs(os.path.join(HERE, "samples"), exist_ok=True)
    with open(os.path.join(HERE, "SAMPLES.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md))
    with open(os.path.join(HERE, "samples", f"baqarah_{AYFROM:03d}-{AYTO:03d}.json"), "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    conn.close()
    print(f"Regenerated SAMPLES.md + samples/baqarah_{AYFROM:03d}-{AYTO:03d}.json "
          f"(ayahs {AYFROM}-{AYTO}, translation {TRANSLATION}).")


if __name__ == "__main__":
    main()
