# Bayaan — Segmentation Kit

Reusable tooling + guidance for segmenting Quran translations into word-anchored
segments, batch by batch, with a human reviewing every 50 ayahs.

## Files

| File | Purpose |
|------|---------|
| `PROMPT.md` | Copy-paste prompt to give a **new/fresh instance** when starting a batch. |
| `GUIDE.md`  | The living rulebook (segmentation criteria + hard constraints). Humans update it after reviewing batches; agents never edit it. |
| `SAMPLES.md` | Approved examples (Al-Baqarah 2:1–18) so an agent can match style. |
| `make_samples.py` | Regenerate `SAMPLES.md` + `samples/` JSON from the DB after a batch is approved. |
| `segment_ayahs.py` | The validated engine: `plan` → `check` → `commit` (+ `restore`). |
| `specs/` | Editorial spec JSON files, one per batch (written by the agent). |
| `work/` | Generated plan work-sheets (one per batch). |
| `backups/` | Automatic timestamped backups written before each `commit`. |

## Why a script (not the API)

The FastAPI `POST /segments` endpoint performs **no server-side validation**; all the
rules live in the editor JS. The segmentation engine validates **everything before
writing** (word coverage, contiguity, no ornament tokens in ranges, text fidelity to the
original), writes each batch in **one transaction**, and refuses to overwrite an
already-segmented ayah unless `--force`. It never touches `translation_originals`.

## Quick usage

```bash
cd D:\Personal_repos\bayaan

# 1. produce a work sheet for the batch (real words + original translation)
python segmentation/segment_ayahs.py plan --surah 2 --translation 2 --from 19 --to 68 --out work/2_19-68.txt

# 2. author specs/2_19-68.json from that work sheet (see segment_ayahs.py docstring)

# 3. validate only
python segmentation/segment_ayahs.py check --surah 2 --from 19 --to 68 --spec specs/2_19-68.json

# 4. validate + back up + write in one transaction
python segmentation/segment_ayahs.py commit --surah 2 --from 19 --to 68 --spec specs/2_19-68.json

# revert a bad batch
python segmentation/segment_ayahs.py restore --backup backups/segments_t2_s2_19-68_<timestamp>.json
```

## Segmenting a different translation later

Segmentation is per-translation. Before using this kit for a new `translation_id`, its
ayahs must exist as whole-ayah rows **and** its originals must be snapshotted into
`translation_originals` (see `data/002_translation_originals.sql`), then run the same
loop with `--translation <id>`.
