# Bayaan — How to run (local dev)

Quick reference for starting the FastAPI server and opening the UI on **Windows / PowerShell**.
For what the project *is*, see `ReadMe.md` (handoff doc). For deferred work, see `TODO.md`.

---

## TL;DR

```powershell
cd d:\Personal_repos\bayaan
C:/Python314/python.exe -m uvicorn app.app:app --host 127.0.0.1 --port 8000
```

Leave that terminal open. Then browse to <http://127.0.0.1:8000/>.
Stop the server with `Ctrl+C` in that terminal.

---

## Before you start: two things must be true

### 1. MySQL is running

The app reads `app/.env` (falling back to the defaults in `app/config.py`):

```
DB_HOST=127.0.0.1
DB_PORT=3212
DB_USER=root
DB_PASSWORD=root
DB_NAME=bayaan
```

Verify from the repo root:

```powershell
C:/Python314/python.exe -c "import mysql.connector; c=mysql.connector.connect(host='127.0.0.1',port=3212,user='root',password='root',database='bayaan'); cur=c.cursor(); cur.execute('SELECT COUNT(*) FROM ayah_words'); print('DB OK, ayah_words =', cur.fetchone()[0]); cur.close(); c.close()"
```

Expected: `DB OK, ayah_words = 83668`.

This is the step that silently breaks after a reboot — the DB is a separate service, not started by the app.

To point at a different DB, copy `app/.env.example` to `app/.env` and edit it. Don't commit real credentials.

### 2. The Python interpreter has the packages

Required: `fastapi`, `uvicorn`, `mysql-connector-python`, `python-dotenv`, `pydantic`.

```powershell
C:/Python314/python.exe -c "import importlib.util as u; [print(m, 'OK' if u.find_spec(m) else 'MISSING') for m in ['fastapi','uvicorn','mysql.connector','dotenv','pydantic']]"
```

If anything is `MISSING`:

```powershell
C:/Python314/python.exe -m pip install fastapi uvicorn mysql-connector-python python-dotenv pydantic
```

> **Interpreter trap.** `python` on your PATH may not be the interpreter that holds the packages. This machine's working interpreter is `C:\Python314\python.exe`. When in doubt, use the full path as shown above.

---

## Run the server

**You must be in the repo root** (`d:\Personal_repos\bayaan`) — the module path `app.app:app` does not resolve from anywhere else.

```powershell
cd d:\Personal_repos\bayaan
C:/Python314/python.exe -m uvicorn app.app:app --host 127.0.0.1 --port 8000
```

Success looks like:

```
INFO:     Started server process [17800]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

### Useful variations

| Goal | Command |
|---|---|
| Auto-restart when `app.py` changes | add `--reload` |
| Port 8000 is busy | `--port 8001` (then change the URL too) |
| Reachable from another device on your LAN | `--host 0.0.0.0` |
| Start detached, keep the terminal free | `Start-Process -NoNewWindow C:/Python314/python.exe -ArgumentList "-m","uvicorn","app.app:app","--host","127.0.0.1","--port","8000"` |

---

## Open the UI

There is **no build step** — no `npm install`, no bundler. The pages are plain HTML/JS served from `app/static/`.

| Page | URL |
|---|---|
| Index (links to everything) | <http://127.0.0.1:8000/> |
| **Segment editor** | <http://127.0.0.1:8000/editor?translation_id=2&surah=1&ayah=1> |
| Reader — interlinear (Layout A) | <http://127.0.0.1:8000/reader?translation_id=2&surah=1> |
| Reader — mushaf / flowing (Layout B) | <http://127.0.0.1:8000/reader-mushaf?translation_id=2&surah=1> |
| Swagger API docs | <http://127.0.0.1:8000/docs> |
| ReDoc API docs | <http://127.0.0.1:8000/redoc> |
| Raw surah data | <http://127.0.0.1:8000/surah/1?translation_id=2> |

`translation_id`: `1` = bayan-ul-quran (no segments loaded yet), `2` = fateh-muhammad-jalandhry (loaded).
`surah` = 1–114. The editor also accepts `ayah` and mirrors all three in the URL, so links are shareable.

---

## Stop the server

`Ctrl+C` in the terminal running uvicorn.

If you lost track of the terminal:

```powershell
# who owns port 8000
Get-NetTCPConnection -LocalPort 8000 -State Listen | Select-Object OwningProcess

# stop it
Stop-Process -Id <PID>
```

To check whether it is up and answering:

```powershell
Invoke-WebRequest -Uri "http://127.0.0.1:8000/surahs" -UseBasicParsing | Select-Object StatusCode
```

---

## Tests

Segmentation logic only — **no DB and no server needed**.

```powershell
npm test
```

Runs `node --test tests/editor-logic.test.js` against the pure, DOM-free module `app/static/editor-logic.js` (the single source of truth shared by the editor page and the tests). Add a test there whenever the editor logic changes.

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `ModuleNotFoundError: No module named 'app'` | Wrong working directory. `cd d:\Personal_repos\bayaan` first. |
| `ModuleNotFoundError: No module named 'fastapi'` | Packages missing or wrong interpreter. See [step 2](#2-the-python-interpreter-has-the-packages). |
| `[Errno 10048] address already in use` | Something already owns port 8000. Stop that PID, or use `--port 8001`. |
| Page returns 500, or the reader/editor hangs on `Loading…` | DB unreachable or empty. Run the DB check in [step 1](#1-mysql-is-running) and read the uvicorn terminal for the traceback. |
| `404 … not built` at `/reader`, `/reader-mushaf`, or `/editor` | The matching file is missing from `app/static/`. |
| Arabic shows as boxes/tofu | The Quran Foundation IndoPak font failed to load from its CDN. The ayah-end ornaments are Private-Use glyphs that only that font renders. |
| A page looks blank on first paint | The reader pages fetch asynchronously — the content appears a moment later. Reload if it never does, and check the browser console (F12). |

---

## Mental model (why it's this simple)

- `app/app.py` — FastAPI app: JSON endpoints (`/surahs`, `/surah/{id}`, `/original/...`, `/segments`) **plus** it mounts `app/static/` and serves the HTML pages at `/`, `/editor`, `/reader`, `/reader-mushaf`.
- `app/static/*.html` — the UI. Vanilla HTML/JS, no framework, no compilation. Edit the file, then reload the browser (no server restart needed for HTML/JS changes; `--reload` is only for `app.py`).
- `app/static/editor-logic.js` — pure segmentation math, shared with `npm test`.
- `app/config.py` + `app/.env` — DB and server settings.
