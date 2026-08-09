console.log("Taniya Receive JS Loaded Successfully");

frappe.ui.form.on('Taniya Receive', {
    refresh(frm) {
        if (!frm.doc.receive_date) {
            frm.set_value('receive_date', frappe.datetime.get_today());
        }

        frm.set_query('taniya_issue', function() {
            return {
                query: 'jari_core.jari_core.doctype.taniya_receive.taniya_receive.taniya_issue_query'
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

                frappe.call({
                    method: 'frappe.client.get_list',
                    args: {
                        doctype: 'Taniya Issue',
                        filters: {
                            batch_no: issue.batch_no,
                            docstatus: ['in', [0, 1]]
                        },
                        fields: ['name', 'total_issue_weight'],
                        limit_page_length: 500
                    },
                    callback(ir) {
                        let total = 0;
                        (ir.message || []).forEach(x => {
                            total += flt(x.total_issue_weight);
                        });
                        frm.set_value('total_input_weight', total);
                    }
                });

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

                        /*
                         * Prevent manual-row copy logic from running while
                         * Process Master rows are being generated.
                         */
                        frm.__loading_taniya_process_rows = true;

                        (p.output_products || []).forEach(row => {
                            let product = row.product || row.product_code || row.item || row.item_code || row.output_product;
                            let d = frm.add_child('output_items');
                            d.receive_date = frm.doc.receive_date || frappe.datetime.get_today();
                            d.operator_name = frm.doc.operator;
                            d.product = product;
                            d.product_name = row.product_name || product;
                            d.uom = row.uom || row.unit || 'KG';
                            d.quantity = 0;
                            d.baad_weight = 0;
                            d.net_weight = 0;
                        });

                        (p.custom_waste_product_items || []).forEach(row => {
                            let waste_product = row.waste_product || row.product || row.product_code || row.item || row.item_code;
                            let d = frm.add_child('waste_items');
                            d.receive_date = frm.doc.receive_date || frappe.datetime.get_today();
                            d.operator_name = frm.doc.operator;
                            d.waste_product = waste_product;
                            d.product_name = row.product_name || waste_product;
                            d.uom = row.uom || row.unit || 'KG';
                        });

                        frm.__loading_taniya_process_rows = false;

                        frm.refresh_field('output_items');
                        frm.refresh_field('waste_items');
                        set_all_product_names(frm);
                    }
                });
            }
        });
    }
});

frappe.ui.form.on('Taniya Output Item', {
    async output_items_add(frm, cdt, cdn) {
        if (frm.__loading_taniya_process_rows) {
            return;
        }

        const previousRow = get_previous_child_row(
            frm,
            'output_items',
            cdn
        );

        if (previousRow) {
            await set_child_values(cdt, cdn, {
                operator_name: previousRow.operator_name,
                receive_date: previousRow.receive_date,
                product: previousRow.product,
                product_name: previousRow.product_name,
                uom: previousRow.uom,
                quantity: 0,
                weight: 0,
                baad_weight: 0,
                net_weight: 0,
                baad_weight_details: '[]',
                approx_silver_weight: 0
            });
        } else {
            await set_child_values(cdt, cdn, {
                receive_date:
                    frm.doc.receive_date ||
                    frappe.datetime.get_today(),
                operator_name: frm.doc.operator,
                quantity: 0,
                weight: 0,
                baad_weight: 0,
                net_weight: 0,
                baad_weight_details: '[]',
                approx_silver_weight: 0
            });
        }
    },

    product(frm, cdt, cdn) {
        set_product_name(cdt, cdn, 'product');
    }
});

frappe.ui.form.on('Taniya Waste Item', {
    async waste_items_add(frm, cdt, cdn) {
        if (frm.__loading_taniya_process_rows) {
            return;
        }

        const previousRow = get_previous_child_row(
            frm,
            'waste_items',
            cdn
        );

        if (previousRow) {
            await set_child_values(cdt, cdn, {
                operator_name: previousRow.operator_name,
                receive_date: previousRow.receive_date,
                waste_product: previousRow.waste_product,
                product_name: previousRow.product_name,
                uom: previousRow.uom,
                quantity: 0,
                weight: 0,
                baad_weight: 0,
                net_weight: 0,
                approx_silver_weight: 0
            });
        } else {
            await set_child_values(cdt, cdn, {
                receive_date:
                    frm.doc.receive_date ||
                    frappe.datetime.get_today(),
                operator_name: frm.doc.operator,
                quantity: 0,
                weight: 0,
                baad_weight: 0,
                net_weight: 0,
                approx_silver_weight: 0
            });
        }
    },

    waste_product(frm, cdt, cdn) {
        set_product_name(cdt, cdn, 'waste_product');
    }
});


function get_previous_child_row(
    frm,
    tableFieldname,
    currentRowName
) {
    const rows = frm.doc[tableFieldname] || [];

    const currentIndex = rows.findIndex(
        row => row.name === currentRowName
    );

    if (currentIndex <= 0) {
        return null;
    }

    return rows[currentIndex - 1];
}


