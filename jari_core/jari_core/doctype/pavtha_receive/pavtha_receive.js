console.log('Pavtha Receive JS Loaded Successfully');

let pdfPayoutPreviewTimer = null;


frappe.ui.form.on('Pavtha Receive', {
    setup(frm) {
        set_pavtha_issue_query(frm);
    },

    refresh(frm) {
        set_pavtha_issue_query(frm);

        if (frm.is_new() && !frm.doc.receive_date) {
            frm.set_value(
                'receive_date',
                frappe.datetime.get_today()
            );
        }

        set_default_type_on_receive_rows(frm);
        calculate_pavtha_preview(frm);
        schedule_pdf_payout_preview(frm);
    },

    async pavtha_issue(frm) {
        if (!frm.doc.pavtha_issue) {
            await clear_pavtha_issue_details(frm);
            return;
        }

        await load_pavtha_issue(frm);
    },

    rate_per_kg(frm) {
        calculate_pavtha_preview(frm);
    },

    loss_standard_percent(frm) {
        calculate_pavtha_preview(frm);
    },

    payout_given(frm) {
        calculate_payout_variance(frm);
    },

    payout_format(frm) {
        schedule_pdf_payout_preview(frm);
    },

    mel(frm) {
        schedule_pdf_payout_preview(frm);
    },

    return_weight(frm) {
        schedule_pdf_payout_preview(frm);
    },

    bg_deduction_percent(frm) {
        schedule_pdf_payout_preview(frm);
    }
});


frappe.ui.form.on('Pavtha Output Item', {
    output_items_add(frm, cdt, cdn) {
        set_receive_row_type(frm, cdt, cdn);
        schedule_pdf_payout_preview(frm);
    },

    product(frm) {
        calculate_pavtha_preview(frm);
        schedule_pdf_payout_preview(frm);
    },

    weight(frm) {
        calculate_pavtha_preview(frm);
        schedule_pdf_payout_preview(frm);
    },

    output_items_remove(frm) {
        calculate_pavtha_preview(frm);
        schedule_pdf_payout_preview(frm);
    }
});


frappe.ui.form.on('Pavtha Waste Item', {
    waste_items_add(frm, cdt, cdn) {
        set_receive_row_type(frm, cdt, cdn);
        schedule_pdf_payout_preview(frm);
    },

    waste_product(frm) {
        calculate_pavtha_preview(frm);
        schedule_pdf_payout_preview(frm);
    },

    weight(frm) {
        calculate_pavtha_preview(frm);
        schedule_pdf_payout_preview(frm);
    },

    waste_items_remove(frm) {
        calculate_pavtha_preview(frm);
        schedule_pdf_payout_preview(frm);
    }
});


function set_pavtha_issue_query(frm) {
    frm.set_query('pavtha_issue', () => {
        return {
            query:
                'jari_core.jari_core.doctype.pavtha_receive.pavtha_receive.pavtha_issue_query'
        };
    });
}


async function load_pavtha_issue(frm) {
    try {
        const issue = await frappe.db.get_doc(
            'Pavtha Issue',
            frm.doc.pavtha_issue
        );

        if (!issue) {
            frappe.throw(
                __('The selected Pavtha Issue was not found.')
            );
        }

        const transactionType =
            determine_issue_transaction_type(issue);

        await frm.set_value({
            company: issue.company || null,
            batch_no: issue.batch_no || null,
            process_master: issue.process_master || null,
            quality_code: issue.quality_code || null,
            outsourcer: issue.outsourcer || null,
            total_input_weight: flt(
                issue.total_issue_weight
            )
        });

        await load_jobworker_values(
            frm,
            issue
        );

        await load_process_output_and_waste_items(
            frm,
            issue.process_master,
            transactionType
        );

        calculate_pavtha_preview(frm);
        schedule_pdf_payout_preview(frm);
    } catch (error) {
        console.error(
            'Unable to load Pavtha Issue:',
            error
        );

        frappe.msgprint({
            title: __('Unable to Load Pavtha Issue'),
            message: __(
                'The Pavtha Issue details could not be loaded. Check the browser console and server logs.'
            ),
            indicator: 'red'
        });
    }
}


