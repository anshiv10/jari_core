import frappe
from frappe.model.document import Document


class WorkerSalaryFormat(Document):

    def validate(self):
        self.validate_rates()

    def validate_rates(self):
        seen_qualities = set()

        for row in self.rate_items or []:
            if row.rate <= 0:
                frappe.throw(
                    f"Rate must be greater than zero "
                    f"in row #{row.idx}."
                )

            quality_key = row.quality_code or "__DEFAULT__"

            if quality_key in seen_qualities:
                frappe.throw(
                    f"Duplicate rate row for Quality "
                    f"{row.quality_code or 'Default'}."
                )

            seen_qualities.add(quality_key)

        if self.requires_quality:
            for row in self.rate_items or []:
                if not row.quality_code:
                    frappe.throw(
                        "Quality is required in every Rate row "
                        "when Requires Quality is enabled."
                    )
