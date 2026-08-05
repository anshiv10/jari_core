
frappe.ui.form.on('Asarva Issue', {
    refresh(frm) {
        if (!frm.doc.issue_date) {
            frm.set_value(
                'issue_date',
                frappe.datetime.get_today()
            );
        }

        frm.set_query(
            'asarva_outsourcer',
            function () {
                if (!frm.doc.process_master) {
                    return {};
                }

                return {
                    filters: {
                        process_master:
                            frm.doc.process_master
                    }
                };
            }
        );

        calculate_asarva_issue_totals(frm);
    },

    process_master(frm) {
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

            if (!frm.doc.to_department) {
                frm.set_value(
                    'to_department',
                    values.to_department ||
                    'Rangrej/Asarva'
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
