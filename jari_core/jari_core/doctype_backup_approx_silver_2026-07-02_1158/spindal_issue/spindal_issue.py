import frappe
from frappe.model.document import Document
from frappe.utils import flt, today


class SpindalIssue(Document):

    def validate(self):
        self.set_defaults()
        self.set_active_batch_no()
        self.validate_issue_items()
        self.calculate_totals()

    def on_submit(self):
        self.post_inventory_transfer()
        self.set_issue_status()

    def set_defaults(self):
        if not self.from_department:
            self.from_department = "Taniya"

        if not self.to_department:
            self.to_department = "Spindal"

        if not self.issue_type:
            self.issue_type = "New Batch"

        if self.is_active_batch is None:
            self.is_active_batch = 1

    def set_active_batch_no(self):
        if self.issue_type == "New Batch":
            if not self.new_batch_no:
                frappe.throw("New Batch No is required.")
            self.active_batch_no = self.new_batch_no

        elif self.issue_type == "Re Issue":
            if not self.existing_batch_no:
                frappe.throw("Existing Batch No is required for Re Issue.")
            self.active_batch_no = self.existing_batch_no

        if not self.active_batch_no:
            frappe.throw("Active Batch No is required.")

    def set_issue_status(self):
        previous_issued = frappe.db.count(
            "Spindal Issue",
            {
                "active_batch_no": self.active_batch_no,
                "docstatus": 1,
                "name": ["!=", self.name]
            }
        )

        status = "Re Issue" if previous_issued or self.issue_type == "Re Issue" else "Issued"
        frappe.db.set_value(self.doctype, self.name, "status", status)

    def get_issue_items(self):
        return self.issue_items or []

    def get_row_weight(self, row):
        return flt(row.weight)

    def validate_issue_items(self):
        items = self.get_issue_items()

        if not items:
            frappe.throw("At least one Issue Product Detail row is required.")

        for row in items:
            if not row.product:
                frappe.throw("Product is required in Issue Product Detail.")

            if self.get_row_weight(row) <= 0:
                frappe.throw(f"Weight must be greater than zero for product {row.product}.")

    def calculate_totals(self):
        self.total_issue_weight = sum(self.get_row_weight(row) for row in self.get_issue_items())

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

    def post_inventory_transfer(self):
        if self.ledger_exists():
            return

        for row in self.get_issue_items():
            product = row.product
            weight = self.get_row_weight(row)

            if not product or not weight:
                continue

            source_balance = self.get_last_balance(self.company, self.from_department, product)

            if weight > flt(source_balance):
                frappe.throw(
                    f"Insufficient stock for {product}. "
                    f"Available: {source_balance} KG, Requested: {weight} KG"
                )

            frappe.get_doc({
                "doctype": "Inventory Ledger",
                "company": self.company,
                "department": self.from_department,
                "product": product,
                "batch_number": self.active_batch_no,
                "in_weight": 0,
                "out_weight": weight,
                "current_balance": flt(source_balance) - weight,
                "transaction_type": "Production Input",
                "reference_doctype": self.doctype,
                "reference_name": self.name,
                "date": self.issue_date or today(),
                "remarks": "Spindal material issued"
            }).insert(ignore_permissions=True)

            target_balance = self.get_last_balance(self.company, self.to_department, product)

            frappe.get_doc({
                "doctype": "Inventory Ledger",
                "company": self.company,
                "department": self.to_department,
                "product": product,
                "batch_number": self.active_batch_no,
                "in_weight": weight,
                "out_weight": 0,
                "current_balance": flt(target_balance) + weight,
                "transaction_type": "Stock Transfer In",
                "reference_doctype": self.doctype,
                "reference_name": self.name,
                "date": self.issue_date or today(),
                "remarks": "Spindal material received in department"
            }).insert(ignore_permissions=True)


@frappe.whitelist()
def get_product_stock_summary(product, company=None):
    if not product:
        return ""

    filters = {"product": product}

    if company:
        filters["company"] = company

    departments = frappe.get_all(
        "Inventory Ledger",
        filters=filters,
        fields=["department"],
        group_by="department"
    )

    lines = []

    for d in departments:
        query_filters = {
            "product": product,
            "department": d.department
        }

        if company:
            query_filters["company"] = company

        bal = frappe.db.get_value(
            "Inventory Ledger",
            query_filters,
            "current_balance",
            order_by="creation desc"
        ) or 0

        if flt(bal) != 0:
            lines.append(f"{d.department} - {bal} KG")

    return "\n".join(lines) if lines else "No stock available"