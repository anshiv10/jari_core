import frappe
from frappe.model.document import Document
from frappe.utils import flt, cint, today


class GilitIssue(Document):

    def validate(self):
        self.set_defaults()
        self.validate_peti_items()
        self.calculate_totals()

    def on_submit(self):
        self.update_peti_balances()
        self.post_inventory_transfer()
        frappe.db.set_value(self.doctype, self.name, "status", "Issued")

    def set_defaults(self):
        if not self.from_department:
            self.from_department = "SPINDAL"

        if not self.to_department:
            self.to_department = "Gilit"

    def validate_peti_items(self):
        if not self.peti_items:
            frappe.throw("At least one Spindal Peti row is required.")

        seen = set()

        for row in self.peti_items:
            if not row.spindal_peti_entry:
                frappe.throw("Spindal Peti Entry is required.")

            if row.spindal_peti_entry in seen:
                frappe.throw(f"Duplicate Spindal Peti Entry selected: {row.spindal_peti_entry}")

            seen.add(row.spindal_peti_entry)

            peti = frappe.get_doc("Spindal Peti Entry", row.spindal_peti_entry)

            if peti.docstatus != 1:
                frappe.throw(f"Peti {peti.name} is not submitted.")

            if cint(peti.remaining_bobbin) <= 0:
                frappe.throw(f"Peti {peti.name} is already fully consumed.")

            if cint(row.issued_bobbin) <= 0:
                frappe.throw(f"Issued Bobbin must be greater than zero for Peti {peti.name}.")

            if cint(row.issued_bobbin) > cint(peti.remaining_bobbin):
                frappe.throw(
                    f"Cannot issue {row.issued_bobbin} bobbin from Peti {peti.name}. "
                    f"Available Bobbin: {peti.remaining_bobbin}"
                )

            self.fill_peti_row(row, peti)

    def fill_peti_row(self, row, peti):
        row.peti_no = peti.name
        row.quality_code = peti.quality_code
        row.khata_no = peti.khata_no
        row.product = self.get_kasab_product()
        row.uom = "KG"
        row.gross_weight = flt(peti.gross_weight)
        row.baad_weight = flt(peti.baad_weight)
        row.net_weight = flt(peti.net_weight)
        row.total_bobbin = cint(peti.bobbin_count)
        row.available_bobbin = cint(peti.remaining_bobbin)
        row.balance_bobbin_after_issue = cint(peti.remaining_bobbin) - cint(row.issued_bobbin)
        row.operator_name = peti.operator

    def calculate_totals(self):
        self.total_peti = len(self.peti_items or [])
        self.total_net_weight = 0

        for row in self.peti_items:
            if cint(row.total_bobbin):
                per_bobbin_weight = flt(row.net_weight) / cint(row.total_bobbin)
                self.total_net_weight += per_bobbin_weight * cint(row.issued_bobbin)

    def update_peti_balances(self):
        for row in self.peti_items:
            peti = frappe.get_doc("Spindal Peti Entry", row.spindal_peti_entry)

            new_balance = cint(peti.remaining_bobbin) - cint(row.issued_bobbin)

            if new_balance < 0:
                frappe.throw(f"Peti {peti.name} has insufficient bobbin balance.")

            status = "Fully Consumed" if new_balance == 0 else "Partially Consumed"

            frappe.db.set_value("Spindal Peti Entry", peti.name, {
                "remaining_bobbin": new_balance,
                "status": status
            })

    def get_kasab_product(self):
        if frappe.db.exists("Product Master", "KASAB"):
            return "KASAB"

        product = frappe.db.get_value("Product Master", {"product_name": "KASAB"}, "name")

        if product:
            return product

        frappe.throw("KASAB product not found in Product Master.")

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

    def post_inventory_transfer(self):
        if self.ledger_exists():
            return

        product = self.get_kasab_product()
        weight = flt(self.total_net_weight)

        if not weight:
            return

        source_balance = self.get_last_balance(self.company, self.from_department, product)

        if weight > flt(source_balance):
            frappe.throw(
                f"Insufficient KASAB stock in {self.from_department}. "
                f"Available: {source_balance} KG, Required: {weight} KG"
            )

        frappe.get_doc({
            "doctype": "Inventory Ledger",
            "company": self.company,
            "department": self.from_department,
            "product": product,
            "batch_number": self.gilit_batch_no,
            "in_weight": 0,
            "out_weight": weight,
            "current_balance": flt(source_balance) - weight,
            "transaction_type": "Gilit Input",
            "reference_doctype": self.doctype,
            "reference_name": self.name,
            "date": self.issue_date or today(),
            "remarks": "Kasab issued to Gilit"
        }).insert(ignore_permissions=True)

        target_balance = self.get_last_balance(self.company, self.to_department, product)

        frappe.get_doc({
            "doctype": "Inventory Ledger",
            "company": self.company,
            "department": self.to_department,
            "product": product,
            "batch_number": self.gilit_batch_no,
            "in_weight": weight,
            "out_weight": 0,
            "current_balance": flt(target_balance) + weight,
            "transaction_type": "Stock Transfer In",
            "reference_doctype": self.doctype,
            "reference_name": self.name,
            "date": self.issue_date or today(),
            "remarks": "Kasab received in Gilit"
        }).insert(ignore_permissions=True)
