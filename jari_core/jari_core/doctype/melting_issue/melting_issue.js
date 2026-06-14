frappe.ui.form.on('Melting Issue', {
    refresh(frm) {
        if (!frm.doc.issue_date) {
            frm.set_value('issue_date', frappe.datetime.get_today());
        }
    },

    quality_code(frm) {
        set_silver_purity(frm);
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
                calculate_totals(frm);

                frappe.show_alert({
                    message: 'Melting input products auto-filled',
                    indicator: 'green'
                });
            }
        });
    }
});

frappe.ui.form.on('Melting Issue Item', {
    weight(frm) {
        calculate_totals(frm);
    },

    issue_items_remove(frm) {
        calculate_totals(frm);
    }
});

function set_silver_purity(frm) {
    if (!frm.doc.quality_code) {
        frm.set_value('silver_purity_percent', 0);
        calculate_totals(frm);
        return;
    }

    frappe.db.get_value('Quality Master', frm.doc.quality_code, 'silver_purity_percent')
        .then(r => {
            let purity = 0;
            if (r.message) {
                purity = flt(r.message.silver_purity_percent);
            }

            frm.set_value('silver_purity_percent', purity);
            calculate_totals(frm);
        });
}

function calculate_totals(frm) {
    let total = 0;

    (frm.doc.issue_items || []).forEach(row => {
        total += flt(row.weight);
    });

    frm.set_value('total_issue_weight', total);
}
