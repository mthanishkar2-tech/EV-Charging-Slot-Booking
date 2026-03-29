"""
EV Charging Slot Booking & Load Balancing Scheduler
Enhanced with: OTP, modify, cancel, complete, admin, cost calc
"""

from flask import Flask, render_template, request, redirect, url_for, session, flash
import random, copy, datetime

app = Flask(__name__)
app.secret_key = "ev_scheduler_ultra_secret"

# ─────────────────────────────────────────────
#  CONSTANTS
# ─────────────────────────────────────────────
TIME_SLOTS = [
    "08:00 - 09:00", "09:00 - 10:00", "10:00 - 11:00", "11:00 - 12:00",
    "12:00 - 13:00", "13:00 - 14:00", "14:00 - 15:00", "15:00 - 16:00",
]
CHARGE_OPTIONS = [10, 20, 30, 40, 50]   # kWh
COST_PER_KWH   = 15                      # ₹ per kWh
MAX_MODS       = 2

# ─────────────────────────────────────────────
#  PREDEFINED STATIONS
# ─────────────────────────────────────────────
STATIONS_TEMPLATE = [
    {
        "id": 1, "name": "GreenCharge Hub",
        "location": "Saibaba Colony, Coimbatore",
        "coords": (11.0168, 76.9558),
        "slots": {
            "08:00 - 09:00": {"booked": True,  "otp": "PRE001"},
            "09:00 - 10:00": {"booked": True,  "otp": "PRE002"},
            "10:00 - 11:00": {"booked": False, "otp": None},
            "11:00 - 12:00": {"booked": False, "otp": None},
            "12:00 - 13:00": {"booked": False, "otp": None},
            "13:00 - 14:00": {"booked": False, "otp": None},
            "14:00 - 15:00": {"booked": False, "otp": None},
            "15:00 - 16:00": {"booked": False, "otp": None},
        },
    },
    {
        "id": 2, "name": "VoltPoint Station",
        "location": "RS Puram, Coimbatore",
        "coords": (11.0068, 76.9559),
        "slots": {
            "08:00 - 09:00": {"booked": True,  "otp": "PRE003"},
            "09:00 - 10:00": {"booked": False, "otp": None},
            "10:00 - 11:00": {"booked": True,  "otp": "PRE004"},
            "11:00 - 12:00": {"booked": True,  "otp": "PRE005"},
            "12:00 - 13:00": {"booked": False, "otp": None},
            "13:00 - 14:00": {"booked": False, "otp": None},
            "14:00 - 15:00": {"booked": False, "otp": None},
            "15:00 - 16:00": {"booked": False, "otp": None},
        },
    },
    {
        "id": 3, "name": "EcoJuice Terminal",
        "location": "Gandhipuram, Coimbatore",
        "coords": (11.0168, 76.9658),
        "slots": {
            "08:00 - 09:00": {"booked": True,  "otp": "PRE006"},
            "09:00 - 10:00": {"booked": True,  "otp": "PRE007"},
            "10:00 - 11:00": {"booked": True,  "otp": "PRE008"},
            "11:00 - 12:00": {"booked": True,  "otp": "PRE009"},
            "12:00 - 13:00": {"booked": True,  "otp": "PRE010"},
            "13:00 - 14:00": {"booked": True,  "otp": "PRE011"},
            "14:00 - 15:00": {"booked": True,  "otp": "PRE012"},
            "15:00 - 16:00": {"booked": True,  "otp": "PRE013"},
        },
    },
    {
        "id": 4, "name": "PowerGrid Charging Co.",
        "location": "Peelamedu, Coimbatore",
        "coords": (11.0268, 76.9758),
        "slots": {
            "08:00 - 09:00": {"booked": False, "otp": None},
            "09:00 - 10:00": {"booked": True,  "otp": "PRE014"},
            "10:00 - 11:00": {"booked": False, "otp": None},
            "11:00 - 12:00": {"booked": False, "otp": None},
            "12:00 - 13:00": {"booked": False, "otp": None},
            "13:00 - 14:00": {"booked": True,  "otp": "PRE015"},
            "14:00 - 15:00": {"booked": False, "otp": None},
            "15:00 - 16:00": {"booked": False, "otp": None},
        },
    },
    {
        "id": 5, "name": "SolarCharge Express",
        "location": "Singanallur, Coimbatore",
        "coords": (11.0068, 76.9858),
        "slots": {
            "08:00 - 09:00": {"booked": True,  "otp": "PRE016"},
            "09:00 - 10:00": {"booked": True,  "otp": "PRE017"},
            "10:00 - 11:00": {"booked": False, "otp": None},
            "11:00 - 12:00": {"booked": True,  "otp": "PRE018"},
            "12:00 - 13:00": {"booked": False, "otp": None},
            "13:00 - 14:00": {"booked": False, "otp": None},
            "14:00 - 15:00": {"booked": False, "otp": None},
            "15:00 - 16:00": {"booked": False, "otp": None},
        },
    },
]

