import frappe
from frappe.model.document import Document
from frappe.utils import flt, today


class SpindalReceive(Document):

    def validate(self):
        self.pull_issue_details()
        self.validate_items()
        self.calculate_totals()

    def on_submit(self):
        self.post_outputs_and_waste()
        frappe.db.set_value("Spindal Issue", self.spindal_issue, "status", "Partially Received")

    def pull_issue_details(self):
        if not self.spindal_issue:
            return

        issue = frappe.get_doc("Spindal Issue", self.spindal_issue)
        self.company = issue.company
        self.active_batch_no = issue.active_batch_no
        self.process_master = issue.process_master
        self.quality_code = issue.quality_code
        self.operator = issue.operator
        self.total_input_weight = issue.total_net_weight

    def validate_items(self):
        if not self.received_peti_items and not self.waste_items:
            frappe.throw("At least one received peti item or waste item is required.")

        if self.received_peti_items:
            issue = frappe.get_doc("Spindal Issue", self.spindal_issue)
            issued_peti = {row.peti_no for row in issue.peti_items}

            seen = set()
            for row in self.received_peti_items:
                if not row.peti_no:
                    frappe.throw("Peti No is required in received peti items.")
                if row.peti_no in seen:
                    frappe.throw(f"Duplicate received Peti No found: {row.peti_no}")
                seen.add(row.peti_no)

                if row.peti_no not in issued_peti:
                    frappe.throw(f"Peti No {row.peti_no} was not issued in Spindal Issue {self.spindal_issue}.")

                if not row.product:
                    frappe.throw(f"Product is required for Peti {row.peti_no}.")
                if flt(row.net_weight) <= 0:
                    frappe.throw(f"Net Weight must be greater than zero for Peti {row.peti_no}.")

    def calculate_totals(self):
        self.total_received_weight = sum(flt(row.net_weight) for row in self.received_peti_items)
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

        self.loss_weight = flt(self.total_input_weight) - flt(self.total_received_weight) - flt(self.total_waste_weight)

        self.loss_percent = (
            flt(self.loss_weight) / flt(self.total_input_weight) * 100
            if flt(self.total_input_weight) else 0
        )

        self.loss_standard_percent = frappe.db.get_value(
            "Loss Standard Master",
            {"department": "Spindal"},
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

        for row in self.received_peti_items:
            if not row.product or not flt(row.net_weight):
                continue

            balance = self.get_last_balance(self.company, "Spindal", row.product)

            frappe.get_doc({
                "doctype": "Inventory Ledger",
                "company": self.company,
                "department": "Spindal",
                "product": row.product,
                "batch_number": self.active_batch_no,
                "in_weight": flt(row.net_weight),
                "out_weight": 0,
                "current_balance": flt(balance) + flt(row.net_weight),
                "transaction_type": "Production Output",
                "reference_doctype": self.doctype,
                "reference_name": self.name,
                "date": self.receive_date or today(),
                "remarks": f"Spindal received Peti {row.peti_no}"
            }).insert(ignore_permissions=True)

        for row in self.waste_items:
            if not row.waste_product or not flt(row.weight):
                continue

            balance = self.get_last_balance(self.company, "Spindal", row.waste_product)

            frappe.get_doc({
                "doctype": "Inventory Ledger",
                "company": self.company,
                "department": "Spindal",
                "product": row.waste_product,
                "batch_number": self.active_batch_no,
                "in_weight": flt(row.weight),
                "out_weight": 0,
                "current_balance": flt(balance) + flt(row.weight),
                "transaction_type": "Waste Generated",
                "reference_doctype": self.doctype,
                "reference_name": self.name,
                "date": self.receive_date or today(),
                "remarks": "Spindal waste generated"
            }).insert(ignore_permissions=True)
