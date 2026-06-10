import frappe
from frappe.model.document import Document
from frappe.utils import flt, today

class StockTransfer(Document):

    def validate(self):
        self.validate_available_stock()

    def validate_available_stock(self):
        balance = frappe.db.get_value(
            "Inventory Ledger",
            {"company": self.from_company, "department": self.from_department, "product": self.product},
            "current_balance",
            order_by="creation desc"
        ) or 0
        if flt(self.weight) > flt(balance):
            frappe.throw(
                f"Insufficient stock. Available: {balance} KG, Requested: {self.weight} KG"
            )

    def on_submit(self):
        self.post_out_entry()
        self.post_in_entry()

    def post_out_entry(self):
        last_balance = frappe.db.get_value(
            "Inventory Ledger",
            {"company": self.from_company, "department": self.from_department, "product": self.product},
            "current_balance",
            order_by="creation desc"
        ) or 0
        doc = frappe.new_doc("Inventory Ledger")
        doc.company = self.from_company
        doc.department = self.from_department
        doc.product = self.product
        doc.batch_number = self.batch_number
        doc.in_weight = 0
        doc.out_weight = self.weight
        doc.current_balance = flt(last_balance) - flt(self.weight)
        doc.transaction_type = "Stock Transfer Out"
        doc.reference_doctype = "Stock Transfer"
        doc.reference_name = self.name
        doc.date = self.transfer_date or today()
        doc.insert(ignore_permissions=True)

    def post_in_entry(self):
        last_balance = frappe.db.get_value(
            "Inventory Ledger",
            {"company": self.to_company, "department": self.to_department, "product": self.product},
            "current_balance",
            order_by="creation desc"
        ) or 0
        doc = frappe.new_doc("Inventory Ledger")
        doc.company = self.to_company
        doc.department = self.to_department
        doc.product = self.product
        doc.batch_number = self.batch_number
        doc.in_weight = self.weight
        doc.out_weight = 0
        doc.current_balance = flt(last_balance) + flt(self.weight)
        doc.transaction_type = "Stock Transfer In"
        doc.reference_doctype = "Stock Transfer"
        doc.reference_name = self.name
        doc.date = self.transfer_date or today()
        doc.insert(ignore_permissions=True)

        frappe.db.commit()