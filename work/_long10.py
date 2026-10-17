import mysql.connector

SULAH = 10
THRESHOLD = 15

c = mysql.connector.connect(host="127.0.0.1", port=3212, user="root", password="root", database="bayaan")
cur = c.cursor()

cur.execute("""
SELECT s.ayah_number, s.segment_index, ws.word_index, we.word_index,
       we.word_index - ws.word_index + 1 AS wlen, s.translation_text
FROM translation_segments s
JOIN ayah_words ws ON ws.id = s.word_start
JOIN ayah_words we ON we.id = s.word_end
WHERE s.translation_id = 2 AND s.surah_id = %s
  AND we.word_index - ws.word_index + 1 > %s
ORDER BY s.ayah_number, s.segment_index
""", (SULAH, THRESHOLD))
rows = cur.fetchall()

print(f"segments longer than {THRESHOLD} words in surah {SULAH}: {len(rows)}")
print(f"across {len(set(r[0] for r in rows))} ayahs\n")
for a, si, ws, we, n, txt in rows:
    print(f"{SULAH}:{a} seg{si} words {ws}-{we} ({n}w)")
    print(f"    {txt}")

cur.execute("SELECT COUNT(*) FROM translation_segments WHERE translation_id=2 AND surah_id=%s", (SULAH,))
print(f"\ntotal segments in surah {SULAH}: {cur.fetchone()[0]}")
c.close()