function determine_issue_transaction_type(issue) {
    const itemTypes = [
        ...new Set(
            (issue.issue_items || [])
                .map(row => row.issue_receive_type)
                .filter(Boolean)
        )
    ];

    if (itemTypes.length > 1) {
        frappe.throw(
            __(
                'The selected Pavtha Issue contains multiple Issue/Receive Types. A single Pavtha Receive cannot process mixed transaction types.'
            )
        );
    }

    if (itemTypes.length === 1) {
        return itemTypes[0];
    }

    return issue.outsourcer
        ? 'Readymade'
        : 'In-house';
}


async function load_jobworker_values(frm, issue) {
    if (!issue.outsourcer) {
        await frm.set_value({
            rate_per_kg: 0,
            loss_standard_percent: 0
        });

        return;
    }

    try {
        const response = await frappe.db.get_value(
            'Jobworker Master',
            issue.outsourcer,
            [
                'rate_per_kg',
                'standard_loss_percent'
            ]
        );

        const values = response.message || {};

        await frm.set_value({
            rate_per_kg: flt(
                values.rate_per_kg
            ),
            loss_standard_percent: flt(
                values.standard_loss_percent
            )
        });
    } catch (error) {
        console.error(
            'Unable to load Jobworker Master:',
            error
        );

        await frm.set_value({
            rate_per_kg: 0,
            loss_standard_percent: 0
        });

        frappe.show_alert({
            message:
                __('Unable to load jobworker rate and loss standard.'),
            indicator: 'orange'
        });
    }
}


async function load_process_output_and_waste_items(
    frm,
    processMaster,
    transactionType
) {
    frm.clear_table('output_items');
    frm.clear_table('waste_items');

    if (!processMaster) {
        frm.refresh_field('output_items');
        frm.refresh_field('waste_items');
        return;
    }

    const process = await frappe.db.get_doc(
        'Process Master',
        processMaster
    );

    (process.output_products || []).forEach(sourceRow => {
        const product =
            sourceRow.product ||
            sourceRow.product_code ||
            sourceRow.item ||
            sourceRow.item_code ||
            sourceRow.output_product;

        if (!product) {
            return;
        }

        frm.add_child('output_items', {
            product: product,
            uom:
                sourceRow.uom ||
                sourceRow.unit ||
                sourceRow.default_uom ||
                'KG',
            weight: 0,
            issue_receive_type: transactionType
        });
    });

    (
        process.custom_waste_product_items || []
    ).forEach(sourceRow => {
        const wasteProduct =
            sourceRow.waste_product ||
            sourceRow.product ||
            sourceRow.product_code ||
            sourceRow.item_code;

        if (!wasteProduct) {
            return;
        }

        frm.add_child('waste_items', {
            waste_product: wasteProduct,
            uom:
                sourceRow.uom ||
                sourceRow.unit ||
                sourceRow.default_uom ||
                'KG',
            weight: 0,
            issue_receive_type: transactionType
        });
    });

    frm.refresh_field('output_items');
    frm.refresh_field('waste_items');

    frappe.show_alert({
        message: __(
            'Pavtha output and waste products were auto-filled.'
        ),
        indicator: 'green'
    });
}


function get_receive_transaction_type(frm) {
    const existingTypes = [
        ...(frm.doc.output_items || []),
        ...(frm.doc.waste_items || [])
    ]
        .map(row => row.issue_receive_type)
        .filter(Boolean);

    if (existingTypes.length) {
        return existingTypes[0];
    }

    return frm.doc.outsourcer
        ? 'Readymade'
        : 'In-house';
}


function set_receive_row_type(frm, cdt, cdn) {
    const row = frappe.get_doc(cdt, cdn);

    if (!row.issue_receive_type) {
        frappe.model.set_value(
            cdt,
            cdn,
            'issue_receive_type',
            get_receive_transaction_type(frm)
        );
    }
}


function set_default_type_on_receive_rows(frm) {
    const transactionType =
        get_receive_transaction_type(frm);

    [
        ...(frm.doc.output_items || []),
        ...(frm.doc.waste_items || [])
    ].forEach(row => {
        if (!row.issue_receive_type) {
            frappe.model.set_value(
                row.doctype,
                row.name,
                'issue_receive_type',
                transactionType
            );
        }
    });
}


