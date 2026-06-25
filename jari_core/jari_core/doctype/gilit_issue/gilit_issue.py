import frappe
from frappe.model.document import Document
from frappe.utils import flt, cint, today


@frappe.whitelist()
def get_kasab_product_name():
    if frappe.db.exists("Product Master", "KASAB"):
        return "KASAB"

    product = frappe.db.get_value("Product Master", {"product_name": "KASAB"}, "name")
    if product:
        return product

    product = frappe.db.get_value("Product Master", {"product_name": ["like", "%KASAB%"]}, "name")
    return product or "KASAB"


@frappe.whitelist()
def get_product_stock_for_gilit(company, department, product):
    current_stock = frappe.db.get_value(
        "Inventory Ledger",
        {
            "company": company,
            "department": department,
            "product": product
        },
        "current_balance",
        order_by="creation desc"
    ) or 0

    uom = ""
    meta = frappe.get_meta("Product Master")

    for fieldname in ["uom", "stock_uom", "default_uom"]:
        if meta.has_field(fieldname):
            uom = frappe.db.get_value("Product Master", product, fieldname) or ""
            if uom:
                break

    return {
        "current_stock": current_stock,
        "uom": uom
    }


class GilitIssue(Document):

    def validate(self):
        self.set_defaults()
        self.validate_peti_items()
        self.validate_metal_water_inputs()
        self.calculate_totals()

    def on_submit(self):
        self.update_peti_balances()
        self.post_inventory_transfer()
        frappe.db.set_value(self.doctype, self.name, "status", "Issued")

    def on_cancel(self):
        self.restore_peti_balances()

    def set_defaults(self):
        if not self.from_department:
            self.from_department = "SPINDAL"

        if not self.to_department:
            self.to_department = "Gilit"

    def get_kasab_product(self):
        product = get_kasab_product_name()

        if not frappe.db.exists("Product Master", product):
            frappe.throw("KASAB product not found in Product Master.")

        return product

    def get_total_bobbin_from_peti(self, peti):
        return cint(peti.bobbin_count or peti.nang)

    def get_available_bobbin_from_peti(self, peti):
        return cint(peti.remaining_bobbin or peti.bobbin_count or peti.nang)

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

            total_bobbin = self.get_total_bobbin_from_peti(peti)
            available = self.get_available_bobbin_from_peti(peti)

            if total_bobbin <= 0:
                frappe.throw(f"Bobbin Count is missing in Peti {peti.name}.")

            if available <= 0 or peti.status == "Fully Consumed":
                frappe.throw(f"Peti {peti.name} is already fully consumed.")

            if cint(row.issued_bobbin) <= 0:
                frappe.throw(f"Issued Bobbin must be greater than zero for Peti {peti.name}.")

            if cint(row.issued_bobbin) > available:
                frappe.throw(
                    f"Cannot issue {row.issued_bobbin} bobbin from Peti {peti.name}. "
                    f"Available Bobbin: {available}"
                )

            row.peti_no = peti.peti_no or peti.name
            row.quality_code = peti.quality_code
            row.khata_no = peti.khata_no
            row.product = self.get_kasab_product()
            row.uom = peti.uom or row.uom
            row.gross_weight = flt(peti.gross_weight)
            row.baad_weight = flt(peti.baad_weight)
            row.net_weight = flt(peti.net_weight)
            row.total_bobbin = total_bobbin
            row.available_bobbin = available
            row.balance_bobbin_after_issue = available - cint(row.issued_bobbin)
            row.operator_name = peti.operator

    def validate_metal_water_inputs(self):
        for row in self.metal_water_inputs or []:
            if not row.product:
                frappe.throw("Product Name is required in Metal Water Input.")

            if not row.input_date:
                row.input_date = self.issue_date or today()

            if flt(row.issued_aani) <= 0:
                frappe.throw(f"Issued Aani must be greater than zero for {row.product}.")

            current_stock = self.get_last_balance(self.company, "Gilit", row.product)
            row.current_stock = current_stock

            if flt(row.issued_aani) > flt(current_stock):
                frappe.throw(
                    f"Insufficient stock for {row.product} in {self.to_department}. "
                    f"Available: {current_stock}, Required: {row.issued_aani}"
                )

    def calculate_totals(self):
        self.total_peti = 0
        self.total_net_weight = 0

        for row in self.peti_items or []:
            if not row.spindal_peti_entry:
                continue

            self.total_peti += 1

            if cint(row.total_bobbin):
                issued_weight_in_grams = (
                    flt(row.net_weight) / cint(row.total_bobbin)
                ) * cint(row.issued_bobbin)

                self.total_net_weight += issued_weight_in_grams / 1000

    def update_peti_balances(self):
        for row in self.peti_items:
            peti = frappe.get_doc("Spindal Peti Entry", row.spindal_peti_entry)

            total_bobbin = self.get_total_bobbin_from_peti(peti)
            available = self.get_available_bobbin_from_peti(peti)
            new_balance = available - cint(row.issued_bobbin)

            if new_balance < 0:
                frappe.throw(f"Peti {peti.name} has insufficient bobbin balance.")

            frappe.db.set_value("Spindal Peti Entry", peti.name, {
                "bobbin_count": total_bobbin,
                "remaining_bobbin": new_balance,
                "status": "Fully Consumed" if new_balance == 0 else "Partial"
            })

    def restore_peti_balances(self):
        for row in self.peti_items:
            peti = frappe.get_doc("Spindal Peti Entry", row.spindal_peti_entry)

            total_bobbin = self.get_total_bobbin_from_peti(peti)
            restored = cint(peti.remaining_bobbin) + cint(row.issued_bobbin)

            if restored > total_bobbin:
                restored = total_bobbin

            status = "Received" if restored == total_bobbin else "Partial"

            frappe.db.set_value("Spindal Peti Entry", peti.name, {
                "remaining_bobbin": restored,
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

        if weight:
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
                "transaction_type": "Stock Transfer Out",
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

        for row in self.metal_water_inputs or []:
            if not row.product or not flt(row.issued_aani):
                continue

            balance = self.get_last_balance(self.company, "Gilit", row.product)

            frappe.get_doc({
                "doctype": "Inventory Ledger",
                "company": self.company,
                "department": "Gilit",
                "product": row.product,
                "batch_number": self.gilit_batch_no,
                "in_weight": 0,
                "out_weight": flt(row.issued_aani),
                "current_balance": flt(balance) - flt(row.issued_aani),
                "transaction_type": "Production Input",
                "reference_doctype": self.doctype,
                "reference_name": self.name,
                "date": row.input_date or self.issue_date or today(),
                "remarks": "Metal Water Input issued in Gilit"
            }).insert(ignore_permissions=True)