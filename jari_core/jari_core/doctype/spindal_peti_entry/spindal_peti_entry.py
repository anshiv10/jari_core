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
        if not self.remaining_bobbin:
            self.db_set("remaining_bobbin", cint(self.bobbin_count))

        self.db_set("status", "Received")

    def on_cancel(self):
        consumed = cint(self.bobbin_count) - cint(self.remaining_bobbin)

        if consumed > 0:
            frappe.throw("Cannot cancel Peti because bobbins are already consumed in Gilit Issue.")

        self.db_set("status", "Cancelled")

    def pull_spindal_issue_details(self):
        if not self.spindal_issue:
            return

        issue = frappe.get_doc("Spindal Issue", self.spindal_issue)

        self.company = issue.company
        self.batch_no = issue.active_batch_no
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

        if cint(self.bobbin_count) <= 0:
            frappe.throw("Bobbin Count must be greater than zero.")

        if cint(self.remaining_bobbin) < 0:
            frappe.throw("Remaining Bobbin cannot be negative.")

        if cint(self.remaining_bobbin) > cint(self.bobbin_count):
            frappe.throw("Remaining Bobbin cannot be greater than Bobbin Count.")