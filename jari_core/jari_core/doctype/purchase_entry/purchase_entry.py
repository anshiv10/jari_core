import frappe
from frappe.model.document import Document
from frappe.utils import flt, today

class PurchaseEntry(Document):

    def validate(self):
        self.calculate_net_weight()

    def calculate_net_weight(self):
        if self.gross_weight and self.purity_percent:
            self.deduction_weight = flt(self.gross_weight) * (1 - flt(self.purity_percent) / 100)
            self.net_weight = flt(self.gross_weight) - flt(self.deduction_weight)

    def on_submit(self):
        self.post_to_inventory_ledger()

    def post_to_inventory_ledger(self):
        doc = frappe.new_doc("Inventory Ledger")
        doc.company = self.company
        doc.department = "Raw Material Store"
        doc.product = self.product
        doc.in_weight = self.net_weight
        doc.out_weight = 0
        doc.transaction_type = "Purchase Inward"
        doc.reference_doctype = "Purchase Entry"
        doc.reference_name = self.name
        doc.date = self.purchase_date or today()

        last_balance = frappe.db.get_value(
            "Inventory Ledger",
            {"company": self.company, "product": self.product},
            "current_balance",
            order_by="creation desc"
        )
        doc.current_balance = flt(last_balance or 0) + flt(self.net_weight)
        doc.insert(ignore_permissions=True)
        frappe.db.commit()

    def on_cancel(self):
        # Reverse the inventory posting
        doc = frappe.new_doc("Inventory Ledger")
        doc.company = self.company
        doc.department = "Raw Material Store"
        doc.product = self.product
        doc.in_weight = 0
        doc.out_weight = self.net_weight
        doc.transaction_type = "Adjustment"
        doc.reference_doctype = "Purchase Entry"
        doc.reference_name = self.name
        doc.date = today()
        doc.remarks = "Cancellation reversal"

        last_balance = frappe.db.get_value(
            "Inventory Ledger",
            {"company": self.company, "product": self.product},
            "current_balance",
            order_by="creation desc"
        )
        doc.current_balance = flt(last_balance or 0) - flt(self.net_weight)
        doc.insert(ignore_permissions=True)
        frappe.db.commit()