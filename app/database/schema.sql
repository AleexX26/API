PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY);
INSERT OR IGNORE INTO schema_version VALUES (1);
CREATE TABLE IF NOT EXISTS categories (
 id INTEGER PRIMARY KEY, source_id TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
 parent_id INTEGER REFERENCES categories(id));
CREATE TABLE IF NOT EXISTS products (
 id INTEGER PRIMARY KEY, source_id TEXT UNIQUE NOT NULL, name TEXT,
 active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)));
CREATE TABLE IF NOT EXISTS product_categories (
 product_id INTEGER REFERENCES products(id), category_id INTEGER REFERENCES categories(id),
 PRIMARY KEY(product_id,category_id));
CREATE TABLE IF NOT EXISTS property_groups (
 id INTEGER PRIMARY KEY, source_name TEXT UNIQUE NOT NULL, title TEXT);
CREATE TABLE IF NOT EXISTS property_options (
 id INTEGER PRIMARY KEY, group_id INTEGER NOT NULL REFERENCES property_groups(id),
 source_id TEXT NOT NULL, label TEXT, UNIQUE(group_id,source_id));
CREATE TABLE IF NOT EXISTS product_property_options (
 product_id INTEGER REFERENCES products(id), option_id INTEGER REFERENCES property_options(id),
 PRIMARY KEY(product_id,option_id));
CREATE TABLE IF NOT EXISTS configurations (
 id TEXT PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES products(id),
 country TEXT NOT NULL, currency TEXT NOT NULL, account_scope TEXT NOT NULL,
 services_json TEXT NOT NULL, canonical_json TEXT NOT NULL,
 validity_evidence TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS configuration_options (
 configuration_id TEXT REFERENCES configurations(id), option_id INTEGER REFERENCES property_options(id),
 PRIMARY KEY(configuration_id,option_id));
CREATE TABLE IF NOT EXISTS quantities (
 id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES products(id),
 source_id TEXT NOT NULL, value INTEGER NOT NULL CHECK(value>0), UNIQUE(product_id,source_id,value));
CREATE TABLE IF NOT EXISTS shipping_options (
 id INTEGER PRIMARY KEY, source_id TEXT UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS sync_runs (
 id INTEGER PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT,
 status TEXT NOT NULL CHECK(status IN ('running','success','failed')),
 source TEXT NOT NULL, source_sha256 TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sync_errors (
 id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL REFERENCES sync_runs(id), message TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS prices (
 id INTEGER PRIMARY KEY, configuration_id TEXT NOT NULL REFERENCES configurations(id),
 quantity_id INTEGER NOT NULL REFERENCES quantities(id), shipping_option_id INTEGER NOT NULL REFERENCES shipping_options(id),
 product_net TEXT NOT NULL, total_net TEXT NOT NULL, total_gross TEXT NOT NULL,
 shipping_net TEXT NOT NULL, shipping_gross TEXT, total_vat TEXT NOT NULL, unit_product_net TEXT NOT NULL,
 delivery_days TEXT NOT NULL, delivery_text TEXT NOT NULL,
 observed_at TEXT NOT NULL, imported_at TEXT NOT NULL, valid_until TEXT NOT NULL,
 run_id INTEGER NOT NULL REFERENCES sync_runs(id),
 UNIQUE(configuration_id,quantity_id,shipping_option_id));
CREATE TABLE IF NOT EXISTS price_history (
 id INTEGER PRIMARY KEY, price_id INTEGER NOT NULL REFERENCES prices(id),
 old_snapshot_json TEXT NOT NULL, replaced_at TEXT NOT NULL,
 replacement_run_id INTEGER NOT NULL REFERENCES sync_runs(id));
CREATE INDEX IF NOT EXISTS idx_config_product ON configurations(product_id);
CREATE INDEX IF NOT EXISTS idx_price_validity ON prices(valid_until);
CREATE INDEX IF NOT EXISTS idx_history_price ON price_history(price_id,replaced_at);
CREATE INDEX IF NOT EXISTS idx_errors_run ON sync_errors(run_id);
