console.log('Pavtha Issue JS Loaded Successfully');

frappe.ui.form.on('Pavtha Issue', {
    setup(frm) {
        set_product_query_by_department(frm);
        set_process_query_by_department(frm);
    },

    refresh(frm) {
        set_product_query_by_department(frm);
        set_process_query_by_department(frm);

        if (frm.is_new() && !frm.doc.issue_date) {
            frm.set_value(
                'issue_date',
                frappe.datetime.get_today()
            );
        }

        set_default_type_on_existing_issue_items(frm);
        refresh_all_stock_summaries(frm);
        calculate_total_issue_weight(frm);
    },

    to_department(frm) {
        clear_process_if_department_changed(frm);
        set_product_query_by_department(frm);
        set_process_query_by_department(frm);
    },

    company(frm) {
        refresh_all_stock_summaries(frm);
    },

    process_master(frm) {
        fetch_process_items(frm);
    },

    outsourcer(frm) {
        synchronize_issue_item_types(frm);
    }
});


frappe.ui.form.on('Pavtha Issue Item', {
    issue_items_add(frm, cdt, cdn) {
        const row = frappe.get_doc(
            cdt,
            cdn
        );

        if (!row.issue_receive_type) {
            frappe.model.set_value(
                cdt,
                cdn,
                'issue_receive_type',
                get_pavtha_transaction_type(frm)
            );
        }
    },

    product(frm, cdt, cdn) {
        const row = frappe.get_doc(
            cdt,
            cdn
        );

        if (row.product) {
            fetch_stock_summary(
                frm,
                cdt,
                cdn,
                row.product
            );
        }
    },

    weight(frm) {
        calculate_total_issue_weight(frm);
    },

    issue_items_remove(frm) {
        calculate_total_issue_weight(frm);
    }
});


async function fetch_process_items(frm) {
    if (!frm.doc.process_master) {
        frm.clear_table('issue_items');
        frm.refresh_field('issue_items');
        calculate_total_issue_weight(frm);
        return;
    }

    try {
        const process = await frappe.db.get_doc(
            'Process Master',
            frm.doc.process_master
        );

        frm.clear_table('issue_items');

        const inputRows =
            process.input_products || [];

        const transactionType =
            get_pavtha_transaction_type(frm);

        if (!inputRows.length) {
            frm.refresh_field('issue_items');

            frappe.msgprint({
                title: __('Process Master'),
                message: __(
                    'No input products were found in the selected Process Master.'
                ),
                indicator: 'orange'
            });

            calculate_total_issue_weight(frm);
            return;
        }

        inputRows.forEach(sourceRow => {
            const product =
                sourceRow.product ||
                sourceRow.product_code ||
                sourceRow.item ||
                sourceRow.item_code ||
                sourceRow.input_product;

            const uom =
                sourceRow.uom ||
                sourceRow.unit ||
                sourceRow.default_uom ||
                'KG';

            if (!product) {
                return;
            }

            const child = frm.add_child(
                'issue_items',
                {
                    product: product,
                    uom: uom,
                    weight: flt(
                        sourceRow.weight ||
                        sourceRow.qty ||
                        sourceRow.input_weight
                    ),
                    issue_receive_type:
                        transactionType,
                    current_stock_summary:
                        __('Loading...')
                }
            );

            fetch_stock_summary(
                frm,
                child.doctype,
                child.name,
                child.product
            );
        });

        frm.refresh_field('issue_items');
        calculate_total_issue_weight(frm);

        frappe.show_alert({
            message:
                __('Pavtha input products were loaded.'),
            indicator: 'green'
        });
    } catch (error) {
        console.error(
            'Unable to load Pavtha process items:',
            error
        );

        frappe.msgprint({
            title: __('Unable to Load Process'),
            message: __(
                'The selected Process Master could not be loaded. Check the browser console and server logs.'
            ),
            indicator: 'red'
        });
    }
}


function get_pavtha_transaction_type(frm) {
    /*
     * Outsource is not a permitted child value.
     * Outsourced/jobworker Pavtha rows use Readymade.
     */
    return frm.doc.outsourcer
        ? 'Readymade'
        : 'In-house';
}


function synchronize_issue_item_types(frm) {
    const transactionType =
        get_pavtha_transaction_type(frm);

    (frm.doc.issue_items || []).forEach(row => {
        frappe.model.set_value(
            row.doctype,
            row.name,
            'issue_receive_type',
            transactionType
        );
    });
}


function set_default_type_on_existing_issue_items(frm) {
    const transactionType =
        get_pavtha_transaction_type(frm);

    (frm.doc.issue_items || []).forEach(row => {
        if (!row.issue_receive_type) {
            frappe.model.set_value(
                row.doctype,
                row.name,
                'issue_receive_type',
                transactionType
            );
        }
    });
}


function fetch_stock_summary(
    frm,
    cdt,
    cdn,
    product
) {
    if (!product) {
        return;
    }

    frappe.call({
        method:
            'jari_core.jari_core.doctype.pavtha_issue.pavtha_issue.get_product_stock_summary',

        args: {
            product: product,
            company: frm.doc.company || null
        },

        callback(r) {
            frappe.model.set_value(
                cdt,
                cdn,
                'current_stock_summary',
                r.message ||
                    __('No stock available')
            );
        },

        error(error) {
            console.error(
                `Unable to fetch stock summary for ${product}:`,
                error
            );

            frappe.model.set_value(
                cdt,
                cdn,
                'current_stock_summary',
                __('Unable to load stock')
            );
        }
    });
}


function refresh_all_stock_summaries(frm) {
    (frm.doc.issue_items || []).forEach(row => {
        if (row.product) {
            fetch_stock_summary(
                frm,
                row.doctype,
                row.name,
                row.product
            );
        }
    });
}


function calculate_total_issue_weight(frm) {
    const total = (
        frm.doc.issue_items || []
    ).reduce(
        (sum, row) =>
            sum + flt(row.weight),
        0
    );

    set_parent_value_if_changed(
        frm,
        'total_issue_weight',
        total
    );
}


function set_process_query_by_department(frm) {
    frm.set_query(
        'process_master',
        () => {
            return {
                filters: {
                    department:
                        frm.doc.to_department || ''
                }
            };
        }
    );
}


function clear_process_if_department_changed(frm) {
    if (frm.doc.process_master) {
        frm.set_value(
            'process_master',
            null
        );
    } else {
        frm.clear_table('issue_items');
        frm.refresh_field('issue_items');
        calculate_total_issue_weight(frm);
    }
}


function set_product_query_by_department(frm) {
    frm.set_query(
        'product',
        'issue_items',
        () => {
            return {
                query:
                    'jari_core.jari_core.stock_utils.product_query_by_department',

                filters: {
                    department:
                        frm.doc.to_department || ''
                }
            };
        }
    );
}


function set_parent_value_if_changed(
    frm,
    fieldname,
    value
) {
    const currentValue = flt(
        frm.doc[fieldname]
    );

    const nextValue = flt(value);

    if (
        Math.abs(
            currentValue - nextValue
        ) > 0.000001
    ) {
        frm.set_value(
            fieldname,
            nextValue
        );
    }
}
