import frappe


DEFAULT_TYPE = "In-house"


def execute():
    """
    Backfill Issue/Receive Type for historical Pavtha transactions.

    This patch is intentionally idempotent:
    - Existing valid values are preserved.
    - Only blank or NULL values are updated.
    - Pavtha Receive inherits the value from its linked Pavtha Issue.
    """

    if not frappe.db.table_exists("Pavtha Issue"):
        return

    if not frappe.db.has_column("Pavtha Issue", "issue_receive_type"):
        return

    frappe.db.sql(
        """
        UPDATE `tabPavtha Issue`
        SET `issue_receive_type` = %s
        WHERE IFNULL(`issue_receive_type`, '') = ''
        """,
        (DEFAULT_TYPE,),
    )

    if not frappe.db.table_exists("Pavtha Receive"):
        return

    if not frappe.db.has_column("Pavtha Receive", "issue_receive_type"):
        return

    frappe.db.sql(
        """
        UPDATE `tabPavtha Receive` pr
        LEFT JOIN `tabPavtha Issue` pi
            ON pi.name = pr.pavtha_issue
        SET pr.issue_receive_type =
            COALESCE(
                NULLIF(pi.issue_receive_type, ''),
                %s
            )
        WHERE IFNULL(pr.issue_receive_type, '') = ''
        """,
        (DEFAULT_TYPE,),
    )
