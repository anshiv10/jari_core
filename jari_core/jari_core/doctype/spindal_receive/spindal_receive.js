frappe.ui.form.on('Spindal Receive', {
    refresh(frm) {
        if (!frm.doc.receive_date && frm.doc.docstatus === 0) {
            frm.set_value(
                'receive_date',
                frappe.datetime.get_today()
            );
        }

        frm.set_query('spindal_issue', function() {
            return {
                query: 'jari_core.jari_core.doctype.spindal_receive.spindal_receive.spindal_issue_query'
            };
        });

        if (frm.doc.docstatus === 0) {
            calculate_spindal_loss(frm);
        }
    },

    spindal_issue(frm) {
        if (!frm.doc.spindal_issue) {
            return;
        }

        frappe.call({
            method: 'jari_core.jari_core.doctype.spindal_receive.spindal_receive.get_spindal_receive_data',
            args: {
                spindal_issue: frm.doc.spindal_issue
            },
            callback(r) {
                const data = r.message;

                if (!data) {
                    return;
                }

                frm.set_value('company', data.company);
                frm.set_value(
                    'active_batch_no',
                    data.active_batch_no
                );
                frm.set_value(
                    'process_master',
                    data.process_master
                );
                frm.set_value(
                    'quality_code',
                    data.quality_code
                );
                frm.set_value(
                    'operator',
                    data.operator
                );
                frm.set_value(
                    'total_input_weight',
                    data.total_input_weight
                );

                frm.clear_table('received_peti_items');

                (data.petis || []).forEach(p => {
                    const d = frm.add_child(
                        'received_peti_items'
                    );

                    d.peti_no = p.name;
                    d.product = data.kasab_product;
                    d.uom = p.uom || 'KG';
                    d.gross_weight = p.gross_weight;
                    d.net_weight = p.net_weight;
                });

                frm.refresh_field(
                    'received_peti_items'
                );

                calculate_spindal_loss(frm);
            }
        });
    },

    total_input_weight(frm) {
        calculate_spindal_loss(frm);
    }
});


frappe.ui.form.on('Spindal Receive Peti Item', {
    net_weight(frm) {
        calculate_spindal_loss(frm);
    },

    uom(frm) {
        calculate_spindal_loss(frm);
    },

    received_peti_items_add(frm) {
        calculate_spindal_loss(frm);
    },

    received_peti_items_remove(frm) {
        calculate_spindal_loss(frm);
    }
});


frappe.ui.form.on('Spindal Waste Item', {
    waste_items_add(frm, cdt, cdn) {
        frappe.model.set_value(
            cdt,
            cdn,
            'uom',
            'gram'
        );

        calculate_spindal_loss(frm);
    },

    weight(frm) {
        calculate_spindal_loss(frm);
    },

    uom(frm) {
        calculate_spindal_loss(frm);
    },

    waste_items_remove(frm) {
        calculate_spindal_loss(frm);
    }
});


function weight_to_grams(weight, uom) {
    const value = flt(weight);
    const unit = (uom || '').trim().toLowerCase();

    const gram_units = [
        'gm',
        'gram',
        'grams',
        'g'
    ];

    const kg_units = [
        'kg',
        'kilogram',
        'kilograms',
        'kgs'
    ];

    if (gram_units.includes(unit)) {
        return value;
    }

    if (kg_units.includes(unit)) {
        return value * 1000;
    }

    // Legacy Spindal Receive child rows are gram based.
    return value;
}


function calculate_spindal_loss(frm) {
    if (frm.doc.docstatus !== 0) {
        return;
    }

    // Spindal Issue input quantity is stored in KG.
    const total_input_gm =
        flt(frm.doc.total_input_weight) * 1000;

    let total_received_gm = 0;

    (frm.doc.received_peti_items || []).forEach(row => {
        total_received_gm += weight_to_grams(
            row.net_weight,
            row.uom
        );
    });

    let total_waste_gm = 0;

    (frm.doc.waste_items || []).forEach(row => {
        total_waste_gm += weight_to_grams(
            row.weight,
            row.uom
        );
    });

    const accounted_weight_gm =
        total_received_gm + total_waste_gm;

    const loss_weight_gm =
        total_input_gm - accounted_weight_gm;

    const loss_percent =
        total_input_gm > 0
            ? (
                loss_weight_gm
                / total_input_gm
                * 100
            )
            : 0;

    frm.set_value(
        'total_received_weight',
        total_received_gm
    );

    frm.set_value(
        'total_waste_weight',
        total_waste_gm
    );

    frm.set_value(
        'loss_weight',
        loss_weight_gm
    );

    frm.set_value(
        'loss_percent',
        loss_percent
    );

    const standard =
        flt(frm.doc.loss_standard_percent);

    frm.set_value(
        'loss_status',
        loss_percent > standard
            ? 'Excess Loss'
            : 'OK'
    );
}
