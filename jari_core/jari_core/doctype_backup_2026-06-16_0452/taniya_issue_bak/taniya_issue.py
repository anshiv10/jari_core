import frappe
from frappe.model.document import Document
from frappe.utils import flt, today


class TaniyaIssue(Document):

    def validate(self):
        self.set_defaults()
        self.validate_items()
        self.calculate_totals()

    def on_submit(self):
        self.post_inventory_transfer()
        frappe.db.set_value(self.doctype, self.name, "status", "Issued")

    def set_defaults(self):
        if not self.from_department:
            self.from_department = "Pavtha"
        if not self.to_department:
            self.to_department = "Taniya"

    def validate_items(self):
        if not self.issue_items:
            frappe.throw("At least one issue item is required.")

        for row in self.issue_items:
            if not row.product:
                frappe.throw("Product is required in issue item.")
            if flt(row.weight) <= 0:
                frappe.throw(f"Weight must be greater than zero for product {row.product}.")

    def calculate_totals(self):
        total = 0
        quality_purity = frappe.db.get_value(
            "Quality Master",
            self.quality_code,
            "silver_purity_percent"
        ) if self.quality_code else 0

        for row in self.issue_items:
            total += flt(row.weight)

            if row.product:
                metal_type = frappe.db.get_value("Product Master", row.product, "metal_type")
                if metal_type == "Silver":
                    row.silver_weight = flt(row.weight) * flt(quality_purity) / 100

        self.total_issue_weight = total

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
        return frappe.db.exists("Inventory Ledger", {
            "reference_doctype": self.doctype,
            "reference_name": self.name
        })

    def post_inventory_transfer(self):
        if self.ledger_exists():
            return

        for row in self.issue_items:
            source_balance = self.get_last_balance(self.company, self.from_department, row.product)

            if flt(row.weight) > flt(source_balance):
                frappe.throw(
                    f"Insufficient stock for {row.product}. Available: {source_balance} KG, Requested: {row.weight} KG"
                )

            frappe.get_doc({
                "doctype": "Inventory Ledger",
                "company": self.company,
                "department": self.from_department,
                "product": row.product,
                "batch_number": self.batch_no,
                "in_weight": 0,
                "out_weight": flt(row.weight),
                "current_balance": flt(source_balance) - flt(row.weight),
                "transaction_type": "Production Input",
                "reference_doctype": self.doctype,
                "reference_name": self.name,
                "date": self.issue_date or today(),
                "remarks": "Taniya material issued"
            }).insert(ignore_permissions=True)

            target_balance = self.get_last_balance(self.company, self.to_department, row.product)

            frappe.get_doc({
                "doctype": "Inventory Ledger",
                "company": self.company,
                "department": self.to_department,
                "product": row.product,
                "batch_number": self.batch_no,
                "in_weight": flt(row.weight),
                "out_weight": 0,
                "current_balance": flt(target_balance) + flt(row.weight),
                "transaction_type": "Stock Transfer In",
                "reference_doctype": self.doctype,
                "reference_name": self.name,
                "date": self.issue_date or today(),
                "remarks": "Taniya material inward"
            }).insert(ignore_permissions=True)
