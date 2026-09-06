#!/usr/bin/env python3
"""
segment_ayahs.py — token-light, validated segmentation writer for Bayaan.

Purpose
-------
Turn an *editorial spec* (per-ayah segment word-ranges + end-markers copied from the
original translation) into `translation_segments` rows, with every hard constraint in
GUIDE.md checked BEFORE anything is written. Agents use this instead of hand-writing
SQL or calling POST /segments (which has no server-side validation).

Modes
-----
  plan   [--out work.txt]   Print/save a compact work sheet (real words + original
                            translation) for a surah/ayah range, so the agent can
                            author the spec accurately and cheaply.
  check  --spec spec.json   Validate a spec fully. Nothing is written.
  commit --spec spec.json   Validate, back up, then write the batch in ONE transaction.
  restore --backup f.json   Restore a batch from a backup file (after a bad commit).

Spec JSON shape
---------------
{
  "translation": 2,
  "surah": 2,
  "from": 19,
  "to": 68,
  "ayahs": {
    "19": [
      {"from": 1,  "to": 5,  "until": "…exact tail substring of the original…"},
      {"from": 6,  "to": 9,  "until": "…exact tail of segment 2…"},
      {"from": 10, "to": 20}              // last segment: no "until" (takes remainder)
    ]
  }
}
word indices are 1-based *real-word* indices (as shown by `plan`).
"until" must be an exact substring of the original translation that ends the segment.

Run (from D:\\Personal_repos\\bayaan):
  python segmentation/segment_ayahs.py plan   --surah 2 --from 19 --to 68 --out work/2_19-68.txt
  python segmentation/segment_ayahs.py check  --surah 2 --from 19 --to 68 --spec specs/2_19-68.json
  python segmentation/segment_ayahs.py commit --surah 2 --from 19 --to 68 --spec specs/2_19-68.json
"""
import argparse
import json
import re
import sys
import time

try:
    import mysql.connector
except ImportError:  # pragma: no cover
    sys.exit("mysql-connector-python is required (pip install mysql-connector-python)")

AR_LETTER = re.compile(r"[\u0621-\u064a\u0671-\u06d3]")
WS = re.compile(r"\s+")

DB_DEFAULTS = dict(host="127.0.0.1", port=3212, user="root", password="root", database="bayaan")


def db(args):
    cfg = dict(DB_DEFAULTS)
    cfg.update({k: v for k, v in vars(args).items()
                if v is not None and k in ("host", "port", "user", "password", "database")})
    return mysql.connector.connect(**cfg)


# ---------------------------------------------------------------- data helpers
def real_words(cur, surah, ayah):
    """(word_index -> id) for letter-bearing tokens only."""
    out, last = {}, 0
    cur.execute("SELECT id, word_index, text FROM ayah_words WHERE surah_id=%s AND ayah_number=%s ORDER BY word_index",
                (surah, ayah))
    for wid, wi, txt in cur.fetchall():
        if AR_LETTER.search(txt):
            out[wi] = wid
            last = max(last, wi)
    return out, last


def original_text(cur, translation, surah, ayah):
    """Pristine whole-ayah translation from translation_originals (or, if missing,
    the single whole-ayah segment text as a fallback). Returns None if absent."""
    cur.execute("SELECT translation_text FROM translation_originals "
                "WHERE translation_id=%s AND surah_id=%s AND ayah_number=%s", (translation, surah, ayah))
    row = cur.fetchone()
    if row and row[0]:
        return row[0]
    cur.execute("SELECT translation_text FROM translation_segments "
                "WHERE translation_id=%s AND surah_id=%s AND ayah_number=%s ORDER BY segment_index", (translation, surah, ayah))
    segs = cur.fetchall()
    if len(segs) == 1:
        return segs[0][0]
    return None


def segmentation_state(cur, translation, surah, ayah):
    cur.execute("SELECT word_start, word_end FROM translation_segments "
                "WHERE translation_id=%s AND surah_id=%s AND ayah_number=%s", (translation, surah, ayah))
    rows = cur.fetchall()
    return rows


def is_whole(rows, first_id, last_id):
    return len(rows) == 1 and rows[0][0] == first_id and rows[0][1] >= last_id


# ---------------------------------------------------------------- spec helpers
def partition(orig, entries):
    """Split ORIG at each 'until' end-marker; the final entry gets the remainder.
    Returns list of trimmed segment texts aligned to entries."""
    parts, cur = [], 0
    for i, e in enumerate(entries):
        marker = e.get("until")
        if marker:
            idx = orig.find(marker, cur)
            if idx < 0:
                raise ValueError(f"'until' marker not found in original: {marker!r}")
            parts.append(orig[cur:idx + len(marker)])
            cur = idx + len(marker)
        else:
            if i != len(entries) - 1:
                raise ValueError("only the last segment of an ayah may omit 'until'")
            parts.append(orig[cur:])
            cur = len(orig)
    return [p.strip() for p in parts]


