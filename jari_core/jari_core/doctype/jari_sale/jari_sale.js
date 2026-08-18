frappe.ui.form.on('Jari Sale', {
    setup(frm) {
        apply_jari_sale_queries(
            frm
        );
    },

    refresh(frm) {
        if (!frm.doc.sale_date) {
            frm.set_value(
                'sale_date',
                frappe.datetime.get_today()
            );
        }

        apply_jari_sale_queries(
            frm
        );
        calculate_jari_sale_totals(
            frm
        );
    },

    company(frm) {
        clear_all_jari_sale_sources(
            frm
        );
    },

    tax_amount(frm) {
        calculate_jari_sale_totals(
            frm
        );
    }
});


frappe.ui.form.on('Jari Sale Item', {
    async product(
        frm,
        cdt,
        cdn
    ) {
        clear_jari_sale_row_source(
            cdt,
            cdn,
            true
        );

        const row =
            locals[cdt][cdn];

        await apply_product_sale_setup(
            frm,
            row
        );

        calculate_jari_sale_row(
            frm,
            row
        );
    },

    async sale_type(
        frm,
        cdt,
        cdn
    ) {
        const row =
            locals[cdt][cdn];

        if (!row) {
            return;
        }

        await frappe.model.set_value(
            cdt,
            cdn,
            'weight_quantity',
            0
        );
        await frappe.model.set_value(
            cdt,
            cdn,
            'marks_quantity',
            0
        );
        await frappe.model.set_value(
            cdt,
            cdn,
            'firki_quantity',
            0
        );

        if (row.sale_type === 'Weight') {
            await frappe.model.set_value(
                cdt,
                cdn,
                'gilit_receive',
                ''
            );
            clear_pack_fields(
                cdt,
                cdn
            );
        } else {
            clear_jari_sale_row_source(
                cdt,
                cdn,
                false
            );

            if (row.gilit_receive) {
                await load_gilit_receive_details(
                    frm,
                    cdt,
                    cdn
                );
            }
        }

        calculate_jari_sale_row(
            frm,
            row
        );
    },

    async gilit_receive(
        frm,
        cdt,
        cdn
    ) {
        await load_gilit_receive_details(
            frm,
            cdt,
            cdn
        );
    },

    async stock_source(
        frm,
        cdt,
        cdn
    ) {
        const row =
            locals[cdt][cdn];

        if (
            !row
            || !row.stock_source
        ) {
            return;
        }

        if (
            row.sale_type === 'Marks'
            || row.sale_type === 'Firki'
        ) {
            // Packed sale source is authoritative from
            // the selected Gilit Receive.  Server validation
            // re-applies that exact source.
            return;
        }

        await load_jari_stock_source(
            frm,
            cdt,
            cdn
        );
    },

    weight_quantity(
        frm,
        cdt,
        cdn
    ) {
        calculate_jari_sale_row(
            frm,
            locals[cdt][cdn]
        );
    },

    marks_quantity(
        frm,
        cdt,
        cdn
    ) {
        calculate_jari_sale_row(
            frm,
            locals[cdt][cdn]
        );
    },

    firki_quantity(
        frm,
        cdt,
        cdn
    ) {
        calculate_jari_sale_row(
            frm,
            locals[cdt][cdn]
        );
    },

    sale_price(
        frm,
        cdt,
        cdn
    ) {
        calculate_jari_sale_row(
            frm,
            locals[cdt][cdn]
        );
    },

    items_remove(frm) {
        calculate_jari_sale_totals(
            frm
        );
    }
});


function apply_jari_sale_queries(
    frm
) {
    frm.set_query(
        'gilit_receive',
        'items',
        function (
            doc,
            cdt,
            cdn
        ) {
            const row =
                locals[cdt][cdn];

            return {
                query:
                    'jari_core.jari_core.doctype.jari_sale.jari_sale.gilit_receive_sale_query',
                filters: {
                    company:
                        frm.doc.company
                        || '',
                    product:
                        row.product
                        || ''
                }
            };
        }
    );

    frm.set_query(
        'stock_source',
        'items',
        function (
            doc,
            cdt,
            cdn
        ) {
            const row =
                locals[cdt][cdn];

            return {
                query:
                    'jari_core.jari_core.stock_utils.stock_source_query',
                filters: {
                    company:
                        frm.doc.company
                        || '',
                    product:
                        row.product
                        || '',
                    preferred_department:
                        ''
                }
            };
        }
    );
}


