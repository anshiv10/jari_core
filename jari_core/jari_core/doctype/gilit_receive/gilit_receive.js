frappe.ui.form.on('Gilit Receive', {
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

        calculate_gilit_receive_totals(frm);
    },

    gilit_issue(frm) {
        if (!frm.doc.gilit_issue) {
            frm.clear_table('output_items');
            frm.refresh_field('output_items');
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
}
