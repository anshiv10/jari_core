console.log("Spindal Issue JS Loaded Successfully");

frappe.ui.form.on('Spindal Issue', {
    refresh(frm) {
        set_product_query_by_department(frm);
        if (!frm.doc.issue_date) frm.set_value('issue_date', frappe.datetime.get_today());


        frm.trigger('set_active_batch_no');
        calculate_spindal_issue_totals(frm);
        refresh_all_stock_summaries(frm);
    },

    after_save(frm) {
        /*
         * Saved Draft rows are now stock reservations.
         * Refresh all stock summaries immediately after Save.
         */
        refresh_all_stock_summaries(frm);
    },

    from_department(frm) {
        set_product_query_by_department(frm);
        refresh_all_stock_summaries(frm);
    },

    to_department(frm) {
        set_product_query_by_department(frm);
    },

    company(frm) {
        refresh_all_stock_summaries(frm);
    },

    issue_type(frm) {
        frm.trigger('set_active_batch_no');
    },

    new_batch_no(frm) {
        frm.trigger('set_active_batch_no');
    },

    existing_batch_no(frm) {
        frm.trigger('set_active_batch_no');
    },

    operator(frm) {
        set_operator_in_child_rows(frm);
    },

    set_active_batch_no(frm) {
        frm.set_value(
            'active_batch_no',
            frm.doc.issue_type === 'Re Issue'
                ? (frm.doc.existing_batch_no || '')
                : (frm.doc.new_batch_no || '')
        );
    },

    process_master(frm) {
        if (!frm.doc.process_master) return;

        frappe.db.get_doc('Process Master', frm.doc.process_master).then(p => {
            frm.clear_table('issue_items');

            (p.input_products || []).forEach(row => {
                let product = row.product || row.product_code || row.item || row.item_code || row.input_product;
                if (!product) return;

                let d = frm.add_child('issue_items');
                d.issue_date = frm.doc.issue_date || frappe.datetime.get_today();
                d.product = product;
                d.uom = row.uom || row.unit || 'KG';
                d.weight = 0;
                d.operator_name = frm.doc.operator || '';
                d.current_stock_summary = 'Loading...';
            });

            frm.refresh_field('issue_items');
            refresh_all_stock_summaries(frm);
            calculate_spindal_issue_totals(frm);
        });
    }
});

frappe.ui.form.on('Spindal Issue Item', {
    issue_items_add(frm, cdt, cdn) {
        let rows = frm.doc.issue_items || [];
        let previous = rows.length > 1 ? rows[rows.length - 2] : null;

        frappe.model.set_value(cdt, cdn, 'issue_date', previous?.issue_date || frm.doc.issue_date || frappe.datetime.get_today());
        frappe.model.set_value(cdt, cdn, 'product', previous?.product || '');
        frappe.model.set_value(cdt, cdn, 'uom', previous?.uom || 'KG');
        frappe.model.set_value(cdt, cdn, 'operator_name', previous?.operator_name || frm.doc.operator || '');
        frappe.model.set_value(cdt, cdn, 'weight', 0);

        if (previous?.product) {
            fetch_spindal_stock_summary(frm, cdt, cdn, previous.product);
        }

        calculate_spindal_issue_totals(frm);
    },

    product(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row.product) fetch_spindal_stock_summary(frm, cdt, cdn, row.product);
    },

    weight(frm) {
        calculate_spindal_issue_totals(frm);
    },

    issue_items_remove(frm) {
        calculate_spindal_issue_totals(frm);
    }
});

function fetch_spindal_stock_summary(frm, cdt, cdn, product) {
    if (!product) return;

    frappe.call({
        method: "jari_core.jari_core.doctype.spindal_issue.spindal_issue.get_spindal_stock_summary",
        args: { product: product, company: frm.doc.company || null },
        callback(r) {
            frappe.model.set_value(cdt, cdn, "current_stock_summary", r.message || "No stock available");
        }
    });
}

