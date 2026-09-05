-- =====================================================================
-- Migration 002 — `translation_originals`
--
-- Immutable original whole-ayah translations, kept separate from the
-- segment table so the editor can always show the ORIGINAL (pre-editing)
-- translation of an ayah as a read-only reference ("Show original").
--
-- `translation_segments` may later be split into many rows per ayah;
-- `translation_originals` always stores the pristine single translation.
--
-- Copy rule (with a check): for each (translation_id, surah_id, ayah_number)
-- that currently has EXACTLY ONE segment, store that text as the original.
-- Groups with 0 or >1 segments are NOT copied (reported by the migration).
-- =====================================================================

CREATE TABLE IF NOT EXISTS `translation_originals` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `translation_id` int NOT NULL,
  `surah_id` int NOT NULL,
  `ayah_number` int NOT NULL,
  `translation_text` text COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_translation_surah_ayah` (`translation_id`,`surah_id`,`ayah_number`),
  KEY `idx_surah_ayah` (`surah_id`,`ayah_number`),
  CONSTRAINT `translation_originals_ibfk_1` FOREIGN KEY (`translation_id`) REFERENCES `translations` (`id`),
  CONSTRAINT `translation_originals_ibfk_2` FOREIGN KEY (`surah_id`) REFERENCES `surahs` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Copy: only ayahs that currently have exactly one (whole-ayah) segment.
INSERT INTO `translation_originals` (`translation_id`, `surah_id`, `ayah_number`, `translation_text`)
SELECT `translation_id`, `surah_id`, `ayah_number`, MIN(`translation_text`)
FROM `translation_segments`
GROUP BY `translation_id`, `surah_id`, `ayah_number`
HAVING COUNT(*) = 1;

-- Sanity queries (run afterwards):
--   SELECT translation_id, COUNT(*) FROM translation_originals GROUP BY translation_id;
--   SELECT COUNT(*) FROM (
--     SELECT translation_id, surah_id, ayah_number FROM translation_segments
--     GROUP BY translation_id, surah_id, ayah_number HAVING COUNT(*) <> 1
--   ) skipped;
