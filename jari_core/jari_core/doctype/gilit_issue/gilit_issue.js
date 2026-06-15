frappe.ui.form.on('Gilit Issue', {
    refresh(frm) {
        if (!frm.doc.issue_date) {
            frm.set_value('issue_date', frappe.datetime.get_today());
        }

        if (!frm.doc.from_department) {
            frm.set_value('from_department', 'SPINDAL');
        }

        if (!frm.doc.to_department) {
            frm.set_value('to_department', 'Gilit');
        }

        frm.set_query('spindal_peti_entry', 'peti_items', function() {
            return {
                filters: {
                    docstatus: 1,
                    status: ['!=', 'Fully Consumed']
                }
            };
        });

        calculate_gilit_totals(frm);
    }
});

frappe.ui.form.on('Gilit Issue Peti Item', {
    spindal_peti_entry(frm, cdt, cdn) {
        let row = locals[cdt][cdn];

        if (!row.spindal_peti_entry) return;

        frappe.db.get_doc('Spindal Peti Entry', row.spindal_peti_entry).then(peti => {
            frappe.model.set_value(cdt, cdn, 'peti_no', peti.name);
            frappe.model.set_value(cdt, cdn, 'quality_code', peti.quality_code);
            frappe.model.set_value(cdt, cdn, 'khata_no', peti.khata_no);
            frappe.model.set_value(cdt, cdn, 'product', 'KASAB');
            frappe.model.set_value(cdt, cdn, 'uom', 'KG');
            frappe.model.set_value(cdt, cdn, 'gross_weight', peti.gross_weight);
            frappe.model.set_value(cdt, cdn, 'baad_weight', peti.baad_weight);
            frappe.model.set_value(cdt, cdn, 'net_weight', peti.net_weight);
            frappe.model.set_value(cdt, cdn, 'total_bobbin', peti.bobbin_count);
            frappe.model.set_value(cdt, cdn, 'available_bobbin', peti.remaining_bobbin);
            frappe.model.set_value(cdt, cdn, 'balance_bobbin_after_issue', peti.remaining_bobbin);
            frappe.model.set_value(cdt, cdn, 'operator_name', peti.operator);

            calculate_gilit_totals(frm);
        });
    },

    issued_bobbin(frm, cdt, cdn) {
        let row = locals[cdt][cdn];

        if (flt(row.issued_bobbin) > flt(row.available_bobbin)) {
            frappe.msgprint('Issued Bobbin cannot be greater than Available Bobbin.');
            frappe.model.set_value(cdt, cdn, 'issued_bobbin', 0);
            return;
        }

        frappe.model.set_value(
            cdt,
            cdn,
            'balance_bobbin_after_issue',
            flt(row.available_bobbin) - flt(row.issued_bobbin)
        );

        calculate_gilit_totals(frm);
    },

    peti_items_remove(frm) {
        calculate_gilit_totals(frm);
    }
});

function calculate_gilit_totals(frm) {
    let total_peti = 0;
    let total_weight = 0;

    (frm.doc.peti_items || []).forEach(row => {
        total_peti += 1;

        if (flt(row.total_bobbin) && flt(row.issued_bobbin)) {
            total_weight += (flt(row.net_weight) / flt(row.total_bobbin)) * flt(row.issued_bobbin);
        }
    });

    frm.set_value('total_peti', total_peti);
    frm.set_value('total_net_weight', total_weight);
}
