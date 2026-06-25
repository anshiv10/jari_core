import frappe
from frappe.model.document import Document
from frappe.utils import flt, today


class GilitReceive(Document):

    def validate(self):
        self.pull_issue_details()
        self.validate_items()
        self.calculate_totals()

    def on_submit(self):
        self.update_peti_remaining_net_weight()
        self.post_outputs_and_waste()
        frappe.db.set_value("Gilit Issue", self.gilit_issue, "status", "Closed")

    def on_cancel(self):
        self.restore_peti_remaining_net_weight()

    def pull_issue_details(self):
        if not self.gilit_issue:
            return

        issue = frappe.get_doc("Gilit Issue", self.gilit_issue)

        self.company = issue.company
        self.active_batch_no = issue.gilit_batch_no
        self.process_master = issue.process_master
        self.quality_code = issue.quality_code
        self.operator = issue.operator
        self.total_input_weight = issue.total_net_weight

        if not self.output_items:
            for peti in issue.peti_items or []:
                total_bobbin = flt(peti.total_bobbin)
                issued_bobbin = flt(peti.issued_bobbin)
                used_net_weight = 0

                if total_bobbin and issued_bobbin:
                    used_net_weight = (flt(peti.net_weight) / total_bobbin) * issued_bobbin / 1000

                row = self.append("output_items", {})
                row.spindal_peti_entry = peti.spindal_peti_entry
                row.peti_no = peti.peti_no
                row.total_bobbin = total_bobbin
                row.issued_bobbin = issued_bobbin
                row.used_net_weight = used_net_weight
                row.uom = peti.uom
                row.weight = used_net_weight

    def validate_items(self):
        if not self.output_items and not self.waste_items:
            frappe.throw("At least one Final Jari Product/Peti Detail or Waste Item is required.")

        for row in self.output_items:
            if not row.spindal_peti_entry:
                continue

            if flt(row.used_net_weight) <= 0:
                frappe.throw("Consumed Net Weight must be greater than zero.")

            remaining = frappe.db.get_value(
                "Spindal Peti Entry",
                row.spindal_peti_entry,
                "remaining_net_weight"
            ) or 0

            if flt(row.used_net_weight) > flt(remaining):
                frappe.throw(
                    f"Consumed Net Weight cannot be greater than Remaining N.W for Peti {row.peti_no}. "
                    f"Available: {remaining}, Entered: {row.used_net_weight}"
                )

            row.weight = flt(row.used_net_weight)

        if flt(self.gross_weight_without_dabba) < 0:
            frappe.throw("G.W Without Dabba Weight cannot be negative.")

        if flt(self.firki_weight) < 0:
            frappe.throw("Firki Weight cannot be negative.")

        if flt(self.filled_firki) < 0:
            frappe.throw("Filled Firki cannot be negative.")

        if flt(self.firki_nang) < 0:
            frappe.throw("Firki Nang cannot be negative.")

    def calculate_totals(self):
        self.total_output_weight = sum(flt(row.used_net_weight or row.weight) for row in self.output_items)
        self.total_waste_weight = 0

        quality_purity = frappe.db.get_value(
            "Quality Master",
            self.quality_code,
            "silver_purity_percent"
        ) if self.quality_code else 0

        for row in self.waste_items:
            self.total_waste_weight += flt(row.weight)

            if row.waste_product:
                metal_type = frappe.db.get_value("Product Master", row.waste_product, "metal_type")
                row.approx_silver_weight = flt(row.weight) * flt(quality_purity) / 100 if metal_type == "Silver" else 0

        self.rangayel_kasab_weight = flt(self.gross_weight_without_dabba) - flt(self.firki_weight)

        self.total_jari_production = (
            flt(self.gross_weight_without_dabba)
            - flt(self.firki_weight)
            - flt(self.total_waste_weight)
        )

        self.weight_of_one_firki = (
            flt(self.total_jari_production) / flt(self.filled_firki)
            if flt(self.filled_firki) else 0
        )

        self.vadh_ghat = (
            flt(self.total_jari_production)
            - flt(self.total_input_weight)
            + flt(self.total_waste_weight)
        )

        self.loss_weight = flt(self.total_input_weight) - flt(self.total_output_weight) - flt(self.total_waste_weight)

        self.loss_percent = (
            flt(self.loss_weight) / flt(self.total_input_weight) * 100
            if flt(self.total_input_weight) else 0
        )

        self.loss_standard_percent = frappe.db.get_value(
            "Loss Standard Master",
            {"department": "Gilit"},
            "standard_loss_percent"
        ) or 0

        self.loss_status = "Excess Loss" if flt(self.loss_percent) > flt(self.loss_standard_percent) else "OK"

    def update_peti_remaining_net_weight(self):
        for row in self.output_items:
            if not row.spindal_peti_entry:
                continue

            peti = frappe.get_doc("Spindal Peti Entry", row.spindal_peti_entry)
            current_remaining = flt(peti.remaining_net_weight)
            new_remaining = current_remaining - flt(row.used_net_weight)

            if new_remaining < 0:
                frappe.throw(f"Remaining N.W cannot become negative for Peti {row.peti_no}.")

            status = "Partial"

            if new_remaining == 0 and flt(peti.remaining_bobbin) == 0:
                status = "Fully Consumed"

            frappe.db.set_value("Spindal Peti Entry", peti.name, {
                "remaining_net_weight": new_remaining,
                "status": status
            })

    def restore_peti_remaining_net_weight(self):
        for row in self.output_items:
            if not row.spindal_peti_entry:
                continue

            peti = frappe.get_doc("Spindal Peti Entry", row.spindal_peti_entry)
            max_weight = flt(peti.net_weight)

            uom = (peti.uom or "").strip().lower()
            if uom in ["gm", "gram", "grams", "g"]:
                max_weight = max_weight / 1000

            restored = flt(peti.remaining_net_weight) + flt(row.used_net_weight)

            if restored > max_weight:
                restored = max_weight

            status = "Received"

            if restored < max_weight or flt(peti.remaining_bobbin) < flt(peti.bobbin_count):
                status = "Partial"

            frappe.db.set_value("Spindal Peti Entry", peti.name, {
                "remaining_net_weight": restored,
                "status": status
            })

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
        return frappe.db.exists("Inventory Ledger", {
            "reference_doctype": self.doctype,
            "reference_name": self.name
        })

    def post_outputs_and_waste(self):
        if self.ledger_exists():
            return

        for row in self.output_items:
            if not row.product or not flt(row.used_net_weight or row.weight):
                continue

            weight = flt(row.used_net_weight or row.weight)
            balance = self.get_last_balance(self.company, "Gilit", row.product)

            frappe.get_doc({
                "doctype": "Inventory Ledger",
                "company": self.company,
                "department": "Gilit",
                "product": row.product,
                "batch_number": self.active_batch_no,
                "in_weight": weight,
                "out_weight": 0,
                "current_balance": flt(balance) + weight,
                "transaction_type": "Production Output",
                "reference_doctype": self.doctype,
                "reference_name": self.name,
                "date": self.receive_date or today(),
                "remarks": "Final Jari Product received from Gilit"
            }).insert(ignore_permissions=True)

        for row in self.waste_items:
            if not row.waste_product or not flt(row.weight):
                continue

            balance = self.get_last_balance(self.company, "Gilit", row.waste_product)

            frappe.get_doc({
                "doctype": "Inventory Ledger",
                "company": self.company,
                "department": "Gilit",
                "product": row.waste_product,
                "batch_number": self.active_batch_no,
                "in_weight": flt(row.weight),
                "out_weight": 0,
                "current_balance": flt(balance) + flt(row.weight),
                "transaction_type": "Waste Generated",
                "reference_doctype": self.doctype,
                "reference_name": self.name,
                "date": self.receive_date or today(),
                "remarks": "Gilit waste generated"
            }).insert(ignore_permissions=True)