import frappe
from frappe.model.document import Document
from frappe.utils import flt, today


def is_kg_uom(uom):
    return (uom or "").strip().lower() in ["kg", "kilogram", "kilograms"]


def gm_value(value, uom=None):
    if is_kg_uom(uom):
        return flt(value) * 1000
    return flt(value)


def get_gram_uom():
    for uom in ["gram", "gm", "Gram", "GM"]:
        if frappe.db.exists("UOM_Jari", uom):
            return uom
    frappe.throw("Please create UOM_Jari record for gram or gm.")
    

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
        self.total_input_weight = flt(issue.total_net_weight) * 1000

        if not self.output_items:
            for issue_peti in issue.peti_items or []:
                if not issue_peti.spindal_peti_entry:
                    continue

                peti = frappe.get_doc("Spindal Peti Entry", issue_peti.spindal_peti_entry)

                total_bobbin = flt(issue_peti.total_bobbin or peti.bobbin_count or peti.nang)
                issued_bobbin = flt(issue_peti.issued_bobbin)

                peti_net_gm = gm_value(peti.net_weight, peti.uom)

                used_net_weight = (
                    (peti_net_gm / total_bobbin) * issued_bobbin
                    if total_bobbin and issued_bobbin else 0
                )

                row = self.append("output_items", {})
                row.spindal_peti_entry = peti.name
                row.peti_no = peti.peti_no or peti.name
                row.total_bobbin = total_bobbin
                row.issued_bobbin = issued_bobbin
                row.used_net_weight = used_net_weight
                row.uom = peti.uom or issue_peti.uom or get_gram_uom()
                row.weight = used_net_weight

    def get_peti_remaining_gm(self, peti):
        remaining = flt(peti.remaining_net_weight)
        net_gm = gm_value(peti.net_weight, peti.uom)
        total_bobbin = flt(peti.bobbin_count or peti.nang)
        remaining_bobbin = flt(peti.remaining_bobbin)

        if remaining and net_gm and remaining <= (net_gm / 100):
            return remaining * 1000

        if remaining:
            return remaining

        if net_gm and total_bobbin and remaining_bobbin:
            return (net_gm / total_bobbin) * remaining_bobbin

        if net_gm and total_bobbin and not remaining_bobbin and peti.status != "Fully Consumed":
            return net_gm

        return 0

    def validate_items(self):
        if not self.output_items and not self.waste_items:
            frappe.throw("At least one Final Jari Product/Peti Detail or Waste Item is required.")

        for row in self.output_items:
            if not row.spindal_peti_entry:
                continue

            if flt(row.used_net_weight) <= 0:
                frappe.throw("Consumed Net Weight must be greater than zero.")

            peti = frappe.get_doc("Spindal Peti Entry", row.spindal_peti_entry)
            remaining_gm = self.get_peti_remaining_gm(peti)

            if flt(row.used_net_weight) > flt(remaining_gm):
                frappe.throw(
                    f"Consumed Net Weight cannot be greater than Remaining N.W for Peti {row.peti_no}. "
                    f"Available: {remaining_gm} gm, Entered: {row.used_net_weight} gm"
                )

            if not row.uom:
                row.uom = peti.uom or get_gram_uom()
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

        self.weight_of_one_firki = flt(self.total_jari_production) / flt(self.filled_firki) if flt(self.filled_firki) else 0

        self.vadh_ghat = flt(self.total_jari_production) - flt(self.total_input_weight) + flt(self.total_waste_weight)

        self.loss_weight = flt(self.total_input_weight) - flt(self.total_output_weight) - flt(self.total_waste_weight)

        self.loss_percent = flt(self.loss_weight) / flt(self.total_input_weight) * 100 if flt(self.total_input_weight) else 0

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
            new_remaining_gm = self.get_peti_remaining_gm(peti) - flt(row.used_net_weight)

            if new_remaining_gm < 0:
                frappe.throw(f"Remaining N.W cannot become negative for Peti {row.peti_no}.")

            frappe.db.set_value("Spindal Peti Entry", peti.name, {
                "remaining_net_weight": new_remaining_gm,
                "status": "Fully Consumed" if new_remaining_gm == 0 and flt(peti.remaining_bobbin) == 0 else "Partial"
            })

    def restore_peti_remaining_net_weight(self):
        for row in self.output_items:
            if not row.spindal_peti_entry:
                continue

            peti = frappe.get_doc("Spindal Peti Entry", row.spindal_peti_entry)
            max_weight_gm = gm_value(peti.net_weight, peti.uom)
            restored = self.get_peti_remaining_gm(peti) + flt(row.used_net_weight)

            if restored > max_weight_gm:
                restored = max_weight_gm

            status = "Received"
            if restored < max_weight_gm or flt(peti.remaining_bobbin) < flt(peti.bobbin_count):
                status = "Partial"

            frappe.db.set_value("Spindal Peti Entry", peti.name, {
                "remaining_net_weight": restored,
                "status": status
            })

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
            if not row.product or not flt(row.used_net_weight or row.weight):
                continue

            weight_kg = flt(row.used_net_weight or row.weight) / 1000
            balance = self.get_last_balance(self.company, "Gilit", row.product)

            frappe.get_doc({
                "doctype": "Inventory Ledger",
                "company": self.company,
                "department": "Gilit",
                "product": row.product,
                "batch_number": self.active_batch_no,
                "in_weight": weight_kg,
                "out_weight": 0,
                "current_balance": flt(balance) + weight_kg,
                "transaction_type": "Production Output",
                "reference_doctype": self.doctype,
                "reference_name": self.name,
                "date": self.receive_date or today(),
                "remarks": "Final Jari Product received from Gilit"
            }).insert(ignore_permissions=True)

        for row in self.waste_items:
            if not row.waste_product or not flt(row.weight):
                continue

            weight_kg = flt(row.weight) / 1000
            balance = self.get_last_balance(self.company, "Gilit", row.waste_product)

            frappe.get_doc({
                "doctype": "Inventory Ledger",
                "company": self.company,
                "department": "Gilit",
                "product": row.waste_product,
                "batch_number": self.active_batch_no,
                "in_weight": weight_kg,
                "out_weight": 0,
                "current_balance": flt(balance) + weight_kg,
                "transaction_type": "Waste Generated",
                "reference_doctype": self.doctype,
                "reference_name": self.name,
                "date": self.receive_date or today(),
                "remarks": "Gilit waste generated"
            }).insert(ignore_permissions=True)
