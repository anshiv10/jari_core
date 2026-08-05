import frappe


PROCESS_TYPES = {
    "Melting": "Melting Issue",
    "Pavtha": "Pavtha Issue",
    "Taniya": "Taniya Issue",
    "Kasab / Spindal": "Spindal Issue",
    "Gilit": "Gilit Issue",
    "AUR to DATA": "Asarva Issue",
}


def execute():
    for process_name, issue_type in (
        PROCESS_TYPES.items()
    ):
        processes = frappe.get_all(
            "Process Master",
            filters={
                "process_name": process_name,
            },
            pluck="name",
            limit_page_length=0,
        )

        if len(processes) != 1:
            frappe.throw(
                f"Expected exactly one Process Master "
                f"named {process_name}; found "
                f"{len(processes)}."
            )

        frappe.db.set_value(
            "Process Master",
            processes[0],
            "jari_issue_type",
            issue_type,
            update_modified=False,
        )
