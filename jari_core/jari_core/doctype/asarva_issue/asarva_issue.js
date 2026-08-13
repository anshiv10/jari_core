
frappe.ui.form.on('Asarva Issue', {
    setup(frm) {
        apply_asarva_multi_process_queries(frm);
    },

    refresh(frm) {
        if (!frm.doc.issue_date) {
            frm.set_value(
                'issue_date',
                frappe.datetime.get_today()
            );
        }

        apply_asarva_multi_process_queries(frm);
        calculate_asarva_issue_totals(frm);
    },

    process_master(frm) {
        apply_asarva_multi_process_queries(frm);

        validate_asarva_process_selection(
            frm,
            'asarva_outsourcer',
            'Jobworker Master',
            0
        );

        validate_asarva_process_selection(
            frm,
            'quality_code',
            'Quality Master',
            0
        );

        (frm.doc.issue_items || []).forEach(
            row => {
                validate_asarva_child_worker(
                    frm,
                    row
                );
            }
        );

        if (!frm.doc.process_master) {
            return;
        }

        frappe.db.get_value(
            'Process Master',
            frm.doc.process_master,
            [
                'from_department',
                'to_department'
            ]
        ).then(r => {
            const values = r.message || {};

            if (
                !frm.doc.from_department &&
                values.from_department
            ) {
                frm.set_value(
                    'from_department',
                    values.from_department
                );
            }

            if (
                !frm.doc.to_department &&
                values.to_department
            ) {
                frm.set_value(
                    'to_department',
                    values.to_department
                );
            }
        });
    },

    expected_receive_percent(frm) {
        calculate_asarva_issue_totals(frm);
    }
});


frappe.ui.form.on('Asarva Issue Item', {
    issue_items_add(frm, cdt, cdn) {
        frappe.model.set_value(
            cdt,
            cdn,
            'issue_date',
            frm.doc.issue_date ||
            frappe.datetime.get_today()
        );

        frappe.model.set_value(
            cdt,
            cdn,
            'product_quality',
            frm.doc.quality_code || ''
        );

        frappe.model.set_value(
            cdt,
            cdn,
            'uom',
            'KG'
        );
    },

    issued_weight(frm) {
        calculate_asarva_issue_totals(frm);
    },

    issue_items_remove(frm) {
        calculate_asarva_issue_totals(frm);
    }
});


function calculate_asarva_issue_totals(frm) {
    const issued = (
        frm.doc.issue_items || []
    ).reduce(
        (total, row) =>
            total + flt(row.issued_weight),
        0
    );

    const expected =
        issued
        * flt(frm.doc.expected_receive_percent)
        / 100;

    frm.set_value(
        'total_issued_weight',
        flt(issued, 3)
    );

    frm.set_value(
        'expected_received_weight',
        flt(expected, 3)
    );

    frm.set_value(
        'balance_expected_weight',
        Math.max(
            0,
            flt(
                expected -
                flt(frm.doc.total_received_weight),
                3
            )
        )
    );
}


/*
 * ============================================================
 * MULTI-PROCESS MASTER FILTERS
 * ============================================================
 */


/*
 * ============================================================
 * MULTI-PROCESS MASTER FILTER HELPERS
 * ============================================================
 */

function get_asarva_process_query(
    frm,
    masterDoctype,
    requireActive
) {
    if (!frm.doc.process_master) {
        return {
            filters: {
                name: '__NO_PROCESS_SELECTED__'
            }
        };
    }

    return {
        query:
            'jari_core.jari_core.doctype.process_master.process_master.process_assigned_master_query',
        filters: {
            master_doctype: masterDoctype,
            process_master:
                frm.doc.process_master,
            require_active:
                requireActive ? 1 : 0
        }
    };
}


function apply_asarva_multi_process_queries(frm) {
    frm.set_query(
        'asarva_outsourcer',
        function () {
            return get_asarva_process_query(
                frm,
                'Jobworker Master',
                0
            );
        }
    );

    frm.set_query(
        'quality_code',
        function () {
            return get_asarva_process_query(
                frm,
                'Quality Master',
                0
            );
        }
    );

    frm.set_query(
        'rangrej_operator',
        'issue_items',
        function () {
            return get_asarva_process_query(
                frm,
                'Worker Master',
                1
            );
        }
    );
}


async function get_asarva_assignment_status(
    frm,
    masterDoctype,
    masterName,
    requireActive
) {
    if (
        !masterName ||
        !frm.doc.process_master
    ) {
        return {
            valid: false
        };
    }

    const response = await frappe.call({
        method:
            'jari_core.jari_core.doctype.process_master.process_master.get_master_process_assignment_status',
        args: {
            master_doctype:
                masterDoctype,
            master_name:
                masterName,
            process_master:
                frm.doc.process_master,
            require_active:
                requireActive ? 1 : 0
        }
    });

    return response.message || {};
}


async function validate_asarva_process_selection(
    frm,
    fieldname,
    masterDoctype,
    requireActive
) {
    const selectedName =
        frm.doc[fieldname];

    if (!selectedName) {
        return;
    }

    try {
        const status =
            await get_asarva_assignment_status(
                frm,
                masterDoctype,
                selectedName,
                requireActive
            );

        if (!status.valid) {
            await frm.set_value(
                fieldname,
                ''
            );

            frappe.show_alert({
                message: __(
                    'Selection cleared because it is not actively assigned to the selected Process.'
                ),
                indicator: 'orange'
            });
        }
    } catch (error) {
        console.error(
            `Unable to validate ${fieldname}:`,
            error
        );
    }
}


