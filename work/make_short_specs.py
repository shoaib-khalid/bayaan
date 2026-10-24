"""Emit a spec file containing single-segment entries for every SHORT ayah
in a plan worksheet (default: real_words <= 8).  Long ayahs are left out and
must be hand-authored separately.

Usage:
    python work/make_short_specs.py <plan.txt> <out.json> <surah> [threshold]

The plan worksheet format (produced by segmentation/segment_ayahs.py plan) is:
    ayah 12  real_words=7  # whole (unsegmented)
    words: 1.... | 7....
    orig : <pristine urdu>
"""
import json
import re
import sys

PATH = sys.argv[1]
OUT = sys.argv[2]
SURAH = int(sys.argv[3])
THRESHOLD = int(sys.argv[4]) if len(sys.argv) > 4 else 8

text = open(PATH, encoding="utf-8").read()
pat = re.compile(r"^ayah (\d+)\s+real_words=(\d+)", re.MULTILINE)
found = [(int(a), int(n)) for a, n in pat.findall(text)]

ayahs = {}
for a, n in found:
    if n <= THRESHOLD:
        ayahs[str(a)] = [{"from": 1, "to": n}]

spec = {
    "translation": 2,
    "surah": SURAH,
    "from": min(a for a, _ in found),
    "to": max(a for a, _ in found),
    "ayahs": ayahs,
}
json.dump(spec, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

long_ones = [(a, n) for a, n in found if n > THRESHOLD]
print(f"{PATH}: {len(found)} ayahs, {len(ayahs)} short (<= {THRESHOLD} words) written to {OUT}")
print(f"hand-segment needed for {len(long_ones)} ayahs:")
print("  " + ", ".join(f"{a}({n})" for a, n in long_ones))
