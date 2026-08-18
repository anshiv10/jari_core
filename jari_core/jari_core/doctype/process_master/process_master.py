import frappe
from frappe.model.document import Document


class ProcessMaster(Document):

    def validate(self):
        self.sync_legacy_department()

    def sync_legacy_department(self):
        """
        `department` is retained for backward compatibility.

        New workflow routing uses:
            from_department
            to_department

        The legacy department continues to represent the destination
        department so existing reports, filters and payout logic remain
        compatible.
        """
        if self.to_department:
            self.department = self.to_department


def get_process_departments(process_master):
    if not process_master:
        return None

    values = frappe.db.get_value(
        "Process Master",
        process_master,
        [
            "process_name",
            "from_department",
            "to_department",
        ],
        as_dict=True,
    )

    if not values:
        frappe.throw(
            f"Process Master does not exist: "
            f"{process_master}"
        )

    if not values.from_department:
        frappe.throw(
            f"From Department is not configured in "
            f"Process {values.process_name or process_master}."
        )

    if not values.to_department:
        frappe.throw(
            f"To Department is not configured in "
            f"Process {values.process_name or process_master}."
        )

    return values


def apply_process_department_defaults(
    doc,
    fallback_from=None,
    fallback_to=None,
):
    """
    Populate Issue routing exclusively from Process Master.

    fallback_from and fallback_to remain in the function signature
    only for compatibility with older callers. They are deliberately
    ignored by the new Process-first workflow.
    """
    if not doc.get("process_master"):
        doc.from_department = None
        doc.to_department = None
        return

    values = get_process_departments(
        doc.process_master
    )

    doc.from_department = (
        values.from_department
    )

    doc.to_department = (
        values.to_department
    )


def validate_process_departments(doc):
    if not doc.get("process_master"):
        frappe.throw("Process is required.")

    values = get_process_departments(
        doc.process_master
    )

    if (
        doc.get("from_department")
        != values.from_department
    ):
        frappe.throw(
            "From Department must be "
            f"{values.from_department} for Process "
            f"{values.process_name or doc.process_master}."
        )

    if (
        doc.get("to_department")
        != values.to_department
    ):
        frappe.throw(
            "To Department must be "
            f"{values.to_department} for Process "
            f"{values.process_name or doc.process_master}."
        )


JARI_ISSUE_TYPES = (
    "Melting Issue",
    "Pavtha Issue",
    "Taniya Issue",
    "Spindal Issue",
    "Gilit Issue",
    "Asarva Issue",
    "YT Issue",
)


def validate_process_issue_type(
    doc,
    expected_issue_type,
):
    """
    Ensure a Process can be used only from its configured
    Jari Issue Type.

    Existing documents that already contain the same Process are
    preserved for historical compatibility. New documents and
    Process changes are validated strictly.
    """
    process_master = doc.get("process_master")

    if not process_master:
        return

    configured_issue_type = frappe.db.get_value(
        "Process Master",
        process_master,
        "jari_issue_type",
    )

    if configured_issue_type == expected_issue_type:
        return

    if not doc.is_new() and doc.name:
        stored_process = frappe.db.get_value(
            doc.doctype,
            doc.name,
            "process_master",
        )

        if stored_process == process_master:
            return

    process_title = (
        frappe.db.get_value(
            "Process Master",
            process_master,
            "process_name",
        )
        or process_master
    )

    if not configured_issue_type:
        frappe.throw(
            f"Jari Issue Type is not configured for "
            f"Process {process_title}."
        )

    frappe.throw(
        f"Process {process_title} belongs to "
        f"{configured_issue_type} and cannot be used in "
        f"{expected_issue_type}."
    )


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def process_by_jari_issue_type_query(
    doctype,
    txt,
    searchfield,
    start,
    page_len,
    filters,
):
    filters = frappe._dict(filters or {})

    issue_type = filters.get("jari_issue_type")

    if not issue_type:
        return []

    if issue_type not in JARI_ISSUE_TYPES:
        frappe.throw(
            f"Unsupported Jari Issue Type: {issue_type}"
        )

    return frappe.db.sql(
        """
        SELECT
            process.name,
            process.process_name
        FROM `tabProcess Master` process
        WHERE process.jari_issue_type = %(issue_type)s
          AND (
              process.name LIKE %(txt)s
              OR COALESCE(
                  process.process_name,
                  ''
              ) LIKE %(txt)s
              OR COALESCE(
                  process.process_code,
                  ''
              ) LIKE %(txt)s
          )
        ORDER BY
            COALESCE(process.sequence_order, 0),
            process.process_name,
            process.name
        LIMIT %(start)s, %(page_len)s
        """,
        {
            "issue_type": issue_type,
            "txt": f"%{txt}%",
            "start": start,
            "page_len": page_len,
        },
    )


