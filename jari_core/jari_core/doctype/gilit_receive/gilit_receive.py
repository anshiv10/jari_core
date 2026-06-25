import frappe
from frappe.model.document import Document
from frappe.utils import flt, today


class GilitReceive(Document):

    def validate(self):
        self.pull_issue_details()
        self.validate_items()
        self.calculate_totals()

    def on_submit(self):
        self.post_outputs_and_waste()
        frappe.db.set_value("Gilit Issue", self.gilit_issue, "status", "Received")

    def pull_issue_details(self):
        if not self.gilit_issue:
            return

        issue = frappe.get_doc("Gilit Issue", self.gilit_issue)

        self.company = issue.company
        self.active_batch_no = issue.gilit_batch_no
        self.process_master = issue.process_master
        self.quality_code = issue.quality_code
        self.operator = issue.operator
        self.total_input_weight = issue.total_net_weight

    def validate_items(self):
        if not self.output_items and not self.waste_items:
            frappe.throw("At least one Final Jari Product or Waste Item is required.")

        for row in self.output_items:
            if not row.product:
                frappe.throw("Final Jari Product is required.")
            if flt(row.weight) <= 0:
                frappe.throw(f"Weight must be greater than zero for product {row.product}.")

    def calculate_totals(self):
        self.total_output_weight = sum(flt(row.weight) for row in self.output_items)
        self.total_waste_weight = 0

        quality_purity = frappe.db.get_value(
            "Quality Master",
            self.quality_code,
            "silver_purity_percent"
        ) if self.quality_code else 0

        for row in self.waste_items:
            self.total_waste_weight += flt(row.weight)

            if row.waste_product:
                metal_type = frappe.db.get_value("Product Master", row.waste_product, "metal_type")
                if metal_type == "Silver":
                    row.approx_silver_weight = flt(row.weight) * flt(quality_purity) / 100
                else:
                    row.approx_silver_weight = 0

        self.loss_weight = flt(self.total_input_weight) - flt(self.total_output_weight) - flt(self.total_waste_weight)

        self.loss_percent = (
            flt(self.loss_weight) / flt(self.total_input_weight) * 100
            if flt(self.total_input_weight) else 0
        )

        self.loss_standard_percent = frappe.db.get_value(
            "Loss Standard Master",
            {"department": "Gilit"},
            "standard_loss_percent"
        ) or 0

        self.loss_status = "Excess Loss" if flt(self.loss_percent) > flt(self.loss_standard_percent) else "OK"

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

    def post_outputs_and_waste(self):
        if self.ledger_exists():
            return

        for row in self.output_items:
            if not row.product or not flt(row.weight):
                continue

            balance = self.get_last_balance(self.company, "Gilit", row.product)

            frappe.get_doc({
                "doctype": "Inventory Ledger",
                "company": self.company,
                "department": "Gilit",
                "product": row.product,
                "batch_number": self.active_batch_no,
                "in_weight": flt(row.weight),
                "out_weight": 0,
                "current_balance": flt(balance) + flt(row.weight),
                "transaction_type": "Production Output",
                "reference_doctype": self.doctype,
                "reference_name": self.name,
                "date": self.receive_date or today(),
                "remarks": "Final Jari Product received from Gilit"
            }).insert(ignore_permissions=True)

        for row in self.waste_items:
            if not row.waste_product or not flt(row.weight):
                continue

            balance = self.get_last_balance(self.company, "Gilit", row.waste_product)

            frappe.get_doc({
                "doctype": "Inventory Ledger",
                "company": self.company,
                "department": "Gilit",
                "product": row.waste_product,
                "batch_number": self.active_batch_no,
                "in_weight": flt(row.weight),
                "out_weight": 0,
                "current_balance": flt(balance) + flt(row.weight),
                "transaction_type": "Waste Generated",
                "reference_doctype": self.doctype,
                "reference_name": self.name,
                "date": self.receive_date or today(),
                "remarks": "Gilit waste generated"
            }).insert(ignore_permissions=True)
