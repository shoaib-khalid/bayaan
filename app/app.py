import re
from contextlib import asynccontextmanager
from pathlib import Path
from string import Template
from urllib.parse import parse_qs, quote, urlencode

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import mysql.connector
from starlette.concurrency import run_in_threadpool

from . import admin, auth, positions, segments
from .config import DATABASE_CONFIG, API_TITLE, API_DESCRIPTION, API_VERSION

# Real Arabic words contain letters or a known complete-word font ligature.
# The end-of-ayah ornament tokens (e.g. "۟ۙ\uf500") carry NO Arabic letter —
# they are Private-Use glyphs the Quran Foundation IndoPak font turns into the
# numbered ayah-end ornament. Treating them as ornaments (not words) lets a
# renderer show the ayah marker once, at the ayah end, instead of inside a
# word range. (Note: the DB `is_symbol` column was filled with a crude
# len()<=2 heuristic, so we re-derive it here. See TODO.md.)
_ARABIC_LETTER = re.compile(r"[\u0621-\u064a\u0671-\u06d3]")

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """First start only: create an administrator from ADMIN_USERNAME/PASSWORD.

    On an empty `users` table with neither variable set, the app starts with no
    accounts at all — nobody can sign in, and `scripts/manage_users.py create`
    is the way in. That is deliberate: no default password ever exists.
    """
    try:
        seeded = auth.ensure_first_admin()
        if seeded:
            print(f"[auth] created the first administrator '{seeded}' from .env")
    except Exception as exc:  # a DB hiccup must not stop the app from starting
        print(f"[auth] could not seed the first administrator: {exc}")
    yield


app = FastAPI(
    title=API_TITLE,
    description=API_DESCRIPTION,
    version=API_VERSION,
    lifespan=lifespan,
)

# -------------------------
# Database Connection
# -------------------------

def get_db():
    return mysql.connector.connect(**DATABASE_CONFIG)

# -------------------------
# Models
# -------------------------

class Segment(BaseModel):
    start: int = Field(..., description="Starting word index (inclusive)", example=1)
    end: int = Field(..., description="Ending word index (inclusive)", example=10)
    text: str = Field(..., description="Translation text for this segment")

class SegmentRequest(BaseModel):
    translation_id: int = Field(..., example=1)
    surah_id: int = Field(..., example=2)
    ayah_number: int = Field(..., example=177)
    segments: list[Segment]

# -------------------------
# Get Ayah Words
# -------------------------

@app.get(
    "/ayah/{surah_id}/{ayah_number}",
    summary="Get Ayah Words",
    description="Fetch all Arabic words for a given Surah and Ayah"
)
def get_ayah(surah_id: int, ayah_number: int):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT word_index, text
        FROM ayah_words
        WHERE surah_id=%s AND ayah_number=%s
        ORDER BY word_index
    """, (surah_id, ayah_number))

    words = cursor.fetchall()

    cursor.close()
    conn.close()

    return {
        "surah": surah_id,
        "ayah": ayah_number,
        "words": words
    }

# -------------------------
# Get Segments
# -------------------------

@app.get(
    "/segments/{translation_id}/{surah_id}/{ayah_number}",
    summary="Get Translation Segments",
    description="Retrieve segmented translation for a specific ayah"
)
def get_segments(translation_id: int, surah_id: int, ayah_number: int, request: Request):
    """Segments of one ayah — the caller's own copy if they have one."""
    user = getattr(request.state, "user", None)
    return segments.for_ayah(
        surah_id, ayah_number, translation_id, user["id"] if user else None
    )

# -------------------------
# Create / Update Segments
# -------------------------

