import frappe
from frappe.model.document import Document
from frappe.utils import flt


class SpindalReceive(Document):

    def validate(self):
        self.validate_duplicate_submitted_receive()
        self.fetch_peti_entries()
        self.calculate_totals()

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

    def fetch_peti_entries(self):
        if not self.spindal_issue:
            return

        if self.received_peti_items:
            return

        petis = get_spindal_peti_entries(self.spindal_issue)

        for peti in petis:
            row = self.append("received_peti_items", {})
            row.spindal_peti_entry = peti.get("name")
            row.peti_no = peti.get("name")
            row.batch_no = peti.get("batch_no")
            row.quality_code = peti.get("quality_code")
            row.khata_no = peti.get("khata_no")
            row.gross_weight = flt(peti.get("gross_weight"))
            row.baad_weight = flt(peti.get("baad_weight"))
            row.net_weight = flt(peti.get("net_weight"))

    def calculate_totals(self):
        total_net = 0

        for row in self.received_peti_items or []:
            total_net += flt(row.net_weight)

        if hasattr(self, "total_net_weight"):
            self.total_net_weight = total_net

        if hasattr(self, "total_receive_weight"):
            self.total_receive_weight = total_net


@frappe.whitelist()
def get_spindal_peti_entries(spindal_issue):
    issue = frappe.get_doc("Spindal Issue", spindal_issue)

    return frappe.get_all(
        "Spindal Peti Entry",
        filters={
            "spindal_issue": spindal_issue,
            "batch_no": issue.active_batch_no,
            "docstatus": 1
        },
        fields=[
            "name",
            "spindal_issue",
            "batch_no",
            "quality_code",
            "khata_no",
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
                ' | Issue: ', si.name,
                ' | Date: ', DATE_FORMAT(COALESCE(si.issue_date, si.creation), '%%d-%%m-%%Y')
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
        ORDER BY si.creation DESC
        LIMIT %(start)s, %(page_len)s
    """, {
        "txt": f"%{txt}%",
        "start": start,
        "page_len": page_len
    })
