import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, today


SALE_TYPES = (
    "Weight",
    "Marks",
    "Firki",
)


def get_pack_reserved_firki(
    stock_source,
    exclude_sale=None,
):
    """
    Commercial reservation for one exact Gilit saleable source.

    Draft and Submitted Jari Sales both reserve packing quantity.
    Cancelled sales do not.
    """
    if not stock_source:
        return 0

    conditions = [
        "parent.docstatus < 2",
        "item.stock_source = %(stock_source)s",
        "item.sale_type IN ('Marks', 'Firki')",
    ]

    values = {
        "stock_source":
            stock_source,
    }

    if exclude_sale:
        conditions.append(
            "parent.name != %(exclude_sale)s"
        )
        values["exclude_sale"] = (
            exclude_sale
        )

    reserved = frappe.db.sql(
        f"""
        SELECT
            COALESCE(
                SUM(
                    CASE
                        WHEN item.sale_type = 'Marks'
                            THEN COALESCE(
                                item.marks_quantity,
                                0
                            ) * 4
                        WHEN item.sale_type = 'Firki'
                            THEN COALESCE(
                                item.firki_quantity,
                                0
                            )
                        ELSE 0
                    END
                ),
                0
            )
        FROM `tabJari Sale Item` item
        INNER JOIN `tabJari Sale` parent
            ON parent.name = item.parent
        WHERE {' AND '.join(conditions)}
        """,
        values,
    )[0][0]

    return cint(
        reserved
    )


def get_saleable_pack_row(
    *,
    gilit_receive=None,
    stock_source=None,
    product=None,
):
    filters = {}

    if gilit_receive:
        filters["parent"] = (
            gilit_receive
        )

    if stock_source:
        filters["stock_source"] = (
            stock_source
        )

    if product:
        filters["product"] = (
            product
        )

    rows = frappe.get_all(
        "Gilit Saleable Product Item",
        filters=filters,
        fields=[
            "name",
            "parent",
            "product",
            "uom",
            "stock_label",
            "filled_firki",
            "weight_of_one_firki",
            "marks",
            "vadharo_firki",
            "total_weight",
            "stock_source",
        ],
        order_by="idx asc",
        limit=2,
    )

    if not rows:
        return None

    if len(rows) > 1:
        frappe.throw(
            _(
                "More than one matching Gilit "
                "Saleable Product row was found. "
                "Please correct the Gilit Receive."
            )
        )

    return frappe._dict(
        rows[0]
    )


def get_pack_availability(
    *,
    stock_source,
    exclude_sale=None,
):
    pack = get_saleable_pack_row(
        stock_source=stock_source,
    )

    if not pack:
        return {
            "original_firki": 0,
            "reserved_firki": 0,
            "available_firki": 0,
            "available_marks": 0,
        }

    original = cint(
        pack.filled_firki
    )
    reserved = (
        get_pack_reserved_firki(
            stock_source,
            exclude_sale=
                exclude_sale,
        )
    )
    available = max(
        0,
        original - reserved,
    )

    return {
        "original_firki":
            original,
        "reserved_firki":
            reserved,
        "available_firki":
            available,
        "available_marks":
            cint(
                available // 4
            ),
    }