@app.post(
    "/segments",
    summary="Create or Update Segments",
    description="Replaces all segments for a given ayah and translation"
)
def create_segments(data: SegmentRequest, request: Request):
    """Replace all segments of one ayah.

    An admin edits the canonical text. Everyone else writes their own private
    copy, so two people can segment the same ayah without overwriting each
    other; an admin can then promote a private copy into the canonical text
    from /admin/promotions.
    """
    user = getattr(request.state, "user", None)
    target_user = user["id"] if user and user["role"] != "admin" else None

    try:
        segments.replace_ayah(
            [seg.model_dump() for seg in data.segments],
            data.translation_id,
            data.surah_id,
            data.ayah_number,
            user_id=target_user,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {
        "status": "success",
        # Told plainly, so a caller can say where the edit landed.
        "saved_to": "user" if target_user else "canonical",
    }

# ---------------------------------------------------------------------------
# Rendering API (minimal, word-based)
# ---------------------------------------------------------------------------

STATIC_DIR = Path(__file__).resolve().parent / "static"


def _is_word(text: str) -> bool:
    """Recognize Arabic letters and complete-word font ligatures, excluding
    end-of-ayah ornaments and pause-mark tokens."""
    # The IndoPak font encodes these complete Quran words as ligatures:
    # U+F658 = wa-l-yatalattaf (18:19), U+F666 = thuluthayi (73:20).
    # Other private-use glyphs include verse ornaments and remain excluded.
    value = text or ""
    return bool(_ARABIC_LETTER.search(value)) or any(
        glyph in value for glyph in ("\uf658", "\uf666")
    )


@app.get(
    "/surah/{surah_id}",
    summary="Get a whole surah for rendering",
    description=(
        "Returns, for one surah + translation: every ayah's word tokens "
        "(with a reliable is_word/ornament flag) and its translation segments "
        "(word_start/word_end as ayah_words ids plus their word_index bounds). "
        "This is everything a renderer needs to draw the interlinear or "
        "flowing+highlight layouts."
    ),
)
def get_surah_render(
    surah_id: int,
    request: Request,
    translation_id: int = Query(default=2, description="translations.id (1=bayan-ul-quran, 2=fateh-muhammad-jalandhry)"),
):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT id, name_arabic, name_english FROM surahs WHERE id=%s",
            (surah_id,),
        )
        surah = cursor.fetchone()
        if not surah:
            raise HTTPException(status_code=404, detail="surah not found")

        cursor.execute(
            "SELECT id, name, language, direction FROM translations WHERE id=%s",
            (translation_id,),
        )
        translation = cursor.fetchone()
        if not translation:
            raise HTTPException(status_code=404, detail="translation not found")

        cursor.execute(
            "SELECT id, ayah_number, word_index, text FROM ayah_words "
            "WHERE surah_id=%s ORDER BY ayah_number, word_index",
            (surah_id,),
        )
        word_rows = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    # The caller's own copy of an ayah wins over the canonical one, ayah by
    # ayah (see app/segments.py). Read outside the cursor block above so a
    # user with no rows costs nothing extra here.
    reader = getattr(request.state, "user", None)
    seg_rows = segments.for_surah(
        surah_id, translation_id, reader["id"] if reader else None
    )

    words_by_ayah: dict[int, list[dict]] = {}
    for r in word_rows:
        words_by_ayah.setdefault(r["ayah_number"], []).append(r)

    ayahs = []
    for ayah_number in sorted(words_by_ayah):
        words = words_by_ayah[ayah_number]
        id_to_wi = {w["id"]: w["word_index"] for w in words}
        words_out = [
            {
                "id": w["id"],
                "word_index": w["word_index"],
                "text": w["text"],
                "is_word": _is_word(w["text"]),
            }
            for w in words
        ]
        # Named `ayah_segments`: `segments` is the module imported above, and a
        # local of that name would shadow it for the whole function.
        ayah_segments = []
        for s in (x for x in seg_rows if x["ayah_number"] == ayah_number):
            ayah_segments.append(
                {
                    "segment_index": s["segment_index"],
                    "word_start": s["word_start"],
                    "word_end": s["word_end"],
                    "word_start_index": id_to_wi.get(s["word_start"]),
                    "word_end_index": id_to_wi.get(s["word_end"]),
                    "translation_text": s["translation_text"],
                    # "user" means this ayah is the caller's own copy.
                    "source": s.get("source", "canonical"),
                }
            )
        ayahs.append(
            {"ayah_number": ayah_number, "words": words_out, "segments": ayah_segments}
        )

    return {
        "surah": surah,
        "translation": translation,
        "ayah_count": len(ayahs),
        "ayahs": ayahs,
    }


