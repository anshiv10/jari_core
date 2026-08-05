import math

import frappe
from frappe import _
from frappe.utils import (
    flt,
    get_datetime,
    getdate,
    now_datetime,
)


EARTH_RADIUS_METERS = 6371000


def calculate_distance_meters(
    latitude_1,
    longitude_1,
    latitude_2,
    longitude_2,
):
    lat_1 = math.radians(flt(latitude_1))
    lon_1 = math.radians(flt(longitude_1))
    lat_2 = math.radians(flt(latitude_2))
    lon_2 = math.radians(flt(longitude_2))

    delta_lat = lat_2 - lat_1
    delta_lon = lon_2 - lon_1

    value = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat_1)
        * math.cos(lat_2)
        * math.sin(delta_lon / 2) ** 2
    )

    return EARTH_RADIUS_METERS * (
        2 * math.atan2(
            math.sqrt(value),
            math.sqrt(1 - value),
        )
    )


def get_current_worker():
    user = frappe.session.user

    if user in ("Guest", "Administrator"):
        frappe.throw(
            _("Attendance must be recorded using a worker user.")
        )

    worker = frappe.db.get_value(
        "Worker Master",
        {
            "attendance_user": user,
            "active": 1,
            "geo_attendance_enabled": 1,
        },
        [
            "name",
            "attendance_location",
        ],
        as_dict=True,
    )

    if not worker:
        frappe.throw(
            _(
                "No active Geo Attendance Worker is linked "
                "to user {0}."
            ).format(frappe.bold(user))
        )

    return worker


def get_location(location_name):
    location = frappe.db.get_value(
        "Attendance Location Master",
        location_name,
        [
            "name",
            "latitude",
            "longitude",
            "allowed_radius_meters",
            "maximum_accuracy_meters",
            "active",
        ],
        as_dict=True,
    )

    if not location or not location.active:
        frappe.throw(
            _("Attendance Location is inactive or unavailable.")
        )

    return location


@frappe.whitelist()
def get_attendance_context():
    worker = get_current_worker()
    location = get_location(
        worker.attendance_location
    )

    last_log = frappe.db.get_value(
        "Worker Attendance Log",
        {
            "worker": worker.name,
        },
        [
            "attendance_type",
            "timestamp",
        ],
        order_by="timestamp desc",
        as_dict=True,
    )

    next_type = (
        "OUT"
        if last_log
        and last_log.attendance_type == "IN"
        else "IN"
    )

    return {
        "worker": worker.name,
        "location": location.name,
        "allowed_radius_meters":
            flt(location.allowed_radius_meters),
        "maximum_accuracy_meters":
            flt(location.maximum_accuracy_meters),
        "next_attendance_type": next_type,
        "last_log": last_log,
    }


