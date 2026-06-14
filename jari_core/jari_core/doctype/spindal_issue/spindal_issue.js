frappe.ui.form.on('Spindal Issue', {
    refresh(frm) {
        if (!frm.doc.issue_date) {
            frm.set_value('issue_date', frappe.datetime.get_today());
        }

        frm.set_query('process_master', function() {
            return { filters: { department: 'Spindal' } };
        });
    },

    process_master(frm) {
        if (!frm.doc.process_master) return;

        frappe.call({
            method: 'frappe.client.get',
            args: {
                doctype: 'Process Master',
                name: frm.doc.process_master
            },
            callback(r) {
                const p = r.message;
                if (!p) return;

                if (!frm.doc.from_department) frm.set_value('from_department', 'Taniya');
                if (!frm.doc.to_department) frm.set_value('to_department', 'Spindal');

                frm.clear_table('peti_items');

                (p.input_products || []).forEach(row => {
                    let d = frm.add_child('peti_items');
                    d.product = row.product;
                    d.uom = row.uom;
                });

                frm.refresh_field('peti_items');
                calculate_spindal_issue_totals(frm);
            }
        });
    }
});

frappe.ui.form.on('Spindal Issue Peti Item', {
    net_weight(frm, cdt, cdn) {
        calculate_spindal_issue_totals(frm);
    },

    peti_items_remove(frm) {
        calculate_spindal_issue_totals(frm);
    }
});

function calculate_spindal_issue_totals(frm) {
    let total_peti = 0;
    let total_net_weight = 0;

    (frm.doc.peti_items || []).forEach(row => {
        total_peti += 1;
        total_net_weight += flt(row.net_weight);
    });

    frm.set_value('total_peti', total_peti);
    frm.set_value('total_net_weight', total_net_weight);
}
