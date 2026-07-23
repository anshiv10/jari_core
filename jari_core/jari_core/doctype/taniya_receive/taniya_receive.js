console.log("Taniya Receive JS Loaded Successfully");

frappe.ui.form.on('Taniya Receive', {
    refresh(frm) {
        if (!frm.doc.receive_date) {
            frm.set_value('receive_date', frappe.datetime.get_today());
        }

        frm.set_query('taniya_issue', function() {
            return {
                query: 'jari_core.jari_core.doctype.taniya_receive.taniya_receive.taniya_issue_query'
            };
        });
    },

    taniya_issue(frm) {
        if (!frm.doc.taniya_issue) return;

        frappe.call({
            method: 'frappe.client.get',
            args: {
                doctype: 'Taniya Issue',
                name: frm.doc.taniya_issue
            },
            callback(r) {
                const issue = r.message;
                if (!issue) return;

                frm.set_value('company', issue.company);
                frm.set_value('batch_no', issue.batch_no);
                frm.set_value('process_master', issue.process_master);
                frm.set_value('quality_code', issue.quality_code);
                frm.set_value('operator', issue.operator);

                frappe.call({
                    method: 'frappe.client.get_list',
                    args: {
                        doctype: 'Taniya Issue',
                        filters: {
                            batch_no: issue.batch_no,
                            docstatus: ['in', [0, 1]]
                        },
                        fields: ['name', 'total_issue_weight'],
                        limit_page_length: 500
                    },
                    callback(ir) {
                        let total = 0;
                        (ir.message || []).forEach(x => {
                            total += flt(x.total_issue_weight);
                        });
                        frm.set_value('total_input_weight', total);
                    }
                });

                frappe.call({
                    method: 'frappe.client.get',
                    args: {
                        doctype: 'Process Master',
                        name: issue.process_master
                    },
                    callback(pr) {
                        const p = pr.message;
                        if (!p) return;

                        frm.clear_table('output_items');
                        frm.clear_table('waste_items');

                        /*
                         * Prevent manual-row copy logic from running while
                         * Process Master rows are being generated.
                         */
                        frm.__loading_taniya_process_rows = true;

                        (p.output_products || []).forEach(row => {
                            let product = row.product || row.product_code || row.item || row.item_code || row.output_product;
                            let d = frm.add_child('output_items');
                            d.receive_date = frm.doc.receive_date || frappe.datetime.get_today();
                            d.operator_name = frm.doc.operator;
                            d.product = product;
                            d.product_name = row.product_name || product;
                            d.uom = row.uom || row.unit || 'KG';
                        });

                        (p.custom_waste_product_items || []).forEach(row => {
                            let waste_product = row.waste_product || row.product || row.product_code || row.item || row.item_code;
                            let d = frm.add_child('waste_items');
                            d.receive_date = frm.doc.receive_date || frappe.datetime.get_today();
                            d.operator_name = frm.doc.operator;
                            d.waste_product = waste_product;
                            d.product_name = row.product_name || waste_product;
                            d.uom = row.uom || row.unit || 'KG';
                        });

                        frm.__loading_taniya_process_rows = false;

                        frm.refresh_field('output_items');
                        frm.refresh_field('waste_items');
                        set_all_product_names(frm);
                    }
                });
            }
        });
    }
});

frappe.ui.form.on('Taniya Output Item', {
    async output_items_add(frm, cdt, cdn) {
        if (frm.__loading_taniya_process_rows) {
            return;
        }

        const previousRow = get_previous_child_row(
            frm,
            'output_items',
            cdn
        );

        if (previousRow) {
            await set_child_values(cdt, cdn, {
                operator_name: previousRow.operator_name,
                receive_date: previousRow.receive_date,
                product: previousRow.product,
                product_name: previousRow.product_name,
                uom: previousRow.uom,
                weight: 0,
                approx_silver_weight: 0
            });
        } else {
            await set_child_values(cdt, cdn, {
                receive_date:
                    frm.doc.receive_date ||
                    frappe.datetime.get_today(),
                operator_name: frm.doc.operator,
                weight: 0,
                approx_silver_weight: 0
            });
        }
    },

    product(frm, cdt, cdn) {
        set_product_name(cdt, cdn, 'product');
    }
});

frappe.ui.form.on('Taniya Waste Item', {
    async waste_items_add(frm, cdt, cdn) {
        if (frm.__loading_taniya_process_rows) {
            return;
        }

        const previousRow = get_previous_child_row(
            frm,
            'waste_items',
            cdn
        );

        if (previousRow) {
            await set_child_values(cdt, cdn, {
                operator_name: previousRow.operator_name,
                receive_date: previousRow.receive_date,
                waste_product: previousRow.waste_product,
                product_name: previousRow.product_name,
                uom: previousRow.uom,
                weight: 0,
                approx_silver_weight: 0
            });
        } else {
            await set_child_values(cdt, cdn, {
                receive_date:
                    frm.doc.receive_date ||
                    frappe.datetime.get_today(),
                operator_name: frm.doc.operator,
                weight: 0,
                approx_silver_weight: 0
            });
        }
    },

    waste_product(frm, cdt, cdn) {
        set_product_name(cdt, cdn, 'waste_product');
    }
});


function get_previous_child_row(
    frm,
    tableFieldname,
    currentRowName
) {
    const rows = frm.doc[tableFieldname] || [];

    const currentIndex = rows.findIndex(
        row => row.name === currentRowName
    );

    if (currentIndex <= 0) {
        return null;
    }

    return rows[currentIndex - 1];
}


async function set_child_values(
    cdt,
    cdn,
    values
) {
    for (const [fieldname, value] of Object.entries(values)) {
        await frappe.model.set_value(
            cdt,
            cdn,
            fieldname,
            value ?? null
        );
    }
}


function set_all_product_names(frm) {
    (frm.doc.output_items || []).forEach(row => {
        if (row.product) set_product_name(row.doctype, row.name, 'product');
    });

    (frm.doc.waste_items || []).forEach(row => {
        if (row.waste_product) set_product_name(row.doctype, row.name, 'waste_product');
    });
}

function set_product_name(cdt, cdn, product_field) {
    let row = locals[cdt][cdn];
    let product = row[product_field];

    if (!product) {
        frappe.model.set_value(cdt, cdn, 'product_name', '');
        return;
    }

    frappe.db.get_value('Product Master', product, 'product_name').then(r => {
        frappe.model.set_value(cdt, cdn, 'product_name', (r.message && r.message.product_name) || product);
    });
}