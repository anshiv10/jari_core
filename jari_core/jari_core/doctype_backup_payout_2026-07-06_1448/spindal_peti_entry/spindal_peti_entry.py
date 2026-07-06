import frappe
from frappe.model.document import Document
from frappe.utils import flt, cint, today


class SpindalPetiEntry(Document):

    def validate(self):
        self.set_peti_id()
        self.pull_spindal_issue_details()
        self.sync_bobbin_count_with_nang()
        self.set_default_uom()
        self.calculate_net_weight()
        self.set_bobbin_balance()
        self.set_remaining_net_weight()
        self.validate_weights()

    def on_submit(self):
        if not self.peti_id:
            self.db_set("peti_id", self.name)

        if not cint(self.remaining_bobbin):
            self.db_set("remaining_bobbin", cint(self.bobbin_count or self.nang))

        if not flt(self.remaining_net_weight):
            self.db_set("remaining_net_weight", self.get_net_weight_in_gm())

        self.post_kasab_stock()
        self.db_set("status", "Received")

    def on_cancel(self):
        consumed_bobbin = cint(self.bobbin_count or self.nang) - cint(self.remaining_bobbin)
        consumed_weight = self.get_net_weight_in_gm() - flt(self.remaining_net_weight)

        if consumed_bobbin > 0 or consumed_weight > 0:
            frappe.throw("Cannot cancel Peti because it is already consumed in Gilit.")

        self.reverse_kasab_stock()
        self.db_set("status", "Cancelled")

    def set_peti_id(self):
        if self.name and not self.peti_id:
            self.peti_id = self.name

    def set_default_uom(self):
        if not self.uom:
            self.uom = "gm"

    def pull_spindal_issue_details(self):
        if not self.spindal_issue:
            return

        issue = frappe.get_doc("Spindal Issue", self.spindal_issue)

        self.company = issue.company
        self.batch_no = issue.active_batch_no
        self.quality_code = issue.quality_code

        if hasattr(self, "quality"):
            self.quality = issue.quality_code

    def sync_bobbin_count_with_nang(self):
        if cint(self.nang) and not cint(self.bobbin_count):
            self.bobbin_count = cint(self.nang)

    def calculate_net_weight(self):
        self.net_weight = flt(self.gross_weight) - flt(self.baad_weight)

    def is_gm_uom(self):
        return (self.uom or "").strip().lower() in ["gm", "gram", "grams", "g"]

    def get_net_weight_in_gm(self):
        if self.is_gm_uom():
            return flt(self.net_weight)
        return flt(self.net_weight) * 1000

    def get_net_weight_in_kg(self):
        if self.is_gm_uom():
            return flt(self.net_weight) / 1000
        return flt(self.net_weight)

    def set_bobbin_balance(self):
        total_bobbin = cint(self.bobbin_count or self.nang)
        if total_bobbin and not cint(self.remaining_bobbin):
            self.remaining_bobbin = total_bobbin

    def set_remaining_net_weight(self):
        if flt(self.net_weight) and not flt(self.remaining_net_weight):
            self.remaining_net_weight = self.get_net_weight_in_gm()

    def validate_weights(self):
        total_bobbin = cint(self.bobbin_count or self.nang)

        if flt(self.gross_weight) <= 0:
            frappe.throw("Gross Weight must be greater than zero.")

        if flt(self.baad_weight) < 0:
            frappe.throw("Baad Weight cannot be negative.")

        if flt(self.net_weight) <= 0:
            frappe.throw("Net Weight must be greater than zero.")

        if total_bobbin <= 0:
            frappe.throw("Bobbin Count must be greater than zero.")

        if cint(self.remaining_bobbin) < 0:
            frappe.throw("Remaining Bobbin cannot be negative.")

        if cint(self.remaining_bobbin) > total_bobbin:
            frappe.throw("Remaining Bobbin cannot be greater than Bobbin Count.")

        if flt(self.remaining_net_weight) < 0:
            frappe.throw("Remaining N.W cannot be negative.")

        if flt(self.remaining_net_weight) > flt(self.get_net_weight_in_gm()):
            frappe.throw("Remaining N.W cannot be greater than Net Weight.")

    def get_kasab_product(self):
        if frappe.db.exists("Product Master", "KASAB"):
            return "KASAB"

        product = frappe.db.get_value("Product Master", {"product_name": "KASAB"}, "name")
        if product:
            return product

        product = frappe.db.get_value("Product Master", {"product_name": ["like", "%KASAB%"]}, "name")
        if product:
            return product

        frappe.throw("KASAB product not found in Product Master.")

    def get_department(self):
        if self.spindal_issue:
            return frappe.db.get_value("Spindal Issue", self.spindal_issue, "to_department") or "spindal"
        return "spindal"

    def get_last_balance(self, company, department, product):
        return frappe.db.get_value(
            "Inventory Ledger",
            {"company": company, "department": department, "product": product},
            "current_balance",
            order_by="creation desc"
        ) or 0

    def ledger_exists(self, transaction_type):
        return frappe.db.exists(
            "Inventory Ledger",
            {
                "reference_doctype": self.doctype,
                "reference_name": self.name,
                "transaction_type": transaction_type
            }
        )

    def post_kasab_stock(self):
        if self.ledger_exists("Production Output"):
            return

        product = self.get_kasab_product()
        department = self.get_department()
        weight = self.get_net_weight_in_kg()

        if weight <= 0:
            return

        last_balance = self.get_last_balance(self.company, department, product)

        frappe.get_doc({
            "doctype": "Inventory Ledger",
            "company": self.company,
            "department": department,
            "product": product,
            "batch_number": self.batch_no,
            "in_weight": weight,
            "out_weight": 0,
            "current_balance": flt(last_balance) + weight,
            "transaction_type": "Production Output",
            "reference_doctype": self.doctype,
            "reference_name": self.name,
            "date": self.peti_date or today(),
            "remarks": "Kasab stock added from Spindal Peti Entry"
        }).insert(ignore_permissions=True)

    def reverse_kasab_stock(self):
        if self.ledger_exists("Adjustment"):
            return

        product = self.get_kasab_product()
        department = self.get_department()
        weight = self.get_net_weight_in_kg()

        if weight <= 0:
            return

        last_balance = self.get_last_balance(self.company, department, product)

        if weight > flt(last_balance):
            frappe.throw("Cannot cancel Peti because KASAB stock is already consumed.")

        frappe.get_doc({
            "doctype": "Inventory Ledger",
            "company": self.company,
            "department": department,
            "product": product,
            "batch_number": self.batch_no,
            "in_weight": 0,
            "out_weight": weight,
            "current_balance": flt(last_balance) - weight,
            "transaction_type": "Adjustment",
            "reference_doctype": self.doctype,
            "reference_name": self.name,
            "date": today(),
            "remarks": "Kasab stock reversed due to Spindal Peti cancellation"
        }).insert(ignore_permissions=True)
