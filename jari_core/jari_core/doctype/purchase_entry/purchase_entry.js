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

    price_per_kg(frm, cdt, cdn) {
        calculate_purchase_row(cdt, cdn);
        calculate_purchase_totals(frm);
    },

    gst_percent(frm, cdt, cdn) {
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

    let pricePerKg = flt(row.price_per_kg);
    let gstPercent = flt(row.gst_percent);

    let deduction = gross * (1 - purity / 100);
    let net = gross - deduction;

    let untaxedAmount = pricePerKg * gross;
    let gstAmount = untaxedAmount * gstPercent / 100;
    let amount = untaxedAmount + gstAmount;

    frappe.model.set_value(
        cdt,
        cdn,
        'deduction_weight',
        deduction
    );

    frappe.model.set_value(
        cdt,
        cdn,
        'net_weight',
        net
    );

    frappe.model.set_value(
        cdt,
        cdn,
        'untaxed_amount',
        untaxedAmount
    );

    frappe.model.set_value(
        cdt,
        cdn,
        'amount',
        amount
    );
}

function calculate_purchase_totals(frm) {
    let totalGross = 0;
    let totalDeduction = 0;
    let totalNet = 0;
    let totalAmount = 0;

    (frm.doc.items || []).forEach(row => {
        totalGross += flt(row.gross_weight);
        totalDeduction += flt(row.deduction_weight);
        totalNet += flt(row.net_weight);
        totalAmount += flt(row.amount);
    });

    frm.set_value(
        'total_gross_weight',
        totalGross
    );

    frm.set_value(
        'total_deduction_weight',
        totalDeduction
    );

    frm.set_value(
        'total_net_weight',
        totalNet
    );

    frm.set_value(
        'total_amount',
        totalAmount
    );
}
