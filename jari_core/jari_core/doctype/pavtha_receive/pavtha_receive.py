import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, today
from jari_core.jari_core.stock_utils import (
    cleanup_unused_draft_receive_stock_sources,
    ensure_draft_receive_stock_sources,
    get_or_create_stock_source,
)


VALID_ISSUE_RECEIVE_TYPES = {
    "In-house",
    "Readymade",
    "Return",
}


class PavthaReceive(Document):

    def validate(self):
        self.validate_issue_is_not_cancelled()
        self.validate_duplicate_submitted_receive()
        self.pull_issue_details()
        self.set_child_type_defaults()
        self.validate_items()
        self.validate_issue_receive_types()

        # Existing production calculations.
        self.calculate_totals()
        self.set_approx_silver()
        self.calculate_payout()

        # Authoritative PDF/physical reconciliation.
        self.calculate_pdf_payout()

    def on_update(self):
        if int(self.docstatus or 0) == 0:
            ensure_draft_receive_stock_sources(
                self
            )

    def on_trash(self):
        cleanup_unused_draft_receive_stock_sources(
            self
        )

    def on_cancel(self):
        from jari_core.jari_core.stock_utils import (
            reverse_reference_inventory_ledger,
        )

        reverse_reference_inventory_ledger(
            self
        )

    def on_submit(self):
        self.validate_issue_is_submitted_for_receive_submit()
        self.validate_duplicate_submitted_receive()

        # Recalculate authoritative values immediately before submission.
        self.pull_issue_details()
        self.set_child_type_defaults()
        self.validate_items()
        self.validate_issue_receive_types()
        self.calculate_totals()
        self.set_approx_silver()
        self.calculate_payout()
        self.calculate_pdf_payout()

        self.db_set(
            "approx_silver_weight",
            flt(self.approx_silver_weight),
            update_modified=False,
        )

        frappe.db.set_value(
            self.doctype,
            self.name,
            {
                "return_weight": flt(self.return_weight),
                "used_silver": flt(self.used_silver),
                "given_silver": flt(self.given_silver),
                "balance_silver": flt(self.balance_silver),
                "remaining_tar": flt(self.remaining_tar),
                "calculated_payout_amount": flt(
                    self.calculated_payout_amount
                ),
                "payout_summary": self.payout_summary or "",
            },
            update_modified=False,
        )

        self.post_outputs_and_waste()

        frappe.db.set_value(
            "Pavtha Issue",
            self.pavtha_issue,
            "status",
            "Received",
            update_modified=False,
        )

    def validate_issue_is_not_cancelled(self):
        if not self.pavtha_issue:
            return

        docstatus = frappe.db.get_value(
            "Pavtha Issue",
            self.pavtha_issue,
            "docstatus",
        )

        if docstatus == 2:
            frappe.throw(
                _(
                    "Pavtha Issue {0} is cancelled and cannot be selected."
                ).format(
                    frappe.bold(self.pavtha_issue)
                )
            )

    def validate_issue_is_submitted_for_receive_submit(self):
        if not self.pavtha_issue:
            frappe.throw(
                _("Pavtha Issue is required before submission.")
            )

        docstatus = frappe.db.get_value(
            "Pavtha Issue",
            self.pavtha_issue,
            "docstatus",
        )

        if docstatus != 1:
            frappe.throw(
                _(
                    "Pavtha Issue {0} is still in Draft. "
                    "You may save Pavtha Receive as Draft, but the "
                    "Pavtha Issue must be submitted before submitting "
                    "this Pavtha Receive."
                ).format(
                    frappe.bold(self.pavtha_issue)
                )
            )

    def validate_duplicate_submitted_receive(self):
        if not self.pavtha_issue:
            return

        existing_receive = frappe.db.exists(
            "Pavtha Receive",
            {
                "pavtha_issue": self.pavtha_issue,
                "docstatus": 1,
                "name": ["!=", self.name],
            },
        )

        if existing_receive:
            frappe.throw(
                _(
                    "Pavtha Issue {0} has already been received in "
                    "submitted Pavtha Receive {1}."
                ).format(
                    frappe.bold(self.pavtha_issue),
                    frappe.bold(existing_receive),
                )
            )

    def pull_issue_details(self):
        """
        Pull authoritative parent information from the linked Pavtha Issue.
        """
        if not self.pavtha_issue:
            return

        issue = frappe.get_doc(
            "Pavtha Issue",
            self.pavtha_issue,
        )

        self.company = issue.company
        self.batch_no = issue.batch_no
        self.process_master = issue.process_master
        self.quality_code = issue.quality_code
        self.outsourcer = issue.outsourcer
        self.rate_per_kg = self.get_jobworker_rate()
        self.total_input_weight = flt(issue.total_issue_weight)

    def get_issue_receive_types(self):
        """
        Return distinct Issue/Receive Types from linked issue child rows.
        """
        if not self.pavtha_issue:
            return set()

        issue_types = frappe.get_all(
            "Pavtha Issue Item",
            filters={
                "parent": self.pavtha_issue,
                "parenttype": "Pavtha Issue",
                "parentfield": "issue_items",
            },
            pluck="issue_receive_type",
        )

        return {
            issue_type
            for issue_type in issue_types
            if issue_type
        }

    def get_default_issue_receive_type(self):
        """
        Return one unambiguous type from the linked issue.

        Older records with blank child values use In-house as a
        backward-compatible fallback.
        """
        issue_types = self.get_issue_receive_types()

        if not issue_types:
            return "In-house"

        if len(issue_types) == 1:
            return next(iter(issue_types))

        return None

    def set_child_type_defaults(self):
        """
        Populate blank output and waste row types when the linked issue
        has one unambiguous type.
        """
        default_type = self.get_default_issue_receive_type()

        if not default_type:
            return

        for row in self.output_items or []:
            if not row.issue_receive_type:
                row.issue_receive_type = default_type

        for row in self.waste_items or []:
            if not row.issue_receive_type:
                row.issue_receive_type = default_type

    def validate_issue_receive_types(self):
        """
        Validate row classifications independently.

        Client-approved behaviour:
        - every row defaults to In-house;
        - every row remains editable;
        - Return may be entered in Issue or Receive;
        - Receive rows are not required to match the Issue row types.
        """
        child_tables = (
            ("output_items", _("Output Item")),
            ("waste_items", _("Waste Item")),
        )

        for table_fieldname, table_label in child_tables:
            for row in self.get(table_fieldname) or []:
                if not row.issue_receive_type:
                    row.issue_receive_type = "In-house"

                if row.issue_receive_type not in VALID_ISSUE_RECEIVE_TYPES:
                    frappe.throw(
                        _(
                            "{0} row #{1}: Issue/Receive Type must be "
                            "In-house, Readymade, or Return."
                        ).format(
                            table_label,
                            row.idx,
                        )
                    )

    def get_jobworker_rate(self):
        if not self.outsourcer:
            return 0

        return flt(
            frappe.db.get_value(
                "Jobworker Master",
                self.outsourcer,
                "rate_per_kg",
            )
            or 0
        )

    def get_jobworker_standard_loss(self):
        if not self.outsourcer:
            return 0

        return flt(
            frappe.db.get_value(
                "Jobworker Master",
                self.outsourcer,
                "standard_loss_percent",
            )
            or 0
        )

    def validate_items(self):
        if not self.output_items and not self.waste_items:
            frappe.throw(
                _("At least one output or waste item is required.")
            )

        for row in self.output_items or []:
            if not row.product:
                frappe.throw(
                    _(
                        "Product is required in output item row #{0}."
                    ).format(row.idx)
                )

            if flt(row.weight) < 0:
                frappe.throw(
                    _(
                        "Weight cannot be negative in output item "
                        "row #{0}."
                    ).format(row.idx)
                )

        for row in self.waste_items or []:
            if not row.waste_product:
                frappe.throw(
                    _(
                        "Waste Product is required in waste item "
                        "row #{0}."
                    ).format(row.idx)
                )

            if flt(row.weight) < 0:
                frappe.throw(
                    _(
                        "Weight cannot be negative in waste item "
                        "row #{0}."
                    ).format(row.idx)
                )

    def get_quality_purity(self):
        if not self.quality_code:
            return 0

        possible_fields = [
            "silver_purity_percent",
            "purity_percent",
            "purity",
            "quality_percent",
        ]

        for fieldname in possible_fields:
            if frappe.db.has_column("Quality Master", fieldname):
                return flt(
                    frappe.db.get_value(
                        "Quality Master",
                        self.quality_code,
                        fieldname,
                    )
                    or 0
                )

        return 0

    def get_product_metal_type(self, product):
        if not product:
            return ""

        if frappe.db.has_column("Product Master", "metal_type"):
            return (
                frappe.db.get_value(
                    "Product Master",
                    product,
                    "metal_type",
                )
                or ""
            )

        return ""

    def get_product_tag(self, product):
        """
        Return the controlled Product Master product_tag.

        Product document names and display labels are not used for
        business classification.
        """
        if not product:
            return ""

        if not frappe.db.has_column(
            "Product Master",
            "product_tag",
        ):
            return ""

        return (
            frappe.db.get_value(
                "Product Master",
                product,
                "product_tag",
            )
            or ""
        ).strip().upper()

    def get_standard_percent(self, fieldname):
        if frappe.db.has_column(
            "Loss Standard Master",
            fieldname,
        ):
            value = frappe.db.get_value(
                "Loss Standard Master",
                {"department": "Pavtha"},
                fieldname,
            )

            if value is not None:
                return flt(value)

        if fieldname == "standard_loss_percent":
            return self.get_jobworker_standard_loss()

        return 0

    def calculate_totals(self):
        """
        Calculate gross weight reconciliation.

        Pavtha output may exceed input because copper or another base
        metal can be added during processing.

        Therefore:
            Process Loss
                = max(Input - Output - Waste, 0)

            Material Addition
                = max(Output + Waste - Input, 0)

        Loss and material addition are mutually exclusive.
        """
        output_total = 0
        waste_total = 0
        quality_purity = self.get_quality_purity()

        for row in self.output_items or []:
            output_total += flt(row.weight)

        for row in self.waste_items or []:
            waste_total += flt(row.weight)
            row.approx_silver_weight = 0

            if row.waste_product:
                metal_type = self.get_product_metal_type(
                    row.waste_product
                )

                if metal_type == "Silver":
                    row.approx_silver_weight = (
                        flt(row.weight)
                        - (
                            flt(row.weight)
                            * flt(quality_purity)
                            / 100
                        )
                    )

        self.total_output_weight = output_total
        self.total_waste_weight = waste_total

        total_input = flt(
            self.total_input_weight
        )

        total_processed = (
            flt(self.total_output_weight)
            + flt(self.total_waste_weight)
        )

        gross_difference = (
            total_input
            - total_processed
        )

        # Floating-point tolerance prevents tiny residual values.
        if abs(gross_difference) < 0.000001:
            gross_difference = 0

        self.loss_weight = max(
            gross_difference,
            0,
        )

        self.material_addition_weight = max(
            -gross_difference,
            0,
        )

        self.waste_percent = (
            flt(self.total_waste_weight)
            / total_input
            * 100
            if total_input
            else 0
        )

        self.loss_percent = (
            flt(self.loss_weight)
            / total_input
            * 100
            if total_input
            else 0
        )

        self.material_addition_percent = (
            flt(self.material_addition_weight)
            / total_input
            * 100
            if total_input
            else 0
        )

        self.loss_standard_percent = self.get_standard_percent(
            "standard_loss_percent"
        )

        self.wastage_standard_percent = self.get_standard_percent(
            "standard_wastage_percent"
        )

        self.loss_status = (
            "Excess Loss"
            if flt(self.loss_percent)
            > flt(self.loss_standard_percent)
            else "OK"
        )

        self.wastage_status = (
            "Excess Wastage"
            if flt(self.waste_percent)
            > flt(self.wastage_standard_percent)
            else "OK"
        )

    def calculate_payout(self):
        """
        Calculate the existing jobworker payout without allowing added
        copper or other material to create an artificial loss-saving
        bonus.

        A bonus remains possible only when:
        - there is no material addition; and
        - actual process loss is below the standard loss.

        Material addition never creates a deduction or bonus by itself.
        """
        self.base_payout = (
            flt(self.total_input_weight)
            * flt(self.rate_per_kg)
        )

        excess_loss_percent = (
            flt(self.loss_percent)
            - flt(self.loss_standard_percent)
        )

        self.bonus_amount = 0
        self.deduction_amount = 0

        if excess_loss_percent > 0:
            excess_weight = (
                flt(self.total_input_weight)
                * excess_loss_percent
                / 100
            )

            self.deduction_amount = (
                excess_weight
                * flt(self.rate_per_kg)
            )

        elif (
            excess_loss_percent < 0
            and flt(
                getattr(
                    self,
                    "material_addition_weight",
                    0,
                )
            )
            <= 0.000001
        ):
            saved_weight = (
                flt(self.total_input_weight)
                * abs(excess_loss_percent)
                / 100
            )

            self.bonus_amount = (
                saved_weight
                * flt(self.rate_per_kg)
            )

        self.payout_suggestion = max(
            0,
            (
                flt(self.base_payout)
                + flt(self.bonus_amount)
                - flt(self.deduction_amount)
            ),
        )

        if not flt(self.payout_given):
            self.payout_given = self.payout_suggestion

    def calculate_approx_silver(self, weight):
        """
        Preserve the existing application formula for compatibility.
        """
        purity = self.get_quality_purity()

        return (
            flt(weight)
            - (
                flt(weight)
                * flt(purity)
                / 100
            )
        )

    def set_approx_silver(self):
        """
        Preserve existing approximate-silver behaviour so this repair
        does not silently alter historical inventory valuation.
        """
        purity = self.get_quality_purity()

        output_approx = 0
        wastage_approx = 0

        for row in self.output_items or []:
            row.approx_silver_weight = (
                flt(row.weight)
                - (
                    flt(row.weight)
                    * flt(purity)
                    / 100
                )
            )

            output_approx += flt(
                row.approx_silver_weight
            )

        for row in self.waste_items or []:
            row.approx_silver_weight = (
                flt(row.weight)
                - (
                    flt(row.weight)
                    * flt(purity)
                    / 100
                )
            )

            wastage_approx += flt(
                row.approx_silver_weight
            )

        self.approx_silver_output = output_approx
        self.approx_silver_wastage = wastage_approx
        self.approx_silver_weight = (
            output_approx + wastage_approx
        )

    def get_issue_tag_weights(self):
        """
        Aggregate linked issue weights by Product Master.product_tag.
        """
        totals = {}

        if not self.pavtha_issue:
            return totals

        issue = frappe.get_doc(
            "Pavtha Issue",
            self.pavtha_issue,
        )

        for row in issue.issue_items or []:
            tag = self.get_product_tag(row.product)

            if not tag:
                continue

            totals[tag] = (
                flt(totals.get(tag))
                + flt(row.weight)
            )

        return totals

    def get_silver_bearing_input_products(self):
        """
        Return Process Master input products marked silver_bearing = 1.
        """
        products = set()

        if not self.process_master:
            return products

        process = frappe.get_doc(
            "Process Master",
            self.process_master,
        )

        for row in process.input_products or []:
            product = (
                getattr(row, "product", None)
                or getattr(row, "product_code", None)
                or getattr(row, "item", None)
                or getattr(row, "item_code", None)
                or getattr(row, "input_product", None)
            )

            if (
                product
                and int(
                    getattr(
                        row,
                        "silver_bearing",
                        0,
                    )
                    or 0
                )
            ):
                products.add(product)

        return products

    def calculate_given_silver(self):
        """
        Return the total issued weight of products explicitly tagged
        SILVER in Product Master.

        Client-approved formula:
            Given Silver =
                Sum of Pavtha Issue Item.weight
                where Product Master.product_tag = "SILVER"

        Important:
        - Use issued gross weight directly.
        - Do not apply Quality Master purity.
        - Do not depend on Process Master.silver_bearing.
        - Sum every matching SILVER row in the linked Pavtha Issue.
        """
        if not self.pavtha_issue:
            return 0

        given_silver = frappe.db.sql(
            """
            SELECT COALESCE(SUM(pii.weight), 0)
            FROM `tabPavtha Issue Item` AS pii
            INNER JOIN `tabProduct Master` AS product
                ON product.name = pii.product
            WHERE pii.parent = %(pavtha_issue)s
              AND pii.parenttype = 'Pavtha Issue'
              AND pii.parentfield = 'issue_items'
              AND UPPER(TRIM(COALESCE(product.product_tag, '')))
                    = 'SILVER'
            """,
            {
                "pavtha_issue": self.pavtha_issue,
            },
        )[0][0]

        return flt(
            given_silver,
            self.precision("given_silver"),
        )

    def calculate_auto_return_weight(self):
        """
        Calculate the client-approved Return weight.

        Client-approved formula:

            Return =
                Return-labelled Pavtha Issue Product Weight
                + Return-labelled Pavtha Receive Product Weight

        Important:
        - Pavtha Issue Product Detail rows labelled Return contribute.
        - Pavtha Receive Received Product Detail rows labelled Return contribute.
        - Readymade weight is not subtracted.
        - Waste Product Detail rows do not contribute.
        """
        readymade_weight = 0
        returned_issue_weight = 0

        # Retain these values only as diagnostic information for the
        # existing preview response. They do not affect Return.
        if self.pavtha_issue:
            issue = frappe.get_doc(
                "Pavtha Issue",
                self.pavtha_issue,
            )

            for row in issue.issue_items or []:
                row_type = (
                    row.issue_receive_type
                    or "In-house"
                )

                if row_type == "Readymade":
                    readymade_weight += flt(row.weight)

                elif row_type == "Return":
                    returned_issue_weight += flt(row.weight)

        # AUTHORITATIVE RETURN:
        # Total weight of Received Product Detail rows labelled Return.
        returned_output_weight = sum(
            flt(row.weight)
            for row in self.output_items or []
            if (
                row.issue_receive_type
                or "In-house"
            ) == "Return"
        )

        # Retained for diagnostic visibility only.
        returned_waste_weight = sum(
            flt(row.weight)
            for row in self.waste_items or []
            if (
                row.issue_receive_type
                or "In-house"
            ) == "Return"
        )

        # Client-approved Return:
        # Return-labelled product weight from Issue
        # + Return-labelled product weight from Receive.
        #
        # Waste Product Detail does not contribute.
        returned_product_weight = (
            flt(returned_issue_weight)
            + flt(returned_output_weight)
        )

        return {
            "readymade_weight": flt(
                readymade_weight
            ),
            "returned_issue_weight": flt(
                returned_issue_weight
            ),
            "returned_output_weight": flt(
                returned_output_weight
            ),
            "returned_waste_weight": flt(
                returned_waste_weight
            ),
            "returned_product_weight": flt(
                returned_product_weight
            ),
            "return_weight": flt(
                returned_product_weight
            ),
        }

    def calculate_pdf_payout(self):
        """
        Authoritative Pavtha physical reconciliation.

        Total Receive:
            Sum of Pavtha output-item weights.

        Total Kachi Goti:
            Issued KACHI GOTI + issued GOTI.

        B.G. Gms:
            Issued BADLA GOTI
            × (100 - B.G. Deduction %) / 100.

        Net:
            Total Receive
            - Return
            - Total Kachi Goti
            - B.G. Gms.

        Used Silver:
            Net / ((Mel + 1000) / 1000).

        Given Silver:
            Total issued weight of Pavtha Issue products whose
            Product Master.product_tag is SILVER.

        Balance Silver:
            Given Silver - Used Silver.

        Remaining TAR:
            Balance Silver × ((Mel + 1000) / 1000).
        """
        return_details = self.calculate_auto_return_weight()

        return_weight = flt(
            return_details["return_weight"]
        )

        self.return_weight = return_weight

        bg_deduction_percent = flt(
            self.bg_deduction_percent
        )
        mel = flt(self.mel)

        if return_weight < 0:
            frappe.throw(
                _("Return Weight cannot be negative.")
            )

        if (
            bg_deduction_percent < 0
            or bg_deduction_percent > 100
        ):
            frappe.throw(
                _(
                    "B.G. Deduction Percentage must be between "
                    "0 and 100."
                )
            )

        mel_factor = (
            mel + 1000
        ) / 1000

        if mel_factor <= 0:
            frappe.throw(
                _(
                    "Mel must be greater than -1000 because "
                    "(Mel + 1000) / 1000 must be positive."
                )
            )

        issue_tag_weights = self.get_issue_tag_weights()

        total_receive = sum(
            flt(row.weight)
            for row in self.output_items or []
        )

        goti_weight = flt(
            issue_tag_weights.get("GOTI")
        )

        kachi_goti_weight = flt(
            issue_tag_weights.get("KACHI GOTI")
        )

        total_kachi_goti = (
            goti_weight
            + kachi_goti_weight
        )

        badla_goti_weight = flt(
            issue_tag_weights.get("BADLA GOTI")
        )

        bg_gms = (
            badla_goti_weight
            * (
                100
                - bg_deduction_percent
            )
            / 100
        )

        net_weight = (
            total_receive
            - return_weight
            - total_kachi_goti
            - bg_gms
        )

        if net_weight < -0.000001:
            frappe.throw(
                _(
                    "Pavtha reconciliation Net cannot be negative. "
                    "Total Receive: {0} KG, Return: {1} KG, "
                    "Total Kachi Goti: {2} KG, "
                    "B.G. Gms: {3} KG, Net: {4} KG."
                ).format(
                    frappe.format_value(
                        total_receive,
                        {"fieldtype": "Float"},
                    ),
                    frappe.format_value(
                        return_weight,
                        {"fieldtype": "Float"},
                    ),
                    frappe.format_value(
                        total_kachi_goti,
                        {"fieldtype": "Float"},
                    ),
                    frappe.format_value(
                        bg_gms,
                        {"fieldtype": "Float"},
                    ),
                    frappe.format_value(
                        net_weight,
                        {"fieldtype": "Float"},
                    ),
                )
            )

        net_weight = max(
            0,
            net_weight,
        )

        used_silver = (
            net_weight
            / mel_factor
        )

        given_silver = (
            self.calculate_given_silver()
        )

        balance_silver = (
            given_silver
            - used_silver
        )

        # Client-approved formula:
        # Remaining TAR =
        #     Balance Silver × ((Mel + 1000) / 1000)
        #
        # Calculate from the unrounded Balance Silver value and round
        # only the final result to the Remaining TAR field precision.
        remaining_tar = flt(
            flt(balance_silver)
            * flt(mel_factor),
            self.precision("remaining_tar"),
        )

        self.used_silver = used_silver
        self.given_silver = given_silver
        self.balance_silver = balance_silver
        self.remaining_tar = remaining_tar

        # A commercial payout amount formula has not yet been supplied.
        self.calculated_payout_amount = 0

        self.payout_summary = (
            self.build_pdf_payout_summary(
                total_receive=total_receive,
                return_weight=return_weight,
                goti_weight=goti_weight,
                kachi_goti_weight=kachi_goti_weight,
                total_kachi_goti=total_kachi_goti,
                badla_goti_weight=badla_goti_weight,
                bg_deduction_percent=bg_deduction_percent,
                bg_gms=bg_gms,
                net_weight=net_weight,
                mel=mel,
                mel_factor=mel_factor,
                used_silver=used_silver,
                given_silver=given_silver,
                balance_silver=balance_silver,
                remaining_tar=remaining_tar,
            )
        )

        return {
            "total_receive": total_receive,
            "readymade_weight": flt(
                return_details["readymade_weight"]
            ),
            "returned_product_weight": flt(
                return_details["returned_product_weight"]
            ),
            "returned_issue_weight": flt(
                return_details["returned_issue_weight"]
            ),
            "returned_output_weight": flt(
                return_details["returned_output_weight"]
            ),
            "returned_waste_weight": flt(
                return_details["returned_waste_weight"]
            ),
            "return_weight": return_weight,
            "goti_weight": goti_weight,
            "kachi_goti_weight": kachi_goti_weight,
            "total_kachi_goti": total_kachi_goti,
            "badla_goti_weight": badla_goti_weight,
            "bg_deduction_percent": bg_deduction_percent,
            "bg_gms": bg_gms,
            "net_weight": net_weight,
            "mel": mel,
            "mel_factor": mel_factor,
            "used_silver": used_silver,
            "given_silver": given_silver,
            "balance_silver": balance_silver,
            "remaining_tar": flt(self.remaining_tar),
            "calculated_payout_amount": flt(
                self.calculated_payout_amount
            ),
            "payout_summary": self.payout_summary,
        }

    def build_pdf_payout_summary(
        self,
        total_receive,
        return_weight,
        goti_weight,
        kachi_goti_weight,
        total_kachi_goti,
        badla_goti_weight,
        bg_deduction_percent,
        bg_gms,
        net_weight,
        mel,
        mel_factor,
        used_silver,
        given_silver,
        balance_silver,
        remaining_tar,
    ):
        """
        Build an auditable, human-readable reconciliation.
        """
        return "\n".join(
            [
                f"Pavtha Issue: {self.pavtha_issue or ''}",
                f"Batch No: {self.batch_no or ''}",
                f"Outsourcer: {self.outsourcer or ''}",
                f"Quality: {self.quality_code or ''}",
                "",
                f"Total Receive: {total_receive:.3f} KG",
                (
                    "Return: "
                    f"{return_weight:.3f} KG "
                    "(Issue + Receive Return-labelled product total)"
                ),
                f"Goti: {goti_weight:.3f} KG",
                f"Kachi Goti: {kachi_goti_weight:.3f} KG",
                (
                    "Total Kachi Goti: "
                    f"{total_kachi_goti:.3f} KG"
                ),
                (
                    "Badla Goti: "
                    f"{badla_goti_weight:.3f} KG"
                ),
                (
                    "B.G. Deduction: "
                    f"{bg_deduction_percent:.3f}%"
                ),
                f"B.G. Gms: {bg_gms:.3f} KG",
                f"Net: {net_weight:.3f} KG",
                f"Mel: {mel:.3f}",
                f"Mel Factor: {mel_factor:.6f}",
                f"Used Silver: {used_silver:.3f} KG",
                f"Given Silver: {given_silver:.3f} KG",
                (
                    "Balance Silver: "
                    f"{balance_silver:.3f} KG"
                ),
                (
                    "Remaining TAR: "
                    f"{remaining_tar:.3f} KG"
                ),
            ]
        )

    def get_last_balance(
        self,
        company,
        department,
        product,
    ):
        return (
            frappe.db.get_value(
                "Inventory Ledger",
                {
                    "company": company,
                    "department": department,
                    "product": product,
                },
                "current_balance",
                order_by="creation desc",
            )
            or 0
        )

    def ledger_exists(self):
        return frappe.db.exists(
            "Inventory Ledger",
            {
                "reference_doctype": self.doctype,
                "reference_name": self.name,
            },
        )

    def post_outputs_and_waste(self):
        """
        Post output and waste inventory using each child row's
        Issue/Receive Type.
        """
        if self.ledger_exists():
            return

        destination_department = "Pavtha"

        for row in self.output_items or []:
            if not row.product or flt(row.weight) <= 0:
                continue

            issue_receive_type = (
                row.issue_receive_type
                or "In-house"
            )

            stock_source = get_or_create_stock_source(
                source_type="Production Receive",
                company=self.company,
                product=row.product,
                source_doctype=self.doctype,
                source_name=self.name,
                source_row=row.name,
                source_date=self.receive_date or today(),
                batch_number=self.batch_no,
                remarks=(
                    f"Pavtha {issue_receive_type} output received"
                ),
            )

            balance = self.get_last_balance(
                self.company,
                destination_department,
                row.product,
            )

            frappe.get_doc(
                {
                    "doctype": "Inventory Ledger",
                    "company": self.company,
                    "department": destination_department,
                    "product": row.product,
                    "batch_number": self.batch_no,
                    "stock_source": stock_source,
                    "in_weight": flt(row.weight),
                    "out_weight": 0,
                    "current_balance": (
                        flt(balance)
                        + flt(row.weight)
                    ),
                    "approx_silver_weight": flt(
                        row.approx_silver_weight
                    ),
                    "transaction_type": "Production Output",
                    "reference_doctype": self.doctype,
                    "reference_name": self.name,
                    "date": self.receive_date or today(),
                    "remarks": (
                        f"Pavtha {issue_receive_type} "
                        f"output received"
                    ),
                }
            ).insert(ignore_permissions=True)

        for row in self.waste_items or []:
            if (
                not row.waste_product
                or flt(row.weight) <= 0
            ):
                continue

            issue_receive_type = (
                row.issue_receive_type
                or "In-house"
            )

            stock_source = get_or_create_stock_source(
                source_type="Production Receive",
                company=self.company,
                product=row.waste_product,
                source_doctype=self.doctype,
                source_name=self.name,
                source_row=row.name,
                source_date=self.receive_date or today(),
                batch_number=self.batch_no,
                remarks=(
                    f"Pavtha {issue_receive_type} waste generated"
                ),
            )

            balance = self.get_last_balance(
                self.company,
                destination_department,
                row.waste_product,
            )

            frappe.get_doc(
                {
                    "doctype": "Inventory Ledger",
                    "company": self.company,
                    "department": destination_department,
                    "product": row.waste_product,
                    "batch_number": self.batch_no,
                    "in_weight": flt(row.weight),
                    "out_weight": 0,
                    "current_balance": (
                        flt(balance)
                        + flt(row.weight)
                    ),
                    "approx_silver_weight": flt(
                        row.approx_silver_weight
                    ),
                    "transaction_type": "Waste Generated",
                    "reference_doctype": self.doctype,
                    "reference_name": self.name,
                    "date": self.receive_date or today(),
                    "remarks": (
                        f"Pavtha {issue_receive_type} "
                        f"waste generated"
                    ),
                }
            ).insert(ignore_permissions=True)


