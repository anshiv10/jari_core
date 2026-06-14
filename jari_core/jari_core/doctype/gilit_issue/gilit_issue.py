import frappe
from frappe.model.document import Document
from frappe.utils import flt, today


class GilitIssue(Document):

    def validate(self):
        self.set_defaults()
        self.pull_spindal_details()
        self.validate_peti_items()
        self.calculate_totals()

    def on_submit(self):
        self.post_inventory_transfer()
        frappe.db.set_value(self.doctype, self.name, "status", "Issued")

    def set_defaults(self):
        if not self.from_department:
            self.from_department = "Spindal"
        if not self.to_department:
            self.to_department = "Gilit"

    def pull_spindal_details(self):
        if not self.spindal_issue:
            return

        sp = frappe.get_doc("Spindal Issue", self.spindal_issue)

        self.company = self.company or sp.company
        self.active_batch_no = sp.active_batch_no
        self.process_master = self.process_master or sp.process_master
        self.quality_code = self.quality_code or sp.quality_code
        self.operator = self.operator or sp.operator

        if not self.peti_items:
            for row in sp.peti_items:
                d = self.append("peti_items", {})
                d.peti_no = row.peti_no
                d.product = row.product
                d.uom = row.uom
                d.gross_weight = row.gross_weight
                d.net_weight = row.net_weight

    def validate_peti_items(self):
        if not self.peti_items:
            frappe.throw("At least one Spindal Peti row is required.")

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
        self.total_peti = len(self.peti_items or [])
        self.total_net_weight = sum(flt(row.net_weight) for row in self.peti_items)

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
                "remarks": f"Gilit Peti {row.peti_no} issued from Spindal"
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
                "remarks": f"Gilit Peti {row.peti_no} inward"
            }).insert(ignore_permissions=True)
