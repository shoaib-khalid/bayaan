# Prompt to hand to a NEW instance (copy-paste as your first message)

You are continuing work on the **Bayaan** Quran project (repo root:
`D:\Personal_repos\bayaan`). Your job is to **segment the Urdu translation by Maulana
Fateh Muhammad Jalandhari (`translation_id = 2`) into word-anchored segments** — ayah by
ayah, in batches of 50 — following an existing, approved rulebook. The DB is live:
MySQL `bayaan` on `127.0.0.1:3212` (root/root).

Do this first, in order:
1. Read `segmentation/GUIDE.md` (the rules + why) and `segmentation/SAMPLES.md`
   (examples already approved: Al-Baqarah 2:1–18).
2. Read `segmentation/README.md` and the docstring of `segmentation/segment_ayahs.py`.

Current state & scope:
- Al-Baqarah (surah 2) ayahs **1–18 are already segmented and approved** — never modify
  them.
- **Segment only ayahs that are NOT yet segmented** (each currently a single whole-ayah
  segment). The engine skips already-segmented ayahs automatically — never use `--force`.
- **Your first batch: ayahs 19–68** (roughly 50; if a stray ayah inside is already
  segmented, the engine skips it and you keep going). After I review it, continue with
  69–118, 119–168, 169–218, 219–268, 269–286 — always the next unsegmented contiguous
  block. When Baqarah is done we move to other surahs; later, other translations may be
  segmented with the same kit.

Workflow (one batch of ~50, then STOP and report):
1. `cd D:\Personal_repos\bayaan`
2. `python segmentation/segment_ayahs.py plan --surah 2 --translation 2 --from 19 --to 68 --out work/2_19-68.txt`
3. Read `work/2_19-68.txt`. Ignore any ayah marked `# ALREADY SEGMENTED`. For each
   unsegmented ayah, choose clause-level splits per `GUIDE.md` and author
   `specs/2_19-68.json` (word ranges; each non-last segment gets an `until` marker that
   is an **exact substring** copied from that ayah’s `orig:` line).
4. `python segmentation/segment_ayahs.py check --surah 2 --from 19 --to 68 --spec specs/2_19-68.json`
   — fix any validation errors by editing the spec. Never weaken the checks.
5. `python segmentation/segment_ayahs.py commit --surah 2 --from 19 --to 68 --spec specs/2_19-68.json`
6. Verify: re-run `check`, and confirm counts (skipped ayahs should be only ones already
   segmented). Then STOP and give me a short report: how many ayahs/segments, any tricky
   ayahs (reordering/merging), and any suggested rule updates. Do not proceed to the next
   block until I confirm.

Hard rules — do NOT violate:
- Use ONLY `segment_ayahs.py` (plan → check → commit). Never write SQL inserts by hand
  and never call the FastAPI `POST /segments` (it has no validation).
- Preserve the original translation **exactly** — copy substrings from the `orig:` line;
  never retype, “fix”, or reformat the Urdu.
- Never modify `translation_originals`, ayahs 1–18, or any ayah already showing as
  segmented (the script skips already-segmented ayahs automatically — never use `--force`
  without my say-so).
- If an ayah can’t be mapped faithfully, leave it out of the spec and ask me — do not
  improvise.
- Do NOT edit `GUIDE.md`, `SAMPLES.md`, or the scripts; I own those and update them
  after reviewing your batch.
- Work efficiently: read only the plan file you generated; don’t dump whole surahs or
  huge outputs into the chat; paste only concise summaries.

Context for decisions: this is a lecture/translation-teaching app — the teacher recites
one segment (a complete sentence in the translation), then reads its translation so the
audience understands one complete idea. Segmentation is therefore translation-driven:
the same ayah segments differently for different translations. Highlighting in the
reader shows the teacher exactly which Arabic words match each segment.
