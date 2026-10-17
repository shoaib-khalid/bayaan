import sys
import mysql.connector

sys.stdout.reconfigure(encoding="utf-8")
SULAH = int(sys.argv[1]) if len(sys.argv) > 1 else 7

c = mysql.connector.connect(host="127.0.0.1", port=3212, user="root",
                            password="root", database="bayaan")
cur = c.cursor()
cur.execute("SELECT ayah_number, segment_index, translation_text FROM translation_segments "
            "WHERE translation_id=2 AND surah_id=%s ORDER BY ayah_number, segment_index",
            (SULAH,))
by = {}
for a, i, t in cur.fetchall():
    by.setdefault(a, []).append((i, t))

JOINERS = ("اور", "پھر", "یا", "کہ", "تو", "مگر", "لیکن", "تاکہ", "بلکہ", "جبکہ")
bad = []
for a in sorted(by):
    segs = by[a]
    for k in range(len(segs) - 1):
        t = (segs[k][1] or "").rstrip()
        words = t.split()
        last = words[-1].strip("۔؟!،:") if words else ""
        if last in JOINERS:
            bad.append((a, segs[k][0], last, t[-50:]))

print(f"surah {SULAH}: dangling-joiner segments = {len(bad)}")
for b in bad:
    print(f"  {SULAH}:{b[0]} seg{b[1]} ends with '{b[2]}'  ...{b[3]}")
c.close()
