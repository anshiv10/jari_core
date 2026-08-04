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


def apply_process_department_defaults(
    doc,
    fallback_from=None,
    fallback_to=None,
):
    """
    Populate missing Issue departments from the linked Process Master.

    Existing values are never overwritten. This is essential because
    users are explicitly allowed to override the Process Master defaults.
    """
    if doc.get("process_master"):
        values = frappe.db.get_value(
            "Process Master",
            doc.process_master,
            [
                "from_department",
                "to_department",
            ],
            as_dict=True,
        )

        if values:
            if not doc.get("from_department"):
                doc.from_department = values.from_department

            if not doc.get("to_department"):
                doc.to_department = values.to_department

    # Backward-compatible fallback for Process Masters not configured yet.
    if not doc.get("from_department") and fallback_from:
        doc.from_department = fallback_from

    if not doc.get("to_department") and fallback_to:
        doc.to_department = fallback_to


def validate_process_party(
    doc,
    fieldname,
    master_doctype,
    label=None,
    require_active=False,
):
    """
    Validate that a selected Worker/Jobworker belongs to the Process
    selected on the transaction.

    Browser filters improve usability, but this validation protects
    imports, API calls, scripts, and modified requests.
    """
    selected_party = doc.get(fieldname)

    if not selected_party:
        return

    process_master = doc.get("process_master")

    if not process_master:
        frappe.throw(
            f"Please select Process before selecting "
            f"{label or fieldname.replace('_', ' ').title()}."
        )

    if not frappe.db.exists(master_doctype, selected_party):
        frappe.throw(
            f"{label or fieldname.replace('_', ' ').title()} "
            f"{selected_party} does not exist in {master_doctype}."
        )

    fields = ["process_master"]

    if require_active and frappe.get_meta(master_doctype).has_field("active"):
        fields.append("active")

    values = frappe.db.get_value(
        master_doctype,
        selected_party,
        fields,
        as_dict=True,
    )

    if not values:
        frappe.throw(
            f"Unable to read {master_doctype} record {selected_party}."
        )

    if not values.process_master:
        frappe.throw(
            f"{label or fieldname.replace('_', ' ').title()} "
            f"{selected_party} is not assigned to any Process."
        )

    if values.process_master != process_master:
        selected_process_title = (
            frappe.db.get_value(
                "Process Master",
                process_master,
                "process_name",
            )
            or process_master
        )

        assigned_process_title = (
            frappe.db.get_value(
                "Process Master",
                values.process_master,
                "process_name",
            )
            or values.process_master
        )

        frappe.throw(
            f"{label or fieldname.replace('_', ' ').title()} "
            f"{selected_party} belongs to Process "
            f"{assigned_process_title}, but this document uses "
            f"Process {selected_process_title}."
        )

    if require_active and hasattr(values, "active") and not values.active:
        frappe.throw(
            f"{label or fieldname.replace('_', ' ').title()} "
            f"{selected_party} is inactive."
        )

