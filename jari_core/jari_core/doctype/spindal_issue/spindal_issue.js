console.log("Spindal Issue JS Loaded Successfully");

frappe.ui.form.on('Spindal Issue', {
    refresh(frm) {
        set_product_query_by_department(frm);
        set_process_query_by_department(frm);
        if (!frm.doc.issue_date) frm.set_value('issue_date', frappe.datetime.get_today());

        set_process_query_by_department(frm);

        frm.trigger('set_active_batch_no');
        calculate_spindal_issue_totals(frm);
        refresh_all_stock_summaries(frm);
    },

    after_save(frm) {
        /*
         * Saved Draft rows are now stock reservations.
         * Refresh all stock summaries immediately after Save.
         */
        refresh_all_stock_summaries(frm);
    },

    from_department(frm) {
        set_product_query_by_department(frm);
        refresh_all_stock_summaries(frm);
    },

    to_department(frm) {
        set_product_query_by_department(frm);
        clear_process_if_department_changed(frm);
        set_process_query_by_department(frm);
    },

    company(frm) {
        refresh_all_stock_summaries(frm);
    },

    issue_type(frm) {
        frm.trigger('set_active_batch_no');
    },

    new_batch_no(frm) {
        frm.trigger('set_active_batch_no');
    },

    existing_batch_no(frm) {
        frm.trigger('set_active_batch_no');
    },

    operator(frm) {
        set_operator_in_child_rows(frm);
    },

    set_active_batch_no(frm) {
        frm.set_value(
            'active_batch_no',
            frm.doc.issue_type === 'Re Issue'
                ? (frm.doc.existing_batch_no || '')
                : (frm.doc.new_batch_no || '')
        );
    },

    process_master(frm) {
        if (!frm.doc.process_master) return;

        frappe.db.get_doc('Process Master', frm.doc.process_master).then(p => {
            frm.clear_table('issue_items');

            (p.input_products || []).forEach(row => {
                let product = row.product || row.product_code || row.item || row.item_code || row.input_product;
                if (!product) return;

                let d = frm.add_child('issue_items');
                d.issue_date = frm.doc.issue_date || frappe.datetime.get_today();
                d.product = product;
                d.uom = row.uom || row.unit || 'KG';
                d.weight = 0;
                d.operator_name = frm.doc.operator || '';
                d.current_stock_summary = 'Loading...';
            });

            frm.refresh_field('issue_items');
            refresh_all_stock_summaries(frm);
            calculate_spindal_issue_totals(frm);
        });
    }
});

frappe.ui.form.on('Spindal Issue Item', {
    issue_items_add(frm, cdt, cdn) {
        let rows = frm.doc.issue_items || [];
        let previous = rows.length > 1 ? rows[rows.length - 2] : null;

        frappe.model.set_value(cdt, cdn, 'issue_date', previous?.issue_date || frm.doc.issue_date || frappe.datetime.get_today());
        frappe.model.set_value(cdt, cdn, 'product', previous?.product || '');
        frappe.model.set_value(cdt, cdn, 'uom', previous?.uom || 'KG');
        frappe.model.set_value(cdt, cdn, 'operator_name', previous?.operator_name || frm.doc.operator || '');
        frappe.model.set_value(cdt, cdn, 'weight', 0);

        if (previous?.product) {
            fetch_spindal_stock_summary(frm, cdt, cdn, previous.product);
        }

        calculate_spindal_issue_totals(frm);
    },

    product(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row.product) fetch_spindal_stock_summary(frm, cdt, cdn, row.product);
    },

    weight(frm) {
        calculate_spindal_issue_totals(frm);
    },

    issue_items_remove(frm) {
        calculate_spindal_issue_totals(frm);
    }
});

function fetch_spindal_stock_summary(frm, cdt, cdn, product) {
    if (!product) return;

    frappe.call({
        method: "jari_core.jari_core.doctype.spindal_issue.spindal_issue.get_spindal_stock_summary",
        args: { product: product, company: frm.doc.company || null },
        callback(r) {
            frappe.model.set_value(cdt, cdn, "current_stock_summary", r.message || "No stock available");
        }
    });
}

function refresh_all_stock_summaries(frm) {
    (frm.doc.issue_items || []).forEach(row => {
        if (row.product) fetch_spindal_stock_summary(frm, row.doctype, row.name, row.product);
    });
}

function set_operator_in_child_rows(frm) {
    (frm.doc.issue_items || []).forEach(row => {
        frappe.model.set_value(row.doctype, row.name, 'operator_name', frm.doc.operator || '');
    });
}

function calculate_spindal_issue_totals(frm) {
    let total_weight = 0;
    (frm.doc.issue_items || []).forEach(row => total_weight += flt(row.weight));
    frm.set_value('total_issue_weight', total_weight);
}

function set_process_query_by_department(frm) {
    frm.set_query('process_master', function() {
        return {
            filters: {
                department: frm.doc.to_department || ''
            }
        };
    });
}

function clear_process_if_department_changed(frm) {
    if (frm.doc.process_master) {
        frm.set_value('process_master', '');
    }
}


function set_product_query_by_department(frm) {
    frm.set_query('product', 'issue_items', function() {
        return {
            query: 'jari_core.jari_core.stock_utils.product_query_by_department',
            filters: {
                department: frm.doc.from_department || ''
            }
        };
    });
}


// BEGIN PROCESS-WISE WORKER FILTER: Spindal Issue
frappe.ui.form.on('Spindal Issue', {
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
            'operator',
            'Worker Master'
        );
    }
});


function apply_process_party_queries(frm) {
    
        frm.set_query('operator', function () {
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
// END PROCESS-WISE WORKER FILTER: Spindal Issue
