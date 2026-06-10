import frappe
from frappe.utils import flt


def execute(filters=None):

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
            "width": 140
        },
        {
            "label": "Product",
            "fieldname": "product",
            "fieldtype": "Link",
            "options": "Product Master",
            "width": 140
        },
        {
            "label": "Total In (KG)",
            "fieldname": "total_in",
            "fieldtype": "Float",
            "width": 120
        },
        {
            "label": "Total Out (KG)",
            "fieldname": "total_out",
            "fieldtype": "Float",
            "width": 120
        },
        {
            "label": "Current Balance (KG)",
            "fieldname": "current_balance",
            "fieldtype": "Float",
            "width": 160
        },
        {
            "label": "Transactions",
            "fieldname": "txn_count",
            "fieldtype": "Int",
            "width": 110
        },
        {
            "label": "Last Updated",
            "fieldname": "last_updated",
            "fieldtype": "Date",
            "width": 120
        },
    ]

    # ── MAIN DATA QUERY ───────────────────────────────────────
    # For each company+department+product combination, get:
    # total in, total out, latest balance, txn count, last date
    data = frappe.db.sql("""
        SELECT
            agg.company,
            agg.department,
            agg.product,
            agg.total_in,
            agg.total_out,
            agg.txn_count,
            latest.current_balance,
            latest.date AS last_updated
        FROM (
            SELECT
                company,
                department,
                product,
                SUM(in_weight)  AS total_in,
                SUM(out_weight) AS total_out,
                COUNT(*)        AS txn_count
            FROM `tabInventory Ledger`
            GROUP BY company, department, product
        ) agg
        INNER JOIN `tabInventory Ledger` latest
            ON  latest.company    = agg.company
            AND latest.department = agg.department
            AND latest.product    = agg.product
            AND latest.creation   = (
                SELECT MAX(creation)
                FROM `tabInventory Ledger` sub
                WHERE sub.company    = agg.company
                  AND sub.department = agg.department
                  AND sub.product    = agg.product
            )
        WHERE latest.current_balance > 0
        ORDER BY agg.company, agg.department, agg.product
    """, as_dict=True)

    # ── SUMMARY CALCULATIONS ──────────────────────────────────
    total_balance   = sum(flt(r.current_balance) for r in data)
    total_in_all    = sum(flt(r.total_in)        for r in data)
    total_out_all   = sum(flt(r.total_out)       for r in data)
    total_txns      = sum(int(r.txn_count)       for r in data)
    unique_products = len(set(r.product          for r in data))
    unique_depts    = len(set(r.department       for r in data))

    # ── REPORT SUMMARY (number cards shown above the table) ──
    # These render as the built-in Frappe summary cards
    report_summary = [
        {
            "value": round(total_balance, 3),
            "label": "Total Stock (KG)",
            "datatype": "Float",
            "indicator": "Green"
        },
        {
            "value": round(total_in_all, 3),
            "label": "Total Inward (KG)",
            "datatype": "Float",
            "indicator": "Blue"
        },
        {
            "value": round(total_out_all, 3),
            "label": "Total Outward (KG)",
            "datatype": "Float",
            "indicator": "Orange"
        },
        {
            "value": total_txns,
            "label": "Total Transactions",
            "datatype": "Int",
            "indicator": "Purple"
        },
        {
            "value": unique_products,
            "label": "Active Products",
            "datatype": "Int",
            "indicator": "Cyan"
        },
        {
            "value": unique_depts,
            "label": "Active Departments",
            "datatype": "Int",
            "indicator": "Yellow"
        },
    ]

    # ── CHART DATA (bar chart rendered above the table) ──────
    # Group by department for the chart
    dept_balances = {}
    for row in data:
        dept = row.department or "Unknown"
        dept_balances[dept] = dept_balances.get(dept, 0) + flt(row.current_balance)

    chart = {
        "data": {
            "labels": list(dept_balances.keys()),
            "datasets": [
                {
                    "name": "Current Balance (KG)",
                    "values": [round(v, 3) for v in dept_balances.values()]
                }
            ]
        },
        "type": "bar",
        "colors": ["#5e64ff"],
        "barOptions": {
            "stacked": False,
            "spaceRatio": 0.3
        },
        "height": 280,
        "axisOptions": {
            "xAxisMode": "tick",
            "yAxisMode": "span",
            "xIsSeries": False
        },
        "tooltipOptions": {
            "formatTooltipY": "d => d + ' KG'"
        }
    }

    return columns, data, None, chart, report_summary