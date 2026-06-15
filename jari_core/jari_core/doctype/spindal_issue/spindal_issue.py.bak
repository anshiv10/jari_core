import frappe
from frappe.model.document import Document
from frappe.utils import flt, today


class SpindalIssue(Document):

    def validate(self):
        self.set_defaults()
        self.validate_active_batch()
        self.validate_peti_items()
        self.calculate_totals()

    def on_submit(self):
        self.post_inventory_transfer()
        frappe.db.set_value(self.doctype, self.name, "status", "Issued")

    def set_defaults(self):
        if not self.from_department:
            self.from_department = "Taniya"
        if not self.to_department:
            self.to_department = "Spindal"
        if self.is_active_batch is None:
            self.is_active_batch = 1

    def validate_active_batch(self):
        if not self.active_batch_no:
            frappe.throw("Active Batch No is required.")

        existing = frappe.db.get_value(
            "Spindal Issue",
            {
                "active_batch_no": self.active_batch_no,
                "docstatus": 1,
                "is_active_batch": 1,
                "name": ["!=", self.name],
                "status": ["!=", "Closed"],
            },
            "name",
        )

        if existing:
            frappe.throw(
                f"Active Spindal Batch {self.active_batch_no} already exists in {existing}. "
                "Use that active batch until it is closed."
            )

    def validate_peti_items(self):
        if not self.peti_items:
            frappe.throw("At least one Peti Item is required.")

        seen = set()
        for row in self.peti_items:
            if not row.peti_no:
                frappe.throw("Peti No is required.")
            if row.peti_no in seen:
                frappe.throw(f"Duplicate Peti No found: {row.peti_no}")
            seen.add(row.peti_no)

            if not row.product:
                frappe.throw(f"Product is required for Peti {row.peti_no}.")
            if flt(row.net_weight) <= 0:
                frappe.throw(f"Net Weight must be greater than zero for Peti {row.peti_no}.")

    def calculate_totals(self):
        quality_purity = frappe.db.get_value(
            "Quality Master",
            self.quality_code,
            "silver_purity_percent"
        ) if self.quality_code else 0

        self.total_peti = len(self.peti_items or [])
        self.total_net_weight = 0
        self.total_silver_weight = 0

        for row in self.peti_items:
            self.total_net_weight += flt(row.net_weight)

            metal_type = frappe.db.get_value("Product Master", row.product, "metal_type") if row.product else None
            if metal_type == "Silver":
                row.silver_weight = flt(row.net_weight) * flt(quality_purity) / 100
            else:
                row.silver_weight = 0

            self.total_silver_weight += flt(row.silver_weight)

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

        for row in self.peti_items:
            source_balance = self.get_last_balance(self.company, self.from_department, row.product)

            if flt(row.net_weight) > flt(source_balance):
                frappe.throw(
                    f"Insufficient stock for {row.product}. "
                    f"Available: {source_balance} KG, Requested: {row.net_weight} KG"
                )

            frappe.get_doc({
                "doctype": "Inventory Ledger",
                "company": self.company,
                "department": self.from_department,
                "product": row.product,
                "batch_number": self.active_batch_no,
                "in_weight": 0,
                "out_weight": flt(row.net_weight),
                "current_balance": flt(source_balance) - flt(row.net_weight),
                "transaction_type": "Production Input",
                "reference_doctype": self.doctype,
                "reference_name": self.name,
                "date": self.issue_date or today(),
                "remarks": f"Spindal Peti {row.peti_no} issued"
            }).insert(ignore_permissions=True)

            target_balance = self.get_last_balance(self.company, self.to_department, row.product)

            frappe.get_doc({
                "doctype": "Inventory Ledger",
                "company": self.company,
                "department": self.to_department,
                "product": row.product,
                "batch_number": self.active_batch_no,
                "in_weight": flt(row.net_weight),
                "out_weight": 0,
                "current_balance": flt(target_balance) + flt(row.net_weight),
                "transaction_type": "Stock Transfer In",
                "reference_doctype": self.doctype,
                "reference_name": self.name,
                "date": self.issue_date or today(),
                "remarks": f"Spindal Peti {row.peti_no} inward"
            }).insert(ignore_permissions=True)
