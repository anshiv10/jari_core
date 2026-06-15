import frappe
from frappe.model.document import Document
from frappe.utils import flt, today


class PurchaseEntry(Document):

    def validate(self):
        self.set_defaults()
        self.calculate_net_weight()

    def on_submit(self):
        self.post_to_inventory_ledger()

    def on_update(self):
        if (
            self.docstatus == 1
            or self.get("workflow_state") in ["Submitted", "Approved"]
        ):
            self.post_to_inventory_ledger()

    def on_cancel(self):
        self.reverse_inventory_ledger()

    # -------------------------
    # DEFAULTS
    # -------------------------

    def set_defaults(self):
        if not self.department:
            self.department = "ROOT"

    # -------------------------
    # CALCULATIONS
    # -------------------------

    def calculate_net_weight(self):
        if self.gross_weight and self.purity_percent:
            self.deduction_weight = (
                flt(self.gross_weight)
                * (1 - flt(self.purity_percent) / 100)
            )

            self.net_weight = (
                flt(self.gross_weight)
                - flt(self.deduction_weight)
            )

        elif self.gross_weight:
            self.deduction_weight = 0
            self.net_weight = flt(self.gross_weight)

    # -------------------------
    # INVENTORY LEDGER
    # -------------------------

    def ledger_exists(self):
        return frappe.db.exists(
            "Inventory Ledger",
            {
                "reference_doctype": self.doctype,
                "reference_name": self.name,
                "transaction_type": "Purchase Inward"
            }
        )

    def get_last_balance(self):
        return frappe.db.get_value(
            "Inventory Ledger",
            filters={
                "company": self.company,
                "department": self.department,
                "product": self.product
            },
            fieldname="current_balance",
            order_by="creation desc"
        ) or 0

    def post_to_inventory_ledger(self):
        if self.ledger_exists():
            return

        new_balance = (
            flt(self.get_last_balance())
            + flt(self.net_weight)
        )

        frappe.get_doc({
            "doctype": "Inventory Ledger",
            "company": self.company,
            "department": self.department,
            "product": self.product,
            "batch_number": self.name,
            "in_weight": flt(self.net_weight),
            "out_weight": 0,
            "current_balance": new_balance,
            "transaction_type": "Purchase Inward",
            "reference_doctype": self.doctype,
            "reference_name": self.name,
            "date": self.purchase_date or today(),
            "remarks": f"Purchase from {self.vendor}"
        }).insert(ignore_permissions=True)

        frappe.msgprint(
            f"Purchase stock posted to {self.department}.",
            indicator="green"
        )

    # -------------------------
    # CANCELLATION REVERSAL
    # -------------------------

    def reverse_inventory_ledger(self):
        last_balance = self.get_last_balance()

        frappe.get_doc({
            "doctype": "Inventory Ledger",
            "company": self.company,
            "department": self.department,
            "product": self.product,
            "batch_number": self.name,
            "in_weight": 0,
            "out_weight": flt(self.net_weight),
            "current_balance": (
                flt(last_balance)
                - flt(self.net_weight)
            ),
            "transaction_type": "Adjustment",
            "reference_doctype": self.doctype,
            "reference_name": self.name,
            "date": today(),
            "remarks": f"Purchase reversal for {self.name}"
        }).insert(ignore_permissions=True)

        frappe.msgprint(
            "Purchase Inventory Ledger reversed.",
            indicator="orange"
        )