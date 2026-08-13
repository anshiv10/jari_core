frappe.ui.form.on('Worker Monthly Salary', {
    refresh(frm) {
        configure_salary_grids(frm);

        if (
            frm.doc.docstatus === 0 &&
            frm.is_new()
        ) {
            frm.set_intro(
                __(
                    'Select Worker and Salary Month, then Save. ' +
                    'Salary Formats and calculation rows will be loaded automatically ' +
                    'from the Worker Salary Format configuration.'
                ),
                'blue'
            );
        }

        if (
            frm.doc.docstatus === 0 &&
            !frm.is_new()
        ) {
            frm.add_custom_button(
                __('Refresh Salary Calculation'),
                function () {
                    frappe.call({
                        method:
                            'jari_core.jari_core.doctype.worker_monthly_salary.worker_monthly_salary.refresh_salary_calculation',
                        args: {
                            salary_name:
                                frm.doc.name
                        },
                        freeze: true,
                        freeze_message:
                            __('Refreshing Salary...'),
                        callback() {
                            frm.reload_doc();
                        }
                    });
                }
            );
        }
    },

    worker(frm) {
        frm.clear_table('salary_details');
        frm.clear_table(
            'salary_quality_details'
        );

        frm.refresh_field('salary_details');
        frm.refresh_field(
            'salary_quality_details'
        );
    },

    salary_month(frm) {
        frm.clear_table('salary_details');
        frm.clear_table(
            'salary_quality_details'
        );

        frm.refresh_field('salary_details');
        frm.refresh_field(
            'salary_quality_details'
        );
    }
});


/*
 * Salary calculation rows are generated from the Salary Formats
 * assigned in Worker Master.
 *
 * Users must not manually create or remove structural calculation
 * rows because Salary Format, Salary Detail Key and Quality linkage
 * are maintained by the server.
 */
function configure_salary_grids(frm) {
    const salaryGrid =
        frm.fields_dict.salary_details?.grid;

    const qualityGrid =
        frm.fields_dict.salary_quality_details?.grid;

    if (salaryGrid) {
        salaryGrid.cannot_add_rows = true;
        salaryGrid.cannot_delete_rows = true;

        salaryGrid.wrapper
            .find('.grid-add-row')
            .hide();

        salaryGrid.wrapper
            .find('.grid-remove-rows')
            .hide();
    }

    if (qualityGrid) {
        qualityGrid.cannot_add_rows = true;
        qualityGrid.cannot_delete_rows = true;

        qualityGrid.wrapper
            .find('.grid-add-row')
            .hide();

        qualityGrid.wrapper
            .find('.grid-remove-rows')
            .hide();
    }
}


frappe.ui.form.on('Worker Monthly Salary Detail', {
    source_quantity(frm, cdt, cdn) {
        calculate_salary_detail(
            frm,
            cdt,
            cdn
        );
    },

    rate(frm, cdt, cdn) {
        calculate_salary_detail(
            frm,
            cdt,
            cdn
        );
    },

    extra_amount(frm, cdt, cdn) {
        calculate_salary_detail(
            frm,
            cdt,
            cdn
        );
    },

    salary_details_remove(frm) {
        calculate_salary_totals(frm);
    }
});


frappe.ui.form.on('Worker Salary Quality Detail', {
    source_quantity(frm, cdt, cdn) {
        calculate_quality_row(
            frm,
            cdt,
            cdn
        );
    },

    rate(frm, cdt, cdn) {
        calculate_quality_row(
            frm,
            cdt,
            cdn
        );
    },

    salary_quality_details_remove(frm) {
        calculate_salary_totals(frm);
    }
});


function get_quality_rows(
    frm,
    detail
) {
    return (
        frm.doc.salary_quality_details || []
    ).filter(
        row =>
            row.salary_detail_key
            === detail.salary_detail_key
    );
}


async function calculate_salary_detail(
    frm,
    cdt,
    cdn
) {
    const detail = locals[cdt][cdn];

    if (detail.requires_quality) {
        calculate_salary_totals(frm);
        return;
    }

    const baseAmount =
        flt(detail.source_quantity)
        * flt(detail.rate);

    await frappe.model.set_value(
        cdt,
        cdn,
        'base_amount',
        flt(baseAmount, 2)
    );

    await frappe.model.set_value(
        cdt,
        cdn,
        'final_amount',
        flt(
            baseAmount
            + flt(detail.extra_amount),
            2
        )
    );

    calculate_salary_totals(frm);
}


async function calculate_quality_row(
    frm,
    cdt,
    cdn
) {
    const qualityRow = locals[cdt][cdn];

    await frappe.model.set_value(
        cdt,
        cdn,
        'amount',
        flt(
            flt(qualityRow.source_quantity)
            * flt(qualityRow.rate),
            2
        )
    );

    calculate_salary_totals(frm);
}


function calculate_salary_totals(frm) {
    let baseTotal = 0;
    let extraTotal = 0;
    let grandTotal = 0;

    (frm.doc.salary_details || []).forEach(
        detail => {
            if (detail.requires_quality) {
                const qualityRows =
                    get_quality_rows(
                        frm,
                        detail
                    );

                detail.source_quantity =
                    flt(
                        qualityRows.reduce(
                            (total, row) =>
                                total
                                + flt(
                                    row.source_quantity
                                ),
                            0
                        ),
                        4
                    );

                detail.base_amount =
                    flt(
                        qualityRows.reduce(
                            (total, row) =>
                                total
                                + flt(row.amount),
                            0
                        ),
                        2
                    );

                detail.final_amount =
                    flt(
                        detail.base_amount
                        + flt(
                            detail.extra_amount
                        ),
                        2
                    );
            }

            baseTotal +=
                flt(detail.base_amount);

            extraTotal +=
                flt(detail.extra_amount);

            grandTotal +=
                flt(detail.final_amount);
        }
    );

    frm.refresh_field('salary_details');
    frm.refresh_field(
        'salary_quality_details'
    );

    frm.set_value(
        'base_salary_total',
        flt(baseTotal, 2)
    );

    frm.set_value(
        'extra_amount_total',
        flt(extraTotal, 2)
    );

    frm.set_value(
        'grand_total_salary',
        flt(grandTotal, 2)
    );
}
