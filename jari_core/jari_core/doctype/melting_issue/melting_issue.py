import frappe
from frappe.model.document import Document
from frappe.utils import flt, today
from jari_core.jari_core.stock_utils import (
    add_source_linked_transfer_in,
    consume_selected_stock_source,
    get_stock_source_balance,
    reverse_reference_inventory_ledger,
)
from jari_core.jari_core.doctype.process_master.process_master import (
    apply_process_department_defaults,
    validate_process_departments,
    validate_process_issue_type,
    validate_process_party,
)


class MeltingIssue(Document):

    def validate(self):
        self.validate_process_assignments()
        self.set_defaults()
        validate_process_departments(self)
        validate_process_issue_type(
            self,
            "Melting Issue",
        )
        self.sync_active_batch_no()
        self.set_silver_purity()
        self.validate_stock_sources()
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
        self.sync_active_batch_no()
        self.post_inventory_transfer()
        frappe.db.set_value(self.doctype, self.name, "status", "Issued")

    def set_defaults(self):
        apply_process_department_defaults(self)

    def sync_active_batch_no(self):
        if getattr(self, "batch_no", None):
            self.active_batch_no = self.batch_no

    def set_silver_purity(self):
        self.silver_purity_percent = (
            frappe.db.get_value("Quality Master", self.quality_code, "silver_purity_percent") or 0
            if self.quality_code else 0
        )

    def validate_stock_sources(self):
        from jari_core.jari_core.stock_utils import (
            prepare_selected_stock_source,
        )

        for row in self.issue_items or []:
            if (
                not row.product
                or flt(row.weight) <= 0
            ):
                continue

            prepare_selected_stock_source(
                doc=self,
                row=row,
                required_qty=row.weight,
            )

    def calculate_totals(self):
        self.total_issue_weight = 0

        for row in self.issue_items or []:
            self.total_issue_weight += flt(row.weight)

            if row.product:
                metal_type = frappe.db.get_value("Product Master", row.product, "metal_type")
                row.silver_weight = (
                    flt(row.weight) * flt(self.silver_purity_percent) / 100
                    if metal_type == "Silver" else 0
                )

    def get_last_balance(self, company, department, product):
        return frappe.db.get_value(
            "Inventory Ledger",
            {"company": company, "department": department, "product": product},
            "current_balance",
            order_by="creation desc"
        ) or 0

    def get_available_sources(self, product):
        departments = frappe.db.sql("""
            SELECT DISTINCT department
            FROM `tabInventory Ledger`
            WHERE company=%s AND product=%s
        """, (self.company, product), as_dict=True)

        rows = []

        for d in departments:
            bal = flt(self.get_last_balance(self.company, d.department, product))
            if bal > 0:
                rows.append({"department": d.department, "balance": bal})

        rows.sort(key=lambda x: (0 if x["department"] == self.from_department else 1, -x["balance"]))
        return rows

    def ledger_exists(self):
        return frappe.db.exists("Inventory Ledger", {
            "reference_doctype": self.doctype,
            "reference_name": self.name
        })

    def post_inventory_transfer(self):
        """
        Consume only the exact Inventory Stock Source selected
        in each Issue Product Detail row.

        Source lineage is retained during the WIP transfer into
        the destination department.
        """
        if self.ledger_exists():
            return

        for row in self.issue_items or []:

            product = row.product
            required = flt(row.weight)

            if not product or required <= 0:
                continue

            consume_selected_stock_source(
                doc=self,
                stock_source=row.stock_source,
                source_department=row.source_department,
                product=product,
                required_qty=required,
                batch_no=self.batch_no,
                posting_date=self.issue_date,
                transaction_type="Production Input",
                remarks=(
                    f"Melting Issue consumed from "
                    f"{row.stock_source}"
                ),
            )

            add_source_linked_transfer_in(
                doc=self,
                stock_source=row.stock_source,
                department=self.to_department,
                product=product,
                qty=required,
                batch_no=self.batch_no,
                posting_date=self.issue_date,
                remarks=(
                    f"Melting Issue source-linked inward "
                    f"in {self.to_department}"
                ),
            )

    def on_cancel(self):
        reverse_reference_inventory_ledger(self)


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
        lookup_filters = {
            "product": product,
            "department": d.department
        }

        if company:
            lookup_filters["company"] = company

        bal = frappe.db.get_value(
            "Inventory Ledger",
            lookup_filters,
            "current_balance",
            order_by="creation desc"
        ) or 0

        if flt(bal) != 0:
            lines.append(f"{d.department} - {bal} KG")

    return "\n".join(lines) if lines else "No stock available"


@frappe.whitelist()
def get_product_display_name(product):
    if not product:
        return ""

    return (
        frappe.db.get_value("Product Master", product, "product_name")
        or frappe.db.get_value("Product Master", product, "item_name")
        or frappe.db.get_value("Product Master", product, "product_code")
        or product
    )
