import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


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

    def on_submit(self):
        self.refresh_issue_totals()

    def on_cancel(self):
        self.refresh_issue_totals()

    def on_trash(self):
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
        self.batch_no = issue.batch_no
        self.process_master = issue.process_master
        self.quality_code = issue.quality_code

        # Do NOT rebuild rows every time the document saves.
        #
        # Existing Receive rows belong to the Receive transaction
        # and are allowed to be greater than Issue row count.
        if self.receive_items:
            return

        # Initial convenience rows:
        # create one starting Receive row per Issue row.
        #
        # User can freely add more rows afterwards.
        for issue_row in issue.issue_items or []:
            row = self.append(
                "receive_items",
                {},
            )

            row.source_issue_item = issue_row.name
            row.product = issue_row.product
            row.product_quality = (
                issue_row.product_quality
            )
            row.colour = issue_row.colour
            row.issued_weight = flt(
                issue_row.issued_weight
            )

            row.quantity_firka = 0
            row.gross_weight = 0
            row.baad_weight = 0
            row.received_weight = 0
            row.uom = "KG"

    # =========================================================
    # RECEIVE ROW VALIDATION
    # =========================================================

    def validate_items(self):
        if not self.receive_items:
            frappe.throw(
                _("At least one Receive Item is required.")
            )

        # Products may be split into any number of Receive rows,
        # but a completely unrelated Product must not be received
        # against this Issue.
        allowed_products = set(
            frappe.get_all(
                "Asarva Issue Item",
                filters={
                    "parent": self.asarva_issue,
                    "parenttype": "Asarva Issue",
                },
                pluck="product",
            )
        )

        for row in self.receive_items:

            if not row.product:
                frappe.throw(
                    _(
                        "Product is required in row #{0}."
                    ).format(row.idx)
                )

            if (
                allowed_products
                and row.product not in allowed_products
            ):
                frappe.throw(
                    _(
                        "Product {0} in row #{1} was not "
                        "issued in Asarva Issue {2}."
                    ).format(
                        frappe.bold(row.product),
                        row.idx,
                        frappe.bold(
                            self.asarva_issue
                        ),
                    )
                )

            if int(row.quantity_firka or 0) < 0:
                frappe.throw(
                    _(
                        "Quantity Firka cannot be negative "
                        "in row #{0}."
                    ).format(row.idx)
                )

            gross = flt(row.gross_weight)
            baad = flt(row.baad_weight)

            if gross < 0:
                frappe.throw(
                    _(
                        "G.W cannot be negative in row #{0}."
                    ).format(row.idx)
                )

            if baad < 0:
                frappe.throw(
                    _(
                        "Baad cannot be negative in row #{0}."
                    ).format(row.idx)
                )

            if baad > gross:
                frappe.throw(
                    _(
                        "Baad cannot exceed G.W in row #{0}."
                    ).format(row.idx)
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
                "Asarva Issue {0} must be submitted."
            ).format(
                frappe.bold(issue_name)
            )
        )

    return {
        "company": issue.company,

        "asarva_outsourcer":
            issue.asarva_outsourcer,

        "batch_no":
            issue.batch_no,

        "process_master":
            issue.process_master,

        "quality_code":
            issue.quality_code,

        "items": [
            {
                "source_issue_item":
                    row.name,

                "product":
                    row.product,

                "product_quality":
                    row.product_quality,

                "colour":
                    row.colour,

                "issued_weight":
                    flt(row.issued_weight),

                "uom":
                    row.uom or "KG",
            }
            for row in issue.issue_items or []
        ],
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
