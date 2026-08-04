
import frappe
from frappe.model.document import Document
from frappe.utils import flt


class AttendanceLocationMaster(Document):

    def validate(self):
        latitude = flt(self.latitude)
        longitude = flt(self.longitude)

        if latitude < -90 or latitude > 90:
            frappe.throw(
                "Latitude must be between -90 and 90."
            )

        if longitude < -180 or longitude > 180:
            frappe.throw(
                "Longitude must be between -180 and 180."
            )

        if flt(self.allowed_radius_meters) <= 0:
            frappe.throw(
                "Allowed Radius must be greater than zero."
            )

        if flt(self.maximum_accuracy_meters) <= 0:
            frappe.throw(
                "Maximum GPS Accuracy must be greater than zero."
            )
