frappe.ui.form.on('Melting Issue', {
    refresh(frm) {
        if (!frm.doc.issue_date) {
            frm.set_value('issue_date', frappe.datetime.get_today());
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

                frm.clear_table('issue_items');

                (p.input_products || []).forEach(row => {
                    let d = frm.add_child('issue_items');
                    d.product = row.product;
                    d.uom = row.uom;
                });

                frm.refresh_field('issue_items');

                frappe.show_alert({
                    message: 'Melting input products auto-filled',
                    indicator: 'green'
                });
            }
        });
    }
});