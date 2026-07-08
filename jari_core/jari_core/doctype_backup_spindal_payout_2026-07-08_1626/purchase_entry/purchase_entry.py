import frappe
from frappe.model.document import Document
from frappe.utils import flt, today


class PurchaseEntry(Document):

    def validate(self):
        self.set_defaults()
        self.validate_items()
        self.calculate_item_weights()
        self.calculate_totals()

    def on_submit(self):
        self.post_to_inventory_ledger()
        frappe.db.set_value(self.doctype, self.name, "status", "Approved")

    def on_cancel(self):
        self.reverse_inventory_ledger()
        frappe.db.set_value(self.doctype, self.name, "status", "Cancelled")

    def set_defaults(self):
        if not self.department:
            self.department = "ROOT"

    def validate_items(self):
        if not self.items:
            frappe.throw("At least one Purchase Item is required.")

        for row in self.items:
            if not row.product:
                frappe.throw("Product is required in Purchase Items.")

            if flt(row.gross_weight) <= 0:
                frappe.throw(f"Gross Weight must be greater than zero for product {row.product}.")

    def calculate_item_weights(self):
        for row in self.items:
            purity = flt(row.purity_percent) if row.purity_percent is not None else 100

            row.deduction_weight = flt(row.gross_weight) * (1 - purity / 100)
            row.net_weight = flt(row.gross_weight) - flt(row.deduction_weight)

    def calculate_totals(self):
        self.total_gross_weight = 0
        self.total_deduction_weight = 0
        self.total_net_weight = 0

        for row in self.items:
            self.total_gross_weight += flt(row.gross_weight)
            self.total_deduction_weight += flt(row.deduction_weight)
            self.total_net_weight += flt(row.net_weight)

    def get_last_balance(self, product):
        return frappe.db.get_value(
            "Inventory Ledger",
            {
                "company": self.company,
                "department": self.department,
                "product": product
            },
            "current_balance",
            order_by="creation desc"
        ) or 0

    def ledger_exists(self):
        return frappe.db.exists(
            "Inventory Ledger",
            {
                "reference_doctype": self.doctype,
                "reference_name": self.name,
                "transaction_type": "Purchase Inward"
            }
        )

    def post_to_inventory_ledger(self):
        if self.ledger_exists():
            return

        for row in self.items:
            if not row.product or not flt(row.net_weight):
                continue

            last_balance = self.get_last_balance(row.product)
            new_balance = flt(last_balance) + flt(row.net_weight)

            frappe.get_doc({
                "doctype": "Inventory Ledger",
                "company": self.company,
                "department": self.department,
                "product": row.product,
                "batch_number": self.name,
                "in_weight": flt(row.net_weight),
                "out_weight": 0,
                "current_balance": new_balance,
                "transaction_type": "Purchase Inward",
                "reference_doctype": self.doctype,
                "reference_name": self.name,
                "date": self.purchase_date or today(),
                "remarks": f"Purchase from {self.vendor}"
            }).insert(ignore_permissions=True)

    def reverse_inventory_ledger(self):
        for row in self.items:
            if not row.product or not flt(row.net_weight):
                continue

            last_balance = self.get_last_balance(row.product)

            frappe.get_doc({
                "doctype": "Inventory Ledger",
                "company": self.company,
                "department": self.department,
                "product": row.product,
                "batch_number": self.name,
                "in_weight": 0,
                "out_weight": flt(row.net_weight),
                "current_balance": flt(last_balance) - flt(row.net_weight),
                "transaction_type": "Purchase Reversal",
                "reference_doctype": self.doctype,
                "reference_name": self.name,
                "date": today(),
                "remarks": f"Reversal on cancellation of {self.name}"
            }).insert(ignore_permissions=True)