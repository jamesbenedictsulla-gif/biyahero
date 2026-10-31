class BiyaheroError(Exception):
    "error"

class InvalidInputError(BiyaheroError):
    "a user types negative blank name and characters that are irrelevant"

class DuplicateRecordError(BiyaheroError):
    "when adding bus which another id exists"

class RecordNotFoundError(BiyaheroError):
    "when bus ID or a specific stop does not exist"

class BusFullError(BiyaheroError):
    "This Bus is fully booked"

class NoBookingError(BiyaheroError):
    "Tries to cancel a seat even when nothing is booked"

class DataNotFoundError(BiyaheroError):
    "when inside the data is unreadable"