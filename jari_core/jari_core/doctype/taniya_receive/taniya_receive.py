import json

import frappe
from frappe.model.document import Document
from frappe.utils import flt, today


class TaniyaReceive(Document):

    def validate(self):
        self.validate_duplicate_submitted_receive()
        self.pull_issue_details()
        self.validate_items()
        self.calculate_output_net_weights()
        self.calculate_totals()
        self.set_approx_silver()
        self.apply_payout_if_outsourced()

    def is_outsourced_process(self):
        """
        Return whether the linked Process Master is outsourced.

        Payout calculation is applicable only to outsourced processes.
        """
        if not self.process_master:
            return False

        return bool(
            frappe.db.get_value(
                "Process Master",
                self.process_master,
                "is_outsourced",
            )
        )

    def clear_payout_values(self):
        """
        Prevent stale outsourced payout values from remaining on an
        in-house Taniya Receive.
        """
        self.payout_format = None
        self.majoori_rate = 0
        self.estimated_goti = 0
        self.estimated_aur = 0
        self.majoori_on = 0
        self.calculated_payout_amount = 0
        self.payout_summary = ""

    def apply_payout_if_outsourced(self):
        """
        Apply Taniya payout only when Process Master is outsourced.

        In-house processing continues through the normal Issue/Receive
        workflow without any payout dependency.
        """
        if not self.is_outsourced_process():
            self.clear_payout_values()
            return

        from jari_core.jari_core import payout_utils

        calculator = getattr(
            payout_utils,
            "calculate_taniya_payout",
            None,
        )

        if not callable(calculator):
            frappe.throw(
                "This Taniya process is marked as Outsourced, but the "
                "Taniya payout calculator is not configured. Please "
                "restore calculate_taniya_payout in payout_utils.py "
                "before saving an outsourced Taniya Receive."
            )

        calculator(self)

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
            WHERE docstatus IN (0, 1)
              AND batch_no = %s
        """, self.batch_no)[0][0]

        self.total_input_weight = flt(total)

    def validate_items(self):
        if not self.output_items and not self.waste_items:
            frappe.throw("At least one output or waste item is required.")

    def calculate_output_net_weights(self):
        """
        Validate Quantity and calculate final DATA weight.

        N.W (DATA) = Received Weight - Baad Weight
        """
        for row_number, row in enumerate(
            self.output_items or [],
            start=1
        ):
            quantity = int(row.quantity or 0)
            received_weight = flt(row.weight)
            baad_weight = flt(row.baad_weight)

            if not row.product and not received_weight:
                row.baad_weight = 0
                row.net_weight = 0
                continue

            if quantity <= 0:
                frappe.throw(
                    f"Quantity must be greater than zero in "
                    f"Out Product Detail Row #{row_number}."
                )

            if received_weight <= 0:
                frappe.throw(
                    f"Received Weight must be greater than zero in "
                    f"Out Product Detail Row #{row_number}."
                )

            if baad_weight < 0:
                frappe.throw(
                    f"Baad Weight cannot be negative in "
                    f"Out Product Detail Row #{row_number}."
                )

            piece_weights = self.get_piece_baad_weights(
                row,
                row_number,
            )

            if piece_weights is not None:
                if len(piece_weights) != quantity:
                    frappe.throw(
                        f"Baad Weight entry count must match "
                        f"Quantity in Out Product Detail "
                        f"Row #{row_number}. Expected {quantity}, "
                        f"found {len(piece_weights)}."
                    )

                calculated_baad_weight = flt(
                    sum(piece_weights),
                    3,
                )

                if abs(
                    calculated_baad_weight - baad_weight
                ) > 0.001:
                    frappe.throw(
                        f"Baad Weight total does not match the "
                        f"piece-wise entries in Out Product Detail "
                        f"Row #{row_number}. Expected "
                        f"{calculated_baad_weight:.3f}, found "
                        f"{baad_weight:.3f}."
                    )

            if baad_weight > received_weight:
                frappe.throw(
                    f"Baad Weight {baad_weight:.3f} cannot exceed "
                    f"Received Weight {received_weight:.3f} in "
                    f"Out Product Detail Row #{row_number}."
                )

            row.net_weight = flt(
                received_weight - baad_weight,
                3
            )

            if row.net_weight <= 0:
                frappe.throw(
                    f"N.W (DATA) must be greater than zero in "
                    f"Out Product Detail Row #{row_number}."
                )

    def get_piece_baad_weights(
        self,
        row,
        row_number,
    ):
        """
        Return saved piece-wise Baad Weight values.

        None means this is a legacy row created before piece details
        were persisted. Such historical rows remain compatible.
        """
        raw_details = row.get(
            "baad_weight_details"
        )

        if not raw_details:
            return None

        try:
            values = (
                json.loads(raw_details)
                if isinstance(raw_details, str)
                else raw_details
            )
        except (TypeError, ValueError):
            frappe.throw(
                f"Invalid Baad Weight Details in "
                f"Out Product Detail Row #{row_number}."
            )

        if not isinstance(values, list):
            frappe.throw(
                f"Baad Weight Details must be a list in "
                f"Out Product Detail Row #{row_number}."
            )

        normalized = []

        for piece_number, value in enumerate(
            values,
            start=1,
        ):
            weight = flt(value)

            if weight < 0:
                frappe.throw(
                    f"Piece {piece_number} Baad Weight cannot "
                    f"be negative in Out Product Detail "
                    f"Row #{row_number}."
                )

            normalized.append(weight)

        return normalized

    def get_quality_purity(self):
        if not self.quality_code:
            return 0
        return flt(frappe.db.get_value("Quality Master", self.quality_code, "silver_purity_percent") or 0)

    def calculate_totals(self):
        output_total = sum(
            flt(row.net_weight)
            for row in self.output_items or []
        )

        waste_total = sum(
            flt(row.weight)
            for row in self.waste_items or []
        )

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
        return flt(weight) - (flt(weight) * flt(purity) / 100)

    def set_approx_silver(self):
        purity = self.get_quality_purity()

        output_approx = 0
        wastage_approx = 0

        for row in self.output_items or []:
            output_weight = flt(row.net_weight)

            row.approx_silver_weight = (
                output_weight
                - (
                    output_weight
                    * flt(purity)
                    / 100
                )
            )

            output_approx += flt(
                row.approx_silver_weight
            )

        for row in self.waste_items or []:
            row.approx_silver_weight = flt(row.weight) - (flt(row.weight) * flt(purity) / 100)
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

        for row in self.output_items or []:
            output_weight = flt(row.net_weight)

            if not row.product or output_weight <= 0:
                continue

            balance = self.get_last_balance(
                self.company,
                "Taniya",
                row.product
            )

            frappe.get_doc({
                "doctype": "Inventory Ledger",
                "company": self.company,
                "department": "Taniya",
                "product": row.product,
                "batch_number": self.batch_no,
                "in_weight": output_weight,
                "out_weight": 0,
                "current_balance": (
                    flt(balance) + output_weight
                ),
                "approx_silver_weight": flt(row.approx_silver_weight),
                "transaction_type": "Production Output",
                "reference_doctype": self.doctype,
                "reference_name": self.name,
                "date": self.receive_date or today(),
                "remarks": (
                    "Taniya DATA output received after "
                    "Baad Weight deduction"
                )
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
                ' | Date: ', DATE_FORMAT(COALESCE(ti.issue_date, ti.creation), '%%d-%%m-%%Y'),
                ' | Status: ', IF(ti.docstatus = 0, 'Saved', 'Submitted')
            ) AS description
        FROM `tabTaniya Issue` ti
        WHERE ti.docstatus IN (0, 1)
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