def validate_ayah(cur, translation, surah, ayah, entries, force):
    """Return (status, message, rows); status is 'ok' | 'skip' | 'error'."""
    wi2id, last_wi = real_words(cur, surah, ayah)
    if not wi2id:
        return "error", "ayah has no real words", None

    existing = segmentation_state(cur, translation, surah, ayah)
    first_id = wi2id[1]
    # Only ayahs that are still a single whole-ayah segment should be touched.
    # Already-segmented ayahs are SKIPPED (never overwritten) unless --force.
    if existing and not is_whole(existing, first_id, wi2id[last_wi]) and not force:
        return "skip", f"already segmented ({len(existing)} segments) — skipped (use --force to overwrite)", None

    orig = original_text(cur, translation, surah, ayah)
    if orig is None:
        return "error", "no original whole-ayah translation found (translation_originals missing?)", None

    # word range continuity + coverage
    prev = 0
    for e in entries:
        f, t = int(e["from"]), int(e["to"])
        if f != prev + 1:
            return "error", f"word range gap at from={f} (previous end {prev})", None
        if f not in wi2id or t not in wi2id or t < f:
            return "error", f"bad word range {f}-{t}", None
        prev = t
    if prev != last_wi:
        return "error", f"segments end at word {prev} but ayah has {last_wi} real words", None
    if not entries:
        return "error", "no segments given", None

    # text partition + fidelity (ignoring whitespace, nothing lost or added)
    try:
        texts = partition(orig, entries)
    except ValueError as exc:
        return "error", str(exc), None
    if len(texts) != len(entries):
        return "error", "text/entry count mismatch", None
    if any(not t for t in texts):
        return "error", "a segment has empty translation text", None
    if WS.sub("", "".join(texts)) != WS.sub("", orig):
        return "error", "segment texts do not reproduce the original translation (words lost/changed?)", None

    rows = [(wi2id[int(e["from"])], wi2id[int(e["to"])], t) for e, t in zip(entries, texts)]
    return "ok", "", rows


# ---------------------------------------------------------------- modes
def cmd_plan(args):
    conn = db(args)
    cur = conn.cursor()
    lines = [f"# surah {args.surah} translation {args.translation} ayahs {args.ayfrom}-{args.ayto}",
             f"# word indices are REAL-word indices; 'orig' is the pristine translation."]
    for ayah in range(args.ayfrom, args.ayto + 1):
        wi2id, last = real_words(cur, args.surah, ayah)
        orig = original_text(cur, args.translation, args.surah, ayah)
        existing = segmentation_state(cur, args.translation, args.surah, ayah)
        status = ""
        if existing:
            status = "  # ALREADY SEGMENTED (skip unless human says --force)" if not is_whole(existing, wi2id[1] if wi2id else -1, wi2id[last] if wi2id else -1) else "  # whole (unsegmented)"
        lines.append("")
        lines.append(f"ayah {ayah}  real_words={last}{status}")
        if wi2id:
            wt = sorted(list(_word_texts(cur, args.surah, ayah, wi2id)))
            lines.append("words: " + " | ".join(f"{wi}.{txt}" for wi, txt in wt))
        lines.append("orig : " + (orig if orig is not None else "<none>"))
    conn.close()
    text = "\n".join(lines)
    if args.out:
        import os
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"plan written to {args.out}")
    else:
        print(text)


def _word_texts(cur, surah, ayah, wi2id):
    cur.execute("SELECT word_index, text FROM ayah_words WHERE surah_id=%s AND ayah_number=%s ORDER BY word_index", (surah, ayah))
    for wi, txt in cur.fetchall():
        if wi in wi2id:
            yield wi, txt


def load_spec(path):
    with open(path, encoding="utf-8") as fh:
        spec = json.load(fh)
    for key in ("translation", "surah", "ayahs"):
        if key not in spec:
            raise SystemExit(f"spec missing '{key}'")
    return spec


