import frappe
from frappe import _


# Only the core process Issue / Receive chain is enabled.
#
# Other submittable DocTypes such as Stock Transfer,
# Metal Recovery Entry, Spindal Peti Entry and Jari Sale
# intentionally remain outside this workflow until their own
# cancellation/amend semantics are reviewed separately.
REOPEN_SUPPORTED_DOCTYPES = {
    "Melting Issue",
    "Melting Receive",
    "Pavtha Issue",
    "Pavtha Receive",
    "Taniya Issue",
    "Taniya Receive",
    "Spindal Issue",
    "Spindal Receive",
    "Gilit Issue",
    "Gilit Receive",
    "Asarva Issue",
    "Asarva Receive",
    "YT Issue",
    "YT Receive",
}


# An Issue must not be reopened while a Receive/Peti document
# still depends on that exact submitted Issue.
ISSUE_DEPENDENCIES = {
    "Melting Issue": (
        ("Melting Receive", "melting_issue"),
    ),
    "Pavtha Issue": (
        ("Pavtha Receive", "pavtha_issue"),
    ),
    "Taniya Issue": (
        ("Taniya Receive", "taniya_issue"),
    ),
    "Spindal Issue": (
        ("Spindal Receive", "spindal_issue"),
        ("Spindal Peti Entry", "spindal_issue"),
    ),
    "Gilit Issue": (
        ("Gilit Receive", "gilit_issue"),
    ),
    "Asarva Issue": (
        ("Asarva Receive", "asarva_issue"),
    ),
    "YT Issue": (
        ("YT Receive", "yt_issue"),
    ),
}


def _validate_supported_doctype(doctype):
    if doctype not in REOPEN_SUPPORTED_DOCTYPES:
        frappe.throw(
            _(
                "{0} is not enabled for Reopen for Editing."
            ).format(doctype)
        )

    meta = frappe.get_meta(doctype)

    if not meta.is_submittable:
        frappe.throw(
            _(
                "{0} is not a submittable DocType."
            ).format(doctype)
        )


def _validate_reopen_permissions(doc):
    if not doc.has_permission("cancel"):
        frappe.throw(
            _(
                "You do not have Cancel permission for {0}."
            ).format(doc.doctype),
            frappe.PermissionError,
        )

    if not doc.has_permission("amend"):
        frappe.throw(
            _(
                "You do not have Amend permission for {0}."
            ).format(doc.doctype),
            frappe.PermissionError,
        )

    if not frappe.has_permission(
        doc.doctype,
        ptype="create",
    ):
        frappe.throw(
            _(
                "You do not have Create permission for {0}."
            ).format(doc.doctype),
            frappe.PermissionError,
        )


def _get_active_issue_dependencies(doc):
    dependencies = []

    for (
        dependent_doctype,
        link_field,
    ) in ISSUE_DEPENDENCIES.get(
        doc.doctype,
        (),
    ):
        if not frappe.db.exists(
            "DocType",
            dependent_doctype,
        ):
            continue

        meta = frappe.get_meta(
            dependent_doctype
        )

        if not meta.has_field(
            link_field
        ):
            continue

        rows = frappe.get_all(
            dependent_doctype,
            filters={
                link_field:
                    doc.name,

                "docstatus":
                    ["<", 2],
            },
            fields=[
                "name",
                "docstatus",
            ],
            order_by="creation asc",
            limit_page_length=20,
        )

        for row in rows:
            dependencies.append(
                {
                    "doctype":
                        dependent_doctype,

                    "name":
                        row.name,

                    "docstatus":
                        row.docstatus,
                }
            )

    return dependencies


