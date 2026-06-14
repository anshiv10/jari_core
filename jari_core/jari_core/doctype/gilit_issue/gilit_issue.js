frappe.ui.form.on('Gilit Issue', {
    refresh(frm) {
        if (!frm.doc.issue_date) {
            frm.set_value('issue_date', frappe.datetime.get_today());
        }

        frm.set_query('spindal_issue', function() {
            return {
                filters: {
                    docstatus: 1,
                    status: ['!=', 'Closed'],
                    is_active_batch: 1
                }
            };
        });

        frm.set_query('process_master', function() {
            return { filters: { department: 'Gilit' } };
        });
    },

    spindal_issue(frm) {
        if (!frm.doc.spindal_issue) return;

        frappe.call({
            method: 'frappe.client.get',
            args: {
                doctype: 'Spindal Issue',
                name: frm.doc.spindal_issue
            },
            callback(r) {
                const sp = r.message;
                if (!sp) return;

                frm.set_value('company', sp.company);
                frm.set_value('active_batch_no', sp.active_batch_no);
                frm.set_value('quality_code', sp.quality_code);
                frm.set_value('operator', sp.operator);

                if (!frm.doc.from_department) frm.set_value('from_department', 'Spindal');
                if (!frm.doc.to_department) frm.set_value('to_department', 'Gilit');

                frm.clear_table('peti_items');

                (sp.peti_items || []).forEach(row => {
                    let d = frm.add_child('peti_items');
                    d.peti_no = row.peti_no;
                    d.product = row.product;
                    d.uom = row.uom;
                    d.gross_weight = row.gross_weight;
                    d.net_weight = row.net_weight;
                });

                frm.refresh_field('peti_items');
                calculate_gilit_issue_totals(frm);
            }
        });
    }
});

frappe.ui.form.on('Gilit Issue Peti Item', {
    net_weight(frm) {
        calculate_gilit_issue_totals(frm);
    },

    peti_items_remove(frm) {
        calculate_gilit_issue_totals(frm);
    }
});

function calculate_gilit_issue_totals(frm) {
    let total_peti = 0;
    let total_net_weight = 0;

    (frm.doc.peti_items || []).forEach(row => {
        total_peti += 1;
        total_net_weight += flt(row.net_weight);
    });

    frm.set_value('total_peti', total_peti);
    frm.set_value('total_net_weight', total_net_weight);
}
