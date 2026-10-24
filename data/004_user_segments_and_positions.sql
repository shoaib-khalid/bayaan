-- =====================================================================
-- Migration 004 — per-user segments, and where each user left off
--
-- Two independent additions:
--
--   1. `user_translation_segments` — a private copy of an ayah's segments
--      for one person, so several people can segment the same ayah without
--      overwriting each other.
--   2. `user_positions` — the last place each person was reading or editing,
--      one per page.
--
-- Why a second segments table instead of a `user_id` column on the existing
-- one: `translation_segments` is the canonical text that every reader gets
-- when nobody has an opinion. Adding a nullable owner there would mean every
-- existing query has to remember to filter (`user_id IS NULL OR user_id = ?`),
-- and forgetting it in one place silently shows one person's private edits to
-- everybody. Two tables make the fallback explicit instead of implicit.
-- =====================================================================


-- ---------------------------------------------------------------------
-- user_translation_segments
--
-- Same shape as `translation_segments` plus `user_id`, with the owner in
-- every unique key.
--
-- THE FALLBACK RULE: the existence of ANY row for a
-- (user_id, translation_id, surah_id, ayah_number) means that person has
-- taken over that ayah — all of its segments come from here, never a mix of
-- their rows and the shared ones. Ayahs with no rows fall back to
-- `translation_segments`. Granularity is the ayah, not the surah: editing one
-- ayah must not blank out the other 285.
--
-- `segment_index` starts at 1 and is dense per ayah, mirroring the canonical
-- table, so a reader can render either one with the same code.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `user_translation_segments` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `translation_id` int NOT NULL,
  `surah_id` int NOT NULL,
  `ayah_number` int NOT NULL,
  `segment_index` int NOT NULL,
  `word_start` bigint NOT NULL,
  `word_end` bigint NOT NULL,
  `translation_text` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_user_segment` (`user_id`,`translation_id`,`surah_id`,`ayah_number`,`segment_index`),
  -- The reader's question is always "does this user have rows for this ayah",
  -- so the covering index leads with the user and ends at the ayah.
  KEY `idx_user_ayah` (`user_id`,`translation_id`,`surah_id`,`ayah_number`),
  KEY `idx_user_segment_words` (`word_start`,`word_end`),
  CONSTRAINT `user_translation_segments_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  CONSTRAINT `user_translation_segments_ibfk_2` FOREIGN KEY (`translation_id`) REFERENCES `translations` (`id`),
  CONSTRAINT `user_translation_segments_ibfk_3` FOREIGN KEY (`surah_id`) REFERENCES `surahs` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ---------------------------------------------------------------------
-- user_positions — "where did I leave off", one row per page per person
-- per translation.
--
-- `context` is the page: reader, reader-mushaf, mushaf, editor. Keeping the
-- translation in the key means reading al-Baqarah in Jalandhri does not
-- overwrite the bookmark you had in Bayan-ul-Quran — the two are separate
-- places to be.
--
-- `location` stores the query string that page needs (surah, ayah, page,
-- font sizes) rather than a hand-picked set of columns, so a reader that
-- later remembers one more thing does not need a migration — and so an
-- existing URL can be restored exactly as it was.
--
-- Opening a page with NO parameters resumes the most recently touched
-- bookmark for that page, whatever its translation (see idx_user_recent);
-- a URL that carries parameters always wins, so a shared link still opens
-- where the link says.
--
-- ON DELETE CASCADE means removing an account takes its bookmarks with it;
-- accounts are normally disabled rather than deleted, so this is a safety net.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `user_positions` (
  `user_id` int NOT NULL,
  `context` varchar(32) NOT NULL,
  `translation_id` int NOT NULL,
  `location` varchar(512) NOT NULL,
  -- Microseconds, not seconds: two bookmarks can be saved inside the same
  -- second (switching translation twice), and with second precision the
  -- "most recently touched" query silently picks one of them at random.
  `updated_at` timestamp(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`user_id`,`context`,`translation_id`),
  KEY `idx_user_recent` (`user_id`,`updated_at`),
  CONSTRAINT `user_positions_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  CONSTRAINT `user_positions_ibfk_2` FOREIGN KEY (`translation_id`) REFERENCES `translations` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- =====================================================================
-- Seed: a capability for saving one's own reading position
--
-- Granting it to every role is what makes it a "self" capability — it guards
-- nothing but the caller's own bookmark, so there is no hierarchy to respect.
-- =====================================================================
INSERT IGNORE INTO `permissions` (`perm_key`, `label`, `description`) VALUES
  ('self.position', 'Save reading position', 'Remembering where the signed-in user left off.');

INSERT IGNORE INTO `permission_paths` (`permission_id`, `path_prefix`, `http_methods`)
SELECT `id`, '/api/position', 'POST' FROM `permissions` WHERE `perm_key` = 'self.position';

INSERT IGNORE INTO `role_permissions` (`role_id`, `permission_id`)
SELECT r.`id`, p.`id`
FROM `roles` r
JOIN `permissions` p ON p.`perm_key` = 'self.position'
WHERE r.`name` IN ('admin', 'editor', 'viewer');


-- =====================================================================
-- Sanity queries (run afterwards):
--
--   SHOW CREATE TABLE user_translation_segments;
--   SHOW CREATE TABLE user_positions;
--
--   -- How many ayahs has each person taken over?
--   SELECT u.username, COUNT(DISTINCT s.surah_id, s.ayah_number) AS ayahs_overridden
--     FROM user_translation_segments s JOIN users u ON u.id = s.user_id
--    GROUP BY u.id, u.username;
--
--   -- Where did a person leave off?
--   SELECT context, location, updated_at FROM user_positions
--    WHERE user_id = 5 ORDER BY context;
--
--   -- Throw away one person's private edit of a single ayah, falling back to
--   -- the canonical segments again:
--   -- DELETE FROM user_translation_segments
--   --  WHERE user_id = 5 AND translation_id = 2 AND surah_id = 2 AND ayah_number = 19;
-- =====================================================================
