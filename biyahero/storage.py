import json
import os

from exceptions import DataNotFoundError, InvalidInputError
from models import Bus, Stop

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BUSES_FILE = os.path.join(BASE_DIR, "buses.json")
STOPS_FILE = os.path.join(BASE_DIR, "stops.json")


def  _read_list(path):
    name = os.path.basename(path)
    if not os.path.exists(path):
        return[]
    try:
        with open(path, "r", encoding="utf-8") as file:
            text = file.read()
    except OSError as err:
        raise DataNotFoundError(f"Cannot read {name}: {err}")

    if not text.strip():
        return[]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as err:
        raise DataNotFoundError(f"{name} is not valid JSON ({err}).")
    if not isinstance(data, list):
        raise DataNotFoundError(f"{name} must contain a list of records.")
    return data


def _write_list(path, records):
    name = os.path.basename(path)
    temp_path = path + ".tmp"
    try:
        with open(temp_path, "w", encoding="utf-8") as file:
            json.dump(records, file, indent=2, ensure_ascii=False)
        os.replace(temp_path, path)
    except (OSError, TypeError) as err:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
        raise DataNotFoundError(f"Cannot save {name}: {err}")


def _build(records, factory, id_field, label, path):
    name = os.path.basename(path)
    items = []
    seen = set()
    for number, record in enumerate(records, start=1):
        try:
            item = factory.from_dict(record)
        except KeyError as err:
            raise DataNotFoundError(f"{label} #{number} in {name} is missing in the field {err}.")
        except (TypeError, InvalidInputError) as err:
            raise DataNotFoundError(f"{label} #{number} in {name} is invalid: {err}")


        item_id = str(getattr(item, id_field)).strip().upper()
        if item_id in seen:
            raise DataNotFoundError(f"Duplicate ID '{item_id}' in {name}.")
        seen.add(item_id)
        items.append(item)
    return items


def load_stops(path=STOPS_FILE):
    return _build(_read_list(path), Stop, "stop_id", "Stop", path)


def load_buses(path=BUSES_FILE):
    return _build(_read_list(path), Bus, "bus_id", Bus, path)


def save_stops(stops, path=STOPS_FILE):
    _write_list(path, [stop.to_dict() for stop in stops])


def save_buses(buses, path=BUSES_FILE):
    _write_list(path, [bus.to_dict() for bus in buses])