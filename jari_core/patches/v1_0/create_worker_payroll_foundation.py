import frappe


DEPARTMENT_NAME = "Rangrej/Asarva"


SALARY_FORMATS = [
    {
        "salary_format_name": "BHATHI - Kasab Rilling Worker",
        "salary_group": "BHATHI",
        "worker_category": "Kasab Rilling Worker",
        "calculation_basis": "Hours",
        "data_source": "Geo Attendance",
        "requires_quality": 0,
        "allow_extra_amount": 0,
        "allow_manual_quantity": 0,
    },
    {
        "salary_format_name": "BHATHI - Chapadiya Worker",
        "salary_group": "BHATHI",
        "worker_category": "Chapadiya Worker",
        "calculation_basis": "Weight",
        "data_source": "Manual Weight",
        "requires_quality": 0,
        "allow_extra_amount": 0,
        "allow_manual_quantity": 1,
    },
    {
        "salary_format_name": "BHATHI - Spindle Worker",
        "salary_group": "BHATHI",
        "worker_category": "Spindle Worker",
        "calculation_basis": "Hours",
        "data_source": "Manual Hours",
        "requires_quality": 1,
        "allow_extra_amount": 0,
        "allow_manual_quantity": 1,
    },
    {
        "salary_format_name": "UMIYA JARI - Chandi Gilit YT Worker",
        "salary_group": "UMIYA JARI",
        "worker_category": "Chandi Gilit YT Worker",
        "calculation_basis": "AUR",
        "data_source": "Transaction Piece",
        "requires_quality": 0,
        "allow_extra_amount": 0,
        "allow_manual_quantity": 0,
    },
    {
        "salary_format_name": "UMIYA JARI - Real Gilit Worker",
        "salary_group": "UMIYA JARI",
        "worker_category": "Real Gilit Worker",
        "calculation_basis": "Hours",
        "data_source": "Manual Hours",
        "requires_quality": 0,
        "allow_extra_amount": 1,
        "allow_manual_quantity": 1,
    },
    {
        "salary_format_name": "UMIYA JARI - Fast Gilit Worker",
        "salary_group": "UMIYA JARI",
        "worker_category": "Fast Gilit Worker",
        "calculation_basis": "Hours",
        "data_source": "Manual Hours",
        "requires_quality": 0,
        "allow_extra_amount": 1,
        "allow_manual_quantity": 1,
    },
    {
        "salary_format_name": "UMIYA JARI - Real Chapadiya Worker",
        "salary_group": "UMIYA JARI",
        "worker_category": "Real Chapadiya Worker",
        "calculation_basis": "Weight",
        "data_source": "Issue Transactions",
        "requires_quality": 0,
        "allow_extra_amount": 0,
        "allow_manual_quantity": 0,
    },
    {
        "salary_format_name": "UMIYA JARI - Imitation Chapadiya Worker",
        "salary_group": "UMIYA JARI",
        "worker_category": "Imitation Chapadiya Worker",
        "calculation_basis": "Issued Minus Received",
        "data_source": "Issue and Receive Transactions",
        "requires_quality": 0,
        "allow_extra_amount": 0,
        "allow_manual_quantity": 0,
    },
    {
        "salary_format_name": "UMIYA JARI - Spindal Worker",
        "salary_group": "UMIYA JARI",
        "worker_category": "Spindal Worker",
        "calculation_basis": "Hours",
        "data_source": "Manual Hours",
        "requires_quality": 1,
        "allow_extra_amount": 0,
        "allow_manual_quantity": 1,
    },
    {
        "salary_format_name": "UMIYA JARI - Firki Riling Worker",
        "salary_group": "UMIYA JARI",
        "worker_category": "Firki Riling Worker",
        "calculation_basis": "Piece",
        "data_source": "Transaction Piece",
        "requires_quality": 1,
        "allow_extra_amount": 0,
        "allow_manual_quantity": 0,
    },
    {
        "salary_format_name": "UMIYA JARI - Chip Worker",
        "salary_group": "UMIYA JARI",
        "worker_category": "Chip Worker",
        "calculation_basis": "Piece",
        "data_source": "Transaction Piece",
        "requires_quality": 1,
        "allow_extra_amount": 0,
        "allow_manual_quantity": 0,
    },
]


def execute():
    create_department()
    create_salary_formats()


def create_department():
    if frappe.db.exists(
        "Department Master",
        DEPARTMENT_NAME,
    ):
        return

    frappe.get_doc(
        {
            "doctype": "Department Master",
            "department_name": DEPARTMENT_NAME,
            "flow_type": "Real",
            "active": 1,
        }
    ).insert(ignore_permissions=True)


def create_salary_formats():
    if not frappe.db.exists(
        "DocType",
        "Worker Salary Format",
    ):
        frappe.throw(
            "Worker Salary Format DocType is not available. "
            "Run DocType synchronization before this patch."
        )

    for values in SALARY_FORMATS:
        name = values["salary_format_name"]

        if frappe.db.exists(
            "Worker Salary Format",
            name,
        ):
            continue

        frappe.get_doc(
            {
                "doctype": "Worker Salary Format",
                **values,
                "active": 1,
            }
        ).insert(ignore_permissions=True)
