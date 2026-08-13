import frappe
from frappe.model.document import Document
from frappe.utils import flt
from jari_core.jari_core.stock_utils import consume_issueable_stock, add_wip_transfer_in, get_product_stock_summary
from jari_core.jari_core.doctype.process_master.process_master import (
    apply_process_department_defaults,
    validate_process_departments,
    validate_process_issue_type,
    validate_process_party,
)


class TaniyaIssue(Document):

    def validate(self):
        self.validate_process_assignments()
        self.set_defaults()
        validate_process_departments(self)
        validate_process_issue_type(
            self,
            "Taniya Issue",
        )
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
        apply_process_department_defaults(self)

        if not self.issue_type:
            self.issue_type = "New Batch"

    def set_batch_no(self):
        """
        Batch No is entered through new_batch_no for both first issue
        and later re-issues.

        The system automatically determines whether the entered Batch
        is new or already exists. The hidden existing_batch_no field is
        retained only for backward compatibility.
        """
        entered_batch = (
            self.new_batch_no
            or self.existing_batch_no
            or self.batch_no
            or ""
        ).strip()

        if not entered_batch:
            frappe.throw("Batch No is required.")

        self.batch_no = entered_batch

        previous_issued = frappe.db.count(
            "Taniya Issue",
            {
                "batch_no": entered_batch,
                "docstatus": 1,
                "name": ["!=", self.name],
            },
        )

        if previous_issued:
            self.issue_type = "Re Issue"
            self.existing_batch_no = entered_batch
        else:
            self.issue_type = "New Batch"
            self.existing_batch_no = None

    def set_issue_status(self):
        previous_issued = frappe.db.count(
            "Taniya Issue",
            {"batch_no": self.batch_no, "docstatus": 1, "name": ["!=", self.name]}
        )
        status = "Re Issue" if previous_issued or self.issue_type == "Re Issue" else "Issued"
        frappe.db.set_value(self.doctype, self.name, "status", status)

    def validate_items(self):
        from jari_core.jari_core.stock_utils import (
            prepare_selected_stock_source,
        )

        if not self.issue_items:
            frappe.throw(
                "At least one issue item is required."
            )

        for row in self.issue_items:
            if not row.product:
                frappe.throw(
                    "Product is required in issue item."
                )

            if flt(row.weight) <= 0:
                frappe.throw(
                    f"Weight must be greater than zero "
                    f"for product {row.product}."
                )

            prepare_selected_stock_source(
                doc=self,
                row=row,
                required_qty=row.weight,
            )

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
        from jari_core.jari_core.stock_utils import (
            consume_selected_stock_source,
            add_source_linked_transfer_in,
        )

        if self.ledger_exists():
            return

        for row in self.issue_items:
            product = row.product
            weight = flt(row.weight)

            consume_selected_stock_source(
                doc=self,
                stock_source=row.stock_source,
                source_department=
                    row.source_department,
                product=product,
                required_qty=weight,
                batch_no=self.batch_no,
                posting_date=self.issue_date,
                transaction_type=
                    "Production Input",
                remarks=(
                    "Taniya Issue consumed from "
                    f"{row.source_reference or row.stock_source}"
                ),
            )

            add_source_linked_transfer_in(
                doc=self,
                stock_source=row.stock_source,
                department=self.to_department,
                product=product,
                qty=weight,
                batch_no=self.batch_no,
                posting_date=self.issue_date,
                remarks=(
                    "Taniya source-linked inward "
                    f"in {self.to_department}"
                ),
            )

    def on_cancel(self):
        from jari_core.jari_core.stock_utils import (
            reverse_reference_inventory_ledger,
        )

        reverse_reference_inventory_ledger(
            self
        )