def run_batch(args, write):
    spec = load_spec(args.spec)
    translation, surah = int(spec["translation"]), int(spec["surah"])
    ayfrom = int(spec.get("from", args.ayfrom))
    ayto = int(spec.get("to", args.ayto))
    conn = db(args)
    cur = conn.cursor()

    # Process exactly the ayahs listed in the spec (their numbers must be in range).
    all_rows, skipped, problems = {}, [], []
    for key in sorted(spec.get("ayahs", {}), key=int):
        ayah = int(key)
        if ayah < ayfrom or ayah > ayto:
            problems.append(f"ayah {ayah}: outside spec range {ayfrom}-{ayto}")
            continue
        entries = spec["ayahs"][key]
        status, msg, rows = validate_ayah(cur, translation, surah, ayah, entries, args.force)
        if status == "ok":
            all_rows[ayah] = rows
        elif status == "skip":
            skipped.append((ayah, msg))
        else:
            problems.append(f"ayah {ayah}: {msg}")

    if problems:
        conn.close()
        print("VALIDATION FAILED — nothing written:")
        for p in problems:
            print("  -", p)
        return 1

    for ayah, msg in skipped:
        print(f"  skip ayah {ayah}: {msg}")
    if not all_rows:
        conn.close()
        print(f"No ayahs to write (all {len(skipped)} in range are already segmented or absent). Nothing changed.")
        return 0
    print(f"Validation OK: {len(all_rows)} ayah(s) to write, {len(skipped)} skipped (already segmented).")

    if not write:
        conn.close()
        print("Dry-run (check) complete — no DB changes.")
        return 0

    # ---- commit ----
    import os
    backup_dir = args.backup_dir or "backups"
    os.makedirs(backup_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup_path = os.path.join(backup_dir, f"segments_t{translation}_s{surah}_{ayfrom}-{ayto}_{stamp}.json")
    backup = {}
    for ayah in all_rows:
        cur.execute("SELECT segment_index, word_start, word_end, translation_text FROM translation_segments "
                    "WHERE translation_id=%s AND surah_id=%s AND ayah_number=%s ORDER BY segment_index",
                    (translation, surah, ayah))
        backup[str(ayah)] = cur.fetchall()
    with open(backup_path, "w", encoding="utf-8") as fh:
        json.dump({"translation": translation, "surah": surah, "from": ayfrom, "to": ayto, "segments": backup},
                  fh, ensure_ascii=False, indent=1)

    try:
        total = 0
        for ayah, rows in all_rows.items():
            cur.execute("DELETE FROM translation_segments WHERE translation_id=%s AND surah_id=%s AND ayah_number=%s",
                        (translation, surah, ayah))
            for i, (ws, we, text) in enumerate(rows, 1):
                cur.execute(
                    "INSERT INTO translation_segments "
                    "(surah_id, ayah_number, translation_id, segment_index, word_start, word_end, translation_text) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (surah, ayah, translation, i, ws, we, text))
                total += 1
        conn.commit()
        print(f"COMMITTED {total} segments for {len(all_rows)} ayahs. Backup: {backup_path}")
    except Exception as exc:  # pragma: no cover
        conn.rollback()
        print(f"ERROR, rolled back (nothing changed): {exc}")
        return 1
    finally:
        conn.close()
    return 0


def cmd_restore(args):
    with open(args.backup, encoding="utf-8") as fh:
        data = json.load(fh)
    translation, surah = int(data["translation"]), int(data["surah"])
    conn = db(args)
    cur = conn.cursor()
    try:
        for ayah, rows in data.get("segments", {}).items():
            cur.execute("DELETE FROM translation_segments WHERE translation_id=%s AND surah_id=%s AND ayah_number=%s",
                        (translation, surah, int(ayah)))
            for si, ws, we, text in rows:
                cur.execute(
                    "INSERT INTO translation_segments "
                    "(surah_id, ayah_number, translation_id, segment_index, word_start, word_end, translation_text) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (surah, int(ayah), translation, si, ws, we, text))
        conn.commit()
        print("Restored from", args.backup)
    except Exception as exc:  # pragma: no cover
        conn.rollback()
        print("Restore failed, rolled back:", exc)
        return 1
    finally:
        conn.close()
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="mode", required=True)

    def common(sp):
        sp.add_argument("--host", default=None); sp.add_argument("--port", type=int, default=None)
        sp.add_argument("--user", default=None); sp.add_argument("--password", default=None)
        sp.add_argument("--database", default=None)

    sp = sub.add_parser("plan"); common(sp)
    sp.add_argument("--surah", type=int, required=True)
    sp.add_argument("--translation", type=int, default=2)
    sp.add_argument("--from", dest="ayfrom", type=int, required=True)
    sp.add_argument("--to", dest="ayto", type=int, required=True)
    sp.add_argument("--out", default=None)

    for name in ("check", "commit"):
        sp = sub.add_parser(name); common(sp)
        sp.add_argument("--surah", type=int, required=True)
        sp.add_argument("--translation", type=int, default=2)
        sp.add_argument("--from", dest="ayfrom", type=int, default=None)
        sp.add_argument("--to", dest="ayto", type=int, default=None)
        sp.add_argument("--spec", required=True)
        sp.add_argument("--force", action="store_true", help="allow overwriting already-segmented ayahs")
        if name == "commit":
            sp.add_argument("--backup-dir", default="backups")

    sp = sub.add_parser("restore"); common(sp)
    sp.add_argument("--backup", required=True)

    args = p.parse_args(argv)
    if args.mode == "plan":
        return cmd_plan(args)
    if args.mode == "restore":
        return cmd_restore(args)
    return run_batch(args, write=(args.mode == "commit"))


if __name__ == "__main__":
    sys.exit(main())