async function apply_product_sale_setup(
    frm,
    row
) {
    if (
        !row
        || !row.product
    ) {
        return;
    }

    const response =
        await frappe.call({
            method:
                'jari_core.jari_core.doctype.jari_sale.jari_sale.get_product_sale_setup',
            args: {
                product:
                    row.product
            }
        });

    const setup =
        response.message || {};

    await frappe.model.set_value(
        row.doctype,
        row.name,
        'uom',
        setup.unit || ''
    );

    const allowed = [];

    if (cint(
        setup.allow_weight_sale
    )) {
        allowed.push('Weight');
    }

    if (cint(
        setup.allow_marks_sale
    )) {
        allowed.push('Marks');
    }

    if (cint(
        setup.allow_firki_sale
    )) {
        allowed.push('Firki');
    }

    if (
        setup.product_tag === 'JARI'
    ) {
        const index =
            allowed.indexOf(
                'Weight'
            );

        if (index !== -1) {
            allowed.splice(
                index,
                1
            );
        }
    }

    if (allowed.length === 1) {
        await frappe.model.set_value(
            row.doctype,
            row.name,
            'sale_type',
            allowed[0]
        );
    } else if (
        row.sale_type
        && !allowed.includes(
            row.sale_type
        )
    ) {
        await frappe.model.set_value(
            row.doctype,
            row.name,
            'sale_type',
            ''
        );
    }

    if (!allowed.length) {
        frappe.show_alert({
            message:
                __(
                    'No Sale Type is enabled for Product {0}.',
                    [
                        row.product
                    ]
                ),
            indicator:
                'orange'
        });
    }
}


async function load_gilit_receive_details(
    frm,
    cdt,
    cdn
) {
    const row =
        locals[cdt][cdn];

    if (
        !row
        || !row.gilit_receive
    ) {
        clear_pack_fields(
            cdt,
            cdn
        );
        return;
    }

    if (
        row.sale_type !== 'Marks'
        && row.sale_type !== 'Firki'
    ) {
        frappe.msgprint(
            __('Gilit Receive Reference is used only for Marks/Firki sale.')
        );
        await frappe.model.set_value(
            cdt,
            cdn,
            'gilit_receive',
            ''
        );
        return;
    }

    if (!row.product) {
        frappe.msgprint(
            __('Please select Product before Gilit Receive Reference.')
        );
        await frappe.model.set_value(
            cdt,
            cdn,
            'gilit_receive',
            ''
        );
        return;
    }

    try {
        const response =
            await frappe.call({
                method:
                    'jari_core.jari_core.doctype.jari_sale.jari_sale.get_gilit_receive_sale_details',
                args: {
                    receive_name:
                        row.gilit_receive,
                    product:
                        row.product || '',
                    current_sale:
                        frm.is_new()
                            ? ''
                            : frm.doc.name
                }
            });

        const data =
            response.message || {};

        if (
            frm.doc.company
            && data.company
            && frm.doc.company
                !== data.company
        ) {
            frappe.msgprint(
                __('Selected Gilit Receive belongs to another Company.')
            );
            await frappe.model.set_value(
                cdt,
                cdn,
                'gilit_receive',
                ''
            );
            clear_pack_fields(
                cdt,
                cdn
            );
            return;
        }

        if (
            !frm.doc.company
            && data.company
        ) {
            await frm.set_value(
                'company',
                data.company
            );
        }

        if (
            row.product
            && data.product
            && row.product
                !== data.product
        ) {
            frappe.msgprint(
                __('Selected Gilit Receive does not match the selected Product.')
            );
            await frappe.model.set_value(
                cdt,
                cdn,
                'gilit_receive',
                ''
            );
            clear_pack_fields(
                cdt,
                cdn
            );
            return;
        }

        await frappe.model.set_value(
            cdt,
            cdn,
            'stock_source',
            data.stock_source || ''
        );
        await frappe.model.set_value(
            cdt,
            cdn,
            'stock_label',
            data.stock_label || ''
        );
        await frappe.model.set_value(
            cdt,
            cdn,
            'filled_firki',
            cint(
                data.filled_firki
            )
        );
        await frappe.model.set_value(
            cdt,
            cdn,
            'weight_of_one_firki',
            flt(
                data.weight_of_one_firki
            )
        );
        await frappe.model.set_value(
            cdt,
            cdn,
            'available_firki',
            cint(
                data.available_firki
            )
        );
        await frappe.model.set_value(
            cdt,
            cdn,
            'available_marks',
            cint(
                data.available_marks
            )
        );

        const locations =
            data.locations || [];

        const department =
            await choose_jari_source_department(
                locations,
                'Gilit'
            );

        if (!department) {
            frappe.msgprint(
                __('Selected Gilit source has no available stock location.')
            );
            clear_jari_sale_row_source(
                cdt,
                cdn,
                false
            );
            return;
        }

        await apply_jari_source_details(
            frm,
            cdt,
            cdn,
            data.stock_source,
            department
        );

        calculate_jari_sale_row(
            frm,
            locals[cdt][cdn]
        );
    } catch (error) {
        console.error(
            'Unable to load Gilit sale details:',
            error
        );
    }
}


