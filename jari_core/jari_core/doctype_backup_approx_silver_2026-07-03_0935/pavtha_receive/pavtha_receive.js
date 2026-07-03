frappe.ui.form.on('Pavtha Receive', {
    refresh(frm) {
        if (!frm.doc.receive_date) {
            frm.set_value('receive_date', frappe.datetime.get_today());
        }

        frm.set_query('pavtha_issue', function() {
            return {
                query: 'jari_core.jari_core.doctype.pavtha_receive.pavtha_receive.pavtha_issue_query'
            };
        });
    },

    pavtha_issue(frm) {
        if (!frm.doc.pavtha_issue) return;

        frappe.call({
            method: 'frappe.client.get',
            args: {
                doctype: 'Pavtha Issue',
                name: frm.doc.pavtha_issue
            },
            callback(r) {
                const issue = r.message;
                if (!issue) return;

                frm.set_value('company', issue.company);
                frm.set_value('batch_no', issue.batch_no);
                frm.set_value('process_master', issue.process_master);
                frm.set_value('quality_code', issue.quality_code);
                frm.set_value('outsourcer', issue.outsourcer);
                frm.set_value('rate_per_kg', issue.rate_per_kg);
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
                            message: 'Pavtha output and waste products auto-filled',
                            indicator: 'green'
                        });
                    }
                });
            }
        });
    }
});
