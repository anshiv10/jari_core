frappe.ui.form.on('Melting Receive', {
    setup(frm) {
        set_issue_query(frm);
    },

    refresh(frm) {
        set_issue_query(frm);
        set_issue_batch_display(frm);
    },

    issue_no(frm) {
        set_issue_batch_display(frm);
    },

    melting_issue(frm) {
        set_issue_batch_display(frm);
    }
});

function set_issue_query(frm) {
    ["issue_no", "melting_issue"].forEach(fieldname => {
        if (frm.fields_dict[fieldname]) {
            frm.set_query(fieldname, function() {
                return {
                    query: "jari_core.jari_core.doctype.melting_receive.melting_receive.melting_issue_query",
                    filters: {
                        company: frm.doc.company
                    }
                };
            });
        }
    });
}

function set_issue_batch_display(frm) {
    let issue = frm.doc.issue_no || frm.doc.melting_issue;

    if (!issue || !frm.fields_dict.issue_batch_display) return;

    frappe.db.get_doc("Melting Issue", issue).then(doc => {
        let batch = doc.active_batch_no || doc.batch_no || doc.name;
        let date = doc.issue_date || doc.posting_date || "";
        frm.set_value("issue_batch_display", batch + (date ? " | " + date : ""));
    });
}
