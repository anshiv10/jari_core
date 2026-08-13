frappe.ui.form.on('Spindal Peti Entry', {

    refresh(frm) {
        frm.set_query(
            'spindal_issue',
            function() {
                return {
                    query:
                        'jari_core.jari_core.doctype.spindal_receive.spindal_receive.spindal_issue_for_peti_query'
                };
            }
        );

        calculate_spindal_peti_weights(frm);
    },

    gross_weight_gm(frm) {
        calculate_spindal_peti_weights(frm);
    },

    baad_weight_gm(frm) {
        calculate_spindal_peti_weights(frm);
    },

    quality_code(frm) {
        /*
         * Keep the read-only display Quality synchronized with the
         * user's selected Quality Code.
         */
        if (
            frm.doc.quality_code &&
            frm.doc.quality !== frm.doc.quality_code
        ) {
            frm.set_value(
                'quality',
                frm.doc.quality_code
            );
        }
    }
});


async function calculate_spindal_peti_weights(frm) {

    const grossGm =
        flt(frm.doc.gross_weight_gm);

    const baadGm =
        flt(frm.doc.baad_weight_gm);

    if (grossGm < 0 || baadGm < 0) {
        frappe.show_alert({
            message:
                __('Weights cannot be negative.'),
            indicator:
                'red'
        });

        return;
    }

    if (
        grossGm > 0 &&
        baadGm > grossGm
    ) {
        frappe.show_alert({
            message:
                __('Baad Weight cannot be greater than Gross Weight.'),
            indicator:
                'red'
        });

        await frm.set_value(
            'gross_weight',
            flt(grossGm / 1000, 3)
        );

        await frm.set_value(
            'baad_weight',
            flt(baadGm / 1000, 3)
        );

        await frm.set_value(
            'net_weight',
            0
        );

        return;
    }

    const grossKg =
        grossGm / 1000;

    const baadKg =
        baadGm / 1000;

    const netKg =
        grossKg - baadKg;

    await frm.set_value(
        'uom',
        'KG'
    );

    await frm.set_value(
        'gross_weight',
        flt(grossKg, 3)
    );

    await frm.set_value(
        'baad_weight',
        flt(baadKg, 3)
    );

    await frm.set_value(
        'net_weight',
        flt(
            Math.max(0, netKg),
            3
        )
    );

    /*
     * Before Gilit consumption starts, Remaining N.W
     * mirrors Net Weight.
     */
    /*
     * A Draft Peti has not yet been consumed by Gilit,
     * therefore Remaining N.W must exactly match Net Weight.
     *
     * Submitted Peti balances are controlled by Gilit and
     * must never be reset from the browser.
     */
    if (frm.doc.docstatus === 0) {
        await frm.set_value(
            'remaining_net_weight',
            flt(
                Math.max(0, netKg),
                3
            )
        );
    }
}

// BEGIN SPINDAL PETI DEPARTMENT WORKER FILTER
frappe.ui.form.on('Spindal Peti Entry', {
    setup(frm) {
        jari_spindal_peti_apply_worker_query(frm);
    },

    refresh(frm) {
        jari_spindal_peti_apply_worker_query(frm);
    },

    spindal_issue(frm) {
        jari_spindal_peti_apply_worker_query(frm);
        jari_spindal_peti_clear_invalid_operator(frm);
    }
});


function jari_spindal_peti_apply_worker_query(frm) {
    frm.set_query(
        'operator',
        function() {
            return {
                query:
                    'jari_core.jari_core.doctype.spindal_issue.spindal_issue.spindal_worker_query',

                filters: {
                    spindal_issue:
                        frm.doc.spindal_issue || ''
                }
            };
        }
    );
}


async function jari_spindal_peti_clear_invalid_operator(frm) {
    if (
        !frm.doc.operator
        || !frm.doc.spindal_issue
    ) {
        return;
    }

    const issueResponse =
        await frappe.db.get_value(
            'Spindal Issue',
            frm.doc.spindal_issue,
            'to_department'
        );

    const department =
        (
            issueResponse.message
            && issueResponse.message.to_department
        ) || '';

    if (!department) {
        await frm.set_value(
            'operator',
            ''
        );
        return;
    }

    const workerResponse =
        await frappe.db.get_value(
            'Worker Master',
            frm.doc.operator,
            [
                'department',
                'active'
            ]
        );

    const worker =
        workerResponse.message || {};

    if (
        worker.department !== department
        || !cint(worker.active)
    ) {
        await frm.set_value(
            'operator',
            ''
        );

        frappe.show_alert({
            message: __(
                'Operator cleared because the worker does not belong to the Spindal department.'
            ),
            indicator: 'orange'
        });
    }
}
// END SPINDAL PETI DEPARTMENT WORKER FILTER

