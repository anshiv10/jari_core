frappe.ui.form.on('Spindal Issue', {
    refresh(frm) {
        if (!frm.doc.issue_date) {
            frm.set_value('issue_date', frappe.datetime.get_today());
        }

        if (!frm.doc.issue_type) {
            frm.set_value('issue_type', 'New Batch');
        }

        frm.set_query('process_master', function() {
            return {
                filters: {
                    department: 'SPINDAL'
                }
            };
        });

        frm.trigger('toggle_batch_fields');
        calculate_spindal_issue_totals(frm);
    },

    issue_type(frm) {
        frm.trigger('toggle_batch_fields');
        frm.trigger('set_active_batch_no');
    },

    new_batch_no(frm) {
        frm.trigger('set_active_batch_no');
    },

    existing_batch_no(frm) {
        frm.trigger('set_active_batch_no');
    },

    toggle_batch_fields(frm) {
        const is_new = frm.doc.issue_type === 'New Batch';
        const is_reissue = frm.doc.issue_type === 'Re Issue';

        frm.toggle_display('new_batch_no', is_new);
        frm.toggle_reqd('new_batch_no', is_new);

        frm.toggle_display('existing_batch_no', is_reissue);
        frm.toggle_reqd('existing_batch_no', is_reissue);

        frm.set_df_property('active_batch_no', 'read_only', 1);
    },

    set_active_batch_no(frm) {
        if (frm.doc.issue_type === 'New Batch') {
            frm.set_value('active_batch_no', frm.doc.new_batch_no || '');
        }

        if (frm.doc.issue_type === 'Re Issue') {
            frm.set_value('active_batch_no', frm.doc.existing_batch_no || '');
        }
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
                    frm.set_value('from_department', 'TANIYA');
                }

                if (!frm.doc.to_department) {
                    frm.set_value('to_department', 'SPINDAL');
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
