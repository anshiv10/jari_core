frappe.ui.form.on('Melting Issue', {
    refresh(frm) {
        setup_melting_issue_child_events(frm);
    }
});

function setup_melting_issue_child_events(frm) {
    let table_field = null;

    (frm.meta.fields || []).forEach(df => {
        if (df.fieldtype === "Table" && !table_field) {
            let key = ((df.fieldname || "") + " " + (df.label || "")).toLowerCase();
            if (key.includes("product") || key.includes("production") || key.includes("item")) {
                table_field = df;
            }
        }
    });

    if (!table_field) {
        table_field = (frm.meta.fields || []).find(df => df.fieldtype === "Table");
    }

    if (!table_field) return;

    let child_dt = table_field.options;

    frappe.ui.form.on(child_dt, {
        product(frm, cdt, cdn) {
            update_product_display_and_stock(frm, cdt, cdn);
        },

        item(frm, cdt, cdn) {
            update_product_display_and_stock(frm, cdt, cdn);
        }
    });
}

function update_product_display_and_stock(frm, cdt, cdn) {
    let row = locals[cdt][cdn];
    let product = row.product || row.item;

    if (!product) return;

    frappe.call({
        method: "jari_core.jari_core.doctype.melting_issue.melting_issue.get_product_display_name",
        args: { product: product },
        callback(r) {
            if (r.message && row.hasOwnProperty("product_name")) {
                frappe.model.set_value(cdt, cdn, "product_name", r.message);
            }
        }
    });

    frappe.call({
        method: "jari_core.jari_core.doctype.melting_issue.melting_issue.get_product_stock_summary",
        args: {
            product: product,
            company: frm.doc.company
        },
        callback(r) {
            if (row.hasOwnProperty("current_stock_summary")) {
                frappe.model.set_value(cdt, cdn, "current_stock_summary", r.message || "");
            }
        }
    });
}
