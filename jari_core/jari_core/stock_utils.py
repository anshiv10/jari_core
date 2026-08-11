import frappe
from frappe.utils import flt, today


def get_last_balance(company, department, product):
    return frappe.db.get_value(
        "Inventory Ledger",
        {"company": company, "department": department, "product": product},
        "current_balance",
        order_by="creation desc"
    ) or 0


def get_issueable_balance(company, department, product):
    return flt(get_last_balance(company, department, product))


def get_issueable_sources(company, product, preferred_department=None):
    departments = frappe.db.sql("""
        SELECT DISTINCT department
        FROM `tabInventory Ledger`
        WHERE company = %s
          AND product = %s
          AND IFNULL(department, '') != ''
    """, (company, product), as_dict=True)

    rows = []

    for d in departments:
        bal = get_issueable_balance(company, d.department, product)
        if bal > 0:
            rows.append({"department": d.department, "balance": bal})

    rows.sort(key=lambda x: (0 if x["department"] == preferred_department else 1, -x["balance"]))
    return rows


def consume_issueable_stock(doc, product, required_qty, batch_no, posting_date, preferred_department=None, remarks=None):
    required_qty = flt(required_qty)

    if not product or required_qty <= 0:
        return

    sources = get_issueable_sources(doc.company, product, preferred_department)
    total_available = sum(flt(x["balance"]) for x in sources)

    if required_qty > total_available:
        frappe.throw(
            f"Insufficient stock for {product}. Available: {total_available} KG, Requested: {required_qty} KG."
        )

    remaining = required_qty

    for src in sources:
        if remaining <= 0:
            break

        consume = min(remaining, flt(src["balance"]))
        last_balance = get_last_balance(doc.company, src["department"], product)

        frappe.get_doc({
            "doctype": "Inventory Ledger",
            "company": doc.company,
            "department": src["department"],
            "product": product,
            "batch_number": batch_no,
            "in_weight": 0,
            "out_weight": consume,
            "current_balance": flt(last_balance) - consume,
            "transaction_type": "Production Input",
            "reference_doctype": doc.doctype,
            "reference_name": doc.name,
            "date": posting_date or today(),
            "remarks": remarks or f"Issue consumed from {src['department']}"
        }).insert(ignore_permissions=True)

        remaining -= consume


def add_wip_transfer_in(doc, department, product, qty, batch_no, posting_date, remarks=None):
    qty = flt(qty)

    if not product or qty <= 0:
        return

    last_balance = get_last_balance(doc.company, department, product)

    frappe.get_doc({
        "doctype": "Inventory Ledger",
        "company": doc.company,
        "department": department,
        "product": product,
        "batch_number": batch_no,
        "in_weight": qty,
        "out_weight": 0,
        "current_balance": flt(last_balance) + qty,
        "transaction_type": "Stock Transfer In",
        "reference_doctype": doc.doctype,
        "reference_name": doc.name,
        "date": posting_date or today(),
        "remarks": remarks or f"WIP material inward in {department}"
    }).insert(ignore_permissions=True)


@frappe.whitelist()
def get_product_stock_summary(product, company=None):
    if not product:
        return ""

    conditions = ["product = %(product)s"]
    values = {"product": product}

    if company:
        conditions.append("company = %(company)s")
        values["company"] = company

    rows = frappe.db.sql("""
        SELECT company, department, current_balance
        FROM `tabInventory Ledger` latest
        INNER JOIN (
            SELECT company AS c, department AS d, product AS p, MAX(creation) AS max_creation
            FROM `tabInventory Ledger`
            WHERE {conditions}
            GROUP BY company, department, product
        ) x
        ON latest.company = x.c
        AND latest.department = x.d
        AND latest.product = x.p
        AND latest.creation = x.max_creation
        WHERE latest.current_balance > 0
        ORDER BY latest.company, latest.department
    """.format(conditions=" AND ".join(conditions)), values, as_dict=True)

    lines = []
    for r in rows:
        lines.append(r.company + " | " + r.department + " - " + str(flt(r.current_balance, 3)) + " KG")

    return "\n".join(lines) if lines else "No stock available"


