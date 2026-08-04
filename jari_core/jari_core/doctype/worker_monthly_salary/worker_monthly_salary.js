frappe.ui.form.on('Worker Monthly Salary', {
    refresh(frm) {
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
        frm.refresh_field('salary_details');
    },

    salary_month(frm) {
        frm.clear_table('salary_details');
        frm.refresh_field('salary_details');
    }
});


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

    quality_details_remove(frm) {
        calculate_salary_totals(frm);
    }
});


async function calculate_salary_detail(
    frm,
    cdt,
    cdn
) {
    const row = locals[cdt][cdn];

    if (row.requires_quality) {
        calculate_salary_totals(frm);
        return;
    }

    const baseAmount =
        flt(row.source_quantity)
        * flt(row.rate);

    const finalAmount =
        baseAmount
        + flt(row.extra_amount);

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
        flt(finalAmount, 2)
    );

    calculate_salary_totals(frm);
}


async function calculate_quality_row(
    frm,
    cdt,
    cdn
) {
    const row = locals[cdt][cdn];

    await frappe.model.set_value(
        cdt,
        cdn,
        'amount',
        flt(
            flt(row.source_quantity)
            * flt(row.rate),
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
                    detail.quality_details || [];

                const quantity =
                    qualityRows.reduce(
                        (total, row) =>
                            total
                            + flt(
                                row.source_quantity
                            ),
                        0
                    );

                const base =
                    qualityRows.reduce(
                        (total, row) =>
                            total
                            + flt(row.amount),
                        0
                    );

                detail.source_quantity =
                    flt(quantity, 4);

                detail.base_amount =
                    flt(base, 2);

                detail.final_amount =
                    flt(
                        base
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
