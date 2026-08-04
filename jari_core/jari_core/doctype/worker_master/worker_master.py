import frappe
from frappe.model.document import Document
from frappe.utils import getdate


class WorkerMaster(Document):

    def validate(self):
        self.validate_salary_formats()

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
