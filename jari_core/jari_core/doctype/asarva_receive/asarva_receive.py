
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, today


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

    def validate_issue(self):
        if not self.asarva_issue:
            return

        issue_status = frappe.db.get_value(
            "Asarva Issue",
            self.asarva_issue,
            "docstatus",
        )

        if issue_status == 2:
            frappe.throw(
                _(
                    "Cancelled Asarva Issue {0} cannot "
                    "be selected."
                ).format(
                    frappe.bold(self.asarva_issue)
                )
            )

        if self.docstatus == 1 and issue_status != 1:
            frappe.throw(
                _(
                    "Asarva Issue {0} must be submitted "
                    "before submitting this Receive."
                ).format(
                    frappe.bold(self.asarva_issue)
                )
            )

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

        if self.receive_items:
            return

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

    def validate_items(self):
        if not self.receive_items:
            frappe.throw(
                _("At least one Receive Item is required.")
            )

        for row in self.receive_items:
            if not row.product:
                frappe.throw(
                    _(
                        "Product is required in row #{0}."
                    ).format(row.idx)
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
            SELECT COALESCE(
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


@frappe.whitelist()
def get_asarva_issue_details(issue_name):
    if not issue_name:
        return {}

    issue = frappe.get_doc(
        "Asarva Issue",
        issue_name,
    )

    return {
        "company": issue.company,
        "asarva_outsourcer":
            issue.asarva_outsourcer,
        "batch_no": issue.batch_no,
        "process_master": issue.process_master,
        "quality_code": issue.quality_code,
        "items": [
            {
                "source_issue_item": row.name,
                "product": row.product,
                "product_quality":
                    row.product_quality,
                "colour": row.colour,
                "issued_weight": flt(
                    row.issued_weight
                ),
                "uom": row.uom or "KG",
            }
            for row in issue.issue_items or []
        ],
    }


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
    return frappe.db.sql(
        """
        SELECT
            issue.name,
            CONCAT(
                'Batch: ',
                COALESCE(issue.batch_no, ''),
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
        WHERE issue.docstatus IN (0, 1)
          AND issue.status != 'Cancelled'
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
            "txt": f"%{txt}%",
            "start": start,
            "page_len": page_len,
        },
    )
