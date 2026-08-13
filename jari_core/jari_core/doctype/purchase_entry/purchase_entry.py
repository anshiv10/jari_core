import frappe
from frappe.model.document import Document
from frappe.utils import flt, today
from jari_core.jari_core.stock_utils import get_or_create_stock_source


class PurchaseEntry(Document):

    def validate(self):
        self.set_defaults()
        self.validate_items()
        self.calculate_item_weights()
        self.calculate_item_amounts()
        self.calculate_totals()

    def on_submit(self):
        self.post_to_inventory_ledger()
        frappe.db.set_value(self.doctype, self.name, "status", "Approved")

    def on_cancel(self):
        from jari_core.jari_core.stock_utils import (
            reverse_reference_inventory_ledger,
        )

        reverse_reference_inventory_ledger(
            self
        )

        frappe.db.set_value(
            self.doctype,
            self.name,
            "status",
            "Cancelled",
        )

    def set_defaults(self):
        if not self.department:
            self.department = "ROOT"

    def validate_items(self):
        if not self.items:
            frappe.throw("At least one Purchase Item is required.")

        for row in self.items:
            if not row.product:
                frappe.throw("Product is required in Purchase Items.")

            if flt(row.gross_weight) <= 0:
                frappe.throw(f"Gross Weight must be greater than zero for product {row.product}.")

    def calculate_item_weights(self):
        for row in self.items:
            purity = flt(row.purity_percent) if row.purity_percent is not None else 100

            row.deduction_weight = flt(row.gross_weight) * (1 - purity / 100)
            row.net_weight = flt(row.gross_weight) - flt(row.deduction_weight)

    def calculate_item_amounts(self):
        """
        Calculate monetary values for every Purchase Item.

        Untaxed Amount = Price/KG x Gross Weight
        GST Amount     = Untaxed Amount x GST % / 100
        Amount         = Untaxed Amount + GST Amount
        """
        for row in self.items:
            price_per_kg = flt(row.price_per_kg)
            gross_weight = flt(row.gross_weight)
            gst_percent = flt(row.gst_percent)

            if price_per_kg < 0:
                frappe.throw(
                    f"Price/KG cannot be negative for product "
                    f"{row.product}."
                )

            if gst_percent < 0 or gst_percent > 100:
                frappe.throw(
                    f"GST % for product {row.product} must be "
                    f"between 0 and 100."
                )

            untaxed_amount = (
                price_per_kg
                * gross_weight
            )

            gst_amount = (
                untaxed_amount
                * gst_percent
                / 100
            )

            row.untaxed_amount = untaxed_amount
            row.amount = (
                untaxed_amount
                + gst_amount
            )

    def calculate_totals(self):
        self.total_gross_weight = 0
        self.total_deduction_weight = 0
        self.total_net_weight = 0
        self.total_amount = 0

        for row in self.items:
            self.total_gross_weight += flt(row.gross_weight)
            self.total_deduction_weight += flt(row.deduction_weight)
            self.total_net_weight += flt(row.net_weight)
            self.total_amount += flt(row.amount)

    def get_last_balance(self, product):
        return frappe.db.get_value(
            "Inventory Ledger",
            {
                "company": self.company,
                "department": self.department,
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
                "reference_name": self.name,
                "transaction_type": "Purchase Inward"
            }
        )

    def post_to_inventory_ledger(self):
        if self.ledger_exists():
            return

        for row in self.items:
            if not row.product or not flt(row.net_weight):
                continue

            stock_source = get_or_create_stock_source(
                source_type="Purchase Entry",
                company=self.company,
                product=row.product,
                source_doctype=self.doctype,
                source_name=self.name,
                source_row=row.name,
                source_date=self.purchase_date or today(),
                batch_number=self.name,
                remarks=f"Purchase from {self.vendor}",
            )

            last_balance = self.get_last_balance(row.product)
            new_balance = flt(last_balance) + flt(row.net_weight)

            frappe.get_doc({
                "doctype": "Inventory Ledger",
                "company": self.company,
                "department": self.department,
                "product": row.product,
                "batch_number": self.name,
                "stock_source": stock_source,
                "in_weight": flt(row.net_weight),
                "out_weight": 0,
                "current_balance": new_balance,
                "transaction_type": "Purchase Inward",
                "reference_doctype": self.doctype,
                "reference_name": self.name,
                "date": self.purchase_date or today(),
                "remarks": f"Purchase from {self.vendor}"
            }).insert(ignore_permissions=True)

    def reverse_inventory_ledger(self):
        for row in self.items:
            if not row.product or not flt(row.net_weight):
                continue

            last_balance = self.get_last_balance(row.product)

            frappe.get_doc({
                "doctype": "Inventory Ledger",
                "company": self.company,
                "department": self.department,
                "product": row.product,
                "batch_number": self.name,
                "in_weight": 0,
                "out_weight": flt(row.net_weight),
                "current_balance": flt(last_balance) - flt(row.net_weight),
                "transaction_type": "Purchase Reversal",
                "reference_doctype": self.doctype,
                "reference_name": self.name,
                "date": today(),
                "remarks": f"Reversal on cancellation of {self.name}"
            }).insert(ignore_permissions=True)
