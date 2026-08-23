import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, today
from jari_core.jari_core.doctype.process_master.process_master import (
    apply_process_department_defaults,
    validate_process_departments,
    validate_process_issue_type,
    validate_process_party,
)


VALID_ISSUE_RECEIVE_TYPES = {
    "In-house",
    "Readymade",
    "Return",
}


class PavthaIssue(Document):

    def validate(self):
        self.set_defaults()
        self.validate_outsourcing()
        self.validate_process_assignments()
        validate_process_departments(self)
        validate_process_issue_type(
            self,
            "Pavtha Issue",
        )
        self.validate_items()
        self.calculate_totals()

    def validate_outsourcing(self):
        """
        Outsourcer requirement is controlled exclusively by
        Process Master.is_outsourced.

        In-house Process:
            Outsourcer is not applicable and is cleared.

        Outsourced Process:
            Outsourcer is mandatory and must also be assigned
            to the selected Process.
        """
        if not self.process_master:
            return

        is_outsourced = bool(
            frappe.db.get_value(
                "Process Master",
                self.process_master,
                "is_outsourced",
            )
        )

        if is_outsourced:
            if not self.outsourcer:
                frappe.throw(
                    _(
                        "Outsourcer is required because the "
                        "selected Process is Outsourced."
                    )
                )
        else:
            self.outsourcer = None

    def validate_process_assignments(self):
        validate_process_party(
            self,
            fieldname="outsourcer",
            master_doctype="Jobworker Master",
            label="Outsourcer",
        )
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
        frappe.db.set_value(
            self.doctype,
            self.name,
            "status",
            "Issued",
            update_modified=False,
        )

    def set_defaults(self):
        """
        Set Process-driven routing and child-row defaults.
        """
        apply_process_department_defaults(self)

        for row in self.issue_items or []:
            if not row.issue_receive_type:
                row.issue_receive_type = "In-house"

    def validate_items(self):
        from jari_core.jari_core.stock_utils import (
            prepare_selected_stock_source,
        )

        if not self.issue_items:
            frappe.throw(
                _(
                    "At least one issue item "
                    "is required."
                )
            )

        for row in self.issue_items:
            if not row.product:
                frappe.throw(
                    _(
                        "Product is required in "
                        "issue item row #{0}."
                    ).format(
                        row.idx
                    )
                )

            if flt(row.weight) <= 0:
                frappe.throw(
                    _(
                        "Weight must be greater than "
                        "zero in row #{0} for "
                        "product {1}."
                    ).format(
                        row.idx,
                        frappe.bold(
                            row.product
                        ),
                    )
                )

            if not row.issue_receive_type:
                frappe.throw(
                    _(
                        "Issue/Receive Type is "
                        "required in issue item "
                        "row #{0}."
                    ).format(
                        row.idx
                    )
                )

            if (
                row.issue_receive_type
                not in VALID_ISSUE_RECEIVE_TYPES
            ):
                frappe.throw(
                    _(
                        "Issue/Receive Type in row "
                        "#{0} must be In-house, "
                        "Readymade, or Return."
                    ).format(
                        row.idx
                    )
                )

            prepare_selected_stock_source(
                doc=self,
                row=row,
                required_qty=row.weight,
            )

    def get_quality_purity(self):
        if not self.quality_code:
            return 0

        possible_fields = [
            "silver_purity_percent",
            "purity_percent",
            "purity",
            "quality_percent",
        ]

        for fieldname in possible_fields:
            if frappe.db.has_column("Quality Master", fieldname):
                return flt(
                    frappe.db.get_value(
                        "Quality Master",
                        self.quality_code,
                        fieldname,
                    )
                    or 0
                )

        return 0

    def calculate_totals(self):
        total = 0
        quality_purity = self.get_quality_purity()

        for row in self.issue_items or []:
            row_weight = flt(row.weight)
            total += row_weight
            row.silver_weight = 0

            if row.product:
                metal_type = frappe.db.get_value(
                    "Product Master",
                    row.product,
                    "metal_type",
                )

                if metal_type == "Silver":
                    row.silver_weight = (
                        row_weight * flt(quality_purity) / 100
                    )

        self.total_issue_weight = total

    def get_last_balance(self, company, department, product):
        return (
            frappe.db.get_value(
                "Inventory Ledger",
                {
                    "company": company,
                    "department": department,
                    "product": product,
                },
                "current_balance",
                order_by="creation desc",
            )
            or 0
        )

    def get_available_sources(self, product):
        departments = frappe.db.sql(
            """
            SELECT DISTINCT department
            FROM `tabInventory Ledger`
            WHERE company = %s
              AND product = %s
              AND department IS NOT NULL
              AND department != ''
            """,
            (self.company, product),
            as_dict=True,
        )

        rows = []

        for department_row in departments:
            balance = flt(
                self.get_last_balance(
                    self.company,
                    department_row.department,
                    product,
                )
            )

            if balance > 0:
                rows.append(
                    {
                        "department": department_row.department,
                        "balance": balance,
                    }
                )

        # Prefer the selected source department first.
        # Remaining departments are ordered by highest stock.
        rows.sort(
            key=lambda row: (
                0
                if row["department"] == self.from_department
                else 1,
                -row["balance"],
            )
        )

        return rows

    def ledger_exists(self):
        return frappe.db.exists(
            "Inventory Ledger",
            {
                "reference_doctype": self.doctype,
                "reference_name": self.name,
            },
        )

    def add_ledger(
        self,
        department,
        product,
        in_weight,
        out_weight,
        transaction_type,
        remarks,
    ):
        balance = self.get_last_balance(
            self.company,
            department,
            product,
        )

        frappe.get_doc(
            {
                "doctype": "Inventory Ledger",
                "company": self.company,
                "department": department,
                "product": product,
                "batch_number": self.batch_no,
                "in_weight": flt(in_weight),
                "out_weight": flt(out_weight),
                "current_balance": (
                    flt(balance)
                    + flt(in_weight)
                    - flt(out_weight)
                ),
                "transaction_type": transaction_type,
                "reference_doctype": self.doctype,
                "reference_name": self.name,
                "date": self.issue_date or today(),
                "remarks": remarks,
            }
        ).insert(ignore_permissions=True)

    def post_inventory_transfer(self):
        from jari_core.jari_core.stock_utils import (
            consume_selected_stock_source,
            add_source_linked_transfer_in,
        )

        if self.ledger_exists():
            return

        for row in self.issue_items or []:
            required = flt(
                row.weight
            )

            product = row.product

            issue_receive_type = (
                row.issue_receive_type
                or "In-house"
            )

            consume_selected_stock_source(
                doc=self,
                stock_source=
                    row.stock_source,
                source_department=
                    row.source_department,
                product=product,
                required_qty=required,
                batch_no=self.batch_no,
                posting_date=
                    self.issue_date,
                transaction_type=
                    "Production Input",
                remarks=(
                    f"Pavtha "
                    f"{issue_receive_type} "
                    "consumed from "
                    f"{row.source_reference or row.stock_source}"
                ),
            )

            add_source_linked_transfer_in(
                doc=self,
                stock_source=
                    row.stock_source,
                department=
                    self.to_department,
                product=product,
                qty=required,
                batch_no=self.batch_no,
                posting_date=
                    self.issue_date,
                remarks=(
                    f"Pavtha "
                    f"{issue_receive_type} "
                    "source-linked inward "
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


@frappe.whitelist()
def get_product_stock_summary(product, company=None):
    if not product:
        return ""

    filters = {
        "product": product,
    }

    if company:
        filters["company"] = company

    departments = frappe.get_all(
        "Inventory Ledger",
        filters=filters,
        fields=["department"],
        group_by="department",
    )

    lines = []

    for department_row in departments:
        if not department_row.department:
            continue

        query_filters = {
            "product": product,
            "department": department_row.department,
        }

        if company:
            query_filters["company"] = company

        balance = (
            frappe.db.get_value(
                "Inventory Ledger",
                query_filters,
                "current_balance",
                order_by="creation desc",
            )
            or 0
        )

        if flt(balance) != 0:
            lines.append(
                f"{department_row.department} - {flt(balance)} KG"
            )

    return "\n".join(lines) if lines else "No stock available"
