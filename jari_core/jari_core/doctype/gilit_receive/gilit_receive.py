import frappe
from frappe.model.document import Document
from frappe.utils import cint, flt, today
from jari_core.jari_core.stock_utils import get_or_create_stock_source


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
        self.sync_saleable_product()
        self.validate_saleable_product(
            require_complete=False
        )
        self.set_approx_silver()

    def before_submit(self):
        self.calculate_totals()
        self.sync_saleable_product()
        self.validate_saleable_product(
            require_complete=True
        )

    def on_submit(self):
        self.set_approx_silver()

        self.db_set(
            "approx_silver_weight",
            flt(
                self.approx_silver_weight
            ),
        )

        self.apply_peti_receive_result()

        # Exact KASAB source is consumed only now,
        # because Receive determines actual Peti usage.
        self.post_peti_source_consumption()

        self.post_outputs_and_waste()

        frappe.db.set_value(
            "Gilit Issue",
            self.gilit_issue,
            "status",
            "Closed",
            update_modified=False,
        )

    def on_cancel(self):
        from jari_core.jari_core.stock_utils import (
            reverse_reference_inventory_ledger,
        )

        # Reverse KASAB consumption + Final Jari/Waste
        # before restoring the physical Peti state.
        reverse_reference_inventory_ledger(
            self
        )

        self.restore_original_peti_state()

        if self.gilit_issue:
            frappe.db.set_value(
                "Gilit Issue",
                self.gilit_issue,
                "status",
                "Issued",
                update_modified=False,
            )

    def pull_issue_details(self):
        if not self.gilit_issue:
            return

        issue = frappe.get_doc(
            "Gilit Issue",
            self.gilit_issue,
        )

        self.company = issue.company
        self.active_batch_no = issue.gilit_batch_no
        self.process_master = issue.process_master
        self.quality_code = issue.quality_code

        self.operator = (
            getattr(issue, "gilit_karigar", None)
            or getattr(issue, "operator", None)
        )

        # Gilit Issue now assigns the complete currently available Peti.
        # Spindal Peti weights are treated as KG.
        self.total_input_weight = flt(
            issue.total_net_weight
        )

        # Do not rebuild rows on every save.
        if self.output_items:
            return

        seen_petis = set()

        for issue_peti in issue.peti_items or []:
            peti_name = issue_peti.spindal_peti_entry

            if not peti_name or peti_name in seen_petis:
                continue

            seen_petis.add(peti_name)

            peti = frappe.get_doc(
                "Spindal Peti Entry",
                peti_name,
            )

            current_bobbin = cint(
                peti.remaining_bobbin
                or peti.bobbin_count
                or peti.nang
            )

            if current_bobbin <= 0:
                frappe.throw(
                    f"Peti {peti.name} has no available bobbins."
                )

            if peti.status in (
                "Fully Consumed",
                "Cancelled",
            ):
                frappe.throw(
                    f"Peti {peti.name} cannot be received because "
                    f"its status is {peti.status}."
                )

            row = self.append(
                "output_items",
                {},
            )

            row.spindal_peti_entry = peti.name
            row.peti_no = peti.peti_no or peti.name
            row.total_bobbin = current_bobbin

            # Default to full consumption of the currently
            # available Peti. For full consumption, Gilit Baad
            # starts from the Peti's existing Baad Weight.
            row.remaining_bobbin = 0
            row.gilit_baad_weight = flt(
                peti.baad_weight
            )

            # Legacy field retained but no longer used.
            row.issued_bobbin = 0

            row.uom = (
                peti.uom
                or issue_peti.uom
                or "KG"
            )

            # Capture the exact pre-Receive Peti state.
            row.original_bobbin_count = cint(
                peti.bobbin_count
                or peti.nang
            )

            row.original_remaining_bobbin = current_bobbin
            row.original_gross_weight = flt(peti.gross_weight)
            row.original_baad_weight = flt(peti.baad_weight)
            row.original_net_weight = flt(peti.net_weight)

            row.original_remaining_net_weight = flt(
                peti.remaining_net_weight
                or peti.net_weight
            )

            row.original_status = peti.status

            # Default values represent full consumption.
            # Consumed Net = Gross - Gilit Baad.
            row.used_net_weight = max(
                0,
                flt(row.original_gross_weight)
                - flt(row.gilit_baad_weight),
            )

            row.weight = flt(
                row.used_net_weight
            )

    def get_default_jari_product(self):
        """
        Return a deterministic JARI product only when there is
        no ambiguity.

        Priority:
        1. One unique legacy Final Jari Product already present
           in the Peti rows and tagged JARI.
        2. Exactly one Product Master tagged JARI.

        If multiple JARI products exist, the operator must choose.
        """
        legacy_products = {
            row.product
            for row in self.output_items or []
            if row.product
            and frappe.db.get_value(
                "Product Master",
                row.product,
                "product_tag",
            ) == "JARI"
        }

        if len(legacy_products) == 1:
            return next(iter(legacy_products))

        products = frappe.get_all(
            "Product Master",
            filters={
                "product_tag": "JARI",
            },
            pluck="name",
            limit=2,
        )

        if len(products) == 1:
            return products[0]

        return None

    def sync_saleable_product(self):
        """
        Keep the sale-ready packing row in sync with the
        authoritative Gilit calculation.

        Gilit physical stock is tracked in KG.  Marks and Firki are
        commercial packing quantities derived from Filled Firki.
        """
        if not self.gilit_issue:
            return

        if not self.saleable_products:
            self.append(
                "saleable_products",
                {},
            )

        default_product = (
            self.get_default_jari_product()
        )

        for row in (
            self.saleable_products
            or []
        ):
            if not row.product and default_product:
                row.product = default_product

            row.uom = "KG"
            row.filled_firki = cint(
                self.filled_firki
            )
            row.weight_of_one_firki = flt(
                self.weight_of_one_firki,
                6,
            )
            row.marks = cint(
                row.filled_firki // 4
            )
            row.vadharo_firki = cint(
                row.filled_firki % 4
            )
            row.total_weight = flt(
                self.total_jari_production,
                6,
            )

    def validate_saleable_product(
        self,
        *,
        require_complete,
    ):
        rows = (
            self.saleable_products
            or []
        )

        if len(rows) > 1:
            frappe.throw(
                "Gilit Receive supports exactly one "
                "saleable Jari output row because Filled Firki "
                "and Weight of One Firki are parent-level "
                "calculations."
            )

        if not rows:
            if require_complete:
                frappe.throw(
                    "Output Product Detail (Jari Sale) "
                    "is required before Submit."
                )
            return

        row = rows[0]

        if row.product:
            product_tag = frappe.db.get_value(
                "Product Master",
                row.product,
                "product_tag",
            )

            if product_tag != "JARI":
                frappe.throw(
                    f"Saleable Output Product {row.product} "
                    "must have Product Tag JARI."
                )

        if not require_complete:
            return

        if not row.product:
            frappe.throw(
                "Please select the JARI Output Product "
                "in Output Product Detail (Jari Sale)."
            )

        if cint(self.filled_firki) <= 0:
            frappe.throw(
                "Filled Firki must be greater than zero "
                "before Gilit Receive can be submitted."
            )

        if flt(self.total_jari_production) <= 0:
            frappe.throw(
                "Total Jari Production must be greater "
                "than zero before Gilit Receive can be submitted."
            )

        if flt(self.weight_of_one_firki) <= 0:
            frappe.throw(
                "Weight of One Firki must be greater "
                "than zero before Gilit Receive can be submitted."
            )

        expected_marks = cint(
            cint(self.filled_firki) // 4
        )
        expected_vadharo = cint(
            cint(self.filled_firki) % 4
        )

        if cint(row.marks) != expected_marks:
            frappe.throw(
                "Marks calculation mismatch in "
                "Output Product Detail (Jari Sale)."
            )

        if (
            cint(row.vadharo_firki)
            != expected_vadharo
        ):
            frappe.throw(
                "Vadharo Firki calculation mismatch in "
                "Output Product Detail (Jari Sale)."
            )

        if abs(
            flt(row.total_weight, 6)
            - flt(
                self.total_jari_production,
                6,
            )
        ) > 0.000001:
            frappe.throw(
                "Saleable Total Weight must equal "
                "Total Jari Production."
            )

    def get_quality_purity(self):
        if not self.quality_code:
            return 0

        return flt(
            frappe.db.get_value(
                "Quality Master",
                self.quality_code,
                "silver_purity_percent"
            ) or 0
        )

    def calculate_approx_silver(self, weight):
        purity = self.get_quality_purity()
        return flt(weight) - (flt(weight) * flt(purity) / 100)

    def set_approx_silver(self):
        output_approx = self.calculate_approx_silver(self.total_output_weight)
        wastage_approx = 0

        for row in self.waste_items or []:
            row.approx_silver_weight = self.calculate_approx_silver(row.weight)
            wastage_approx += flt(row.approx_silver_weight)

        self.approx_silver_output = output_approx
        self.approx_silver_wastage = wastage_approx
        self.approx_silver_weight = output_approx + wastage_approx

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
            frappe.throw(
                "At least one Final Jari Product/Peti Detail "
                "or Waste Item is required."
            )

        seen_petis = set()

        for row in self.output_items or []:
            if not row.spindal_peti_entry:
                continue

            if row.spindal_peti_entry in seen_petis:
                frappe.throw(
                    f"Duplicate Spindal Peti Entry selected: "
                    f"{row.spindal_peti_entry}"
                )

            seen_petis.add(
                row.spindal_peti_entry
            )

            peti = frappe.get_doc(
                "Spindal Peti Entry",
                row.spindal_peti_entry,
            )

            if peti.docstatus != 1:
                frappe.throw(
                    f"Peti {peti.name} is not submitted."
                )

            if peti.status in (
                "Fully Consumed",
                "Cancelled",
            ):
                frappe.throw(
                    f"Peti {peti.name} cannot be received because "
                    f"its status is {peti.status}."
                )

            # Populate snapshots if an older draft row is missing them.
            if not cint(row.original_bobbin_count):
                row.original_bobbin_count = cint(
                    peti.bobbin_count
                    or peti.nang
                )

            if not cint(row.original_remaining_bobbin):
                row.original_remaining_bobbin = cint(
                    peti.remaining_bobbin
                    or peti.bobbin_count
                    or peti.nang
                )

            if not flt(row.original_gross_weight):
                row.original_gross_weight = flt(
                    peti.gross_weight
                )

            if not flt(row.original_baad_weight):
                row.original_baad_weight = flt(
                    peti.baad_weight
                )

            if not flt(row.original_net_weight):
                row.original_net_weight = flt(
                    peti.net_weight
                )

            if not flt(row.original_remaining_net_weight):
                row.original_remaining_net_weight = flt(
                    peti.remaining_net_weight
                    or peti.net_weight
                )

            if not row.original_status:
                row.original_status = peti.status

            available_bobbin = cint(
                row.original_remaining_bobbin
                or row.original_bobbin_count
            )

            remaining_bobbin = cint(
                row.remaining_bobbin
            )

            gilit_baad_weight = flt(
                row.gilit_baad_weight
            )

            original_gross = flt(
                row.original_gross_weight
            )

            original_baad = flt(
                row.original_baad_weight
            )

            if available_bobbin <= 0:
                frappe.throw(
                    f"Peti {row.peti_no or peti.name} "
                    f"has no available bobbins."
                )

            if remaining_bobbin < 0:
                frappe.throw(
                    f"Remaining Bobbin cannot be negative "
                    f"for Peti {row.peti_no or peti.name}."
                )

            if remaining_bobbin > available_bobbin:
                frappe.throw(
                    f"Remaining Bobbin cannot exceed "
                    f"{available_bobbin} for Peti "
                    f"{row.peti_no or peti.name}."
                )

            if gilit_baad_weight < 0:
                frappe.throw(
                    f"Gilit Baad Weight cannot be negative "
                    f"for Peti {row.peti_no or peti.name}."
                )

            if gilit_baad_weight > original_gross:
                frappe.throw(
                    f"Gilit Baad Weight cannot exceed Gross Weight "
                    f"{original_gross} KG for Peti "
                    f"{row.peti_no or peti.name}."
                )

            if remaining_bobbin > 0:
                remaining_net_weight = (
                    gilit_baad_weight
                    - original_baad
                )

                if remaining_net_weight <= 0:
                    frappe.throw(
                        f"For partial Peti "
                        f"{row.peti_no or peti.name}, "
                        f"Gilit Baad Weight must be greater than "
                        f"the original Baad Weight "
                        f"{original_baad} KG."
                    )

            consumed_weight = (
                original_gross
                - gilit_baad_weight
            )

            if consumed_weight <= 0:
                frappe.throw(
                    f"Consumed Net Weight must be greater than zero "
                    f"for Peti {row.peti_no or peti.name}."
                )

            row.used_net_weight = consumed_weight
            row.weight = consumed_weight

            if not row.uom:
                row.uom = peti.uom or "KG"

        if flt(self.gross_weight_without_dabba) < 0:
            frappe.throw(
                "G.W Without Dabba Weight cannot be negative."
            )

        if flt(self.firki_weight) < 0:
            frappe.throw(
                "Firki Weight cannot be negative."
            )

        if flt(self.filled_firki) < 0:
            frappe.throw(
                "Filled Firki cannot be negative."
            )

        if flt(self.firki_nang) < 0:
            frappe.throw(
                "Firki Nang cannot be negative."
            )

    def calculate_totals(self):
        self.total_output_weight = sum(
            flt(row.used_net_weight or row.weight)
            for row in self.output_items or []
        )

        self.total_waste_weight = sum(
            flt(row.weight)
            for row in self.waste_items or []
        )

        self.rangayel_kasab_weight = (
            flt(self.gross_weight_without_dabba)
            - flt(self.firki_weight)
        )

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

        self.loss_weight = (
            flt(self.total_input_weight)
            - flt(self.total_output_weight)
            - flt(self.total_waste_weight)
        )

        self.loss_percent = (
            flt(self.loss_weight) / flt(self.total_input_weight) * 100
            if flt(self.total_input_weight) else 0
        )

        self.loss_standard_percent = frappe.db.get_value(
            "Loss Standard Master",
            {"department": "Gilit"},
            "standard_loss_percent"
        ) or 0

        self.loss_status = (
            "Excess Loss"
            if flt(self.loss_percent) > flt(self.loss_standard_percent)
            else "OK"
        )

    def apply_peti_receive_result(self):
        """
        Update each source Peti using the measurements entered in
        Gilit Receive.

        The row is locked so that two Receive transactions cannot
        update the same Peti concurrently.
        """
        for row in self.output_items or []:
            if not row.spindal_peti_entry:
                continue

            frappe.db.sql(
                """
                SELECT name
                FROM `tabSpindal Peti Entry`
                WHERE name = %s
                FOR UPDATE
                """,
                row.spindal_peti_entry,
            )

            current = frappe.db.get_value(
                "Spindal Peti Entry",
                row.spindal_peti_entry,
                [
                    "bobbin_count",
                    "remaining_bobbin",
                    "gross_weight",
                    "baad_weight",
                    "net_weight",
                    "remaining_net_weight",
                    "status",
                ],
                as_dict=True,
            )

            if not current:
                frappe.throw(
                    f"Spindal Peti Entry "
                    f"{row.spindal_peti_entry} does not exist."
                )

            expected_bobbin = cint(
                row.original_remaining_bobbin
                or row.original_bobbin_count
            )

            current_bobbin = cint(
                current.remaining_bobbin
                or current.bobbin_count
            )

            if current_bobbin != expected_bobbin:
                frappe.throw(
                    f"Peti {row.peti_no or row.spindal_peti_entry} "
                    f"was changed after this Receive was created. "
                    f"Expected available bobbins: {expected_bobbin}; "
                    f"current available bobbins: {current_bobbin}. "
                    f"Reload the document and try again."
                )

            if current.status in (
                "Fully Consumed",
                "Cancelled",
            ):
                frappe.throw(
                    f"Peti {row.peti_no or row.spindal_peti_entry} "
                    f"cannot be updated because its status is "
                    f"{current.status}."
                )

            remaining_bobbin = cint(
                row.remaining_bobbin
            )

            if remaining_bobbin == 0:
                values = {
                    "bobbin_count": 0,
                    "remaining_bobbin": 0,
                    "gross_weight": 0,
                    "baad_weight": 0,
                    "net_weight": 0,
                    "remaining_net_weight": 0,
                    "status": "Fully Consumed",
                }
            else:
                remaining_net_weight = (
                    flt(row.gilit_baad_weight)
                    - flt(row.original_baad_weight)
                )

                values = {
                    "bobbin_count": remaining_bobbin,
                    "remaining_bobbin": remaining_bobbin,
                    "gross_weight": flt(
                        row.gilit_baad_weight
                    ),
                    "baad_weight": flt(
                        row.original_baad_weight
                    ),
                    "net_weight": remaining_net_weight,
                    "remaining_net_weight":
                        remaining_net_weight,
                    "status": "Partial",
                }

            frappe.db.set_value(
                "Spindal Peti Entry",
                row.spindal_peti_entry,
                values,
                update_modified=True,
            )

    def restore_original_peti_state(self):
        """
        Restore the exact Peti state captured before this Receive
        was submitted.
        """
        for row in self.output_items or []:
            if not row.spindal_peti_entry:
                continue

            if not row.original_status:
                frappe.throw(
                    f"Original Peti snapshot is missing for "
                    f"{row.peti_no or row.spindal_peti_entry}. "
                    f"Cancellation cannot safely continue."
                )

            frappe.db.sql(
                """
                SELECT name
                FROM `tabSpindal Peti Entry`
                WHERE name = %s
                FOR UPDATE
                """,
                row.spindal_peti_entry,
            )

            frappe.db.set_value(
                "Spindal Peti Entry",
                row.spindal_peti_entry,
                {
                    "bobbin_count": cint(
                        row.original_bobbin_count
                    ),
                    "remaining_bobbin": cint(
                        row.original_remaining_bobbin
                    ),
                    "gross_weight": flt(
                        row.original_gross_weight
                    ),
                    "baad_weight": flt(
                        row.original_baad_weight
                    ),
                    "net_weight": flt(
                        row.original_net_weight
                    ),
                    "remaining_net_weight": flt(
                        row.original_remaining_net_weight
                    ),
                    "status": row.original_status,
                },
                update_modified=True,
            )

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
        existing_output = frappe.db.exists(
            "Inventory Ledger",
            {
                "reference_doctype":
                    self.doctype,
                "reference_name":
                    self.name,
                "transaction_type":
                    ["in", [
                        "Production Output",
                        "Waste Generated",
                    ]],
            },
        )

        if existing_output:
            return

        # Final Jari physical stock is created from the dedicated
        # sale-ready packing row, not from Peti consumption rows.
        for row in (
            self.saleable_products
            or []
        ):
            if (
                not row.product
                or not flt(row.total_weight)
            ):
                continue

            weight_kg = flt(
                row.total_weight,
                6,
            )

            stock_source = get_or_create_stock_source(
                source_type="Production Receive",
                company=self.company,
                product=row.product,
                source_doctype=self.doctype,
                source_name=self.name,
                source_row=row.name,
                source_date=self.receive_date or today(),
                batch_number=self.active_batch_no,
                remarks="Saleable Final Jari received from Gilit",
            )

            frappe.db.set_value(
                "Gilit Saleable Product Item",
                row.name,
                "stock_source",
                stock_source,
                update_modified=False,
            )
            row.stock_source = stock_source

            balance = self.get_last_balance(
                self.company,
                "Gilit",
                row.product,
            )

            frappe.get_doc({
                "doctype": "Inventory Ledger",
                "company": self.company,
                "department": "Gilit",
                "product": row.product,
                "batch_number": self.active_batch_no,
                "stock_source": stock_source,
                "in_weight": weight_kg,
                "out_weight": 0,
                "current_balance": (
                    flt(balance)
                    + weight_kg
                ),
                "approx_silver_weight": flt(
                    self.calculate_approx_silver(
                        weight_kg
                    )
                ),
                "transaction_type": "Production Output",
                "reference_doctype": self.doctype,
                "reference_name": self.name,
                "date": self.receive_date or today(),
                "remarks": "Saleable Final Jari received from Gilit",
            }).insert(
                ignore_permissions=True
            )

        for row in self.waste_items:
            if not row.waste_product or not flt(row.weight):
                continue

            weight_kg = flt(row.weight)

            stock_source = get_or_create_stock_source(
                source_type="Production Receive",
                company=self.company,
                product=row.waste_product,
                source_doctype=self.doctype,
                source_name=self.name,
                source_row=row.name,
                source_date=self.receive_date or today(),
                batch_number=self.active_batch_no,
                remarks="Gilit waste generated",
            )

            balance = self.get_last_balance(self.company, "Gilit", row.waste_product)

            frappe.get_doc({
                "doctype": "Inventory Ledger",
                "company": self.company,
                "department": "Gilit",
                "product": row.waste_product,
                "batch_number": self.active_batch_no,
                "stock_source": stock_source,
                "in_weight": weight_kg,
                "out_weight": 0,
                "current_balance": flt(balance) + weight_kg,
                "approx_silver_weight": flt(row.approx_silver_weight),
                "transaction_type": "Waste Generated",
                "reference_doctype": self.doctype,
                "reference_name": self.name,
                "date": self.receive_date or today(),
                "remarks": "Gilit waste generated"
            }).insert(ignore_permissions=True)

    def post_peti_source_consumption(self):
        from jari_core.jari_core.stock_utils import (
            consume_selected_stock_source,
        )

        for row in (
            self.output_items
            or []
        ):
            if not row.spindal_peti_entry:
                continue

            qty = flt(
                row.used_net_weight
                or row.weight,
                6,
            )

            if qty <= 0:
                continue

            source_row = (
                frappe.db.get_value(
                    "Inventory Ledger",
                    {
                        "reference_doctype":
                            "Spindal Peti Entry",
                        "reference_name":
                            row.spindal_peti_entry,
                        "transaction_type":
                            "Production Output",
                    },
                    [
                        "stock_source",
                        "product",
                    ],
                    order_by="creation desc",
                    as_dict=True,
                )
            )

            # Historical Peti:
            # no source existed when it was produced.
            # Never assign a guessed source now.
            if (
                not source_row
                or not source_row.stock_source
            ):
                continue

            consume_selected_stock_source(
                doc=self,
                stock_source=
                    source_row.stock_source,
                source_department=
                    "Gilit",
                product=
                    source_row.product,
                required_qty=
                    qty,
                batch_no=
                    self.active_batch_no,
                posting_date=
                    self.receive_date
                    or today(),
                transaction_type=
                    "Production Input",
                remarks=(
                    "Actual KASAB Peti "
                    "consumption in Gilit Receive"
                ),
            )


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def gilit_issue_query(doctype, txt, searchfield, start, page_len, filters):
    return frappe.db.sql("""
        SELECT
            gi.name,
            CONCAT(
                'Batch: ', COALESCE(gi.gilit_batch_no, gi.name),
                ' | Issue: ', gi.name,
                ' | Date: ', DATE_FORMAT(COALESCE(gi.issue_date, gi.creation), '%%d-%%m-%%Y')
            ) AS description
        FROM `tabGilit Issue` gi
        WHERE gi.docstatus = 1
          AND NOT EXISTS (
              SELECT 1
              FROM `tabGilit Receive` gr
              WHERE gr.docstatus = 1
                AND gr.gilit_issue = gi.name
          )
          AND (
              gi.name LIKE %(txt)s
              OR COALESCE(gi.gilit_batch_no, '') LIKE %(txt)s
              OR COALESCE(gi.company, '') LIKE %(txt)s
          )
        ORDER BY gi.creation DESC
        LIMIT %(start)s, %(page_len)s
    """, {
        "txt": f"%{txt}%",
        "start": start,
        "page_len": page_len
    })