@app.get(
    "/surahs",
    summary="List surahs (with names and ayah counts)",
    description="Used by the editor/reader to build a named surah dropdown.",
)
def list_surahs():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT s.id, s.name_arabic, s.name_english, COUNT(a.ayah_number) AS ayah_count "
            "FROM surahs s LEFT JOIN ayahs a ON a.surah_id = s.id "
            "GROUP BY s.id, s.name_arabic, s.name_english ORDER BY s.id"
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


@app.get(
    "/translations",
    summary="List translations (id, name, language, direction)",
    description="Used by the reader/editor to build the translation dropdown.",
)
def list_translations():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT id, name, language, direction FROM translations ORDER BY id"
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


@app.get(
    "/original/{translation_id}/{surah_id}/{ayah_number}",
    summary="Get the original whole-ayah translation (read-only reference)",
    description=(
        "Returns the pristine, pre-editing translation of one ayah from "
        "translation_originals. This is the immutable whole-ayah text the "
        "editor shows under 'Show original' — independent of however the ayah "
        "may later be segmented in translation_segments."
    ),
)
def get_original_translation(translation_id: int, surah_id: int, ayah_number: int):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT translation_text FROM translation_originals "
            "WHERE translation_id=%s AND surah_id=%s AND ayah_number=%s",
            (translation_id, surah_id, ayah_number),
        )
        row = cursor.fetchone()
    finally:
        cursor.close()
        conn.close()
    if not row:
        raise HTTPException(
            status_code=404,
            detail="No original whole-ayah translation stored for this (translation, surah, ayah).",
        )
    return {"translation_text": row["translation_text"]}


# ---------------------------------------------------------------------------
# Minimal static reader (see app/static/reader.html)
# ---------------------------------------------------------------------------
if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _resume_or_remember(request: Request, context: str) -> RedirectResponse | None:
    """Resume a bare URL where this user left off, or record this one.

    A URL carrying parameters is an explicit request — a shared link, a
    bookmark, a deliberate jump — so it always wins over the stored position and
    becomes the new one. Only a bare page URL resumes, which is what makes
    `/editor` with nothing attached reopen the last ayah that person edited.
    """
    user = getattr(request.state, "user", None)
    if not user:
        return None

    query = request.url.query
    if not query:
        saved = positions.get(user["id"], context)
        if saved and saved["location"]:
            return RedirectResponse(
                request.url.path + saved["location"], status_code=302
            )
        return None

    raw = (parse_qs(query).get("translation_id") or ["2"])[0]
    try:
        translation_id = int(raw)
    except ValueError:
        translation_id = 2
    positions.save(user["id"], context, translation_id, "?" + query)
    return None


@app.get("/reader", response_class=HTMLResponse, include_in_schema=False)
def reader_page(request: Request):
    jump = _resume_or_remember(request, "reader")
    if jump:
        return jump
    index = STATIC_DIR / "reader.html"
    if not index.is_file():
        raise HTTPException(status_code=404, detail="reader.html not built")
    return FileResponse(index, headers={"Cache-Control": "no-cache"})


@app.get("/mushaf", response_class=HTMLResponse, include_in_schema=False)
def mushaf_page(request: Request):
    """Flowing, print-ready reader backed by the saved Quran segments."""
    jump = _resume_or_remember(request, "mushaf")
    if jump:
        return jump
    page = STATIC_DIR / "mushaf.html"
    if not page.is_file():
        raise HTTPException(status_code=404, detail="mushaf.html not built")
    return FileResponse(page, headers={"Cache-Control": "no-cache"})


