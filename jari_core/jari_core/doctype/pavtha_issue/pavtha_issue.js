console.log('Pavtha Issue JS Loaded Successfully');


frappe.ui.form.on('Pavtha Issue', {

    setup(frm) {
        set_jari_issue_type_process_query(
            frm,
            'Pavtha Issue'
        );

        set_product_query_by_department(frm);
        apply_process_party_queries(frm);
    },


    refresh(frm) {
        if (
            frm.is_new() &&
            !frm.doc.issue_date
        ) {
            frm.set_value(
                'issue_date',
                frappe.datetime.get_today()
            );
        }

        /*
         * Process selection is controlled by
         * Process Master.jari_issue_type.
         *
         * We deliberately DO NOT filter Process by
         * to_department because Process itself controls
         * From / To Department.
         */
        set_jari_issue_type_process_query(
            frm,
            'Pavtha Issue'
        );

        set_product_query_by_department(frm);
        apply_process_party_queries(frm);

        set_default_type_on_existing_issue_items(frm);
        refresh_all_stock_summaries(frm);
        calculate_total_issue_weight(frm);
    },


    async process_master(frm) {

        /*
         * Correct Process-first sequence:
         *
         * 1. Process selected
         * 2. Fetch From / To Department
         * 3. Apply Process-specific master filters
         * 4. Validate previous party selections
         * 5. Fetch Process input products
         */

        await apply_issue_process_departments(frm);

        set_product_query_by_department(frm);
        apply_process_party_queries(frm);

        await validate_selected_process_party(
            frm,
            'outsourcer',
            'Jobworker Master',
            0
        );

        await validate_selected_process_party(
            frm,
            'operator',
            'Worker Master',
            1
        );

        await validate_selected_process_party(
            frm,
            'quality_code',
            'Quality Master',
            0
        );

        await fetch_process_items(frm);
    },


    /*
     * IMPORTANT:
     *
     * Department is generated from Process Master.
     * Therefore changing To Department programmatically
     * must NOT clear Process Master.
     */
    to_department(frm) {
        set_product_query_by_department(frm);
    },


    company(frm) {
        refresh_all_stock_summaries(frm);
    },


    outsourcer(frm) {
        /*
         * Issue/Receive classification is row-wise.
         * Outsourcer selection must never overwrite it.
         */
        set_default_type_on_existing_issue_items(frm);
    }
});


frappe.ui.form.on('Pavtha Issue Item', {

    issue_items_add(frm, cdt, cdn) {
        const row = frappe.get_doc(
            cdt,
            cdn
        );

        if (!row.issue_receive_type) {
            frappe.model.set_value(
                cdt,
                cdn,
                'issue_receive_type',
                get_pavtha_transaction_type(frm)
            );
        }
    },


    product(frm, cdt, cdn) {
        const row = frappe.get_doc(
            cdt,
            cdn
        );

        if (!row.product) {
            return;
        }

        fetch_stock_summary(
            frm,
            cdt,
            cdn,
            row.product
        );
    },


    weight(frm) {
        calculate_total_issue_weight(frm);
    },


    issue_items_remove(frm) {
        calculate_total_issue_weight(frm);
    }
});


