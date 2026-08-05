# Copyright (c) 2026, anSHIV and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

from jari_core.jari_core.doctype.process_master.process_master import (
    validate_master_process_assignments,
)


class QualityMaster(Document):

    def validate(self):
        validate_master_process_assignments(self)
        self.validate_department()

    def validate_department(self):
        if not self.department:
            frappe.throw(_("Department is required."))

        department = frappe.db.get_value(
            "Department Master",
            self.department,
            ["department_name", "flow_type", "active"],
            as_dict=True,
        )

        if not department:
            frappe.throw(
                _("Department Master {0} does not exist.").format(
                    frappe.bold(self.department)
                )
            )

        if cint(department.active) != 1:
            frappe.throw(
                _("Department {0} is inactive.").format(
                    frappe.bold(department.department_name)
                )
            )

        if (
            self.flow_type
            and department.flow_type
            and self.flow_type != department.flow_type
        ):
            frappe.throw(
                _(
                    "Quality Flow Type {0} does not match Department "
                    "Flow Type {1}."
                ).format(
                    frappe.bold(self.flow_type),
                    frappe.bold(department.flow_type),
                )
            )
