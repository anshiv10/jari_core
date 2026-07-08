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
    result = frappe.db.sql("""
        SELECT
            SUM(
                CASE
                    WHEN transaction_type != 'Stock Transfer In'
                    THEN IFNULL(in_weight, 0)
                    ELSE 0
                END
            ) - SUM(IFNULL(out_weight, 0)) AS balance
        FROM `tabInventory Ledger`
        WHERE company = %s
          AND department = %s
          AND product = %s
    """, (company, department, product), as_dict=True)

    return flt(result[0].balance if result and result[0].balance is not None else 0)


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
            rows.append({
                "department": d.department,
                "balance": bal
            })

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
            f"Insufficient issueable stock for {product}. "
            f"Available across all departments: {total_available} KG, Requested: {required_qty} KG. "
            f"WIP / Stock Transfer In stock is not allowed for re-issue."
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
        bal = get_issueable_balance(company, d.department, product) if company else 0
        if flt(bal) > 0:
            lines.append(f"{d.department} - {bal} KG")

    return "\n".join(lines) if lines else "No issueable stock available"
