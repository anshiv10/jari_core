import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from jari_core.jari_core.stock_utils import (
    cleanup_unused_draft_receive_stock_sources,
    ensure_draft_receive_stock_sources,
)


class AsarvaReceive(Document):

    def validate(self):
        self.validate_issue()
        self.pull_issue_details()
        self.validate_items()
        self.calculate_totals()

    def after_insert(self):
        self.refresh_issue_totals()

    def on_update(self):
        self.refresh_issue_totals()

        if int(self.docstatus or 0) == 0:
            ensure_draft_receive_stock_sources(
                self
            )

    def on_submit(self):
        self.post_inventory_transaction()
        self.refresh_issue_totals()

    def on_cancel(self):
        from jari_core.jari_core.stock_utils import (
            reverse_reference_inventory_ledger,
        )

        reverse_reference_inventory_ledger(
            self
        )

        self.refresh_issue_totals()

    def on_trash(self):
        cleanup_unused_draft_receive_stock_sources(
            self
        )

        self.refresh_issue_totals(
            exclude_receive=self.name
        )

    # =========================================================
    # ISSUE VALIDATION
    # =========================================================

    def validate_issue(self):
        if not self.asarva_issue:
            return

        # Lock the Issue row during validation.
        #
        # This prevents two users from saving two different
        # Asarva Receive documents against the same Issue at
        # almost exactly the same time.
        issue_rows = frappe.db.sql(
            """
            SELECT
                name,
                docstatus,
                status
            FROM `tabAsarva Issue`
            WHERE name = %s
            FOR UPDATE
            """,
            (self.asarva_issue,),
            as_dict=True,
        )

        if not issue_rows:
            frappe.throw(
                _(
                    "Asarva Issue {0} does not exist."
                ).format(
                    frappe.bold(self.asarva_issue)
                )
            )

        issue = issue_rows[0]

        # An Asarva Receive must always come from a submitted Issue.
        if issue.docstatus != 1:
            frappe.throw(
                _(
                    "Asarva Issue {0} must be submitted "
                    "before creating an Asarva Receive."
                ).format(
                    frappe.bold(self.asarva_issue)
                )
            )

        if issue.status == "Cancelled":
            frappe.throw(
                _(
                    "Cancelled Asarva Issue {0} cannot "
                    "be selected."
                ).format(
                    frappe.bold(self.asarva_issue)
                )
            )

        # IMPORTANT BUSINESS RULE:
        #
        # One Asarva Issue can have only ONE active
        # Asarva Receive document.
        #
        # Draft Receive also reserves the Issue.
        #
        # Cancelled Receive does NOT reserve it.
        existing_receive = frappe.db.sql(
            """
            SELECT name
            FROM `tabAsarva Receive`
            WHERE asarva_issue = %s
              AND docstatus < 2
              AND name != %s
            ORDER BY creation ASC
            LIMIT 1
            """,
            (
                self.asarva_issue,
                self.name or "",
            ),
            as_dict=True,
        )

        if existing_receive:
            frappe.throw(
                _(
                    "Asarva Issue {0} is already being used "
                    "in Asarva Receive {1}.<br><br>"
                    "Please open the existing Receive and add "
                    "additional Received Product rows there."
                ).format(
                    frappe.bold(self.asarva_issue),
                    frappe.bold(
                        existing_receive[0].name
                    ),
                )
            )

    # =========================================================
    # FETCH ISSUE INFORMATION
    # =========================================================

    def pull_issue_details(self):
        if not self.asarva_issue:
            return

        issue = frappe.get_doc(
            "Asarva Issue",
            self.asarva_issue,
        )

        self.company = issue.company

        self.asarva_outsourcer = (
            issue.asarva_outsourcer
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

        # Existing Receive rows belong to this
        # transaction and must never be rebuilt.
        if self.receive_items:
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

        colours = {
            row.colour
            for row in (
                issue.issue_items
                or []
            )
            if row.colour
        }

        default_colour = (
            next(iter(colours))
            if len(colours) == 1
            else None
        )

        one_output = (
            len(outputs) == 1
        )

        for output in outputs:

            row = self.append(
                "receive_items",
                {},
            )

            row.source_issue_item = None

            row.product = (
                output.product
            )

            row.product_quality = (
                issue.quality_code
            )

            row.colour = (
                default_colour
            )

            row.issued_weight = (
                flt(
                    issue.total_issued_weight
                )
                if one_output
                else 0
            )

            row.quantity_firka = 0
            row.gross_weight = 0
            row.baad_weight = 0
            row.received_weight = 0

            product_uom = (
                frappe.db.get_value(
                    "Product Master",
                    output.product,
                    "unit",
                )
                or ""
            )

            row.uom = (
                product_uom
                or "KG"
            )

    # =========================================================
    # RECEIVE ROW VALIDATION
    # =========================================================

    def validate_items(self):
        if not self.receive_items:
            frappe.throw(
                _(
                    "At least one Receive Item "
                    "is required."
                )
            )

        issue = frappe.get_doc(
            "Asarva Issue",
            self.asarva_issue,
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

            if int(
                row.quantity_firka
                or 0
            ) < 0:
                frappe.throw(
                    _(
                        "Quantity Firka cannot be "
                        "negative in row #{0}."
                    ).format(
                        row.idx
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
                        "Baad cannot be negative "
                        "in row #{0}."
                    ).format(
                        row.idx
                    )
                )

            if baad > gross:
                frappe.throw(
                    _(
                        "Baad cannot exceed G.W "
                        "in row #{0}."
                    ).format(
                        row.idx
                    )
                )

            row.received_weight = flt(
                gross - baad,
                3,
            )

            if not row.uom:
                row.uom = "KG"

    # =========================================================
    # TOTALS
    # =========================================================

    def calculate_totals(self):
        self.total_gross_weight = flt(
            sum(
                flt(row.gross_weight)
                for row in self.receive_items or []
            ),
            3,
        )

        self.total_baad_weight = flt(
            sum(
                flt(row.baad_weight)
                for row in self.receive_items or []
            ),
            3,
        )

        self.total_received_weight = flt(
            sum(
                flt(row.received_weight)
                for row in self.receive_items or []
            ),
            3,
        )

    # =========================================================
    # UPDATE ASARVA ISSUE SUMMARY
    # =========================================================

    def refresh_issue_totals(
        self,
        exclude_receive=None,
    ):
        if not self.asarva_issue:
            return

        conditions = [
            "parent.asarva_issue = %(issue)s",
            "parent.docstatus < 2",
        ]

        values = {
            "issue": self.asarva_issue,
        }

        if exclude_receive:
            conditions.append(
                "parent.name != %(exclude_receive)s"
            )

            values["exclude_receive"] = (
                exclude_receive
            )

        total_received = frappe.db.sql(
            f"""
            SELECT
                COALESCE(
                    SUM(item.received_weight),
                    0
                )
            FROM `tabAsarva Receive Item` item
            INNER JOIN `tabAsarva Receive` parent
                ON parent.name = item.parent
            WHERE {' AND '.join(conditions)}
            """,
            values,
        )[0][0]

        issue = frappe.db.get_value(
            "Asarva Issue",
            self.asarva_issue,
            [
                "docstatus",
                "expected_received_weight",
            ],
            as_dict=True,
        )

        if not issue:
            return

        total_received = flt(
            total_received,
            3,
        )

        expected = flt(
            issue.expected_received_weight,
            3,
        )

        balance = max(
            0,
            flt(
                expected - total_received,
                3,
            ),
        )

        if issue.docstatus == 2:
            status = "Cancelled"

        elif total_received <= 0:
            status = (
                "Issued"
                if issue.docstatus == 1
                else "Draft"
            )

        elif (
            expected > 0
            and total_received >= expected
        ):
            status = "Received"

        else:
            status = "Partially Received"

        frappe.db.set_value(
            "Asarva Issue",
            self.asarva_issue,
            {
                "total_received_weight":
                    total_received,
                "balance_expected_weight":
                    balance,
                "status": status,
            },
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
            "Asarva Issue",
            self.asarva_issue,
        )

        # -----------------------------------------------------
        # 1. Consume the exact AUR WIP that Asarva Issue moved
        #    into the Process To Department.
        # -----------------------------------------------------

        for issue_row in (
            issue.issue_items
            or []
        ):

            required = flt(
                issue_row.issued_weight
            )

            if (
                not issue_row.product
                or required <= 0
            ):
                continue

            if not issue_row.stock_source:
                frappe.throw(
                    _(
                        "Asarva Issue row #{0} does "
                        "not contain Stock Source lineage."
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
                    "Asarva WIP consumed during "
                    "Receive / transformation"
                ),
            )

        # -----------------------------------------------------
        # 2. Create new physical stock sources for actual
        #    Process Output Products, e.g. DATA.
        # -----------------------------------------------------

        for row in (
            self.receive_items
            or []
        ):

            qty = flt(
                row.received_weight
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
                        "Asarva Process Output "
                        "received"
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
                        "Asarva output received "
                        f"in {issue.to_department}"
                    ),
            }).insert(
                ignore_permissions=True
            )


