frappe.ui.form.on('Pavtha Issue', {
    refresh(frm) {
        if (!frm.doc.issue_date) {
            frm.set_value('issue_date', frappe.datetime.get_today());
        }

        frm.set_query('process_master', function() {
            return { filters: { department: 'Pavtha' } };
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

                frm.clear_table('issue_items');

                (p.input_products || []).forEach(row => {
                    let d = frm.add_child('issue_items');
                    d.product = row.product;
                    d.uom = row.uom;
                });

                frm.refresh_field('issue_items');

                frappe.show_alert({
                    message: 'Pavtha input products auto-filled',
                    indicator: 'green'
                });
            }
        });
    },

    rate_per_kg(frm) {
        calculate_total_payout(frm);
    }
});

frappe.ui.form.on('Pavtha Issue Item', {
    weight(frm) {
        calculate_total_payout(frm);
    },

    issue_items_remove(frm) {
        calculate_total_payout(frm);
    }
});

function calculate_total_payout(frm) {
    let total = 0;

    (frm.doc.issue_items || []).forEach(row => {
        total += flt(row.weight);
    });

    frm.set_value('total_issue_weight', total);
    frm.set_value('total_payout', total * flt(frm.doc.rate_per_kg));
}
