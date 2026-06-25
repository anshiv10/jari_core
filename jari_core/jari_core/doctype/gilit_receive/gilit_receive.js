frappe.ui.form.on('Gilit Receive', {
    refresh(frm) {
        if (!frm.doc.receive_date) {
            frm.set_value('receive_date', frappe.datetime.get_today());
        }

        frm.set_query('gilit_issue', function() {
            return {
                filters: {
                    docstatus: 1,
                    status: ['!=', 'Closed']
                }
            };
        });
    },

    gilit_issue(frm) {
        if (!frm.doc.gilit_issue) return;

        frappe.call({
            method: 'frappe.client.get',
            args: {
                doctype: 'Gilit Issue',
                name: frm.doc.gilit_issue
            },
            callback(r) {
                const issue = r.message;
                if (!issue) return;

                frm.set_value('company', issue.company);
                frm.set_value('active_batch_no', issue.gilit_batch_no);
                frm.set_value('process_master', issue.process_master);
                frm.set_value('quality_code', issue.quality_code);
                frm.set_value('operator', issue.operator);
                frm.set_value('total_input_weight', issue.total_net_weight);

                frm.clear_table('output_items');

                (issue.peti_items || []).forEach(peti => {
                    let row = frm.add_child('output_items');

                    let total_bobbin = flt(peti.total_bobbin);
                    let issued_bobbin = flt(peti.issued_bobbin);
                    let used_net_weight = 0;

                    if (total_bobbin && issued_bobbin) {
                        used_net_weight = (flt(peti.net_weight) / total_bobbin) * issued_bobbin / 1000;
                    }

                    row.spindal_peti_entry = peti.spindal_peti_entry;
                    row.peti_no = peti.peti_no;
                    row.total_bobbin = total_bobbin;
                    row.issued_bobbin = issued_bobbin;
                    row.used_net_weight = used_net_weight;
                    row.uom = peti.uom;
                    row.weight = used_net_weight;
                });

                frm.refresh_field('output_items');
                calculate_gilit_receive_totals(frm);
            }
        });
    }
});

frappe.ui.form.on('Gilit Output Item', {
    weight(frm) {
        calculate_gilit_receive_totals(frm);
    },

    output_items_remove(frm) {
        calculate_gilit_receive_totals(frm);
    }
});

frappe.ui.form.on('Gilit Waste Item', {
    weight(frm) {
        calculate_gilit_receive_totals(frm);
    },

    waste_items_remove(frm) {
        calculate_gilit_receive_totals(frm);
    }
});

function calculate_gilit_receive_totals(frm) {
    let output = 0;
    let waste = 0;

    (frm.doc.output_items || []).forEach(row => {
        output += flt(row.weight);
    });

    (frm.doc.waste_items || []).forEach(row => {
        waste += flt(row.weight);
    });

    frm.set_value('total_output_weight', output);
    frm.set_value('total_waste_weight', waste);

    let loss = flt(frm.doc.total_input_weight) - output - waste;
    frm.set_value('loss_weight', loss);

    let loss_percent = flt(frm.doc.total_input_weight) ? loss / flt(frm.doc.total_input_weight) * 100 : 0;
    frm.set_value('loss_percent', loss_percent);
}