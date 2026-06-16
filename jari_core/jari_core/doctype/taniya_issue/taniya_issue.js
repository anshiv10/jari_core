frappe.ui.form.on('Taniya Issue', {
    refresh(frm) {
        if (!frm.doc.issue_date) frm.set_value('issue_date', frappe.datetime.get_today());
        if (!frm.doc.issue_type) frm.set_value('issue_type', 'New Batch');

        frm.set_query('process_master', () => ({ filters: { department: 'TANIYA' } }));

        frm.trigger('load_existing_batches');
        frm.trigger('toggle_batch_fields');
        calculate_taniya_issue_totals(frm);
    },

    issue_type(frm) {
        frm.trigger('toggle_batch_fields');
        frm.trigger('set_batch_no');
    },

    load_existing_batches(frm) {
        frappe.call({
            method: 'frappe.client.get_list',
            args: {
                doctype: 'Taniya Issue',
                filters: { docstatus: 1 },
                fields: ['batch_no'],
                limit_page_length: 500
            },
            callback(r) {
                let batches = [...new Set((r.message || []).map(x => x.batch_no).filter(Boolean))];
                frm.set_df_property('existing_batch_no', 'options', [''].concat(batches).join('\n'));
            }
        });
    },

    new_batch_no(frm) { frm.trigger('set_batch_no'); },
    existing_batch_no(frm) { frm.trigger('set_batch_no'); },

    toggle_batch_fields(frm) {
        let is_new = frm.doc.issue_type === 'New Batch';
        frm.toggle_display('new_batch_no', is_new);
        frm.toggle_reqd('new_batch_no', is_new);
        frm.toggle_display('existing_batch_no', !is_new);
        frm.toggle_reqd('existing_batch_no', !is_new);
        frm.set_df_property('batch_no', 'read_only', 1);
    },

    set_batch_no(frm) {
        frm.set_value('batch_no', frm.doc.issue_type === 'New Batch' ? (frm.doc.new_batch_no || '') : (frm.doc.existing_batch_no || ''));
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
                d.operator_name = frm.doc.operator;
            });

            frm.refresh_field('issue_items');
            calculate_taniya_issue_totals(frm);
        });
    }
});

frappe.ui.form.on('Taniya Issue Item', {
    weight(frm) { calculate_taniya_issue_totals(frm); },
    issue_items_add(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        frappe.model.set_value(cdt, cdn, 'issue_date', frm.doc.issue_date || frappe.datetime.get_today());
        frappe.model.set_value(cdt, cdn, 'operator_name', frm.doc.operator);
    },
    issue_items_remove(frm) { calculate_taniya_issue_totals(frm); }
});

function calculate_taniya_issue_totals(frm) {
    let total = 0;
    (frm.doc.issue_items || []).forEach(row => total += flt(row.weight));
    frm.set_value('total_issue_weight', total);
}
