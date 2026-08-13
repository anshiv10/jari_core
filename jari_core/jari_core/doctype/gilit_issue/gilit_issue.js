console.log("Gilit Issue JS Loaded Successfully");

frappe.ui.form.on('Gilit Issue', {
    refresh(frm) {
        if (!frm.doc.issue_date) {
            frm.set_value('issue_date', frappe.datetime.get_today());
        }

        frm.set_query('spindal_peti_entry', 'peti_items', function() {
            return {
                filters: {
                    docstatus: 1,
                    status: ['!=', 'Fully Consumed'],
                    remaining_bobbin: ['>', 0]
                }
            };
        });

        refresh_all_metal_water_stock(frm);
        calculate_gilit_totals(frm);
    },

    company(frm) {
        refresh_all_metal_water_stock(frm);
    },

    to_department(frm) {
        refresh_all_metal_water_stock(frm);
    },

    issue_date(frm) {
        (frm.doc.metal_water_inputs || []).forEach(row => {
            if (!row.input_date) {
                frappe.model.set_value(row.doctype, row.name, 'input_date', frm.doc.issue_date);
            }
        });
    }
});

frappe.ui.form.on('Gilit Issue Peti Item', {
    spindal_peti_entry(frm, cdt, cdn) {
        let row = locals[cdt][cdn];

        if (!row.spindal_peti_entry) {
            row.quality_code = '';
            sync_gilit_quality(frm);
            return;
        }

        frappe.db.get_doc('Spindal Peti Entry', row.spindal_peti_entry).then(peti => {
            let total_bobbin = flt(peti.bobbin_count || peti.nang);
            let available_bobbin = flt(peti.remaining_bobbin || total_bobbin);

            if (available_bobbin <= 0 || peti.status === 'Fully Consumed') {
                frappe.msgprint('Selected Peti is already fully consumed.');
                frappe.model.set_value(cdt, cdn, 'spindal_peti_entry', '');
                return;
            }

            const peti_quality = peti.quality_code || peti.quality || '';

            if (!peti_quality) {
                frappe.msgprint(
                    `Quality is missing in Spindal Peti ${peti.name}.`
                );
                frappe.model.set_value(
                    cdt,
                    cdn,
                    'spindal_peti_entry',
                    ''
                );
                return;
            }

            if (
                frm.doc.quality_code &&
                frm.doc.quality_code !== peti_quality
            ) {
                frappe.msgprint({
                    title: __('Quality Mismatch'),
                    indicator: 'red',
                    message: __(
                        `Selected Peti ${peti.name} has Quality ` +
                        `${peti_quality}, while this Gilit Issue is ` +
                        `already using Quality ${frm.doc.quality_code}.`
                    )
                });

                frappe.model.set_value(
                    cdt,
                    cdn,
                    'spindal_peti_entry',
                    ''
                );

                return;
            }

            if (!frm.doc.quality_code) {
                frm.set_value(
                    'quality_code',
                    peti_quality
                );
            }

            frappe.call({
                method: 'jari_core.jari_core.doctype.gilit_issue.gilit_issue.get_kasab_product_name',
                callback(r) {
                    let kasab = r.message || 'KASAB';

                    frappe.model.set_value(cdt, cdn, 'peti_no', peti.peti_no || peti.name);
                    frappe.model.set_value(
                        cdt,
                        cdn,
                        'quality_code',
                        peti_quality
                    );
                    frappe.model.set_value(cdt, cdn, 'khata_no', peti.khata_no);
                    frappe.model.set_value(cdt, cdn, 'product', kasab);
                    frappe.model.set_value(cdt, cdn, 'uom', peti.uom || 'KG');
                    frappe.model.set_value(cdt, cdn, 'gross_weight', peti.gross_weight);
                    frappe.model.set_value(cdt, cdn, 'baad_weight', peti.baad_weight);
                    frappe.model.set_value(cdt, cdn, 'net_weight', peti.net_weight);
                    frappe.model.set_value(cdt, cdn, 'total_bobbin', available_bobbin);
                    frappe.model.set_value(cdt, cdn, 'available_bobbin', available_bobbin);
                    frappe.model.set_value(cdt, cdn, 'issued_bobbin', 0);
                    frappe.model.set_value(cdt, cdn, 'balance_bobbin_after_issue', 0);
                    frappe.model.set_value(cdt, cdn, 'peti_status', peti.status);
                    frappe.model.set_value(cdt, cdn, 'operator_name', peti.operator);

                    calculate_gilit_totals(frm);
                }
            });
        });
    },

    peti_items_remove(frm) {
        sync_gilit_quality(frm);
        calculate_gilit_totals(frm);
    }
});

frappe.ui.form.on('Gilit Metal Water Input', {

    product(frm, cdt, cdn) {
        gilit_clear_metal_source(
            cdt,
            cdn
        );
    },

    uom(frm, cdt, cdn) {
        gilit_refresh_metal_remaining(
            cdt,
            cdn
        );
    },

    async stock_source(
        frm,
        cdt,
        cdn
    ) {
        await gilit_load_metal_source(
            frm,
            cdt,
            cdn
        );
    },

    issued_aani(
        frm,
        cdt,
        cdn
    ) {
        gilit_refresh_metal_remaining(
            cdt,
            cdn
        );
    },

    metal_water_inputs_add(
        frm,
        cdt,
        cdn
    ) {
        frappe.model.set_value(
            cdt,
            cdn,
            'input_date',
            frm.doc.issue_date
            || frappe.datetime.get_today()
        );
    }
});


