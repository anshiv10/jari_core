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

        if (!row.spindal_peti_entry) return;

        frappe.db.get_doc('Spindal Peti Entry', row.spindal_peti_entry).then(peti => {
            let total_bobbin = flt(peti.bobbin_count || peti.nang);
            let available_bobbin = flt(peti.remaining_bobbin || total_bobbin);

            if (available_bobbin <= 0 || peti.status === 'Fully Consumed') {
                frappe.msgprint('Selected Peti is already fully consumed.');
                frappe.model.set_value(cdt, cdn, 'spindal_peti_entry', '');
                return;
            }

            frappe.call({
                method: 'jari_core.jari_core.doctype.gilit_issue.gilit_issue.get_kasab_product_name',
                callback(r) {
                    let kasab = r.message || 'KASAB';

                    frappe.model.set_value(cdt, cdn, 'peti_no', peti.peti_no || peti.name);
                    frappe.model.set_value(cdt, cdn, 'quality_code', peti.quality_code);
                    frappe.model.set_value(cdt, cdn, 'khata_no', peti.khata_no);
                    frappe.model.set_value(cdt, cdn, 'product', kasab);
                    frappe.model.set_value(cdt, cdn, 'uom', peti.uom || '');
                    frappe.model.set_value(cdt, cdn, 'gross_weight', peti.gross_weight);
                    frappe.model.set_value(cdt, cdn, 'baad_weight', peti.baad_weight);
                    frappe.model.set_value(cdt, cdn, 'net_weight', peti.net_weight);
                    frappe.model.set_value(cdt, cdn, 'total_bobbin', total_bobbin);
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

        if (flt(row.issued_bobbin) > available) {
            frappe.msgprint('Issued Bobbin cannot be greater than Available Bobbin.');
            frappe.model.set_value(cdt, cdn, 'issued_bobbin', 0);
            frappe.model.set_value(cdt, cdn, 'balance_bobbin_after_issue', available);
            return;
        }

        frappe.model.set_value(cdt, cdn, 'balance_bobbin_after_issue', available - flt(row.issued_bobbin));
        calculate_gilit_totals(frm);
    },

    peti_items_remove(frm) {
        calculate_gilit_totals(frm);
    }
});

frappe.ui.form.on('Gilit Metal Water Input', {
    product(frm, cdt, cdn) {
        let row = locals[cdt][cdn];

        if (!row.product) return;

        frappe.model.set_value(cdt, cdn, 'input_date', frm.doc.issue_date || frappe.datetime.get_today());

        frappe.call({
            method: 'jari_core.jari_core.doctype.gilit_issue.gilit_issue.get_product_stock_for_gilit',
            args: {
                company: frm.doc.company,
                department: frm.doc.to_department || 'Gilit',
                product: row.product
            },
            callback(r) {
                if (!r.message) return;

                frappe.model.set_value(cdt, cdn, 'current_stock', r.message.current_stock || 0);
                frappe.model.set_value(cdt, cdn, 'uom', r.message.uom || '');
            }
        });
    },

    issued_aani(frm, cdt, cdn) {
        let row = locals[cdt][cdn];

        if (flt(row.issued_aani) > flt(row.current_stock)) {
            frappe.msgprint('Issued Aani cannot be greater than Current Stock.');
            frappe.model.set_value(cdt, cdn, 'issued_aani', 0);
        }
    },

    metal_water_inputs_add(frm, cdt, cdn) {
        frappe.model.set_value(cdt, cdn, 'input_date', frm.doc.issue_date || frappe.datetime.get_today());
    }
});

function calculate_gilit_totals(frm) {
    let total_peti = 0;
    let total_weight_kg = 0;

    (frm.doc.peti_items || []).forEach(row => {
        if (!row.spindal_peti_entry) return;

        total_peti += 1;

        if (flt(row.total_bobbin) && flt(row.issued_bobbin)) {
            let issued_weight_gm = (flt(row.net_weight) / flt(row.total_bobbin)) * flt(row.issued_bobbin);
            total_weight_kg += issued_weight_gm / 1000;
        }
    });

    frm.set_value('total_peti', total_peti);
    frm.set_value('total_net_weight', total_weight_kg);
}