#Requires -Version 7.0
<#
.SYNOPSIS
    Creates the Bayaan tracking setup on GitHub: labels, milestone, issues, and a
    repo-linked Project (v2) board.

.DESCRIPTION
    Idempotent-ish: labels are force-updated, the milestone and project are reused
    if they already exist, and issues are created once (guard with -SkipIssues on
    a re-run). Prints the resulting issue numbers and writes them to
    scripts/.issue-map.json so TODO.md can be rewritten to reference them.

    Requires an authenticated gh with the 'project' scope:

        gh auth login --hostname github.com --git-protocol https --web `
          --scopes "repo,project,read:org"

.PARAMETER Plan
    Print the actions without performing any mutation. Use this first.

.PARAMETER PushDevelop
    Also push the local 'develop' branch to origin.

.EXAMPLE
    pwsh scripts/setup-github-tracking.ps1 -Plan
    pwsh scripts/setup-github-tracking.ps1
    pwsh scripts/setup-github-tracking.ps1 -PushDevelop
#>
[CmdletBinding()]
param(
    [string]$Repo         = 'shoaib-khalid/bayaan',
    [string]$Owner        = 'shoaib-khalid',
    [string]$ProjectTitle = 'Bayaan',
    [string]$Milestone    = 'v0.2.0',
    [switch]$Plan,
    [switch]$PushDevelop
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# ---------------------------------------------------------------------------
# gh discovery (PATH may be stale in an already-open shell after winget install)
# ---------------------------------------------------------------------------
function Resolve-Gh {
    $cmd = Get-Command gh -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }

    $roots = @(
        (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages'),
        (Join-Path $env:LOCALAPPDATA 'Programs'),
        $env:ProgramFiles,
        ${env:ProgramFiles(x86)}
    ) | Where-Object { $_ -and (Test-Path $_) }

    foreach ($root in $roots) {
        $hit = Get-ChildItem -Path $root -Recurse -Filter 'gh.exe' -ErrorAction SilentlyContinue |
               Select-Object -First 1
        if ($hit) { return $hit.FullName }
    }
    throw "gh.exe not found. Install with: winget install --id GitHub.cli --exact --scope user"
}

$GhExe = Resolve-Gh
Write-Host "gh: $GhExe" -ForegroundColor DarkGray

function Invoke-Gh {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    $out = & $GhExe @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "gh $($Arguments -join ' ') failed (exit $LASTEXITCODE):`n$($out -join "`n")"
    }
    return $out
}

function Write-Step { param([string]$Text) Write-Host "`n== $Text" -ForegroundColor Cyan }
function Write-Ok   { param([string]$Text) Write-Host "   $Text" -ForegroundColor Green }
function Write-Do   { param([string]$Text) Write-Host "   [plan] $Text" -ForegroundColor Yellow }

# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------
Write-Step 'Preflight'
$authHint = 'gh auth login --hostname github.com --git-protocol https --web --scopes "repo,project,read:org"'

& $GhExe auth status *> $null
$authed = ($LASTEXITCODE -eq 0)

if (-not $authed) {
    if ($Plan) {
        Write-Host "   WARNING: not authenticated - showing the plan only." -ForegroundColor Yellow
        Write-Host "            To apply:  $authHint" -ForegroundColor Yellow
    } else {
        throw "Not authenticated. Run:  $authHint"
    }
} else {
    Write-Ok 'authenticated'

    $status = (& $GhExe auth status 2>&1) -join "`n"
    if ($status -notmatch 'project') {
        Write-Host "   WARNING: the token may lack the 'project' scope; board creation will fail." -ForegroundColor Yellow
        Write-Host "            Fix with:  gh auth refresh --scopes project" -ForegroundColor Yellow
    }

    & $GhExe repo view $Repo --json name *> $null
    if ($LASTEXITCODE -ne 0) { throw "Cannot access repo '$Repo'." }
    Write-Ok "repo $Repo reachable"
}

# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------
$Labels = @(
    @{ n = 'type:feat';  c = '0E8A16'; d = 'New capability' }
    @{ n = 'type:fix';   c = 'D73A4A'; d = 'Defect in existing behaviour' }
    @{ n = 'type:docs';  c = '0075CA'; d = 'Documentation only' }
    @{ n = 'type:test';  c = '5319E7'; d = 'Tests and verification' }
    @{ n = 'type:chore'; c = '6E7781'; d = 'Maintenance; no behaviour change' }
    @{ n = 'area:api';          c = '0052CC'; d = 'FastAPI layer (app/app.py)' }
    @{ n = 'area:editor';       c = '1D76DB'; d = 'Segment editor UI (app/static/editor.html)' }
    @{ n = 'area:reader';       c = '006B75'; d = 'Reader UI (reader.html, reader-mushaf.html)' }
    @{ n = 'area:db';           c = 'D4C5F9'; d = 'Schema, migrations, data/' }
    @{ n = 'area:data';         c = 'C2E0C6'; d = 'Translation/segment content' }
    @{ n = 'area:segmentation'; c = 'F9D0C4'; d = 'segmentation/ kit and specs' }
    @{ n = 'blocked';   c = 'B60205'; d = 'Has an open dependency' }
    @{ n = 'editorial'; c = 'FBCA04'; d = 'Requires human judgement/approval, not just code that runs' }
)

Write-Step "Labels ($($Labels.Count))"
foreach ($l in $Labels) {
    if ($Plan) { Write-Do "label $($l.n) #$($l.c)" ; continue }
    Invoke-Gh label create $l.n --repo $Repo --color $l.c --description $l.d --force | Out-Null
    Write-Ok "label $($l.n)"
}

# ---------------------------------------------------------------------------
# Milestone
# ---------------------------------------------------------------------------
Write-Step "Milestone '$Milestone'"
if ($Plan) {
    Write-Do "milestone $Milestone (reused if present)"
} else {
    $existing = @(Invoke-Gh api "repos/$Repo/milestones?state=all" --paginate | ConvertFrom-Json)
    if ($existing | Where-Object { $_.title -eq $Milestone }) {
        Write-Ok "already exists"
    } else {
        Invoke-Gh api --method POST "repos/$Repo/milestones" -f "title=$Milestone" | Out-Null
        Write-Ok 'created'
    }
}

