frappe.ui.form.on('Asarva Receive', {

    setup(frm) {
        apply_asarva_issue_query(frm);
        apply_receive_product_query(frm);
    },

    refresh(frm) {
        if (!frm.doc.receive_date) {
            frm.set_value(
                'receive_date',
                frappe.datetime.get_today()
            );
        }

        apply_asarva_issue_query(frm);

        /*
         * When opening an existing Receive,
         * load Issue context only.
         *
         * Do NOT recreate its Receive rows.
         */
        if (frm.doc.asarva_issue) {
            load_asarva_issue_context(
                frm,
                false
            );
        }

        calculate_asarva_receive_totals(frm);
    },

    asarva_issue(frm) {
        if (!frm.doc.asarva_issue) {

            frm.__asarva_issue_items = [];

            frm.clear_table(
                'receive_items'
            );

            frm.refresh_field(
                'receive_items'
            );

            calculate_asarva_receive_totals(
                frm
            );

            return;
        }

        /*
         * Selecting an Issue initially creates
         * convenient starting rows.
         *
         * It does NOT limit how many Receive rows
         * the user may add afterwards.
         */
        load_asarva_issue_context(
            frm,
            true
        );
    }
});


frappe.ui.form.on('Asarva Receive Item', {

    receive_items_add(frm, cdt, cdn) {
        const row = locals[cdt][cdn];

        frappe.model.set_value(
            cdt,
            cdn,
            'uom',
            'KG'
        );

        /*
         * Convenience:
         *
         * If the Issue contains only one source product,
         * an additional Receive row automatically gets
         * that source information.
         *
         * If there are multiple Issue products, we do
         * NOT guess. User selects Product manually.
         */
        const sourceItems =
            frm.__asarva_issue_items || [];

        if (sourceItems.length === 1) {
            apply_source_item_to_row(
                frm,
                row,
                sourceItems[0]
            );
        }

        calculate_asarva_receive_totals(frm);
    },

    product(frm, cdt, cdn) {
        const row = locals[cdt][cdn];

        if (!row.product) {
            return;
        }

        const sourceItems =
            (
                frm.__asarva_issue_items || []
            ).filter(
                item =>
                    item.product === row.product
            );

        /*
         * If this Product exists only once in the
         * original Issue, safely copy its reference
         * details.
         *
         * If the same Product exists multiple times,
         * do not make an unsafe assumption.
         */
        if (sourceItems.length === 1) {
            apply_source_item_to_row(
                frm,
                row,
                sourceItems[0]
            );
        }
    },

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

    quantity_firka(frm) {
        calculate_asarva_receive_totals(frm);
    },

    receive_items_remove(frm) {
        calculate_asarva_receive_totals(frm);
    }
});


function apply_asarva_issue_query(frm) {

    frm.set_query(
        'asarva_issue',
        function () {

            return {
                query:
                    'jari_core.jari_core.doctype.asarva_receive.asarva_receive.asarva_issue_query',

                filters: {
                    /*
                     * Existing Receive must still be
                     * able to retain/show its own Issue.
                     */
                    current_receive:
                        frm.is_new()
                            ? ''
                            : frm.doc.name
                }
            };
        }
    );
}


function apply_receive_product_query(frm) {

    frm.set_query(
        'product',
        'receive_items',
        function () {

            const products = [
                ...new Set(
                    (
                        frm.__asarva_issue_items || []
                    )
                    .map(item => item.product)
                    .filter(Boolean)
                )
            ];

            if (!products.length) {
                return {};
            }

            return {
                filters: {
                    name: [
                        'in',
                        products
                    ]
                }
            };
        }
    );
}


function load_asarva_issue_context(
    frm,
    populateRows
) {

    if (!frm.doc.asarva_issue) {
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

            const data =
                r.message || {};

            frm.__asarva_issue_items =
                data.items || [];

            apply_receive_product_query(frm);

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

                    row.source_issue_item =
                        item.source_issue_item;

                    row.product =
                        item.product;

                    row.product_quality =
                        item.product_quality;

                    row.colour =
                        item.colour;

                    row.issued_weight =
                        flt(
                            item.issued_weight
                        );

                    row.quantity_firka = 0;
                    row.gross_weight = 0;
                    row.baad_weight = 0;
                    row.received_weight = 0;
                    row.uom =
                        item.uom || 'KG';
                }
            );

            frm.refresh_field(
                'receive_items'
            );

            calculate_asarva_receive_totals(
                frm
            );
        }
    });
}


async function apply_source_item_to_row(
    frm,
    row,
    source
) {

    if (!source) {
        return;
    }

    await frappe.model.set_value(
        row.doctype,
        row.name,
        'source_issue_item',
        source.source_issue_item || ''
    );

    await frappe.model.set_value(
        row.doctype,
        row.name,
        'product',
        source.product || ''
    );

    await frappe.model.set_value(
        row.doctype,
        row.name,
        'product_quality',
        source.product_quality || ''
    );

    await frappe.model.set_value(
        row.doctype,
        row.name,
        'colour',
        source.colour || ''
    );

    await frappe.model.set_value(
        row.doctype,
        row.name,
        'issued_weight',
        flt(source.issued_weight)
    );

    await frappe.model.set_value(
        row.doctype,
        row.name,
        'uom',
        source.uom || 'KG'
    );
}


async function calculate_asarva_receive_row(
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
        gross < 0 ||
        baad < 0
    ) {
        frappe.show_alert({
            message:
                __(
                    'G.W and Baad cannot be negative.'
                ),
            indicator:
                'red'
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
            message:
                __(
                    'Baad cannot exceed G.W.'
                ),
            indicator:
                'red'
        });

        calculate_asarva_receive_totals(
            frm
        );

        return;
    }

    await frappe.model.set_value(
        cdt,
        cdn,
        'received_weight',
        flt(
            gross - baad,
            3
        )
    );

    calculate_asarva_receive_totals(
        frm
    );
}


function calculate_asarva_receive_totals(frm) {

    const rows =
        frm.doc.receive_items || [];

    const gross = rows.reduce(
        (total, row) =>
            total +
            flt(row.gross_weight),
        0
    );

    const baad = rows.reduce(
        (total, row) =>
            total +
            flt(row.baad_weight),
        0
    );

    const received = rows.reduce(
        (total, row) =>
            total +
            flt(row.received_weight),
        0
    );

    frm.set_value(
        'total_gross_weight',
        flt(
            gross,
            3
        )
    );

    frm.set_value(
        'total_baad_weight',
        flt(
            baad,
            3
        )
    );

    frm.set_value(
        'total_received_weight',
        flt(
            received,
            3
        )
    );
}
