import frappe
from frappe.model.document import Document
from frappe.utils import flt, today


def get_kasab_product():
    product = frappe.db.get_value("Product Master", {"product_tag": "KASAB"}, "name")
    if product:
        return product

    if frappe.db.exists("Product Master", "KASAB"):
        return "KASAB"

    product = frappe.db.get_value("Product Master", {"product_name": ["like", "%kasab%"]}, "name")
    if product:
        return product

    frappe.throw("KASAB product not found in Product Master. Please set Product Tag = KASAB in Product Master.")


class SpindalReceive(Document):

    def validate(self):
        self.validate_duplicate_submitted_receive()
        self.pull_issue_details()
        self.fetch_peti_entries()
        self.normalize_product_links()
        self.calculate_totals()
        self.set_approx_silver()

        from jari_core.jari_core.payout_utils import calculate_spindal_payout
        calculate_spindal_payout(self)

    def on_submit(self):
        self.post_inventory_ledgers()

    def validate_duplicate_submitted_receive(self):
        if not self.spindal_issue:
            return

        exists = frappe.db.exists(
            "Spindal Receive",
            {
                "spindal_issue": self.spindal_issue,
                "docstatus": 1,
                "name": ["!=", self.name]
            }
        )

        if exists:
            frappe.throw(f"Spindal Issue {self.spindal_issue} is already received in submitted Spindal Receive {exists}.")

    def pull_issue_details(self):
        if not self.spindal_issue:
            return

        issue = frappe.get_doc("Spindal Issue", self.spindal_issue)

        self.company = issue.company
        self.active_batch_no = issue.active_batch_no
        self.process_master = issue.process_master
        self.quality_code = issue.quality_code
        self.operator = issue.operator

        total = frappe.db.sql("""
            SELECT SUM(total_issue_weight)
            FROM `tabSpindal Issue`
            WHERE docstatus = 1
              AND active_batch_no = %s
        """, self.active_batch_no)[0][0]

        self.total_input_weight = flt(total)

    def fetch_peti_entries(self):
        if not self.spindal_issue:
            return

        if self.received_peti_items:
            return

        kasab = get_kasab_product()
        petis = get_spindal_peti_entries(self.spindal_issue)

        for peti in petis:
            row = self.append("received_peti_items", {})
            row.peti_no = peti.get("name")
            row.product = kasab
            row.uom = peti.get("uom") or "gram"
            row.gross_weight = flt(peti.get("gross_weight"))
            row.net_weight = flt(peti.get("net_weight"))

    def normalize_product_links(self):
        kasab = get_kasab_product()

        for row in self.received_peti_items or []:
            row.product = kasab

    def calculate_totals(self):
        total_net = sum(flt(row.net_weight) for row in self.received_peti_items or [])

        self.total_received_weight = total_net
        self.total_waste_weight = sum(flt(row.weight) for row in self.waste_items or [])
        self.loss_weight = flt(self.total_input_weight) - flt(self.total_received_weight) - flt(self.total_waste_weight)

        if flt(self.total_input_weight):
            self.loss_percent = flt(self.loss_weight) / flt(self.total_input_weight) * 100
        else:
            self.loss_percent = 0

        self.loss_standard_percent = frappe.db.get_value(
            "Loss Standard Master", {"department": "Spindal"}, "standard_loss_percent"
        ) or 0

        self.loss_status = "Excess Loss" if flt(self.loss_percent) > flt(self.loss_standard_percent) else "OK"

    def get_quality_purity(self):
        if not self.quality_code:
            return 0

        return flt(frappe.db.get_value("Quality Master", self.quality_code, "silver_purity_percent") or 0)

    def set_approx_silver(self):
        purity = self.get_quality_purity()

        output_approx = flt(self.total_received_weight) - (flt(self.total_received_weight) * flt(purity) / 100)
        wastage_approx = 0

        for row in self.waste_items or []:
            if hasattr(row, "approx_silver_weight"):
                row.approx_silver_weight = flt(row.weight) - (flt(row.weight) * flt(purity) / 100)
                wastage_approx += flt(row.approx_silver_weight)

        self.approx_silver_output = output_approx
        self.approx_silver_wastage = wastage_approx
        self.approx_silver_weight = output_approx + wastage_approx

    def get_last_balance(self, company, department, product):
        return frappe.db.get_value(
            "Inventory Ledger",
            {
                "company": company,
                "department": department,
                "product": product
            },
            "current_balance",
            order_by="creation desc"
        ) or 0

    def ledger_exists(self):
        return frappe.db.exists(
            "Inventory Ledger",
            {
                "reference_doctype": self.doctype,
                "reference_name": self.name
            }
        )

    def add_ledger(self, department, product, in_weight, out_weight, transaction_type, remarks):
        if not product or (not flt(in_weight) and not flt(out_weight)):
            return

        balance = self.get_last_balance(self.company, department, product)

        frappe.get_doc({
            "doctype": "Inventory Ledger",
            "company": self.company,
            "department": department,
            "product": product,
            "batch_number": self.active_batch_no,
            "in_weight": flt(in_weight),
            "out_weight": flt(out_weight),
            "current_balance": flt(balance) + flt(in_weight) - flt(out_weight),
            "transaction_type": transaction_type,
            "reference_doctype": self.doctype,
            "reference_name": self.name,
            "date": self.receive_date or today(),
            "remarks": remarks
        }).insert(ignore_permissions=True)

    def post_inventory_ledgers(self):
        if self.ledger_exists():
            return

        department = "Spindal"
        kasab = get_kasab_product()

        for row in self.received_peti_items or []:
            uom = (row.uom or "").lower()
            weight = flt(row.net_weight)

            if uom in ["gm", "gram", "grams", "g"]:
                weight = weight / 1000

            self.add_ledger(
                department=department,
                product=kasab,
                in_weight=weight,
                out_weight=0,
                transaction_type="Production Output",
                remarks="Spindal peti output received"
            )

        for row in self.waste_items or []:
            product = getattr(row, "waste_product", None)

            self.add_ledger(
                department=department,
                product=product,
                in_weight=flt(row.weight),
                out_weight=0,
                transaction_type="Waste Generated",
                remarks="Spindal waste generated"
            )


