import frappe


def execute():
    rows = frappe.get_all(
        "Inventory Ledger",
        filters=[["out_weight", "<", 0]],
        fields=["name", "out_weight", "remarks"],
        limit_page_length=0
    )

    for row in rows:
        remarks = row.remarks or ""
        if "Corrected negative out_weight to positive value." not in remarks:
            remarks += "\nCorrected negative out_weight to positive value."

        frappe.db.set_value(
            "Inventory Ledger",
            row.name,
            {
                "out_weight": abs(float(row.out_weight or 0)),
                "remarks": remarks
            },
            update_modified=False
        )
