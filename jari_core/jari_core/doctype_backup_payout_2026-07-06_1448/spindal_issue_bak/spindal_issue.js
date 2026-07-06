frappe.ui.form.on('Spindal Issue', {
    refresh(frm) {
        if (!frm.doc.issue_date) {
            frm.set_value('issue_date', frappe.datetime.get_today());
        }

        frm.set_query('process_master', function() {
            return {
                filters: {
                    department: 'Spindal'
                }
            };
        });

        calculate_spindal_issue_totals(frm);
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

                if (!frm.doc.from_department) {
                    frm.set_value('from_department', 'Taniya');
                }

                if (!frm.doc.to_department) {
                    frm.set_value('to_department', 'Spindal');
                }

                frm.clear_table('issue_items');

                (p.input_products || []).forEach(row => {
                    let d = frm.add_child('issue_items');
                    d.product = row.product;
                    d.uom = row.uom;
                    d.weight = 0;
                });

                frm.refresh_field('issue_items');
                calculate_spindal_issue_totals(frm);
            }
        });
    }
});

frappe.ui.form.on('Spindal Issue Item', {
    weight(frm) {
        calculate_spindal_issue_totals(frm);
    },

    issue_items_remove(frm) {
        calculate_spindal_issue_totals(frm);
    }
});

function calculate_spindal_issue_totals(frm) {
    let total_weight = 0;

    (frm.doc.issue_items || []).forEach(row => {
        total_weight += flt(row.weight);
    });

    frm.set_value('total_issue_weight', total_weight);
}