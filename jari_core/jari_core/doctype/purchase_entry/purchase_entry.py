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
        elif self.gross_weight:
            self.deduction_weight = 0
            self.net_weight = flt(self.gross_weight)

    def on_submit(self):
        self.post_to_inventory_ledger()

    def post_to_inventory_ledger(self):
        # Get last balance for this company + product
        last_balance = frappe.db.get_value(
            "Inventory Ledger",
            filters={
                "company": self.company,
                "department": "Raw Material Store",
                "product": self.product
            },
            fieldname="current_balance",
            order_by="creation desc"
        )

        new_balance = flt(last_balance or 0) + flt(self.net_weight)

        ledger = frappe.get_doc({
            "doctype": "Inventory Ledger",
            "company": self.company,
            "department": "Raw Material Store",
            "product": self.product,
            "batch_number": "",
            "in_weight": flt(self.net_weight),
            "out_weight": 0,
            "current_balance": new_balance,
            "transaction_type": "Purchase Inward",
            "reference_doctype": "Purchase Entry",
            "reference_name": self.name,
            "date": self.purchase_date or today(),
            "remarks": f"Purchase from {self.vendor}"
        })
        ledger.insert(ignore_permissions=True)
        frappe.db.commit()

        frappe.msgprint(
            f"Inventory updated — Silver stock increased by {self.net_weight} KG. "
            f"New balance: {new_balance} KG",
            title="Inventory Posted",
            indicator="green"
        )

    def on_cancel(self):
        self.reverse_inventory_ledger()

    def reverse_inventory_ledger(self):
        # Get last balance
        last_balance = frappe.db.get_value(
            "Inventory Ledger",
            filters={
                "company": self.company,
                "department": "Raw Material Store",
                "product": self.product
            },
            fieldname="current_balance",
            order_by="creation desc"
        )

        new_balance = flt(last_balance or 0) - flt(self.net_weight)

        ledger = frappe.get_doc({
            "doctype": "Inventory Ledger",
            "company": self.company,
            "department": "Raw Material Store",
            "product": self.product,
            "batch_number": "",
            "in_weight": 0,
            "out_weight": flt(self.net_weight),
            "current_balance": new_balance,
            "transaction_type": "Adjustment",
            "reference_doctype": "Purchase Entry",
            "reference_name": self.name,
            "date": today(),
            "remarks": f"Reversal on cancellation of {self.name}"
        })
        ledger.insert(ignore_permissions=True)
        frappe.db.commit()
