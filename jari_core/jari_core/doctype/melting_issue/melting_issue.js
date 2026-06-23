console.log("Melting Issue JS Loaded Successfully");

frappe.ui.form.on('Melting Issue', {
    refresh(frm) {
        if (!frm.doc.issue_date) {
            frm.set_value('issue_date', frappe.datetime.get_today());
        }

        refresh_all_stock_summaries(frm);
    },

    company(frm) {
        refresh_all_stock_summaries(frm);
    },

    process_master(frm) {
        fetch_process_items(frm);
    }
});

frappe.ui.form.on('Melting Issue Item', {
    product(frm, cdt, cdn) {
        let row = locals[cdt][cdn];

        if (row.product) {
            fetch_product_display_name(cdt, cdn, row.product);
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
        console.log("Fetched Process Master:", p);

        frm.clear_table('issue_items');

        let rows = p.input_products || [];

        if (!rows.length) {
            frappe.msgprint("No Input Products found in selected Process Master.");
            frm.refresh_field('issue_items');
            return;
        }

        rows.forEach(row => {
            console.log("Input Product Row:", row);

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

            if (!product) {
                console.warn("Skipped row because product field was not found:", row);
                return;
            }

            let d = frm.add_child('issue_items');

            d.product = product;
            d.product_name = row.product_name || product;
            d.uom = uom;
            d.weight = row.weight || row.qty || row.input_weight || 0;
            d.current_stock_summary = "Loading...";
        });

        frm.refresh_field('issue_items');

        (frm.doc.issue_items || []).forEach(row => {
            if (row.product) {
                fetch_product_display_name(row.doctype, row.name, row.product);
                fetch_stock_summary(frm, row.doctype, row.name, row.product);
            }
        });

        calculate_total_issue_weight(frm);
    });
}

function fetch_product_display_name(cdt, cdn, product) {
    if (!product) return;

    frappe.call({
        method: "jari_core.jari_core.doctype.melting_issue.melting_issue.get_product_display_name",
        args: {
            product: product
        },
        callback(r) {
            if (r.message) {
                frappe.model.set_value(cdt, cdn, "product_name", r.message);
            }
        }
    });
}

function fetch_stock_summary(frm, cdt, cdn, product) {
    if (!product) return;

    frappe.call({
        method: "jari_core.jari_core.doctype.melting_issue.melting_issue.get_product_stock_summary",
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