function refresh_all_stock_summaries(frm) {
    (frm.doc.issue_items || []).forEach(row => {
        if (row.product) fetch_spindal_stock_summary(frm, row.doctype, row.name, row.product);
    });
}

function set_operator_in_child_rows(frm) {
    (frm.doc.issue_items || []).forEach(row => {
        frappe.model.set_value(row.doctype, row.name, 'operator_name', frm.doc.operator || '');
    });
}

function calculate_spindal_issue_totals(frm) {
    let total_weight = 0;
    (frm.doc.issue_items || []).forEach(row => total_weight += flt(row.weight));
    frm.set_value('total_issue_weight', total_weight);
}

function set_product_query_by_department(frm) {
    frm.set_query('product', 'issue_items', function() {
        return {
            query: 'jari_core.jari_core.stock_utils.product_query_by_department',
            filters: {
                department: frm.doc.from_department || ''
            }
        };
    });
}


// BEGIN PROCESS-WISE WORKER FILTER: Spindal Issue
frappe.ui.form.on('Spindal Issue', {
    setup(frm) {
        apply_process_party_queries(frm);
    },

    refresh(frm) {
        apply_process_party_queries(frm);
    },

    process_master(frm) {
        apply_process_party_queries(frm);

        validate_selected_process_party(
            frm,
            'operator',
            'Worker Master',
            1
        );

        validate_selected_process_party(
            frm,
            'quality_code',
            'Quality Master',
            0
        );

    }
});


function get_process_assigned_query(
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
        query: 'jari_core.jari_core.doctype.process_master.process_master.process_assigned_master_query',
        filters: {
            master_doctype: masterDoctype,
            process_master:
                frm.doc.process_master,
            require_active:
                requireActive ? 1 : 0
        }
    };
}


function apply_process_party_queries(frm) {

    frm.set_query(
        'operator',
        function () {
            return get_process_assigned_query(
                frm,
                'Worker Master',
                1
            );
        }
    );

    frm.set_query(
        'quality_code',
        function () {
            return get_process_assigned_query(
                frm,
                'Quality Master',
                0
            );
        }
    );

}