stations  = copy.deepcopy(STATIONS_TEMPLATE)
bookings  = {}   # otp -> booking dict

# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────
def get_station(sid):
    return next((s for s in stations if s["id"] == sid), None)

def available_count(s):
    return sum(1 for v in s["slots"].values() if not v["booked"])

def occupied_count(s):
    return sum(1 for v in s["slots"].values() if v["booked"])

def load_pct(s):
    return round(occupied_count(s) / len(s["slots"]) * 100)

def dist(c1, c2):
    return ((c1[0]-c2[0])**2 + (c1[1]-c2[1])**2)**0.5

def suggest_nearest(station):
    candidates = [s for s in stations if s["id"] != station["id"] and available_count(s) > 0]
    return min(candidates, key=lambda s: dist(s["coords"], station["coords"])) if candidates else None

def generate_otp():
    while True:
        otp = str(random.randint(100000, 999999))
        if otp not in bookings:
            return otp

def calc_cost(kwh):
    return kwh * COST_PER_KWH

# ─────────────────────────────────────────────
#  ROUTES
# ─────────────────────────────────────────────

@app.route("/")
def index():
    data = [{**s, "available": available_count(s), "occupied": occupied_count(s),
             "load_pct": load_pct(s), "is_full": available_count(s) == 0} for s in stations]
    return render_template("index.html", stations=data)


@app.route("/book/<int:sid>")
def booking(sid):
    station = get_station(sid)
    if not station:
        return redirect(url_for("index"))
    is_full    = available_count(station) == 0
    suggestion = suggest_nearest(station) if is_full else None
    return render_template("booking.html", station=station,
                           available=available_count(station),
                           occupied=occupied_count(station),
                           is_full=is_full, suggestion=suggestion,
                           charge_options=CHARGE_OPTIONS,
                           cost_per_kwh=COST_PER_KWH)