async function set_child_values(
    cdt,
    cdn,
    values
) {
    for (const [fieldname, value] of Object.entries(values)) {
        await frappe.model.set_value(
            cdt,
            cdn,
            fieldname,
            value ?? null
        );
    }
}


function set_all_product_names(frm) {
    (frm.doc.output_items || []).forEach(row => {
        if (row.product) set_product_name(row.doctype, row.name, 'product');
    });

    (frm.doc.waste_items || []).forEach(row => {
        if (row.waste_product) set_product_name(row.doctype, row.name, 'waste_product');
    });
}

function set_product_name(cdt, cdn, product_field) {
    let row = locals[cdt][cdn];
    let product = row[product_field];

    if (!product) {
        frappe.model.set_value(cdt, cdn, 'product_name', '');
        return;
    }

    frappe.db.get_value('Product Master', product, 'product_name').then(r => {
        frappe.model.set_value(cdt, cdn, 'product_name', (r.message && r.message.product_name) || product);
    });
}

/*
 * ============================================================
 * TANIYA OUTPUT PIECE-WISE BAAD WEIGHT
 * ============================================================
 */

frappe.ui.form.on('Taniya Output Item', {
    quantity(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        const quantity = cint(row.quantity);

        if (quantity < 0) {
            frappe.model.set_value(
                cdt,
                cdn,
                'quantity',
                0
            );

            frappe.msgprint(
                __('Quantity cannot be negative.')
            );

            return;
        }

        if (quantity > 0) {
            show_taniya_baad_weight_dialog(
                frm,
                cdt,
                cdn
            );
        }
    },

    weight(frm, cdt, cdn) {
        calculate_taniya_output_net_weight(
            frm,
            cdt,
            cdn
        );
    },

    baad_weight(frm, cdt, cdn) {
        calculate_taniya_output_net_weight(
            frm,
            cdt,
            cdn
        );
    },

    edit_baad_weight(frm, cdt, cdn) {
        show_taniya_baad_weight_dialog(
            frm,
            cdt,
            cdn
        );
    },

    output_items_remove(frm) {
        calculate_taniya_output_totals(frm);
    }
});


function show_taniya_baad_weight_dialog(
    frm,
    cdt,
    cdn
) {
    const row = locals[cdt][cdn];

    if (!row) {
        frappe.msgprint(
            __('Unable to locate the selected output row.')
        );
        return;
    }

    const quantity = cint(row.quantity);

    if (quantity <= 0) {
        frappe.msgprint(
            __('Please enter Quantity greater than zero first.')
        );
        return;
    }

    const existingWeights =
        get_taniya_baad_weight_entries(row);

    const normalizedWeights =
        normalize_taniya_baad_weight_entries(
            existingWeights,
            quantity
        );

    const fields = [];

    /*
     * Summary of the selected row.
     */
    fields.push({
        fieldname: 'information',
        fieldtype: 'HTML',
        options: `
            <div class="alert alert-info">
                <strong>${__('Product')}:</strong>
                ${frappe.utils.escape_html(
                    row.product_name ||
                    row.product ||
                    ''
                )}
                &nbsp; | &nbsp;

                <strong>${__('Quantity')}:</strong>
                ${quantity}
                &nbsp; | &nbsp;

                <strong>${__('UOM')}:</strong>
                ${frappe.utils.escape_html(
                    row.uom || ''
                )}
            </div>
        `
    });

    /*
     * Client requested editable Received Weight inside popup.
     */
    fields.push({
        fieldname: 'received_weight',
        fieldtype: 'Float',
        label: __('Received Weight'),
        reqd: 1,
        default: flt(row.weight),
        precision: 3,
        description: __(
            'Edit the total received weight for this output row.'
        )
    });

    fields.push({
        fieldname: 'baad_section',
        fieldtype: 'Section Break',
        label: __('Piece-wise Baad Weight')
    });

    /*
     * Generate one Baad Weight field per Quantity.
     */
    for (
        let pieceNumber = 1;
        pieceNumber <= quantity;
        pieceNumber += 1
    ) {
        fields.push({
            fieldname:
                `piece_weight_${pieceNumber}`,

            fieldtype: 'Float',

            label: __(
                'Piece {0} Baad Weight',
                [pieceNumber]
            ),

            reqd: 1,

            default: flt(
                normalizedWeights[
                    pieceNumber - 1
                ]
            ),

            precision: 3
        });
    }

    const dialog = new frappe.ui.Dialog({
        title: __('Edit Weight'),

        size:
            quantity > 8
                ? 'large'
                : 'small',

        fields,

        primary_action_label:
            __('Apply Weight'),

        async primary_action(values) {

            const receivedWeight =
                flt(values.received_weight);

            /*
             * Received Weight validation.
             */
            if (receivedWeight <= 0) {
                frappe.msgprint(
                    __(
                        'Received Weight must be greater than zero.'
                    )
                );
                return;
            }


            let totalBaadWeight = 0;
            const pieceWeights = [];

            /*
             * Validate and total every individual
             * Baad Weight entry.
             */
            for (
                let pieceNumber = 1;
                pieceNumber <= quantity;
                pieceNumber += 1
            ) {
                const value = flt(
                    values[
                        `piece_weight_${pieceNumber}`
                    ]
                );

                if (value < 0) {
                    frappe.msgprint(
                        __(
                            'Baad Weight cannot be negative ' +
                            'for Piece {0}.',
                            [pieceNumber]
                        )
                    );
                    return;
                }

                pieceWeights.push(
                    flt(value, 3)
                );

                totalBaadWeight += value;
            }


            totalBaadWeight =
                flt(totalBaadWeight, 3);


            /*
             * Baad cannot exceed Received Weight.
             */
            if (
                totalBaadWeight >
                receivedWeight
            ) {
                frappe.msgprint({
                    title:
                        __('Invalid Weight'),

                    indicator:
                        'red',

                    message:
                        __(
                            'Total Baad Weight {0} cannot exceed ' +
                            'Received Weight {1}.',
                            [
                                format_number(
                                    totalBaadWeight,
                                    null,
                                    3
                                ),
                                format_number(
                                    receivedWeight,
                                    null,
                                    3
                                )
                            ]
                        )
                });

                return;
            }


            const netWeight =
                flt(
                    receivedWeight -
                    totalBaadWeight,
                    3
                );


            if (netWeight <= 0) {
                frappe.msgprint({
                    title:
                        __('Invalid Net Weight'),

                    indicator:
                        'red',

                    message:
                        __(
                            'N.W (DATA) must be greater than zero.'
                        )
                });

                return;
            }


            /*
             * Save all values back to the child row.
             *
             * These values are validated again by Python
             * during Save/Submit, so JS is not the sole
             * calculation authority.
             */

            await frappe.model.set_value(
                cdt,
                cdn,
                'baad_weight_details',
                JSON.stringify(
                    pieceWeights
                )
            );

            await frappe.model.set_value(
                cdt,
                cdn,
                'weight',
                flt(
                    receivedWeight,
                    3
                )
            );

            await frappe.model.set_value(
                cdt,
                cdn,
                'baad_weight',
                totalBaadWeight
            );

            await frappe.model.set_value(
                cdt,
                cdn,
                'net_weight',
                netWeight
            );


            frm.refresh_field(
                'output_items'
            );

            calculate_taniya_output_totals(
                frm
            );

            dialog.hide();

            frappe.show_alert({
                message: __(
                    'Received Weight, Baad Weight and ' +
                    'N.W (DATA) updated successfully.'
                ),
                indicator: 'green'
            });
        }
    });


    dialog.show();
}



