
import frappe
from frappe.model.document import Document
from frappe.utils import flt, now_datetime


class WorkerDailyAttendance(Document):

    def validate(self):
        if flt(self.approved_hours) < 0:
            frappe.throw(
                "Approved Hours cannot be negative."
            )

        if self.approval_status == "Approved":
            if not self.approved_hours:
                self.approved_hours = self.worked_hours

            self.approved_by = frappe.session.user
            self.approval_date = now_datetime()

        elif self.approval_status == "Rejected":
            self.approved_hours = 0
            self.approved_by = frappe.session.user
            self.approval_date = now_datetime()