async function validate_asarva_child_worker(
    frm,
    row
) {
    if (!row.rangrej_operator) {
        return;
    }

    try {
        const status =
            await get_asarva_assignment_status(
                frm,
                'Worker Master',
                row.rangrej_operator,
                1
            );

        if (!status.valid) {
            await frappe.model.set_value(
                row.doctype,
                row.name,
                'rangrej_operator',
                ''
            );

            frappe.show_alert({
                message: __(
                    'Rangrej Operator was cleared because it is not actively assigned to the selected Process.'
                ),
                indicator: 'orange'
            });
        }
    } catch (error) {
        console.error(
            'Unable to validate Rangrej Operator:',
            error
        );
    }
}


async function apply_issue_process_departments(frm) {
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

    const response = await frappe.db.get_value(
        'Process Master',
        frm.doc.process_master,
        [
            'process_name',
            'from_department',
            'to_department'
        ]
    );

    const route = response.message || {};

    if (
        !route.from_department ||
        !route.to_department
    ) {
        await frm.set_value(
            'from_department',
            ''
        );

        await frm.set_value(
            'to_department',
            ''
        );

        frappe.msgprint({
            title: __('Process Routing Missing'),
            indicator: 'red',
            message: __(
                'Please configure From Department and To Department in Process Master {0}.',
                [
                    route.process_name ||
                    frm.doc.process_master
                ]
            )
        });

        return;
    }

    await frm.set_value(
        'from_department',
        route.from_department
    );

    await frm.set_value(
        'to_department',
        route.to_department
    );
}

// BEGIN PROCESS-FIRST DEPARTMENT ROUTING
frappe.ui.form.on('Asarva Issue', {
    process_master(frm) {
        apply_issue_process_departments(frm);
    }
});
// END PROCESS-FIRST DEPARTMENT ROUTING

// BEGIN JARI ISSUE TYPE PROCESS FILTER
frappe.ui.form.on('Asarva Issue', {
    setup(frm) {
        set_jari_issue_type_process_query(
            frm,
            'Asarva Issue'
        );
    },

    refresh(frm) {
        set_jari_issue_type_process_query(
            frm,
            'Asarva Issue'
        );
    }
});

function set_jari_issue_type_process_query(
    frm,
    issueType
) {
    frm.set_query(
        'process_master',
        function () {
            return {
                query:
                    'jari_core.jari_core.doctype.process_master.process_master.process_by_jari_issue_type_query',
                filters: {
                    jari_issue_type: issueType
                }
            };
        }
    );
}
// END JARI ISSUE TYPE PROCESS FILTER

// BEGIN ASARVA EXACT STOCK SOURCE

frappe.ui.form.on('Asarva Issue', {
    setup(frm) {
        asarva_setup_stock_source_query(
            frm
        );
    },

    refresh(frm) {
        asarva_setup_stock_source_query(
            frm
        );
    },

    company(frm) {
        asarva_clear_all_stock_sources(
            frm
        );
    }
});


frappe.ui.form.on('Asarva Issue Item', {

    product(frm, cdt, cdn) {
        asarva_clear_source_row(
            cdt,
            cdn
        );
    },

    async stock_source(
        frm,
        cdt,
        cdn
    ) {
        await asarva_load_stock_source(
            frm,
            cdt,
            cdn
        );
    },

    issued_weight(
        frm,
        cdt,
        cdn
    ) {
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
                    row.issued_weight
                )
            )
        );

        calculate_asarva_issue_totals(
            frm
        );
    }
});


function asarva_setup_stock_source_query(
    frm
) {
    frm.set_query(
        'stock_source',
        'issue_items',
        function(
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


async function asarva_load_stock_source(
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
                    selectedSource
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
        frappe.msgprint({
            title:
                __('Invalid Stock Source'),

            indicator:
                'red',

            message:
                __(
                    'Selected Stock Source does not match this Company/Product.'
                )
        });

        await frappe.model.set_value(
            cdt,
            cdn,
            'stock_source',
            ''
        );

        return;
    }

    const locations =
        details.locations || [];

    if (!locations.length) {
        frappe.msgprint(
            __(
                'Selected Stock Source has no remaining stock.'
            )
        );

        await frappe.model.set_value(
            cdt,
            cdn,
            'stock_source',
            ''
        );

        return;
    }

    let department = '';

    const preferred =
        frm.doc.from_department
        || '';

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
            await asarva_choose_source_department(
                locations
            );
    }

    if (!department) {
        await frappe.model.set_value(
            cdt,
            cdn,
            'stock_source',
            ''
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
                    department
            }
        });

    const finalDetails =
        finalResponse.message
        || {};

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
        'source_remaining_weight',
        Math.max(
            0,
            flt(
                finalDetails.available_weight
            )
            -
            flt(
                row.issued_weight
            )
        )
    );
}


function asarva_choose_source_department(
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
                    __(
                        'Select Source Department'
                    ),

                fields: [
                    {
                        fieldname:
                            'department',

                        fieldtype:
                            'Select',

                        label:
                            __(
                                'Source Department'
                            ),

                        options:
                            options.join('\n'),

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
            function() {
                if (!resolved) {
                    resolve('');
                }
            }
        );

        dialog.show();
    });
}


function asarva_clear_source_row(
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


function asarva_clear_all_stock_sources(
    frm
) {
    (
        frm.doc.issue_items
        || []
    ).forEach(
        row => {
            asarva_clear_source_row(
                row.doctype,
                row.name
            );
        }
    );
}

// END ASARVA EXACT STOCK SOURCE
