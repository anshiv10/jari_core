import frappe
from frappe.utils import flt


def execute(filters=None):

    # ── BUILD WHERE CLAUSE FROM FILTERS ──────────────────────
    conditions = "WHERE il2.current_balance > 0"
    filter_values = {}

    if filters:
        if filters.get("company"):
            conditions += " AND il2.company = %(company)s"
            filter_values["company"] = filters["company"]
        if filters.get("department"):
            conditions += " AND il2.department = %(department)s"
            filter_values["department"] = filters["department"]
        if filters.get("product"):
            conditions += " AND il2.product = %(product)s"
            filter_values["product"] = filters["product"]

    # ── COLUMNS ──────────────────────────────────────────────
    columns = [
        {
            "label": "Company",
            "fieldname": "company",
            "fieldtype": "Link",
            "options": "Company Master",
            "width": 160
        },
        {
            "label": "Department",
            "fieldname": "department",
            "fieldtype": "Link",
            "options": "Department Master",
            "width": 150
        },
        {
            "label": "Product",
            "fieldname": "product",
            "fieldtype": "Link",
            "options": "Product Master",
            "width": 150
        },
        {
            "label": "Total In (KG)",
            "fieldname": "total_in",
            "fieldtype": "Float",
            "width": 130
        },
        {
            "label": "Total Out (KG)",
            "fieldname": "total_out",
            "fieldtype": "Float",
            "width": 130
        },
        {
            "label": "Current Balance (KG)",
            "fieldname": "current_balance",
            "fieldtype": "Float",
            "width": 170
        },
        {
            "label": "Transactions",
            "fieldname": "txn_count",
            "fieldtype": "Int",
            "width": 120
        },
        {
            "label": "Last Updated",
            "fieldname": "last_updated",
            "fieldtype": "Date",
            "width": 130
        },
    ]

    # ── MAIN DATA QUERY ───────────────────────────────────────
    data = frappe.db.sql("""
        SELECT
            il2.company,
            il2.department,
            il2.product,
            agg.total_in,
            agg.total_out,
            agg.txn_count,
            il2.current_balance,
            il2.date AS last_updated
        FROM `tabInventory Ledger` il2
        INNER JOIN (
            SELECT
                company,
                department,
                product,
                SUM(in_weight)   AS total_in,
                SUM(out_weight)  AS total_out,
                COUNT(*)         AS txn_count,
                MAX(creation)    AS max_creation
            FROM `tabInventory Ledger`
            GROUP BY company, department, product
        ) agg
            ON  il2.company    = agg.company
            AND il2.department = agg.department
            AND il2.product    = agg.product
            AND il2.creation   = agg.max_creation
        {conditions}
        ORDER BY il2.company, il2.department, il2.product
    """.format(conditions=conditions), filter_values, as_dict=True)

    return columns, data