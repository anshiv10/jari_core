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
                frm.clear_table('custom_waste_product_items');

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

                (p.custom_waste_product_items || []).forEach(row => {
                    let d = frm.add_child('custom_waste_product_items');
                    d.waste_product = row.waste_product;
                    d.uom = row.uom;
                    d.expected_percent = row.expected_percent;
                    d.silver_bearing = row.silver_bearing;
                    d.gold_bearing = row.gold_bearing;
                });

                frm.refresh_field('input_products');
                frm.refresh_field('output_products');
                frm.refresh_field('waste_products');
                frm.refresh_field('custom_waste_product_items');

                frappe.show_alert({
                    message: 'Process details auto-filled from Product Master based Process Configuration',
                    indicator: 'green'
                });
            }
        });
    }
});