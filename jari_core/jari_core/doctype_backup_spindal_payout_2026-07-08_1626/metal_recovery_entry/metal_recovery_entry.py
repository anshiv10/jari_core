import frappe
from frappe.model.document import Document
from frappe.utils import flt, today


class MetalRecoveryEntry(Document):

    def validate(self):
        self.calculate_loss()
        self.validate_available_stock()

    def calculate_loss(self):
        self.loss_weight = flt(self.input_weight) - flt(self.recovered_weight)
        self.loss_percent = (flt(self.loss_weight) / flt(self.input_weight) * 100) if flt(self.input_weight) else 0

    def get_last_balance(self, company, department, product):
        return frappe.db.get_value(
            "Inventory Ledger",
            filters={
                "company": company,
                "department": department,
                "product": product
            },
            fieldname="current_balance",
            order_by="creation desc"
        ) or 0

    def validate_available_stock(self):
        balance = self.get_last_balance(self.company, self.source_department, self.input_product)

        if flt(self.input_weight) > flt(balance):
            frappe.throw(
                f"Insufficient stock for recovery. Available: {balance} KG — Requested: {self.input_weight} KG",
                title="Recovery Stock Validation Failed"
            )

    def on_submit(self):
        self.post_input_consumed()
        self.post_recovered_output()
        frappe.msgprint("Metal Recovery posted successfully.", indicator="green")

    def post_input_consumed(self):
        last_balance = self.get_last_balance(self.company, self.source_department, self.input_product)

        frappe.get_doc({
            "doctype": "Inventory Ledger",
            "company": self.company,
            "department": self.source_department,
            "product": self.input_product,
            "batch_number": "",
            "in_weight": 0,
            "out_weight": flt(self.input_weight),
            "current_balance": flt(last_balance) - flt(self.input_weight),
            "transaction_type": "Recovery",
            "reference_doctype": "Metal Recovery Entry",
            "reference_name": self.name,
            "date": self.recovery_date or today(),
            "remarks": f"{self.metal_type} recovery input consumed"
        }).insert(ignore_permissions=True)

    def post_recovered_output(self):
        last_balance = self.get_last_balance(self.company, self.target_department, self.output_product)

        frappe.get_doc({
            "doctype": "Inventory Ledger",
            "company": self.company,
            "department": self.target_department,
            "product": self.output_product,
            "batch_number": "",
            "in_weight": flt(self.recovered_weight),
            "out_weight": 0,
            "current_balance": flt(last_balance) + flt(self.recovered_weight),
            "transaction_type": "Recovery",
            "reference_doctype": "Metal Recovery Entry",
            "reference_name": self.name,
            "date": self.recovery_date or today(),
            "remarks": f"{self.metal_type} recovered output"
        }).insert(ignore_permissions=True)

    def on_cancel(self):
        self.reverse_recovery()

    def reverse_recovery(self):
        source_balance = self.get_last_balance(self.company, self.source_department, self.input_product)

        frappe.get_doc({
            "doctype": "Inventory Ledger",
            "company": self.company,
            "department": self.source_department,
            "product": self.input_product,
            "in_weight": flt(self.input_weight),
            "out_weight": 0,
            "current_balance": flt(source_balance) + flt(self.input_weight),
            "transaction_type": "Adjustment",
            "reference_doctype": "Metal Recovery Entry",
            "reference_name": self.name,
            "date": today(),
            "remarks": f"Reversal of recovery {self.name}"
        }).insert(ignore_permissions=True)

        target_balance = self.get_last_balance(self.company, self.target_department, self.output_product)

        frappe.get_doc({
            "doctype": "Inventory Ledger",
            "company": self.company,
            "department": self.target_department,
            "product": self.output_product,
            "in_weight": 0,
            "out_weight": flt(self.recovered_weight),
            "current_balance": flt(target_balance) - flt(self.recovered_weight),
            "transaction_type": "Adjustment",
            "reference_doctype": "Metal Recovery Entry",
            "reference_name": self.name,
            "date": today(),
            "remarks": f"Reversal of recovery {self.name}"
        }).insert(ignore_permissions=True)