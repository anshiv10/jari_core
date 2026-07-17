import frappe


PRODUCT_TAGS = {
    "PASA": "PASA",
    "GULLA": "GULLA",
}


def execute():
    """
    Ensure products used by the Pavtha reconciliation engine have stable,
    controlled Product Master tags.

    The patch is idempotent and may safely run more than once.
    """
    if not frappe.db.has_column(
        "Product Master",
        "product_tag",
    ):
        return

    for product, product_tag in PRODUCT_TAGS.items():
        if not frappe.db.exists(
            "Product Master",
            product,
        ):
            continue

        current_tag = (
            frappe.db.get_value(
                "Product Master",
                product,
                "product_tag",
            )
            or ""
        )

        if current_tag == product_tag:
            continue

        frappe.db.set_value(
            "Product Master",
            product,
            "product_tag",
            product_tag,
            update_modified=False,
        )
