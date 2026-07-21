import frappe


def execute():
    child_doctypes = [
        "Pavtha Issue Item",
        "Pavtha Output Item",
        "Pavtha Waste Item",
    ]

    results = {}

    for child_doctype in child_doctypes:
        table = "tab" + child_doctype

        blank_count = frappe.db.sql(
            f"""
            SELECT COUNT(*)
            FROM `{table}`
            WHERE IFNULL(`issue_receive_type`, '') = ''
            """
        )[0][0]

        if blank_count:
            frappe.db.sql(
                f"""
                UPDATE `{table}`
                SET `issue_receive_type` = 'In-house'
                WHERE IFNULL(`issue_receive_type`, '') = ''
                """
            )

        results[child_doctype] = int(blank_count)

    frappe.db.commit()

    return results