async function fetch_process_items(frm) {

    if (!frm.doc.process_master) {
        frm.clear_table('issue_items');
        frm.refresh_field('issue_items');

        calculate_total_issue_weight(frm);

        return;
    }

    try {

        const selectedProcess =
            frm.doc.process_master;

        const process =
            await frappe.db.get_doc(
                'Process Master',
                selectedProcess
            );

        /*
         * Prevent an older asynchronous response from
         * populating rows after the user has selected a
         * different Process.
         */
        if (
            frm.doc.process_master !==
            selectedProcess
        ) {
            return;
        }

        frm.clear_table('issue_items');

        const inputRows =
            process.input_products || [];

        const transactionType =
            get_pavtha_transaction_type(frm);

        if (!inputRows.length) {

            frm.refresh_field('issue_items');

            calculate_total_issue_weight(frm);

            frappe.msgprint({
                title: __('Process Master'),
                message: __(
                    'No input products were found in the selected Process Master.'
                ),
                indicator: 'orange'
            });

            return;
        }


        inputRows.forEach(sourceRow => {

            const product =
                sourceRow.product ||
                sourceRow.product_code ||
                sourceRow.item ||
                sourceRow.item_code ||
                sourceRow.input_product;

            const uom =
                sourceRow.uom ||
                sourceRow.unit ||
                sourceRow.default_uom ||
                'KG';

            if (!product) {
                return;
            }


            const child = frm.add_child(
                'issue_items',
                {
                    product: product,

                    uom: uom,

                    weight: flt(
                        sourceRow.weight ||
                        sourceRow.qty ||
                        sourceRow.input_weight
                    ),

                    issue_receive_type:
                        transactionType,

                    current_stock_summary:
                        __('Loading...')
                }
            );


            fetch_stock_summary(
                frm,
                child.doctype,
                child.name,
                child.product
            );
        });


        frm.refresh_field(
            'issue_items'
        );

        calculate_total_issue_weight(frm);


        frappe.show_alert({
            message:
                __('Pavtha input products were loaded.'),
            indicator: 'green'
        });


    } catch (error) {

        console.error(
            'Unable to load Pavtha process items:',
            error
        );

        frappe.msgprint({
            title:
                __('Unable to Load Process'),

            message: __(
                'The selected Process Master could not be loaded. Check the browser console and server logs.'
            ),

            indicator:
                'red'
        });
    }
}


function get_pavtha_transaction_type(frm) {

    /*
     * Default transaction classification.
     *
     * Individual rows may subsequently be changed to:
     *
     * In-house
     * Readymade
     * Return
     */
    return 'In-house';
}


function set_default_type_on_existing_issue_items(frm) {

    const transactionType =
        get_pavtha_transaction_type(frm);

    (frm.doc.issue_items || []).forEach(
        row => {

            if (!row.issue_receive_type) {

                frappe.model.set_value(
                    row.doctype,
                    row.name,
                    'issue_receive_type',
                    transactionType
                );
            }
        }
    );
}


function fetch_stock_summary(
    frm,
    cdt,
    cdn,
    product
) {

    if (!product) {
        return;
    }


    frappe.call({

        method:
            'jari_core.jari_core.doctype.pavtha_issue.pavtha_issue.get_product_stock_summary',

        args: {
            product: product,
            company:
                frm.doc.company || null
        },


        callback(r) {

            /*
             * Row may have been removed while the
             * async request was executing.
             */
            if (
                !locals[cdt] ||
                !locals[cdt][cdn]
            ) {
                return;
            }

            frappe.model.set_value(
                cdt,
                cdn,
                'current_stock_summary',
                r.message ||
                    __('No stock available')
            );
        },


        error(error) {

            console.error(
                `Unable to fetch stock summary for ${product}:`,
                error
            );

            if (
                locals[cdt] &&
                locals[cdt][cdn]
            ) {

                frappe.model.set_value(
                    cdt,
                    cdn,
                    'current_stock_summary',
                    __('Unable to load stock')
                );
            }
        }
    });
}


function refresh_all_stock_summaries(frm) {

    (frm.doc.issue_items || []).forEach(
        row => {

            if (row.product) {

                fetch_stock_summary(
                    frm,
                    row.doctype,
                    row.name,
                    row.product
                );
            }
        }
    );
}


function calculate_total_issue_weight(frm) {

    const total = (
        frm.doc.issue_items || []
    ).reduce(
        (sum, row) =>
            sum + flt(row.weight),
        0
    );


    set_parent_value_if_changed(
        frm,
        'total_issue_weight',
        total
    );
}


function set_product_query_by_department(frm) {

    frm.set_query(
        'product',
        'issue_items',
        () => {

            return {
                query:
                    'jari_core.jari_core.stock_utils.product_query_by_department',

                filters: {
                    department:
                        frm.doc.to_department || ''
                }
            };
        }
    );
}