function gilit_qty_to_kg(
    value,
    uom
) {
    const qty = flt(value);

    const unit =
        (uom || '')
        .trim()
        .toLowerCase();

    if (
        [
            'kg',
            'kilogram',
            'kilograms'
        ].includes(unit)
    ) {
        return qty;
    }

    if (
        [
            'gram',
            'grams',
            'gm',
            'g'
        ].includes(unit)
    ) {
        return qty / 1000;
    }

    return null;
}


function gilit_setup_metal_source_query(
    frm
) {
    frm.set_query(
        'stock_source',
        'metal_water_inputs',
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
                        frm.doc.to_department
                        || 'Gilit'
                }
            };
        }
    );
}


async function gilit_load_metal_source(
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

    const sourceName =
        row.stock_source;

    const response =
        await frappe.call({
            method:
                'jari_core.jari_core.stock_utils.get_stock_source_details',

            args: {
                stock_source:
                    sourceName
            }
        });

    const details =
        response.message || {};

    const locations =
        details.locations || [];

    if (!locations.length) {
        frappe.msgprint(
            __(
                'Selected source has no remaining stock.'
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
        frm.doc.to_department
        || 'Gilit';

    const preferredLocation =
        locations.find(
            x =>
                x.department
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
            locations[0].department;
    }

    const detailResponse =
        await frappe.call({
            method:
                'jari_core.jari_core.stock_utils.get_stock_source_details',

            args: {
                stock_source:
                    sourceName,

                department:
                    department
            }
        });

    const finalDetails =
        detailResponse.message || {};

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

    gilit_refresh_metal_remaining(
        cdt,
        cdn
    );
}


function gilit_refresh_metal_remaining(
    cdt,
    cdn
) {
    const row =
        locals[cdt][cdn];

    if (!row) {
        return;
    }

    const issuedKg =
        gilit_qty_to_kg(
            row.issued_aani,
            row.uom
        );

    if (issuedKg === null) {
        frappe.model.set_value(
            cdt,
            cdn,
            'issued_weight_kg',
            0
        );

        return;
    }

    frappe.model.set_value(
        cdt,
        cdn,
        'issued_weight_kg',
        issuedKg
    );

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
            issuedKg
        )
    );
}


function gilit_clear_metal_source(
    cdt,
    cdn
) {
    [
        'stock_source',
        'source_department',
        'source_reference',
        'source_date',
        'source_original_weight',
        'source_available_weight',
        'issued_weight_kg',
        'source_remaining_weight',
        'current_stock'
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


function set_metal_water_stock(
    frm,
    cdt,
    cdn
) {
    const row =
        locals[cdt][cdn];

    if (
        row
        && row.stock_source
    ) {
        gilit_load_metal_source(
            frm,
            cdt,
            cdn
        );
    }
}

function refresh_all_metal_water_stock(frm) {
    (frm.doc.metal_water_inputs || []).forEach(row => {
        if (row.product) {
            set_metal_water_stock(frm, row.doctype, row.name);
        }
    });
}

function sync_gilit_quality(frm) {
    const qualities = [
        ...new Set(
            (frm.doc.peti_items || [])
                .filter(row => row.spindal_peti_entry && row.quality_code)
                .map(row => row.quality_code)
        )
    ];

    if (qualities.length === 0) {
        frm.set_value('quality_code', '');
        return;
    }

    if (qualities.length === 1) {
        frm.set_value('quality_code', qualities[0]);
    }
}


function calculate_gilit_totals(frm) {
    let total_peti = 0;
    let total_weight_kg = 0;

    (frm.doc.peti_items || []).forEach(row => {
        if (!row.spindal_peti_entry) return;

        total_peti += 1;

        total_weight_kg += flt(row.net_weight);
    });

    frm.set_value('total_peti', total_peti);
    frm.set_value('total_net_weight', total_weight_kg);
}

// BEGIN PROCESS-WISE WORKER FILTER: Gilit Issue
frappe.ui.form.on('Gilit Issue', {
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
            'gilit_karigar',
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
        'gilit_karigar',
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
// END PROCESS-WISE WORKER FILTER: Gilit Issue


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
frappe.ui.form.on('Gilit Issue', {
    process_master(frm) {
        apply_issue_process_departments(frm);
    }
});
// END PROCESS-FIRST DEPARTMENT ROUTING

// BEGIN JARI ISSUE TYPE PROCESS FILTER
frappe.ui.form.on('Gilit Issue', {
    setup(frm) {
        set_jari_issue_type_process_query(
            frm,
            'Gilit Issue'
        );
    },

    refresh(frm) {
        set_jari_issue_type_process_query(
            frm,
            'Gilit Issue'
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


// BEGIN GILIT EXACT SOURCE QUERY
frappe.ui.form.on('Gilit Issue', {
    setup(frm) {
        gilit_setup_metal_source_query(
            frm
        );
    },

    refresh(frm) {
        gilit_setup_metal_source_query(
            frm
        );
    }
});
// END GILIT EXACT SOURCE QUERY
