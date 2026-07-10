import frappe
from frappe.model.document import Document
from frappe.utils import flt, today


class PavthaIssue(Document):

    def validate(self):
        self.set_defaults()
        self.validate_items()
        self.calculate_totals()

    def on_submit(self):
        self.post_inventory_transfer()
        frappe.db.set_value(self.doctype, self.name, "status", "Issued")

    def set_defaults(self):
        if not self.from_department:
            self.from_department = "Melting"

        if not self.to_department:
            self.to_department = "Pavtha"

    def validate_items(self):
        if not self.issue_items:
            frappe.throw("At least one issue item is required.")

        for row in self.issue_items:
            if not row.product:
                frappe.throw("Product is required in issue item.")

            if flt(row.weight) <= 0:
                frappe.throw(f"Weight must be greater than zero for product {row.product}.")

    def get_quality_purity(self):
        if not self.quality_code:
            return 0

        possible_fields = [
            "silver_purity_percent",
            "purity_percent",
            "purity",
            "quality_percent"
        ]

        for fieldname in possible_fields:
            if frappe.db.has_column("Quality Master", fieldname):
                return flt(frappe.db.get_value("Quality Master", self.quality_code, fieldname) or 0)

        return 0

    def calculate_totals(self):
        total = 0
        quality_purity = self.get_quality_purity()

        for row in self.issue_items:
            total += flt(row.weight)
            row.silver_weight = 0

            if row.product:
                metal_type = frappe.db.get_value("Product Master", row.product, "metal_type")

                if metal_type == "Silver":
                    row.silver_weight = flt(row.weight) * flt(quality_purity) / 100

        self.total_issue_weight = total

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

    def get_available_sources(self, product):
        departments = frappe.db.sql("""
            SELECT DISTINCT department
            FROM `tabInventory Ledger`
            WHERE company = %s
              AND product = %s
        """, (self.company, product), as_dict=True)

        rows = []

        for d in departments:
            bal = flt(self.get_last_balance(self.company, d.department, product))
            if bal > 0:
                rows.append({
                    "department": d.department,
                    "balance": bal
                })

        rows.sort(key=lambda x: (0 if x["department"] == self.from_department else 1, -x["balance"]))
        return rows

    def ledger_exists(self):
        return frappe.db.exists(
            "Inventory Ledger",
            {
                "reference_doctype": self.doctype,
                "reference_name": self.name
            }
        )

    def add_ledger(self, department, product, in_weight, out_weight, transaction_type, remarks):
        balance = self.get_last_balance(self.company, department, product)

        frappe.get_doc({
            "doctype": "Inventory Ledger",
            "company": self.company,
            "department": department,
            "product": product,
            "batch_number": self.batch_no,
            "in_weight": flt(in_weight),
            "out_weight": flt(out_weight),
            "current_balance": flt(balance) + flt(in_weight) - flt(out_weight),
            "transaction_type": transaction_type,
            "reference_doctype": self.doctype,
            "reference_name": self.name,
            "date": self.issue_date or today(),
            "remarks": remarks
        }).insert(ignore_permissions=True)

    def post_inventory_transfer(self):
        if self.ledger_exists():
            return

        for row in self.issue_items:
            required = flt(row.weight)
            product = row.product

            sources = self.get_available_sources(product)
            total_available = sum(flt(x["balance"]) for x in sources)

            if required > total_available:
                frappe.throw(
                    f"Insufficient stock for {product}. "
                    f"Available across all departments: {total_available} KG, Requested: {required} KG"
                )

            remaining = required

            for src in sources:
                if remaining <= 0:
                    break

                consume = min(remaining, flt(src["balance"]))

                self.add_ledger(
                    department=src["department"],
                    product=product,
                    in_weight=0,
                    out_weight=consume,
                    transaction_type="Production Input",
                    remarks=f"Pavtha issue consumed from {src['department']}"
                )

                remaining -= consume

            self.add_ledger(
                department=self.to_department,
                product=product,
                in_weight=required,
                out_weight=0,
                transaction_type="Stock Transfer In",
                remarks="Pavtha outsource material inward"
            )


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
        query_filters = {
            "product": product,
            "department": d.department
        }

        if company:
            query_filters["company"] = company

        bal = frappe.db.get_value(
            "Inventory Ledger",
            query_filters,
            "current_balance",
            order_by="creation desc"
        ) or 0

        if flt(bal) != 0:
            lines.append(f"{d.department} - {bal} KG")

    return "\n".join(lines) if lines else "No stock available"