@frappe.whitelist()
def record_attendance(
    latitude,
    longitude,
    accuracy,
    device_information=None,
):
    worker = get_current_worker()
    location = get_location(
        worker.attendance_location
    )

    latitude = flt(latitude)
    longitude = flt(longitude)
    accuracy = flt(accuracy)

    if latitude < -90 or latitude > 90:
        frappe.throw(_("Invalid captured latitude."))

    if longitude < -180 or longitude > 180:
        frappe.throw(_("Invalid captured longitude."))

    if accuracy <= 0:
        frappe.throw(
            _("GPS accuracy information is required.")
        )

    if accuracy > flt(
        location.maximum_accuracy_meters
    ):
        frappe.throw(
            _(
                "GPS accuracy is {0} metres. "
                "Required accuracy is {1} metres or better."
            ).format(
                flt(accuracy, 2),
                flt(
                    location.maximum_accuracy_meters,
                    2,
                ),
            )
        )

    distance = calculate_distance_meters(
        latitude,
        longitude,
        location.latitude,
        location.longitude,
    )

    if distance > flt(
        location.allowed_radius_meters
    ):
        frappe.throw(
            _(
                "You are {0} metres away from the attendance "
                "location. Allowed radius is {1} metres."
            ).format(
                flt(distance, 2),
                flt(
                    location.allowed_radius_meters,
                    2,
                ),
            )
        )

    frappe.db.sql(
        """
        SELECT name
        FROM `tabWorker Attendance Log`
        WHERE worker = %s
        ORDER BY timestamp DESC
        LIMIT 1
        FOR UPDATE
        """,
        worker.name,
    )

    last_log = frappe.db.get_value(
        "Worker Attendance Log",
        {
            "worker": worker.name,
        },
        [
            "name",
            "attendance_type",
            "timestamp",
        ],
        order_by="timestamp desc",
        as_dict=True,
    )

    attendance_type = (
        "OUT"
        if last_log
        and last_log.attendance_type == "IN"
        else "IN"
    )

    current_time = now_datetime()

    if last_log:
        seconds_since_last = (
            current_time
            - get_datetime(last_log.timestamp)
        ).total_seconds()

        if seconds_since_last < 30:
            frappe.throw(
                _(
                    "Please wait at least 30 seconds before "
                    "recording another attendance entry."
                )
            )

    request_ip = (
        frappe.local.request_ip
        if getattr(frappe.local, "request_ip", None)
        else None
    )

    log = frappe.get_doc({
        "doctype": "Worker Attendance Log",
        "worker": worker.name,
        "attendance_user": frappe.session.user,
        "attendance_type": attendance_type,
        "timestamp": current_time,
        "attendance_date": getdate(current_time),
        "location": location.name,
        "latitude": latitude,
        "longitude": longitude,
        "accuracy_meters": accuracy,
        "distance_meters": flt(distance, 2),
        "within_geofence": 1,
        "device_information":
            device_information or "",
        "ip_address": request_ip,
        "remarks": "Recorded through Geo Attendance",
    })

    log.insert(ignore_permissions=True)

    rebuild_daily_attendance(
        worker.name,
        getdate(current_time),
    )

    return {
        "name": log.name,
        "worker": worker.name,
        "attendance_type": attendance_type,
        "timestamp": current_time,
        "distance_meters": flt(distance, 2),
        "location": location.name,
    }


def rebuild_daily_attendance(
    worker,
    attendance_date,
):
    logs = frappe.get_all(
        "Worker Attendance Log",
        filters={
            "worker": worker,
            "attendance_date": attendance_date,
        },
        fields=[
            "attendance_type",
            "timestamp",
        ],
        order_by="timestamp asc",
        limit_page_length=0,
    )

    worked_seconds = 0
    completed_pairs = 0
    open_in = None
    first_check_in = None
    last_check_out = None

    for log in logs:
        timestamp = get_datetime(log.timestamp)

        if log.attendance_type == "IN":
            if open_in is None:
                open_in = timestamp

                if first_check_in is None:
                    first_check_in = timestamp

        elif (
            log.attendance_type == "OUT"
            and open_in is not None
        ):
            duration = (
                timestamp - open_in
            ).total_seconds()

            if duration > 0:
                worked_seconds += int(duration)
                completed_pairs += 1
                last_check_out = timestamp

            open_in = None

    status = "Absent"

    if completed_pairs:
        status = "Present"
    elif open_in:
        status = "Open"

    name = f"{worker}-{attendance_date}"

    values = {
        "first_check_in": first_check_in,
        "last_check_out": last_check_out,
        "worked_seconds": worked_seconds,
        "worked_hours": flt(
            worked_seconds / 3600,
            4,
        ),
        "completed_pairs": completed_pairs,
        "attendance_status": status,
    }

    if frappe.db.exists(
        "Worker Daily Attendance",
        name,
    ):
        frappe.db.set_value(
            "Worker Daily Attendance",
            name,
            values,
            update_modified=True,
        )
    else:
        frappe.get_doc({
            "doctype": "Worker Daily Attendance",
            "worker": worker,
            "attendance_date": attendance_date,
            "approval_status": "Pending",
            **values,
        }).insert(ignore_permissions=True)
