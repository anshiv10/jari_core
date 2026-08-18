frappe.ui.form.on('Gilit Receive', {
    setup(frm) {
        frm.set_query(
            'product',
            'saleable_products',
            function () {
                return {
                    filters: {
                        product_tag: 'JARI'
                    }
                };
            }
        );
    },

    refresh(frm) {
        if (!frm.doc.receive_date) {
            frm.set_value(
                'receive_date',
                frappe.datetime.get_today()
            );
        }

        frm.set_query('gilit_issue', function () {
            return {
                query:
                    'jari_core.jari_core.doctype.gilit_receive.gilit_receive.gilit_issue_query'
            };
        });

        ensure_gilit_saleable_row(frm);
        calculate_gilit_receive_totals(frm);
    },

    gilit_issue(frm) {
        if (!frm.doc.gilit_issue) {
            frm.clear_table('output_items');
            frm.clear_table('saleable_products');
            frm.refresh_field('output_items');
            frm.refresh_field('saleable_products');
            calculate_gilit_receive_totals(frm);
            return;
        }

        frappe.call({
            method: 'frappe.client.get',
            args: {
                doctype: 'Gilit Issue',
                name: frm.doc.gilit_issue
            },
            callback(r) {
                const issue = r.message;

                if (!issue) {
                    return;
                }

                frm.set_value(
                    'company',
                    issue.company
                );

                frm.set_value(
                    'active_batch_no',
                    issue.gilit_batch_no
                );

                frm.set_value(
                    'process_master',
                    issue.process_master
                );

                frm.set_value(
                    'quality_code',
                    issue.quality_code
                );

                frm.set_value(
                    'operator',
                    issue.gilit_karigar ||
                    issue.operator ||
                    ''
                );

                frm.set_value(
                    'total_input_weight',
                    flt(issue.total_net_weight)
                );

                frm.clear_table('output_items');

                const calls = [];

                (issue.peti_items || []).forEach(
                    issuePeti => {
                        if (
                            !issuePeti.spindal_peti_entry
                        ) {
                            return;
                        }

                        calls.push(
                            frappe.db.get_doc(
                                'Spindal Peti Entry',
                                issuePeti.spindal_peti_entry
                            ).then(peti => {
                                const currentBobbin =
                                    cint(
                                        peti.remaining_bobbin ||
                                        peti.bobbin_count ||
                                        peti.nang
                                    );

                                const row =
                                    frm.add_child(
                                        'output_items'
                                    );

                                row.spindal_peti_entry =
                                    peti.name;

                                row.peti_no =
                                    peti.peti_no ||
                                    peti.name;

                                row.total_bobbin =
                                    currentBobbin;

                                row.remaining_bobbin = 0;
                                row.gilit_baad_weight = 0;
                                row.issued_bobbin = 0;

                                row.original_bobbin_count =
                                    cint(
                                        peti.bobbin_count ||
                                        peti.nang
                                    );

                                row.original_remaining_bobbin =
                                    currentBobbin;

                                row.original_gross_weight =
                                    flt(peti.gross_weight);

                                row.original_baad_weight =
                                    flt(peti.baad_weight);

                                row.original_net_weight =
                                    flt(peti.net_weight);

                                row.original_remaining_net_weight =
                                    flt(
                                        peti.remaining_net_weight ||
                                        peti.net_weight
                                    );

                                row.original_status =
                                    peti.status;

                                row.used_net_weight =
                                    flt(
                                        peti.gross_weight
                                    );

                                row.weight =
                                    row.used_net_weight;

                                row.uom =
                                    peti.uom ||
                                    issuePeti.uom ||
                                    'KG';
                            })
                        );
                    }
                );

                Promise.all(calls).then(() => {
                    frm.refresh_field(
                        'output_items'
                    );

                    ensure_gilit_saleable_row(frm);
                    calculate_gilit_receive_totals(
                        frm
                    );
                });
            }
        });
    },

    firki_weight(frm) {
        calculate_gilit_receive_totals(frm);
    },

    gross_weight_without_dabba(frm) {
        calculate_gilit_receive_totals(frm);
    },

    filled_firki(frm) {
        calculate_gilit_receive_totals(frm);
    }
});


