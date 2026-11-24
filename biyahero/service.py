import os
import re
import sqlite3
from contextlib import contextmanager

from werkzeug.security import check_password_hash, generate_password_hash

import db
from exceptions import (
    BusFullError,
    DataNotFoundError,
    DuplicateRecordError,
    InvalidInputError,
    NoBookingError,
    RecordNotFoundError,
)
from models import Bus, Stop

DEFAULT_PASSENGER = "Walk-in passenger"
USERNAME_RE = re.compile(r"[A-Za-z0-9_]{3,30}")
MIN_PASSWORD = 6


def _key(record_id):
    """IDs are not case-sensitive: ' b1 ' and 'B1' are the same bus."""
    return str(record_id).strip().upper()


def _clean_passenger(name):
    name = str(name).strip()
    if not name:
        raise InvalidInputError("Passenger name cannot be empty.")
    if len(name) > 60:
        raise InvalidInputError("Passenger name is too long (max 60 characters).")
    return name


def _stop_from_row(row):
    return Stop(row["stop_id"], row["name"], row["latitude"], row["longitude"])


def _bus_from_row(row):
    """Rows come from the bus_status view, which already has 'booked'."""
    return Bus(row["bus_id"], row["name"], row["route"], row["latitude"],
               row["longitude"], row["capacity"], row["booked"])


