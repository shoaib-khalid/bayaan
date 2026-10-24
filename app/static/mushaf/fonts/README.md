# Fonts used by the Mushaf reader

Fonts are served locally so pagination does not depend on an external font service loading after the first render. A locally loaded face also means the page is measured with the font it is drawn in — a late web font changes every width and silently invalidates the pagination.

## Arabic — `indopak-v4.2.1.woff2`

Quran Foundation **IndoPak Nastaleeq** (waqf-lazim v4.2.1), the same file the existing reader loads. It is the only face that carries the Private-Use ornament glyphs the `ayah_words` tokens use for end-of-ayah markers; with any other font those characters render as boxes.

Source: <https://verses.quran.foundation/fonts/quran/hafs/nastaleeq/indopak/indopak-nastaleeq-waqf-lazim-v4.2.1.woff2>

## Urdu — `jameel-noori-nastaleeq.ttf`

**Jameel Noori Nastaleeq**, version 1, 2008. Credited as the font itself declares, read from its `name` table:

| Field | Value |
|---|---|
| Family | `Jameel Noori Nastaleeq` |
| Designer | `Urdu Lover` |
| Version | `Version 1; 2008` |
| Copyright | `This Font Is Free Of Charge For Urdu Lovers` |
| License | `This Font Is Free Of Charge For Urdu Lovers` |

That sentence is the whole of the terms the file states: it declares no fee, no attribution requirement, no redistribution grant and no license URL. It is bundled here on that basis, credited to its designer as above. Anyone redistributing this repository further should satisfy themselves that "free of charge" covers their use; the substitution below is the way out if it does not.

The page asks for the family as `Urdu` via `@font-face` in `styles.css` and has **no fallback chain**, so replacing the file is all that is needed — any Nastaliq face works, provided it is re-checked against `npm test` and a print preview, since the layout measures real glyph widths rather than assuming them.

