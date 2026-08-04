import frappe
from frappe.model.document import Document
from frappe.utils import flt
from jari_core.jari_core.stock_utils import (
from jari_core.jari_core.doctype.process_master.process_master import (
    apply_process_department_defaults,
)
    add_wip_transfer_in,
    consume_issueable_stock,
    get_issueable_sources,
)


class SpindalIssue(Document):

    def validate(self):
        self.set_defaults()
        self.set_active_batch_no()
        self.validate_issue_items()
        self.validate_draft_stock_availability()
        self.calculate_totals()

    def on_submit(self):
        self.post_inventory_transfer()
        self.set_issue_status()

    def set_defaults(self):
        if not self.from_department:
            self.from_department = "Taniya"
        if not self.to_department:
            self.to_department = "Spindal"
        if not self.issue_type:
            self.issue_type = "New Batch"
        if self.is_active_batch is None:
            self.is_active_batch = 1

    def set_active_batch_no(self):
        if self.issue_type == "New Batch":
            if not self.new_batch_no:
                frappe.throw("New Batch No is required.")
            self.active_batch_no = self.new_batch_no
        elif self.issue_type == "Re Issue":
            if not self.existing_batch_no:
                frappe.throw("Existing Batch No is required for Re Issue.")
            self.active_batch_no = self.existing_batch_no

        if not self.active_batch_no:
            frappe.throw("Active Batch No is required.")

    def set_issue_status(self):
        previous_issued = frappe.db.count(
            "Spindal Issue",
            {"active_batch_no": self.active_batch_no, "docstatus": 1, "name": ["!=", self.name]}
        )
        status = "Re Issue" if previous_issued or self.issue_type == "Re Issue" else "Issued"
        frappe.db.set_value(self.doctype, self.name, "status", status)

    def get_issue_items(self):
        return self.issue_items or []

    def get_row_weight(self, row):
        return flt(row.weight)

    def validate_issue_items(self):
        items = self.get_issue_items()

        if not items:
            frappe.throw("At least one Issue Product Detail row is required.")

        for row in items:
            if not row.product:
                frappe.throw("Product is required in Issue Product Detail.")
            if self.get_row_weight(row) <= 0:
                frappe.throw(f"Weight must be greater than zero for product {row.product}.")

    def validate_draft_stock_availability(self):
        """
        Reserve stock logically while Spindal Issue is saved as Draft.

        Inventory Ledger remains untouched until Submit.

        Available quantity =
            physical issueable stock
            - reservations in OTHER saved Spindal Issue drafts.
        """
        if not self.company:
            return

        required_by_product = {}

        for row in self.get_issue_items():
            if not row.product:
                continue

            required_by_product[row.product] = (
                flt(required_by_product.get(row.product))
                + self.get_row_weight(row)
            )

        for product, required_qty in required_by_product.items():
            sources = get_issueable_sources(
                self.company,
                product,
                self.from_department,
            )

            physical_available = sum(
                flt(source.get("balance"))
                for source in sources
            )

            reserved_by_other_drafts = (
                get_spindal_draft_reserved_weight(
                    company=self.company,
                    product=product,
                    exclude_name=self.name,
                )
            )

            available_to_this_document = max(
                0,
                physical_available
                - reserved_by_other_drafts,
            )

            if required_qty > available_to_this_document + 0.000001:
                frappe.throw(
                    f"Insufficient available stock for {product}. "
                    f"Physical Stock: {physical_available:.3f} KG, "
                    f"Reserved in Other Draft Spindal Issues: "
                    f"{reserved_by_other_drafts:.3f} KG, "
                    f"Available: {available_to_this_document:.3f} KG, "
                    f"Requested: {required_qty:.3f} KG."
                )

    def calculate_totals(self):
        self.total_issue_weight = sum(self.get_row_weight(row) for row in self.get_issue_items())

    def ledger_exists(self):
        return frappe.db.exists(
            "Inventory Ledger",
            {"reference_doctype": self.doctype, "reference_name": self.name}
        )

    def post_inventory_transfer(self):
        if self.ledger_exists():
            return

        for row in self.get_issue_items():
            product = row.product
            weight = self.get_row_weight(row)

            consume_issueable_stock(
                doc=self,
                product=product,
                required_qty=weight,
                batch_no=self.active_batch_no,
                posting_date=self.issue_date,
                preferred_department=self.from_department,
                remarks="Spindal material issued from issueable stock"
            )

            add_wip_transfer_in(
                doc=self,
                department=self.to_department,
                product=product,
                qty=weight,
                batch_no=self.active_batch_no,
                posting_date=self.issue_date,
                remarks="Spindal material inward as WIP"
            )


def get_spindal_draft_reserved_weight(
    company,
    product,
    exclude_name=None,
    department=None,
):
    """
    Return weight reserved by saved Draft Spindal Issues.

    Drafts do not post to Inventory Ledger, so this provides a
    reservation layer without mutating physical stock.
    """
    if not company or not product:
        return 0

    conditions = [
        "si.docstatus = 0",
        "si.company = %(company)s",
        "sii.product = %(product)s",
    ]

    values = {
        "company": company,
        "product": product,
    }

    if exclude_name:
        conditions.append("si.name != %(exclude_name)s")
        values["exclude_name"] = exclude_name

    if department:
        conditions.append(
            "si.from_department = %(department)s"
        )
        values["department"] = department

    reserved = frappe.db.sql(
        """
        SELECT COALESCE(SUM(sii.weight), 0)
        FROM `tabSpindal Issue Item` sii
        INNER JOIN `tabSpindal Issue` si
            ON si.name = sii.parent
        WHERE {conditions}
        """.format(
            conditions=" AND ".join(conditions)
        ),
        values,
    )[0][0]

    return flt(reserved)


@frappe.whitelist()
def get_spindal_stock_summary(product, company=None):
    """
    Show physical stock less saved Draft Spindal Issue reservations.

    Physical Inventory Ledger is still changed only on Submit.
    """
    if not product:
        return ""

    conditions = [
        "product = %(product)s",
    ]

    values = {
        "product": product,
    }

    if company:
        conditions.append(
            "company = %(company)s"
        )
        values["company"] = company

    rows = frappe.db.sql(
        """
        SELECT
            latest.company,
            latest.department,
            latest.current_balance
        FROM `tabInventory Ledger` latest
        INNER JOIN (
            SELECT
                company AS c,
                department AS d,
                product AS p,
                MAX(creation) AS max_creation
            FROM `tabInventory Ledger`
            WHERE {conditions}
            GROUP BY
                company,
                department,
                product
        ) x
            ON latest.company = x.c
            AND latest.department = x.d
            AND latest.product = x.p
            AND latest.creation = x.max_creation
        WHERE latest.current_balance > 0
        ORDER BY
            latest.company,
            latest.department
        """.format(
            conditions=" AND ".join(conditions)
        ),
        values,
        as_dict=True,
    )

    lines = []

    for row in rows:
        reserved = get_spindal_draft_reserved_weight(
            company=row.company,
            product=product,
            department=row.department,
        )

        available = max(
            0,
            flt(row.current_balance)
            - flt(reserved),
        )

        lines.append(
            f"{row.company} | {row.department} "
            f"- {flt(available, 3)} KG"
        )

    return (
        "\n".join(lines)
        if lines
        else "No stock available"
    )
