import frappe
from frappe.model.document import Document
from frappe.utils import flt, today


class PavthaReceive(Document):

    def validate(self):
        self.pull_issue_details()
        self.validate_items()
        self.calculate_totals()
        self.calculate_payout()

    def on_submit(self):
        self.post_outputs_and_waste()
        frappe.db.set_value("Pavtha Issue", self.pavtha_issue, "status", "Received")

    def pull_issue_details(self):
        if not self.pavtha_issue:
            return

        issue = frappe.get_doc("Pavtha Issue", self.pavtha_issue)

        self.company = issue.company
        self.batch_no = issue.batch_no
        self.process_master = issue.process_master
        self.quality_code = issue.quality_code
        self.outsourcer = issue.outsourcer
        self.rate_per_kg = issue.rate_per_kg
        self.total_input_weight = issue.total_issue_weight

    def validate_items(self):
        if not self.output_items and not self.waste_items:
            frappe.throw("At least one output or waste item is required.")

    def calculate_totals(self):
        output_total = sum(flt(row.weight) for row in self.output_items)
        waste_total = 0

        quality_purity = frappe.db.get_value(
            "Quality Master",
            self.quality_code,
            "silver_purity_percent"
        ) if self.quality_code else 0

        for row in self.waste_items:
            waste_total += flt(row.weight)

            if row.waste_product:
                metal_type = frappe.db.get_value("Product Master", row.waste_product, "metal_type")
                if metal_type == "Silver":
                    row.approx_silver_weight = flt(row.weight) * flt(quality_purity) / 100

        self.total_output_weight = output_total
        self.total_waste_weight = waste_total
        self.loss_weight = flt(self.total_input_weight) - flt(self.total_output_weight) - flt(self.total_waste_weight)

        self.loss_percent = (
            flt(self.loss_weight) / flt(self.total_input_weight) * 100
            if flt(self.total_input_weight) else 0
        )

        self.loss_standard_percent = frappe.db.get_value(
            "Loss Standard Master",
            {"department": "Pavtha"},
            "standard_loss_percent"
        ) or 0

        self.loss_status = "Excess Loss" if flt(self.loss_percent) > flt(self.loss_standard_percent) else "OK"

    def calculate_payout(self):
        self.base_payout = flt(self.total_input_weight) * flt(self.rate_per_kg)
        excess_loss_percent = flt(self.loss_percent) - flt(self.loss_standard_percent)

        self.bonus_amount = 0
        self.deduction_amount = 0

        if excess_loss_percent > 0:
            excess_weight = flt(self.total_input_weight) * excess_loss_percent / 100
            self.deduction_amount = excess_weight * flt(self.rate_per_kg)

        elif excess_loss_percent < 0:
            saved_weight = flt(self.total_input_weight) * abs(excess_loss_percent) / 100
            self.bonus_amount = saved_weight * flt(self.rate_per_kg)

        self.payout_suggestion = flt(self.base_payout) + flt(self.bonus_amount) - flt(self.deduction_amount)

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

            balance = self.get_last_balance(self.company, "Pavtha", row.product)

            frappe.get_doc({
                "doctype": "Inventory Ledger",
                "company": self.company,
                "department": "Pavtha",
                "product": row.product,
                "batch_number": self.batch_no,
                "in_weight": flt(row.weight),
                "out_weight": 0,
                "current_balance": flt(balance) + flt(row.weight),
                "transaction_type": "Production Output",
                "reference_doctype": self.doctype,
                "reference_name": self.name,
                "date": self.receive_date or today(),
                "remarks": "Pavtha output received"
            }).insert(ignore_permissions=True)

        for row in self.waste_items:
            if not row.waste_product or not flt(row.weight):
                continue

            balance = self.get_last_balance(self.company, "Pavtha", row.waste_product)

            frappe.get_doc({
                "doctype": "Inventory Ledger",
                "company": self.company,
                "department": "Pavtha",
                "product": row.waste_product,
                "batch_number": self.batch_no,
                "in_weight": flt(row.weight),
                "out_weight": 0,
                "current_balance": flt(balance) + flt(row.weight),
                "transaction_type": "Waste Generated",
                "reference_doctype": self.doctype,
                "reference_name": self.name,
                "date": self.receive_date or today(),
                "remarks": "Pavtha waste generated"
            }).insert(ignore_permissions=True)
