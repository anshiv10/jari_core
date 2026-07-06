frappe.ui.form.on('Spindal Receive', {
    refresh(frm) {
        if (!frm.doc.receive_date) {
            frm.set_value('receive_date', frappe.datetime.get_today());
        }

        frm.set_query('spindal_issue', function() {
            return {
                query: 'jari_core.jari_core.doctype.spindal_receive.spindal_receive.spindal_issue_query'
            };
        });
    },

    spindal_issue(frm) {
        if (!frm.doc.spindal_issue) return;

        frappe.db.get_doc('Spindal Issue', frm.doc.spindal_issue).then(issue => {
            frm.set_value('company', issue.company);

            let batch_no = issue.active_batch_no || issue.batch_no;

            frappe.db.get_list('Spindal Peti Entry', {
                filters: {
                    spindal_issue: frm.doc.spindal_issue,
                    docstatus: 1
                },
                fields: ['name', 'net_weight'],
                limit: 500
            }).then(rows => {
                frm.clear_table('received_peti_items');

                rows.forEach(p => {
                    let d = frm.add_child('received_peti_items');
                    d.peti_no = p.name;
                    d.product = 'KASAB';
                    d.uom = 'KG';
                    d.net_weight = p.net_weight;
                });

                frm.refresh_field('received_peti_items');
            });
        });
    },

    waste_items_add(frm, cdt, cdn) {
        frappe.model.set_value(cdt, cdn, 'uom', 'KG');
    }
});
