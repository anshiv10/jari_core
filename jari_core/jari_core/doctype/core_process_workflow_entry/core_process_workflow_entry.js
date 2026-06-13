frappe.ui.form.on('Core Process Workflow Entry', {
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

                frm.set_value('department', p.department);
                frm.set_value('flow_type', p.flow_type);
                frm.set_value('is_outsourced', p.is_outsourced);

                frm.clear_table('input_products');
                frm.clear_table('output_products');
                frm.clear_table('waste_products');

                (p.input_products || []).forEach(row => {
                    let d = frm.add_child('input_products');
                    d.product = row.product;
                    d.uom = row.uom;
                    d.is_mandatory = row.is_mandatory;
                    d.silver_bearing = row.silver_bearing;
                });

                (p.output_products || []).forEach(row => {
                    let d = frm.add_child('output_products');
                    d.product = row.product;
                    d.uom = row.uom;
                    d.is_primary = row.is_primary;
                });

                (p.waste_products || []).forEach(row => {
                    let d = frm.add_child('waste_products');
                    d.waste_type = row.waste_type;
                    d.uom = row.uom;
                    d.expected_percent = row.expected_percent;
                });

                frm.refresh_field('input_products');
                frm.refresh_field('output_products');
                frm.refresh_field('waste_products');

                frappe.show_alert({
                    message: 'Process details auto-filled from Process Master',
                    indicator: 'green'
                });
            }
        });
    }
});