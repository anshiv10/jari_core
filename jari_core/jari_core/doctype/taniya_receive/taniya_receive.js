frappe.ui.form.on('Taniya Receive', {
    refresh(frm) {
        if (!frm.doc.receive_date) {
            frm.set_value('receive_date', frappe.datetime.get_today());
        }

        frm.set_query('taniya_issue', function() {
            return {
                filters: {
                    docstatus: 1,
                    status: ['!=', 'Closed']
                }
            };
        });
    },

    taniya_issue(frm) {
        if (!frm.doc.taniya_issue) return;

        frappe.call({
            method: 'frappe.client.get',
            args: {
                doctype: 'Taniya Issue',
                name: frm.doc.taniya_issue
            },
            callback(r) {
                const issue = r.message;
                if (!issue) return;

                frm.set_value('company', issue.company);
                frm.set_value('batch_no', issue.batch_no);
                frm.set_value('process_master', issue.process_master);
                frm.set_value('quality_code', issue.quality_code);
                frm.set_value('operator', issue.operator);
                frm.set_value('total_input_weight', issue.total_issue_weight);

                frappe.call({
                    method: 'frappe.client.get',
                    args: {
                        doctype: 'Process Master',
                        name: issue.process_master
                    },
                    callback(pr) {
                        const p = pr.message;
                        if (!p) return;

                        frm.clear_table('output_items');
                        frm.clear_table('waste_items');

                        (p.output_products || []).forEach(row => {
                            let d = frm.add_child('output_items');
                            d.product = row.product;
                            d.uom = row.uom;
                        });

                        (p.custom_waste_product_items || []).forEach(row => {
                            let d = frm.add_child('waste_items');
                            d.waste_product = row.waste_product;
                            d.uom = row.uom;
                        });

                        frm.refresh_field('output_items');
                        frm.refresh_field('waste_items');

                        frappe.show_alert({
                            message: 'Taniya output and waste products auto-filled',
                            indicator: 'green'
                        });
                    }
                });
            }
        });
    }
});