# ---------------------------------------------------------------------------
# Issues
# ---------------------------------------------------------------------------
$Issues = @(
    [ordered]@{
        Key   = 'ornament'
        Title = 'Re-classify ornament tokens and repoint translation_segments.word_end'
        Labels = @('type:fix', 'area:db', 'area:data')
        BlockedBy = @()
        Body = @'
## Why

`ayah_words.is_symbol` was populated with a crude heuristic in `data/import-quran-aya-words.py`:

    is_symbol = 1 if len(text.strip()) <= 2

End-of-ayah ornament tokens are usually 3 code points (pause marks plus a single Private-Use
glyph, e.g. U+06DF U+06D9 U+F500), so they were stored with `is_symbol = 0`. As a result
**2,798 of the 6,236** Jalandhri segments have `word_end` pointing at an ornament token instead
of the last real word.

## Impact today

Low for rendering: `app/app.py` and the renderers re-derive "is this a real word?" from the
Arabic-letter rule, so ornaments are never highlighted and render exactly once at the ayah end.
But the **stored data is wrong**, and any consumer that trusts `is_symbol` or reads `word_end`
directly is wrong too. Fix this before mass segmentation (#2).

## Acceptance criteria

- [ ] A token is an ornament **iff** it contains no Arabic letter (rule: `[\u0621-\u064a\u0671-\u06d3]`).
- [ ] `ayah_words.is_symbol` backfilled from that rule.
- [ ] Every `translation_segments` row has `word_end` pointing at the **last letter-bearing** word
      in its range; ranges stay contiguous, non-overlapping, and cover each real word exactly once.
- [ ] Verification query below returns **0**.
- [ ] Ornament rows are **not** deleted - the Quran Foundation IndoPak font turns their PUA glyphs
      into the visible ayah-end markers, so they must still render.

## Verification query

```sql
SELECT COUNT(*) AS bad
FROM translation_segments s
JOIN ayah_words w ON w.id = s.word_end
WHERE w.text NOT REGEXP '[\u0621-\u064a\u0671-\u06d3]';
```

Expected: `bad = 0`.

## Notes

Do this on a copy or after a dry `SELECT` first. `segmentation/segment_ayahs.py` already refuses
ranges containing ornament tokens, so it can act as the reference implementation of the rule.
'@
    },
    [ordered]@{
        Key   = 'segment-epic'
        Title = 'Epic: sentence-level segmentation of Jalandhri (translation_id=2)'
        Labels = @('type:feat', 'area:segmentation', 'editorial')
        BlockedBy = @('ornament')
        Body = @'
## Goal

Split every Jalandhri ayah from one whole-ayah segment into sentence/phrase-level segments, each
with `translation_text` and an exact `word_start`/`word_end` range (as `ayah_words.id`).

## Current state

`translation_id = 2` has **1 segment per ayah** (6,236 rows). The editor MVP at `/editor` works
end-to-end, and `segmentation/` holds the batch kit (`PROMPT.md`, `GUIDE.md`, `SAMPLES.md`,
`segment_ayahs.py`). The remaining work is **editorial**, not technical.

## Constraints (non-negotiable)

- Ranges are contiguous, non-overlapping, and cover every real word exactly once.
- Ornament / end-of-ayah tokens are never inside a range.
- `translation_text` must stay faithful to `translation_originals` - re-splitting only, never rewording.
- `GUIDE.md` rules are followed verbatim; a human approves every batch.

## Definition of done

- [ ] Batches proceed via `segment_ayahs.py plan -> check -> commit` (validated, transactional, backed up).
- [ ] `GUIDE.md` updated by a **human** after review; `SAMPLES.md` regenerated from approved batches.
- [ ] No ayah remains a single whole-ayah segment where its length warrants splitting.
- [ ] A coverage audit over all of `translation_id = 2` reports no gaps, overlaps, or ornament tokens.

## Child work

Per-batch issues get created as they are scheduled; this issue tracks the overall editorial effort.
'@
    },
    [ordered]@{
        Key   = 'translation1'
        Title = 'Populate bayan-ul-quran (translation_id=1) segments'
        Labels = @('type:feat', 'area:data', 'editorial')
        BlockedBy = @('ornament', 'originals')
        Body = @'
## Why

`translations.id = 1` (bayan-ul-quran) is registered but has **0 segments**, so the reader shows
nothing for it while `translation_id = 2` (fateh-muhammad-jalandhry) renders fully.

## Sequencing (order matters)

1. Upsert this translation's ayahs as **whole-ayah rows** in `translation_segments`.
2. Snapshot its whole-ayah originals into `translation_originals` **before** segmenting - while each
   ayah still has exactly one segment (the `HAVING COUNT(*) = 1` check from
   `data/002_translation_originals.sql`). See #7.
3. Segment using the same kit and rules as #2, with `--translation 1`.

## Acceptance criteria

- [ ] `translation_segments` has 6,236 whole-ayah rows for `translation_id = 1`.
- [ ] `translation_originals` has 6,236 rows for `translation_id = 1` (single-segment check passed).
- [ ] `GET /surah/1?translation_id=1` and `/reader?translation_id=1&surah=1` render correctly.
- [ ] No range contains an ornament token; coverage is gapless and non-overlapping.

## Notes

The ordering is the trap: inserting segments before snapshotting originals destroys the ability to
recover the pristine whole-ayah text. Do not skip step 2.
'@
    },
    [ordered]@{
        Key   = 'post-segments'
        Title = 'Align POST /segments contract with the ayah_words.id foreign key'
        Labels = @('type:fix', 'area:api')
        BlockedBy = @()
        Body = @'
## Problem

`POST /segments` in `app/app.py` declares:

```python
class Segment(BaseModel):
    start: int = Field(..., description="Starting word index (inclusive)")
    end: int   = Field(..., description="Ending word index (inclusive)")
```

but `translation_segments.word_start` / `word_end` are **foreign keys to `ayah_words.id`** (global ids,
not `word_index`). The docstring says "word index", the FK requires a global id, and nothing validates
which one arrives. `app/ReadMe.md` documents the wrong (index) semantics too.

## Why it matters

The endpoint also **deletes all segments for the ayah before inserting**, with no coverage validation.
A caller passing `word_index` values either violates the FK or - worse - silently writes a valid-looking
id that belongs to a *different* ayah, corrupting ranges. Every other writer in this repo
(`segmentation/segment_ayahs.py`, `app/static/editor-logic.js`) validates first; this endpoint does not.

## Acceptance criteria

- [ ] The request model makes the id semantics unambiguous (rename to `word_start`/`word_end`, or
      document explicitly that they are `ayah_words.id`).
- [ ] Server-side validation mirroring `editor-logic.js`: ranges contiguous, ordered, no gaps or
      overlaps, every real word covered exactly once, no ornament tokens inside a range.
- [ ] Invalid payloads return `400` with a message naming the rule that failed - never a partial write.
- [ ] The delete+insert happens in a single transaction that rolls back on failure.
- [ ] `app/ReadMe.md` example body corrected.
- [ ] Tests cover: valid payload, gap, overlap, ornament in range, id from another ayah.

## Notes

Decide whether the editor should keep calling this endpoint at all, or whether it should route through
the validated `segmentation/` engine. Record the decision here.
'@
    },
    [ordered]@{
        Key   = 'reader-render'
        Title = 'Reader: highlight word tokens only, isolate bidi per line, internal pause marks'
        Labels = @('type:fix', 'area:reader')
        BlockedBy = @()
        Body = @'
## Scope

Three rendering correctness items that share the same cause: the reader treats every token as a word.

## Items

- [ ] **Highlight only word tokens.** Segment highlighting must key off the Arabic-letter rule, never
      ornament/pause tokens. Verify with an ayah whose `word_end` currently points at an ornament
      (see #1) - the ornament must not be tinted.
- [ ] **Per-line `unicode-bidi: isolate`.** An LTR container holding RTL runs currently risks
      mis-ordering the ayah marker relative to the script. Apply isolation per rendered line.
- [ ] **Internal pause marks render as-is.** Words carrying a pause mark inside the token (for example
      the Al-Fatiha 1:7 word ending in U+06D9 U+06EC U+06E6) must render inline, not split the word or
      break the line box.
- [ ] Layout A (interlinear) and Layout B (flowing) both checked, at the same surah/ayah.

## Evidence

Screenshots of the affected ayahs before/after, in both layouts, plus the surah/ayah used.
'@
    },
    [ordered]@{
        Key   = 'reader-pagination'
        Title = 'Reader: mushaf pagination, surah navigation, zoom'
        Labels = @('type:feat', 'area:reader')
        BlockedBy = @('reader-render')
        Body = @'
## Goal

Make Layout A (interlinear) usable as a reading experience rather than a scroll dump.

## Items

- [ ] Paginate Layout A into mushaf-like pages (currently one long scroll per surah; Surah 2 is 286
      ayahs).
- [ ] Surah navigation: jump-to-surah with names, plus prev/next surah. `GET /surahs` already supplies
      `name_arabic`, `name_english`, `ayah_count`.
- [ ] Reading-order navigation across page boundaries; keep the current page in the URL so links are
      shareable (the editor already mirrors `translation_id`/`surah`/`ayah` this way).
- [ ] Zoom / font-size control that persists across navigation (a `data-zoom` cookie pattern, as used
      by deen.pk, is a reasonable model).
- [ ] Line spacing and the "empty remainder of the line stays empty" rule from ReadMe §4 preserved.

## Depends on

#5 - pagination amplifies any token-classification bug, so fix rendering first.
'@
    },
    [ordered]@{
        Key   = 'originals'
        Title = 'translation_originals: document and automate the snapshot for new translations'
        Labels = @('type:docs', 'area:db')
        BlockedBy = @()
        Body = @'
## Context

`translation_originals` (created by `data/002_translation_originals.sql`) holds an immutable copy of each
ayah's whole-ayah translation, independent of how `translation_segments` is later split. It currently has
6,236 rows for `translation_id = 2` and none for `translation_id = 1`.

The migration's copy uses `HAVING COUNT(*) = 1` as its guard: it snapshots only ayahs that still have
exactly one segment. That is correct, but it is a **one-shot SQL file with no instructions**, so the
next person to add a translation can easily segment it first and lose the pristine text forever.

## Acceptance criteria

- [ ] The snapshot step is scripted or templated so it can be run for a new `translation_id` in one
      command, with the single-segment guard and a clear failure if the guard is violated.
- [ ] Documented in `ReadMe.md` (data model section) **and** `segmentation/README.md` (the "segmenting a
      different translation later" section), stating that snapshotting happens **before** segmenting.
- [ ] Running it twice is a no-op (idempotent), and reports how many rows were written vs skipped.
- [ ] #3 references this as its prerequisite.

## Why it is docs-first

The failure mode is procedural, not technical: an agent or human segments a translation and the original
whole-ayah text becomes unrecoverable. A written rule plus a safe command prevents that.
'@
    },
    [ordered]@{
        Key   = 'tests'
        Title = 'API/integration tests, import idempotency, seed-count verification'
        Labels = @('type:test', 'area:api')
        BlockedBy = @('post-segments')
        Body = @'
## Gap

Unit tests exist for **editor logic only** (`npm test` -> `tests/editor-logic.test.js`, 30 tests, sharing
the pure module `app/static/editor-logic.js`). The API itself is untested, so endpoint regressions are
only caught by hand.

## Acceptance criteria

- [ ] Endpoint tests for `GET /surahs`, `GET /surah/{id}`, `GET /original/...`, `GET /segments/...` and
      `POST /segments` (valid + each invalid shape from #4).
- [ ] A seed-count verification test asserting the documented invariants: 114 surahs, 6,236 ayahs,
      83,668 `ayah_words`, 6,236 segments for `translation_id = 2`, 6,236 `translation_originals`.
- [ ] Import idempotency: re-running `data/import-quran-aya-words.py` does not duplicate or renumber rows.
- [ ] An outline of how tests are run locally, added to `HowToRun.md` (this repo has no CI yet).
- [ ] Tests skip cleanly (not fail) when no database is reachable, so they are safe to run anywhere.

## Notes

`GET /surah/{id}` is the contract the renderers depend on; pin its response shape (`words[]` with
`id`/`word_index`/`text`/`is_word`, `segments[]` with `word_start_index`/`word_end_index`) so a refactor
that breaks the UI fails here first.
'@
    }
)

Write-Step "Issues ($($Issues.Count))"

if ($Plan) {
    foreach ($i in $Issues) {
        $deps = if ($i.BlockedBy.Count) { " (blocked by: $($i.BlockedBy -join ', '))" } else { '' }
        Write-Do "issue '$($i.Title)' [$($i.Labels -join ', ')]$deps"
    }
    Write-Host ""
    Write-Host "Dry run complete. Re-run without -Plan to apply." -ForegroundColor Cyan
    return
}

$numberByKey = @{}
foreach ($i in $Issues) {
    $json = Invoke-Gh issue create `
        --repo $Repo `
        --title $i.Title `
        --body $i.Body `
        --label ($i.Labels -join ',') `
        --milestone $Milestone `
        --format json | ConvertFrom-Json

    $numberByKey[$i.Key] = [int]$json.number
    Write-Ok "#$($json.number)  $($i.Title)"
}

Write-Step 'Dependencies (blocked by)'
foreach ($i in $Issues) {
    if (-not $i.BlockedBy.Count) { continue }
    $n    = $numberByKey[$i.Key]
    $deps = $i.BlockedBy | ForEach-Object { $numberByKey[$_] }
    Invoke-Gh issue edit $n --repo $Repo --add-blocked-by ($deps -join ',') | Out-Null
    Write-Ok "#$n blocked by $($deps -join ', ')"
}

# ---------------------------------------------------------------------------
# Project (v2)
# NOTE: Projects v2 are owned by a user or organisation, never by a repository.
# To make it behave like a "repo project" we create it under $Owner and then
# LINK it to the repository, which is what the GitHub UI does when you create a
# project from the repo's Projects tab.
# ---------------------------------------------------------------------------
Write-Step "Project '$ProjectTitle' (owner: $Owner)"
$projList = @(Invoke-Gh project list --owner $Owner --limit 100 --format json | ConvertFrom-Json)
$proj     = $projList | Where-Object { $_.title -eq $ProjectTitle } | Select-Object -First 1

if ($proj) {
    $projNumber = [int]$proj.number
    Write-Ok "reusing project #$projNumber"
} else {
    $created    = Invoke-Gh project create --owner $Owner --title $ProjectTitle --format json | ConvertFrom-Json
    $projNumber = [int]$created.number
    Write-Ok "created project #$projNumber"
}

Invoke-Gh project link $projNumber --owner $Owner --repo $Repo | Out-Null
Write-Ok "linked to $Repo (shows on the repo's Projects tab)"

Write-Step 'Adding issues to the board'
foreach ($key in $numberByKey.Keys) {
    $n = $numberByKey[$key]
    Invoke-Gh project item-add $projNumber --owner $Owner --url "https://github.com/$Repo/issues/$n" | Out-Null
}
Write-Ok "$($numberByKey.Count) items added"

# Best-effort: set Status -> Todo (new items otherwise land in 'No Status')
try {
    $fields = @(Invoke-Gh project field-list $projNumber --owner $Owner --format json | ConvertFrom-Json).fields
    $status = $fields | Where-Object { $_.name -eq 'Status' } | Select-Object -First 1
    $todo   = $status.options | Where-Object { $_.name -eq 'Todo' } | Select-Object -First 1
    if ($status -and $todo) {
        $items = @(Invoke-Gh project item-list $projNumber --owner $Owner --limit 200 --format json | ConvertFrom-Json).items
        foreach ($it in $items) {
            Invoke-Gh project item-edit --id $it.id --project-id $status.id `
                --field-id $status.id --single-select-option-id $todo.id | Out-Null
        }
        Write-Ok 'Status set to Todo'
    }
} catch {
    Write-Host "   (skipped Status assignment: $($_.Exception.Message))" -ForegroundColor Yellow
}

# ---------------------------------------------------------------------------
# Artefacts
# ---------------------------------------------------------------------------
Write-Step 'Writing issue map'
$mapPath = Join-Path $PSScriptRoot '.issue-map.json'
$numberByKey | ConvertTo-Json | Set-Content -Path $mapPath -Encoding utf8
Write-Ok $mapPath

if ($PushDevelop) {
    Write-Step 'Pushing develop'
    & git -C (Resolve-Path (Join-Path $PSScriptRoot '..')) push -u origin develop
    if ($LASTEXITCODE -ne 0) { throw 'git push failed' }
    Write-Ok 'develop pushed'
}

Write-Host "`nDone." -ForegroundColor Cyan
Write-Host "Board:  https://github.com/$Repo/projects/$projNumber" -ForegroundColor Cyan
Write-Host "Next:   rewrite TODO.md to reference the new issue numbers (scripts/.issue-map.json)." -ForegroundColor Cyan