class JariSale(Document):

    def validate(self):
        self.set_defaults()
        self.validate_customer()
        self.validate_items()
        self.calculate_totals()

    def before_submit(self):
        self.validate_items()
        self.calculate_totals()

    def set_defaults(self):
        if not self.sale_date:
            self.sale_date = today()

    def validate_customer(self):
        if not self.customer:
            frappe.throw(
                _("Customer is required.")
            )

        customer_name = (
            frappe.db.get_value(
                "Customer",
                self.customer,
                "customer_name",
            )
        )

        if not customer_name:
            frappe.throw(
                _(
                    "Customer {0} does not exist."
                ).format(
                    frappe.bold(
                        self.customer
                    )
                )
            )

        self.customer_name = (
            customer_name
        )

    def validate_items(self):
        from jari_core.jari_core.stock_utils import (
            prepare_selected_stock_source,
        )

        if not self.items:
            frappe.throw(
                _(
                    "At least one Product row "
                    "is required."
                )
            )

        if flt(
            self.tax_amount
        ) < 0:
            frappe.throw(
                _(
                    "Tax Amount cannot be negative."
                )
            )

        # External availability excludes this saved Draft.
        # These dictionaries additionally protect against multiple
        # rows in the same Jari Sale using one source.
        physical_used = {}
        pack_used = {}

        for row in self.items:
            self.validate_and_calculate_row(
                row
            )

            prepare_selected_stock_source(
                doc=self,
                row=row,
                required_qty=
                    row.stock_weight,
            )

            source_key = (
                row.stock_source,
                row.source_department,
            )

            cumulative_physical = flt(
                physical_used.get(
                    source_key,
                    0,
                )
                + flt(
                    row.stock_weight
                ),
                6,
            )

            available_physical = flt(
                row.source_available_weight,
                6,
            )

            if (
                cumulative_physical
                > available_physical
                + 0.000001
            ):
                frappe.throw(
                    _(
                        "Rows using Stock Source {0} "
                        "request {1} KG in this Jari Sale, "
                        "but only {2} KG is available "
                        "after other Draft reservations."
                    ).format(
                        frappe.bold(
                            row.stock_source
                        ),
                        cumulative_physical,
                        available_physical,
                    )
                )

            physical_used[
                source_key
            ] = cumulative_physical

            row.source_remaining_weight = (
                flt(
                    available_physical
                    - cumulative_physical,
                    6,
                )
            )

            if (
                row.sale_type
                in (
                    "Marks",
                    "Firki",
                )
            ):
                pack = (
                    get_pack_availability(
                        stock_source=
                            row.stock_source,
                        exclude_sale=
                            self.name,
                    )
                )

                row.available_firki = (
                    cint(
                        pack[
                            "available_firki"
                        ]
                    )
                )
                row.available_marks = (
                    cint(
                        pack[
                            "available_marks"
                        ]
                    )
                )

                required_firki = (
                    cint(
                        row.marks_quantity
                    )
                    * 4
                    if row.sale_type
                    == "Marks"
                    else cint(
                        row.firki_quantity
                    )
                )

                cumulative_pack = (
                    cint(
                        pack_used.get(
                            row.stock_source,
                            0,
                        )
                    )
                    + required_firki
                )

                if (
                    cumulative_pack
                    > cint(
                        pack[
                            "available_firki"
                        ]
                    )
                ):
                    frappe.throw(
                        _(
                            "Rows using Stock Source {0} "
                            "request {1} Firki-equivalent "
                            "in this Jari Sale, but only "
                            "{2} Firki are available."
                        ).format(
                            frappe.bold(
                                row.stock_source
                            ),
                            cumulative_pack,
                            pack[
                                "available_firki"
                            ],
                        )
                    )

                pack_used[
                    row.stock_source
                ] = cumulative_pack

                remaining_firki = max(
                    0,
                    cint(
                        pack[
                            "available_firki"
                        ]
                    )
                    - cumulative_pack,
                )

                row.remaining_firki = (
                    remaining_firki
                )
                row.remaining_marks = (
                    cint(
                        remaining_firki
                        // 4
                    )
                )
            else:
                row.available_firki = 0
                row.available_marks = 0
                row.remaining_firki = 0
                row.remaining_marks = 0

    def validate_and_calculate_row(
        self,
        row,
    ):
        if not row.product:
            frappe.throw(
                _(
                    "Product is required in "
                    "row #{0}."
                ).format(
                    row.idx
                )
            )

        if (
            row.sale_type
            not in SALE_TYPES
        ):
            frappe.throw(
                _(
                    "Valid Sale Type is required "
                    "in row #{0}."
                ).format(
                    row.idx
                )
            )

        product = frappe.db.get_value(
            "Product Master",
            row.product,
            [
                "unit",
                "product_tag",
                "allow_weight_sale",
                "allow_marks_sale",
                "allow_firki_sale",
            ],
            as_dict=True,
        )

        if not product:
            frappe.throw(
                _(
                    "Product {0} does not exist."
                ).format(
                    frappe.bold(
                        row.product
                    )
                )
            )

        row.uom = (
            product.unit
            or ""
        )

        allowed = {
            "Weight":
                cint(
                    product.allow_weight_sale
                ),
            "Marks":
                cint(
                    product.allow_marks_sale
                ),
            "Firki":
                cint(
                    product.allow_firki_sale
                ),
        }

        if not allowed[
            row.sale_type
        ]:
            frappe.throw(
                _(
                    "Sale Type {0} is not enabled "
                    "for Product {1}."
                ).format(
                    frappe.bold(
                        row.sale_type
                    ),
                    frappe.bold(
                        row.product
                    ),
                )
            )

        if (
            product.product_tag == "JARI"
            and row.sale_type == "Weight"
        ):
            frappe.throw(
                _(
                    "Product {0} is tagged JARI and "
                    "must be sold by Marks or Firki."
                ).format(
                    frappe.bold(
                        row.product
                    )
                )
            )

        if (
            row.sale_type
            in (
                "Marks",
                "Firki",
            )
            and product.product_tag
            != "JARI"
        ):
            frappe.throw(
                _(
                    "Marks/Firki sale requires a "
                    "Product tagged JARI."
                )
            )

        if flt(
            row.sale_price
        ) < 0:
            frappe.throw(
                _(
                    "Sale Price cannot be negative "
                    "in row #{0}."
                ).format(
                    row.idx
                )
            )

        if row.sale_type == "Weight":
            self.calculate_weight_sale_row(
                row
            )
            return

        self.calculate_packed_sale_row(
            row
        )

    def calculate_weight_sale_row(
        self,
        row,
    ):
        quantity = flt(
            row.weight_quantity,
            6,
        )

        if quantity <= 0:
            frappe.throw(
                _(
                    "Weight Quantity must be "
                    "greater than zero in row #{0}."
                ).format(
                    row.idx
                )
            )

        uom = (
            row.uom
            or ""
        ).strip().upper()

        if uom == "KG":
            stock_weight = quantity
        elif uom == "GM":
            stock_weight = (
                quantity
                / 1000
            )
        else:
            frappe.throw(
                _(
                    "Weight sale supports only "
                    "KG or GM Product UOM. "
                    "Product {0} uses {1}."
                ).format(
                    frappe.bold(
                        row.product
                    ),
                    frappe.bold(
                        row.uom
                        or "(blank)"
                    ),
                )
            )

        row.gilit_receive = None
        row.stock_label = None
        row.filled_firki = 0
        row.weight_of_one_firki = 0
        row.marks_quantity = 0
        row.firki_quantity = 0
        row.stock_weight = flt(
            stock_weight,
            6,
        )

        # Client requirement:
        # weight sale amount = entered weight quantity × rate.
        # For GM products the entered rate is therefore per gram.
        row.untaxed_amount = flt(
            quantity
            * flt(
                row.sale_price
            ),
            2,
        )

    def calculate_packed_sale_row(
        self,
        row,
    ):
        if not row.gilit_receive:
            frappe.throw(
                _(
                    "Gilit Receive Reference is "
                    "required in row #{0} for "
                    "{1} sale."
                ).format(
                    row.idx,
                    row.sale_type,
                )
            )

        receive = frappe.db.get_value(
            "Gilit Receive",
            row.gilit_receive,
            [
                "docstatus",
                "company",
            ],
            as_dict=True,
        )

        if not receive:
            frappe.throw(
                _(
                    "Gilit Receive {0} does "
                    "not exist."
                ).format(
                    frappe.bold(
                        row.gilit_receive
                    )
                )
            )

        if receive.docstatus != 1:
            frappe.throw(
                _(
                    "Gilit Receive {0} must be "
                    "submitted before sale."
                ).format(
                    frappe.bold(
                        row.gilit_receive
                    )
                )
            )

        if receive.company != self.company:
            frappe.throw(
                _(
                    "Gilit Receive {0} belongs to "
                    "Company {1}, not {2}."
                ).format(
                    frappe.bold(
                        row.gilit_receive
                    ),
                    frappe.bold(
                        receive.company
                    ),
                    frappe.bold(
                        self.company
                    ),
                )
            )

        pack = get_saleable_pack_row(
            gilit_receive=
                row.gilit_receive,
            product=
                row.product,
        )

        if not pack:
            frappe.throw(
                _(
                    "Gilit Receive {0} does not "
                    "contain a submitted saleable "
                    "JARI output for Product {1}."
                ).format(
                    frappe.bold(
                        row.gilit_receive
                    ),
                    frappe.bold(
                        row.product
                    ),
                )
            )

        if not pack.stock_source:
            frappe.throw(
                _(
                    "Gilit Receive {0} saleable "
                    "output has no Stock Source."
                ).format(
                    frappe.bold(
                        row.gilit_receive
                    )
                )
            )

        source = frappe.get_doc(
            "Inventory Stock Source",
            pack.stock_source,
        )

        if (
            source.source_doctype
            != "Gilit Receive"
            or source.source_name
            != row.gilit_receive
            or source.source_row
            != pack.name
        ):
            frappe.throw(
                _(
                    "Stock Source lineage does not "
                    "match Gilit Receive {0}."
                ).format(
                    frappe.bold(
                        row.gilit_receive
                    )
                )
            )

        row.stock_source = (
            pack.stock_source
        )
        row.stock_label = (
            pack.stock_label
        )
        row.filled_firki = (
            cint(
                pack.filled_firki
            )
        )
        row.weight_of_one_firki = (
            flt(
                pack.weight_of_one_firki,
                6,
            )
        )
        row.weight_quantity = 0

        if (
            row.weight_of_one_firki
            <= 0
        ):
            frappe.throw(
                _(
                    "Weight of One Firki is not "
                    "available for Gilit Receive {0}."
                ).format(
                    frappe.bold(
                        row.gilit_receive
                    )
                )
            )

        if row.sale_type == "Marks":
            marks = cint(
                row.marks_quantity
            )

            if marks <= 0:
                frappe.throw(
                    _(
                        "Marks must be greater "
                        "than zero in row #{0}."
                    ).format(
                        row.idx
                    )
                )

            row.firki_quantity = 0
            row.stock_weight = flt(
                marks
                * 4
                * row.weight_of_one_firki,
                6,
            )
            row.untaxed_amount = flt(
                marks
                * flt(
                    row.sale_price
                ),
                2,
            )
            return

        firki = cint(
            row.firki_quantity
        )

        if firki <= 0:
            frappe.throw(
                _(
                    "Firki Count must be greater "
                    "than zero in row #{0}."
                ).format(
                    row.idx
                )
            )

        row.marks_quantity = 0
        row.stock_weight = flt(
            firki
            * row.weight_of_one_firki,
            6,
        )

        # Client requirement explicitly states:
        # Firki-wise amount = physical weight × sale price.
        row.untaxed_amount = flt(
            row.stock_weight
            * flt(
                row.sale_price
            ),
            2,
        )

    def calculate_totals(self):
        self.untaxed_total = flt(
            sum(
                flt(
                    row.untaxed_amount
                )
                for row in (
                    self.items
                    or []
                )
            ),
            2,
        )

        self.subtotal = flt(
            self.untaxed_total
            + flt(
                self.tax_amount
            ),
            2,
        )

    def ledger_exists(self):
        return bool(
            frappe.db.exists(
                "Inventory Ledger",
                {
                    "reference_doctype":
                        self.doctype,
                    "reference_name":
                        self.name,
                },
            )
        )

    def on_submit(self):
        from jari_core.jari_core.stock_utils import (
            consume_selected_stock_source,
        )

        if self.ledger_exists():
            return

        for row in (
            self.items
            or []
        ):
            qty = flt(
                row.stock_weight,
                6,
            )

            if qty <= 0:
                continue

            consume_selected_stock_source(
                doc=self,
                stock_source=
                    row.stock_source,
                source_department=
                    row.source_department,
                product=
                    row.product,
                required_qty=
                    qty,
                batch_no=
                    (
                        frappe.db.get_value(
                            "Inventory Stock Source",
                            row.stock_source,
                            "batch_number",
                        )
                        or ""
                    ),
                posting_date=
                    self.sale_date,
                transaction_type=
                    "Sale Outward",
                remarks=(
                    "Jari Sale to "
                    f"{self.customer}"
                ),
            )

    def on_cancel(self):
        from jari_core.jari_core.stock_utils import (
            reverse_reference_inventory_ledger,
        )

        reverse_reference_inventory_ledger(
            self
        )


