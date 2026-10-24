-- =====================================================================
-- Migration 003 — roles, permissions, users, sessions
--
-- Access control is defined in the DATABASE, not in code. Nothing in
-- this file is compiled into the app, and nothing here needs a restart:
-- the guard re-reads `permission_paths` / `role_permissions` as it
-- serves requests, so an INSERT or DELETE below takes effect on the
-- next request.
--
-- Three ideas, kept deliberately separate:
--
--   permissions       a capability, e.g. `page.editor` or `api.write`.
--   permission_paths  which URL(s) that capability protects.
--   role_permissions  which role has which capability.
--
-- Resolving a request is therefore: longest matching `path_prefix` for
-- the request path and method -> that permission -> does the signed-in
-- user's role have it. A prefix matches the path itself or anything
-- below it, so `/static` covers `/static/mushaf/fonts/x.woff2` while
-- `/reader` does NOT cover `/reader-mushaf`. Rows flagged `is_public`
-- are served without signing in.
--
-- Because the table is the source of truth, a new page is protected by
-- inserting one `permission_paths` row — no code change, no restart.
-- The inverse is also true: a URL with no row is not protected, so
-- `scripts/manage_users.py permissions` lists any path the guard is
-- not covering.
--
-- CSRF: token-based CSRF protection is intentionally NOT implemented
-- yet. Session cookies are HttpOnly + SameSite=Lax, which blocks the
-- cross-site form POST, and writes are restricted to roles that already
-- have `api.write`. Documented in ReadMe.md as a known limitation.
-- =====================================================================


-- ---------------------------------------------------------------------
-- roles
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `roles` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(32) NOT NULL,
  `description` varchar(255) DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_roles_name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ---------------------------------------------------------------------
