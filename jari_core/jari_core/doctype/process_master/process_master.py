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
