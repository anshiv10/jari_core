import frappe
from frappe.model.document import Document
from frappe.utils import flt, today


class TaniyaReceive(Document):

    def validate(self):
        self.pull_issue_details()
        self.validate_items()
        self.calculate_totals()

    def on_submit(self):
        self.post_outputs_and_waste()
        frappe.db.set_value("Taniya Issue", self.taniya_issue, "status", "Partially Received")

    def pull_issue_details(self):
        if not self.taniya_issue:
            return
        issue = frappe.get_doc("Taniya Issue", self.taniya_issue)
        self.company = issue.company
        self.batch_no = issue.batch_no
        self.process_master = issue.process_master
        self.quality_code = issue.quality_code
        self.operator = issue.operator
        self.total_input_weight = issue.total_issue_weight

    def validate_items(self):
        if not self.output_items and not self.waste_items:
            frappe.throw("At least one output or waste item is required.")

    def calculate_totals(self):
        output_total = sum(flt(row.weight) for row in self.output_items)
        waste_total = sum(flt(row.weight) for row in self.waste_items)

        self.total_output_weight = output_total
        self.total_waste_weight = waste_total
        self.current_wastage_percent = waste_total / flt(self.total_input_weight) * 100 if flt(self.total_input_weight) else 0
        self.loss_weight = flt(self.total_input_weight) - output_total - waste_total
        self.loss_percent = self.loss_weight / flt(self.total_input_weight) * 100 if flt(self.total_input_weight) else 0

        self.loss_standard_percent = frappe.db.get_value(
            "Loss Standard Master", {"department": "Taniya"}, "standard_loss_percent"
        ) or 0

        self.loss_status = "Excess Loss" if flt(self.loss_percent) > flt(self.loss_standard_percent) else "OK"

    def get_last_balance(self, company, department, product):
        return frappe.db.get_value(
            "Inventory Ledger",
            {"company": company, "department": department, "product": product},
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
            balance = self.get_last_balance(self.company, "Taniya", row.product)
            frappe.get_doc({
                "doctype": "Inventory Ledger",
                "company": self.company,
                "department": "Taniya",
                "product": row.product,
                "batch_number": self.batch_no,
                "in_weight": flt(row.weight),
                "out_weight": 0,
                "current_balance": flt(balance) + flt(row.weight),
                "transaction_type": "Production Output",
                "reference_doctype": self.doctype,
                "reference_name": self.name,
                "date": self.receive_date or today(),
                "remarks": "Taniya output received"
            }).insert(ignore_permissions=True)

        for row in self.waste_items:
            if not row.waste_product or not flt(row.weight):
                continue
            balance = self.get_last_balance(self.company, "Taniya", row.waste_product)
            frappe.get_doc({
                "doctype": "Inventory Ledger",
                "company": self.company,
                "department": "Taniya",
                "product": row.waste_product,
                "batch_number": self.batch_no,
                "in_weight": flt(row.weight),
                "out_weight": 0,
                "current_balance": flt(balance) + flt(row.weight),
                "transaction_type": "Waste Generated",
                "reference_doctype": self.doctype,
                "reference_name": self.name,
                "date": self.receive_date or today(),
                "remarks": "Taniya waste generated"
            }).insert(ignore_permissions=True)
