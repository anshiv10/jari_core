import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, today

from jari_core.jari_core.doctype.process_master.process_master import (
    apply_process_department_defaults,
    validate_process_departments,
    validate_process_issue_type,
)


class YTIssue(Document):

    def validate(self):
        self.set_defaults()
        validate_process_departments(
            self
        )
        validate_process_issue_type(
            self,
            "YT Issue",
        )
        self.validate_yt_route()
        self.validate_items()
        self.calculate_totals()

    def set_defaults(self):
        apply_process_department_defaults(
            self
        )

        if not self.issue_date:
            self.issue_date = today()

        if not self.issued_by:
            self.issued_by = (
                frappe.session.user
            )

        for row in (
            self.issue_items
            or []
        ):
            if not row.issue_date:
                row.issue_date = (
                    self.issue_date
                )

            row.uom = "KG"

    def validate_yt_route(self):
        process = frappe.db.get_value(
            "Process Master",
            self.process_master,
            [
                "flow_type",
                "to_department",
            ],
            as_dict=True,
        )

        if not process:
            frappe.throw(
                _("Process does not exist.")
            )

        if (
            process.flow_type
            not in (
                "Imitation",
                "Both",
            )
        ):
            frappe.throw(
                _(
                    "YT Issue requires an Imitation "
                    "or Both flow Process."
                )
            )

        if (
            process.to_department
            != "YT Department"
        ):
            frappe.throw(
                _(
                    "YT Issue Process must route "
                    "To Department to YT Department."
                )
            )

    def validate_items(self):
        from jari_core.jari_core.stock_utils import (
            prepare_selected_stock_source,
        )

        if not self.issue_items:
            frappe.throw(
                _(
                    "At least one Issue Product "
                    "Detail row is required."
                )
            )

        for row in self.issue_items:
            if not row.product:
                frappe.throw(
                    _(
                        "Product is required in "
                        "row #{0}."
                    ).format(
                        row.idx
                    )
                )

            if not row.machine_name:
                frappe.throw(
                    _(
                        "Machine Name is required "
                        "in row #{0}."
                    ).format(
                        row.idx
                    )
                )

            if not row.supplier:
                frappe.throw(
                    _(
                        "Supplier is required in "
                        "row #{0}."
                    ).format(
                        row.idx
                    )
                )

            if int(
                row.piece
                or 0
            ) < 0:
                frappe.throw(
                    _(
                        "Piece cannot be negative "
                        "in row #{0}."
                    ).format(
                        row.idx
                    )
                )

            if flt(
                row.weight
            ) <= 0:
                frappe.throw(
                    _(
                        "Weight must be greater "
                        "than zero in row #{0}."
                    ).format(
                        row.idx
                    )
                )

            machine = frappe.db.get_value(
                "Khata Machine Master",
                row.machine_name,
                [
                    "department",
                    "is_active",
                ],
                as_dict=True,
            )

            if not machine:
                frappe.throw(
                    _(
                        "Machine {0} does not exist."
                    ).format(
                        frappe.bold(
                            row.machine_name
                        )
                    )
                )

            if not int(
                machine.is_active
                or 0
            ):
                frappe.throw(
                    _(
                        "Machine {0} is inactive."
                    ).format(
                        frappe.bold(
                            row.machine_name
                        )
                    )
                )

            if (
                machine.department
                != self.to_department
            ):
                frappe.throw(
                    _(
                        "Machine {0} must belong "
                        "to {1}."
                    ).format(
                        frappe.bold(
                            row.machine_name
                        ),
                        frappe.bold(
                            self.to_department
                        ),
                    )
                )

            prepare_selected_stock_source(
                doc=self,
                row=row,
                required_qty=
                    row.weight,
            )

            row.current_stock = flt(
                row.source_available_weight,
                6,
            )

    def calculate_totals(self):
        self.total_issued_weight = flt(
            sum(
                flt(row.weight)
                for row in (
                    self.issue_items
                    or []
                )
            ),
            6,
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

    def on_cancel(self):
        from jari_core.jari_core.stock_utils import (
            reverse_reference_inventory_ledger,
        )

        reverse_reference_inventory_ledger(
            self
        )

        frappe.db.set_value(
            self.doctype,
            self.name,
            "status",
            "Cancelled",
            update_modified=False,
        )

    def ledger_exists(self):
        return bool(
            frappe.db.exists(
                "Inventory Ledger",
                {
                    "reference_doctype":
                        self.doctype,
                    "reference_name":
                        self.name,
                },
            )
        )

    def post_inventory_transfer(self):
        from jari_core.jari_core.stock_utils import (
            add_source_linked_transfer_in,
            consume_selected_stock_source,
        )

        if self.ledger_exists():
            return

        for row in (
            self.issue_items
            or []
        ):
            required = flt(
                row.weight,
                6,
            )

            if (
                not row.product
                or required <= 0
            ):
                continue

            consume_selected_stock_source(
                doc=self,
                stock_source=
                    row.stock_source,
                source_department=
                    row.source_department,
                product=
                    row.product,
                required_qty=
                    required,
                batch_no=
                    self.batch_no,
                posting_date=
                    self.issue_date,
                transaction_type=
                    "Production Input",
                remarks=(
                    "YT input issued from "
                    f"{row.source_reference or row.stock_source}"
                ),
            )

            add_source_linked_transfer_in(
                doc=self,
                stock_source=
                    row.stock_source,
                department=
                    self.to_department,
                product=
                    row.product,
                qty=
                    required,
                batch_no=
                    self.batch_no,
                posting_date=
                    self.issue_date,
                remarks=(
                    "YT source-linked WIP "
                    f"in {self.to_department}"
                ),
            )