frappe.ui.form.on('Gilit Output Item', {
    remaining_bobbin(frm, cdt, cdn) {
        calculate_row_consumption(
            frm,
            cdt,
            cdn
        );
    },

    gilit_baad_weight(frm, cdt, cdn) {
        calculate_row_consumption(
            frm,
            cdt,
            cdn
        );
    },

    product(frm) {
        calculate_gilit_receive_totals(frm);
    },

    output_items_remove(frm) {
        calculate_gilit_receive_totals(frm);
    }
});


frappe.ui.form.on('Gilit Saleable Product Item', {
    product(frm, cdt, cdn) {
        const row = locals[cdt][cdn];

        frappe.model.set_value(
            cdt,
            cdn,
            'uom',
            'KG'
        );

        sync_gilit_saleable_row(frm);

        if (
            row
            && row.product
        ) {
            frappe.db.get_value(
                'Product Master',
                row.product,
                'product_tag'
            ).then(response => {
                const tag =
                    response.message
                    && response.message.product_tag;

                if (tag !== 'JARI') {
                    frappe.model.set_value(
                        cdt,
                        cdn,
                        'product',
                        ''
                    );

                    frappe.msgprint(
                        __('Output Product must have Product Tag JARI.')
                    );
                }
            });
        }
    },

    saleable_products_add(frm) {
        sync_gilit_saleable_row(frm);
    },

    saleable_products_remove(frm) {
        ensure_gilit_saleable_row(frm);
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


function calculate_row_consumption(
    frm,
    cdt,
    cdn
) {
    const row = locals[cdt][cdn];

    const availableBobbin =
        cint(
            row.original_remaining_bobbin ||
            row.total_bobbin
        );

    let remainingBobbin =
        cint(row.remaining_bobbin);

    let gilitBaadWeight =
        flt(row.gilit_baad_weight);

    const originalGross =
        flt(row.original_gross_weight);

    const originalBaad =
        flt(row.original_baad_weight);

    if (remainingBobbin < 0) {
        remainingBobbin = 0;

        frappe.model.set_value(
            cdt,
            cdn,
            'remaining_bobbin',
            0
        );
    }

    if (
        availableBobbin &&
        remainingBobbin > availableBobbin
    ) {
        frappe.msgprint(
            __(
                `Remaining Bobbin cannot exceed ` +
                `${availableBobbin}.`
            )
        );

        remainingBobbin =
            availableBobbin;

        frappe.model.set_value(
            cdt,
            cdn,
            'remaining_bobbin',
            availableBobbin
        );
    }

    if (gilitBaadWeight < 0) {
        gilitBaadWeight = 0;

        frappe.model.set_value(
            cdt,
            cdn,
            'gilit_baad_weight',
            0
        );
    }

    if (
        originalGross &&
        gilitBaadWeight > originalGross
    ) {
        frappe.msgprint(
            __(
                `Gilit Baad Weight cannot exceed ` +
                `Gross Weight ${originalGross} KG.`
            )
        );

        gilitBaadWeight =
            originalGross;

        frappe.model.set_value(
            cdt,
            cdn,
            'gilit_baad_weight',
            originalGross
        );
    }

    if (
        remainingBobbin > 0 &&
        gilitBaadWeight <= originalBaad
    ) {
        frappe.show_alert({
            message: __(
                `For a partial Peti, Gilit Baad ` +
                `Weight must be greater than ` +
                `${originalBaad} KG.`
            ),
            indicator: 'orange'
        });
    }

    const consumedWeight =
        Math.max(
            0,
            originalGross -
            gilitBaadWeight
        );

    frappe.model.set_value(
        cdt,
        cdn,
        'used_net_weight',
        consumedWeight
    );

    frappe.model.set_value(
        cdt,
        cdn,
        'weight',
        consumedWeight
    );

    calculate_gilit_receive_totals(frm);
}


function calculate_gilit_receive_totals(frm) {
    let output = 0;
    let waste = 0;

    (frm.doc.output_items || []).forEach(
        row => {
            output += flt(
                row.used_net_weight
            );
        }
    );

    (frm.doc.waste_items || []).forEach(
        row => {
            waste += flt(row.weight);
        }
    );

    frm.set_value(
        'total_output_weight',
        output
    );

    frm.set_value(
        'total_waste_weight',
        waste
    );

    const rangayelKasab =
        flt(frm.doc.gross_weight_without_dabba)
        - flt(frm.doc.firki_weight);

    frm.set_value(
        'rangayel_kasab_weight',
        rangayelKasab
    );

    const totalJari =
        flt(frm.doc.gross_weight_without_dabba)
        - flt(frm.doc.firki_weight)
        - waste;

    frm.set_value(
        'total_jari_production',
        totalJari
    );

    const oneFirkiWeight =
        flt(frm.doc.filled_firki)
            ? totalJari /
                flt(frm.doc.filled_firki)
            : 0;

    frm.set_value(
        'weight_of_one_firki',
        oneFirkiWeight
    );

    const vadhGhat =
        totalJari
        - flt(frm.doc.total_input_weight)
        + waste;

    frm.set_value(
        'vadh_ghat',
        vadhGhat
    );

    const loss =
        flt(frm.doc.total_input_weight)
        - output
        - waste;

    frm.set_value(
        'loss_weight',
        loss
    );

    const lossPercent =
        flt(frm.doc.total_input_weight)
            ? (
                loss /
                flt(frm.doc.total_input_weight)
            ) * 100
            : 0;

    frm.set_value(
        'loss_percent',
        lossPercent
    );

    sync_gilit_saleable_row(frm);
}


function sync_gilit_saleable_row(frm) {
    const rows =
        frm.doc.saleable_products || [];

    if (!rows.length) {
        return;
    }

    const row = rows[0];
    const filledFirki =
        cint(frm.doc.filled_firki);
    const oneFirkiWeight =
        flt(frm.doc.weight_of_one_firki);
    const totalWeight =
        flt(frm.doc.total_jari_production);

    frappe.model.set_value(
        row.doctype,
        row.name,
        'uom',
        'KG'
    );
    frappe.model.set_value(
        row.doctype,
        row.name,
        'filled_firki',
        filledFirki
    );
    frappe.model.set_value(
        row.doctype,
        row.name,
        'weight_of_one_firki',
        oneFirkiWeight
    );
    frappe.model.set_value(
        row.doctype,
        row.name,
        'marks',
        Math.floor(
            filledFirki / 4
        )
    );
    frappe.model.set_value(
        row.doctype,
        row.name,
        'vadharo_firki',
        filledFirki % 4
    );
    frappe.model.set_value(
        row.doctype,
        row.name,
        'total_weight',
        totalWeight
    );

    frm.refresh_field(
        'saleable_products'
    );
}


async function ensure_gilit_saleable_row(frm) {
    if (!frm.doc.gilit_issue) {
        return;
    }

    if (
        !(frm.doc.saleable_products || []).length
    ) {
        const row = frm.add_child(
            'saleable_products'
        );
        row.uom = 'KG';
        frm.refresh_field(
            'saleable_products'
        );
    }

    const rows =
        frm.doc.saleable_products || [];

    if (
        rows.length !== 1
        || rows[0].product
    ) {
        sync_gilit_saleable_row(frm);
        return;
    }

    try {
        const products =
            await frappe.db.get_list(
                'Product Master',
                {
                    filters: {
                        product_tag: 'JARI'
                    },
                    fields: ['name'],
                    limit: 2
                }
            );

        if (
            products
            && products.length === 1
        ) {
            await frappe.model.set_value(
                rows[0].doctype,
                rows[0].name,
                'product',
                products[0].name
            );
        }
    } catch (error) {
        console.error(
            'Unable to determine default JARI product:',
            error
        );
    }

    sync_gilit_saleable_row(frm);
}
