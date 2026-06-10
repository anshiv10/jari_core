import frappe
from frappe.model.document import Document
from frappe.utils import flt, today


class StockTransfer(Document):

    def validate(self):
        self.validate_available_stock()

    def validate_available_stock(self):
        if not self.from_company or not self.from_department or not self.product:
            return

        balance = frappe.db.get_value(
            "Inventory Ledger",
            filters={
                "company": self.from_company,
                "department": self.from_department,
                "product": self.product
            },
            fieldname="current_balance",
            order_by="creation desc"
        ) or 0

        if flt(self.weight) > flt(balance):
            frappe.throw(
                f"Insufficient stock in {self.from_department}. "
                f"Available: {balance} KG — Requested: {self.weight} KG",
                title="Stock Validation Failed"
            )

    def on_submit(self):
        self.post_out_entry()
        self.post_in_entry()
        frappe.msgprint(
            f"Stock transfer posted — {self.weight} KG moved from "
            f"{self.from_department} to {self.to_department}",
            title="Transfer Posted",
            indicator="green"
        )

    def post_out_entry(self):
        last_balance = frappe.db.get_value(
            "Inventory Ledger",
            filters={
                "company": self.from_company,
                "department": self.from_department,
                "product": self.product
            },
            fieldname="current_balance",
            order_by="creation desc"
        ) or 0

        new_balance = flt(last_balance) - flt(self.weight)

        frappe.get_doc({
            "doctype": "Inventory Ledger",
            "company": self.from_company,
            "department": self.from_department,
            "product": self.product,
            "batch_number": self.batch_number or "",
            "in_weight": 0,
            "out_weight": flt(self.weight),
            "current_balance": new_balance,
            "transaction_type": "Stock Transfer Out",
            "reference_doctype": "Stock Transfer",
            "reference_name": self.name,
            "date": self.transfer_date or today(),
            "remarks": f"Transfer out to {self.to_department}"
        }).insert(ignore_permissions=True)

    def post_in_entry(self):
        last_balance = frappe.db.get_value(
            "Inventory Ledger",
            filters={
                "company": self.to_company,
                "department": self.to_department,
                "product": self.product
            },
            fieldname="current_balance",
            order_by="creation desc"
        ) or 0

        new_balance = flt(last_balance) + flt(self.weight)

        frappe.get_doc({
            "doctype": "Inventory Ledger",
            "company": self.to_company,
            "department": self.to_department,
            "product": self.product,
            "batch_number": self.batch_number or "",
            "in_weight": flt(self.weight),
            "out_weight": 0,
            "current_balance": new_balance,
            "transaction_type": "Stock Transfer In",
            "reference_doctype": "Stock Transfer",
            "reference_name": self.name,
            "date": self.transfer_date or today(),
            "remarks": f"Transfer in from {self.from_department}"
        }).insert(ignore_permissions=True)

        frappe.db.commit()

    def on_cancel(self):
        self.reverse_transfer()

    def reverse_transfer(self):
        # Reverse OUT entry — add back to source
        last_from = frappe.db.get_value(
            "Inventory Ledger",
            filters={
                "company": self.from_company,
                "department": self.from_department,
                "product": self.product
            },
            fieldname="current_balance",
            order_by="creation desc"
        ) or 0

        frappe.get_doc({
            "doctype": "Inventory Ledger",
            "company": self.from_company,
            "department": self.from_department,
            "product": self.product,
            "in_weight": flt(self.weight),
            "out_weight": 0,
            "current_balance": flt(last_from) + flt(self.weight),
            "transaction_type": "Adjustment",
            "reference_doctype": "Stock Transfer",
            "reference_name": self.name,
            "date": today(),
            "remarks": f"Reversal of transfer {self.name}"
        }).insert(ignore_permissions=True)

        # Reverse IN entry — deduct from destination
        last_to = frappe.db.get_value(
            "Inventory Ledger",
            filters={
                "company": self.to_company,
                "department": self.to_department,
                "product": self.product
            },
            fieldname="current_balance",
            order_by="creation desc"
        ) or 0

        frappe.get_doc({
            "doctype": "Inventory Ledger",
            "company": self.to_company,
            "department": self.to_department,
            "product": self.product,
            "in_weight": 0,
            "out_weight": flt(self.weight),
            "current_balance": flt(last_to) - flt(self.weight),
            "transaction_type": "Adjustment",
            "reference_doctype": "Stock Transfer",
            "reference_name": self.name,
            "date": today(),
            "remarks": f"Reversal of transfer {self.name}"
        }).insert(ignore_permissions=True)

        frappe.db.commit()
