import re
import mysql.connector

SULAH = 58

c = mysql.connector.connect(host="127.0.0.1", port=3212, user="root", password="root", database="bayaan")
cur = c.cursor()

cur.execute("SELECT COUNT(*), COUNT(DISTINCT ayah_number) FROM translation_segments "
            "WHERE translation_id=2 AND surah_id=%s", (SULAH,))
tot, ay = cur.fetchone()
print(f"surah {SULAH}: {tot} segments | ayahs covered: {ay}")

cur.execute("SELECT ayah_number, COUNT(*) FROM translation_segments WHERE translation_id=2 "
            "AND surah_id=%s GROUP BY ayah_number HAVING COUNT(*)=1 ORDER BY ayah_number", (SULAH,))
print("single-segment ayahs:", [r[0] for r in cur.fetchall()])

cur.execute("SELECT ayah_number, translation_text FROM translation_segments "
            "WHERE translation_id=2 AND surah_id=%s ORDER BY ayah_number, segment_index", (SULAH,))
joined = {}
for a, t in cur.fetchall():
    joined.setdefault(a, []).append(t)

cur.execute("SELECT ayah_number, translation_text FROM translation_originals "
            "WHERE translation_id=2 AND surah_id=%s", (SULAH,))
orig = dict(cur.fetchall())

norm = lambda s: re.sub(r"\s+", "", s or "")
bad = [a for a in sorted(orig) if norm(" ".join(joined.get(a, []))) != norm(orig[a])]
print("ayahs in originals:", len(orig))
print("full-lossless reconstruction:", "YES (all match, whitespace-normalised)" if not bad else f"NO -> {bad}")

c.close()

