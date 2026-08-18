frappe.ui.form.on('YT Receive', {
    setup(frm) {
        apply_yt_receive_queries(
            frm
        );
    },

    refresh(frm) {
        if (!frm.doc.receive_date) {
            frm.set_value(
                'receive_date',
                frappe.datetime.get_today()
            );
        }

        apply_yt_receive_queries(
            frm
        );

        if (frm.doc.yt_issue) {
            load_yt_issue_context(
                frm,
                false
            );
        }

        calculate_yt_receive_totals(
            frm
        );
    },

    yt_issue(frm) {
        if (!frm.doc.yt_issue) {
            frm.clear_table(
                'receive_items'
            );
            frm.refresh_field(
                'receive_items'
            );
            calculate_yt_receive_totals(
                frm
            );
            return;
        }

        load_yt_issue_context(
            frm,
            true
        );
    }
});


frappe.ui.form.on('YT Receive Item', {
    receive_items_add(frm, cdt, cdn) {
        frappe.model.set_value(
            cdt,
            cdn,
            'date',
            frm.doc.receive_date
        );
        frappe.model.set_value(
            cdt,
            cdn,
            'uom',
            'KG'
        );
        calculate_yt_receive_totals(
            frm
        );
    },

    gross_weight(frm, cdt, cdn) {
        calculate_yt_receive_row(
            frm,
            cdt,
            cdn
        );
    },

    baad_weight(frm, cdt, cdn) {
        calculate_yt_receive_row(
            frm,
            cdt,
            cdn
        );
    },

    receive_items_remove(frm) {
        calculate_yt_receive_totals(
            frm
        );
    }
});


function apply_yt_receive_queries(
    frm
) {
    frm.set_query(
        'yt_issue',
        function () {
            return {
                query:
                    'jari_core.jari_core.doctype.yt_receive.yt_receive.yt_issue_query',
                filters: {
                    current_receive:
                        frm.is_new()
                            ? ''
                            : frm.doc.name
                }
            };
        }
    );

    frm.set_query(
        'machine_name',
        'receive_items',
        function () {
            return {
                filters: {
                    department:
                        'YT Department',
                    is_active:
                        1
                }
            };
        }
    );
}


function load_yt_issue_context(
    frm,
    populateRows
) {
    if (!frm.doc.yt_issue) {
        return;
    }

    frappe.call({
        method:
            'jari_core.jari_core.doctype.yt_receive.yt_receive.get_yt_issue_details',
        args: {
            issue_name:
                frm.doc.yt_issue
        },
        callback(r) {
            const data =
                r.message || {};

            frm.set_value(
                'company',
                data.company || ''
            );
            frm.set_value(
                'batch_no',
                data.batch_no || ''
            );
            frm.set_value(
                'process_master',
                data.process_master || ''
            );
            frm.set_value(
                'quality_code',
                data.quality_code || ''
            );

            if (!populateRows) {
                return;
            }

            frm.clear_table(
                'receive_items'
            );

            (data.items || []).forEach(
                item => {
                    const row =
                        frm.add_child(
                            'receive_items'
                        );

                    row.date =
                        frm.doc.receive_date;
                    row.product =
                        item.product;
                    row.uom =
                        'KG';
                    row.machine_name =
                        item.machine_name || '';
                    row.baad_weight =
                        0;
                    row.gross_weight =
                        0;
                    row.net_weight =
                        0;
                }
            );

            frm.refresh_field(
                'receive_items'
            );

            calculate_yt_receive_totals(
                frm
            );
        }
    });
}


async function calculate_yt_receive_row(
    frm,
    cdt,
    cdn
) {
    const row =
        locals[cdt][cdn];

    const gross =
        flt(row.gross_weight);
    const baad =
        flt(row.baad_weight);

    if (
        gross < 0
        || baad < 0
    ) {
        return;
    }

    if (baad > gross) {
        await frappe.model.set_value(
            cdt,
            cdn,
            'net_weight',
            0
        );

        frappe.show_alert({
            message:
                __(
                    'Baad Weight cannot exceed G.W.'
                ),
            indicator:
                'red'
        });

        calculate_yt_receive_totals(
            frm
        );
        return;
    }

    await frappe.model.set_value(
        cdt,
        cdn,
        'net_weight',
        flt(
            gross - baad,
            6
        )
    );

    calculate_yt_receive_totals(
        frm
    );
}


function calculate_yt_receive_totals(
    frm
) {
    const rows =
        frm.doc.receive_items || [];

    const gross = rows.reduce(
        (total, row) =>
            total
            + flt(
                row.gross_weight
            ),
        0
    );

    const baad = rows.reduce(
        (total, row) =>
            total
            + flt(
                row.baad_weight
            ),
        0
    );

    const net = rows.reduce(
        (total, row) =>
            total
            + flt(
                row.net_weight
            ),
        0
    );

    frm.set_value(
        'total_gross_weight',
        flt(
            gross,
            6
        )
    );
    frm.set_value(
        'total_baad_weight',
        flt(
            baad,
            6
        )
    );
    frm.set_value(
        'total_received_weight',
        flt(
            net,
            6
        )
    );
}