@frappe.whitelist()
def get_spindal_receive_data(spindal_issue):
    issue = frappe.get_doc("Spindal Issue", spindal_issue)

    total = frappe.db.sql("""
        SELECT SUM(total_issue_weight)
        FROM `tabSpindal Issue`
        WHERE docstatus = 1
          AND active_batch_no = %s
    """, issue.active_batch_no)[0][0]

    return {
        "company": issue.company,
        "active_batch_no": issue.active_batch_no,
        "process_master": issue.process_master,
        "quality_code": issue.quality_code,
        "operator": issue.operator,
        "total_input_weight": flt(total),
        "kasab_product": get_kasab_product(),
        "petis": get_spindal_peti_entries(spindal_issue)
    }


@frappe.whitelist()
def get_spindal_peti_entries(spindal_issue):
    issue = frappe.get_doc("Spindal Issue", spindal_issue)

    return frappe.get_all(
        "Spindal Peti Entry",
        filters={
            "spindal_issue": spindal_issue,
            "batch_no": issue.active_batch_no,
            "docstatus": 1,
            "status": ["!=", "Cancelled"]
        },
        fields=[
            "name",
            "spindal_issue",
            "batch_no",
            "quality_code",
            "khata_no",
            "uom",
            "gross_weight",
            "baad_weight",
            "net_weight"
        ],
        order_by="creation asc"
    )


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def spindal_issue_query(doctype, txt, searchfield, start, page_len, filters):
    return frappe.db.sql("""
        SELECT
            si.name,
            CONCAT(
                'Batch: ', COALESCE(si.active_batch_no, si.new_batch_no, si.name),
                ' | Date: ', DATE_FORMAT(COALESCE(si.issue_date, si.creation), '%%d-%%m-%%Y'),
                ' | Issue: ', si.name
            ) AS description
        FROM `tabSpindal Issue` si
        WHERE si.docstatus = 1
          AND EXISTS (
              SELECT 1
              FROM `tabSpindal Peti Entry` pe
              WHERE pe.docstatus = 1
                AND pe.spindal_issue = si.name
          )
          AND NOT EXISTS (
              SELECT 1
              FROM `tabSpindal Receive` sr
              WHERE sr.docstatus = 1
                AND sr.spindal_issue = si.name
          )
          AND (
              si.name LIKE %(txt)s
              OR COALESCE(si.active_batch_no, '') LIKE %(txt)s
              OR COALESCE(si.new_batch_no, '') LIKE %(txt)s
              OR COALESCE(si.company, '') LIKE %(txt)s
          )
        ORDER BY si.issue_date DESC, si.creation DESC
        LIMIT %(start)s, %(page_len)s
    """, {
        "txt": f"%{txt}%",
        "start": start,
        "page_len": page_len
    })


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def spindal_issue_for_peti_query(doctype, txt, searchfield, start, page_len, filters):
    return frappe.db.sql("""
        SELECT
            si.name,
            CONCAT(
                'Batch: ', COALESCE(si.active_batch_no, si.new_batch_no, si.name),
                ' | Date: ', DATE_FORMAT(COALESCE(si.issue_date, si.creation), '%%d-%%m-%%Y'),
                ' | Issue: ', si.name
            ) AS description
        FROM `tabSpindal Issue` si
        WHERE si.docstatus = 1
          AND NOT EXISTS (
              SELECT 1
              FROM `tabSpindal Receive` sr
              WHERE sr.docstatus = 1
                AND sr.spindal_issue = si.name
          )
          AND (
              si.name LIKE %(txt)s
              OR COALESCE(si.active_batch_no, '') LIKE %(txt)s
              OR COALESCE(si.new_batch_no, '') LIKE %(txt)s
              OR COALESCE(si.company, '') LIKE %(txt)s
          )
        ORDER BY si.issue_date DESC, si.creation DESC
        LIMIT %(start)s, %(page_len)s
    """, {
        "txt": f"%{txt}%",
        "start": start,
        "page_len": page_len
    })