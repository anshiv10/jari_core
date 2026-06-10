import frappe

def execute(filters=None):
    columns = [
        {"label": "Company", "fieldname": "company", "fieldtype": "Link",
         "options": "Company Master", "width": 150},
        {"label": "Department", "fieldname": "department", "fieldtype": "Link",
         "options": "Department Master", "width": 130},
        {"label": "Product", "fieldname": "product", "fieldtype": "Link",
         "options": "Product Master", "width": 130},
        {"label": "Current Balance (KG)", "fieldname": "current_balance",
         "fieldtype": "Float", "width": 140},
        {"label": "Last Updated", "fieldname": "last_updated",
         "fieldtype": "Date", "width": 110},
    ]

    data = frappe.db.sql("""
        SELECT
            il.company,
            il.department,
            il.product,
            il.current_balance,
            il.date as last_updated
        FROM `tabInventory Ledger` il
        INNER JOIN (
            SELECT company, department, product, MAX(creation) as max_creation
            FROM `tabInventory Ledger`
            GROUP BY company, department, product
        ) latest
        ON il.company = latest.company
        AND il.department = latest.department
        AND il.product = latest.product
        AND il.creation = latest.max_creation
        WHERE il.current_balance > 0
        ORDER BY il.company, il.department, il.product
    """, as_dict=True)

    return columns, data