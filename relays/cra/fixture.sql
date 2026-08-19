PRAGMA user_version = 1;
CREATE TABLE civil_person_source (
            record_id TEXT PRIMARY KEY,
            record_revision TEXT NOT NULL,
            lifecycle_state TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            uin TEXT NOT NULL UNIQUE,
            birth_date TEXT NOT NULL,
            birth_brn TEXT,
            deceased INTEGER NOT NULL CHECK (deceased IN (0, 1))
        ) STRICT;
CREATE VIEW relay_civil_person AS
        SELECT record_id, record_revision, lifecycle_state, recorded_at,
               uin, birth_date, birth_brn, deceased
        FROM civil_person_source;
INSERT INTO civil_person_source VALUES
('CP-DEAD','rev-1','deceased','2026-07-04T09:00:00Z','2300109568','1944-02-01','BRN-1944-0301-00012',1),
('CP-LIVE','rev-2','active','2026-07-04T09:00:00Z','2300010248','2022-03-14','BRN-2022-0101-00001',0),
('CP-BAD','rev-3','deceased','invalid-date-time','2300999999','1950-01-01',NULL,1);
PRAGMA optimize;
-- relayctl's bundled SQLite enables STAT4 while the live Python publication does not.
-- Remove only that fixture-only schema entry so the fixture proves the published fingerprint.
PRAGMA writable_schema = ON;
DELETE FROM sqlite_schema WHERE name = 'sqlite_stat4';
PRAGMA writable_schema = OFF;