async function load_jari_stock_source(
    frm,
    cdt,
    cdn
) {
    const row =
        locals[cdt][cdn];

    if (
        !row
        || !row.stock_source
    ) {
        return;
    }

    const response =
        await frappe.call({
            method:
                'jari_core.jari_core.stock_utils.get_stock_source_details',
            args: {
                stock_source:
                    row.stock_source,
                current_doctype:
                    frm.doc.doctype,
                current_name:
                    frm.is_new()
                        ? ''
                        : frm.doc.name
            }
        });

    const details =
        response.message || {};

    if (
        details.company
            !== frm.doc.company
        ||
        details.product
            !== row.product
    ) {
        frappe.msgprint(
            __('Selected Stock Source does not match this Company/Product.')
        );
        clear_jari_sale_row_source(
            cdt,
            cdn,
            false
        );
        return;
    }

    const department =
        await choose_jari_source_department(
            details.locations || [],
            ''
        );

    if (!department) {
        clear_jari_sale_row_source(
            cdt,
            cdn,
            false
        );
        return;
    }

    await apply_jari_source_details(
        frm,
        cdt,
        cdn,
        row.stock_source,
        department
    );

    calculate_jari_sale_row(
        frm,
        locals[cdt][cdn]
    );
}


async function apply_jari_source_details(
    frm,
    cdt,
    cdn,
    stockSource,
    department
) {
    const response =
        await frappe.call({
            method:
                'jari_core.jari_core.stock_utils.get_stock_source_details',
            args: {
                stock_source:
                    stockSource,
                department:
                    department,
                current_doctype:
                    frm.doc.doctype,
                current_name:
                    frm.is_new()
                        ? ''
                        : frm.doc.name
            }
        });

    const data =
        response.message || {};

    await frappe.model.set_value(
        cdt,
        cdn,
        'source_department',
        department
    );
    await frappe.model.set_value(
        cdt,
        cdn,
        'source_reference',
        data.source_reference || ''
    );
    await frappe.model.set_value(
        cdt,
        cdn,
        'source_date',
        data.source_date || ''
    );
    await frappe.model.set_value(
        cdt,
        cdn,
        'source_original_weight',
        flt(
            data.original_weight
        )
    );
    await frappe.model.set_value(
        cdt,
        cdn,
        'source_available_weight',
        flt(
            data.available_weight
        )
    );
}


function choose_jari_source_department(
    locations,
    preferred
) {
    if (!locations.length) {
        return Promise.resolve('');
    }

    const preferredLocation =
        locations.find(
            location =>
                location.department
                === preferred
        );

    if (preferredLocation) {
        return Promise.resolve(
            preferredLocation.department
        );
    }

    if (locations.length === 1) {
        return Promise.resolve(
            locations[0].department
        );
    }

    return new Promise(resolve => {
        let resolved = false;

        const dialog =
            new frappe.ui.Dialog({
                title:
                    __('Select Source Department'),
                fields: [
                    {
                        fieldname:
                            'department',
                        fieldtype:
                            'Select',
                        label:
                            __('Source Department'),
                        options:
                            locations
                                .map(
                                    location =>
                                        location.department
                                )
                                .join('\n'),
                        reqd:
                            1
                    }
                ],
                primary_action_label:
                    __('Select'),
                primary_action(values) {
                    resolved = true;
                    dialog.hide();
                    resolve(
                        values.department
                    );
                }
            });

        dialog.$wrapper.on(
            'hidden.bs.modal',
            function () {
                if (!resolved) {
                    resolve('');
                }
            }
        );

        dialog.show();
    });
}


