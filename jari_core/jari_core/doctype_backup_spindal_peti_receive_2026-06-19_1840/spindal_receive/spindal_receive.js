frappe.ui.form.on('Spindal Receive', {
    refresh(frm) {
        if (!frm.doc.receive_date) {
            frm.set_value('receive_date', frappe.datetime.get_today());
        }

        frm.set_query('spindal_issue', function() {
            return {
                filters: {
                    docstatus: 1,
                    status: ['!=', 'Closed'],
                    is_active_batch: 1
                }
            };
        });
    },

    spindal_issue(frm) {
        if (!frm.doc.spindal_issue) return;

        frappe.call({
            method: 'frappe.client.get',
            args: {
                doctype: 'Spindal Issue',
                name: frm.doc.spindal_issue
            },
            callback(r) {
                const issue = r.message;
                if (!issue) return;

                frm.set_value('company', issue.company);
                frm.set_value('active_batch_no', issue.active_batch_no);
                frm.set_value('process_master', issue.process_master);
                frm.set_value('quality_code', issue.quality_code);
                frm.set_value('operator', issue.operator);
                frm.set_value('total_input_weight', issue.total_net_weight);

                frm.clear_table('received_peti_items');

                (issue.peti_items || []).forEach(row => {
                    let d = frm.add_child('received_peti_items');
                    d.peti_no = row.peti_no;
                    d.product = row.product;
                    d.uom = row.uom;
                    d.gross_weight = row.gross_weight;
                    d.net_weight = row.net_weight;
                });

                frm.refresh_field('received_peti_items');
                calculate_spindal_receive_totals(frm);
            }
        });
    }
});

frappe.ui.form.on('Spindal Receive Peti Item', {
    net_weight(frm) {
        calculate_spindal_receive_totals(frm);
    },

    received_peti_items_remove(frm) {
        calculate_spindal_receive_totals(frm);
    }
});

frappe.ui.form.on('Spindal Waste Item', {
    weight(frm) {
        calculate_spindal_receive_totals(frm);
    },

    waste_items_remove(frm) {
        calculate_spindal_receive_totals(frm);
    }
});

function calculate_spindal_receive_totals(frm) {
    let received = 0;
    let waste = 0;

    (frm.doc.received_peti_items || []).forEach(row => {
        received += flt(row.net_weight);
    });

    (frm.doc.waste_items || []).forEach(row => {
        waste += flt(row.weight);
    });

    frm.set_value('total_received_weight', received);
    frm.set_value('total_waste_weight', waste);

    let loss = flt(frm.doc.total_input_weight) - received - waste;
    frm.set_value('loss_weight', loss);

    let loss_percent = flt(frm.doc.total_input_weight) ? loss / flt(frm.doc.total_input_weight) * 100 : 0;
    frm.set_value('loss_percent', loss_percent);
}