MASTER_PROCESS_PARENTFIELD = "processes"

SUPPORTED_PROCESS_MASTERS = {
    "Jobworker Master": {
        "title_field": "jobworker_name",
        "has_active": False,
    },
    "Worker Master": {
        "title_field": "employee",
        "has_active": True,
    },
    "Quality Master": {
        "title_field": "quality_code",
        "has_active": False,
    },
}


def validate_master_process_assignments(doc):
    """
    Validate the reusable Processes child table on Worker,
    Jobworker and Quality masters.
    """
    seen = set()

    for row in doc.get(MASTER_PROCESS_PARENTFIELD) or []:
        if not row.process_master:
            frappe.throw(
                f"Process is required in row #{row.idx}."
            )

        if not frappe.db.exists(
            "Process Master",
            row.process_master,
        ):
            frappe.throw(
                f"Process Master {row.process_master} "
                f"does not exist in row #{row.idx}."
            )

        if row.process_master in seen:
            frappe.throw(
                f"Process {row.process_master} is selected "
                f"more than once."
            )

        seen.add(row.process_master)


def sync_legacy_process_assignment(doc):
    """
    Keep the hidden single process_master field populated with
    the first active mapping for backward compatibility.

    New filtering and validation must use the Processes table.
    """
    if not doc.meta.has_field("process_master"):
        return

    active_processes = [
        row.process_master
        for row in (
            doc.get(MASTER_PROCESS_PARENTFIELD)
            or []
        )
        if row.process_master and row.active
    ]

    doc.process_master = (
        active_processes[0]
        if active_processes
        else None
    )


def get_process_assignment(
    master_doctype,
    master_name,
    process_master,
    active_only=True,
):
    if master_doctype not in SUPPORTED_PROCESS_MASTERS:
        frappe.throw(
            f"Unsupported Process assignment master: "
            f"{master_doctype}"
        )

    if not master_name or not process_master:
        return None

    filters = {
        "parent": master_name,
        "parenttype": master_doctype,
        "parentfield": MASTER_PROCESS_PARENTFIELD,
        "process_master": process_master,
    }

    if active_only:
        filters["active"] = 1

    return frappe.db.get_value(
        "Master Process Assignment",
        filters,
        [
            "name",
            "process_master",
            "active",
        ],
        as_dict=True,
    )


def party_has_process(
    master_doctype,
    master_name,
    process_master,
):
    return bool(
        get_process_assignment(
            master_doctype,
            master_name,
            process_master,
            active_only=True,
        )
    )


def validate_party_process_assignment(
    selected_party,
    process_master,
    master_doctype,
    label=None,
    require_active=False,
):
    display_label = (
        label
        or master_doctype.replace(" Master", "")
    )

    if not selected_party:
        return

    if not process_master:
        frappe.throw(
            f"Please select Process before selecting "
            f"{display_label}."
        )

    if not frappe.db.exists(
        master_doctype,
        selected_party,
    ):
        frappe.throw(
            f"{display_label} {selected_party} does not "
            f"exist in {master_doctype}."
        )

    if require_active:
        meta = frappe.get_meta(master_doctype)

        if meta.has_field("active"):
            active = frappe.db.get_value(
                master_doctype,
                selected_party,
                "active",
            )

            if not active:
                frappe.throw(
                    f"{display_label} {selected_party} "
                    f"is inactive."
                )

    if not party_has_process(
        master_doctype,
        selected_party,
        process_master,
    ):
        process_title = (
            frappe.db.get_value(
                "Process Master",
                process_master,
                "process_name",
            )
            or process_master
        )

        frappe.throw(
            f"{display_label} {selected_party} is not "
            f"assigned to Process {process_title}."
        )