function calculate_pavtha_preview(frm) {
    const inputWeight = flt(
        frm.doc.total_input_weight
    );

    const outputWeight = (
        frm.doc.output_items || []
    ).reduce(
        (total, row) =>
            total + flt(row.weight),
        0
    );

    const wasteWeight = (
        frm.doc.waste_items || []
    ).reduce(
        (total, row) =>
            total + flt(row.weight),
        0
    );

    /*
     * Pavtha gross output may exceed input because copper or another
     * base metal can be added.
     */
    let grossDifference =
        inputWeight -
        outputWeight -
        wasteWeight;

    if (
        Math.abs(grossDifference)
        < 0.000001
    ) {
        grossDifference = 0;
    }

    const lossWeight = Math.max(
        grossDifference,
        0
    );

    const materialAdditionWeight = Math.max(
        -grossDifference,
        0
    );

    const lossPercent = inputWeight
        ? (
            lossWeight /
            inputWeight
        ) * 100
        : 0;

    const materialAdditionPercent = inputWeight
        ? (
            materialAdditionWeight /
            inputWeight
        ) * 100
        : 0;

    const wastePercent = inputWeight
        ? (
            wasteWeight /
            inputWeight
        ) * 100
        : 0;

    const ratePerKg = flt(
        frm.doc.rate_per_kg
    );

    const standardLossPercent = flt(
        frm.doc.loss_standard_percent
    );

    const basePayout =
        inputWeight *
        ratePerKg;

    const variancePercent =
        lossPercent -
        standardLossPercent;

    let bonusAmount = 0;
    let deductionAmount = 0;

    if (variancePercent > 0) {
        const excessLossWeight =
            inputWeight *
            variancePercent /
            100;

        deductionAmount =
            excessLossWeight *
            ratePerKg;
    } else if (
        variancePercent < 0 &&
        materialAdditionWeight <= 0.000001
    ) {
        /*
         * Added copper or other material must not create an artificial
         * saved-loss bonus.
         */
        const savedWeight =
            inputWeight *
            Math.abs(variancePercent) /
            100;

        bonusAmount =
            savedWeight *
            ratePerKg;
    }

    const payoutSuggestion = Math.max(
        0,
        basePayout +
        bonusAmount -
        deductionAmount
    );

    const lossStatus = get_loss_status(
        inputWeight,
        lossPercent,
        standardLossPercent
    );

    set_parent_value_if_changed(
        frm,
        'total_output_weight',
        outputWeight
    );

    set_parent_value_if_changed(
        frm,
        'total_waste_weight',
        wasteWeight
    );

    set_parent_value_if_changed(
        frm,
        'loss_weight',
        lossWeight
    );

    set_parent_value_if_changed(
        frm,
        'loss_percent',
        lossPercent
    );

    set_parent_value_if_changed(
        frm,
        'material_addition_weight',
        materialAdditionWeight
    );

    set_parent_value_if_changed(
        frm,
        'material_addition_percent',
        materialAdditionPercent
    );

    set_parent_value_if_changed(
        frm,
        'waste_percent',
        wastePercent
    );

    set_parent_value_if_changed(
        frm,
        'base_payout',
        basePayout
    );

    set_parent_value_if_changed(
        frm,
        'bonus_amount',
        bonusAmount
    );

    set_parent_value_if_changed(
        frm,
        'deduction_amount',
        deductionAmount
    );

    set_parent_value_if_changed(
        frm,
        'payout_suggestion',
        payoutSuggestion
    );

    if (
        frm.is_new() &&
        !flt(frm.doc.payout_given)
    ) {
        set_parent_value_if_changed(
            frm,
            'payout_given',
            payoutSuggestion
        );
    }

    if (
        frm.doc.loss_status !== lossStatus
    ) {
        frm.set_value(
            'loss_status',
            lossStatus
        );
    }

    calculate_payout_variance(frm);
}

function get_loss_status(
    inputWeight,
    lossPercent,
    standardLossPercent
) {
    if (!inputWeight) {
        return '';
    }

    if (
        lossPercent >
        standardLossPercent
    ) {
        return 'Excess Loss';
    }

    return 'OK';
}

