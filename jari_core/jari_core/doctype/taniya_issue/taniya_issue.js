frappe.ui.form.on('Taniya Issue', {
    refresh(frm) {
        if (!frm.doc.issue_date) {
            frm.set_value('issue_date', frappe.datetime.get_today());
        }

        if (!frm.doc.issue_type) {
            frm.set_value('issue_type', 'New Batch');
        }

        frm.trigger('toggle_batch_fields');
        calculate_taniya_issue_totals(frm);
    },

    issue_type(frm) {
        frm.trigger('toggle_batch_fields');
        frm.trigger('set_batch_no');
    },

    new_batch_no(frm) {
        frm.trigger('set_batch_no');
    },

    existing_batch_no(frm) {
        frm.trigger('set_batch_no');
    },

    toggle_batch_fields(frm) {
        const is_new = frm.doc.issue_type === 'New Batch';
        const is_reissue = frm.doc.issue_type === 'Re Issue';

        frm.toggle_display('new_batch_no', is_new);
        frm.toggle_reqd('new_batch_no', is_new);

        frm.toggle_display('existing_batch_no', is_reissue);
        frm.toggle_reqd('existing_batch_no', is_reissue);

        frm.set_df_property('batch_no', 'read_only', 1);
    },

    set_batch_no(frm) {
        if (frm.doc.issue_type === 'New Batch') {
            frm.set_value('batch_no', frm.doc.new_batch_no || '');
        }

        if (frm.doc.issue_type === 'Re Issue') {
            frm.set_value('batch_no', frm.doc.existing_batch_no || '');
        }
    }
});

frappe.ui.form.on('Taniya Issue Item', {
    weight(frm) {
        calculate_taniya_issue_totals(frm);
    },

    issue_items_remove(frm) {
        calculate_taniya_issue_totals(frm);
    }
});

function calculate_taniya_issue_totals(frm) {
    let total = 0;

    (frm.doc.issue_items || []).forEach(row => {
        total += flt(row.weight);
    });

    frm.set_value('total_issue_weight', total);
}
