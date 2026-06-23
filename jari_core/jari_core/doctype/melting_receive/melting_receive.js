frappe.ui.form.on('Melting Receive', {
    setup(frm) {
        set_issue_query(frm);
    },

    refresh(frm) {
        set_issue_query(frm);

        if (!frm.doc.receive_date) {
            frm.set_value('receive_date', frappe.datetime.get_today());
        }

        set_issue_batch_display(frm);
    },

    issue_no(frm) {
        fetch_issue_receive_details(frm);
    },

    melting_issue(frm) {
        fetch_issue_receive_details(frm);
    }
});

function set_issue_query(frm) {
    ["issue_no", "melting_issue"].forEach(fieldname => {
        if (frm.fields_dict[fieldname]) {
            frm.set_query(fieldname, function() {
                return {
                    query: "jari_core.jari_core.doctype.melting_receive.melting_receive.melting_issue_query"
                };
            });
        }
    });
}

function fetch_issue_receive_details(frm) {
    let issue = frm.doc.issue_no || frm.doc.melting_issue;

    if (!issue) {
        return;
    }

    frappe.call({
        method: "jari_core.jari_core.doctype.melting_receive.melting_receive.get_melting_issue_receive_details",
        args: {
            melting_issue: issue
        },
        callback(r) {
            if (!r.message) {
                return;
            }

            let data = r.message;

            frm.set_value("company", data.company);
            frm.set_value("batch_no", data.batch_no);
            frm.set_value("process_master", data.process_master);
            frm.set_value("quality_code", data.quality_code);
            frm.set_value("total_input_weight", data.total_issue_weight || 0);

            if (frm.fields_dict.issue_batch_display) {
                frm.set_value("issue_batch_display", data.batch_display);
            }

            frm.clear_table("output_items");
            (data.output_items || []).forEach(row => {
                let d = frm.add_child("output_items");
                d.product = row.product;
                d.uom = row.uom || "KG";
                d.weight = row.weight || 0;
            });
            frm.refresh_field("output_items");

            frm.clear_table("waste_items");
            (data.waste_items || []).forEach(row => {
                let d = frm.add_child("waste_items");
                d.waste_product = row.waste_product;
                d.uom = row.uom || "KG";
                d.weight = row.weight || 0;
            });
            frm.refresh_field("waste_items");
        }
    });
}

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