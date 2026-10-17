import mysql.connector

c = mysql.connector.connect(host="127.0.0.1", port=3212, user="root",
                            password="root", database="bayaan")
cur = c.cursor()
cur.execute("SELECT surah_id, ayah_number, segment_index, translation_text FROM translation_segments "
            "WHERE translation_id=2 ORDER BY surah_id, ayah_number, segment_index")

JOINERS = ("اور", "پھر", "یا", "کہ", "تو", "مگر", "لیکن", "تاکہ", "بلکہ", "جبکہ")
by = {}
for s, a, i, t in cur.fetchall():
    by.setdefault((s, a), []).append((i, t))

bad = []
for key in sorted(by):
    segs = by[key]
    for k in range(len(segs) - 1):
        t = (segs[k][1] or "").rstrip()
        words = t.split()
        last = words[-1].strip("۔؟!،:") if words else ""
        if last in JOINERS:
            bad.append((key[0], key[1], segs[k][0], last, t[-60:]))

print(f"ALL SURAHS: dangling-joiner segments = {len(bad)}")
for b in bad[:40]:
    print(f"  {b[0]}:{b[1]} seg{b[2]} ends '{b[3]}' ...{b[4]}")
c.close()
