import frappe
from frappe.utils import flt


def execute(filters=None):
    filters = filters or {}

    conditions = ["latest.current_balance > 0"]
    values = {}

    if filters.get("company"):
        conditions.append("latest.company = %(company)s")
        values["company"] = filters.get("company")

    if filters.get("department"):
        conditions.append("latest.department = %(department)s")
        values["department"] = filters.get("department")

    if filters.get("product"):
        conditions.append("latest.product = %(product)s")
        values["product"] = filters.get("product")

    where_clause = " AND ".join(conditions)

    columns = [
        {"label": "Stock Summary", "fieldname": "stock_summary", "fieldtype": "Data", "width": 260},
        {"label": "Company", "fieldname": "company", "fieldtype": "Link", "options": "Company Master", "width": 160},
        {"label": "Department", "fieldname": "department", "fieldtype": "Link", "options": "Department Master", "width": 160},
        {"label": "Product", "fieldname": "product", "fieldtype": "Link", "options": "Product Master", "width": 160},
        {"label": "Current Balance (KG)", "fieldname": "current_balance", "fieldtype": "Float", "width": 170},
        {"label": "Total In (KG)", "fieldname": "total_in", "fieldtype": "Float", "width": 130},
        {"label": "Total Out (KG)", "fieldname": "total_out", "fieldtype": "Float", "width": 130},
        {"label": "Transactions", "fieldname": "txn_count", "fieldtype": "Int", "width": 110},
        {"label": "Last Updated", "fieldname": "last_updated", "fieldtype": "Date", "width": 130},
    ]

    data = frappe.db.sql("""
        SELECT
            CONCAT(latest.product, ' - ', ROUND(latest.current_balance, 3), ' KG - ', latest.department) AS stock_summary,
            latest.company,
            latest.department,
            latest.product,
            latest.current_balance,
            agg.total_in,
            agg.total_out,
            agg.txn_count,
            latest.date AS last_updated
        FROM `tabInventory Ledger` latest
        INNER JOIN (
            SELECT
                company,
                department,
                product,
                SUM(in_weight) AS total_in,
                SUM(out_weight) AS total_out,
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

    return columns, data
