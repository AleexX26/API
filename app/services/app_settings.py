"""Settings of the screen that a person changes: the standard configuration (what the buttons start on), the quantity
buttons, and the providers that must not appear for a product. Kept in the workbench database, apart from the collected
data, so they survive a new collection and are the same for everyone who uses this PC's comparator.
"""
import json
import sqlite3
from pathlib import Path

EMPTY = {"standard": {}, "quantities": [], "hidden": {}}


def init(path: Path) -> None:
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")


def load(path: Path | None) -> dict:
    if path is None or not Path(path).exists():
        return json.loads(json.dumps(EMPTY))
    with sqlite3.connect(path) as db:
        try:
            row = db.execute("SELECT value FROM app_settings WHERE key='screen'").fetchone()
        except sqlite3.OperationalError:
            row = None
    try:
        data = json.loads(row[0]) if row else {}
    except ValueError:
        data = {}
    return {key: data.get(key, json.loads(json.dumps(default))) for key, default in EMPTY.items()}


def save(path: Path, data: dict) -> dict:
    clean = {key: data.get(key, json.loads(json.dumps(default))) for key, default in EMPTY.items()}
    with sqlite3.connect(path) as db:
        db.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES ('screen', ?)", (json.dumps(clean, ensure_ascii=False),))
    return clean
