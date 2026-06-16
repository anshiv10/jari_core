import frappe
from frappe.model.document import Document
from frappe.utils import flt, today


class SpindalReceive(Document):

    def validate(self):
        self.pull_issue_details()
        self.pull_peti_kasab_weight()
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

        self.total_input_weight = (
            flt(getattr(issue, "total_issue_weight", 0))
            or flt(getattr(issue, "total_net_weight", 0))
        )

    def get_total_kasab_from_peti(self):
        if not self.spindal_issue:
            return 0

        total = frappe.db.sql(
            """
            SELECT SUM(net_weight)
            FROM `tabSpindal Peti Entry`
            WHERE spindal_issue = %s
              AND docstatus = 1
            """,
            self.spindal_issue
        )[0][0]

        return flt(total or 0)

    def pull_peti_kasab_weight(self):
        total_kasab = self.get_total_kasab_from_peti()

        if not total_kasab:
            return

        if hasattr(self, "total_received_weight"):
            self.total_received_weight = total_kasab

        if hasattr(self, "total_output_weight"):
            self.total_output_weight = total_kasab

        if hasattr(self, "received_peti_items"):
            self.set("received_peti_items", [])

            row = self.append("received_peti_items", {})
            row.peti_no = "AUTO"
            row.product = self.get_kasab_product()
            row.uom = "KG"
            row.net_weight = total_kasab

        elif hasattr(self, "output_items"):
            self.set("output_items", [])

            row = self.append("output_items", {})
            row.product = self.get_kasab_product()
            row.uom = "KG"
            row.weight = total_kasab

    def get_kasab_product(self):
        if frappe.db.exists("Product Master", "KASAB"):
            return "KASAB"

        product = frappe.db.get_value(
            "Product Master",
            {"product_name": "KASAB"},
            "name"
        )

        if product:
            return product

        frappe.throw("KASAB product not found in Product Master.")

    def validate_items(self):
        has_output = False

        if hasattr(self, "received_peti_items") and self.received_peti_items:
            has_output = True

        if hasattr(self, "output_items") and self.output_items:
            has_output = True

        if not has_output and not self.waste_items:
            frappe.throw("At least one output item or waste item is required.")

    def get_output_weight_total(self):
        if hasattr(self, "received_peti_items") and self.received_peti_items:
            return sum(flt(row.net_weight) for row in self.received_peti_items)

        if hasattr(self, "output_items") and self.output_items:
            return sum(flt(row.weight) for row in self.output_items)

        return 0

    def calculate_totals(self):
        received_total = self.get_output_weight_total()
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
                else:
                    row.approx_silver_weight = 0

        if hasattr(self, "total_received_weight"):
            self.total_received_weight = received_total

        if hasattr(self, "total_output_weight"):
            self.total_output_weight = received_total

        self.total_waste_weight = waste_total

        self.loss_weight = (
            flt(self.total_input_weight)
            - flt(received_total)
            - flt(self.total_waste_weight)
        )

        self.loss_percent = (
            flt(self.loss_weight) / flt(self.total_input_weight) * 100
            if flt(self.total_input_weight) else 0
        )

        self.loss_standard_percent = frappe.db.get_value(
            "Loss Standard Master",
            {"department": "Spindal"},
            "standard_loss_percent"
        ) or 0

        self.loss_status = (
            "Excess Loss"
            if flt(self.loss_percent) > flt(self.loss_standard_percent)
            else "OK"
        )

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

    def post_outputs_and_waste(self):
        if self.ledger_exists():
            return

        kasab_product = self.get_kasab_product()
        received_weight = self.get_output_weight_total()

        if received_weight:
            balance = self.get_last_balance(self.company, "Spindal", kasab_product)

            frappe.get_doc({
                "doctype": "Inventory Ledger",
                "company": self.company,
                "department": "Spindal",
                "product": kasab_product,
                "batch_number": self.active_batch_no,
                "in_weight": flt(received_weight),
                "out_weight": 0,
                "current_balance": flt(balance) + flt(received_weight),
                "transaction_type": "Production Output",
                "reference_doctype": self.doctype,
                "reference_name": self.name,
                "date": self.receive_date or today(),
                "remarks": "Spindal KASAB received from PETI entries"
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