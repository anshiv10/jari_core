frappe.ui.form.on('Melting Receive', {
    refresh(frm) {
        if (!frm.doc.receive_date) {
            frm.set_value('receive_date', frappe.datetime.get_today());
        }

        set_issue_batch_display(frm);
    },

    issue_no(frm) {
        set_issue_batch_display(frm);
    },

    melting_issue(frm) {
        set_issue_batch_display(frm);
    }
});

function set_issue_batch_display(frm) {
    let issue = frm.doc.issue_no || frm.doc.melting_issue;

    if (!issue || !frm.fields_dict.issue_batch_display) {
        return;
    }

    frappe.db.get_doc("Melting Issue", issue).then(doc => {
        let batch = doc.batch_no || doc.name;
        let date = doc.issue_date || "";

        frm.set_value(
            "issue_batch_display",
            batch + (date ? " | " + date : "")
        );
    });
}