@frappe.whitelist()
def product_query_by_department(doctype, txt, searchfield, start, page_len, filters):
    department = filters.get("department") if filters else None

    if not department:
        return []

    return frappe.db.sql("""
        SELECT DISTINCT pm.name, pm.product_name
        FROM `tabProduct Master` pm
        INNER JOIN `tabProduct Department Item` pdi
            ON pdi.parent = pm.name
        WHERE pdi.department = %(department)s
          AND (
              pm.name LIKE %(txt)s
              OR pm.product_name LIKE %(txt)s
              OR pm.product_code LIKE %(txt)s
              OR pm.product_tag LIKE %(txt)s
          )
        ORDER BY pm.product_name
        LIMIT %(start)s, %(page_len)s
    """, {
        "department": department,
        "txt": "%" + txt + "%",
        "start": start,
        "page_len": page_len
    })

# ============================================================
# SOURCE-WISE INVENTORY TRACKING
# ============================================================


def make_stock_source_key(
    source_doctype,
    source_name,
    source_row=None,
):
    return "|".join([
        source_doctype or "",
        source_name or "",
        source_row or "__PARENT__",
    ])


def get_or_create_stock_source(
    *,
    source_type,
    company,
    product,
    source_doctype,
    source_name,
    source_row=None,
    source_date=None,
    batch_number=None,
    remarks=None,
):
    """
    Register one immutable stock source.

    One Purchase/Receive child row = one Inventory Stock Source.
    """

    source_key = make_stock_source_key(
        source_doctype,
        source_name,
        source_row,
    )

    existing = frappe.db.get_value(
        "Inventory Stock Source",
        {
            "source_key": source_key,
        },
        "name",
    )

    if existing:
        source = frappe.get_doc(
            "Inventory Stock Source",
            existing,
        )

        if source.company != company:
            frappe.throw(
                f"Stock Source {existing} belongs to "
                f"Company {source.company}, not {company}."
            )

        if source.product != product:
            frappe.throw(
                f"Stock Source {existing} belongs to "
                f"Product {source.product}, not {product}."
            )

        return existing

    source = frappe.get_doc({
        "doctype": "Inventory Stock Source",
        "source_type": source_type,
        "company": company,
        "product": product,
        "source_doctype": source_doctype,
        "source_name": source_name,
        "source_row": source_row,
        "source_date": source_date,
        "batch_number": batch_number,
        "source_key": source_key,
        "remarks": remarks,
    })

    source.insert(
        ignore_permissions=True
    )

    return source.name


def get_stock_source_balance(
    stock_source,
    department,
):
    """
    Return available KG for one exact Source + Department.

    Normal sources:
        SUM(source-linked ledger IN - OUT)

    Legacy sources:
        Legacy opening balance
        + subsequent source-linked ledger IN - OUT
    """

    if not stock_source or not department:
        return 0

    source = frappe.get_cached_doc(
        "Inventory Stock Source",
        stock_source,
    )

    opening = 0

    if (
        source.is_legacy
        and source.opening_department == department
    ):
        opening = flt(
            source.opening_weight
        )

    ledger_net = frappe.db.sql(
        """
        SELECT
            COALESCE(
                SUM(in_weight),
                0
            )
            -
            COALESCE(
                SUM(out_weight),
                0
            )
        FROM `tabInventory Ledger`
        WHERE stock_source = %s
          AND company = %s
          AND department = %s
          AND product = %s
        """,
        (
            stock_source,
            source.company,
            department,
            source.product,
        ),
    )[0][0]

    return flt(
        opening + flt(ledger_net),
        6,
    )