function calculate_payout_variance(frm) {
    if (
        !frappe.meta.has_field(
            'Pavtha Receive',
            'payout_variance'
        )
    ) {
        return;
    }

    const variance =
        flt(frm.doc.payout_given) -
        flt(frm.doc.payout_suggestion);

    set_parent_value_if_changed(
        frm,
        'payout_variance',
        variance
    );
}


async function clear_pavtha_issue_details(frm) {
    await frm.set_value({
        company: null,
        batch_no: null,
        process_master: null,
        quality_code: null,
        outsourcer: null,
        total_input_weight: 0,
        rate_per_kg: 0,
        loss_standard_percent: 0,
        used_silver: 0,
        given_silver: 0,
        balance_silver: 0,
        remaining_tar: 0,
        calculated_payout_amount: 0,
        payout_summary: ''
    });

    frm.clear_table('output_items');
    frm.clear_table('waste_items');

    frm.refresh_field('output_items');
    frm.refresh_field('waste_items');

    calculate_pavtha_preview(frm);
}


function set_parent_value_if_changed(
    frm,
    fieldname,
    value
) {
    if (
        !frappe.meta.has_field(
            'Pavtha Receive',
            fieldname
        )
    ) {
        return;
    }

    const currentValue = flt(
        frm.doc[fieldname]
    );

    const nextValue = flt(value);

    if (
        Math.abs(
            currentValue - nextValue
        ) > 0.000001
    ) {
        frm.set_value(
            fieldname,
            nextValue
        );
    }
}


function schedule_pdf_payout_preview(frm) {
    /*
     * Submitted records are updated only through controlled server-side
     * backfill. Opening a submitted document must not make it dirty.
     */
    if (
        frm.doc.docstatus !== 0 ||
        !frm.doc.pavtha_issue ||
        frm.__applying_pdf_payout_preview
    ) {
        return;
    }

    clearTimeout(
        pdfPayoutPreviewTimer
    );

    pdfPayoutPreviewTimer = setTimeout(
        () => {
            fetch_pdf_payout_preview(frm);
        },
        350
    );
}


function fetch_pdf_payout_preview(frm) {
    if (
        frm.__fetching_pdf_payout_preview ||
        frm.__applying_pdf_payout_preview
    ) {
        return;
    }

    frm.__fetching_pdf_payout_preview = true;

    frappe.call({
        method:
            'jari_core.jari_core.doctype.pavtha_receive.pavtha_receive.preview_pdf_payout',

        args: {
            doc: JSON.stringify(frm.doc)
        },

        freeze: false,

        callback(r) {
            const values = r.message || {};

            apply_pdf_payout_preview(
                frm,
                values
            );
        },

        error(error) {
            console.error(
                'Unable to calculate Pavtha reconciliation preview:',
                error
            );
        },

        always() {
            frm.__fetching_pdf_payout_preview = false;
        }
    });
}


async function apply_pdf_payout_preview(
    frm,
    values
) {
    frm.__applying_pdf_payout_preview = true;

    try {
        await set_numeric_field_if_changed(
            frm,
            'used_silver',
            values.used_silver
        );

        await set_numeric_field_if_changed(
            frm,
            'given_silver',
            values.given_silver
        );

        await set_numeric_field_if_changed(
            frm,
            'balance_silver',
            values.balance_silver
        );

        await set_numeric_field_if_changed(
            frm,
            'remaining_tar',
            values.remaining_tar
        );

        await set_numeric_field_if_changed(
            frm,
            'calculated_payout_amount',
            values.calculated_payout_amount
        );

        const summary =
            values.payout_summary || '';

        if (
            (frm.doc.payout_summary || '')
            !== summary
        ) {
            await frm.set_value(
                'payout_summary',
                summary
            );
        }
    } finally {
        frm.__applying_pdf_payout_preview = false;
    }
}


async function set_numeric_field_if_changed(
    frm,
    fieldname,
    value
) {
    if (
        !frappe.meta.has_field(
            'Pavtha Receive',
            fieldname
        )
    ) {
        return;
    }

    const currentValue = flt(
        frm.doc[fieldname]
    );

    const nextValue = flt(value);

    if (
        Math.abs(
            currentValue - nextValue
        ) > 0.000001
    ) {
        await frm.set_value(
            fieldname,
            nextValue
        );
    }
}
