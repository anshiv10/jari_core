console.log("Taniya Issue JS Loaded Successfully");

frappe.ui.form.on('Taniya Issue', {
    refresh(frm) {
        if (!frm.doc.issue_date) frm.set_value('issue_date', frappe.datetime.get_today());

        frm.set_query('process_master', () => ({ filters: { department: 'TANIYA' } }));

        frm.trigger('set_batch_no');
        calculate_taniya_issue_totals(frm);
        refresh_all_stock_summaries(frm);
    },

    company(frm) {
        refresh_all_stock_summaries(frm);
    },

    new_batch_no(frm) {
        frm.trigger('set_batch_no');
    },

    operator(frm) {
        set_operator_in_child_rows(frm);
    },

    set_batch_no(frm) {
        frm.set_value('batch_no', frm.doc.new_batch_no || '');

        if (!frm.doc.new_batch_no) {
            frm.set_value('issue_type', 'New Batch');
            return;
        }

        frappe.db.count('Taniya Issue', {
            filters: {
                batch_no: frm.doc.new_batch_no,
                docstatus: 1,
                name: ['!=', frm.doc.name || '']
            }
        }).then(count => {
            frm.set_value('issue_type', count > 0 ? 'Re Issue' : 'New Batch');
        });
    },

    process_master(frm) {
        if (!frm.doc.process_master) return;

        frappe.db.get_doc('Process Master', frm.doc.process_master).then(p => {
            frm.clear_table('issue_items');

            (p.input_products || []).forEach(row => {
                let d = frm.add_child('issue_items');
                d.issue_date = frm.doc.issue_date || frappe.datetime.get_today();
                d.product = row.product;
                d.uom = row.uom || 'KG';
                d.weight = 0;
                d.operator_name = frm.doc.operator || '';
                d.current_stock_summary = 'Loading...';
            });

            frm.refresh_field('issue_items');
            refresh_all_stock_summaries(frm);
            calculate_taniya_issue_totals(frm);
        });
    }
});

frappe.ui.form.on('Taniya Issue Item', {
    issue_items_add(frm, cdt, cdn) {
        let rows = frm.doc.issue_items || [];
        let previous = rows.length > 1 ? rows[rows.length - 2] : null;

        frappe.model.set_value(cdt, cdn, 'issue_date', previous?.issue_date || frm.doc.issue_date || frappe.datetime.get_today());
        frappe.model.set_value(cdt, cdn, 'product', previous?.product || '');
        frappe.model.set_value(cdt, cdn, 'uom', previous?.uom || 'KG');
        frappe.model.set_value(cdt, cdn, 'operator_name', previous?.operator_name || frm.doc.operator || '');
        frappe.model.set_value(cdt, cdn, 'weight', 0);

        if (previous?.product) {
            fetch_taniya_stock_summary(frm, cdt, cdn, previous.product);
        }

        calculate_taniya_issue_totals(frm);
    },

    product(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row.product) fetch_taniya_stock_summary(frm, cdt, cdn, row.product);
    },

    weight(frm) {
        calculate_taniya_issue_totals(frm);
    },

    issue_items_remove(frm) {
        calculate_taniya_issue_totals(frm);
    }
});

function fetch_taniya_stock_summary(frm, cdt, cdn, product) {
    if (!product) return;

    frappe.call({
        method: "jari_core.jari_core.doctype.taniya_issue.taniya_issue.get_product_stock_summary",
        args: { product: product, company: frm.doc.company || null },
        callback(r) {
            frappe.model.set_value(cdt, cdn, "current_stock_summary", r.message || "No stock available");
        }
    });
}

function refresh_all_stock_summaries(frm) {
    (frm.doc.issue_items || []).forEach(row => {
        if (row.product) fetch_taniya_stock_summary(frm, row.doctype, row.name, row.product);
    });
}

function set_operator_in_child_rows(frm) {
    (frm.doc.issue_items || []).forEach(row => {
        frappe.model.set_value(row.doctype, row.name, 'operator_name', frm.doc.operator || '');
    });
}

function calculate_taniya_issue_totals(frm) {
    let total = 0;
    (frm.doc.issue_items || []).forEach(row => total += flt(row.weight));
    frm.set_value('total_issue_weight', total);
}