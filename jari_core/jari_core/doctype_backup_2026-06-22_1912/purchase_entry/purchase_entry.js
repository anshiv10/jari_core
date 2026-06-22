frappe.ui.form.on('Purchase Entry', {
    refresh(frm) {
        if (!frm.doc.purchase_date) {
            frm.set_value('purchase_date', frappe.datetime.get_today());
        }

        if (!frm.doc.department) {
            frm.set_value('department', 'ROOT');
        }

        calculate_purchase_totals(frm);
    }
});

frappe.ui.form.on('Purchase Entry Item', {
    gross_weight(frm, cdt, cdn) {
        calculate_purchase_row(cdt, cdn);
        calculate_purchase_totals(frm);
    },

    purity_percent(frm, cdt, cdn) {
        calculate_purchase_row(cdt, cdn);
        calculate_purchase_totals(frm);
    },

    items_remove(frm) {
        calculate_purchase_totals(frm);
    }
});

function calculate_purchase_row(cdt, cdn) {
    let row = locals[cdt][cdn];

    let gross = flt(row.gross_weight);
    let purity = row.purity_percent === undefined || row.purity_percent === null
        ? 100
        : flt(row.purity_percent);

    let deduction = gross * (1 - purity / 100);
    let net = gross - deduction;

    frappe.model.set_value(cdt, cdn, 'deduction_weight', deduction);
    frappe.model.set_value(cdt, cdn, 'net_weight', net);
}

function calculate_purchase_totals(frm) {
    let total_gross = 0;
    let total_deduction = 0;
    let total_net = 0;

    (frm.doc.items || []).forEach(row => {
        total_gross += flt(row.gross_weight);
        total_deduction += flt(row.deduction_weight);
        total_net += flt(row.net_weight);
    });

    frm.set_value('total_gross_weight', total_gross);
    frm.set_value('total_deduction_weight', total_deduction);
    frm.set_value('total_net_weight', total_net);
}