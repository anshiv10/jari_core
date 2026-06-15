import frappe
from frappe.model.document import Document
from frappe.utils import flt, cint


class SpindalPetiEntry(Document):

    def validate(self):
        self.pull_spindal_issue_details()
        self.calculate_net_weight()
        self.set_remaining_bobbin()
        self.validate_weights()

    def on_submit(self):
        if flt(self.gross_weight) <= 0:
            frappe.throw("Gross Weight is required before submitting Peti Receive.")

        if flt(self.net_weight) <= 0:
            frappe.throw("Net Weight must be greater than zero before submitting.")

        if cint(self.bobbin_count) <= 0:
            frappe.throw("Bobbin Count must be greater than zero.")

        self.status = "Received"

    def pull_spindal_issue_details(self):
        if not self.spindal_issue:
            return

        issue = frappe.get_doc("Spindal Issue", self.spindal_issue)

        self.company = issue.company
        self.batch_no = issue.active_batch_no
        self.quality_code = issue.quality_code

        if hasattr(self, "operator") and not self.operator:
            self.operator = issue.operator

    def calculate_net_weight(self):
        if flt(self.gross_weight) > 0:
            self.net_weight = flt(self.gross_weight) - flt(self.baad_weight)
        else:
            self.net_weight = 0

    def set_remaining_bobbin(self):
        if self.is_new():
            self.remaining_bobbin = cint(self.bobbin_count)

    def validate_weights(self):
        if flt(self.baad_weight) < 0:
            frappe.throw("Baad Weight cannot be negative.")

        if flt(self.gross_weight) > 0 and flt(self.net_weight) <= 0:
            frappe.throw("Net Weight must be greater than zero.")