class BiyaheroService:

    def __init__(self, db_path=db.DB_FILE):
        self._db_path = db_path
        try:
            if os.path.exists(db_path):
                db.init_db(db_path)      # makes sure all tables exist
            else:
                db.setup(db_path)        # first run: create + import the JSON data
        except (sqlite3.Error, OSError, ValueError, KeyError) as err:
            raise DataNotFoundError(f"Cannot open the database: {err}")

    # Database session: commit on success, roll back on error
    @contextmanager
    def _session(self):
        try:
            conn = db.get_connection(self._db_path)
        except sqlite3.Error as err:
            raise DataNotFoundError(f"Cannot open the database: {err}")
        try:
            with conn:
                yield conn
        except sqlite3.IntegrityError as err:      # database rules fired
            text = str(err)
            if "Bus is full" in text:
                raise BusFullError("This bus is full.")
            if "UNIQUE" in text:
                raise DuplicateRecordError("That ID already exists.")
            if "lower than booked" in text:
                raise InvalidInputError(
                    "Capacity cannot be lower than the seats already booked.")
            raise InvalidInputError(f"The database refused that data: {text}")
        except sqlite3.Error as err:
            raise DataNotFoundError(f"Database error: {err}")
        finally:
            conn.close()



    # USERS
    def register_user(self, username, password, confirm):
        """Create a passenger account. Returns the username."""
        username = str(username or "").strip()
        if not USERNAME_RE.fullmatch(username):
            raise InvalidInputError(
                "Username must be 3-30 characters: letters, numbers or _ only.")
        password = str(password or "")
        if len(password) < MIN_PASSWORD:
            raise InvalidInputError(
                f"Password must be at least {MIN_PASSWORD} characters.")
        if password != str(confirm or ""):
            raise InvalidInputError("Passwords do not match.")
        with self._session() as conn:
            if conn.execute("SELECT 1 FROM users WHERE username = ?",
                            (username,)).fetchone():
                raise DuplicateRecordError(
                    f"Username '{username}' is already taken.")
            conn.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (username, generate_password_hash(password)))
        return username

    def authenticate(self, username, password):
        """Return {'user_id', 'username', 'is_admin'} or raise InvalidInputError."""
        with self._session() as conn:
            row = conn.execute("SELECT * FROM users WHERE username = ?",
                               (str(username or "").strip(),)).fetchone()
        if row is None or not check_password_hash(row["password_hash"],
                                                   str(password or "")):
            raise InvalidInputError("Wrong username or password.")
        return {"user_id": row["user_id"], "username": row["username"],
                "is_admin": bool(row["is_admin"])}

    def ensure_admin(self, password, username="admin"):
        """Create the admin account on first run (does nothing if it exists)."""
        with self._session() as conn:
            if conn.execute("SELECT 1 FROM users WHERE username = ?",
                            (username,)).fetchone():
                return
            conn.execute(
                "INSERT INTO users (username, password_hash, is_admin) "
                "VALUES (?, ?, 1)",
                (username, generate_password_hash(password)))



    # STOPS
    def list_stops(self):
        with self._session() as conn:
            rows = conn.execute("SELECT * FROM stops ORDER BY stop_id").fetchall()
        return [_stop_from_row(r) for r in rows]

    def get_stop(self, stop_id):
        with self._session() as conn:
            row = conn.execute("SELECT * FROM stops WHERE stop_id = ?",
                               (_key(stop_id),)).fetchone()
        if row is None:
            raise RecordNotFoundError(f"Stop '{str(stop_id).strip()}' was not found.")
        return _stop_from_row(row)

    def add_stop(self, stop_id, name, latitude, longitude):
        key = _key(stop_id)
        stop = Stop(key, name, latitude, longitude)      # validates the values
        with self._session() as conn:
            if conn.execute("SELECT 1 FROM stops WHERE stop_id = ?",
                            (key,)).fetchone():
                raise DuplicateRecordError(f"Stop '{key}' already exists.")
            conn.execute(
                "INSERT INTO stops (stop_id, name, latitude, longitude) "
                "VALUES (?, ?, ?, ?)",
                (stop.stop_id, stop.name, stop.latitude, stop.longitude))
        return stop

    def update_stop(self, stop_id, name=None, latitude=None, longitude=None):
        """Only the fields you pass (not None) are changed."""
        stop = self.get_stop(stop_id)
        if name is not None:
            stop.name = name
        if latitude is not None:
            stop.latitude = latitude
        if longitude is not None:
            stop.longitude = longitude
        with self._session() as conn:
            conn.execute(
                "UPDATE stops SET name = ?, latitude = ?, longitude = ? "
                "WHERE stop_id = ?",
                (stop.name, stop.latitude, stop.longitude, stop.stop_id))
        return stop

    def delete_stop(self, stop_id):
        stop = self.get_stop(stop_id)
        with self._session() as conn:
            conn.execute("DELETE FROM stops WHERE stop_id = ?", (stop.stop_id,))
        return stop

    # BUSES
    def list_buses(self):
        with self._session() as conn:
            rows = conn.execute(
                "SELECT * FROM bus_status ORDER BY bus_id").fetchall()
        return [_bus_from_row(r) for r in rows]

    def get_bus(self, bus_id):
        with self._session() as conn:
            row = conn.execute("SELECT * FROM bus_status WHERE bus_id = ?",
                               (_key(bus_id),)).fetchone()
        if row is None:
            raise RecordNotFoundError(f"Bus '{str(bus_id).strip()}' was not found.")
        return _bus_from_row(row)

    def add_bus(self, bus_id, name, route, latitude, longitude, capacity):
        key = _key(bus_id)
        bus = Bus(key, name, route, latitude, longitude, capacity)
        with self._session() as conn:
            if conn.execute("SELECT 1 FROM buses WHERE bus_id = ?",
                            (key,)).fetchone():
                raise DuplicateRecordError(f"Bus '{key}' already exists.")
            conn.execute(
                "INSERT INTO buses (bus_id, name, route, latitude, longitude,"
                " capacity) VALUES (?, ?, ?, ?, ?, ?)",
                (bus.bus_id, bus.name, bus.route, bus.latitude,
                 bus.longitude, bus.capacity))
        return bus

    def update_bus(self, bus_id, name=None, route=None,
                   latitude=None, longitude=None, capacity=None):
        """Only the fields you pass (not None) are changed."""
        bus = self.get_bus(bus_id)        # has the real 'booked' count
        if name is not None:
            bus.name = name
        if route is not None:
            bus.route = route
        if latitude is not None:
            bus.latitude = latitude
        if longitude is not None:
            bus.longitude = longitude
        if capacity is not None:
            bus.capacity = capacity       # refuses if lower than booked seats
        with self._session() as conn:
            conn.execute(
                "UPDATE buses SET name = ?, route = ?, latitude = ?, "
                "longitude = ?, capacity = ? WHERE bus_id = ?",
                (bus.name, bus.route, bus.latitude, bus.longitude,
                 bus.capacity, bus.bus_id))
        return bus

    def delete_bus(self, bus_id):
        bus = self.get_bus(bus_id)
        with self._session() as conn:     # its bookings are deleted with it
            conn.execute("DELETE FROM buses WHERE bus_id = ?", (bus.bus_id,))
        return bus

    # PASSENGER actions
    def book_seat(self, bus_id, passenger_name=DEFAULT_PASSENGER):
        passenger = _clean_passenger(passenger_name)
        bus = self.get_bus(bus_id)
        if bus.seats_left == 0:
            raise BusFullError(f"Bus {bus.bus_id} is full.")
        with self._session() as conn:     # the database re-checks 'full'
            conn.execute(
                "INSERT INTO bookings (bus_id, passenger_name) VALUES (?, ?)",
                (bus.bus_id, passenger))
        return self.get_bus(bus.bus_id)

    def cancel_seat(self, bus_id, passenger_name=None):
        """Cancel the newest booking on this bus (or the newest one
        with that passenger name)."""
        bus = self.get_bus(bus_id)
        sql = ("SELECT booking_id FROM bookings "
               "WHERE bus_id = ? AND status = 'booked'")
        args = [bus.bus_id]
        if passenger_name is not None:
            sql += " AND passenger_name = ?"
            args.append(str(passenger_name).strip())
        sql += " ORDER BY booking_id DESC LIMIT 1"
        with self._session() as conn:
            row = conn.execute(sql, args).fetchone()
            if row is None:
                raise NoBookingError(
                    f"Bus {bus.bus_id} has no bookings to cancel.")
            conn.execute("UPDATE bookings SET status = 'cancelled' "
                         "WHERE booking_id = ?", (row["booking_id"],))
        return self.get_bus(bus.bus_id)

    def cancel_booking(self, booking_id):
        """Cancel one specific booking (used by the web pages)."""
        with self._session() as conn:
            row = conn.execute(
                "SELECT bus_id, status FROM bookings WHERE booking_id = ?",
                (booking_id,)).fetchone()
            if row is None:
                raise RecordNotFoundError(f"Booking #{booking_id} was not found.")
            if row["status"] != "booked":
                raise NoBookingError(f"Booking #{booking_id} is already cancelled.")
            conn.execute("UPDATE bookings SET status = 'cancelled' "
                         "WHERE booking_id = ?", (booking_id,))
        return self.get_bus(row["bus_id"])

    def list_bookings(self, bus_id=None, status="booked"):
        """Return a list of dicts: booking_id, bus_id, passenger_name, status, created_at."""
        sql = "SELECT * FROM bookings WHERE status = ?"
        args = [status]
        if bus_id is not None:
            sql += " AND bus_id = ?"
            args.append(_key(bus_id))
        sql += " ORDER BY booking_id"
        with self._session() as conn:
            rows = conn.execute(sql, args).fetchall()
        return [dict(r) for r in rows]

    # ROUTES
    def build_route(self, from_id, to_id):
        """Turn two chosen stop IDs into route text like 'Stop A - Stop B'."""
        if not from_id or not to_id:
            raise InvalidInputError("Please choose where the route starts and ends.")
        origin = self.get_stop(from_id)
        destination = self.get_stop(to_id)
        if origin.stop_id == destination.stop_id:
            raise InvalidInputError("The route must start and end at different stops.")
        return f"{origin.name} - {destination.name}"

    def route_stops(self, route, stops=None):
        """Return (start_stop, end_stop) for a route text, or (None, None).

        A part matches a stop by its full name, or by the start of the name,
        so older routes such as 'Butuan - Cabadbaran' still work."""
        parts = str(route).split(" - ")
        if len(parts) != 2:
            return None, None
        stops = self.list_stops() if stops is None else stops

        def find(text):
            text = text.strip().lower()
            for stop in stops:
                if stop.name.lower() == text:
                    return stop
            for stop in stops:
                if text and stop.name.lower().startswith(text):
                    return stop
            return None

        start, end = find(parts[0]), find(parts[1])
        if start is None or end is None:
            return None, None
        return start, end

    def route_distance(self, route, stops=None):
        """Straight-line km between the route's two stops, or None."""
        start, end = self.route_stops(route, stops)
        if start is None:
            return None
        # Bus.distance_to only reads .latitude/.longitude, so it works for stops too
        return Bus.distance_to(start, end)

    def route_lengths(self):
        """Return {bus_id: km}; buses whose route can't be matched are left out."""
        stops = self.list_stops()
        lengths = {}
        for bus in self.list_buses():
            km = self.route_distance(bus.route, stops)
            if km is not None:
                lengths[bus.bus_id] = km
        return lengths


    

    # DISTANCES
    def distance_table(self):
        """Return [(bus, [(stop, km), (stop, km), ...]), ...]"""
        stops = self.list_stops()
        return [
            (bus, [(stop, bus.distance_to(stop)) for stop in stops])
            for bus in self.list_buses()
        ]


