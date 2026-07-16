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
                frm.set_value(
                    'issue_receive_type',
                    issue.issue_receive_type || 'In-house'
                );
                frm.set_value('process_master', issue.process_master);
                frm.set_value('quality_code', issue.quality_code);
                frm.set_value('outsourcer', issue.outsourcer);
                frm.set_value('total_input_weight', issue.total_issue_weight);

                if (issue.outsourcer) {
                    frappe.db.get_value(
                        'Jobworker Master',
                        issue.outsourcer,
                        ['rate_per_kg', 'standard_loss_percent']
                    ).then(r => {
                        const values = r.message || {};

                        frm.set_value(
                            'rate_per_kg',
                            flt(values.rate_per_kg)
                        );

                        frm.set_value(
                            'loss_standard_percent',
                            flt(values.standard_loss_percent)
                        );
                    });
                } else {
                    frm.set_value('rate_per_kg', 0);
                }

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


frappe.ui.form.on('Pavtha Output Item', {
    weight(frm) {
        calculate_pavtha_preview(frm);
    },

    output_items_remove(frm) {
        calculate_pavtha_preview(frm);
    }
});


frappe.ui.form.on('Pavtha Waste Item', {
    weight(frm) {
        calculate_pavtha_preview(frm);
    },

    waste_items_remove(frm) {
        calculate_pavtha_preview(frm);
    }
});


function calculate_pavtha_preview(frm) {
    const input = flt(frm.doc.total_input_weight);

    const output = (frm.doc.output_items || []).reduce(
        (total, row) => total + flt(row.weight),
        0
    );

    const waste = (frm.doc.waste_items || []).reduce(
        (total, row) => total + flt(row.weight),
        0
    );

    const loss = input - output - waste;
    const lossPercent = input ? (loss / input) * 100 : 0;
    const wastePercent = input ? (waste / input) * 100 : 0;

    const rate = flt(frm.doc.rate_per_kg);
    const standardLoss = flt(frm.doc.loss_standard_percent);

    const basePayout = input * rate;
    const variancePercent = lossPercent - standardLoss;

    let bonus = 0;
    let deduction = 0;

    if (variancePercent > 0) {
        const excessWeight = input * variancePercent / 100;
        deduction = excessWeight * rate;
    } else if (variancePercent < 0) {
        const savedWeight = input * Math.abs(variancePercent) / 100;
        bonus = savedWeight * rate;
    }

    const suggestion = basePayout + bonus - deduction;

    frm.set_value('total_output_weight', output);
    frm.set_value('total_waste_weight', waste);
    frm.set_value('loss_weight', loss);
    frm.set_value('loss_percent', lossPercent);
    frm.set_value('waste_percent', wastePercent);
    frm.set_value('base_payout', basePayout);
    frm.set_value('bonus_amount', bonus);
    frm.set_value('deduction_amount', deduction);
    frm.set_value('payout_suggestion', suggestion);

    if (!flt(frm.doc.payout_given)) {
        frm.set_value('payout_given', suggestion);
    }

    frm.set_value(
        'loss_status',
        lossPercent > standardLoss ? 'Excess Loss' : 'OK'
    );
}
