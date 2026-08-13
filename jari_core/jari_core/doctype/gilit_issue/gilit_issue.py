import frappe
from frappe.model.document import Document
from frappe.utils import flt, cint, today
from jari_core.jari_core.doctype.process_master.process_master import (
    apply_process_department_defaults,
    validate_process_departments,
    validate_process_issue_type,
    validate_process_party,
)


def gm_value(value, uom=None):
    uom = (uom or "").strip().lower()
    if uom in ["kg", "kilogram", "kilograms"]:
        return flt(value) * 1000
    return flt(value)


def resolve_product(product):
    if not product:
        return product

    if frappe.db.exists("Product Master", product):
        return product

    found = frappe.db.get_value("Product Master", {"product_name": product}, "name")
    if found:
        return found

    found = frappe.db.get_value("Product Master", {"product_name": ["like", f"%{product}%"]}, "name")
    return found or product


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
def get_product_stock_for_gilit(company, product, department=None):
    product = resolve_product(product)

    if not company or not product:
        return {
            "product": product,
            "current_stock": 0,
            "uom": "",
            "source_department": "",
            "breakdown": ""
        }

    dept_rows = frappe.db.sql("""
        SELECT DISTINCT department
        FROM `tabInventory Ledger`
        WHERE company = %s
          AND product = %s
          AND IFNULL(department, '') != ''
    """, (company, product), as_dict=True)

    total_stock = 0
    source_department = ""
    breakdown = []

    preferred_departments = []
    if department:
        preferred_departments.append(department)

    for d in ["Gilit", "gilit", "GILIT"]:
        if d not in preferred_departments:
            preferred_departments.append(d)

    all_departments = preferred_departments + [
        d.department for d in dept_rows if d.department not in preferred_departments
    ]

    for dept in all_departments:
        balance = frappe.db.get_value(
            "Inventory Ledger",
            {
                "company": company,
                "department": dept,
                "product": product
            },
            "current_balance",
            order_by="creation desc"
        ) or 0

        if flt(balance) > 0:
            total_stock += flt(balance)
            breakdown.append(f"{dept}: {balance}")

            if not source_department:
                source_department = dept

    uom = ""
    meta = frappe.get_meta("Product Master")

    for fieldname in ["uom", "stock_uom", "default_uom"]:
        if meta.has_field(fieldname):
            uom = frappe.db.get_value("Product Master", product, fieldname) or ""
            if uom:
                break

    return {
        "product": product,
        "current_stock": total_stock,
        "uom": uom,
        "source_department": source_department,
        "breakdown": ", ".join(breakdown)
    }


def gilit_qty_to_kg(value, uom):
    """
    Normalize Metal Water issue quantities to Inventory Ledger KG.

    Supported:
      KG   -> unchanged
      gram -> divide by 1000

    Unknown/custom units are rejected instead of being silently
    interpreted incorrectly.
    """
    qty = flt(value, 9)

    unit = (
        (uom or "")
        .strip()
        .lower()
    )

    if unit in (
        "kg",
        "kilogram",
        "kilograms",
    ):
        return flt(
            qty,
            9,
        )

    if unit in (
        "gram",
        "grams",
        "gm",
        "g",
    ):
        return flt(
            qty / 1000,
            9,
        )

    frappe.throw(
        f"Unsupported Metal Water UOM: "
        f"{uom or '(blank)'}. "
        f"Please use KG or gram."
    )

