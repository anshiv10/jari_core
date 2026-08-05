
frappe.ui.form.on('Asarva Receive', {
    refresh(frm) {
        if (!frm.doc.receive_date) {
            frm.set_value(
                'receive_date',
                frappe.datetime.get_today()
            );
        }

        frm.set_query(
            'asarva_issue',
            function () {
                return {
                    query:
                        'jari_core.jari_core.doctype.asarva_receive.asarva_receive.asarva_issue_query'
                };
            }
        );

        calculate_asarva_receive_totals(frm);
    },

    asarva_issue(frm) {
        if (!frm.doc.asarva_issue) {
            frm.clear_table('receive_items');
            frm.refresh_field('receive_items');
            calculate_asarva_receive_totals(frm);
            return;
        }

        frappe.call({
            method:
                'jari_core.jari_core.doctype.asarva_receive.asarva_receive.get_asarva_issue_details',
            args: {
                issue_name:
                    frm.doc.asarva_issue
            },
            callback(r) {
                const data = r.message || {};

                frm.set_value(
                    'company',
                    data.company || ''
                );

                frm.set_value(
                    'asarva_outsourcer',
                    data.asarva_outsourcer || ''
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

                frm.clear_table('receive_items');

                (data.items || []).forEach(item => {
                    const row = frm.add_child(
                        'receive_items'
                    );

                    row.source_issue_item =
                        item.source_issue_item;

                    row.product = item.product;

                    row.product_quality =
                        item.product_quality;

                    row.colour = item.colour;

                    row.issued_weight =
                        flt(item.issued_weight);

                    row.quantity_firka = 0;
                    row.gross_weight = 0;
                    row.baad_weight = 0;
                    row.received_weight = 0;
                    row.uom = item.uom || 'KG';
                });

                frm.refresh_field(
                    'receive_items'
                );

                calculate_asarva_receive_totals(
                    frm
                );
            }
        });
    }
});


frappe.ui.form.on('Asarva Receive Item', {
    gross_weight(frm, cdt, cdn) {
        calculate_asarva_receive_row(
            frm,
            cdt,
            cdn
        );
    },

    baad_weight(frm, cdt, cdn) {
        calculate_asarva_receive_row(
            frm,
            cdt,
            cdn
        );
    },

    receive_items_remove(frm) {
        calculate_asarva_receive_totals(frm);
    }
});


async function calculate_asarva_receive_row(
    frm,
    cdt,
    cdn
) {
    const row = locals[cdt][cdn];

    const gross = flt(row.gross_weight);
    const baad = flt(row.baad_weight);

    if (gross < 0 || baad < 0) {
        frappe.show_alert({
            message: __(
                'G.W and Baad cannot be negative.'
            ),
            indicator: 'red'
        });

        return;
    }

    if (baad > gross) {
        await frappe.model.set_value(
            cdt,
            cdn,
            'received_weight',
            0
        );

        frappe.show_alert({
            message: __(
                'Baad cannot exceed G.W.'
            ),
            indicator: 'red'
        });

        return;
    }

    await frappe.model.set_value(
        cdt,
        cdn,
        'received_weight',
        flt(gross - baad, 3)
    );

    calculate_asarva_receive_totals(frm);
}


function calculate_asarva_receive_totals(frm) {
    const rows =
        frm.doc.receive_items || [];

    const gross = rows.reduce(
        (total, row) =>
            total + flt(row.gross_weight),
        0
    );

    const baad = rows.reduce(
        (total, row) =>
            total + flt(row.baad_weight),
        0
    );

    const received = rows.reduce(
        (total, row) =>
            total + flt(row.received_weight),
        0
    );

    frm.set_value(
        'total_gross_weight',
        flt(gross, 3)
    );

    frm.set_value(
        'total_baad_weight',
        flt(baad, 3)
    );

    frm.set_value(
        'total_received_weight',
        flt(received, 3)
    );
}