@app.get("/reader-mushaf", response_class=HTMLResponse, include_in_schema=False)
def reader_mushaf_page(request: Request):
    jump = _resume_or_remember(request, "reader-mushaf")
    if jump:
        return jump
    index = STATIC_DIR / "reader-mushaf.html"
    if not index.is_file():
        raise HTTPException(status_code=404, detail="reader-mushaf.html not built")
    return FileResponse(index)


@app.get("/editor", response_class=HTMLResponse, include_in_schema=False)
def editor_page(request: Request):
    jump = _resume_or_remember(request, "editor")
    if jump:
        return jump
    index = STATIC_DIR / "editor.html"
    if not index.is_file():
        raise HTTPException(status_code=404, detail="editor.html not built")
    return FileResponse(index)


@app.get("/editor/release-notes", response_class=HTMLResponse, include_in_schema=False)
def editor_release_notes_page():
    page = STATIC_DIR / "editor-release-notes.html"
    if not page.is_file():
        raise HTTPException(status_code=404, detail="editor-release-notes.html not built")
    return FileResponse(page)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def index_page():
    index = STATIC_DIR / "index.html"
    if not index.is_file():
        raise HTTPException(status_code=404, detail="index.html not built")
    return FileResponse(index)


# ---------------------------------------------------------------------------
# Access control
#
# The rules are rows, not code: `permission_paths` says which capability a URL
# needs and `role_permissions` says which role holds it. Both are read per
# request, so a grant or revocation applies to the next request with no restart
# (see app/auth.py and data/003_auth_rbac.sql).
#
# A path with no row is not protected, so every page and endpoint here must have
# one. `python scripts/manage_users.py permissions` lists the covered paths.
# ---------------------------------------------------------------------------

_FORBIDDEN_PAGE = Template("""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Not permitted — Bayaan</title>
<style>
  :root { color-scheme: dark; }
  body { margin:0; min-height:100vh; display:flex; align-items:center; justify-content:center;
         background:#12100e; color:#f2ece3; font:16px/1.6 system-ui, sans-serif; padding:24px; }
  .card { max-width:540px; padding:32px 36px; border:1px solid #3a332a; border-radius:10px; background:#191612; }
  h1 { margin:0 0 10px; font-size:20px; letter-spacing:.02em; }
  code { background:#241f18; padding:1px 5px; border-radius:4px; font-size:14px; }
  a { color:#c8a96a; }
  p { margin:0 0 14px; }
  .who { color:#c8a96a; }
  .muted { color:#a89b88; font-size:14px; }
</style>
</head>
<body>
  <div class="card">
    <h1>Not permitted</h1>
    <p class="who">Signed in as $who ($role).</p>
    <p>This page needs the <code>$permission</code> permission, which your role does not have.</p>
    <p class="muted">Ask an administrator to grant it, or <a href="/logout">sign out</a>.</p>
    <p class="muted">Access rules live in the database, so a grant applies on your next request.</p>
  </div>
</body>
</html>
""")


def _forbidden_page(user: dict, permission: str) -> HTMLResponse:
    return HTMLResponse(
        _FORBIDDEN_PAGE.substitute(
            who=user.get("display_name") or user["username"],
            role=user["role"],
            permission=permission,
        ),
        status_code=403,
    )


def _redirect_target(request: Request) -> str:
    """The path (with query) to come back to after signing in."""
    return request.url.path + (("?" + request.url.query) if request.url.query else "")


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _wants_html(request: Request) -> bool:
    """Is this a browser following a page, or a client calling the API?

    The method alone cannot tell them apart: a page and a JSON endpoint are both
    a GET. The Accept header can — a browser navigating asks for `text/html`,
    and a `fetch()` from a page or a script sends `*/*`, which must get a status
    it can handle instead of a login page it cannot parse.
    """
    return "text/html" in request.headers.get("accept", "").lower()


