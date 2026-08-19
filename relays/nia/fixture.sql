PRAGMA user_version = 1;
CREATE TABLE population_person_source (
            record_id TEXT PRIMARY KEY,
            record_revision TEXT NOT NULL,
            lifecycle_state TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            uin TEXT NOT NULL UNIQUE,
            legacy_nid TEXT,
            given_name TEXT NOT NULL,
            family_name TEXT NOT NULL,
            sex TEXT NOT NULL,
            birth_date TEXT NOT NULL,
            identity_status TEXT NOT NULL,
            alive INTEGER NOT NULL CHECK (alive IN (0, 1))
        ) STRICT;
CREATE VIEW relay_population_person AS
        SELECT record_id, record_revision, lifecycle_state, recorded_at,
               uin, legacy_nid, given_name, family_name, sex, birth_date,
               identity_status, alive
        FROM population_person_source;
INSERT INTO population_person_source VALUES
('CP-1','rev-1','active','2026-07-04T09:00:00Z','2300010248','NID-1001','Mateo','Santos','male','2022-03-14','active',1), -- legacy_nid migration fixture
('CP-BAD','rev-2','active','2026-07-04T09:00:00Z','2300999999',NULL,'Bad','Row','unknown','not-a-date','active',1);
PRAGMA optimize;
-- Keep the fixture schema identical to the non-STAT4 live Python publication.
PRAGMA writable_schema = ON;
DELETE FROM sqlite_schema WHERE name = 'sqlite_stat4';
PRAGMA writable_schema = OFF;
