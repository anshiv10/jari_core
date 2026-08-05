import frappe
from frappe.model.document import Document
from frappe.utils import getdate

from jari_core.jari_core.doctype.process_master.process_master import (
    sync_legacy_process_assignment,
    validate_master_process_assignments,
)


class WorkerMaster(Document):

    def validate(self):
        validate_master_process_assignments(self)
        sync_legacy_process_assignment(self)
        self.validate_salary_formats()
        self.validate_geo_attendance()

    def validate_geo_attendance(self):
        if not self.geo_attendance_enabled:
            return

        if not self.attendance_user:
            frappe.throw(
                "Attendance User is required when "
                "Geo Attendance is enabled."
            )

        if not self.attendance_location:
            frappe.throw(
                "Default Attendance Location is required when "
                "Geo Attendance is enabled."
            )

        duplicate = frappe.db.exists(
            "Worker Master",
            {
                "attendance_user": self.attendance_user,
                "name": ["!=", self.name],
            },
        )

        if duplicate:
            frappe.throw(
                f"Attendance User {self.attendance_user} is "
                f"already linked to Worker {duplicate}."
            )

    def validate_salary_formats(self):
        seen = set()

        for row in self.salary_formats or []:
            if not row.salary_format:
                frappe.throw(
                    f"Salary Format is required in row #{row.idx}."
                )

            if row.salary_format in seen:
                frappe.throw(
                    f"Salary Format {row.salary_format} "
                    f"is selected more than once."
                )

            seen.add(row.salary_format)

            if (
                row.effective_from
                and row.effective_to
                and getdate(row.effective_from)
                > getdate(row.effective_to)
            ):
                frappe.throw(
                    f"Effective From cannot be after "
                    f"Effective To in row #{row.idx}."
                )