@frappe.whitelist()
def get_stock_source_details(
    stock_source,
    department,
):
    if not stock_source:
        return {}

    source = frappe.get_doc(
        "Inventory Stock Source",
        stock_source,
    )

    return {
        "stock_source": source.name,
        "source_type": source.source_type,
        "source_doctype": source.source_doctype,
        "source_name": source.source_name,
        "source_row": source.source_row,
        "source_date": source.source_date,
        "batch_number": source.batch_number,
        "company": source.company,
        "product": source.product,
        "department": department,
        "available_weight": get_stock_source_balance(
            source.name,
            department,
        ),
    }


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def stock_source_query(
    doctype,
    txt,
    searchfield,
    start,
    page_len,
    filters,
):
    """
    Show stock sources available for one exact:

        Company
        Department
        Product

    Submitted Purchase/Receive sources and Legacy Opening
    sources are handled through the same query.
    """

    filters = filters or {}

    company = filters.get("company")
    department = filters.get("department")
    product = filters.get("product")

    if not company or not department or not product:
        return []

    return frappe.db.sql(
        """
        SELECT
            src.name,

            CONCAT(
                CASE
                    WHEN src.is_legacy = 1
                        THEN 'Legacy Opening'
                    ELSE COALESCE(
                        src.source_name,
                        src.name
                    )
                END,

                ' | ',

                src.source_type,

                ' | Date: ',

                COALESCE(
                    DATE_FORMAT(
                        src.source_date,
                        '%%d-%%m-%%Y'
                    ),
                    '-'
                ),

                ' | Available: ',

                FORMAT(
                    (
                        CASE
                            WHEN src.is_legacy = 1
                             AND src.opening_department = %(department)s
                            THEN src.opening_weight
                            ELSE 0
                        END
                        +
                        COALESCE(
                            ledger.net_qty,
                            0
                        )
                    ),
                    3
                ),

                ' KG'
            ) AS description

        FROM `tabInventory Stock Source` src

        LEFT JOIN (
            SELECT
                stock_source,
                SUM(in_weight - out_weight) AS net_qty
            FROM `tabInventory Ledger`
            WHERE company = %(company)s
              AND department = %(department)s
              AND product = %(product)s
              AND IFNULL(stock_source, '') != ''
            GROUP BY stock_source
        ) ledger
            ON ledger.stock_source = src.name

        WHERE src.company = %(company)s
          AND src.product = %(product)s

          AND (
                (
                    CASE
                        WHEN src.is_legacy = 1
                         AND src.opening_department = %(department)s
                        THEN src.opening_weight
                        ELSE 0
                    END
                    +
                    COALESCE(
                        ledger.net_qty,
                        0
                    )
                )
              ) > 0.000001

          AND (
                src.name LIKE %(txt)s
                OR COALESCE(
                    src.source_name,
                    ''
                ) LIKE %(txt)s
                OR COALESCE(
                    src.source_type,
                    ''
                ) LIKE %(txt)s
                OR COALESCE(
                    src.batch_number,
                    ''
                ) LIKE %(txt)s
              )

        ORDER BY
            src.source_date ASC,
            src.creation ASC

        LIMIT %(start)s, %(page_len)s
        """,
        {
            "company": company,
            "department": department,
            "product": product,
            "txt": f"%{txt}%",
            "start": start,
            "page_len": page_len,
        },
    )


def consume_selected_stock_source(
    *,
    doc,
    stock_source,
    source_department,
    product,
    required_qty,
    batch_no,
    posting_date,
    transaction_type="Production Input",
    remarks=None,
):
    """
    Consume only the exact stock source selected by the user.

    The source row is locked during submission so two users
    cannot successfully over-consume the same stock source.
    """

    required_qty = flt(
        required_qty,
        6,
    )

    if required_qty <= 0:
        return

    if not stock_source:
        frappe.throw(
            f"Stock Source is required for product {product}."
        )

    if not source_department:
        frappe.throw(
            f"Source Department is required for product {product}."
        )

    # Serialize consumption attempts for this source.
    locked = frappe.db.sql(
        """
        SELECT name
        FROM `tabInventory Stock Source`
        WHERE name = %s
        FOR UPDATE
        """,
        stock_source,
    )

    if not locked:
        frappe.throw(
            f"Stock Source {stock_source} does not exist."
        )

    source = frappe.get_doc(
        "Inventory Stock Source",
        stock_source,
    )

    if source.company != doc.company:
        frappe.throw(
            f"Stock Source {stock_source} belongs to "
            f"{source.company}, not {doc.company}."
        )

    if source.product != product:
        frappe.throw(
            f"Stock Source {stock_source} belongs to "
            f"Product {source.product}, not {product}."
        )

    source_available = get_stock_source_balance(
        stock_source,
        source_department,
    )

    if required_qty > source_available + 0.000001:
        frappe.throw(
            f"Insufficient balance in selected Stock Source "
            f"{stock_source} for {product}. "
            f"Available: {source_available:.3f} KG, "
            f"Requested: {required_qty:.3f} KG."
        )

    physical_balance = flt(
        get_last_balance(
            doc.company,
            source_department,
            product,
        )
    )

    if required_qty > physical_balance + 0.000001:
        frappe.throw(
            f"Insufficient physical stock for {product} in "
            f"{source_department}. "
            f"Available: {physical_balance:.3f} KG, "
            f"Requested: {required_qty:.3f} KG."
        )

    frappe.get_doc({
        "doctype": "Inventory Ledger",
        "company": doc.company,
        "department": source_department,
        "product": product,
        "batch_number": batch_no,
        "stock_source": stock_source,
        "in_weight": 0,
        "out_weight": required_qty,
        "current_balance": (
            physical_balance
            - required_qty
        ),
        "transaction_type": transaction_type,
        "reference_doctype": doc.doctype,
        "reference_name": doc.name,
        "date": posting_date or today(),
        "remarks": (
            remarks
            or f"Issue consumed from Stock Source {stock_source}"
        ),
    }).insert(
        ignore_permissions=True
    )