async function validate_selected_process_party(
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

    if (!frm.doc.process_master) {
        await frm.set_value(
            fieldname,
            ''
        );

        return;
    }

    try {
        const response = await frappe.call({
            method: 'jari_core.jari_core.doctype.process_master.process_master.get_master_process_assignment_status',
            args: {
                master_doctype:
                    masterDoctype,
                master_name:
                    selectedName,
                process_master:
                    frm.doc.process_master,
                require_active:
                    requireActive ? 1 : 0
            }
        });

        const status =
            response.message || {};

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
// END PROCESS-WISE WORKER FILTER: Spindal Issue


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
frappe.ui.form.on('Spindal Issue', {
    process_master(frm) {
        apply_issue_process_departments(frm);
    }
});
// END PROCESS-FIRST DEPARTMENT ROUTING

// BEGIN JARI ISSUE TYPE PROCESS FILTER
frappe.ui.form.on('Spindal Issue', {
    setup(frm) {
        set_jari_issue_type_process_query(
            frm,
            'Spindal Issue'
        );
    },

    refresh(frm) {
        set_jari_issue_type_process_query(
            frm,
            'Spindal Issue'
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


// BEGIN EXACT STOCK SOURCE SELECTION: Spindal Issue

frappe.ui.form.on('Spindal Issue', {
    setup(frm) {
        jari_spindal_source_setup_source_query(frm);
    },

    refresh(frm) {
        jari_spindal_source_setup_source_query(frm);
    },

    company(frm) {
        jari_spindal_source_clear_all_sources(frm);
    }
});


frappe.ui.form.on('Spindal Issue Item', {
    product(frm, cdt, cdn) {
        jari_spindal_source_clear_source_row(
            cdt,
            cdn
        );
    },

    async stock_source(frm, cdt, cdn) {
        await jari_spindal_source_load_source(
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
                - flt(row.weight)
            )
        );
    }
});


function jari_spindal_source_setup_source_query(frm) {
    frm.set_query(
        'stock_source',
        'issue_items',
        function(doc, cdt, cdn) {
            const row =
                locals[cdt][cdn];

            return {
                query:
                    'jari_core.jari_core.stock_utils.stock_source_query',

                filters: {
                    company:
                        frm.doc.company || '',

                    product:
                        row.product || '',

                    preferred_department:
                        frm.doc.from_department || ''
                }
            };
        }
    );
}


async function jari_spindal_source_load_source(
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
        || locals[cdt][cdn].stock_source
            !== selectedSource
    ) {
        return;
    }

    const details =
        response.message || {};

    if (
        details.company
            !== frm.doc.company
        || details.product
            !== row.product
    ) {
        frappe.msgprint({
            title:
                __('Invalid Stock Source'),

            indicator:
                'red',

            message:
                __('Selected Stock Source does not match the Company/Product of this Issue row.')
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
            __('Selected Stock Source has no remaining stock.')
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
            await jari_spindal_source_choose_department(
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

    if (
        !locals[cdt]
        || !locals[cdt][cdn]
        || locals[cdt][cdn].stock_source
            !== selectedSource
    ) {
        return;
    }

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
        'source_remaining_weight',
        Math.max(
            0,
            flt(
                finalDetails.available_weight
            )
            - flt(row.weight)
        )
    );
}


function jari_spindal_source_choose_department(
    locations
) {
    return new Promise(resolve => {
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
                    const selected =
                        values.department;

                    dialog.hide();

                    resolve(
                        selected
                    );
                }
            });

        dialog.$wrapper.on(
            'hidden.bs.modal',
            function() {
                resolve('');
            }
        );

        dialog.show();
    });
}


function jari_spindal_source_clear_source_row(
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
    ].forEach(fieldname => {
        frappe.model.set_value(
            cdt,
            cdn,
            fieldname,
            ''
        );
    });
}


function jari_spindal_source_clear_all_sources(frm) {
    (
        frm.doc.issue_items
        || []
    ).forEach(row => {
        jari_spindal_source_clear_source_row(
            row.doctype,
            row.name
        );
    });
}

// END EXACT STOCK SOURCE SELECTION: Spindal Issue

// BEGIN SPINDAL DEPARTMENT WORKER FILTER
frappe.ui.form.on('Spindal Issue', {
    setup(frm) {
        jari_spindal_apply_worker_query(frm);
    },

    refresh(frm) {
        jari_spindal_apply_worker_query(frm);
    },

    to_department(frm) {
        jari_spindal_apply_worker_query(frm);
        jari_spindal_clear_invalid_row_workers(frm);
    }
});


function jari_spindal_apply_worker_query(frm) {
    frm.set_query(
        'operator_name',
        'issue_items',
        function() {
            return {
                query:
                    'jari_core.jari_core.doctype.spindal_issue.spindal_issue.spindal_worker_query',

                filters: {
                    department:
                        frm.doc.to_department || ''
                }
            };
        }
    );
}


async function jari_spindal_clear_invalid_row_workers(frm) {
    const department =
        frm.doc.to_department;

    if (!department) {
        return;
    }

    for (
        const row of
        (frm.doc.issue_items || [])
    ) {
        if (!row.operator_name) {
            continue;
        }

        const response =
            await frappe.db.get_value(
                'Worker Master',
                row.operator_name,
                [
                    'department',
                    'active'
                ]
            );

        const worker =
            response.message || {};

        if (
            worker.department !== department
            || !cint(worker.active)
        ) {
            await frappe.model.set_value(
                row.doctype,
                row.name,
                'operator_name',
                ''
            );
        }
    }
}
// END SPINDAL DEPARTMENT WORKER FILTER

