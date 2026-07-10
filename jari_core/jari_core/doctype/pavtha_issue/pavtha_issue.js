console.log("Pavtha Issue JS Loaded Successfully");

frappe.ui.form.on('Pavtha Issue', {
    refresh(frm) {\n        set_product_query_by_department(frm);
        set_process_query_by_department(frm);
        if (!frm.doc.issue_date) {
            frm.set_value('issue_date', frappe.datetime.get_today());
        }

        refresh_all_stock_summaries(frm);
    },

    to_department(frm) {\n        set_product_query_by_department(frm);
        clear_process_if_department_changed(frm);
        set_process_query_by_department(frm);
    },

    company(frm) {
        refresh_all_stock_summaries(frm);
    },

    process_master(frm) {
        fetch_process_items(frm);
    }
});

frappe.ui.form.on('Pavtha Issue Item', {
    product(frm, cdt, cdn) {
        let row = locals[cdt][cdn];

        if (row.product) {
            fetch_stock_summary(frm, cdt, cdn, row.product);
        }
    },

    weight(frm) {
        calculate_total_issue_weight(frm);
    },

    issue_items_remove(frm) {
        calculate_total_issue_weight(frm);
    }
});

function fetch_process_items(frm) {
    if (!frm.doc.process_master) {
        return;
    }

    frappe.db.get_doc('Process Master', frm.doc.process_master).then(p => {
        frm.clear_table('issue_items');

        let rows = p.input_products || [];

        if (!rows.length) {
            frappe.msgprint("No Input Products found in selected Process Master.");
            frm.refresh_field('issue_items');
            return;
        }

        rows.forEach(row => {
            let product =
                row.product ||
                row.product_code ||
                row.item ||
                row.item_code ||
                row.input_product;

            let uom =
                row.uom ||
                row.unit ||
                row.default_uom ||
                "KG";

            if (!product) return;

            let d = frm.add_child('issue_items');
            d.product = product;
            d.uom = uom;
            d.weight = row.weight || row.qty || row.input_weight || 0;
            d.current_stock_summary = "Loading...";
        });

        frm.refresh_field('issue_items');

        (frm.doc.issue_items || []).forEach(row => {
            if (row.product) {
                fetch_stock_summary(frm, row.doctype, row.name, row.product);
            }
        });

        calculate_total_issue_weight(frm);
    });
}

function fetch_stock_summary(frm, cdt, cdn, product) {
    if (!product) return;

    frappe.call({
        method: "jari_core.jari_core.doctype.pavtha_issue.pavtha_issue.get_product_stock_summary",
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
            fetch_stock_summary(frm, row.doctype, row.name, row.product);
        }
    });
}

function calculate_total_issue_weight(frm) {
    let total = 0;

    (frm.doc.issue_items || []).forEach(row => {
        total += flt(row.weight);
    });

    frm.set_value('total_issue_weight', total);
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
\n
function set_product_query_by_department(frm) {
    frm.set_query('product', 'issue_items', function() {
        return {
            query: 'jari_core.jari_core.stock_utils.product_query_by_department',
            filters: {
                department: frm.doc.to_department || ''
            }
        };
    });
}