def add_source_linked_transfer_in(
    *,
    doc,
    stock_source,
    department,
    product,
    qty,
    batch_no,
    posting_date,
    remarks=None,
):
    """
    Move selected-source lineage into the destination
    department without creating a new inventory source.
    """

    qty = flt(
        qty,
        6,
    )

    if qty <= 0:
        return

    balance = flt(
        get_last_balance(
            doc.company,
            department,
            product,
        )
    )

    frappe.get_doc({
        "doctype": "Inventory Ledger",
        "company": doc.company,
        "department": department,
        "product": product,
        "batch_number": batch_no,
        "stock_source": stock_source,
        "in_weight": qty,
        "out_weight": 0,
        "current_balance": balance + qty,
        "transaction_type": "Stock Transfer In",
        "reference_doctype": doc.doctype,
        "reference_name": doc.name,
        "date": posting_date or today(),
        "remarks": (
            remarks
            or f"Source-linked WIP material inward in {department}"
        ),
    }).insert(
        ignore_permissions=True
    )


def reverse_reference_inventory_ledger(doc):
    """
    Append exact reversals for Inventory Ledger movements created
    by one submitted source document.

    Source lineage is preserved through stock_source.
    """

    reversal_exists = frappe.db.exists(
        "Inventory Ledger",
        {
            "reference_doctype": doc.doctype,
            "reference_name": doc.name,
            "transaction_type": "Cancellation Reversal",
        },
    )

    if reversal_exists:
        return

    original_rows = frappe.get_all(
        "Inventory Ledger",
        filters={
            "reference_doctype": doc.doctype,
            "reference_name": doc.name,
            "transaction_type": ["!=", "Cancellation Reversal"],
        },
        fields=[
            "name",
            "company",
            "department",
            "product",
            "batch_number",
            "stock_source",
            "in_weight",
            "out_weight",
        ],
        order_by="creation asc",
    )

    for row in original_rows:

        current = flt(
            get_last_balance(
                row.company,
                row.department,
                row.product,
            ),
            6,
        )

        reverse_in = flt(
            row.out_weight,
            6,
        )

        reverse_out = flt(
            row.in_weight,
            6,
        )

        # If cancellation would remove stock from a department,
        # verify that the exact source being reversed still has
        # enough quantity there. This prevents source-wise stock
        # from becoming negative when downstream transactions have
        # already consumed that particular source.
        if row.stock_source and reverse_out > 0:
            source_available = get_stock_source_balance(
                row.stock_source,
                row.department,
            )

            if reverse_out > source_available + 0.000001:
                frappe.throw(
                    f"Cannot cancel {doc.doctype} {doc.name}. "
                    f"Stock Source {row.stock_source} has already been "
                    f"consumed downstream in {row.department}. "
                    f"Source Available: {source_available:.3f} KG, "
                    f"Required for reversal: {reverse_out:.3f} KG."
                )

        new_balance = (
            current
            + reverse_in
            - reverse_out
        )

        if new_balance < -0.000001:
            frappe.throw(
                f"Cannot cancel {doc.doctype} {doc.name}. "
                f"Reversing {row.product} in {row.department} "
                f"would make stock negative."
            )

        frappe.get_doc({
            "doctype": "Inventory Ledger",
            "company": row.company,
            "department": row.department,
            "product": row.product,
            "batch_number": row.batch_number,
            "stock_source": row.stock_source,
            "in_weight": reverse_in,
            "out_weight": reverse_out,
            "current_balance": new_balance,
            "transaction_type": "Cancellation Reversal",
            "reference_doctype": doc.doctype,
            "reference_name": doc.name,
            "date": today(),
            "remarks": (
                f"Cancellation reversal of ledger {row.name}"
            ),
        }).insert(
            ignore_permissions=True
        )