@app.middleware("http")
async def require_permission(request: Request, call_next):
    """Reject a request whose URL needs a capability the caller lacks.

    The two database reads happen in a worker thread: the connection and the
    cursor are blocking, and running them on the event loop would stall every
    other in-flight request for the duration.
    """
    rule = await run_in_threadpool(
        auth.resolve_rule, request.url.path, request.method
    )
    if rule is None or rule["is_public"]:
        return await call_next(request)

    user = await run_in_threadpool(
        auth.get_session, request.cookies.get(auth.SESSION_COOKIE)
    )
    if user is None:
        # A page gets sent to sign in and comes back; an API call gets a status
        # it can actually act on, rather than a page of HTML.
        if request.method in auth.NAVIGATION_METHODS and _wants_html(request):
            return RedirectResponse(
                "/login?next=" + quote(_redirect_target(request), safe=""),
                status_code=303,
            )
        return JSONResponse({"detail": "Sign in required."}, status_code=401)

    held = await run_in_threadpool(auth.role_permissions, user["role_id"])
    if rule["perm_key"] not in held:
        if request.method in auth.NAVIGATION_METHODS and _wants_html(request):
            return _forbidden_page(user, rule["perm_key"])
        return JSONResponse(
            {"detail": f"Not permitted: {rule['perm_key']}."}, status_code=403
        )

    request.state.user = user
    return await call_next(request)


@app.get("/login", response_class=HTMLResponse, include_in_schema=False)
def login_page(request: Request, next: str = "/"):
    """The sign-in form. Already signed in means no reason to show it."""
    if auth.get_session(request.cookies.get(auth.SESSION_COOKIE)):
        return RedirectResponse(auth.safe_next(next), status_code=303)
    page = STATIC_DIR / "login.html"
    if not page.is_file():
        raise HTTPException(status_code=404, detail="login.html not built")
    return FileResponse(page, headers={"Cache-Control": "no-cache"})


@app.post("/login", include_in_schema=False)
async def login_submit(request: Request):
    """Verify the form and start a session.

    The body is parsed here rather than declared with `Form(...)`, which would
    drag in python-multipart for one form. The page posts urlencoded, so
    parse_qs is enough and the app keeps its current dependency list.
    """
    form = parse_qs((await request.body()).decode("utf-8"))
    username = form.get("username", [""])[0].strip()
    password = form.get("password", [""])[0]
    remember = bool(form.get("remember", [""])[0])
    next_path = auth.safe_next(form.get("next", ["/"])[0])

    user = await run_in_threadpool(auth.authenticate, username, password)
    if not user:
        # One message for every failure: an unknown user, a wrong password and
        # a disabled account must be indistinguishable from outside.
        query = urlencode({"error": "1", "next": next_path, "username": username})
        return RedirectResponse("/login?" + query, status_code=303)

    token = await run_in_threadpool(
        auth.create_session,
        user["id"],
        remember,
        _client_ip(request),
        request.headers.get("user-agent"),
    )
    response = RedirectResponse(next_path, status_code=303)
    response.set_cookie(
        auth.SESSION_COOKIE,
        token,
        # A remembered session survives a browser restart; otherwise the cookie
        # is dropped when the browser closes and the row expires on its own.
        max_age=auth.REMEMBER_SECONDS if remember else None,
        httponly=True,
        samesite="lax",
        # Set True once this is served over HTTPS.
        secure=False,
        path="/",
    )
    return response


@app.get("/logout", include_in_schema=False)
@app.post("/logout", include_in_schema=False)
def logout(request: Request):
    auth.delete_session(request.cookies.get(auth.SESSION_COOKIE))
    response = RedirectResponse("/login?signed_out=1", status_code=303)
    response.delete_cookie(auth.SESSION_COOKIE, path="/")
    return response


