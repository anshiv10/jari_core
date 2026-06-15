import frappe
from frappe.model.document import Document
from frappe.utils import flt


class SpindalPetiEntry(Document):

    def validate(self):
        self.pull_spindal_issue_details()
        self.calculate_net_weight()
        self.validate_weights()

    def on_submit(self):
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
        self.net_weight = flt(self.gross_weight) - flt(self.baad_weight)

    def validate_weights(self):
        if flt(self.gross_weight) <= 0:
            frappe.throw("Gross Weight must be greater than zero.")

        if flt(self.baad_weight) < 0:
            frappe.throw("Baad Weight cannot be negative.")

        if flt(self.net_weight) <= 0:
            frappe.throw("Net Weight must be greater than zero.")