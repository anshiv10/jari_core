console.log("Gilit Issue JS Loaded Successfully");

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
                    status: ['!=', 'Fully Consumed'],
                    remaining_bobbin: ['>', 0]
                }
            };
        });

        calculate_gilit_totals(frm);
    }
});

frappe.ui.form.on('Gilit Issue Peti Item', {
    spindal_peti_entry(frm, cdt, cdn) {
        let row = locals[cdt][cdn];

        if (!row.spindal_peti_entry) {
            return;
        }

        frappe.db.get_doc('Spindal Peti Entry', row.spindal_peti_entry).then(peti => {
            let available_bobbin = flt(peti.remaining_bobbin || peti.bobbin_count);

            if (available_bobbin <= 0 || peti.status === 'Fully Consumed') {
                frappe.msgprint('Selected Peti is already fully consumed.');
                frappe.model.set_value(cdt, cdn, 'spindal_peti_entry', '');
                return;
            }

            frappe.call({
                method: 'jari_core.jari_core.doctype.gilit_issue.gilit_issue.get_kasab_product_name',
                callback(r) {
                    let kasab = r.message || 'KASAB';

                    frappe.model.set_value(cdt, cdn, 'peti_no', peti.name);
                    frappe.model.set_value(cdt, cdn, 'quality_code', peti.quality_code);
                    frappe.model.set_value(cdt, cdn, 'khata_no', peti.khata_no);
                    frappe.model.set_value(cdt, cdn, 'product', kasab);
                    frappe.model.set_value(cdt, cdn, 'uom', 'KG');
                    frappe.model.set_value(cdt, cdn, 'gross_weight', peti.gross_weight);
                    frappe.model.set_value(cdt, cdn, 'baad_weight', peti.baad_weight);
                    frappe.model.set_value(cdt, cdn, 'net_weight', peti.net_weight);
                    frappe.model.set_value(cdt, cdn, 'total_bobbin', peti.bobbin_count);
                    frappe.model.set_value(cdt, cdn, 'available_bobbin', available_bobbin);
                    frappe.model.set_value(cdt, cdn, 'balance_bobbin_after_issue', available_bobbin);
                    frappe.model.set_value(cdt, cdn, 'operator_name', peti.operator);

                    calculate_gilit_totals(frm);
                }
            });
        });
    },

    issued_bobbin(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        let available = flt(row.available_bobbin);

        if (!available) {
            frappe.msgprint('Please select Spindal Peti Entry first so Available Bobbin can be fetched.');
            frappe.model.set_value(cdt, cdn, 'issued_bobbin', 0);
            return;
        }

        if (flt(row.issued_bobbin) <= 0) {
            frappe.model.set_value(cdt, cdn, 'balance_bobbin_after_issue', available);
            calculate_gilit_totals(frm);
            return;
        }

        if (flt(row.issued_bobbin) > available) {
            frappe.msgprint('Issued Bobbin cannot be greater than Available Bobbin.');
            frappe.model.set_value(cdt, cdn, 'issued_bobbin', 0);
            frappe.model.set_value(cdt, cdn, 'balance_bobbin_after_issue', available);
            return;
        }

        frappe.model.set_value(
            cdt,
            cdn,
            'balance_bobbin_after_issue',
            available - flt(row.issued_bobbin)
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
        if (!row.spindal_peti_entry) return;

        total_peti += 1;

        if (flt(row.total_bobbin) && flt(row.issued_bobbin)) {
            total_weight += (flt(row.net_weight) / flt(row.total_bobbin)) * flt(row.issued_bobbin);
        }
    });

    frm.set_value('total_peti', total_peti);
    frm.set_value('total_net_weight', total_weight);
}