# =============================================================
# CLIENT FETCH METHOD
# =============================================================

@frappe.whitelist()
def get_asarva_issue_details(issue_name):
    if not issue_name:
        return {}

    issue = frappe.get_doc(
        "Asarva Issue",
        issue_name,
    )

    if issue.docstatus != 1:
        frappe.throw(
            _(
                "Asarva Issue {0} must be "
                "submitted."
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

    colours = {
        row.colour
        for row in (
            issue.issue_items
            or []
        )
        if row.colour
    }

    default_colour = (
        next(iter(colours))
        if len(colours) == 1
        else None
    )

    one_output = (
        len(outputs) == 1
    )

    items = []

    for output in outputs:

        product_uom = (
            frappe.db.get_value(
                "Product Master",
                output.product,
                "unit",
            )
            or "KG"
        )

        items.append({
            "source_issue_item":
                None,

            "product":
                output.product,

            "product_quality":
                issue.quality_code,

            "colour":
                default_colour,

            "issued_weight":
                (
                    flt(
                        issue.total_issued_weight
                    )
                    if one_output
                    else 0
                ),

            "uom":
                product_uom,
        })

    return {
        "company":
            issue.company,

        "asarva_outsourcer":
            issue.asarva_outsourcer,

        "batch_no":
            issue.batch_no,

        "process_master":
            issue.process_master,

        "quality_code":
            issue.quality_code,

        "items":
            items,
    }


# =============================================================
# ASARVA ISSUE LINK QUERY
# =============================================================

@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def asarva_issue_query(
    doctype,
    txt,
    searchfield,
    start,
    page_len,
    filters,
):
    filters = filters or {}

    current_receive = (
        filters.get("current_receive")
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

                ' | Outsourcer: ',
                COALESCE(
                    issue.asarva_outsourcer,
                    ''
                ),

                ' | Expected: ',
                FORMAT(
                    issue.expected_received_weight,
                    3
                ),

                ' KG | Received: ',
                FORMAT(
                    issue.total_received_weight,
                    3
                ),

                ' KG | Status: ',
                issue.status
            ) AS description

        FROM `tabAsarva Issue` issue

        WHERE issue.docstatus = 1

          AND issue.status != 'Cancelled'

          AND NOT EXISTS (
              SELECT 1
              FROM `tabAsarva Receive` receive_doc
              WHERE
                  receive_doc.asarva_issue =
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

              OR COALESCE(
                  issue.asarva_outsourcer,
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
