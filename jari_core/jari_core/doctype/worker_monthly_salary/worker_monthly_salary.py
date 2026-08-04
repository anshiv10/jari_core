import calendar

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import (
    flt,
    get_first_day,
    get_last_day,
    getdate,
)


class WorkerMonthlySalary(Document):

    def validate(self):
        self.set_period_dates()
        self.validate_duplicate_salary()
        self.load_worker_salary_formats()
        self.fetch_approved_attendance_hours()
        self.calculate_salary_details()
        self.calculate_totals()

    def before_submit(self):
        self.validate_all_required_values()

    def on_submit(self):
        frappe.db.set_value(
            self.doctype,
            self.name,
            "status",
            "Submitted",
            update_modified=False,
        )

    def on_cancel(self):
        frappe.db.set_value(
            self.doctype,
            self.name,
            "status",
            "Cancelled",
            update_modified=False,
        )

    def set_period_dates(self):
        if not self.salary_month:
            return

        salary_month = getdate(
            self.salary_month
        )

        self.salary_month = salary_month.replace(
            day=1
        )

        self.period_start = get_first_day(
            salary_month
        )

        self.period_end = get_last_day(
            salary_month
        )

    def validate_duplicate_salary(self):
        if not self.worker or not self.salary_month:
            return

        duplicate = frappe.db.exists(
            "Worker Monthly Salary",
            {
                "worker": self.worker,
                "salary_month": self.salary_month,
                "docstatus": ["<", 2],
                "name": ["!=", self.name],
            },
        )

        if duplicate:
            frappe.throw(
                _(
                    "Salary for Worker {0} and Month {1} "
                    "already exists in {2}."
                ).format(
                    frappe.bold(self.worker),
                    frappe.bold(
                        str(self.salary_month)
                    ),
                    frappe.bold(duplicate),
                )
            )

    def get_active_worker_mappings(self):
        if not self.worker:
            return []

        worker = frappe.get_doc(
            "Worker Master",
            self.worker,
        )

        salary_date = getdate(
            self.period_end
        )

        mappings = []

        for row in worker.salary_formats or []:
            if not row.active:
                continue

            if (
                row.effective_from
                and getdate(row.effective_from)
                > salary_date
            ):
                continue

            if (
                row.effective_to
                and getdate(row.effective_to)
                < getdate(self.period_start)
            ):
                continue

            mappings.append(row)

        return mappings

    def load_worker_salary_formats(self):
        if not self.worker:
            return

        mappings = self.get_active_worker_mappings()

        if not mappings:
            frappe.throw(
                _(
                    "No active Salary Formats are assigned "
                    "to Worker {0} for this salary period."
                ).format(
                    frappe.bold(self.worker)
                )
            )

        existing_rows = {
            row.salary_format: row
            for row in self.salary_details or []
            if row.salary_format
        }

        ordered_rows = []

        for mapping in mappings:
            salary_format = frappe.get_doc(
                "Worker Salary Format",
                mapping.salary_format,
            )

            row = existing_rows.get(
                mapping.salary_format
            )

            if not row:
                row = self.append(
                    "salary_details",
                    {},
                )

            row.salary_format = salary_format.name
            row.salary_group = (
                salary_format.salary_group
            )
            row.calculation_basis = (
                salary_format.calculation_basis
            )
            row.data_source = (
                salary_format.data_source
            )
            row.requires_quality = (
                salary_format.requires_quality
            )

            if not flt(row.rate):
                row.rate = flt(
                    mapping.default_rate
                )

            self.populate_quality_rates(
                row,
                salary_format,
            )

            ordered_rows.append(row)

        self.set(
            "salary_details",
            ordered_rows,
        )

    def populate_quality_rates(
        self,
        detail_row,
        salary_format,
    ):
        if not salary_format.requires_quality:
            return

        existing = {
            row.quality_code: row
            for row in detail_row.quality_details or []
            if row.quality_code
        }

        rows = []

        for rate_row in salary_format.rate_items or []:
            if not rate_row.active:
                continue

            if not rate_row.quality_code:
                continue

            row = existing.get(
                rate_row.quality_code
            )

            if not row:
                row = detail_row.append(
                    "quality_details",
                    {},
                )

            row.quality_code = (
                rate_row.quality_code
            )

            if not flt(row.rate):
                row.rate = flt(rate_row.rate)

            rows.append(row)

        detail_row.set(
            "quality_details",
            rows,
        )

    def fetch_approved_attendance_hours(self):
        if not self.worker:
            self.approved_attendance_hours = 0
            return

        approved_hours = frappe.db.sql(
            """
            SELECT COALESCE(
                SUM(approved_hours),
                0
            )
            FROM `tabWorker Daily Attendance`
            WHERE worker = %(worker)s
              AND attendance_date
                  BETWEEN %(start)s AND %(end)s
              AND approval_status = 'Approved'
            """,
            {
                "worker": self.worker,
                "start": self.period_start,
                "end": self.period_end,
            },
        )[0][0]

        self.approved_attendance_hours = flt(
            approved_hours,
            4,
        )

    def calculate_salary_details(self):
        for row in self.salary_details or []:
            if row.requires_quality:
                self.calculate_quality_detail(row)
                continue

            if row.data_source == "Geo Attendance":
                row.source_quantity = flt(
                    self.approved_attendance_hours,
                    4,
                )

                row.source_reference = (
                    f"Approved Geo Attendance: "
                    f"{self.period_start} to "
                    f"{self.period_end}"
                )

            quantity = flt(
                row.source_quantity
            )

            rate = flt(row.rate)

            if quantity < 0:
                frappe.throw(
                    _(
                        "Source Quantity cannot be negative "
                        "for Salary Format {0}."
                    ).format(
                        frappe.bold(
                            row.salary_format
                        )
                    )
                )

            if rate < 0:
                frappe.throw(
                    _(
                        "Rate cannot be negative for "
                        "Salary Format {0}."
                    ).format(
                        frappe.bold(
                            row.salary_format
                        )
                    )
                )

            row.base_amount = flt(
                quantity * rate,
                2,
            )

            row.final_amount = flt(
                row.base_amount
                + flt(row.extra_amount),
                2,
            )

    def calculate_quality_detail(self, row):
        base_amount = 0
        total_quantity = 0

        if not row.quality_details:
            frappe.throw(
                _(
                    "Quality-wise rows are required for "
                    "Salary Format {0}."
                ).format(
                    frappe.bold(
                        row.salary_format
                    )
                )
            )

        seen_quality = set()

        for quality_row in row.quality_details:
            if not quality_row.quality_code:
                frappe.throw(
                    _(
                        "Quality is required in every row "
                        "for Salary Format {0}."
                    ).format(
                        frappe.bold(
                            row.salary_format
                        )
                    )
                )

            if (
                quality_row.quality_code
                in seen_quality
            ):
                frappe.throw(
                    _(
                        "Duplicate Quality {0} in Salary "
                        "Format {1}."
                    ).format(
                        frappe.bold(
                            quality_row.quality_code
                        ),
                        frappe.bold(
                            row.salary_format
                        ),
                    )
                )

            seen_quality.add(
                quality_row.quality_code
            )

            quantity = flt(
                quality_row.source_quantity
            )

            rate = flt(
                quality_row.rate
            )

            if quantity < 0 or rate < 0:
                frappe.throw(
                    _(
                        "Quality quantity and rate cannot "
                        "be negative."
                    )
                )

            quality_row.amount = flt(
                quantity * rate,
                2,
            )

            total_quantity += quantity
            base_amount += flt(
                quality_row.amount
            )

        row.source_quantity = flt(
            total_quantity,
            4,
        )

        row.base_amount = flt(
            base_amount,
            2,
        )

        row.final_amount = flt(
            row.base_amount
            + flt(row.extra_amount),
            2,
        )

    def calculate_totals(self):
        self.base_salary_total = flt(
            sum(
                flt(row.base_amount)
                for row in self.salary_details or []
            ),
            2,
        )

        self.extra_amount_total = flt(
            sum(
                flt(row.extra_amount)
                for row in self.salary_details or []
            ),
            2,
        )

        self.grand_total_salary = flt(
            sum(
                flt(row.final_amount)
                for row in self.salary_details or []
            ),
            2,
        )

    def validate_all_required_values(self):
        for row in self.salary_details or []:
            if row.requires_quality:
                continue

            if flt(row.source_quantity) <= 0:
                frappe.throw(
                    _(
                        "Source Quantity must be greater "
                        "than zero for Salary Format {0}."
                    ).format(
                        frappe.bold(
                            row.salary_format
                        )
                    )
                )

            if flt(row.rate) <= 0:
                frappe.throw(
                    _(
                        "Rate must be greater than zero "
                        "for Salary Format {0}."
                    ).format(
                        frappe.bold(
                            row.salary_format
                        )
                    )
                )


@frappe.whitelist()
def refresh_salary_calculation(
    salary_name,
):
    document = frappe.get_doc(
        "Worker Monthly Salary",
        salary_name,
    )

    if document.docstatus != 0:
        frappe.throw(
            "Only Draft Salary documents can be refreshed."
        )

    document.validate()
    document.save()

    return {
        "approved_attendance_hours":
            document.approved_attendance_hours,
        "base_salary_total":
            document.base_salary_total,
        "extra_amount_total":
            document.extra_amount_total,
        "grand_total_salary":
            document.grand_total_salary,
    }