function calculate_jari_sale_row(
    frm,
    row
) {
    if (!row) {
        return;
    }

    const price =
        flt(row.sale_price);
    let stockWeight = 0;
    let amount = 0;
    let requiredFirki = 0;

    if (
        row.sale_type === 'Weight'
    ) {
        const quantity =
            flt(row.weight_quantity);
        const uom =
            (row.uom || '')
                .trim()
                .toUpperCase();

        if (uom === 'KG') {
            stockWeight =
                quantity;
        } else if (uom === 'GM') {
            stockWeight =
                quantity / 1000;
        }

        amount =
            quantity * price;
    } else if (
        row.sale_type === 'Marks'
    ) {
        const marks =
            cint(row.marks_quantity);
        const one =
            flt(
                row.weight_of_one_firki
            );

        requiredFirki =
            marks * 4;
        stockWeight =
            requiredFirki * one;
        amount =
            marks * price;
    } else if (
        row.sale_type === 'Firki'
    ) {
        const firki =
            cint(row.firki_quantity);
        const one =
            flt(
                row.weight_of_one_firki
            );

        requiredFirki =
            firki;
        stockWeight =
            firki * one;
        amount =
            stockWeight * price;
    }

    frappe.model.set_value(
        row.doctype,
        row.name,
        'stock_weight',
        flt(
            stockWeight,
            6
        )
    );
    frappe.model.set_value(
        row.doctype,
        row.name,
        'untaxed_amount',
        flt(
            amount,
            2
        )
    );
    frappe.model.set_value(
        row.doctype,
        row.name,
        'source_remaining_weight',
        Math.max(
            0,
            flt(
                row.source_available_weight
            )
            -
            flt(
                stockWeight
            )
        )
    );

    if (
        row.sale_type === 'Marks'
        || row.sale_type === 'Firki'
    ) {
        const remainingFirki =
            Math.max(
                0,
                cint(
                    row.available_firki
                )
                - requiredFirki
            );

        frappe.model.set_value(
            row.doctype,
            row.name,
            'remaining_firki',
            remainingFirki
        );
        frappe.model.set_value(
            row.doctype,
            row.name,
            'remaining_marks',
            Math.floor(
                remainingFirki
                / 4
            )
        );
    }

    calculate_jari_sale_totals(
        frm
    );
}


function calculate_jari_sale_totals(
    frm
) {
    const untaxed =
        (
            frm.doc.items
            || []
        ).reduce(
            (total, row) =>
                total
                + flt(
                    row.untaxed_amount
                ),
            0
        );

    frm.set_value(
        'untaxed_total',
        flt(
            untaxed,
            2
        )
    );

    frm.set_value(
        'subtotal',
        flt(
            untaxed
            + flt(
                frm.doc.tax_amount
            ),
            2
        )
    );
}


function clear_pack_fields(
    cdt,
    cdn
) {
    [
        'stock_label',
        'filled_firki',
        'weight_of_one_firki',
        'available_marks',
        'available_firki',
        'remaining_marks',
        'remaining_firki'
    ].forEach(
        fieldname => {
            frappe.model.set_value(
                cdt,
                cdn,
                fieldname,
                ''
            );
        }
    );
}


function clear_jari_sale_row_source(
    cdt,
    cdn,
    clearReceive
) {
    if (
        !locals[cdt]
        || !locals[cdt][cdn]
    ) {
        return;
    }

    [
        'stock_source',
        'source_department',
        'source_reference',
        'source_date',
        'source_original_weight',
        'source_available_weight',
        'source_remaining_weight'
    ].forEach(
        fieldname => {
            frappe.model.set_value(
                cdt,
                cdn,
                fieldname,
                ''
            );
        }
    );

    clear_pack_fields(
        cdt,
        cdn
    );

    if (clearReceive) {
        frappe.model.set_value(
            cdt,
            cdn,
            'gilit_receive',
            ''
        );
    }
}


function clear_all_jari_sale_sources(
    frm
) {
    (
        frm.doc.items
        || []
    ).forEach(
        row => {
            clear_jari_sale_row_source(
                row.doctype,
                row.name,
                false
            );
        }
    );
}