def validate_process_party(
    doc,
    fieldname,
    master_doctype,
    label=None,
    require_active=False,
):
    validate_party_process_assignment(
        selected_party=doc.get(fieldname),
        process_master=doc.get("process_master"),
        master_doctype=master_doctype,
        label=(
            label
            or fieldname.replace(
                "_",
                " ",
            ).title()
        ),
        require_active=require_active,
    )



@frappe.whitelist()
def get_master_process_assignment_status(
    master_doctype,
    master_name,
    process_master,
    require_active=0,
):
    """
    Return Process-assignment status for browser-side validation.

    Server-side transaction validation remains authoritative.
    """
    if master_doctype not in SUPPORTED_PROCESS_MASTERS:
        frappe.throw(
            f"Unsupported Process assignment master: "
            f"{master_doctype}"
        )

    result = {
        "exists": False,
        "assigned": False,
        "active": True,
        "valid": False,
    }

    if not master_name or not process_master:
        return result

    if not frappe.db.exists(
        master_doctype,
        master_name,
    ):
        return result

    result["exists"] = True

    config = SUPPORTED_PROCESS_MASTERS[
        master_doctype
    ]

    if (
        int(require_active or 0)
        and config["has_active"]
    ):
        result["active"] = bool(
            frappe.db.get_value(
                master_doctype,
                master_name,
                "active",
            )
        )

    result["assigned"] = party_has_process(
        master_doctype,
        master_name,
        process_master,
    )

    result["valid"] = bool(
        result["exists"]
        and result["assigned"]
        and result["active"]
    )

    return result


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def process_assigned_master_query(
    doctype,
    txt,
    searchfield,
    start,
    page_len,
    filters,
):
    filters = frappe._dict(filters or {})

    master_doctype = filters.get(
        "master_doctype"
    )

    process_master = filters.get(
        "process_master"
    )

    require_active = int(
        filters.get("require_active") or 0
    )

    config = SUPPORTED_PROCESS_MASTERS.get(
        master_doctype
    )

    if not config:
        frappe.throw(
            f"Unsupported Process assignment master: "
            f"{master_doctype}"
        )

    if doctype != master_doctype:
        frappe.throw(
            "Link query DocType does not match "
            "the configured master."
        )

    if not process_master:
        return []

    title_field = config["title_field"]

    active_condition = ""

    if (
        require_active
        and config["has_active"]
    ):
        active_condition = (
            " AND COALESCE(master.active, 0) = 1 "
        )

    return frappe.db.sql(
        f"""
        SELECT DISTINCT
            master.name,
            COALESCE(
                master.`{title_field}`,
                master.name
            ) AS description
        FROM `tab{master_doctype}` master
        INNER JOIN
            `tabMaster Process Assignment` assignment
          ON assignment.parent = master.name
         AND assignment.parenttype = %(master_doctype)s
         AND assignment.parentfield =
             %(parentfield)s
         AND assignment.process_master =
             %(process_master)s
         AND assignment.active = 1
        WHERE (
            master.name LIKE %(txt)s
            OR COALESCE(
                master.`{title_field}`,
                ''
            ) LIKE %(txt)s
        )
        {active_condition}
        ORDER BY
            COALESCE(
                master.`{title_field}`,
                master.name
            )
        LIMIT %(start)s, %(page_len)s
        """,
        {
            "master_doctype":
                master_doctype,
            "parentfield":
                MASTER_PROCESS_PARENTFIELD,
            "process_master":
                process_master,
            "txt": f"%{txt}%",
            "start": start,
            "page_len": page_len,
        },
    )
