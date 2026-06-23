console.log("Spindal Issue JS Loaded Successfully");

frappe.ui.form.on('Spindal Issue', {
    refresh(frm) {
        if (!frm.doc.issue_date) {
            frm.set_value('issue_date', frappe.datetime.get_today());
        }

        frm.set_query('process_master', function() {
            return {
                filters: {
                    department: 'SPINDAL'
                }
            };
        });

        frm.trigger('set_active_batch_no');
        calculate_spindal_issue_totals(frm);
        refresh_all_stock_summaries(frm);
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
        if (frm.doc.issue_type === 'Re Issue') {
            frm.set_value('active_batch_no', frm.doc.existing_batch_no || '');
        } else {
            frm.set_value('active_batch_no', frm.doc.new_batch_no || '');
        }
    },

    process_master(frm) {
        if (!frm.doc.process_master) return;

        frappe.db.get_doc('Process Master', frm.doc.process_master).then(p => {
            frm.clear_table('issue_items');

            (p.input_products || []).forEach(row => {
                let product =
                    row.product ||
                    row.product_code ||
                    row.item ||
                    row.item_code ||
                    row.input_product;

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

            (frm.doc.issue_items || []).forEach(row => {
                if (row.product) {
                    fetch_spindal_stock_summary(frm, row.doctype, row.name, row.product);
                }
            });

            calculate_spindal_issue_totals(frm);
        });
    }
});

frappe.ui.form.on('Spindal Issue Item', {
    issue_items_add(frm, cdt, cdn) {
        frappe.model.set_value(cdt, cdn, 'issue_date', frm.doc.issue_date || frappe.datetime.get_today());
        frappe.model.set_value(cdt, cdn, 'operator_name', frm.doc.operator || '');
    },

    product(frm, cdt, cdn) {
        let row = locals[cdt][cdn];

        if (row.product) {
            fetch_spindal_stock_summary(frm, cdt, cdn, row.product);
        }
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
        method: "jari_core.jari_core.doctype.spindal_issue.spindal_issue.get_product_stock_summary",
        args: {
            product: product,
            company: frm.doc.company || null
        },
        callback(r) {
            frappe.model.set_value(
                cdt,
                cdn,
                "current_stock_summary",
                r.message || "No stock available"
            );
        }
    });
}

function refresh_all_stock_summaries(frm) {
    (frm.doc.issue_items || []).forEach(row => {
        if (row.product) {
            fetch_spindal_stock_summary(frm, row.doctype, row.name, row.product);
        }
    });
}

function set_operator_in_child_rows(frm) {
    (frm.doc.issue_items || []).forEach(row => {
        frappe.model.set_value(row.doctype, row.name, 'operator_name', frm.doc.operator || '');
    });
}

function calculate_spindal_issue_totals(frm) {
    let total_weight = 0;

    (frm.doc.issue_items || []).forEach(row => {
        total_weight += flt(row.weight);
    });

    frm.set_value('total_issue_weight', total_weight);
}