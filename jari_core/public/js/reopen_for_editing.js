(() => {
    const supported_doctypes = new Set([
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
    ]);

    function user_can_reopen(frm) {
        if (!frm || !frm.doc) {
            return false;
        }

        if (!supported_doctypes.has(frm.doctype)) {
            return false;
        }

        if (frm.doc.docstatus !== 1) {
            return false;
        }

        const permissions = frm.perm || [];

        return permissions.some(
            (perm) =>
                Boolean(perm.cancel) &&
                Boolean(perm.amend)
        );
    }

    function add_reopen_button(frm) {
        if (!user_can_reopen(frm)) {
            return;
        }

        frm.add_custom_button(
            __("Reopen for Editing"),
            () => {
                const document_name =
                    frappe.utils.escape_html(
                        frm.doc.name
                    );

                const message = __(
                    "This will safely cancel {0} and create a new amended Draft.<br><br>" +
                    "The submitted original will remain Cancelled for audit history.<br><br>" +
                    "Continue?",
                    [
                        `<b>${document_name}</b>`,
                    ]
                );

                frappe.confirm(
                    message,
                    () => {
                        frappe.call({
                            method:
                                "jari_core.jari_core.reopen_utils.reopen_for_editing",

                            args: {
                                doctype:
                                    frm.doctype,

                                name:
                                    frm.doc.name,
                            },

                            freeze:
                                true,

                            freeze_message:
                                __(
                                    "Reopening document safely..."
                                ),
                        }).then((response) => {
                            const result =
                                response.message;

                            if (
                                !result ||
                                !result.doctype ||
                                !result.name
                            ) {
                                frappe.throw(
                                    __(
                                        "Reopen completed without a valid amended document."
                                    )
                                );
                            }

                            frappe.show_alert(
                                {
                                    message: __(
                                        "Amended Draft {0} created.",
                                        [
                                            result.name,
                                        ]
                                    ),
                                    indicator:
                                        "green",
                                },
                                5
                            );

                            frappe.set_route(
                                "Form",
                                result.doctype,
                                result.name
                            );
                        });
                    }
                );
            },
            __("Actions")
        );
    }

    supported_doctypes.forEach(
        (doctype) => {
            frappe.ui.form.on(
                doctype,
                {
                    refresh(frm) {
                        add_reopen_button(
                            frm
                        );
                    },
                }
            );
        }
    );
})();
