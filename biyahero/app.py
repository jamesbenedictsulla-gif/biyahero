"""Biyahero web app (Flask). Routes only: all rules live in service.py."""
from functools import wraps

from flask import (Flask, flash, redirect, render_template, request,
                   session, url_for)

from exceptions import BiyaheroError
from service import BiyaheroService

app = Flask(__name__)
app.secret_key = "change-this-to-something-random"   # needed for session/flash
ADMIN_PASSWORD = "admin123"                          # change before demo!

service = BiyaheroService()
service.ensure_admin(ADMIN_PASSWORD)     # admin account: username "admin"


# ---------- helpers ----------
def _safe_next(target):
    """Only allow redirects to pages on this site."""
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return url_for("home")


def _stop_choices():
    """Stops shown in the route dropdowns."""
    try:
        return service.list_stops()
    except BiyaheroError as err:
        flash(str(err), "error")
        return []


def login_required(view):
    """Only logged-in users (passengers or admin) may open the page."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("username"):
            flash("Please log in or register first.", "error")
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapper


def admin_required(view):
    """Only logged-in admins may open the page."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("is_admin"):
            flash("Please log in as admin first.", "error")
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapper


@app.context_processor
def inject_user():
    """Makes 'is_admin' and 'current_user' available in every template."""
    return {"is_admin": session.get("is_admin", False),
            "current_user": session.get("username")}


# ---------- register / login ----------
@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("username"):
        return redirect(url_for("home"))
    form = request.form
    if request.method == "POST":
        try:
            username = service.register_user(form.get("username"),
                                             form.get("password"),
                                             form.get("confirm"))
            flash(f"Account created! Welcome, {username}. Please log in.",
                  "success")
            return redirect(url_for("login", next=request.args.get("next", "")))
        except BiyaheroError as err:
            flash(str(err), "error")
    return render_template("register.html", form=form)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        try:
            user = service.authenticate(request.form.get("username"),
                                        request.form.get("password"))
            session.clear()
            session["user_id"] = user["user_id"]
            session["username"] = user["username"]
            session["is_admin"] = user["is_admin"]
            flash(f"Welcome back, {user['username']}!", "success")
            return redirect(_safe_next(request.args.get("next", "")))
        except BiyaheroError as err:
            flash(str(err), "error")
    return render_template("login.html", form=request.form)


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out.", "success")
    return redirect(url_for("home"))


# ---------- passenger pages ----------
@app.route("/")
def home():
    try:
        buses = service.list_buses()
    except BiyaheroError as err:
        flash(str(err), "error")
        buses = []
    return render_template("buses.html", buses=buses)


@app.route("/stops")
def stops():
    try:
        items = service.list_stops()
    except BiyaheroError as err:
        flash(str(err), "error")
        items = []
    return render_template("stops.html", stops=items)


@app.route("/distances")
def distances():
    try:
        table = service.distance_table()
        stop_list = service.list_stops()
        route_km = service.route_lengths()
    except BiyaheroError as err:
        flash(str(err), "error")
        table, stop_list, route_km = [], [], {}
    return render_template("distances.html", table=table, stops=stop_list,
                           route_km=route_km)


@app.route("/book/<bus_id>", methods=["GET", "POST"])
@login_required
def book(bus_id):
    try:
        bus = service.get_bus(bus_id)
    except BiyaheroError as err:
        flash(str(err), "error")
        return redirect(url_for("home"))

    if request.method == "POST":
        name = request.form.get("passenger_name", "").strip()
        try:
            service.book_seat(bus_id, name or session["username"])
            flash(f"Seat booked on {bus.name}!", "success")
            return redirect(url_for("bookings"))
        except BiyaheroError as err:
            flash(str(err), "error")
            bus = service.get_bus(bus_id)        # refresh seats_left
    return render_template("book.html", bus=bus)


@app.route("/bookings")
@login_required
def bookings():
    try:
        items = service.list_bookings()
        names = {b.bus_id: b.name for b in service.list_buses()}
    except BiyaheroError as err:
        flash(str(err), "error")
        items, names = [], {}
    return render_template("bookings.html", bookings=items, bus_names=names)


