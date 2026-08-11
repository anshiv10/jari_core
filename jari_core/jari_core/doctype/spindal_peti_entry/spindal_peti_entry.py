import frappe
from frappe.model.document import Document
from frappe.utils import flt, cint, today


class SpindalPetiEntry(Document):

    def validate(self):
        self.set_peti_id()
        self.pull_spindal_issue_details()
        self.sync_bobbin_count_with_nang()
        self.validate_source_weights()
        self.normalize_peti_weights()
        self.calculate_net_weight()
        self.set_bobbin_balance()
        self.set_remaining_net_weight()
        self.validate_weights()

    def before_submit(self):
        """
        Client-approved workflow:

        Spindal Peti Entry may be submitted while its linked
        Spindal Issue is either Draft or Submitted.

        Cancelled Spindal Issue is never allowed.

        If the Issue is still Draft, Peti submission is allowed
        but KASAB stock posting is deferred until the Issue is
        eventually submitted.
        """
        if not self.spindal_issue:
            frappe.throw(
                "Spindal Issue is required before submitting Peti."
            )

        issue_docstatus = frappe.db.get_value(
            "Spindal Issue",
            self.spindal_issue,
            "docstatus",
        )

        if issue_docstatus is None:
            frappe.throw(
                f"Spindal Issue {self.spindal_issue} does not exist."
            )

        issue_docstatus = cint(issue_docstatus)

        if issue_docstatus == 2:
            frappe.throw(
                "The linked Spindal Issue is Cancelled. "
                "This Peti Entry cannot be submitted."
            )

        if issue_docstatus not in (0, 1):
            frappe.throw(
                f"Invalid document status for linked Spindal Issue "
                f"{self.spindal_issue}."
            )

        if flt(self.gross_weight) <= 0:
            frappe.throw(
                "Gross Weight must be greater than zero "
                "before submission."
            )

        if flt(self.net_weight) <= 0:
            frappe.throw(
                "Net Weight must be greater than zero "
                "before submission."
            )

    def on_submit(self):
        if not self.peti_id:
            self.db_set("peti_id", self.name)

        if not cint(self.remaining_bobbin):
            self.db_set(
                "remaining_bobbin",
                cint(self.bobbin_count or self.nang)
            )

        if not flt(self.remaining_net_weight):
            self.db_set(
                "remaining_net_weight",
                self.get_net_weight_in_kg()
            )

        # Peti may be submitted while the linked Issue is Draft.
        # KASAB stock is posted only after the source Issue has
        # actually posted its inventory transaction.
        if self.is_linked_spindal_issue_submitted():
            self.post_kasab_stock()

        self.db_set("status", "Received")

    def is_linked_spindal_issue_submitted(self):
        if not self.spindal_issue:
            return False

        issue_docstatus = frappe.db.get_value(
            "Spindal Issue",
            self.spindal_issue,
            "docstatus",
        )

        return cint(issue_docstatus) == 1

    def on_cancel(self):
        consumed_bobbin = (
            cint(self.bobbin_count or self.nang)
            - cint(self.remaining_bobbin)
        )

        consumed_weight = (
            self.get_net_weight_in_kg()
            - flt(self.remaining_net_weight)
        )

        if consumed_bobbin > 0 or consumed_weight > 0:
            frappe.throw(
                "Cannot cancel Peti because it is already consumed in Gilit."
            )

        self.reverse_kasab_stock()
        self.db_set("status", "Cancelled")

    def set_peti_id(self):
        if self.name and not self.peti_id:
            self.peti_id = self.name

    def validate_source_weights(self):
        """
        Validate the dedicated GM input fields.

        Client workflow:
        - Baad Weight may be entered first.
        - Gross Weight may remain blank/zero while the Peti is Draft.
        - Once Gross Weight is entered, Baad Weight cannot exceed it.
        - Final Gross/Net requirements are enforced in before_submit().

        Derived Gross/Baad/Net values are stored in KG only.
        """

        gross_gm = flt(self.gross_weight_gm)
        baad_gm = flt(self.baad_weight_gm)

        if gross_gm < 0:
            frappe.throw(
                "Gross Weight (GM) cannot be negative."
            )

        if baad_gm < 0:
            frappe.throw(
                "Baad Weight (GM) cannot be negative."
            )

        # While Draft, Baad Weight may be recorded before Gross Weight.
        # Validate the comparison only after Gross Weight is entered.
        if gross_gm > 0 and baad_gm > gross_gm:
            frappe.throw(
                "Baad Weight (GM) cannot be greater than "
                "Gross Weight (GM)."
            )

    def normalize_peti_weights(self):
        """
        Spindal Peti physical weights are ENTERED in grams but
        permanently STORED in KG.

        Example:
            Gross input = 9888 GM
            Baad input  = 2635 GM

            Gross KG = 9.888
            Baad KG  = 2.635
            Net KG   = 7.253

        Dedicated gram fields remove all ambiguity caused by changing
        UOM from gram to KG after an earlier save.
        """

        gross_gm = flt(self.gross_weight_gm)
        baad_gm = flt(self.baad_weight_gm)

        if gross_gm < 0:
            frappe.throw(
                "Gross Weight (GM) cannot be negative."
            )

        if baad_gm < 0:
            frappe.throw(
                "Baad Weight (GM) cannot be negative."
            )

        if gross_gm > 0 and baad_gm > gross_gm:
            frappe.throw(
                "Baad Weight (GM) cannot be greater than "
                "Gross Weight (GM)."
            )

        self.gross_weight = flt(
            gross_gm / 1000,
            3
        )

        self.baad_weight = flt(
            baad_gm / 1000,
            3
        )

        # Downstream Peti/Gilit/Inventory values are always KG.
        self.uom = "KG"

    def pull_spindal_issue_details(self):
        if not self.spindal_issue:
            return

        issue = frappe.get_doc(
            "Spindal Issue",
            self.spindal_issue
        )

        self.company = issue.company
        self.batch_no = issue.active_batch_no
        self.quality_code = issue.quality_code

        if hasattr(self, "quality"):
            self.quality = issue.quality_code

    def sync_bobbin_count_with_nang(self):
        if cint(self.nang) and not cint(self.bobbin_count):
            self.bobbin_count = cint(self.nang)

    def calculate_net_weight(self):
        gross_weight = flt(self.gross_weight)
        baad_weight = flt(self.baad_weight)

        if gross_weight <= 0:
            self.net_weight = 0
            return

        self.net_weight = (
            gross_weight
            - baad_weight
        )

    def get_net_weight_in_kg(self):
        """
        Spindal Peti weight is permanently stored in KG.
        """
        return flt(self.net_weight)

    def set_bobbin_balance(self):
        total_bobbin = cint(
            self.bobbin_count or self.nang
        )

        if total_bobbin and not cint(self.remaining_bobbin):
            self.remaining_bobbin = total_bobbin

    def set_remaining_net_weight(self):
        """
        While the Peti is Draft, Remaining N.W must always mirror
        the newly calculated Net Weight.

        After submission, Gilit consumption controls the remaining
        balance and it must never be reset here.
        """
        if self.docstatus == 0:
            self.remaining_net_weight = flt(
                self.net_weight,
                3
            )

    def validate_weights(self):
        total_bobbin = cint(
            self.bobbin_count or self.nang
        )

        gross_weight = flt(self.gross_weight)
        baad_weight = flt(self.baad_weight)
        net_weight = flt(self.net_weight)

        if gross_weight < 0:
            frappe.throw(
                "Gross Weight cannot be negative."
            )

        if baad_weight < 0:
            frappe.throw(
                "Baad Weight cannot be negative."
            )

        if (
            gross_weight > 0
            and baad_weight > gross_weight
        ):
            frappe.throw(
                "Baad Weight cannot be greater than Gross Weight."
            )

        if (
            gross_weight > 0
            and net_weight <= 0
        ):
            frappe.throw(
                "Net Weight must be greater than zero."
            )

        if total_bobbin <= 0:
            frappe.throw(
                "Bobbin Count must be greater than zero."
            )

        if cint(self.remaining_bobbin) < 0:
            frappe.throw(
                "Remaining Bobbin cannot be negative."
            )

        if cint(self.remaining_bobbin) > total_bobbin:
            frappe.throw(
                "Remaining Bobbin cannot be greater than Bobbin Count."
            )

        if flt(self.remaining_net_weight) < 0:
            frappe.throw(
                "Remaining N.W cannot be negative."
            )

        if (
            flt(self.remaining_net_weight)
            > flt(self.get_net_weight_in_kg())
        ):
            frappe.throw(
                "Remaining N.W cannot be greater than Net Weight."
            )

    def get_kasab_product(self):
        product = frappe.db.get_value(
            "Product Master",
            {"product_tag": "KASAB"},
            "name"
        )

        if product:
            return product

        if frappe.db.exists(
            "Product Master",
            "KASAB"
        ):
            return "KASAB"

        product = frappe.db.get_value(
            "Product Master",
            {"product_name": ["like", "%kasab%"]},
            "name"
        )

        if product:
            return product

        frappe.throw(
            "KASAB product not found in Product Master. "
            "Please set Product Tag = KASAB in Product Master."
        )

    def get_department(self):
        if self.spindal_issue:
            return (
                frappe.db.get_value(
                    "Spindal Issue",
                    self.spindal_issue,
                    "to_department"
                )
                or "spindal"
            )

        return "spindal"

    def get_last_balance(
        self,
        company,
        department,
        product
    ):
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

        last_balance = self.get_last_balance(
            self.company,
            department,
            product
        )

        frappe.get_doc({
            "doctype": "Inventory Ledger",
            "company": self.company,
            "department": department,
            "product": product,
            "batch_number": self.batch_no,
            "in_weight": weight,
            "out_weight": 0,
            "current_balance": (
                flt(last_balance)
                + weight
            ),
            "transaction_type": "Production Output",
            "reference_doctype": self.doctype,
            "reference_name": self.name,
            "date": self.peti_date or today(),
            "remarks": (
                "Kasab stock added from "
                "Spindal Peti Entry"
            )
        }).insert(ignore_permissions=True)

    def reverse_kasab_stock(self):
        if self.ledger_exists("Adjustment"):
            return

        product = self.get_kasab_product()
        department = self.get_department()
        weight = self.get_net_weight_in_kg()

        if weight <= 0:
            return

        last_balance = self.get_last_balance(
            self.company,
            department,
            product
        )

        if weight > flt(last_balance):
            frappe.throw(
                "Cannot cancel Peti because "
                "KASAB stock is already consumed."
            )

        frappe.get_doc({
            "doctype": "Inventory Ledger",
            "company": self.company,
            "department": department,
            "product": product,
            "batch_number": self.batch_no,
            "in_weight": 0,
            "out_weight": weight,
            "current_balance": (
                flt(last_balance)
                - weight
            ),
            "transaction_type": "Adjustment",
            "reference_doctype": self.doctype,
            "reference_name": self.name,
            "date": today(),
            "remarks": (
                "Kasab stock reversed due to "
                "Spindal Peti cancellation"
            )
        }).insert(ignore_permissions=True)