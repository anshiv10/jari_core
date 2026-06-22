import frappe
from frappe.model.document import Document
from frappe.utils import flt, today


class MeltingIssue(Document):

    def validate(self):
        self.set_defaults()
        self.set_silver_purity()
        self.calculate_totals()

    def on_submit(self):
        self.post_inventory_transfer()
        frappe.db.set_value(self.doctype, self.name, "status", "Issued")

    def set_defaults(self):
        if not self.process_master:
            self.process_master = frappe.db.get_value("Process Master", {"process_code": "MELT"}, "name")
        if not self.from_department:
            self.from_department = "Raw Material Store"
        if not self.to_department:
            self.to_department = "Melting"

    def set_silver_purity(self):
        self.silver_purity_percent = frappe.db.get_value(
            "Quality Master", self.quality_code, "silver_purity_percent"
        ) or 0 if self.quality_code else 0

    def calculate_totals(self):
        self.total_issue_weight = 0
        for row in self.issue_items:
            self.total_issue_weight += flt(row.weight)
            if row.product:
                metal_type = frappe.db.get_value("Product Master", row.product, "metal_type")
                row.silver_weight = flt(row.weight) * flt(self.silver_purity_percent) / 100 if metal_type == "Silver" else 0

    def get_last_balance(self, company, department, product):
        return frappe.db.get_value(
            "Inventory Ledger",
            {"company": company, "department": department, "product": product},
            "current_balance",
            order_by="creation desc"
        ) or 0

    def get_available_sources(self, product):
        departments = frappe.db.sql("""
            SELECT DISTINCT department
            FROM `tabInventory Ledger`
            WHERE company=%s AND product=%s
        """, (self.company, product), as_dict=True)

        rows = []
        for d in departments:
            bal = flt(self.get_last_balance(self.company, d.department, product))
            if bal > 0:
                rows.append({"department": d.department, "balance": bal})

        rows.sort(key=lambda x: (0 if x["department"] == self.from_department else 1, -x["balance"]))
        return rows

    def ledger_exists(self):
        return frappe.db.exists("Inventory Ledger", {
            "reference_doctype": self.doctype,
            "reference_name": self.name
        })

    def post_inventory_transfer(self):
        if self.ledger_exists():
            return

        for row in self.issue_items:
            product = row.product
            required = flt(row.weight)
            if not product or not required:
                continue

            sources = self.get_available_sources(product)
            total_available = sum(flt(x["balance"]) for x in sources)

            if required > total_available:
                frappe.throw(
                    f"Insufficient stock for {product}. Available across all departments: {total_available} KG, Requested: {required} KG"
                )

            remaining = required

            for src in sources:
                if remaining <= 0:
                    break

                consume = min(remaining, flt(src["balance"]))
                source_balance = self.get_last_balance(self.company, src["department"], product)

                frappe.get_doc({
                    "doctype": "Inventory Ledger",
                    "company": self.company,
                    "department": src["department"],
                    "product": product,
                    "batch_number": self.batch_no,
                    "in_weight": 0,
                    "out_weight": consume,
                    "current_balance": flt(source_balance) - consume,
                    "transaction_type": "Production Input",
                    "reference_doctype": self.doctype,
                    "reference_name": self.name,
                    "date": self.issue_date or today(),
                    "remarks": f"Melting issue consumed from {src['department']}"
                }).insert(ignore_permissions=True)

                remaining -= consume

            target_balance = self.get_last_balance(self.company, self.to_department, product)

            frappe.get_doc({
                "doctype": "Inventory Ledger",
                "company": self.company,
                "department": self.to_department,
                "product": product,
                "batch_number": self.batch_no,
                "in_weight": required,
                "out_weight": 0,
                "current_balance": flt(target_balance) + required,
                "transaction_type": "Stock Transfer In",
                "reference_doctype": self.doctype,
                "reference_name": self.name,
                "date": self.issue_date or today(),
                "remarks": f"Melting Issue received in {self.to_department}"
            }).insert(ignore_permissions=True)


@frappe.whitelist()
def get_product_stock_summary(product, company=None):
    if not product:
        return ""

    filters = {"product": product}
    if company:
        filters["company"] = company

    departments = frappe.get_all(
        "Inventory Ledger",
        filters=filters,
        fields=["department"],
        group_by="department"
    )

    lines = []

    for d in departments:
        bal = frappe.db.get_value(
            "Inventory Ledger",
            {
                "product": product,
                "department": d.department,
                **({"company": company} if company else {})
            },
            "current_balance",
            order_by="creation desc"
        ) or 0

        if float(bal) != 0:
            lines.append(f"{d.department} - {bal} KG")

    return "\n".join(lines) if lines else "No stock available"


@frappe.whitelist()
def get_product_display_name(product):
    if not product:
        return ""

    return (
        frappe.db.get_value("Product Master", product, "product_name")
        or frappe.db.get_value("Product Master", product, "item_name")
        or frappe.db.get_value("Product Master", product, "product_code")
        or product
    )