@frappe.whitelist()
def get_product_sale_setup(
    product,
):
    if not product:
        return {}

    values = frappe.db.get_value(
        "Product Master",
        product,
        [
            "unit",
            "product_tag",
            "allow_weight_sale",
            "allow_marks_sale",
            "allow_firki_sale",
        ],
        as_dict=True,
    )

    return values or {}


@frappe.whitelist()
def get_gilit_receive_sale_details(
    receive_name,
    product=None,
    current_sale=None,
):
    if not receive_name:
        return {}

    receive = frappe.db.get_value(
        "Gilit Receive",
        receive_name,
        [
            "docstatus",
            "company",
            "receive_date",
            "active_batch_no",
        ],
        as_dict=True,
    )

    if not receive:
        frappe.throw(
            _(
                "Gilit Receive {0} does "
                "not exist."
            ).format(
                frappe.bold(
                    receive_name
                )
            )
        )

    if receive.docstatus != 1:
        frappe.throw(
            _(
                "Gilit Receive {0} must "
                "be submitted."
            ).format(
                frappe.bold(
                    receive_name
                )
            )
        )

    pack = get_saleable_pack_row(
        gilit_receive=
            receive_name,
        product=
            product or None,
    )

    if not pack:
        frappe.throw(
            _(
                "No matching saleable JARI "
                "output exists in Gilit Receive {0}."
            ).format(
                frappe.bold(
                    receive_name
                )
            )
        )

    if not pack.stock_source:
        frappe.throw(
            _(
                "Saleable JARI output in "
                "Gilit Receive {0} has no "
                "Stock Source."
            ).format(
                frappe.bold(
                    receive_name
                )
            )
        )

    from jari_core.jari_core.stock_utils import (
        get_stock_source_details,
    )

    source_details = (
        get_stock_source_details(
            pack.stock_source,
            current_doctype=
                "Jari Sale",
            current_name=
                current_sale or None,
        )
    )

    commercial = (
        get_pack_availability(
            stock_source=
                pack.stock_source,
            exclude_sale=
                current_sale or None,
        )
    )

    return {
        "company":
            receive.company,
        "gilit_receive":
            receive_name,
        "receive_date":
            receive.receive_date,
        "batch_number":
            receive.active_batch_no,
        "product":
            pack.product,
        "uom":
            pack.uom,
        "stock_label":
            pack.stock_label,
        "filled_firki":
            cint(
                pack.filled_firki
            ),
        "weight_of_one_firki":
            flt(
                pack.weight_of_one_firki,
                6,
            ),
        "marks":
            cint(
                pack.marks
            ),
        "vadharo_firki":
            cint(
                pack.vadharo_firki
            ),
        "total_weight":
            flt(
                pack.total_weight,
                6,
            ),
        "stock_source":
            pack.stock_source,
        "locations":
            source_details.get(
                "locations"
            )
            or [],
        "available_weight":
            flt(
                source_details.get(
                    "total_available_weight"
                ),
                6,
            ),
        "available_firki":
            commercial[
                "available_firki"
            ],
        "available_marks":
            commercial[
                "available_marks"
            ],
    }


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def gilit_receive_sale_query(
    doctype,
    txt,
    searchfield,
    start,
    page_len,
    filters,
):
    filters = frappe._dict(
        filters or {}
    )

    company = (
        filters.get("company")
        or ""
    )
    product = (
        filters.get("product")
        or ""
    )

    conditions = [
        "receive.docstatus = 1",
        "item.stock_source IS NOT NULL",
        "item.stock_source != ''",
    ]

    values = {
        "txt":
            f"%{txt}%",
        "start":
            start,
        "page_len":
            page_len,
    }

    if company:
        conditions.append(
            "receive.company = %(company)s"
        )
        values["company"] = company

    if product:
        conditions.append(
            "item.product = %(product)s"
        )
        values["product"] = product

    return frappe.db.sql(
        f"""
        SELECT
            receive.name,
            CONCAT(
                'Product: ',
                item.product,
                ' | Label: ',
                COALESCE(
                    item.stock_label,
                    ''
                ),
                ' | Firki: ',
                item.filled_firki,
                ' | Marks: ',
                item.marks,
                ' | Weight: ',
                FORMAT(
                    item.total_weight,
                    3
                ),
                ' KG'
            ) AS description
        FROM `tabGilit Receive` receive
        INNER JOIN `tabGilit Saleable Product Item` item
            ON item.parent = receive.name
        WHERE {' AND '.join(conditions)}
          AND (
              receive.name LIKE %(txt)s
              OR item.product LIKE %(txt)s
              OR COALESCE(
                  item.stock_label,
                  ''
              ) LIKE %(txt)s
          )
          AND EXISTS (
              SELECT 1
              FROM `tabInventory Ledger` ledger
              WHERE ledger.stock_source =
                    item.stock_source
              GROUP BY ledger.stock_source
              HAVING
                  SUM(
                      ledger.in_weight
                      - ledger.out_weight
                  ) > 0.000001
          )
        ORDER BY receive.creation DESC
        LIMIT %(start)s, %(page_len)s
        """,
        values,
    )
