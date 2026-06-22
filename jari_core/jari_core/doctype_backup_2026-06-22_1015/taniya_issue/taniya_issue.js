frappe.ui.form.on('Taniya Issue', {
    refresh(frm) {
        if (!frm.doc.issue_date) {
            frm.set_value('issue_date', frappe.datetime.get_today());
        }

        frm.set_query('process_master', function() {
            return {
                filters: {
                    department: 'TANIYA'
                }
            };
        });

        frm.trigger('set_batch_no');
        calculate_taniya_issue_totals(frm);
    },

    new_batch_no(frm) {
        frm.trigger('set_batch_no');
    },

    operator(frm) {
        set_operator_in_child_rows(frm);
    },

    set_batch_no(frm) {
        frm.set_value('batch_no', frm.doc.new_batch_no || '');

        if (!frm.doc.new_batch_no) {
            frm.set_value('issue_type', 'New Batch');
            return;
        }

        frappe.db.count('Taniya Issue', {
            filters: {
                batch_no: frm.doc.new_batch_no,
                docstatus: 1,
                name: ['!=', frm.doc.name || '']
            }
        }).then(count => {
            frm.set_value('issue_type', count > 0 ? 'Re Issue' : 'New Batch');
        });
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
            calculate_taniya_issue_totals(frm);
        });
    }
});

frappe.ui.form.on('Taniya Issue Item', {
    issue_items_add(frm, cdt, cdn) {
        frappe.model.set_value(cdt, cdn, 'issue_date', frm.doc.issue_date || frappe.datetime.get_today());
        frappe.model.set_value(cdt, cdn, 'operator_name', frm.doc.operator || '');
    },

    weight(frm) {
        calculate_taniya_issue_totals(frm);
    },

    issue_items_remove(frm) {
        calculate_taniya_issue_totals(frm);
    }
});

function set_operator_in_child_rows(frm) {
    (frm.doc.issue_items || []).forEach(row => {
        frappe.model.set_value(row.doctype, row.name, 'operator_name', frm.doc.operator || '');
    });
}

function calculate_taniya_issue_totals(frm) {
    let total = 0;

    (frm.doc.issue_items || []).forEach(row => {
        total += flt(row.weight);
    });

    frm.set_value('total_issue_weight', total);
}
