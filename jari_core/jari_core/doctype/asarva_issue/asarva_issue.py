
import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.naming import make_autoname
from frappe.utils import flt, getdate, today

from jari_core.jari_core.doctype.process_master.process_master import (
    apply_process_department_defaults,
    validate_process_departments,
    validate_process_issue_type,
    validate_party_process_assignment,
    validate_process_party,
)


class AsarvaIssue(Document):

    def autoname(self):
        issue_date = getdate(
            self.issue_date or today()
        )

        party_name = (
            frappe.db.get_value(
                "Jobworker Master",
                self.asarva_outsourcer,
                "jobworker_name",
            )
            or self.asarva_outsourcer
            or "ASV"
        )

        clean_name = re.sub(
            r"[^A-Za-z0-9]",
            "",
            party_name,
        ).upper()

        prefix = (
            clean_name[:3]
            if clean_name
            else "ASV"
        ).ljust(3, "X")

        series = (
            f"{prefix}-"
            f"{issue_date.strftime('%m')}-"
            f"{issue_date.strftime('%y')}-"
            ".####"
        )

        self.name = make_autoname(series)

    def validate(self):
        self.set_defaults()
        validate_process_departments(self)
        validate_process_issue_type(
            self,
            "Asarva Issue",
        )
        self.validate_parties()
        self.validate_items()
        self.calculate_totals()

    def set_defaults(self):
        apply_process_department_defaults(self)

        if not self.issued_by:
            self.issued_by = frappe.session.user

        for row in self.issue_items or []:
            if not row.issue_date:
                row.issue_date = self.issue_date

            if not row.product_quality:
                row.product_quality = self.quality_code

    def validate_parties(self):
        validate_process_party(
            self,
            fieldname="quality_code",
            master_doctype="Quality Master",
            label="Quality",
        )

        validate_process_party(
            self,
            fieldname="asarva_outsourcer",
            master_doctype="Jobworker Master",
            label="Asarva Outsourcer",
        )

        checked_workers = set()

        for row in self.issue_items or []:
            if (
                not row.rangrej_operator
                or row.rangrej_operator
                in checked_workers
            ):
                continue

            checked_workers.add(
                row.rangrej_operator
            )

            validate_party_process_assignment(
                selected_party=row.rangrej_operator,
                process_master=self.process_master,
                master_doctype="Worker Master",
                label=(
                    f"Rangrej Operator in row #{row.idx}"
                ),
                require_active=True,
            )

    def validate_items(self):
        from jari_core.jari_core.stock_utils import (
            prepare_selected_stock_source,
        )

        if not self.issue_items:
            frappe.throw(
                _(
                    "At least one Product Issue row "
                    "is required."
                )
            )

        for row in self.issue_items:

            if not row.product:
                frappe.throw(
                    _(
                        "Product is required in row #{0}."
                    ).format(
                        row.idx
                    )
                )

            if not row.colour:
                frappe.throw(
                    _(
                        "Colour is required in row #{0}."
                    ).format(
                        row.idx
                    )
                )

            if flt(row.issued_weight) <= 0:
                frappe.throw(
                    _(
                        "Issued Weight must be greater "
                        "than zero in row #{0}."
                    ).format(
                        row.idx
                    )
                )

            prepare_selected_stock_source(
                doc=self,
                row=row,
                required_qty=
                    row.issued_weight,
            )

    def calculate_totals(self):
        total_issued = sum(
            flt(row.issued_weight)
            for row in self.issue_items or []
        )

        expected_percent = flt(
            self.expected_receive_percent
        )

        if (
            expected_percent < 0
            or expected_percent > 100
        ):
            frappe.throw(
                _(
                    "Expected Receive Percentage must be "
                    "between 0 and 100."
                )
            )

        self.total_issued_weight = flt(
            total_issued,
            3,
        )

        self.expected_received_weight = flt(
            total_issued
            * expected_percent
            / 100,
            3,
        )

        current_received_weight = flt(
            self.total_received_weight
        )

        self.total_received_weight = flt(
            current_received_weight,
            3,
        )

        self.balance_expected_weight = max(
            0,
            flt(
                flt(self.expected_received_weight)
                - current_received_weight,
                3,
            ),
        )

    def on_submit(self):
        self.post_inventory_transfer()

        total_received = flt(
            frappe.db.get_value(
                self.doctype,
                self.name,
                "total_received_weight",
            )
            or self.total_received_weight
        )

        expected_received = flt(
            frappe.db.get_value(
                self.doctype,
                self.name,
                "expected_received_weight",
            )
            or self.expected_received_weight
        )

        if (
            expected_received > 0
            and total_received
            >= expected_received
        ):
            status = "Received"

        elif total_received > 0:
            status = "Partially Received"

        else:
            status = "Issued"

        frappe.db.set_value(
            self.doctype,
            self.name,
            "status",
            status,
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
            consume_selected_stock_source,
            add_source_linked_transfer_in,
        )

        if self.ledger_exists():
            return

        for row in self.issue_items or []:

            required = flt(
                row.issued_weight
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
                    "Asarva input issued from "
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
                    "Asarva source-linked WIP "
                    f"in {self.to_department}"
                ),
            )
