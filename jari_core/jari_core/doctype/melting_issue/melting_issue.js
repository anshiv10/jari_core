console.log("Melting Issue JS Loaded Successfully");

frappe.ui.form.on('Melting Issue', {
    refresh(frm) {
        if (!frm.doc.issue_date) {
            frm.set_value('issue_date', frappe.datetime.get_today());
        }
    },

    process_master(frm) {
        fetch_process_items(frm);
    }
});

frappe.ui.form.on('Melting Issue Item', {
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
        });

        frm.refresh_field('issue_items');
        calculate_total_issue_weight(frm);
    });
}

function calculate_total_issue_weight(frm) {
    let total = 0;

    (frm.doc.issue_items || []).forEach(row => {
        total += flt(row.weight);
    });

    frm.set_value('total_issue_weight', total);
}