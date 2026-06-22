import frappe
from frappe.model.document import Document
from frappe.utils import flt, cint


class SpindalPetiEntry(Document):

    def validate(self):
        self.pull_spindal_issue_details()
        self.calculate_net_weight()
        self.set_bobbin_balance()
        self.validate_weights()

    def on_submit(self):
        self.db_set("status", "Received")

    def on_cancel(self):
        self.db_set("status", "Cancelled")

    def pull_spindal_issue_details(self):
        if not self.spindal_issue:
            return

        issue = frappe.get_doc("Spindal Issue", self.spindal_issue)

        if hasattr(issue, "company"):
            self.company = issue.company

        if hasattr(issue, "active_batch_no"):
            self.batch_no = issue.active_batch_no
        elif hasattr(issue, "batch_no"):
            self.batch_no = issue.batch_no

        if hasattr(issue, "quality_code"):
            if hasattr(self, "quality_code"):
                self.quality_code = issue.quality_code
            if hasattr(self, "quality"):
                self.quality = issue.quality_code

    def calculate_net_weight(self):
        self.net_weight = flt(self.gross_weight) - flt(self.baad_weight)

    def set_bobbin_balance(self):
        if cint(self.bobbin_count) and not cint(self.remaining_bobbin):
            self.remaining_bobbin = cint(self.bobbin_count)

    def validate_weights(self):
        if flt(self.gross_weight) <= 0:
            frappe.throw("Gross Weight must be greater than zero.")

        if flt(self.baad_weight) < 0:
            frappe.throw("Baad Weight cannot be negative.")

        if flt(self.net_weight) <= 0:
            frappe.throw("Net Weight must be greater than zero.")

        if cint(self.bobbin_count) < 0:
            frappe.throw("Bobbin Count cannot be negative.")

        if cint(self.remaining_bobbin) < 0:
            frappe.throw("Remaining Bobbin cannot be negative.")
