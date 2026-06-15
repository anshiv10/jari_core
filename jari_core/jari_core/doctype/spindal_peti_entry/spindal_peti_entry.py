import frappe
from frappe.model.document import Document
from frappe.utils import flt, today


class SpindalPetiEntry(Document):

    def validate(self):
        self.pull_spindal_issue_details()
        self.calculate_net_weight()

    def on_submit(self):
        self.status = "Received"

    def pull_spindal_issue_details(self):
        if not self.spindal_issue:
            return

        issue = frappe.get_doc("Spindal Issue", self.spindal_issue)

        self.company = issue.company
        self.batch_no = issue.batch_no
        self.quality_code = issue.quality_code

    def calculate_net_weight(self):
        self.net_weight = flt(self.gross_weight) - flt(self.baad_weight)

        if self.net_weight < 0:
            frappe.throw("Net Weight cannot be negative.")