if __name__ == "__main__":
    # Self-test: uses a temporary database, so biyahero.db is untouched.
    import tempfile

    def expect(error, func, *args, **kwargs):
        try:
            func(*args, **kwargs)
        except error as err:
            print(f"  OK   {error.__name__}: {err}")
        else:
            print(f"  FAIL {error.__name__} was NOT raised")

    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "test.db")
        db.init_db(path)                   # empty database
        service = BiyaheroService(path)

        service.add_stop("s1", "Butuan City Terminal", 8.9589, 125.5349)
        service.add_stop("S2", "Cabadbaran City Terminal", 9.1236, 125.5339)
        service.add_bus("b1", "Bachelor Express", "Butuan - Cabadbaran",
                        9.0300, 125.5400, 2)
        service.add_bus("B2", "Agusan Liner", "Butuan - Nasipit",
                        8.9700, 125.4300, 30)

        print("Error checks:")
        expect(DuplicateRecordError, service.add_stop, "S1", "Copy", 1, 1)
        expect(RecordNotFoundError, service.delete_stop, "S99")
        expect(InvalidInputError, service.add_bus,
               "B9", "Bad", "Route", 0, 0, -5)
        expect(InvalidInputError, service.add_stop, "S8", "Far", 150, 0)

        service.book_seat("B1", "Juan Dela Cruz")
        service.book_seat("B1", "Maria Santos")
        expect(BusFullError, service.book_seat, "B1", "Pedro")
        service.cancel_seat("B1", "Juan Dela Cruz")
        expect(NoBookingError, service.cancel_seat, "B2")
        expect(InvalidInputError, service.update_bus, "B1", capacity=0)
        expect(InvalidInputError, service.book_seat, "B2", "   ")
        expect(RecordNotFoundError, service.cancel_booking, 999)

        service.update_bus("B1", name="Bachelor Express Plus")

        print("\nReload from the database (proves saving works):")
        again = BiyaheroService(path)
        for bus, rows in again.distance_table():
            print(" ", bus)
            for stop, km in rows:
                print(f"      {km:6.1f} km to {stop.name}")
        print("\nBookings on B1:", [(b["passenger_name"], b["status"])
              for b in again.list_bookings("B1", "booked")])