@app.get("/me/password", response_class=HTMLResponse, include_in_schema=False)
def me_password_page():
    page = STATIC_DIR / "me-password.html"
    if not page.is_file():
        raise HTTPException(status_code=404, detail="me-password.html not built")
    return FileResponse(page, headers={"Cache-Control": "no-cache"})


@app.post("/me/password", include_in_schema=False)
async def me_password_submit(request: Request):
    """Change the signed-in user's own password.

    The current password is required as well: a borrowed session should not be
    enough to lock the real owner out of their own account.
    """
    token = request.cookies.get(auth.SESSION_COOKIE)
    user = await run_in_threadpool(auth.get_session, token)
    if not user:
        return RedirectResponse("/login?next=%2Fme%2Fpassword", status_code=303)

    form = parse_qs((await request.body()).decode("utf-8"))
    current = form.get("current", [""])[0]
    new = form.get("new", [""])[0]
    confirm = form.get("confirm", [""])[0]

    def back_with(error: str) -> RedirectResponse:
        return RedirectResponse("/me/password?" + urlencode({"error": error}), status_code=303)

    stored = await run_in_threadpool(auth.get_user_by_username, user["username"])
    if not stored or not auth.verify_password(current, stored["password_hash"]):
        return back_with("current")
    if len(new) < auth.MIN_PASSWORD_LENGTH:
        return back_with("short")
    if new != confirm:
        return back_with("mismatch")

    await run_in_threadpool(auth.set_password, user["id"], new)
    # Every other session was opened with the old password, so end them all -
    # then issue a fresh one here so this browser is not thrown out with them.
    await run_in_threadpool(auth.delete_user_sessions, user["id"])
    fresh = await run_in_threadpool(
        auth.create_session,
        user["id"],
        # Keep the session type the person originally chose.
        bool(user.get("remember_me")),
        _client_ip(request),
        request.headers.get("user-agent"),
    )
    response = RedirectResponse("/me/password?changed=1", status_code=303)
    response.set_cookie(
        auth.SESSION_COOKIE,
        fresh,
        httponly=True,
        samesite="lax",
        secure=False,
        path="/",
    )
    return response


@app.get("/api/me", include_in_schema=False)
def api_me(request: Request):
    """Who is signed in, for the sign-out strip on every page.

    Public on purpose: with no valid cookie it answers `{"user": null}` and
    nothing else, so it is safe to call from the sign-in page too.
    """
    user = auth.get_session(request.cookies.get(auth.SESSION_COOKIE))
    if not user:
        return {"user": None}
    return {
        "user": {
            "username": user["username"],
            "display_name": user.get("display_name"),
            "role": user["role"],
        }
    }


# ---------------------------------------------------------------------------
# User administration (/admin/users — requires page.admin)
#
# Every action is a form POST that redirects back to the page with a code, so a
# refresh cannot resend it and the URL never carries a message the page would
# have to trust.
# ---------------------------------------------------------------------------

def _admin_back(query: str) -> RedirectResponse:
    return RedirectResponse("/admin/users?" + query, status_code=303)


async def _admin_form(request: Request) -> dict[str, str]:
    form = parse_qs((await request.body()).decode("utf-8"))
    return {key: (values[0] if values else "") for key, values in form.items()}


@app.get("/admin/users", response_class=HTMLResponse, include_in_schema=False)
def admin_users_page(request: Request, ok: str = "", error: str = ""):
    page = admin.render_users(
        request.state.user,
        auth.list_users(),
        auth.list_roles(),
        ok or None,
        error or None,
    )
    return HTMLResponse(page, headers={"Cache-Control": "no-cache"})


