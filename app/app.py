import re
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import mysql.connector
from .config import DATABASE_CONFIG, API_TITLE, API_DESCRIPTION, API_VERSION

# A token is a real Arabic *word* only if it contains an Arabic letter.
# The end-of-ayah ornament tokens (e.g. "۟ۙ\uf500") carry NO Arabic letter —
# they are Private-Use glyphs the Quran Foundation IndoPak font turns into the
# numbered ayah-end ornament. Treating them as ornaments (not words) lets a
# renderer show the ayah marker once, at the ayah end, instead of inside a
# word range. (Note: the DB `is_symbol` column was filled with a crude
# len()<=2 heuristic, so we re-derive it here. See TODO.md.)
_ARABIC_LETTER = re.compile(r"[\u0621-\u064a\u0671-\u06d3]")

app = FastAPI(
    title=API_TITLE,
    description=API_DESCRIPTION,
    version=API_VERSION
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
def get_segments(translation_id: int, surah_id: int, ayah_number: int):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT segment_index, word_start, word_end, translation_text
        FROM translation_segments
        WHERE translation_id=%s AND surah_id=%s AND ayah_number=%s
        ORDER BY segment_index
    """, (translation_id, surah_id, ayah_number))

    segments = cursor.fetchall()

    cursor.close()
    conn.close()

    return segments

# -------------------------
# Create / Update Segments
# -------------------------

@app.post(
    "/segments",
    summary="Create or Update Segments",
    description="Replaces all segments for a given ayah and translation"
)
def create_segments(data: SegmentRequest):
    conn = get_db()
    cursor = conn.cursor()

    # Remove existing segments (overwrite strategy)
    cursor.execute("""
        DELETE FROM translation_segments
        WHERE translation_id=%s AND surah_id=%s AND ayah_number=%s
    """, (data.translation_id, data.surah_id, data.ayah_number))

    # Insert new segments
    for i, seg in enumerate(data.segments, start=1):
        if seg.start > seg.end:
            raise HTTPException(status_code=400, detail="start cannot be greater than end")

        cursor.execute("""
            INSERT INTO translation_segments (
                surah_id, ayah_number, translation_id,
                segment_index, word_start, word_end, translation_text
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            data.surah_id,
            data.ayah_number,
            data.translation_id,
            i,
            seg.start,
            seg.end,
            seg.text
        ))

    conn.commit()
    cursor.close()
    conn.close()

    return {"status": "success"}

# ---------------------------------------------------------------------------
# Rendering API (minimal, word-based)
# ---------------------------------------------------------------------------

STATIC_DIR = Path(__file__).resolve().parent / "static"


def _is_word(text: str) -> bool:
    """True when a token contains an Arabic letter (i.e. it is a real word,
    not an end-of-ayah ornament / pause-mark token)."""
    return bool(_ARABIC_LETTER.search(text or ""))


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

        cursor.execute(
            "SELECT ayah_number, segment_index, word_start, word_end, translation_text "
            "FROM translation_segments "
            "WHERE surah_id=%s AND translation_id=%s "
            "ORDER BY ayah_number, segment_index",
            (surah_id, translation_id),
        )
        seg_rows = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

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
        segments = []
        for s in (x for x in seg_rows if x["ayah_number"] == ayah_number):
            segments.append(
                {
                    "segment_index": s["segment_index"],
                    "word_start": s["word_start"],
                    "word_end": s["word_end"],
                    "word_start_index": id_to_wi.get(s["word_start"]),
                    "word_end_index": id_to_wi.get(s["word_end"]),
                    "translation_text": s["translation_text"],
                }
            )
        ayahs.append({"ayah_number": ayah_number, "words": words_out, "segments": segments})

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


# ---------------------------------------------------------------------------
# Minimal static reader (see app/static/reader.html)
# ---------------------------------------------------------------------------
if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/reader", response_class=HTMLResponse, include_in_schema=False)
def reader_page():
    index = STATIC_DIR / "reader.html"
    if not index.is_file():
        raise HTTPException(status_code=404, detail="reader.html not built")
    return FileResponse(index)


@app.get("/editor", response_class=HTMLResponse, include_in_schema=False)
def editor_page():
    index = STATIC_DIR / "editor.html"
    if not index.is_file():
        raise HTTPException(status_code=404, detail="editor.html not built")
    return FileResponse(index)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def index_page():
    return HTMLResponse(
        "<html lang='en'><body style='font-family:sans-serif'>"
        "<h2>Bayaan API</h2>"
        "<ul>"
        "<li>Interactive docs: <a href='/docs'>/docs</a></li>"
        "<li>Segment editor: <a href='/editor?translation_id=2&surah=1&ayah=1'>/editor?translation_id=2&amp;surah=1&amp;ayah=1</a></li>"
        "<li>Sample renderer (uses the API): <a href='/reader?translation_id=2&surah=1'>/reader?translation_id=2&amp;surah=1</a></li>"
        "<li>Data endpoint: <a href='/surah/1?translation_id=2'>/surah/1?translation_id=2</a></li>"
        "</ul></body></html>"
    )