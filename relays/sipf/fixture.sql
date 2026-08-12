PRAGMA user_version = 1;
CREATE TABLE pension_case_source (
            record_id TEXT PRIMARY KEY,
            record_revision TEXT NOT NULL,
            lifecycle_state TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            pensioner_uin TEXT NOT NULL UNIQUE,
            payment_status TEXT NOT NULL
        ) STRICT;
CREATE TABLE survivor_case_source (
            record_id TEXT PRIMARY KEY,
            record_revision TEXT NOT NULL,
            lifecycle_state TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            spouse_uin TEXT NOT NULL UNIQUE,
            survivor_eligible INTEGER NOT NULL CHECK (survivor_eligible IN (0, 1))
        ) STRICT;
CREATE VIEW relay_pension_payment AS
        SELECT record_id, record_revision, lifecycle_state, recorded_at,
               pensioner_uin, payment_status
        FROM pension_case_source;
CREATE VIEW relay_survivor_case AS
        SELECT record_id, record_revision, lifecycle_state, recorded_at,
               spouse_uin, survivor_eligible
        FROM survivor_case_source;
INSERT INTO pension_case_source VALUES
('SIPF-P-1','rev-1','in_payment','2026-07-04T09:00:00Z','2300109568','active'),
('SIPF-P-BAD','rev-2','in_payment','invalid-date-time','2300999999','active');
INSERT INTO survivor_case_source VALUES
('SIPF-S-1','rev-1','active','2026-07-04T09:00:00Z','2300118698',1),
('SIPF-S-BAD','rev-2','active','invalid-date-time','2300888888',0);
PRAGMA optimize;
-- Keep the fixture schema identical to the non-STAT4 live Python publication.
PRAGMA writable_schema = ON;
DELETE FROM sqlite_schema WHERE name = 'sqlite_stat4';
PRAGMA writable_schema = OFF;