-- permissions — one row per capability
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `permissions` (
  `id` int NOT NULL AUTO_INCREMENT,
  `perm_key` varchar(64) NOT NULL,
  `label` varchar(128) NOT NULL,
  `description` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_permissions_key` (`perm_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ---------------------------------------------------------------------
-- permission_paths — the URLs each capability guards.
--   path_prefix  matched against the request path: exact, or anything
--                below it on a `/` boundary.
--   http_methods comma-separated list, or `*` for every method.
--   is_public    1 = reachable signed out; the capability is ignored.
--
-- A path may appear twice with different methods (e.g. `/segments` GET
-- is readable, `/segments` POST is a write).
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `permission_paths` (
  `id` int NOT NULL AUTO_INCREMENT,
  `permission_id` int NOT NULL,
  `path_prefix` varchar(255) NOT NULL,
  `http_methods` varchar(64) NOT NULL DEFAULT '*',
  `is_public` tinyint(1) NOT NULL DEFAULT 0,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_permission_paths` (`path_prefix`,`http_methods`),
  KEY `idx_permission_paths_permission` (`permission_id`),
  CONSTRAINT `permission_paths_ibfk_1` FOREIGN KEY (`permission_id`) REFERENCES `permissions` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ---------------------------------------------------------------------
-- role_permissions — which role has which capability.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `role_permissions` (
  `role_id` int NOT NULL,
  `permission_id` int NOT NULL,
  PRIMARY KEY (`role_id`,`permission_id`),
  KEY `idx_role_permissions_permission` (`permission_id`),
  CONSTRAINT `role_permissions_ibfk_1` FOREIGN KEY (`role_id`) REFERENCES `roles` (`id`) ON DELETE CASCADE,
  CONSTRAINT `role_permissions_ibfk_2` FOREIGN KEY (`permission_id`) REFERENCES `permissions` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ---------------------------------------------------------------------
-- users
--
-- password_hash holds the whole verifier as one string, so the
-- algorithm and its cost are stored with the value and can be raised
-- later without a schema change:
--
--     pbkdf2_sha256$<iterations>$<salt-b64>$<hash-b64>
--
-- There is no password column, no reset token and no email: an admin
-- sets a new password and passes it on by hand. `is_active` is the only
-- off switch — accounts are disabled, never deleted, so the segments a
-- person wrote keep their author.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `users` (
  `id` int NOT NULL AUTO_INCREMENT,
  `username` varchar(64) NOT NULL,
  `display_name` varchar(128) DEFAULT NULL,
  `password_hash` varchar(255) NOT NULL,
  `role_id` int NOT NULL,
  `is_active` tinyint(1) NOT NULL DEFAULT 1,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `last_login_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_users_username` (`username`),
  KEY `idx_users_role` (`role_id`),
  CONSTRAINT `users_ibfk_1` FOREIGN KEY (`role_id`) REFERENCES `roles` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ---------------------------------------------------------------------
-- sessions
--
-- The cookie carries a random token; only its SHA-256 is stored, so a
-- dump of this table cannot be replayed as a sign-in. Ended sessions
-- are deleted rather than flagged, and the row disappears with the
-- user.
--
-- `expires_at` is the idle deadline and is pushed forward on use;
-- `remember_me` marks the long-lived ones so they can be recognised.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `sessions` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `token_hash` char(64) NOT NULL,
  `user_id` int NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `last_seen_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `expires_at` datetime NOT NULL,
  `remember_me` tinyint(1) NOT NULL DEFAULT 0,
  `ip` varchar(45) DEFAULT NULL,
  `user_agent` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_sessions_token` (`token_hash`),
  KEY `idx_sessions_user` (`user_id`),
  KEY `idx_sessions_expires` (`expires_at`),
  CONSTRAINT `sessions_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- =====================================================================
-- Seed: roles
-- =====================================================================
INSERT IGNORE INTO `roles` (`name`, `description`) VALUES
  ('admin',  'Everything, including user administration and the API docs.'),
  ('editor', 'Reads every reader and may create and save translation segments.'),
  ('viewer', 'Reads the readers only; cannot open the editor or change anything.');


-- =====================================================================
-- Seed: capabilities
-- =====================================================================
INSERT IGNORE INTO `permissions` (`perm_key`, `label`, `description`) VALUES
  ('public',               'Signed-out access',      'Pages reachable without a session: sign-in, sign-out, static files.'),
  ('page.home',            'Home page',              'The index listing the readers.'),
  ('page.reader',          'Reader (interlinear)',   'The segment-aligned reader.'),
  ('page.reader_mushaf',   'Mushaf reader',          'The fixed-page mushaf reader.'),
  ('page.mushaf',          'Print-ready mushaf',     'The A4 print-ready mushaf.'),
  ('page.editor',          'Segment editor',         'The segment editor and its release notes.'),
  ('page.admin',           'Administration',         'User administration under /admin.'),
  ('page.docs',            'API documentation',      'Swagger UI and the OpenAPI document.'),
  ('api.read',             'Read the API',           'Surahs, ayahs, translations and segments.'),
  ('api.write',            'Write segments',         'Saving segments (POST /segments).'),
  ('self.password',        'Change own password',    'The signed-in user changing their own password.');


-- =====================================================================
-- Seed: which URLs each capability guards
--
-- Signed-out URLs first. `/login` must be open or nobody can sign in.
-- =====================================================================
INSERT IGNORE INTO `permission_paths` (`permission_id`, `path_prefix`, `http_methods`, `is_public`)
SELECT `id`, '/login',      'GET,POST', 1 FROM `permissions` WHERE `perm_key` = 'public';
INSERT IGNORE INTO `permission_paths` (`permission_id`, `path_prefix`, `http_methods`, `is_public`)
SELECT `id`, '/logout',     'GET,POST', 1 FROM `permissions` WHERE `perm_key` = 'public';
INSERT IGNORE INTO `permission_paths` (`permission_id`, `path_prefix`, `http_methods`, `is_public`)
SELECT `id`, '/static',     'GET',      1 FROM `permissions` WHERE `perm_key` = 'public';
INSERT IGNORE INTO `permission_paths` (`permission_id`, `path_prefix`, `http_methods`, `is_public`)
SELECT `id`, '/favicon.ico','GET',      1 FROM `permissions` WHERE `perm_key` = 'public';
-- Public by design: with no valid cookie it answers {"user": null} and nothing
-- else, so the sign-out strip can call it from the sign-in page too.
INSERT IGNORE INTO `permission_paths` (`permission_id`, `path_prefix`, `http_methods`, `is_public`)
SELECT `id`, '/api/me',     'GET',      1 FROM `permissions` WHERE `perm_key` = 'public';

INSERT IGNORE INTO `permission_paths` (`permission_id`, `path_prefix`, `http_methods`)
SELECT `id`, '/',                'GET' FROM `permissions` WHERE `perm_key` = 'page.home';
INSERT IGNORE INTO `permission_paths` (`permission_id`, `path_prefix`, `http_methods`)
SELECT `id`, '/reader',          'GET' FROM `permissions` WHERE `perm_key` = 'page.reader';
INSERT IGNORE INTO `permission_paths` (`permission_id`, `path_prefix`, `http_methods`)
SELECT `id`, '/reader-mushaf',   'GET' FROM `permissions` WHERE `perm_key` = 'page.reader_mushaf';
INSERT IGNORE INTO `permission_paths` (`permission_id`, `path_prefix`, `http_methods`)
SELECT `id`, '/mushaf',          'GET' FROM `permissions` WHERE `perm_key` = 'page.mushaf';
-- `/editor` also covers `/editor/release-notes`, by the prefix rule.
INSERT IGNORE INTO `permission_paths` (`permission_id`, `path_prefix`, `http_methods`)
SELECT `id`, '/editor',          'GET' FROM `permissions` WHERE `perm_key` = 'page.editor';
INSERT IGNORE INTO `permission_paths` (`permission_id`, `path_prefix`, `http_methods`)
SELECT `id`, '/admin',           'GET,POST' FROM `permissions` WHERE `perm_key` = 'page.admin';
INSERT IGNORE INTO `permission_paths` (`permission_id`, `path_prefix`, `http_methods`)
SELECT `id`, '/docs',            'GET' FROM `permissions` WHERE `perm_key` = 'page.docs';
INSERT IGNORE INTO `permission_paths` (`permission_id`, `path_prefix`, `http_methods`)
SELECT `id`, '/openapi.json',    'GET' FROM `permissions` WHERE `perm_key` = 'page.docs';
-- FastAPI serves a second docs page at /redoc; it needs the same guard.
INSERT IGNORE INTO `permission_paths` (`permission_id`, `path_prefix`, `http_methods`)
SELECT `id`, '/redoc',           'GET' FROM `permissions` WHERE `perm_key` = 'page.docs';

INSERT IGNORE INTO `permission_paths` (`permission_id`, `path_prefix`, `http_methods`)
SELECT `id`, '/surahs',          'GET' FROM `permissions` WHERE `perm_key` = 'api.read';
INSERT IGNORE INTO `permission_paths` (`permission_id`, `path_prefix`, `http_methods`)
SELECT `id`, '/surah',           'GET' FROM `permissions` WHERE `perm_key` = 'api.read';
INSERT IGNORE INTO `permission_paths` (`permission_id`, `path_prefix`, `http_methods`)
SELECT `id`, '/ayah',            'GET' FROM `permissions` WHERE `perm_key` = 'api.read';
INSERT IGNORE INTO `permission_paths` (`permission_id`, `path_prefix`, `http_methods`)
SELECT `id`, '/translations',    'GET' FROM `permissions` WHERE `perm_key` = 'api.read';
INSERT IGNORE INTO `permission_paths` (`permission_id`, `path_prefix`, `http_methods`)
SELECT `id`, '/original',        'GET' FROM `permissions` WHERE `perm_key` = 'api.read';
INSERT IGNORE INTO `permission_paths` (`permission_id`, `path_prefix`, `http_methods`)
SELECT `id`, '/segments',        'GET' FROM `permissions` WHERE `perm_key` = 'api.read';
-- The same path again, but only POST: reading is api.read, writing is api.write.
INSERT IGNORE INTO `permission_paths` (`permission_id`, `path_prefix`, `http_methods`)
SELECT `id`, '/segments',        'POST' FROM `permissions` WHERE `perm_key` = 'api.write';
INSERT IGNORE INTO `permission_paths` (`permission_id`, `path_prefix`, `http_methods`)
SELECT `id`, '/me/password',     'GET,POST' FROM `permissions` WHERE `perm_key` = 'self.password';


-- =====================================================================
-- Seed: role -> capability
--
-- admin   everything
-- editor  every reader + the editor + reading and writing segments
-- viewer  every reader, read-only API, own password
-- =====================================================================
INSERT IGNORE INTO `role_permissions` (`role_id`, `permission_id`)
SELECT r.`id`, p.`id`
FROM `roles` r
JOIN `permissions` p ON p.`perm_key` IN (
  'page.home', 'page.reader', 'page.reader_mushaf', 'page.mushaf', 'page.editor',
  'page.admin', 'page.docs', 'api.read', 'api.write', 'self.password'
)
WHERE r.`name` = 'admin';

INSERT IGNORE INTO `role_permissions` (`role_id`, `permission_id`)
SELECT r.`id`, p.`id`
FROM `roles` r
JOIN `permissions` p ON p.`perm_key` IN (
  'page.home', 'page.reader', 'page.reader_mushaf', 'page.mushaf', 'page.editor',
  'api.read', 'api.write', 'self.password'
)
WHERE r.`name` = 'editor';

INSERT IGNORE INTO `role_permissions` (`role_id`, `permission_id`)
SELECT r.`id`, p.`id`
FROM `roles` r
JOIN `permissions` p ON p.`perm_key` IN (
  'page.home', 'page.reader', 'page.reader_mushaf', 'page.mushaf',
  'api.read', 'self.password'
)
WHERE r.`name` = 'viewer';


-- =====================================================================
-- Sanity queries (run afterwards):
--
--   SELECT r.name, COUNT(rp.permission_id) AS capabilities
--     FROM roles r LEFT JOIN role_permissions rp ON rp.role_id = r.id
--    GROUP BY r.name ORDER BY r.name;
--   -- expect admin 10, editor 8, viewer 6
--
--   -- Every path a URL could hit, and who may:
--   SELECT pp.path_prefix, pp.http_methods, pp.is_public, p.perm_key
--     FROM permission_paths pp JOIN permissions p ON p.id = pp.permission_id
--    ORDER BY pp.path_prefix;
--
--   -- Which role may open /editor?
--   SELECT r.name FROM roles r
--     JOIN role_permissions rp ON rp.role_id = r.id
--     JOIN permissions p ON p.id = rp.permission_id
--    WHERE p.perm_key = 'page.editor';
--
--   -- Grant the editor role /admin too, with no restart:
--   -- INSERT IGNORE INTO role_permissions (role_id, permission_id)
--   -- SELECT r.id, p.id FROM roles r, permissions p
--   --  WHERE r.name = 'editor' AND p.perm_key = 'page.admin';
-- =====================================================================
