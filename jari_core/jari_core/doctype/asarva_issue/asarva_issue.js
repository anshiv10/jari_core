
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
