frappe.ui.form.on('Spindal Issue', {
    refresh(frm) {
        if (!frm.doc.issue_date) {
            frm.set_value('issue_date', frappe.datetime.get_today());
        }

        frm.set_value('issue_type', 'New Batch');

        frm.set_query('process_master', function() {
            return {
                filters: {
                    department: 'SPINDAL'
                }
            };
        });

        frm.trigger('set_active_batch_no');
        calculate_spindal_issue_totals(frm);
    },

    new_batch_no(frm) {
        frm.trigger('set_active_batch_no');
    },

    operator(frm) {
        set_operator_in_child_rows(frm);
    },

    set_active_batch_no(frm) {
        frm.set_value('issue_type', 'New Batch');
        frm.set_value('active_batch_no', frm.doc.new_batch_no || '');
    },

    process_master(frm) {
        if (!frm.doc.process_master) return;

        frappe.db.get_doc('Process Master', frm.doc.process_master).then(p => {
            frm.clear_table('issue_items');

            (p.input_products || []).forEach(row => {
                let d = frm.add_child('issue_items');
                d.issue_date = frm.doc.issue_date || frappe.datetime.get_today();
                d.product = row.product;
                d.uom = row.uom;
                d.weight = 0;
                d.operator_name = frm.doc.operator || '';
            });

            frm.refresh_field('issue_items');
            calculate_spindal_issue_totals(frm);
        });
    }
});

frappe.ui.form.on('Spindal Issue Item', {
    issue_items_add(frm, cdt, cdn) {
        frappe.model.set_value(cdt, cdn, 'issue_date', frm.doc.issue_date || frappe.datetime.get_today());
        frappe.model.set_value(cdt, cdn, 'operator_name', frm.doc.operator || '');
    },

    weight(frm) {
        calculate_spindal_issue_totals(frm);
    },

    issue_items_remove(frm) {
        calculate_spindal_issue_totals(frm);
    }
});

function set_operator_in_child_rows(frm) {
    (frm.doc.issue_items || []).forEach(row => {
        frappe.model.set_value(row.doctype, row.name, 'operator_name', frm.doc.operator || '');
    });
}

function calculate_spindal_issue_totals(frm) {
    let total_weight = 0;

    (frm.doc.issue_items || []).forEach(row => {
        total_weight += flt(row.weight);
    });

    frm.set_value('total_issue_weight', total_weight);
}
