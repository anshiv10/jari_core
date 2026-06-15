import frappe
from frappe.model.document import Document
from frappe.utils import flt, today


class MeltingReceive(Document):

    def validate(self):
        self.pull_issue_details()
        self.calculate_totals()

    def on_submit(self):
        self.post_outputs_and_waste()
        frappe.db.set_value("Melting Issue", self.melting_issue, "status", "Received")

    def pull_issue_details(self):
        if not self.melting_issue:
            return

        issue = frappe.get_doc("Melting Issue", self.melting_issue)

        self.company = issue.company
        self.batch_no = issue.batch_no
        self.process_master = issue.process_master
        self.quality_code = issue.quality_code
        self.total_input_weight = issue.total_issue_weight

    def get_quality_purity(self):
        if not self.quality_code:
            return 0

        if frappe.db.has_column("Quality Master", "silver_purity_percent"):
            return flt(
                frappe.db.get_value(
                    "Quality Master",
                    self.quality_code,
                    "silver_purity_percent"
                ) or 0
            )

        return 0

    def get_product_metal_type(self, product):
        if not product:
            return ""

        if frappe.db.has_column("Product Master", "metal_type"):
            return frappe.db.get_value("Product Master", product, "metal_type") or ""

        return ""

    def calculate_totals(self):
        output_total = 0
        waste_total = 0
        quality_purity = self.get_quality_purity()

        for row in self.output_items:
            output_total += flt(row.weight)

        for row in self.waste_items:
            waste_total += flt(row.weight)
            row.approx_silver_weight = 0

            if row.waste_product:
                metal_type = self.get_product_metal_type(row.waste_product)

                if metal_type == "Silver":
                    row.approx_silver_weight = flt(row.weight) * flt(quality_purity) / 100

        self.total_output_weight = output_total
        self.total_waste_weight = waste_total

        self.loss_weight = (
            flt(self.total_input_weight)
            - flt(self.total_output_weight)
            - flt(self.total_waste_weight)
        )

        self.loss_percent = (
            flt(self.loss_weight) / flt(self.total_input_weight) * 100
            if flt(self.total_input_weight) else 0
        )

        self.waste_percent = (
            flt(self.total_waste_weight) / flt(self.total_input_weight) * 100
            if flt(self.total_input_weight) else 0
        )

        standard_loss = 0
        if self.process_master:
            standard_loss = frappe.db.get_value(
                "Loss Standard Master",
                {
                    "department": "Melting"
                },
                "standard_loss_percent"
            ) or 0

        self.loss_standard_percent = standard_loss
        self.loss_status = "Excess Loss" if flt(self.loss_percent) > flt(standard_loss) else "OK"

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

    def ledger_exists(self):
        return frappe.db.exists(
            "Inventory Ledger",
            {
                "reference_doctype": self.doctype,
                "reference_name": self.name
            }
        )

    def post_outputs_and_waste(self):
        if self.ledger_exists():
            return

        for row in self.output_items:
            if not row.product or not flt(row.weight):
                continue

            balance = self.get_last_balance(self.company, "Melting", row.product)

            frappe.get_doc({
                "doctype": "Inventory Ledger",
                "company": self.company,
                "department": "Melting",
                "product": row.product,
                "batch_number": self.batch_no,
                "in_weight": flt(row.weight),
                "out_weight": 0,
                "current_balance": flt(balance) + flt(row.weight),
                "transaction_type": "Production Output",
                "reference_doctype": self.doctype,
                "reference_name": self.name,
                "date": self.receive_date or today(),
                "remarks": "Melting output received"
            }).insert(ignore_permissions=True)

        for row in self.waste_items:
            if not row.waste_product or not flt(row.weight):
                continue

            balance = self.get_last_balance(self.company, "Melting", row.waste_product)

            frappe.get_doc({
                "doctype": "Inventory Ledger",
                "company": self.company,
                "department": "Melting",
                "product": row.waste_product,
                "batch_number": self.batch_no,
                "in_weight": flt(row.weight),
                "out_weight": 0,
                "current_balance": flt(balance) + flt(row.weight),
                "transaction_type": "Waste Generated",
                "reference_doctype": self.doctype,
                "reference_name": self.name,
                "date": self.receive_date or today(),
                "remarks": "Melting waste generated"
            }).insert(ignore_permissions=True)


@frappe.whitelist()
def get_waste_products(quality_code=None):
    filters = {
        "product_type": "Waste"
    }

    if quality_code and frappe.db.has_column("Product Master", "quality_code"):
        filters["quality_code"] = quality_code

    fields = ["name", "product_code", "product_name", "unit"]

    if frappe.db.has_column("Product Master", "metal_type"):
        fields.append("metal_type")

    return frappe.get_all(
        "Product Master",
        filters=filters,
        fields=fields
    )