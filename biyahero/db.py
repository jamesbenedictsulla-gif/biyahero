"""SQLite database for Biyahero.

service.py uses these names: DB_FILE, init_db, setup, get_connection.
The database file (biyahero.db) is created automatically on first run.
If buses.json / stops.json exist next to this file, their data is
imported once, the first time the database is created.
"""
import json
import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "biyahero.db")
BUSES_JSON = os.path.join(BASE_DIR, "buses.json")
STOPS_JSON = os.path.join(BASE_DIR, "stops.json")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    is_admin      INTEGER NOT NULL DEFAULT 0 CHECK (is_admin IN (0, 1)),
    created_at    TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS stops (
    stop_id   TEXT PRIMARY KEY,
    name      TEXT NOT NULL,
    latitude  REAL NOT NULL CHECK (latitude  BETWEEN -90  AND 90),
    longitude REAL NOT NULL CHECK (longitude BETWEEN -180 AND 180)
);

CREATE TABLE IF NOT EXISTS buses (
    bus_id    TEXT PRIMARY KEY,
    name      TEXT NOT NULL,
    route     TEXT NOT NULL,
    latitude  REAL NOT NULL CHECK (latitude  BETWEEN -90  AND 90),
    longitude REAL NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    capacity  INTEGER NOT NULL CHECK (capacity > 0)
);

CREATE TABLE IF NOT EXISTS bookings (
    booking_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    bus_id         TEXT NOT NULL REFERENCES buses(bus_id) ON DELETE CASCADE,
    passenger_name TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'booked'
                   CHECK (status IN ('booked', 'cancelled')),
    created_at     TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- A bus plus how many seats are currently booked.
CREATE VIEW IF NOT EXISTS bus_status AS
SELECT b.*,
       (SELECT COUNT(*) FROM bookings k
         WHERE k.bus_id = b.bus_id AND k.status = 'booked') AS booked
FROM buses b;

-- Rule: never book more seats than the capacity.
CREATE TRIGGER IF NOT EXISTS trg_bus_full
BEFORE INSERT ON bookings
WHEN NEW.status = 'booked' AND
     (SELECT COUNT(*) FROM bookings
       WHERE bus_id = NEW.bus_id AND status = 'booked')
     >= (SELECT capacity FROM buses WHERE bus_id = NEW.bus_id)
BEGIN
    SELECT RAISE(ABORT, 'Bus is full');
END;

-- Rule: capacity can't be lowered below the seats already booked.
CREATE TRIGGER IF NOT EXISTS trg_capacity_check
BEFORE UPDATE OF capacity ON buses
WHEN NEW.capacity < (SELECT COUNT(*) FROM bookings
                      WHERE bus_id = NEW.bus_id AND status = 'booked')
BEGIN
    SELECT RAISE(ABORT, 'Capacity lower than booked seats');
END;
"""


def get_connection(path=DB_FILE):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row            # rows work like dicts
    conn.execute("PRAGMA foreign_keys = ON")  # needed for ON DELETE CASCADE
    return conn


def init_db(path=DB_FILE):
    """Create any missing tables, views and triggers."""
    conn = get_connection(path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def _read_json_list(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as file:
        text = file.read()
    if not text.strip():
        return []
    data = json.loads(text)                   # bad JSON -> ValueError
    if not isinstance(data, list):
        raise ValueError(f"{os.path.basename(path)} must contain a list.")
    return data


def setup(path=DB_FILE):
    """First run: create the database, then import old JSON data if present."""
    init_db(path)
    stops = _read_json_list(STOPS_JSON)
    buses = _read_json_list(BUSES_JSON)

    conn = get_connection(path)
    try:
        with conn:
            for s in stops:
                conn.execute(
                    "INSERT OR IGNORE INTO stops VALUES (?, ?, ?, ?)",
                    (str(s["stop_id"]).strip().upper(), s["name"],
                     float(s["latitude"]), float(s["longitude"])))
            for b in buses:
                bus_id = str(b["bus_id"]).strip().upper()
                conn.execute(
                    "INSERT OR IGNORE INTO buses "
                    "(bus_id, name, route, latitude, longitude, capacity) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (bus_id, b["name"], b["route"], float(b["latitude"]),
                     float(b["longitude"]), int(b["capacity"])))
                # old files stored only a count, so make that many bookings
                for _ in range(int(b.get("booked", 0))):
                    conn.execute(
                        "INSERT INTO bookings (bus_id, passenger_name) "
                        "VALUES (?, 'Walk-in passenger')", (bus_id,))
    finally:
        conn.close()


if __name__ == "__main__":
    setup()
    print("Database ready:", DB_FILE)