import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, today


class YTReceive(Document):

    def validate(self):
        self.validate_issue()
        self.pull_issue_details()
        self.validate_items()
        self.calculate_totals()

    def before_submit(self):
        self.validate_issue()
        self.pull_issue_details()
        self.validate_items()
        self.calculate_totals()

        if flt(
            self.total_received_weight
        ) <= 0:
            frappe.throw(
                _(
                    "Total N.W must be greater "
                    "than zero before Submit."
                )
            )

    def on_submit(self):
        self.post_inventory_transaction()

        frappe.db.set_value(
            "YT Issue",
            self.yt_issue,
            "status",
            "Received",
            update_modified=False,
        )

    def on_cancel(self):
        from jari_core.jari_core.stock_utils import (
            reverse_reference_inventory_ledger,
        )

        reverse_reference_inventory_ledger(
            self
        )

        if self.yt_issue:
            frappe.db.set_value(
                "YT Issue",
                self.yt_issue,
                "status",
                "Issued",
                update_modified=False,
            )

    def validate_issue(self):
        if not self.yt_issue:
            return

        issue_rows = frappe.db.sql(
            """
            SELECT
                name,
                docstatus,
                status
            FROM `tabYT Issue`
            WHERE name = %s
            FOR UPDATE
            """,
            (
                self.yt_issue,
            ),
            as_dict=True,
        )

        if not issue_rows:
            frappe.throw(
                _(
                    "YT Issue {0} does not exist."
                ).format(
                    frappe.bold(
                        self.yt_issue
                    )
                )
            )

        issue = issue_rows[0]

        if issue.docstatus != 1:
            frappe.throw(
                _(
                    "YT Issue {0} must be submitted "
                    "before creating YT Receive."
                ).format(
                    frappe.bold(
                        self.yt_issue
                    )
                )
            )

        if issue.status == "Cancelled":
            frappe.throw(
                _(
                    "Cancelled YT Issue {0} "
                    "cannot be selected."
                ).format(
                    frappe.bold(
                        self.yt_issue
                    )
                )
            )

        existing_receive = frappe.db.sql(
            """
            SELECT name
            FROM `tabYT Receive`
            WHERE yt_issue = %s
              AND docstatus < 2
              AND name != %s
            ORDER BY creation ASC
            LIMIT 1
            """,
            (
                self.yt_issue,
                self.name or "",
            ),
            as_dict=True,
        )

        if existing_receive:
            frappe.throw(
                _(
                    "YT Issue {0} is already used "
                    "in YT Receive {1}."
                ).format(
                    frappe.bold(
                        self.yt_issue
                    ),
                    frappe.bold(
                        existing_receive[0].name
                    ),
                )
            )

    def pull_issue_details(self):
        if not self.yt_issue:
            return

        issue = frappe.get_doc(
            "YT Issue",
            self.yt_issue,
        )

        self.company = (
            issue.company
        )
        self.batch_no = (
            issue.batch_no
        )
        self.process_master = (
            issue.process_master
        )
        self.quality_code = (
            issue.quality_code
        )

        if not self.receive_date:
            self.receive_date = today()

        if self.receive_items:
            for row in self.receive_items:
                if not row.date:
                    row.date = (
                        self.receive_date
                    )
                row.uom = "KG"
            return

        process = frappe.get_doc(
            "Process Master",
            issue.process_master,
        )

        outputs = [
            row
            for row in (
                process.output_products
                or []
            )
            if row.product
        ]

        if not outputs:
            frappe.throw(
                _(
                    "No Output Product is configured "
                    "in Process {0}."
                ).format(
                    frappe.bold(
                        process.process_name
                        or process.name
                    )
                )
            )

        machines = {
            row.machine_name
            for row in (
                issue.issue_items
                or []
            )
            if row.machine_name
        }

        default_machine = (
            next(iter(machines))
            if len(machines) == 1
            else None
        )

        for output in outputs:
            row = self.append(
                "receive_items",
                {},
            )
            row.date = (
                self.receive_date
            )
            row.product = (
                output.product
            )
            row.uom = "KG"
            row.machine_name = (
                default_machine
            )
            row.baad_weight = 0
            row.gross_weight = 0
            row.net_weight = 0

    def validate_items(self):
        if not self.receive_items:
            frappe.throw(
                _(
                    "At least one Received Product "
                    "Detail row is required."
                )
            )

        issue = frappe.get_doc(
            "YT Issue",
            self.yt_issue,
        )

        process = frappe.get_doc(
            "Process Master",
            issue.process_master,
        )

        allowed_products = {
            row.product
            for row in (
                process.output_products
                or []
            )
            if row.product
        }

        if not allowed_products:
            frappe.throw(
                _(
                    "No Output Product is configured "
                    "in Process {0}."
                ).format(
                    frappe.bold(
                        process.process_name
                        or process.name
                    )
                )
            )

        for row in self.receive_items:
            if not row.date:
                row.date = (
                    self.receive_date
                )

            row.uom = "KG"

            if not row.product:
                frappe.throw(
                    _(
                        "Product is required in "
                        "row #{0}."
                    ).format(
                        row.idx
                    )
                )

            if (
                row.product
                not in allowed_products
            ):
                frappe.throw(
                    _(
                        "Product {0} is not configured "
                        "as an Output Product of "
                        "Process {1}."
                    ).format(
                        frappe.bold(
                            row.product
                        ),
                        frappe.bold(
                            process.process_name
                            or process.name
                        ),
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
                != issue.to_department
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
                            issue.to_department
                        ),
                    )
                )

            gross = flt(
                row.gross_weight
            )
            baad = flt(
                row.baad_weight
            )

            if gross < 0:
                frappe.throw(
                    _(
                        "G.W cannot be negative "
                        "in row #{0}."
                    ).format(
                        row.idx
                    )
                )

            if baad < 0:
                frappe.throw(
                    _(
                        "Baad Weight cannot be "
                        "negative in row #{0}."
                    ).format(
                        row.idx
                    )
                )

            if baad > gross:
                frappe.throw(
                    _(
                        "Baad Weight cannot exceed "
                        "G.W in row #{0}."
                    ).format(
                        row.idx
                    )
                )

            row.net_weight = flt(
                gross - baad,
                6,
            )

    def calculate_totals(self):
        self.total_gross_weight = flt(
            sum(
                flt(row.gross_weight)
                for row in (
                    self.receive_items
                    or []
                )
            ),
            6,
        )
        self.total_baad_weight = flt(
            sum(
                flt(row.baad_weight)
                for row in (
                    self.receive_items
                    or []
                )
            ),
            6,
        )
        self.total_received_weight = flt(
            sum(
                flt(row.net_weight)
                for row in (
                    self.receive_items
                    or []
                )
            ),
            6,
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

    def get_last_balance(
        self,
        department,
        product,
    ):
        return (
            frappe.db.get_value(
                "Inventory Ledger",
                {
                    "company":
                        self.company,
                    "department":
                        department,
                    "product":
                        product,
                },
                "current_balance",
                order_by=
                    "creation desc",
            )
            or 0
        )

    def post_inventory_transaction(self):
        from jari_core.jari_core.stock_utils import (
            consume_selected_stock_source,
            get_or_create_stock_source,
        )

        if self.ledger_exists():
            return

        issue = frappe.get_doc(
            "YT Issue",
            self.yt_issue,
        )

        # Consume the exact source-linked WIP moved by YT Issue.
        for issue_row in (
            issue.issue_items
            or []
        ):
            required = flt(
                issue_row.weight,
                6,
            )

            if (
                not issue_row.product
                or required <= 0
            ):
                continue

            if not issue_row.stock_source:
                frappe.throw(
                    _(
                        "YT Issue row #{0} does not "
                        "contain Stock Source lineage."
                    ).format(
                        issue_row.idx
                    )
                )

            consume_selected_stock_source(
                doc=self,
                stock_source=
                    issue_row.stock_source,
                source_department=
                    issue.to_department,
                product=
                    issue_row.product,
                required_qty=
                    required,
                batch_no=
                    self.batch_no,
                posting_date=
                    self.receive_date,
                transaction_type=
                    "Production Input",
                remarks=(
                    "YT WIP consumed during "
                    "Receive / transformation"
                ),
            )

        # Create new stock sources for actual YT output products.
        for row in (
            self.receive_items
            or []
        ):
            qty = flt(
                row.net_weight,
                6,
            )

            if (
                not row.product
                or qty <= 0
            ):
                continue

            stock_source = (
                get_or_create_stock_source(
                    source_type=
                        "Production Receive",
                    company=
                        self.company,
                    product=
                        row.product,
                    source_doctype=
                        self.doctype,
                    source_name=
                        self.name,
                    source_row=
                        row.name,
                    source_date=
                        self.receive_date,
                    batch_number=
                        self.batch_no,
                    remarks=(
                        "YT Process Output received"
                    ),
                )
            )

            last_balance = (
                self.get_last_balance(
                    issue.to_department,
                    row.product,
                )
            )

            frappe.get_doc({
                "doctype":
                    "Inventory Ledger",
                "company":
                    self.company,
                "department":
                    issue.to_department,
                "product":
                    row.product,
                "batch_number":
                    self.batch_no,
                "stock_source":
                    stock_source,
                "in_weight":
                    qty,
                "out_weight":
                    0,
                "current_balance":
                    flt(
                        last_balance
                        + qty,
                        6,
                    ),
                "transaction_type":
                    "Production Output",
                "reference_doctype":
                    self.doctype,
                "reference_name":
                    self.name,
                "date":
                    self.receive_date,
                "remarks":
                    (
                        "YT output received "
                        f"in {issue.to_department}"
                    ),
            }).insert(
                ignore_permissions=True
            )


@frappe.whitelist()
def get_yt_issue_details(
    issue_name,
):
    if not issue_name:
        return {}

    issue = frappe.get_doc(
        "YT Issue",
        issue_name,
    )

    if issue.docstatus != 1:
        frappe.throw(
            _(
                "YT Issue {0} must be submitted."
            ).format(
                frappe.bold(
                    issue_name
                )
            )
        )

    process = frappe.get_doc(
        "Process Master",
        issue.process_master,
    )

    outputs = [
        row
        for row in (
            process.output_products
            or []
        )
        if row.product
    ]

    if not outputs:
        frappe.throw(
            _(
                "No Output Product is configured "
                "in Process {0}."
            ).format(
                frappe.bold(
                    process.process_name
                    or process.name
                )
            )
        )

    machines = {
        row.machine_name
        for row in (
            issue.issue_items
            or []
        )
        if row.machine_name
    }

    default_machine = (
        next(iter(machines))
        if len(machines) == 1
        else None
    )

    items = [
        {
            "product":
                output.product,
            "uom":
                "KG",
            "machine_name":
                default_machine,
        }
        for output in outputs
    ]

    return {
        "company":
            issue.company,
        "batch_no":
            issue.batch_no,
        "process_master":
            issue.process_master,
        "quality_code":
            issue.quality_code,
        "to_department":
            issue.to_department,
        "items":
            items,
    }


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def yt_issue_query(
    doctype,
    txt,
    searchfield,
    start,
    page_len,
    filters,
):
    filters = filters or {}

    current_receive = (
        filters.get(
            "current_receive"
        )
        or ""
    )

    return frappe.db.sql(
        """
        SELECT
            issue.name,
            CONCAT(
                'Batch: ',
                COALESCE(
                    issue.batch_no,
                    ''
                ),
                ' | Weight: ',
                FORMAT(
                    issue.total_issued_weight,
                    3
                ),
                ' KG | Status: ',
                issue.status
            ) AS description
        FROM `tabYT Issue` issue
        WHERE issue.docstatus = 1
          AND issue.status != 'Cancelled'
          AND NOT EXISTS (
              SELECT 1
              FROM `tabYT Receive` receive_doc
              WHERE receive_doc.yt_issue =
                    issue.name
                AND receive_doc.docstatus < 2
                AND (
                    %(current_receive)s = ''
                    OR receive_doc.name !=
                       %(current_receive)s
                )
          )
          AND (
              issue.name LIKE %(txt)s
              OR COALESCE(
                  issue.batch_no,
                  ''
              ) LIKE %(txt)s
          )
        ORDER BY issue.creation DESC
        LIMIT %(start)s, %(page_len)s
        """,
        {
            "txt":
                f"%{txt}%",
            "current_receive":
                current_receive,
            "start":
                start,
            "page_len":
                page_len,
        },
    )
