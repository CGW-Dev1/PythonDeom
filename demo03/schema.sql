PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'viewer',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS data_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'csv',
    url TEXT,
    compliance_note TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id TEXT NOT NULL UNIQUE,
    city TEXT NOT NULL,
    district TEXT NOT NULL,
    block TEXT,
    community TEXT NOT NULL,
    layout TEXT,
    bedrooms INTEGER,
    living_rooms INTEGER,
    area REAL NOT NULL,
    floor_level TEXT,
    total_floors INTEGER,
    orientation TEXT,
    decoration TEXT,
    build_year INTEGER,
    list_total_price REAL,
    list_unit_price REAL,
    deal_total_price REAL,
    deal_unit_price REAL,
    price_adjust_count INTEGER DEFAULT 0,
    price_adjust_amount REAL DEFAULT 0,
    avg_mom REAL DEFAULT 0,
    avg_yoy REAL DEFAULT 0,
    status TEXT NOT NULL DEFAULT '在售',
    listing_date TEXT,
    deal_date TEXT,
    transaction_cycle INTEGER,
    transaction_type TEXT,
    school TEXT,
    hospital TEXT,
    mall TEXT,
    metro_station TEXT,
    plot_ratio REAL,
    greening_rate REAL,
    property_fee REAL,
    view_count INTEGER DEFAULT 0,
    follow_count INTEGER DEFAULT 0,
    source_name TEXT,
    data_version TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS import_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name TEXT,
    status TEXT NOT NULL,
    rows_total INTEGER DEFAULT 0,
    rows_inserted INTEGER DEFAULT 0,
    rows_updated INTEGER DEFAULT 0,
    rows_error INTEGER DEFAULT 0,
    message TEXT,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS system_configs (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS operation_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT,
    action TEXT NOT NULL,
    detail TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_listings_city ON listings(city);
CREATE INDEX IF NOT EXISTS idx_listings_district ON listings(district);
CREATE INDEX IF NOT EXISTS idx_listings_status ON listings(status);
CREATE INDEX IF NOT EXISTS idx_listings_listing_date ON listings(listing_date);
CREATE INDEX IF NOT EXISTS idx_listings_deal_date ON listings(deal_date);
CREATE INDEX IF NOT EXISTS idx_listings_price ON listings(list_unit_price);
CREATE INDEX IF NOT EXISTS idx_listings_area ON listings(area);
CREATE INDEX IF NOT EXISTS idx_listings_city_district ON listings(city, district);
