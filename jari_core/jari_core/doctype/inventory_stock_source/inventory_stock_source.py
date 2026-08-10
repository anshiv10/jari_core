import frappe
from frappe.model.document import Document
from frappe.utils import flt


class InventoryStockSource(Document):

    def validate(self):
        self.set_source_key()
        self.validate_legacy_source()

    def set_source_key(self):
        if self.is_legacy:
            parts = [
                "LEGACY",
                self.company or "",
                self.opening_department or "",
                self.product or "",
            ]
        else:
            if not self.source_doctype:
                frappe.throw(
                    "Source Doctype is required for a normal stock source."
                )

            if not self.source_name:
                frappe.throw(
                    "Source Document is required for a normal stock source."
                )

            parts = [
                self.source_doctype or "",
                self.source_name or "",
                self.source_row or "__PARENT__",
            ]

        self.source_key = "|".join(parts)

    def validate_legacy_source(self):
        if not self.is_legacy:
            self.opening_weight = 0
            return

        if not self.opening_department:
            frappe.throw(
                "Opening Department is required for a Legacy Opening Source."
            )

        if flt(self.opening_weight) < 0:
            frappe.throw(
                "Legacy Opening Weight cannot be negative."
            )

        self.source_type = "Legacy Opening"
