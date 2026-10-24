import re
import mysql.connector

c = mysql.connector.connect(host="127.0.0.1", port=3212, user="root", password="root", database="bayaan")
cur = c.cursor()

norm = lambda s: re.sub(r"\s+", "", s or "")

cur.execute("SELECT surah_id, ayah_number, translation_text FROM translation_originals WHERE translation_id=2")
orig = {}
for s, a, t in cur.fetchall():
    orig[(s, a)] = t

cur.execute("SELECT surah_id, ayah_number, segment_index, translation_text FROM translation_segments "
            "WHERE translation_id=2 ORDER BY surah_id, ayah_number, segment_index")
joined = {}
segs = 0
for s, a, i, t in cur.fetchall():
    joined.setdefault((s, a), []).append(t)
    segs += 1

print("ayahs in originals:", len(orig))
print("ayahs with segments:", len(joined))
print("total segments:", segs)

missing = [k for k in orig if k not in joined]
bad = [k for k in orig if k in joined and norm(" ".join(joined[k])) != norm(orig[k])]
extra = [k for k in joined if k not in orig]

print("ayahs with no segments:", len(missing), missing[:20])
print("ayahs NOT lossless:", len(bad), bad[:20])
print("segments for unknown ayahs:", extra[:10])

surahs = sorted({s for (s, a) in orig})
bad_surahs = sorted({s for (s, a) in bad})
print("surahs covered:", len(surahs), surahs[0], "->", surahs[-1])
print("surahs with lossless failures:", bad_surahs)

c.close()