@frappe.whitelist()
def preview_pdf_payout(doc):
    """
    Calculate an unsaved Draft preview through the authoritative Python
    implementation.

    JavaScript does not reproduce the business formula.
    """
    if isinstance(doc, str):
        doc = json.loads(doc)

    preview_doc = frappe.get_doc(doc)

    if preview_doc.doctype != "Pavtha Receive":
        frappe.throw(
            _("Only Pavtha Receive can use this preview.")
        )

    if not preview_doc.pavtha_issue:
        return {
            "return_weight": 0,
            "readymade_weight": 0,
            "returned_product_weight": 0,
            "used_silver": 0,
            "given_silver": 0,
            "balance_silver": 0,
            "remaining_tar": 0,
            "calculated_payout_amount": 0,
            "payout_summary": "",
        }

    preview_doc.pull_issue_details()
    preview_doc.set_child_type_defaults()
    preview_doc.calculate_totals()
    preview_doc.set_approx_silver()
    preview_doc.calculate_payout()

    return preview_doc.calculate_pdf_payout()


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def pavtha_issue_query(
    doctype,
    txt,
    searchfield,
    start,
    page_len,
    filters,
):
    """
    Search available Pavtha Issues and show child-row transaction types.
    """
    return frappe.db.sql(
        """
        SELECT
            pi.name,
            CONCAT(
                'Batch: ',
                COALESCE(pi.batch_no, pi.name),
                ' | Issue: ',
                pi.name,
                ' | Type: ',
                COALESCE(
                    (
                        SELECT GROUP_CONCAT(
                            DISTINCT pii.issue_receive_type
                            ORDER BY pii.issue_receive_type
                            SEPARATOR ', '
                        )
                        FROM `tabPavtha Issue Item` pii
                        WHERE pii.parent = pi.name
                          AND pii.parenttype = 'Pavtha Issue'
                          AND pii.parentfield = 'issue_items'
                          AND COALESCE(
                              pii.issue_receive_type,
                              ''
                          ) != ''
                    ),
                    'In-house'
                ),
                ' | Date: ',
                DATE_FORMAT(
                    COALESCE(pi.issue_date, pi.creation),
                    '%%d-%%m-%%Y'
                )
            ) AS description
        FROM `tabPavtha Issue` pi
        WHERE pi.docstatus IN (0, 1)
          AND NOT EXISTS (
              SELECT 1
              FROM `tabPavtha Receive` pr
              WHERE pr.docstatus = 1
                AND pr.pavtha_issue = pi.name
          )
          AND (
              pi.name LIKE %(txt)s
              OR COALESCE(pi.batch_no, '') LIKE %(txt)s
              OR COALESCE(pi.company, '') LIKE %(txt)s
          )
        ORDER BY pi.creation DESC
        LIMIT %(start)s, %(page_len)s
        """,
        {
            "txt": f"%{txt}%",
            "start": start,
            "page_len": page_len,
        },
    )