def _validate_issue_dependencies(doc):
    dependencies = (
        _get_active_issue_dependencies(
            doc
        )
    )

    if not dependencies:
        return

    labels = []

    for dependency in dependencies[:10]:
        status = (
            "Saved"
            if int(
                dependency["docstatus"]
                or 0
            ) == 0
            else "Submitted"
        )

        labels.append(
            f"{dependency['doctype']} "
            f"{dependency['name']} "
            f"({status})"
        )

    if len(dependencies) > 10:
        labels.append(
            f"... and "
            f"{len(dependencies) - 10} more"
        )

    frappe.throw(
        _(
            "Cannot reopen {0} {1} because dependent "
            "documents still exist:<br><br>{2}<br><br>"
            "Cancel/delete the dependent documents first, "
            "then reopen this Issue."
        ).format(
            doc.doctype,
            doc.name,
            "<br>".join(labels),
        )
    )


def _create_amended_draft(cancelled_doc):
    """
    Materialize a previously-valid Submitted document as an
    editable amended Draft.

    The historical copy is intentionally persisted without
    running current entry-time business validation. Historical
    rows may reference resources that are no longer selectable
    today (for example a Peti that was consumed after the
    original Submit).

    This bypass applies ONLY to initial amended-Draft creation.
    Any later normal Save or Submit executes the DocType's full
    current validation/controller lifecycle.
    """
    amended = frappe.copy_doc(
        cancelled_doc
    )

    amended.docstatus = 0
    amended.name = None

    if amended.meta.has_field(
        "amended_from"
    ):
        amended.amended_from = (
            cancelled_doc.name
        )

    # Generate the normal amended document identity.
    amended.set_new_name()

    amended_name = amended.name
    amended.docstatus = 0

    # Persist parent directly so historical content is not
    # rejected merely while creating the editable Draft.
    amended.db_insert()

    # Persist child rows as fresh Draft rows.
    for table_field in (
        amended.meta.get_table_fields()
    ):
        rows = (
            amended.get(
                table_field.fieldname
            )
            or []
        )

        for row in rows:
            row.name = None
            row.parent = amended_name
            row.parenttype = amended.doctype
            row.parentfield = (
                table_field.fieldname
            )
            row.docstatus = 0

            row.set_new_name()
            row.db_insert()

    return frappe.get_doc(
        amended.doctype,
        amended_name,
    )


@frappe.whitelist()
def reopen_for_editing(
    doctype,
    name,
):
    """
    Safely reopen one submitted JARI process document.

    The submitted document is NEVER converted directly back
    to Draft.

    Workflow:
        Submitted
            -> Cancel safely
            -> create amended Draft
            -> return new Draft name

    Any exception rolls the whole request back automatically.
    """
    if not doctype or not name:
        frappe.throw(
            _("DocType and document name are required.")
        )

    _validate_supported_doctype(
        doctype
    )

    doc = frappe.get_doc(
        doctype,
        name,
    )

    if int(doc.docstatus or 0) != 1:
        frappe.throw(
            _(
                "{0} {1} must be Submitted before it "
                "can be reopened for editing."
            ).format(
                doctype,
                name,
            )
        )

    _validate_reopen_permissions(
        doc
    )

    # Issues can have directly linked Receive/Peti documents
    # that do not necessarily consume a Stock Source while Draft.
    # Protect those relationships explicitly.
    _validate_issue_dependencies(
        doc
    )

    # Standard Frappe cancellation is deliberate:
    # all controller on_cancel hooks and JARI inventory
    # reversal/dependency checks must execute.
    doc.cancel()

    if int(doc.docstatus or 0) != 2:
        frappe.throw(
            _(
                "Cancellation of {0} {1} did not complete."
            ).format(
                doctype,
                name,
            )
        )

    amended = _create_amended_draft(
        doc
    )

    if int(amended.docstatus or 0) != 0:
        frappe.throw(
            _(
                "Amended document {0} was not created "
                "as Draft."
            ).format(
                amended.name
            )
        )

    return {
        "doctype":
            amended.doctype,

        "name":
            amended.name,

        "amended_from":
            doc.name,

        "cancelled_original":
            doc.name,
    }
