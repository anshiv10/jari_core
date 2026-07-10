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