@app.post("/admin/users/create", include_in_schema=False)
async def admin_users_create(request: Request):
    form = await _admin_form(request)
    username = form.get("username", "").strip()
    display_name = form.get("display_name", "").strip() or None
    role = form.get("role", "").strip() or "viewer"
    password = form.get("password", "")
    confirm = form.get("confirm", "")

    if not username or not password or not confirm:
        return _admin_back("error=missing")
    if not any(r["name"] == role for r in auth.list_roles()):
        return _admin_back("error=role")
    if password != confirm:
        return _admin_back("error=mismatch")
    if len(password) < auth.MIN_PASSWORD_LENGTH:
        return _admin_back("error=short")
    if auth.get_user_by_username(username):
        return _admin_back("error=duplicate")

    try:
        auth.create_user(username, password, role=role, display_name=display_name)
    except ValueError:
        return _admin_back("error=short")
    return _admin_back("ok=created")


@app.post("/admin/users/password", include_in_schema=False)
async def admin_users_password(request: Request):
    """Set somebody else's password. Ends the sessions they had open."""
    form = await _admin_form(request)
    target = auth.get_user(int(form.get("user_id") or 0))
    if not target:
        return _admin_back("error=user")

    password = form.get("password", "")
    confirm = form.get("confirm", "")
    if password != confirm:
        return _admin_back("error=mismatch")
    if len(password) < auth.MIN_PASSWORD_LENGTH:
        return _admin_back("error=short")

    auth.set_password(target["id"], password)
    auth.delete_user_sessions(target["id"])
    return _admin_back("ok=password")


@app.post("/admin/users/active", include_in_schema=False)
async def admin_users_active(request: Request):
    form = await _admin_form(request)
    target = auth.get_user(int(form.get("user_id") or 0))
    if not target:
        return _admin_back("error=user")

    make_active = form.get("active") == "1"
    if not make_active:
        # Locking yourself out mid-session is a support call waiting to happen;
        # and leaving no active administrator means nobody can grant anything.
        if target["id"] == request.state.user["id"]:
            return _admin_back("error=self")
        others = [
            u for u in auth.list_users()
            if u["role"] == "admin" and u["is_active"] and u["id"] != target["id"]
        ]
        if target["role"] == "admin" and not others:
            return _admin_back("error=lastadmin")

    auth.set_active(target["id"], make_active)
    return _admin_back("ok=enabled" if make_active else "ok=disabled")


# ---------------------------------------------------------------------------
# Promotion: a person's private copy -> the canonical text
# ---------------------------------------------------------------------------

@app.get("/admin/promotions", response_class=HTMLResponse, include_in_schema=False)
def admin_promotions_page(request: Request, ok: str = "", error: str = "", n: int = 0):
    page = admin.render_promotions(
        request.state.user, segments.list_overrides(), ok or None, error or None, n
    )
    return HTMLResponse(page, headers={"Cache-Control": "no-cache"})


@app.post("/admin/promote", include_in_schema=False)
async def admin_promote(request: Request):
    """Copy one ayah from someone's private segments into `translation_segments`."""
    form = await _admin_form(request)
    try:
        copied = segments.promote(
            int(form.get("user_id") or 0),
            int(form.get("translation_id") or 0),
            int(form.get("surah_id") or 0),
            int(form.get("ayah_number") or 0),
        )
    except ValueError:
        return RedirectResponse("/admin/promotions?error=promote", status_code=303)
    return RedirectResponse(f"/admin/promotions?ok=promoted&n={copied}", status_code=303)


# ---------------------------------------------------------------------------
# Reading position (self-service, see app/positions.py)
# ---------------------------------------------------------------------------

@app.post("/api/position", include_in_schema=False)
async def save_position(request: Request):
    """Record where the signed-in user is, as pages change URL client-side.

    The page routes already record a position when they are loaded with
    parameters; this is for movement inside a page (next page, next surah)
    that never reaches the server.
    """
    user = getattr(request.state, "user", None)
    if not user:
        return JSONResponse({"detail": "Sign in required."}, status_code=401)

    form = parse_qs((await request.body()).decode("utf-8"))
    context = form.get("context", [""])[0]
    try:
        translation_id = int(form.get("translation_id", ["2"])[0])
        positions.save(user["id"], context, translation_id, form.get("location", [""])[0])
    except ValueError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=400)
    return {"status": "saved"}