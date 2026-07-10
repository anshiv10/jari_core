import frappe
from frappe.model.document import Document
from frappe.utils import flt


class InventoryLedger(Document):

    def validate(self):
        self.validate_non_negative_weights()

    def validate_non_negative_weights(self):
        if flt(self.in_weight) < 0:
            frappe.throw("In Weight cannot be negative.")

        if flt(self.out_weight) < 0:
            frappe.throw("Out Weight cannot be negative.")

        if flt(self.current_balance) < 0:
            frappe.throw("Current Balance cannot be negative.")
