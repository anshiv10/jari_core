import frappe
from frappe.model.document import Document
from frappe.utils import flt, today


class SpindalPetiEntry(Document):

    def validate(self):
        self.pull_spindal_issue_details()
        self.calculate_net_weight()
        self.validate_weights()

    def on_submit(self):
        self.post_kasab_stock()
        frappe.db.set_value(self.doctype, self.name, "status", "Received")

    def on_cancel(self):
        self.cancel_kasab_stock()
        frappe.db.set_value(self.doctype, self.name, "status", "Cancelled")

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
        gross = flt(self.gross_weight)
        baad = flt(self.baad_weight)

        # If gross is available, calculate net automatically.
        # If gross is not available, allow manually entered net_weight.
        if gross > 0:
            self.net_weight = gross - baad

    def validate_weights(self):
        if flt(self.baad_weight) < 0:
            frappe.throw("Baad Weight cannot be negative.")

        if flt(self.gross_weight) < 0:
            frappe.throw("Gross Weight cannot be negative.")

        if flt(self.gross_weight) > 0 and flt(self.net_weight) < 0:
            frappe.throw("Net Weight cannot be negative.")

        # Allow submission when only Baad Weight is entered.
        # But if stock is to be posted, Net Weight must be positive.
        return

    def get_kasab_product(self):
        if frappe.db.exists("Product Master", "KASAB"):
            return "KASAB"

        product = frappe.db.get_value("Product Master", {"product_name": "KASAB"}, "name")

        if product:
            return product

        frappe.throw("KASAB product not found in Product Master.")

    def get_last_balance(self, company, department, product):
        return frappe.db.get_value(
            "Inventory Ledger",
            {
                "company": company,
                "department": department,
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
                "reference_name": self.name
            }
        )

    def post_kasab_stock(self):
        if self.ledger_exists():
            return

        if flt(self.net_weight) <= 0:
            return

        product = self.get_kasab_product()
        department = "Spindal"

        last_balance = self.get_last_balance(self.company, department, product)

        frappe.get_doc({
            "doctype": "Inventory Ledger",
            "company": self.company,
            "department": department,
            "product": product,
            "batch_number": self.batch_no,
            "in_weight": flt(self.net_weight),
            "out_weight": 0,
            "current_balance": flt(last_balance) + flt(self.net_weight),
            "transaction_type": "Spindal Peti Receive",
            "reference_doctype": self.doctype,
            "reference_name": self.name,
            "date": self.peti_date or today(),
            "remarks": "KASAB stock increased from Spindal Peti Entry"
        }).insert(ignore_permissions=True)

    def cancel_kasab_stock(self):
        product = self.get_kasab_product()
        department = "Spindal"

        if flt(self.net_weight) <= 0:
            return

        last_balance = self.get_last_balance(self.company, department, product)

        frappe.get_doc({
            "doctype": "Inventory Ledger",
            "company": self.company,
            "department": department,
            "product": product,
            "batch_number": self.batch_no,
            "in_weight": 0,
            "out_weight": flt(self.net_weight),
            "current_balance": flt(last_balance) - flt(self.net_weight),
            "transaction_type": "Spindal Peti Receive Cancel",
            "reference_doctype": self.doctype,
            "reference_name": self.name,
            "date": today(),
            "remarks": "KASAB stock reversed from cancelled Spindal Peti Entry"
        }).insert(ignore_permissions=True)
