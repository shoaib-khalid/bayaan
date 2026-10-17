import mysql.connector
c = mysql.connector.connect(host="127.0.0.1", port=3212, user="root", password="root", database="bayaan")
cur = c.cursor()
cur.execute("SELECT segment_index, word_start, word_end, translation_text FROM translation_segments "
            "WHERE translation_id=2 AND surah_id=10 AND ayah_number=59 ORDER BY segment_index")
rows = cur.fetchall()
cur.execute("SELECT translation_text FROM translation_originals "
            "WHERE translation_id=2 AND surah_id=10 AND ayah_number=59")
o = cur.fetchone()[0]
with open("work/_10_59.txt", "w", encoding="utf-8") as f:
    f.write("ORIG: " + o + "\n\n")
    for r in rows:
        f.write(f"seg{r[0]} {r[1]}-{r[2]}: {r[3]}\n")
print("ok")
c.close()
