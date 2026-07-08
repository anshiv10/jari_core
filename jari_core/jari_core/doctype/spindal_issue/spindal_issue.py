import frappe
from frappe.model.document import Document
from frappe.utils import flt
from jari_core.jari_core.stock_utils import consume_issueable_stock, add_wip_transfer_in, get_product_stock_summary


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
            {"active_batch_no": self.active_batch_no, "docstatus": 1, "name": ["!=", self.name]}
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

    def ledger_exists(self):
        return frappe.db.exists(
            "Inventory Ledger",
            {"reference_doctype": self.doctype, "reference_name": self.name}
        )

    def post_inventory_transfer(self):
        if self.ledger_exists():
            return

        for row in self.get_issue_items():
            product = row.product
            weight = self.get_row_weight(row)

            consume_issueable_stock(
                doc=self,
                product=product,
                required_qty=weight,
                batch_no=self.active_batch_no,
                posting_date=self.issue_date,
                preferred_department=self.from_department,
                remarks="Spindal material issued from issueable stock"
            )

            add_wip_transfer_in(
                doc=self,
                department=self.to_department,
                product=product,
                qty=weight,
                batch_no=self.active_batch_no,
                posting_date=self.issue_date,
                remarks="Spindal material inward as WIP"
            )
