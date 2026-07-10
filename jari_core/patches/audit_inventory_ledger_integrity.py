import frappe


def execute():
    bad_rows = frappe.get_all(
        "Inventory Ledger",
        filters=[
            ["out_weight", "<", 0]
        ],
        fields=["name", "out_weight", "remarks"],
        limit_page_length=0
    )

    for row in bad_rows:
        remarks = row.remarks or ""
        if "Audit correction: negative out_weight converted to positive." not in remarks:
            remarks += "\nAudit correction: negative out_weight converted to positive."

        frappe.db.set_value(
            "Inventory Ledger",
            row.name,
            {
                "out_weight": abs(float(row.out_weight or 0)),
                "remarks": remarks
            },
            update_modified=False
        )

    negative_in_rows = frappe.get_all(
        "Inventory Ledger",
        filters=[
            ["in_weight", "<", 0]
        ],
        fields=["name", "in_weight", "remarks"],
        limit_page_length=0
    )

    for row in negative_in_rows:
        remarks = row.remarks or ""
        if "Audit correction: negative in_weight converted to positive." not in remarks:
            remarks += "\nAudit correction: negative in_weight converted to positive."

        frappe.db.set_value(
            "Inventory Ledger",
            row.name,
            {
                "in_weight": abs(float(row.in_weight or 0)),
                "remarks": remarks
            },
            update_modified=False
        )
