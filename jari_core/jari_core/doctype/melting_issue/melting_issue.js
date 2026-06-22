frappe.ui.form.on('Melting Issue', {
    refresh(frm) {
        if (!frm.doc.issue_date) {
            frm.set_value('issue_date', frappe.datetime.get_today());
        }
    },

    process_master(frm) {
        if (!frm.doc.process_master) return;

        frappe.db.get_doc('Process Master', frm.doc.process_master).then(p => {
            frm.clear_table('issue_items');

            let rows = p.input_products || p.product_detail || p.input_items || [];

            rows.forEach(row => {
                let d = frm.add_child('issue_items');
                d.product = row.product;
                d.product_name = row.product_name || row.product;
                d.uom = row.uom || 'KG';
                d.weight = 0;
            });

            frm.refresh_field('issue_items');
        });
    }
});
