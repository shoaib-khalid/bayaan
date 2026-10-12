# Contributing to Bayaan

**The one rule:** every commit references the task (GitHub issue) it belongs to, and every
branch follows git-flow. Work that isn't traceable to an issue doesn't get merged.

Task board: <https://github.com/shoaib-khalid/bayaan/projects>
Issues: <https://github.com/shoaib-khalid/bayaan/issues>

Local setup (server, DB, UI): see [HowToRun.md](HowToRun.md).
Deferred work backlog: see [TODO.md](TODO.md).

---

## 1. Branch model (git-flow)

| Branch | Branches from | Merges into | Lifetime |
|---|---|---|---|
| `main` | — | — | permanent; always releasable, **the default branch** |
| `develop` | `main` | — | permanent; integration branch, always green |
| `feature/<issue>-<slug>` | `develop` | `develop` | one task |
| `release/<version>` | `develop` | `main` **and** `develop` | until release |
| `hotfix/<issue>-<slug>` | `main` | `main` **and** `develop` | until patched |

Naming:

```
feature/14-split-at-caret          # issue 14
feature/3-populate-bayan-ul-quran
release/0.2.0
hotfix/21-ornament-word-end
```

Rules:

- **Never commit directly to `main` or `develop`.** Both are protected by convention (and should
  be protected in repo settings — see §6).
- One issue per feature branch. If you find unrelated work, open an issue and a new branch.
- Sync before you start: `git checkout develop && git pull && git checkout -b feature/14-split-at-caret`.
- Back-merge `develop` into long-running feature branches regularly to avoid merge debt.

---

## 2. Commit messages

[Conventional Commits](https://www.conventionalcommits.org/), with the task reference in the
subject. Format:

```
<type>(<scope>): <subject> (#<issue>)

<body — why, not what>

Refs #<issue>
```

Types: `feat`, `fix`, `chore`, `docs`, `test`, `refactor`, `perf`, `build`, `ci`.
Scopes used in this repo: `api`, `editor`, `reader`, `db`, `data`, `segmentation`, `ui`.

Examples:

```
feat(editor): split segment at caret position (#14)
fix(api): return last real word as word_end (#21)
docs(reader): document Layout A vs Layout B (#17)
test(editor): cover merge-into-previous case (#24)
chore(db): backfill is_symbol from Arabic-letter rule (#21)
```

Keep the subject in the imperative, under ~72 chars. Explain *why* in the body, especially for
segmentation/orthography decisions — those are hard to reconstruct later.

---

## 3. How commits link to tasks

GitHub auto-links `#<n>` in commit messages and PR titles/bodies to the issue. Two keywords,
two very different behaviours:

| Keyword | Effect |
|---|---|
| `Refs #14`, `Part of #14` | links the commit/PR to the issue — **does not close it** |
| `Closes #14`, `Fixes #14` | links **and auto-closes** the issue when merged |

**git-flow gotcha:** GitHub only auto-closes on a closing keyword when the commit lands on the
repository's **default branch** (`main`). Most of your work merges into `develop`, so a
`Closes #14` in a feature PR will *not* close anything — it silently does nothing.

So:

- **Feature → `develop`:** use `Refs #14` in commits and the PR body.
- **`release/*` → `main`:** list the closing keywords for everything shipping in that release.
  This is where issues actually close:

  ```
  Release 0.2.0

  Closes #14
  Closes #21
  Closes #17
  ```

- **`hotfix/*` → `main`:** `Closes #<n>` works here, since it merges into `main` directly.
- The `develop` back-merge of a release must **not** carry the closing keywords again — rewrite
  or strip them to avoid a second close attempt and a confusing history.

Issue numbers are permanent; don't renumber. Reference the issue, not the branch name.

---

## 4. Pull requests

- Title: same Conventional Commits form as commits, e.g. `feat(editor): split at caret (#14)`.
- Body: link the issue (`Refs #14`), state what changed, and paste the **verification evidence**
  — the command you ran and its result. This repo has no CI yet, so evidence is the gate.
- Keep PRs single-task and reviewable. A 900-line PR will be sent back.
- Merge strategy:
  - feature → `develop`: **squash** (keeps `develop` readable, one commit per task)
  - `develop` → `release/*`: merge
  - `release/*`/`hotfix/*` → `main`: **merge (no fast-forward)** so the release point stays visible
- Delete the branch after merge.

Minimum evidence by change type:

| Change | Evidence required |
|---|---|
| `app/app.py`, `app/config.py` | server starts; the affected endpoint returns expected JSON |
| `app/static/*.js` logic (`editor-logic.js`) | `npm test` passes |
| `app/static/*.html` | the page loads and the flow works, with a screenshot |
| `data/*.sql`, schema, backfills | before/after counts from the verification query in the issue |
| `segmentation/specs/*.json` | `segment_ayahs.py check` passes before `commit` |
| Docs only | none beyond a read-through |

---

## 5. Releases

```bash
git checkout develop && git pull
git checkout -b release/0.2.0
#  bump versions, update ReadMe/TODO, final fixes only (no new features)
git checkout main && git merge --no-ff release/0.2.0
git tag -a v0.2.0 -m "v0.2.0"
git push origin main --follow-tags
git checkout develop && git merge --no-ff release/0.2.0
git push origin develop
git branch -d release/0.2.0
```

The PR into `main` is where `Closes #…` for the release's issues goes (see §3).

---

## 6. Task board

**Project:** repo-scoped GitHub Project (v2) on `shoaib-khalid/bayaan`, kanban layout.

| Column | Meaning |
|---|---|
| `Todo` | groomed, has acceptance criteria, not started |
| `In Progress` | a branch exists; limit to 1–2 cards per person |
| `In Review` | PR open against `develop` |
| `Done` | merged to `develop` (or closed via `main` for hotfixes) |

Workflow: pick a `Todo` card → move to `In Progress` → create `feature/<issue>-<slug>` →
commit with `Refs #<issue>` → open PR into `develop` → move to `In Review` → merge → `Done`.

Labels:

| Label | Use |
|---|---|
| `type:feat` `type:fix` `type:docs` `type:test` `type:chore` | mirrors the commit type |
| `area:api` `area:editor` `area:reader` `area:db` `area:data` `area:segmentation` | which part of the repo |
| `blocked` | has an open dependency |
| `editorial` | requires human judgement/approval, not just code that runs |

---

## 7. Repo settings worth turning on

Not enforceable from a file, so set these in **Settings**:

- **Branches → protect `main` and `develop`:** no direct pushes, no force-push, require a PR
  before merging. Optionally require one approval.
- **General → default branch stays `main`** (the `Closes` behaviour in §3 depends on it).
- **General → automatically delete head branches** after merge.
- **Issues →** enable, and add the labels in §6 before creating tasks.