@app.route("/confirm_booking", methods=["POST"])
def confirm_booking():
    sid        = int(request.form["station_id"])
    time_slot  = request.form["time_slot"]
    user_name  = request.form.get("user_name", "Guest").strip() or "Guest"
    kwh        = int(request.form["charge_kwh"])
    station    = get_station(sid)

    if not station or time_slot not in station["slots"]:
        return redirect(url_for("index"))

    slot = station["slots"][time_slot]
    if slot["booked"]:
        flash("Sorry, that slot was just taken! Please choose another.", "error")
        return redirect(url_for("booking", sid=sid))

    otp  = generate_otp()
    cost = calc_cost(kwh)

    slot["booked"] = True
    slot["otp"]    = otp

    bookings[otp] = {
        "name":          user_name,
        "station_id":    sid,
        "station_name":  station["name"],
        "location":      station["location"],
        "slot":          time_slot,
        "charge_kwh":    kwh,
        "total_cost":    cost,
        "status":        "Booked",
        "modifications": 0,
        "booked_at":     datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    session["otp_confirm"] = otp
    return redirect(url_for("confirmation"))


@app.route("/confirmation")
def confirmation():
    otp  = session.pop("otp_confirm", None)
    if not otp or otp not in bookings:
        return redirect(url_for("index"))
    return render_template("confirmation.html", booking=bookings[otp], otp=otp)


# ── Manage booking via OTP ──
@app.route("/manage", methods=["GET", "POST"])
def manage():
    booking = otp = error = None
    if request.method == "POST":
        otp = request.form.get("otp", "").strip()
        if otp in bookings:
            booking = bookings[otp]
        else:
            error = "Invalid OTP. No booking found."
    return render_template("manage.html", booking=booking, otp=otp,
                           error=error, charge_options=CHARGE_OPTIONS,
                           time_slots=TIME_SLOTS, max_mods=MAX_MODS,
                           cost_per_kwh=COST_PER_KWH)


@app.route("/start_charging", methods=["POST"])
def start_charging():
    otp = request.form["otp"]
    if otp in bookings and bookings[otp]["status"] == "Booked":
        bookings[otp]["status"] = "Active"
    return redirect(url_for("manage_result", otp=otp))


@app.route("/complete_charging", methods=["POST"])
def complete_charging():
    otp = request.form["otp"]
    if otp in bookings and bookings[otp]["status"] == "Active":
        bookings[otp]["status"] = "Completed"
    return redirect(url_for("manage_result", otp=otp))


@app.route("/cancel_booking", methods=["POST"])
def cancel_booking():
    otp = request.form["otp"]
    if otp in bookings:
        b = bookings[otp]
        if b["status"] == "Booked":
            b["status"] = "Cancelled"
            station = get_station(b["station_id"])
            if station and b["slot"] in station["slots"]:
                station["slots"][b["slot"]]["booked"] = False
                station["slots"][b["slot"]]["otp"]    = None
    return redirect(url_for("manage_result", otp=otp))


@app.route("/modify_booking", methods=["POST"])
def modify_booking():
    otp      = request.form["otp"]
    mod_type = request.form.get("mod_type")

    if otp not in bookings:
        return redirect(url_for("manage"))

    b = bookings[otp]
    if b["status"] != "Booked" or b["modifications"] >= MAX_MODS:
        return redirect(url_for("manage_result", otp=otp))

    if mod_type == "slot":
        new_slot = request.form.get("new_slot")
        station  = get_station(b["station_id"])
        if station and new_slot in station["slots"] and not station["slots"][new_slot]["booked"]:
            # Free old slot
            station["slots"][b["slot"]]["booked"] = False
            station["slots"][b["slot"]]["otp"]    = None
            # Book new slot
            station["slots"][new_slot]["booked"] = True
            station["slots"][new_slot]["otp"]    = otp
            b["slot"]          = new_slot
            b["modifications"] += 1

    elif mod_type == "kwh":
        new_kwh = int(request.form.get("new_kwh", b["charge_kwh"]))
        if new_kwh != b["charge_kwh"]:
            b["charge_kwh"]    = new_kwh
            b["total_cost"]    = calc_cost(new_kwh)
            b["modifications"] += 1

    return redirect(url_for("manage_result", otp=otp))


@app.route("/manage/result/<otp>")
def manage_result(otp):
    if otp not in bookings:
        return redirect(url_for("manage"))
    station = get_station(bookings[otp]["station_id"])
    return render_template("manage.html", booking=bookings[otp], otp=otp,
                           error=None, charge_options=CHARGE_OPTIONS,
                           time_slots=TIME_SLOTS, max_mods=MAX_MODS,
                           cost_per_kwh=COST_PER_KWH, station=station)


# ── Admin ──
@app.route("/admin")
def admin():
    total     = len(bookings)
    revenue   = sum(b["total_cost"] for b in bookings.values() if b["status"] in ["Booked","Active","Completed"])
    counts    = {s: sum(1 for b in bookings.values() if b["status"] == s) for s in ["Booked","Active","Completed","Cancelled"]}
    return render_template("admin.html", bookings=bookings, total=total,
                           revenue=revenue, counts=counts)


@app.route("/reset")
def reset():
    global stations, bookings
    stations = copy.deepcopy(STATIONS_TEMPLATE)
    bookings = {}
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True)
