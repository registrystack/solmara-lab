PRAGMA user_version = 1;
CREATE TABLE farmer_voucher_source (
            record_id TEXT PRIMARY KEY,
            record_revision TEXT NOT NULL,
            lifecycle_state TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            farmer_id TEXT NOT NULL UNIQUE,
            farmer_registered INTEGER NOT NULL CHECK (farmer_registered IN (0, 1)),
            data_use_authorized INTEGER NOT NULL CHECK (data_use_authorized IN (0, 1)),
            active_smallholder_farmer INTEGER NOT NULL CHECK (active_smallholder_farmer IN (0, 1)),
            active_farm_parcel INTEGER NOT NULL CHECK (active_farm_parcel IN (0, 1)),
            crop_declared_for_season INTEGER NOT NULL CHECK (crop_declared_for_season IN (0, 1)),
            district_climate_risk_active INTEGER NOT NULL CHECK (district_climate_risk_active IN (0, 1)),
            voucher_entitlement_current INTEGER NOT NULL CHECK (voucher_entitlement_current IN (0, 1)),
            voucher_not_redeemed INTEGER NOT NULL CHECK (voucher_not_redeemed IN (0, 1))
        ) STRICT;
CREATE TABLE livestock_movement_source (
            record_id TEXT PRIMARY KEY,
            record_revision TEXT NOT NULL,
            lifecycle_state TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            herd_id TEXT NOT NULL UNIQUE,
            farmer_id TEXT NOT NULL,
            registered_herd INTEGER NOT NULL CHECK (registered_herd IN (0, 1)),
            herd_vaccination_current INTEGER NOT NULL CHECK (herd_vaccination_current IN (0, 1)),
            origin_district_not_quarantined_for_species INTEGER NOT NULL CHECK (origin_district_not_quarantined_for_species IN (0, 1)),
            destination_district_open INTEGER NOT NULL CHECK (destination_district_open IN (0, 1)),
            no_conflicting_open_movement_permit INTEGER NOT NULL CHECK (no_conflicting_open_movement_permit IN (0, 1))
        ) STRICT;
CREATE VIEW relay_farmer_voucher AS
        SELECT record_id, record_revision, lifecycle_state, recorded_at,
               farmer_id, farmer_registered, data_use_authorized,
               active_smallholder_farmer, active_farm_parcel,
               crop_declared_for_season, district_climate_risk_active,
               voucher_entitlement_current, voucher_not_redeemed
        FROM farmer_voucher_source;
CREATE VIEW relay_livestock_movement AS
        SELECT record_id, record_revision, lifecycle_state, recorded_at,
               herd_id, farmer_id, registered_herd,
               herd_vaccination_current,
               origin_district_not_quarantined_for_species,
               destination_district_open,
               no_conflicting_open_movement_permit
        FROM livestock_movement_source;
INSERT INTO farmer_voucher_source VALUES
('NAGDI-V-1','rev-1','active','2026-07-04T09:00:00Z','FR-1001',1,1,1,1,1,1,1,1),
('NAGDI-V-BAD','rev-2','active','invalid-date-time','FR-BAD01',1,1,1,1,1,1,1,1);
INSERT INTO livestock_movement_source VALUES
('NAGDI-M-1','rev-1','active','2026-07-04T09:00:00Z','HERD-000001','FR-1001',1,1,1,1,1),
('NAGDI-M-A1','rev-2','active','2026-07-04T09:00:00Z','HERD-AMB-001','FR-AMB1',1,1,1,1,1),
('NAGDI-M-A2','rev-3','active','2026-07-04T09:00:00Z','HERD-AMB-002','FR-AMB1',1,1,1,1,1),
('NAGDI-M-BAD','rev-4','active','invalid-date-time','HERD-BAD-001','FR-BAD01',1,1,1,1,1);
PRAGMA optimize;
-- Keep the fixture schema identical to the non-STAT4 live Python publication.
PRAGMA writable_schema = ON;
DELETE FROM sqlite_schema WHERE name = 'sqlite_stat4';
PRAGMA writable_schema = OFF;
