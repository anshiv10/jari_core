import frappe
from frappe.model.document import Document
from frappe.utils import flt
from jari_core.jari_core.stock_utils import consume_issueable_stock, add_wip_transfer_in, get_product_stock_summary
from jari_core.jari_core.doctype.process_master.process_master import (
    apply_process_department_defaults,
    validate_process_party,
)


class TaniyaIssue(Document):

    def validate(self):
        self.validate_process_assignments()
        self.set_defaults()
        self.set_batch_no()
        self.validate_items()
        self.calculate_totals()

    def validate_process_assignments(self):
        validate_process_party(
            self,
            fieldname="operator",
            master_doctype="Worker Master",
            label="Operator",
            require_active=True,
        )
        validate_process_party(
            self,
            fieldname="quality_code",
            master_doctype="Quality Master",
            label="Quality",
        )

    def on_submit(self):
        self.post_inventory_transfer()
        self.set_issue_status()

    def set_defaults(self):
        if not self.from_department:
            self.from_department = "Pavtha"
        if not self.to_department:
            self.to_department = "Taniya"
        if not self.issue_type:
            self.issue_type = "New Batch"

    def set_batch_no(self):
        if self.issue_type == "New Batch":
            if not self.new_batch_no:
                frappe.throw("New Batch No is required.")
            self.batch_no = self.new_batch_no
        elif self.issue_type == "Re Issue":
            if not self.existing_batch_no:
                frappe.throw("Existing Batch No is required for Re Issue.")
            self.batch_no = self.existing_batch_no

    def set_issue_status(self):
        previous_issued = frappe.db.count(
            "Taniya Issue",
            {"batch_no": self.batch_no, "docstatus": 1, "name": ["!=", self.name]}
        )
        status = "Re Issue" if previous_issued or self.issue_type == "Re Issue" else "Issued"
        frappe.db.set_value(self.doctype, self.name, "status", status)

    def validate_items(self):
        if not self.issue_items:
            frappe.throw("At least one issue item is required.")

        for row in self.issue_items:
            if not row.product:
                frappe.throw("Product is required in issue item.")
            if flt(row.weight) <= 0:
                frappe.throw(f"Weight must be greater than zero for product {row.product}.")

    def calculate_totals(self):
        total = 0
        quality_purity = frappe.db.get_value(
            "Quality Master", self.quality_code, "silver_purity_percent"
        ) if self.quality_code else 0

        for row in self.issue_items:
            total += flt(row.weight)

            if row.product:
                metal_type = frappe.db.get_value("Product Master", row.product, "metal_type")
                row.silver_weight = flt(row.weight) * flt(quality_purity) / 100 if metal_type == "Silver" else 0

        self.total_issue_weight = total

    def ledger_exists(self):
        return frappe.db.exists(
            "Inventory Ledger",
            {"reference_doctype": self.doctype, "reference_name": self.name}
        )

    def post_inventory_transfer(self):
        if self.ledger_exists():
            return

        for row in self.issue_items:
            product = row.product
            weight = flt(row.weight)

            consume_issueable_stock(
                doc=self,
                product=product,
                required_qty=weight,
                batch_no=self.batch_no,
                posting_date=self.issue_date,
                preferred_department=self.from_department,
                remarks="Taniya material issued from issueable stock"
            )

            add_wip_transfer_in(
                doc=self,
                department=self.to_department,
                product=product,
                qty=weight,
                batch_no=self.batch_no,
                posting_date=self.issue_date,
                remarks="Taniya material inward as WIP"
            )
