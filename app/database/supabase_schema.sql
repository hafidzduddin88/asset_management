-- Supabase Schema for Asset Management System
-- Run this in Supabase SQL Editor

-- Reference Tables
CREATE TABLE IF NOT EXISTS ref_companies (
    company_name TEXT PRIMARY KEY,
    company_code TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS ref_categories (
    category_name TEXT PRIMARY KEY,
    category_code INTEGER NOT NULL,
    residual_percent DECIMAL(3,2) NOT NULL,
    useful_life INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS ref_locations (
    location_name TEXT,
    room_name TEXT,
    PRIMARY KEY (location_name)
);

CREATE TABLE IF NOT EXISTS ref_business_units (
    unit_name TEXT PRIMARY KEY,
    company_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ref_owners (
    owner_name TEXT PRIMARY KEY,
    owner_code TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ref_asset_types (
    type_name TEXT PRIMARY KEY,
    category_name TEXT NOT NULL,
    type_code TEXT
);

-- Main Assets Table
CREATE TABLE IF NOT EXISTS assets (
    id INTEGER PRIMARY KEY,
    item_name TEXT NOT NULL,
    category TEXT,
    type TEXT,
    manufacture TEXT,
    model TEXT,
    serial_number TEXT,
    asset_tag TEXT UNIQUE,
    company TEXT,
    business_unit TEXT,
    location TEXT,
    room TEXT,
    notes TEXT,
    item_condition TEXT,
    purchase_date DATE,
    purchase_cost DECIMAL(15,2),
    warranty TEXT,
    supplier TEXT,
    journal TEXT,
    owner TEXT,
    depreciation_value DECIMAL(15,2),
    residual_percent DECIMAL(3,2),
    residual_value DECIMAL(15,2),
    useful_life INTEGER,
    book_value DECIMAL(15,2),
    status TEXT,
    year INTEGER,
    photo_url TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Approvals Table
CREATE TABLE IF NOT EXISTS approvals (
    id INTEGER PRIMARY KEY,
    type TEXT NOT NULL,
    asset_id TEXT,
    asset_name TEXT,
    status TEXT NOT NULL,
    submitted_by TEXT NOT NULL,
    submitted_date TIMESTAMP,
    description TEXT,
    approved_by TEXT,
    approved_date TIMESTAMP,
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Damage Log Table
CREATE TABLE IF NOT EXISTS damage_log (
    id INTEGER PRIMARY KEY,
    asset_id INTEGER,
    asset_name TEXT,
    damage_type TEXT,
    severity TEXT,
    description TEXT,
    reported_by TEXT,
    report_date TIMESTAMP,
    status TEXT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Repair Log Table
CREATE TABLE IF NOT EXISTS repair_log (
    id INTEGER PRIMARY KEY,
    asset_id INTEGER,
    asset_name TEXT,
    repair_action TEXT,
    action_type TEXT,
    description TEXT,
    performed_by TEXT,
    action_date TIMESTAMP,
    status TEXT,
    new_location TEXT,
    new_room TEXT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Disposal Log Table
CREATE TABLE IF NOT EXISTS disposal_log (
    id SERIAL PRIMARY KEY,
    asset_id INTEGER,
    asset_name TEXT,
    disposal_reason TEXT,
    disposal_method TEXT,
    description TEXT,
    requested_by TEXT,
    request_date TIMESTAMP,
    status TEXT,
    disposal_date TIMESTAMP,
    disposed_by TEXT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Lost Log Table
CREATE TABLE IF NOT EXISTS lost_log (
    id SERIAL PRIMARY KEY,
    asset_id INTEGER,
    asset_name TEXT,
    last_location TEXT,
    last_room TEXT,
    date_lost DATE,
    description TEXT,
    reported_by TEXT,
    report_date TIMESTAMP,
    status TEXT,
    investigation_notes TEXT,
    resolution TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_assets_tag ON assets(asset_tag);
CREATE INDEX IF NOT EXISTS idx_assets_status ON assets(status);
CREATE INDEX IF NOT EXISTS idx_assets_category ON assets(category);
CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(status);
CREATE INDEX IF NOT EXISTS idx_damage_asset ON damage_log(asset_id);
CREATE INDEX IF NOT EXISTS idx_repair_asset ON repair_log(asset_id);

-- Enable Row Level Security
ALTER TABLE ref_companies ENABLE ROW LEVEL SECURITY;
ALTER TABLE ref_categories ENABLE ROW LEVEL SECURITY;
ALTER TABLE ref_locations ENABLE ROW LEVEL SECURITY;
ALTER TABLE ref_business_units ENABLE ROW LEVEL SECURITY;
ALTER TABLE ref_owners ENABLE ROW LEVEL SECURITY;
ALTER TABLE ref_asset_types ENABLE ROW LEVEL SECURITY;
ALTER TABLE assets ENABLE ROW LEVEL SECURITY;
ALTER TABLE approvals ENABLE ROW LEVEL SECURITY;
ALTER TABLE damage_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE repair_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE disposal_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE lost_log ENABLE ROW LEVEL SECURITY;

-- Basic RLS Policies (adjust based on your auth requirements)
CREATE POLICY "Enable read access for all users" ON assets FOR SELECT USING (true);
CREATE POLICY "Enable read access for all users" ON approvals FOR SELECT USING (true);
CREATE POLICY "Enable read access for all users" ON damage_log FOR SELECT USING (true);
CREATE POLICY "Enable read access for all users" ON repair_log FOR SELECT USING (true);

-- Reference tables read access
CREATE POLICY "Enable read access for all users" ON ref_companies FOR SELECT USING (true);
CREATE POLICY "Enable read access for all users" ON ref_categories FOR SELECT USING (true);
CREATE POLICY "Enable read access for all users" ON ref_locations FOR SELECT USING (true);
CREATE POLICY "Enable read access for all users" ON ref_business_units FOR SELECT USING (true);
CREATE POLICY "Enable read access for all users" ON ref_owners FOR SELECT USING (true);
CREATE POLICY "Enable read access for all users" ON ref_asset_types FOR SELECT USING (true);