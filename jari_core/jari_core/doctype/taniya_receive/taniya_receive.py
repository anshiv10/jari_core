import frappe
from frappe.model.document import Document
from frappe.utils import flt, today


class TaniyaReceive(Document):

    def validate(self):
        self.validate_duplicate_submitted_receive()
        self.pull_issue_details()
        self.validate_items()
        self.calculate_totals()
        self.set_approx_silver()

    def validate_duplicate_submitted_receive(self):
        if not self.taniya_issue:
            return

        exists = frappe.db.exists(
            "Taniya Receive",
            {
                "taniya_issue": self.taniya_issue,
                "docstatus": 1,
                "name": ["!=", self.name]
            }
        )

        if exists:
            frappe.throw(f"Taniya Issue {self.taniya_issue} is already received in submitted Taniya Receive {exists}.")

    def on_submit(self):
        self.set_approx_silver()
        self.db_set('approx_silver_weight', flt(self.approx_silver_weight))
        self.post_outputs_and_waste()
        self.mark_batch_issues_partially_received()

    def pull_issue_details(self):
        if not self.taniya_issue:
            return

        issue = frappe.get_doc("Taniya Issue", self.taniya_issue)

        self.company = issue.company
        self.batch_no = issue.batch_no
        self.process_master = issue.process_master
        self.quality_code = issue.quality_code
        self.operator = issue.operator

        # IMPORTANT: total input from ALL submitted Taniya Issues of same batch
        total = frappe.db.sql("""
            SELECT SUM(total_issue_weight)
            FROM `tabTaniya Issue`
            WHERE docstatus = 1
              AND batch_no = %s
        """, self.batch_no)[0][0]

        self.total_input_weight = flt(total)

    def validate_items(self):
        if not self.output_items and not self.waste_items:
            frappe.throw("At least one output or waste item is required.")

    def get_quality_purity(self):
        if not self.quality_code:
            return 0
        return flt(frappe.db.get_value("Quality Master", self.quality_code, "silver_purity_percent") or 0)

    def calculate_totals(self):
        output_total = sum(flt(row.weight) for row in self.output_items)
        waste_total = sum(flt(row.weight) for row in self.waste_items)

        self.total_output_weight = output_total
        self.total_waste_weight = waste_total
        self.current_wastage_percent = waste_total / flt(self.total_input_weight) * 100 if flt(self.total_input_weight) else 0
        self.loss_weight = flt(self.total_input_weight) - output_total - waste_total
        self.loss_percent = self.loss_weight / flt(self.total_input_weight) * 100 if flt(self.total_input_weight) else 0

        self.loss_standard_percent = frappe.db.get_value(
            "Loss Standard Master", {"department": "Taniya"}, "standard_loss_percent"
        ) or 0

        self.loss_status = "Excess Loss" if flt(self.loss_percent) > flt(self.loss_standard_percent) else "OK"

    def calculate_approx_silver(self, weight):
        purity = self.get_quality_purity() if hasattr(self, "get_quality_purity") else 0
        return flt(weight) * flt(purity) / 100

    def set_approx_silver(self):
        purity = self.get_quality_purity()

        output_approx = 0
        wastage_approx = 0

        for row in self.output_items or []:
            row.approx_silver_weight = flt(row.weight) * flt(purity) / 100
            output_approx += flt(row.approx_silver_weight)

        for row in self.waste_items or []:
            row.approx_silver_weight = flt(row.weight) * flt(purity) / 100
            wastage_approx += flt(row.approx_silver_weight)

        self.approx_silver_output = output_approx
        self.approx_silver_wastage = wastage_approx
        self.approx_silver_weight = output_approx + wastage_approx

    def get_last_balance(self, company, department, product):
        return frappe.db.get_value(
            "Inventory Ledger",
            {"company": company, "department": department, "product": product},
            "current_balance",
            order_by="creation desc"
        ) or 0

    def ledger_exists(self):
        return frappe.db.exists("Inventory Ledger", {
            "reference_doctype": self.doctype,
            "reference_name": self.name
        })

    def post_outputs_and_waste(self):
        if self.ledger_exists():
            return

        for row in self.output_items:
            if not row.product or not flt(row.weight):
                continue

            balance = self.get_last_balance(self.company, "Taniya", row.product)

            frappe.get_doc({
                "doctype": "Inventory Ledger",
                "company": self.company,
                "department": "Taniya",
                "product": row.product,
                "batch_number": self.batch_no,
                "in_weight": flt(row.weight),
                "out_weight": 0,
                "current_balance": flt(balance) + flt(row.weight),
                "approx_silver_weight": flt(row.approx_silver_weight),
                "transaction_type": "Production Output",
                "reference_doctype": self.doctype,
                "reference_name": self.name,
                "date": self.receive_date or today(),
                "remarks": "Taniya output received"
            }).insert(ignore_permissions=True)

        for row in self.waste_items:
            if not row.waste_product or not flt(row.weight):
                continue

            balance = self.get_last_balance(self.company, "Taniya", row.waste_product)

            frappe.get_doc({
                "doctype": "Inventory Ledger",
                "company": self.company,
                "department": "Taniya",
                "product": row.waste_product,
                "batch_number": self.batch_no,
                "in_weight": flt(row.weight),
                "out_weight": 0,
                "current_balance": flt(balance) + flt(row.weight),
                "approx_silver_weight": flt(row.approx_silver_weight),
                "transaction_type": "Waste Generated",
                "reference_doctype": self.doctype,
                "reference_name": self.name,
                "date": self.receive_date or today(),
                "remarks": "Taniya waste generated"
            }).insert(ignore_permissions=True)

    def mark_batch_issues_partially_received(self):
        if not self.batch_no:
            return

        issues = frappe.get_all(
            "Taniya Issue",
            filters={"batch_no": self.batch_no, "docstatus": 1},
            pluck="name"
        )

        for issue in issues:
            frappe.db.set_value("Taniya Issue", issue, "status", "Partially Received")


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def taniya_issue_query(doctype, txt, searchfield, start, page_len, filters):
    return frappe.db.sql("""
        SELECT
            ti.name,
            CONCAT(
                'Batch: ', COALESCE(ti.batch_no, ti.new_batch_no, ti.name),
                ' | Issue: ', ti.name,
                ' | Date: ', DATE_FORMAT(COALESCE(ti.issue_date, ti.creation), '%%d-%%m-%%Y')
            ) AS description
        FROM `tabTaniya Issue` ti
        WHERE ti.docstatus = 1
          AND NOT EXISTS (
              SELECT 1
              FROM `tabTaniya Receive` tr
              WHERE tr.docstatus = 1
                AND tr.taniya_issue = ti.name
          )
          AND (
              ti.name LIKE %(txt)s
              OR COALESCE(ti.batch_no, '') LIKE %(txt)s
              OR COALESCE(ti.new_batch_no, '') LIKE %(txt)s
              OR COALESCE(ti.company, '') LIKE %(txt)s
          )
        ORDER BY ti.creation DESC
        LIMIT %(start)s, %(page_len)s
    """, {
        "txt": f"%{txt}%",
        "start": start,
        "page_len": page_len
    })
