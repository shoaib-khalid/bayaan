import mysql.connector

TRANS = 2
SURAHS = [2, 3, 4, 5]

# Tokens that, appearing at the START of the next segment, suggest the previous
# segment was cut before its own predicate / verdict had arrived.
PREDICATE_STARTERS = (
    "یہ سب", "یہی", "یہ ", "وہ ", "وہی", "تو ", "پھر ", "ہیں", "ہے ",
    "تھا", "تھی", "گا ", "گی ", "گے ", "بلکہ", "مگر ", "اور یہ", "اور وہ",
    "اس ", "ان ", "جن ", "جس ", "کرو ", "دیا", "کیا", "لیا", "جاتا",
    "ہوتا", "ہوگا", "ہوں گے", "اسے", "انہیں", "اسکو", "انکو",
)
TERMINALS = ("۔", "؟", "!", ":", "؛")


def main():
    c = mysql.connector.connect(host="127.0.0.1", port=3212, user="root",
                                password="root", database="bayaan")
    cur = c.cursor()
    total_midcut = 0
    total_susp = 0
    for s in SURAHS:
        cur.execute("SELECT ayah_number, segment_index, translation_text FROM translation_segments "
                    "WHERE translation_id=%s AND surah_id=%s ORDER BY ayah_number, segment_index",
                    (TRANS, s))
        rows = cur.fetchall()
        by_ayah = {}
        for a, i, t in rows:
            by_ayah.setdefault(a, []).append(t)
        midcut, susp = [], []
        for a, segs in by_ayah.items():
            for i in range(len(segs) - 1):
                t = (segs[i] or "").rstrip()
                if t.endswith(TERMINALS):
                    continue
                midcut.append((a, i + 1))
                nxt = (segs[i + 1] or "").lstrip()
                if nxt.startswith(PREDICATE_STARTERS):
                    susp.append((a, i + 1, t[-60:], nxt[:60]))
        total_midcut += len(midcut)
        total_susp += len(susp)
        print(f"surah {s}: {len(rows)} segments | mid-sentence cuts: {len(midcut)} | "
              f"predicate-deferred (suspicious): {len(susp)}")
        for a, idx, tail, head in susp[:8]:
            print(f"   {s}:{a} seg{idx}  ...{tail}  ||  {head}...")
    print(f"\nTOTAL mid-sentence cuts: {total_midcut}")
    print(f"TOTAL predicate-deferred: {total_susp}")
    c.close()


if __name__ == "__main__":
    main()