@app.route("/bookings/<int:booking_id>/cancel", methods=["POST"])
@login_required
def cancel_booking(booking_id):
    try:
        service.cancel_booking(booking_id)
        flash("Booking cancelled.", "success")
    except BiyaheroError as err:
        flash(str(err), "error")
    return redirect(url_for("bookings"))


# ---------- admin: buses ----------
@app.route("/admin/buses/add", methods=["GET", "POST"])
@admin_required
def add_bus():
    form = request.form
    if request.method == "POST":
        try:
            route = service.build_route(form.get("route_from"),
                                        form.get("route_to"))
            start = service.get_stop(form.get("route_from"))
            # a new bus starts at the first stop of its route
            service.add_bus(form.get("bus_id"), form.get("name"), route,
                            form.get("latitude") or start.latitude,
                            form.get("longitude") or start.longitude,
                            form.get("capacity"))
            flash("Bus added!", "success")
            return redirect(url_for("home"))
        except BiyaheroError as err:
            flash(str(err), "error")
    return render_template("bus_form.html", bus=form, editing=False,
                           stops=_stop_choices(),
                           route_from=form.get("route_from", ""),
                           route_to=form.get("route_to", ""))


@app.route("/admin/buses/<bus_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_bus(bus_id):
    try:
        bus = service.get_bus(bus_id)
    except BiyaheroError as err:
        flash(str(err), "error")
        return redirect(url_for("home"))

    if request.method == "POST":
        form = request.form
        try:
            route = service.build_route(form.get("route_from"),
                                        form.get("route_to"))
            service.update_bus(bus_id, name=form.get("name"),
                               route=route,
                               latitude=form.get("latitude"),
                               longitude=form.get("longitude"),
                               capacity=form.get("capacity"))
            flash("Bus updated!", "success")
            return redirect(url_for("home"))
        except BiyaheroError as err:
            flash(str(err), "error")
        route_from = form.get("route_from", "")
        route_to = form.get("route_to", "")
    else:
        start, end = service.route_stops(bus.route)    # preselect current route
        route_from = start.stop_id if start else ""
        route_to = end.stop_id if end else ""
    return render_template("bus_form.html", bus=bus, editing=True,
                           stops=_stop_choices(),
                           route_from=route_from, route_to=route_to)


@app.route("/admin/buses/<bus_id>/delete", methods=["POST"])
@admin_required
def delete_bus(bus_id):
    try:
        service.delete_bus(bus_id)
        flash("Bus deleted.", "success")
    except BiyaheroError as err:
        flash(str(err), "error")
    return redirect(url_for("home"))


# ---------- admin: stops ----------
@app.route("/admin/stops/add", methods=["GET", "POST"])
@admin_required
def add_stop():
    form = request.form
    if request.method == "POST":
        try:
            service.add_stop(form.get("stop_id"), form.get("name"),
                             form.get("latitude"), form.get("longitude"))
            flash("Stop added!", "success")
            return redirect(url_for("stops"))
        except BiyaheroError as err:
            flash(str(err), "error")
    return render_template("stop_form.html", stop=form, editing=False)


@app.route("/admin/stops/<stop_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_stop(stop_id):
    try:
        stop = service.get_stop(stop_id)
    except BiyaheroError as err:
        flash(str(err), "error")
        return redirect(url_for("stops"))

    if request.method == "POST":
        form = request.form
        try:
            service.update_stop(stop_id, name=form.get("name"),
                                latitude=form.get("latitude"),
                                longitude=form.get("longitude"))
            flash("Stop updated!", "success")
            return redirect(url_for("stops"))
        except BiyaheroError as err:
            flash(str(err), "error")
    return render_template("stop_form.html", stop=stop, editing=True)


@app.route("/admin/stops/<stop_id>/delete", methods=["POST"])
@admin_required
def delete_stop(stop_id):
    try:
        service.delete_stop(stop_id)
        flash("Stop deleted.", "success")
    except BiyaheroError as err:
        flash(str(err), "error")
    return redirect(url_for("stops"))


if __name__ == "__main__":
    app.run(debug=True)