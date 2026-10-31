import math

from exceptions import (BusFullError, InvalidInputError, NoBookingError)


def _clean_text(value, field):

    text = str(value).strip()
    if not text:
        raise InvalidInputError(f"{field} cannot be empty.")
    return text


def _clean_coord(value, field, low, high):

    try:
        number = float(value)
    except (TypeError, ValueError):
        raise InvalidInputError(f"{field} must be a number.")
    if not low <= number <= high:
        raise InvalidInputError(f"{field} must be between {low} and {high}.")
    return number


class Stop:


    def __init__(self, stop_id, name, latitude, longitude):
        self.stop_id = _clean_text(stop_id, "STOP ID")
        self.name = name
        self.latitude = latitude
        self.longitude = longitude
        self.__capacity = 0
        self.__booked = 0


    @property
    def name(self):
        return self.__name

    @name.setter
    def name(self, value):
        self.__name = _clean_text(value, "Stop Name")

    @property
    def latitude(self):
        return self.__latitude

    @latitude.setter
    def latitude(self, value):
        self.__latitude = _clean_coord(value, "Latitude", -90, 90)

    @property
    def longitude(self):
        return self.__longitude

    @longitude.setter
    def longitude(self, value):
        self.__longitude = _clean_coord(value, "Longitude", -180, 180)

    
    def to_dict(self):
        return {
            "stop_id": self.stop_id,
            "name": self.name,
            "latitude": self.latitude,
            "longitude": self.longitude
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            data["stop_id"], data["name"], data["latitude"], data["longitude"]
        )

    def __str__(self):
        return f"[{self.stop_id}] {self.name} ({self.latitude}, {self.longitude})"


class Bus:

    def __init__(self, bus_id, name, route, latitude, longitude, capacity, booked=0):
        self.bus_id = _clean_text(bus_id, "BUS ID")
        self.name = name
        self.route = route
        self.latitude = latitude
        self.longitude = longitude
        self.__capacity = 0
        self.__booked = 0
        self.capacity = capacity
        self.booked = booked

    @property
    def name(self):
        return self.__name

    @name.setter
    def name(self, value):
        self.__name = _clean_text(value, "Bus Name")

    @property
    def route(self):
        return self.__route

    @route.setter
    def route(self, value):
        self.__route = _clean_text(value, "Route")

    @property
    def latitude(self):
        return self.__latitude

    @latitude.setter
    def latitude(self, value):
        self.__latitude = _clean_coord(value, "Latitude", -90, 90)

    @property
    def longitude(self):
        return self.__longitude

    @longitude.setter
    def longitude(self, value):
        self.__longitude = _clean_coord(value, "Longitude", -180, 180)


    @property
    def capacity(self):
        return self.__capacity

    @capacity.setter
    def capacity(self, value):
        try:
            value = int(value)
        except (TypeError, ValueError):
            raise InvalidInputError("Capacity must be a whole number.")
        if value <= 0:
            raise InvalidInputError("Capacity must be at least 1.")
        if value < self.__booked:
            raise InvalidInputError(
                f"Capacity cannot be lower than booked seats ({self.__booked})."
            )
        self.__capacity = value

    @property
    def booked(self):
        return self.__booked

    @booked.setter
    def booked(self, value):
        try:
            value = int(value)
        except (TypeError, ValueError):
            raise InvalidInputError("Booked seats must be a whole number.")
        if value < 0:
            raise InvalidInputError("Booked seats cannot be negative.")
        if value > self.capacity:
            raise InvalidInputError("Booked seats cannot exceed the capacity.")
        self.__booked = value

    @property
    def seats_left(self):
        return self.__capacity - self.__booked

    def book_seat(self):
        if self.seats_left == 0:
            raise BusFullError(f"Bus {self.bus_id}  is full.")
        self.__booked += 1

    def cancel_seat(self):
        if self.__booked == 0:
            raise NoBookingError(f"Bus {self.bus_id} has no bookings to cancel.")
        self.__booked -= 1

    def distance_to(self, stop):
        radius_km = 6371.0
        lat1, lon1 = math.radians(self.latitude), math.radians(self.longitude)
        lat2, lon2 = math.radians(stop.latitude), math.radians(stop.longitude)
        a = (math.sin((lat2 - lat1) / 2) ** 2
             + math.cos(lat1) * math.cos(lat2)
             * math.sin((lon2 - lon1) / 2) ** 2)
        return 2 * radius_km * math.asin(math.sqrt(a))


    def to_dict(self):
        return {
            "bus_id": self.bus_id,
            "name": self.name,
            "route": self.route,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "capacity": self.capacity,
            "booked": self.booked,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            data["bus_id"], data["name"], data["route"],
            data["latitude"], data["longitude"],
            data["capacity"], data.get("booked", 0),
        )

    def __str__(self):
        return (f"[{self.bus_id}] {self.name} | {self.route} | "
                f"{self.seats_left}/{self.capacity} seats left")

if __name__ == "__main__":
    stop1 = Stop("S1", "Butuan City Terminal", 8.9475, 125.5406)
    stop2 = Stop("S2", "Cabadbaran City Terminal", 9.1236, 125.5339)
    bus = Bus("B1", "Biyahe Express", "Butuan - Cabadbaran",
              9.0300, 125.5400, capacity=2)

    print(stop1)
    print(stop2)
    print(bus)
    print(f"Distance to Butuan: {bus.distance_to(stop1):.1f} km")
    print(f"Distance to Cabadbaran: {bus.distance_to(stop2):.1f} km")

    bus.book_seat()
    bus.book_seat()
    try:
        bus.book_seat()
    except BusFullError as err:
        print("Expected error:", err)

    try:
        bus.booked = 99  
    except InvalidInputError as err:
        print("Expected error:", err)