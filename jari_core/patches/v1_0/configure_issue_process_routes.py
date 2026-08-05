import frappe


ROUTES = {
    "Melting": (
        "Raw Material Store",
        "Melting",
    ),
    "Pavtha": (
        "Melting",
        "Pavtha",
    ),
    "Taniya": (
        "Pavtha",
        "Taniya",
    ),
    "Kasab / Spindal": (
        "Taniya",
        "Spindal",
    ),
    "Gilit": (
        "Spindal",
        "Gilit",
    ),
    "AUR to DATA": (
        "Taniya",
        "Rangrej/Asarva",
    ),
}


def execute():
    for process_name, (
        from_department,
        to_department,
    ) in ROUTES.items():
        process = frappe.db.get_value(
            "Process Master",
            {"process_name": process_name},
            "name",
        )

        if not process:
            frappe.throw(
                f"Process Master does not exist: "
                f"{process_name}"
            )

        for department in [
            from_department,
            to_department,
        ]:
            if not frappe.db.exists(
                "Department Master",
                department,
            ):
                frappe.throw(
                    f"Department Master does not exist: "
                    f"{department}"
                )

        frappe.db.set_value(
            "Process Master",
            process,
            {
                "from_department": from_department,
                "to_department": to_department,
                "department": to_department,
            },
            update_modified=False,
        )
