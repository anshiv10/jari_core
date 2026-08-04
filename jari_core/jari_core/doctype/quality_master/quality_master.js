// Copyright (c) 2026, anSHIV and contributors
// For license information, please see license.txt

frappe.ui.form.on("Quality Master", {
    setup(frm) {
        frm.set_query("department", function () {
            const filters = {
                active: 1
            };

            if (frm.doc.flow_type) {
                filters.flow_type = frm.doc.flow_type;
            }

            return {
                filters: filters
            };
        });
    },

    flow_type(frm) {
        if (!frm.doc.department) {
            return;
        }

        frappe.db.get_value(
            "Department Master",
            frm.doc.department,
            ["flow_type", "active"]
        ).then((r) => {
            const department = r.message;

            if (!department) {
                frm.set_value("department", "");
                return;
            }

            if (
                cint(department.active) !== 1 ||
                (
                    frm.doc.flow_type &&
                    department.flow_type !== frm.doc.flow_type
                )
            ) {
                frm.set_value("department", "");
                frappe.show_alert({
                    message: __(
                        "Department was cleared because it does not match the selected Flow Type or is inactive."
                    ),
                    indicator: "orange"
                });
            }
        });
    }
});