function set_parent_value_if_changed(
    frm,
    fieldname,
    value
) {

    const currentValue =
        flt(
            frm.doc[fieldname]
        );

    const nextValue =
        flt(value);


    if (
        Math.abs(
            currentValue -
            nextValue
        ) > 0.000001
    ) {

        frm.set_value(
            fieldname,
            nextValue
        );
    }
}


/*
 * ============================================================
 * PROCESS-SPECIFIC PARTY FILTERING
 * ============================================================
 */

function get_process_assigned_query(
    frm,
    masterDoctype,
    requireActive
) {

    if (!frm.doc.process_master) {

        return {
            filters: {
                name:
                    '__NO_PROCESS_SELECTED__'
            }
        };
    }


    return {

        query:
            'jari_core.jari_core.doctype.process_master.process_master.process_assigned_master_query',

        filters: {

            master_doctype:
                masterDoctype,

            process_master:
                frm.doc.process_master,

            require_active:
                requireActive ? 1 : 0
        }
    };
}


function apply_process_party_queries(frm) {

    frm.set_query(
        'outsourcer',
        () => {

            return get_process_assigned_query(
                frm,
                'Jobworker Master',
                0
            );
        }
    );


    frm.set_query(
        'operator',
        () => {

            return get_process_assigned_query(
                frm,
                'Worker Master',
                1
            );
        }
    );


    frm.set_query(
        'quality_code',
        () => {

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

        const response =
            await frappe.call({

                method:
                    'jari_core.jari_core.doctype.process_master.process_master.get_master_process_assignment_status',

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

                indicator:
                    'orange'
            });
        }


    } catch (error) {

        console.error(
            `Unable to validate ${fieldname}:`,
            error
        );
    }
}


/*
 * ============================================================
 * PROCESS-FIRST DEPARTMENT ROUTING
 * ============================================================
 */

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


    const selectedProcess =
        frm.doc.process_master;


    const response =
        await frappe.db.get_value(
            'Process Master',
            selectedProcess,
            [
                'process_name',
                'from_department',
                'to_department'
            ]
        );


    /*
     * Ignore stale asynchronous response.
     */
    if (
        frm.doc.process_master !==
        selectedProcess
    ) {
        return;
    }


    const route =
        response.message || {};


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

            title:
                __('Process Routing Missing'),

            indicator:
                'red',

            message: __(
                'Please configure From Department and To Department in Process Master {0}.',
                [
                    route.process_name ||
                    selectedProcess
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


/*
 * ============================================================
 * JARI ISSUE TYPE PROCESS FILTER
 * ============================================================
 */

function set_jari_issue_type_process_query(
    frm,
    issueType
) {

    frm.set_query(
        'process_master',
        () => {

            return {

                query:
                    'jari_core.jari_core.doctype.process_master.process_master.process_by_jari_issue_type_query',

                filters: {
                    jari_issue_type:
                        issueType
                }
            };
        }
    );
}


// BEGIN EXACT STOCK SOURCE SELECTION: Pavtha Issue

frappe.ui.form.on('Pavtha Issue', {
    setup(frm) {
        jari_pavtha_source_setup_source_query(frm);
    },

    refresh(frm) {
        jari_pavtha_source_setup_source_query(frm);
    },

    company(frm) {
        jari_pavtha_source_clear_all_sources(frm);
    }
});


frappe.ui.form.on('Pavtha Issue Item', {
    product(frm, cdt, cdn) {
        jari_pavtha_source_clear_source_row(
            cdt,
            cdn
        );
    },

    async stock_source(frm, cdt, cdn) {
        await jari_pavtha_source_load_source(
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


function jari_pavtha_source_setup_source_query(frm) {
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


async function jari_pavtha_source_load_source(
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
            await jari_pavtha_source_choose_department(
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


function jari_pavtha_source_choose_department(
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


function jari_pavtha_source_clear_source_row(
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


function jari_pavtha_source_clear_all_sources(frm) {
    (
        frm.doc.issue_items
        || []
    ).forEach(row => {
        jari_pavtha_source_clear_source_row(
            row.doctype,
            row.name
        );
    });
}

// END EXACT STOCK SOURCE SELECTION: Pavtha Issue