class GilitIssue(Document):

    def validate(self):
        self.validate_process_assignments()
        self.set_defaults()
        validate_process_departments(self)
        validate_process_issue_type(
            self,
            "Gilit Issue",
        )
        self.validate_peti_items()
        self.validate_metal_water_inputs()
        self.calculate_totals()

    def validate_process_assignments(self):
        validate_process_party(
            self,
            fieldname="gilit_karigar",
            master_doctype="Worker Master",
            label="Gilit Karigar",
            require_active=True,
        )
        validate_process_party(
            self,
            fieldname="quality_code",
            master_doctype="Quality Master",
            label="Quality",
        )

    def on_submit(self):
        # Peti consumption is now measured and applied in Gilit Receive.
        # Gilit Issue only reserves/assigns the selected Peti.
        self.post_inventory_transfer()
        frappe.db.set_value(
            self.doctype,
            self.name,
            "status",
            "Issued",
        )

    def set_defaults(self):
        apply_process_department_defaults(self)

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
        qualities = set()

        for row in self.peti_items:
            if not row.spindal_peti_entry:
                frappe.throw("Spindal Peti Entry is required.")

            if row.spindal_peti_entry in seen:
                frappe.throw(f"Duplicate Spindal Peti Entry selected: {row.spindal_peti_entry}")

            seen.add(row.spindal_peti_entry)

            peti = frappe.get_doc(
                "Spindal Peti Entry",
                row.spindal_peti_entry
            )

            peti_quality = (
                peti.quality_code
                or getattr(peti, "quality", None)
            )

            if not peti_quality:
                frappe.throw(
                    f"Quality is missing in Spindal Peti {peti.name}."
                )

            qualities.add(peti_quality)

            if len(qualities) > 1:
                frappe.throw(
                    "All Spindal Peti Entries in one Gilit Issue "
                    "must have the same Quality."
                )

            if peti.docstatus != 1:
                frappe.throw(f"Peti {peti.name} is not submitted.")

            total_bobbin = self.get_total_bobbin_from_peti(peti)
            available = self.get_available_bobbin_from_peti(peti)

            if total_bobbin <= 0:
                frappe.throw(f"Bobbin Count is missing in Peti {peti.name}.")

            if available <= 0 or peti.status == "Fully Consumed":
                frappe.throw(f"Peti {peti.name} is already fully consumed.")

            row.peti_no = peti.peti_no or peti.name
            row.quality_code = peti_quality
            row.khata_no = peti.khata_no
            row.product = self.get_kasab_product()
            row.uom = peti.uom or row.uom or "KG"
            row.gross_weight = flt(peti.gross_weight)
            row.baad_weight = flt(peti.baad_weight)
            row.net_weight = flt(peti.net_weight)
            # For a partial Peti, current available bobbins become
            # the Total Bobbin shown in the next Gilit Issue.
            row.total_bobbin = available
            row.available_bobbin = available
            row.issued_bobbin = 0
            row.balance_bobbin_after_issue = 0
            row.peti_status = peti.status
            row.operator_name = peti.operator

            row.stock_source = (
                frappe.db.get_value(
                    "Inventory Ledger",
                    {
                        "reference_doctype":
                            "Spindal Peti Entry",
                        "reference_name":
                            peti.name,
                        "transaction_type":
                            "Production Output",
                    },
                    "stock_source",
                    order_by="creation desc",
                )
                or ""
            )

        self.quality_code = (
            next(iter(qualities))
            if qualities
            else None
        )

    def validate_metal_water_inputs(self):
        from jari_core.jari_core.stock_utils import (
            prepare_selected_stock_source,
        )

        for row in (
            self.metal_water_inputs
            or []
        ):
            if not row.product:
                frappe.throw(
                    "Product Name is required "
                    "in Metal Water Input."
                )

            row.product = resolve_product(
                row.product
            )

            if not row.input_date:
                row.input_date = (
                    self.issue_date
                    or today()
                )

            if flt(row.issued_aani) <= 0:
                frappe.throw(
                    f"Issued Aani must be greater "
                    f"than zero for {row.product}."
                )

            if not row.uom:
                row.uom = (
                    frappe.db.get_value(
                        "Product Master",
                        row.product,
                        "unit",
                    )
                    or "KG"
                )

            required_kg = gilit_qty_to_kg(
                row.issued_aani,
                row.uom,
            )

            if required_kg <= 0:
                frappe.throw(
                    f"Normalized issue quantity "
                    f"must be greater than zero "
                    f"for {row.product}."
                )

            row.issued_weight_kg = (
                flt(
                    required_kg,
                    6,
                )
            )

            prepare_selected_stock_source(
                doc=self,
                row=row,
                required_qty=
                    required_kg,
            )

            row.current_stock = flt(
                row.source_available_weight,
                6,
            )

    def calculate_totals(self):
        self.total_peti = 0
        self.total_net_weight = 0

        for row in self.peti_items or []:
            if not row.spindal_peti_entry:
                continue

            self.total_peti += 1

            # Spindal Peti weights are normalized to KG.
            # The whole currently available Peti is assigned to Gilit;
            # actual consumption is measured in Gilit Receive.
            self.total_net_weight += flt(row.net_weight)

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

            frappe.db.set_value("Spindal Peti Entry", peti.name, {
                "remaining_bobbin": restored,
                "status": "Received" if restored == total_bobbin else "Partial"
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

    def post_out_from_available_department(self, product, required_qty, transaction_type, remarks, uom=None):
        required_qty = flt(required_qty)
        if required_qty <= 0:
            return

        stock_info = get_product_stock_for_gilit(
            self.company,
            product,
            self.to_department
        )

        if flt(stock_info.get("current_stock")) < required_qty:
            frappe.throw(
                f"Insufficient stock for {product}. "
                f"Available: {stock_info.get('current_stock')}, Required: {required_qty}. "
                f"Breakdown: {stock_info.get('breakdown') or 'No stock found'}"
            )

        remaining_qty = required_qty

        dept_rows = frappe.db.sql("""
            SELECT DISTINCT department
            FROM `tabInventory Ledger`
            WHERE company = %s
              AND product = %s
              AND IFNULL(department, '') != ''
        """, (self.company, product), as_dict=True)

        preferred = []
        for dept in [self.to_department, "Gilit", "gilit", "GILIT"]:
            if dept and dept not in preferred:
                preferred.append(dept)

        departments = preferred + [
            d.department for d in dept_rows if d.department not in preferred
        ]

        for dept in departments:
            if remaining_qty <= 0:
                break

            balance = self.get_last_balance(self.company, dept, product)
            if flt(balance) <= 0:
                continue

            issue_qty = min(flt(balance), remaining_qty)

            frappe.get_doc({
                "doctype": "Inventory Ledger",
                "company": self.company,
                "department": dept,
                "product": product,
                "batch_number": self.gilit_batch_no,
                "in_weight": 0,
                "out_weight": issue_qty,
                "current_balance": flt(balance) - issue_qty,
                "transaction_type": transaction_type,
                "reference_doctype": self.doctype,
                "reference_name": self.name,
                "date": self.issue_date or today(),
                "remarks": remarks
            }).insert(ignore_permissions=True)

            remaining_qty -= issue_qty

        if remaining_qty > 0:
            frappe.throw(f"Unable to fully issue {product}. Remaining Qty: {remaining_qty}")

    def post_inventory_transfer(self):
        from jari_core.jari_core.stock_utils import (
            consume_selected_stock_source,
            add_source_linked_transfer_in,
            get_stock_source_locations,
        )

        if self.ledger_exists():
            return

        kasab_product = (
            self.get_kasab_product()
        )

        # ====================================================
        # PETI / KASAB
        # ====================================================

        for row in (
            self.peti_items
            or []
        ):

            if not row.spindal_peti_entry:
                continue

            weight = flt(
                row.net_weight,
                6,
            )

            if weight <= 0:
                continue

            # Determine whether this Peti has actually posted
            # its KASAB Production Output yet.
            peti_ledger = frappe.db.get_value(
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
                    "name",
                    "stock_source",
                ],
                order_by="creation desc",
                as_dict=True,
            )

            # A NEW Peti submitted while its linked Spindal
            # Issue is still Draft has no Production Output.
            # It must not consume arbitrary legacy KASAB.
            if not peti_ledger:
                frappe.throw(
                    f"Spindal Peti "
                    f"{row.spindal_peti_entry} "
                    f"has not posted its KASAB stock yet. "
                    f"Please submit its linked Spindal "
                    f"Issue before issuing this Peti "
                    f"to Gilit."
                )

            # ------------------------------------------------
            # SOURCE-AWARE NEW PETI
            # ------------------------------------------------

            if peti_ledger.stock_source:

                row.stock_source = (
                    peti_ledger.stock_source
                )

                locations = (
                    get_stock_source_locations(
                        row.stock_source
                    )
                )

                positive_departments = [
                    location[
                        "department"
                    ]
                    for location
                    in locations
                    if flt(
                        location[
                            "available_weight"
                        ]
                    ) > 0.000001
                ]

                if not positive_departments:
                    frappe.throw(
                        f"KASAB source "
                        f"{row.stock_source} for Peti "
                        f"{row.spindal_peti_entry} "
                        f"has no remaining stock."
                    )

                # Partial Peti previously processed in Gilit:
                # source is already physically in Gilit.
                # Do NOT transfer it again.
                if (
                    self.to_department
                    in positive_departments
                ):
                    continue

                # Normal first-time Peti:
                # source should usually be in Spindal.
                if (
                    self.from_department
                    in positive_departments
                ):
                    source_department = (
                        self.from_department
                    )

                # Cross-department support:
                # if exact source exists in one other location,
                # transfer it from its actual location.
                elif (
                    len(
                        positive_departments
                    ) == 1
                ):
                    source_department = (
                        positive_departments[0]
                    )

                else:
                    frappe.throw(
                        f"KASAB source "
                        f"{row.stock_source} for Peti "
                        f"{row.spindal_peti_entry} "
                        f"exists in multiple departments: "
                        f"{', '.join(positive_departments)}. "
                        f"Cannot determine a unique physical "
                        f"source location."
                    )

                consume_selected_stock_source(
                    doc=self,

                    stock_source=
                        row.stock_source,

                    source_department=
                        source_department,

                    product=
                        kasab_product,

                    required_qty=
                        weight,

                    batch_no=
                        self.gilit_batch_no,

                    posting_date=
                        self.issue_date
                        or today(),

                    transaction_type=
                        "Stock Transfer Out",

                    remarks=(
                        "KASAB Peti transferred "
                        f"from {source_department} "
                        "to Gilit"
                    ),
                )

                add_source_linked_transfer_in(
                    doc=self,

                    stock_source=
                        row.stock_source,

                    department=
                        self.to_department,

                    product=
                        kasab_product,

                    qty=
                        weight,

                    batch_no=
                        self.gilit_batch_no,

                    posting_date=
                        self.issue_date
                        or today(),

                    remarks=(
                        "KASAB Peti source-linked "
                        "inward in Gilit"
                    ),
                )

                continue

            # ------------------------------------------------
            # HISTORICAL SOURCE-LESS PETI
            # ------------------------------------------------
            # Only Petis that ALREADY HAVE a legacy source-less
            # Production Output reach this block.
            # We deliberately do not invent an ISSRC for them.
            # ------------------------------------------------

            source_balance = (
                self.get_last_balance(
                    self.company,
                    self.from_department,
                    kasab_product,
                )
            )

            if (
                weight
                > flt(source_balance)
            ):
                frappe.throw(
                    f"Insufficient legacy KASAB "
                    f"stock in "
                    f"{self.from_department}. "
                    f"Available: "
                    f"{source_balance} KG, "
                    f"Required: {weight} KG"
                )

            frappe.get_doc({
                "doctype":
                    "Inventory Ledger",

                "company":
                    self.company,

                "department":
                    self.from_department,

                "product":
                    kasab_product,

                "batch_number":
                    self.gilit_batch_no,

                "in_weight":
                    0,

                "out_weight":
                    weight,

                "current_balance":
                    flt(
                        source_balance
                        - weight,
                        6,
                    ),

                "transaction_type":
                    "Stock Transfer Out",

                "reference_doctype":
                    self.doctype,

                "reference_name":
                    self.name,

                "date":
                    self.issue_date
                    or today(),

                "remarks":
                    (
                        "Historical source-less "
                        "KASAB Peti issued to Gilit"
                    ),
            }).insert(
                ignore_permissions=True
            )

            target_balance = (
                self.get_last_balance(
                    self.company,
                    self.to_department,
                    kasab_product,
                )
            )

            frappe.get_doc({
                "doctype":
                    "Inventory Ledger",

                "company":
                    self.company,

                "department":
                    self.to_department,

                "product":
                    kasab_product,

                "batch_number":
                    self.gilit_batch_no,

                "in_weight":
                    weight,

                "out_weight":
                    0,

                "current_balance":
                    flt(
                        target_balance
                        + weight,
                        6,
                    ),

                "transaction_type":
                    "Stock Transfer In",

                "reference_doctype":
                    self.doctype,

                "reference_name":
                    self.name,

                "date":
                    self.issue_date
                    or today(),

                "remarks":
                    (
                        "Historical source-less "
                        "KASAB Peti received in Gilit"
                    ),
            }).insert(
                ignore_permissions=True
            )

        # ====================================================
        # METAL WATER
        # ====================================================

        for row in (
            self.metal_water_inputs
            or []
        ):

            if (
                not row.product
                or not flt(
                    row.issued_aani
                )
            ):
                continue

            product = resolve_product(
                row.product
            )

            required_kg = (
                gilit_qty_to_kg(
                    row.issued_aani,
                    row.uom,
                )
            )

            consume_selected_stock_source(
                doc=self,

                stock_source=
                    row.stock_source,

                source_department=
                    row.source_department,

                product=
                    product,

                required_qty=
                    required_kg,

                batch_no=
                    self.gilit_batch_no,

                posting_date=
                    row.input_date
                    or self.issue_date
                    or today(),

                transaction_type=
                    "Production Input",

                remarks=(
                    "Gilit Metal Water exact "
                    "source consumption"
                ),
            )

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
            update_modified=False,
        )
