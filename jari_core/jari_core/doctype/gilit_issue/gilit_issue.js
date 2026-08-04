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

        refresh_all_metal_water_stock(frm);
        calculate_gilit_totals(frm);
    },

    company(frm) {
        refresh_all_metal_water_stock(frm);
    },

    to_department(frm) {
        refresh_all_metal_water_stock(frm);
    },

    issue_date(frm) {
        (frm.doc.metal_water_inputs || []).forEach(row => {
            if (!row.input_date) {
                frappe.model.set_value(row.doctype, row.name, 'input_date', frm.doc.issue_date);
            }
        });
    }
});

frappe.ui.form.on('Gilit Issue Peti Item', {
    spindal_peti_entry(frm, cdt, cdn) {
        let row = locals[cdt][cdn];

        if (!row.spindal_peti_entry) {
            row.quality_code = '';
            sync_gilit_quality(frm);
            return;
        }

        frappe.db.get_doc('Spindal Peti Entry', row.spindal_peti_entry).then(peti => {
            let total_bobbin = flt(peti.bobbin_count || peti.nang);
            let available_bobbin = flt(peti.remaining_bobbin || total_bobbin);

            if (available_bobbin <= 0 || peti.status === 'Fully Consumed') {
                frappe.msgprint('Selected Peti is already fully consumed.');
                frappe.model.set_value(cdt, cdn, 'spindal_peti_entry', '');
                return;
            }

            const peti_quality = peti.quality_code || peti.quality || '';

            if (!peti_quality) {
                frappe.msgprint(
                    `Quality is missing in Spindal Peti ${peti.name}.`
                );
                frappe.model.set_value(
                    cdt,
                    cdn,
                    'spindal_peti_entry',
                    ''
                );
                return;
            }

            if (
                frm.doc.quality_code &&
                frm.doc.quality_code !== peti_quality
            ) {
                frappe.msgprint({
                    title: __('Quality Mismatch'),
                    indicator: 'red',
                    message: __(
                        `Selected Peti ${peti.name} has Quality ` +
                        `${peti_quality}, while this Gilit Issue is ` +
                        `already using Quality ${frm.doc.quality_code}.`
                    )
                });

                frappe.model.set_value(
                    cdt,
                    cdn,
                    'spindal_peti_entry',
                    ''
                );

                return;
            }

            if (!frm.doc.quality_code) {
                frm.set_value(
                    'quality_code',
                    peti_quality
                );
            }

            frappe.call({
                method: 'jari_core.jari_core.doctype.gilit_issue.gilit_issue.get_kasab_product_name',
                callback(r) {
                    let kasab = r.message || 'KASAB';

                    frappe.model.set_value(cdt, cdn, 'peti_no', peti.peti_no || peti.name);
                    frappe.model.set_value(
                        cdt,
                        cdn,
                        'quality_code',
                        peti_quality
                    );
                    frappe.model.set_value(cdt, cdn, 'khata_no', peti.khata_no);
                    frappe.model.set_value(cdt, cdn, 'product', kasab);
                    frappe.model.set_value(cdt, cdn, 'uom', peti.uom || 'gram');
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
        sync_gilit_quality(frm);
        calculate_gilit_totals(frm);
    }
});

frappe.ui.form.on('Gilit Metal Water Input', {
    product(frm, cdt, cdn) {
        set_metal_water_stock(frm, cdt, cdn);
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

function set_metal_water_stock(frm, cdt, cdn) {
    let row = locals[cdt][cdn];

    if (!frm.doc.company || !row.product) {
        return;
    }

    frappe.call({
        method: 'jari_core.jari_core.doctype.gilit_issue.gilit_issue.get_product_stock_for_gilit',
        args: {
            company: frm.doc.company,
            product: row.product,
            department: frm.doc.to_department || 'Gilit'
        },
        callback(r) {
            if (!r.message) return;

            frappe.model.set_value(cdt, cdn, 'current_stock', flt(r.message.current_stock));

            if (r.message.uom) {
                frappe.model.set_value(cdt, cdn, 'uom', r.message.uom);
            }

            if (r.message.product) {
                frappe.model.set_value(cdt, cdn, 'product', r.message.product);
            }

            frm.refresh_field('metal_water_inputs');
        }
    });
}

function refresh_all_metal_water_stock(frm) {
    (frm.doc.metal_water_inputs || []).forEach(row => {
        if (row.product) {
            set_metal_water_stock(frm, row.doctype, row.name);
        }
    });
}

function sync_gilit_quality(frm) {
    const qualities = [
        ...new Set(
            (frm.doc.peti_items || [])
                .filter(row => row.spindal_peti_entry && row.quality_code)
                .map(row => row.quality_code)
        )
    ];

    if (qualities.length === 0) {
        frm.set_value('quality_code', '');
        return;
    }

    if (qualities.length === 1) {
        frm.set_value('quality_code', qualities[0]);
    }
}


function calculate_gilit_totals(frm) {
    let total_peti = 0;
    let total_weight_kg = 0;

    (frm.doc.peti_items || []).forEach(row => {
        if (!row.spindal_peti_entry) return;

        total_peti += 1;

        if (flt(row.total_bobbin) && flt(row.issued_bobbin)) {
            let net_weight = flt(row.net_weight);
            let uom = (row.uom || '').toLowerCase();

            if (['kg', 'kilogram', 'kilograms'].includes(uom)) {
                net_weight = net_weight * 1000;
            }

            let issued_weight_gm = (net_weight / flt(row.total_bobbin)) * flt(row.issued_bobbin);
            total_weight_kg += issued_weight_gm / 1000;
        }
    });

    frm.set_value('total_peti', total_peti);
    frm.set_value('total_net_weight', total_weight_kg);
}

// BEGIN PROCESS-WISE WORKER FILTER: Gilit Issue
frappe.ui.form.on('Gilit Issue', {
    setup(frm) {
        apply_process_party_queries(frm);
    },

    refresh(frm) {
        apply_process_party_queries(frm);
    },

    process_master(frm) {
        apply_process_party_queries(frm);
        
        validate_selected_process_party(
            frm,
            'gilit_karigar',
            'Worker Master'
        );
    }
});


function apply_process_party_queries(frm) {
    
        frm.set_query('gilit_karigar', function () {
            if (!frm.doc.process_master) {
                return {
                    filters: {
                        name: '__NO_PROCESS_SELECTED__'
                    }
                };
            }

            return {
                filters: {
                    process_master: frm.doc.process_master,
                    active: 1
                }
            };
        });
}


async function validate_selected_process_party(
    frm,
    fieldname,
    master_doctype
) {
    const selectedName =
        frm.doc[fieldname];

    if (!selectedName) {
        return;
    }

    if (!frm.doc.process_master) {
        await frm.set_value(
            fieldname,
            ''
        );

        return;
    }

    try {
        const result =
            await frappe.db.get_value(
                master_doctype,
                selectedName,
                [
                    'process_master',
                    'active'
                ]
            );

        const record =
            result.message || {};

        const processMismatch =
            record.process_master !==
            frm.doc.process_master;

        const inactiveWorker =
            master_doctype === 'Worker Master' &&
            cint(record.active) !== 1;

        if (
            processMismatch ||
            inactiveWorker
        ) {
            await frm.set_value(
                fieldname,
                ''
            );

            frappe.show_alert({
                message: __(
                    'Selection cleared because it does not belong to the selected Process or is inactive.'
                ),
                indicator: 'orange'
            });
        }
    } catch (error) {
        console.error(
            `Unable to validate ${fieldname}:`,
            error
        );
    }
}
// END PROCESS-WISE WORKER FILTER: Gilit Issue
