frappe.ui.form.on('YT Issue', {
    setup(frm) {
        apply_yt_queries(frm);
    },

    refresh(frm) {
        if (!frm.doc.issue_date) {
            frm.set_value(
                'issue_date',
                frappe.datetime.get_today()
            );
        }

        apply_yt_queries(frm);
        calculate_yt_issue_totals(frm);
    },

    async process_master(frm) {
        await apply_yt_process_departments(
            frm
        );
        clear_yt_stock_sources(frm);
        apply_yt_queries(frm);
    },

    company(frm) {
        clear_yt_stock_sources(frm);
    }
});


frappe.ui.form.on('YT Issue Item', {
    issue_items_add(frm, cdt, cdn) {
        frappe.model.set_value(
            cdt,
            cdn,
            'issue_date',
            frm.doc.issue_date
        );
        frappe.model.set_value(
            cdt,
            cdn,
            'uom',
            'KG'
        );
    },

    product(frm, cdt, cdn) {
        clear_yt_source_row(
            cdt,
            cdn
        );
        frappe.model.set_value(
            cdt,
            cdn,
            'uom',
            'KG'
        );
    },

    async stock_source(
        frm,
        cdt,
        cdn
    ) {
        await load_yt_stock_source(
            frm,
            cdt,
            cdn
        );
    },

    weight(frm, cdt, cdn) {
        const row =
            locals[cdt][cdn];

        if (!row) {
            return;
        }

        frappe.model.set_value(
            cdt,
            cdn,
            'source_remaining_weight',
            Math.max(
                0,
                flt(
                    row.source_available_weight
                )
                -
                flt(
                    row.weight
                )
            )
        );

        calculate_yt_issue_totals(
            frm
        );
    },

    issue_items_remove(frm) {
        calculate_yt_issue_totals(
            frm
        );
    }
});


function apply_yt_queries(frm) {
    frm.set_query(
        'process_master',
        function () {
            return {
                query:
                    'jari_core.jari_core.doctype.process_master.process_master.process_by_jari_issue_type_query',
                filters: {
                    jari_issue_type:
                        'YT Issue'
                }
            };
        }
    );

    frm.set_query(
        'machine_name',
        'issue_items',
        function () {
            return {
                filters: {
                    department:
                        frm.doc.to_department
                        || 'YT Department',
                    is_active: 1
                }
            };
        }
    );

    frm.set_query(
        'stock_source',
        'issue_items',
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
                        frm.doc.from_department
                        || ''
                }
            };
        }
    );
}


async function apply_yt_process_departments(
    frm
) {
    if (!frm.doc.process_master) {
        await frm.set_value(
            'from_department',
            ''
        );
        await frm.set_value(
            'to_department',
            ''
        );
        return;
    }

    const response =
        await frappe.db.get_value(
            'Process Master',
            frm.doc.process_master,
            [
                'from_department',
                'to_department'
            ]
        );

    const route =
        response.message || {};

    await frm.set_value(
        'from_department',
        route.from_department || ''
    );
    await frm.set_value(
        'to_department',
        route.to_department || ''
    );
}


async function load_yt_stock_source(
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

    const selectedSource =
        row.stock_source;

    const response =
        await frappe.call({
            method:
                'jari_core.jari_core.stock_utils.get_stock_source_details',
            args: {
                stock_source:
                    selectedSource,
                current_doctype:
                    frm.doc.doctype,
                current_name:
                    frm.is_new()
                        ? ''
                        : frm.doc.name
            }
        });

    if (
        !locals[cdt]
        || !locals[cdt][cdn]
        || locals[cdt][cdn]
            .stock_source
            !== selectedSource
    ) {
        return;
    }

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
        clear_yt_source_row(
            cdt,
            cdn
        );
        return;
    }

    const locations =
        details.locations || [];

    if (!locations.length) {
        frappe.msgprint(
            __('Selected Stock Source has no remaining stock.')
        );
        clear_yt_source_row(
            cdt,
            cdn
        );
        return;
    }

    let department = '';
    const preferred =
        frm.doc.from_department || '';

    const preferredLocation =
        locations.find(
            location =>
                location.department
                === preferred
        );

    if (preferredLocation) {
        department =
            preferredLocation.department;
    } else if (
        locations.length === 1
    ) {
        department =
            locations[0].department;
    } else {
        department =
            await choose_yt_source_department(
                locations
            );
    }

    if (!department) {
        clear_yt_source_row(
            cdt,
            cdn
        );
        return;
    }

    const finalResponse =
        await frappe.call({
            method:
                'jari_core.jari_core.stock_utils.get_stock_source_details',
            args: {
                stock_source:
                    selectedSource,
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

    const finalDetails =
        finalResponse.message || {};

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
        finalDetails.source_reference
        || ''
    );
    await frappe.model.set_value(
        cdt,
        cdn,
        'source_date',
        finalDetails.source_date
        || ''
    );
    await frappe.model.set_value(
        cdt,
        cdn,
        'source_original_weight',
        flt(
            finalDetails.original_weight
        )
    );
    await frappe.model.set_value(
        cdt,
        cdn,
        'source_available_weight',
        flt(
            finalDetails.available_weight
        )
    );
    await frappe.model.set_value(
        cdt,
        cdn,
        'current_stock',
        flt(
            finalDetails.available_weight
        )
    );
    await frappe.model.set_value(
        cdt,
        cdn,
        'source_remaining_weight',
        Math.max(
            0,
            flt(
                finalDetails.available_weight
            )
            -
            flt(
                row.weight
            )
        )
    );
}


function choose_yt_source_department(
    locations
) {
    return new Promise(resolve => {
        let resolved = false;
        const options =
            locations.map(
                location =>
                    location.department
            );

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
                            options.join('\n'),
                        reqd: 1
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


function clear_yt_source_row(
    cdt,
    cdn
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
        'current_stock',
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
}


function clear_yt_stock_sources(
    frm
) {
    (
        frm.doc.issue_items
        || []
    ).forEach(
        row => {
            clear_yt_source_row(
                row.doctype,
                row.name
            );
        }
    );
}


function calculate_yt_issue_totals(
    frm
) {
    const total =
        (
            frm.doc.issue_items
            || []
        ).reduce(
            (sum, row) =>
                sum
                + flt(
                    row.weight
                ),
            0
        );

    frm.set_value(
        'total_issued_weight',
        flt(
            total,
            6
        )
    );
}
