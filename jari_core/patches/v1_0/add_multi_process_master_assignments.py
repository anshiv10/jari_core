import frappe


PARENTFIELD = "processes"


def add_assignment(
    master_doctype,
    master_name,
    process_master,
):
    """
    Insert one child mapping directly.

    The parent master is intentionally not saved because historical
    Quality Master records may predate currently mandatory fields.
    Direct child insertion avoids unrelated parent validation while
    preserving the correct parent, parenttype and parentfield links.
    """
    if (
        not master_name
        or not process_master
        or not frappe.db.exists(
            master_doctype,
            master_name,
        )
        or not frappe.db.exists(
            "Process Master",
            process_master,
        )
    ):
        return False

    existing = frappe.db.exists(
        "Master Process Assignment",
        {
            "parent": master_name,
            "parenttype": master_doctype,
            "parentfield": PARENTFIELD,
            "process_master": process_master,
        },
    )

    if existing:
        frappe.db.set_value(
            "Master Process Assignment",
            existing,
            "active",
            1,
            update_modified=False,
        )
        return False

    max_idx = frappe.db.sql(
        """
        SELECT COALESCE(MAX(idx), 0)
        FROM `tabMaster Process Assignment`
        WHERE parent = %s
          AND parenttype = %s
          AND parentfield = %s
        """,
        (
            master_name,
            master_doctype,
            PARENTFIELD,
        ),
    )[0][0]

    assignment = frappe.get_doc({
        "doctype": "Master Process Assignment",
        "parent": master_name,
        "parenttype": master_doctype,
        "parentfield": PARENTFIELD,
        "idx": int(max_idx or 0) + 1,
        "process_master": process_master,
        "active": 1,
    })

    assignment.insert(
        ignore_permissions=True
    )

    return True


def migrate_legacy_fields():
    created = 0

    for master_doctype in [
        "Jobworker Master",
        "Worker Master",
    ]:
        for row in frappe.get_all(
            master_doctype,
            filters={
                "process_master":
                    ["is", "set"],
            },
            fields=[
                "name",
                "process_master",
            ],
            limit_page_length=0,
        ):
            created += int(
                add_assignment(
                    master_doctype,
                    row.name,
                    row.process_master,
                )
            )

    return created


def migrate_parent_transactions():
    created = 0

    mappings = [
        (
            "Pavtha Issue",
            "outsourcer",
            "Jobworker Master",
        ),
        (
            "Pavtha Issue",
            "operator",
            "Worker Master",
        ),
        (
            "Gilit Issue",
            "gilit_karigar",
            "Worker Master",
        ),
        (
            "Taniya Issue",
            "operator",
            "Worker Master",
        ),
        (
            "Melting Issue",
            "operator",
            "Worker Master",
        ),
        (
            "Spindal Issue",
            "operator",
            "Worker Master",
        ),
        (
            "Asarva Issue",
            "asarva_outsourcer",
            "Jobworker Master",
        ),
    ]

    for (
        transaction_doctype,
        party_field,
        master_doctype,
    ) in mappings:
        meta = frappe.get_meta(
            transaction_doctype
        )

        if not (
            meta.has_field("process_master")
            and meta.has_field(party_field)
        ):
            continue

        rows = frappe.get_all(
            transaction_doctype,
            filters={
                "docstatus": ["<", 2],
                "process_master": ["is", "set"],
                party_field: ["is", "set"],
            },
            fields=[
                "process_master",
                party_field,
            ],
            limit_page_length=0,
        )

        for row in rows:
            created += int(
                add_assignment(
                    master_doctype,
                    row.get(party_field),
                    row.process_master,
                )
            )

    return created


def migrate_quality_transactions():
    created = 0

    for transaction_doctype in [
        "Pavtha Issue",
        "Gilit Issue",
        "Taniya Issue",
        "Melting Issue",
        "Spindal Issue",
        "Asarva Issue",
    ]:
        meta = frappe.get_meta(
            transaction_doctype
        )

        if not (
            meta.has_field("process_master")
            and meta.has_field("quality_code")
        ):
            continue

        rows = frappe.get_all(
            transaction_doctype,
            filters={
                "docstatus": ["<", 2],
                "process_master": ["is", "set"],
                "quality_code": ["is", "set"],
            },
            fields=[
                "process_master",
                "quality_code",
            ],
            limit_page_length=0,
        )

        for row in rows:
            created += int(
                add_assignment(
                    "Quality Master",
                    row.quality_code,
                    row.process_master,
                )
            )

    return created


def migrate_asarva_child_workers():
    created = 0

    if not frappe.db.exists(
        "DocType",
        "Asarva Issue Item",
    ):
        return created

    rows = frappe.db.sql(
        """
        SELECT DISTINCT
            parent_issue.process_master,
            item.rangrej_operator
        FROM `tabAsarva Issue Item` item
        INNER JOIN `tabAsarva Issue` parent_issue
            ON parent_issue.name = item.parent
        WHERE parent_issue.docstatus < 2
          AND parent_issue.process_master IS NOT NULL
          AND parent_issue.process_master != ''
          AND item.rangrej_operator IS NOT NULL
          AND item.rangrej_operator != ''
        """,
        as_dict=True,
    )

    for row in rows:
        created += int(
            add_assignment(
                "Worker Master",
                row.rangrej_operator,
                row.process_master,
            )
        )

    return created


def execute():
    frappe.db.savepoint(
        "migrate_multi_process_assignments"
    )

    try:
        summary = {
            "legacy_assignments":
                migrate_legacy_fields(),
            "party_assignments":
                migrate_parent_transactions(),
            "quality_assignments":
                migrate_quality_transactions(),
            "asarva_child_workers":
                migrate_asarva_child_workers(),
        }

        frappe.db.commit()

        print(
            "\nMULTI-PROCESS ASSIGNMENT "
            "MIGRATION COMPLETED"
        )

        print(summary)

    except Exception:
        frappe.db.rollback(
            save_point=
                "migrate_multi_process_assignments"
        )
        raise
