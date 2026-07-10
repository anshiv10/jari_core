import frappe
from frappe.utils import flt


def execute(filters=None):
    filters = filters or {}

    conditions = ["latest.current_balance > 0"]
    values = {}

    if filters.get("company"):
        conditions.append("latest.company = %(company)s")
        values["company"] = filters["company"]

    if filters.get("department"):
        conditions.append("latest.department = %(department)s")
        values["department"] = filters["department"]

    if filters.get("product"):
        conditions.append("latest.product = %(product)s")
        values["product"] = filters["product"]

    where_clause = " AND ".join(conditions)

    columns = [
        {"label": "Stock Summary", "fieldname": "stock_summary", "fieldtype": "Data", "width": 300},
        {"label": "Company", "fieldname": "company", "fieldtype": "Link", "options": "Company Master", "width": 160},
        {"label": "Department", "fieldname": "department", "fieldtype": "Link", "options": "Department Master", "width": 160},
        {"label": "Product", "fieldname": "product", "fieldtype": "Link", "options": "Product Master", "width": 160},
        {"label": "Current Balance (KG)", "fieldname": "current_balance", "fieldtype": "Float", "width": 170},
        {"label": "Total In (KG)", "fieldname": "total_in", "fieldtype": "Float", "width": 130},
        {"label": "Consumed / Used (KG)", "fieldname": "total_out", "fieldtype": "Float", "width": 160},
        {"label": "Transactions", "fieldname": "txn_count", "fieldtype": "Int", "width": 110},
        {"label": "Last Updated", "fieldname": "last_updated", "fieldtype": "Date", "width": 130}
    ]

    data = frappe.db.sql("""
        SELECT
            latest.company,
            latest.department,
            latest.product,
            latest.current_balance,
            agg.total_in,
            CASE
                WHEN agg.total_in >= latest.current_balance
                THEN agg.total_in - latest.current_balance
                ELSE 0
            END AS total_out,
            agg.txn_count,
            latest.date AS last_updated
        FROM `tabInventory Ledger` latest
        INNER JOIN (
            SELECT
                company,
                department,
                product,
                SUM(CASE WHEN in_weight > 0 THEN in_weight ELSE 0 END) AS total_in,
                COUNT(*) AS txn_count,
                MAX(creation) AS max_creation
            FROM `tabInventory Ledger`
            GROUP BY company, department, product
        ) agg
            ON latest.company = agg.company
            AND latest.department = agg.department
            AND latest.product = agg.product
            AND latest.creation = agg.max_creation
        WHERE {where_clause}
        ORDER BY latest.product, latest.department
    """.format(where_clause=where_clause), values, as_dict=True)

    for row in data:
        row.current_balance = flt(row.current_balance, 3)
        row.total_in = flt(row.total_in, 3)
        row.total_out = flt(row.total_out, 3)
        row.stock_summary = (
            row.product + " - " +
            str(row.current_balance) + " KG - " +
            row.department
        )

    return columns, data