function get_taniya_baad_weight_entries(row) {
    const rawValue =
        row.baad_weight_details;

    if (!rawValue) {
        return [];
    }

    try {
        const parsed =
            typeof rawValue === 'string'
                ? JSON.parse(rawValue)
                : rawValue;

        if (!Array.isArray(parsed)) {
            return [];
        }

        return parsed.map(
            value => flt(value)
        );
    } catch (error) {
        console.error(
            'Invalid Baad Weight Details JSON:',
            error
        );

        return [];
    }
}


function normalize_taniya_baad_weight_entries(
    existingWeights,
    quantity
) {
    const normalized =
        Array.isArray(existingWeights)
            ? existingWeights.slice(0, quantity)
            : [];

    while (normalized.length < quantity) {
        normalized.push(0);
    }

    return normalized;
}


async function calculate_taniya_output_net_weight(
    frm,
    cdt,
    cdn
) {
    const row = locals[cdt][cdn];

    const receivedWeight =
        flt(row.weight);

    const baadWeight =
        flt(row.baad_weight);

    if (baadWeight > receivedWeight) {
        await frappe.model.set_value(
            cdt,
            cdn,
            'net_weight',
            0
        );

        frappe.show_alert({
            message: __(
                'Baad Weight cannot exceed Received Weight.'
            ),
            indicator: 'red'
        });

        return;
    }

    await frappe.model.set_value(
        cdt,
        cdn,
        'net_weight',
        flt(
            receivedWeight - baadWeight,
            3
        )
    );

    calculate_taniya_output_totals(frm);
}


function calculate_taniya_output_totals(frm) {
    const outputTotal = (
        frm.doc.output_items || []
    ).reduce(
        (total, row) =>
            total + flt(row.net_weight),
        0
    );

    const wasteTotal = (
        frm.doc.waste_items || []
    ).reduce(
        (total, row) =>
            total + flt(row.weight),
        0
    );

    const inputWeight =
        flt(frm.doc.total_input_weight);

    frm.set_value(
        'total_output_weight',
        flt(outputTotal, 3)
    );

    frm.set_value(
        'total_waste_weight',
        flt(wasteTotal, 3)
    );

    frm.set_value(
        'current_wastage_percent',
        inputWeight
            ? wasteTotal / inputWeight * 100
            : 0
    );

    const lossWeight =
        inputWeight
        - outputTotal
        - wasteTotal;

    frm.set_value(
        'loss_weight',
        flt(lossWeight, 3)
    );

    frm.set_value(
        'loss_percent',
        inputWeight
            ? lossWeight / inputWeight * 100
            : 0
    );
}
