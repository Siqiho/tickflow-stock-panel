CREATE TABLE dataset_state (
    dataset_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    unit_version TEXT NOT NULL,
    quality_status TEXT NOT NULL CHECK (quality_status IN ('unknown', 'healthy', 'degraded', 'failed')),
    row_count INTEGER NOT NULL CHECK (row_count >= 0),
    symbol_count INTEGER NOT NULL CHECK (symbol_count >= 0),
    expected_symbol_count INTEGER CHECK (expected_symbol_count >= 0),
    earliest_time TEXT,
    latest_time TEXT,
    managed_bytes INTEGER NOT NULL CHECK (managed_bytes >= 0),
    last_run_id TEXT,
    updated_at TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE TABLE sync_runs (
    run_id TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL,
    provider TEXT,
    operation TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'succeeded', 'degraded', 'failed')),
    rows_fetched INTEGER NOT NULL CHECK (rows_fetched >= 0),
    rows_published INTEGER NOT NULL CHECK (rows_published >= 0),
    quality_status TEXT NOT NULL CHECK (quality_status IN ('unknown', 'healthy', 'degraded', 'failed')),
    error_code TEXT,
    error_message TEXT
);

CREATE TABLE artifacts (
    dataset_id TEXT NOT NULL,
    path TEXT NOT NULL,
    run_id TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    row_count INTEGER NOT NULL CHECK (row_count >= 0),
    bytes INTEGER NOT NULL CHECK (bytes >= 0),
    partition_value TEXT,
    published_at TEXT NOT NULL,
    PRIMARY KEY (dataset_id, path),
    FOREIGN KEY (run_id) REFERENCES sync_runs(run_id) ON DELETE CASCADE
);

CREATE TABLE source_health (
    provider TEXT NOT NULL,
    operation TEXT NOT NULL,
    last_success_at TEXT,
    last_failure_at TEXT,
    consecutive_failures INTEGER NOT NULL CHECK (consecutive_failures >= 0),
    cooldown_until TEXT,
    last_error_code TEXT,
    PRIMARY KEY (provider, operation)
);

CREATE TABLE catalog_meta (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX idx_sync_runs_dataset_started_at ON sync_runs(dataset_id, started_at DESC);
CREATE INDEX idx_artifacts_dataset_id ON artifacts(dataset_id);
