PRAGMA user_version = 1;
CREATE TABLE beneficiary_enrolment_source (
            record_id TEXT PRIMARY KEY,
            record_revision TEXT NOT NULL,
            lifecycle_state TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            uin TEXT NOT NULL UNIQUE,
            duplicate_flag INTEGER NOT NULL CHECK (duplicate_flag IN (0, 1))
        ) STRICT;
CREATE VIEW relay_beneficiary_enrolment AS
        SELECT record_id, record_revision, lifecycle_state, recorded_at,
               uin, duplicate_flag
        FROM beneficiary_enrolment_source;
INSERT INTO beneficiary_enrolment_source VALUES
('MOSD-1','rev-1','active','2026-07-04T09:00:00Z','2300010248',0),
('MOSD-BAD','rev-2','active','invalid-date-time','2300999999',1);
PRAGMA optimize;
-- Keep the fixture schema identical to the non-STAT4 live Python publication.
PRAGMA writable_schema = ON;
DELETE FROM sqlite_schema WHERE name = 'sqlite_stat4';
PRAGMA writable_schema = OFF;
