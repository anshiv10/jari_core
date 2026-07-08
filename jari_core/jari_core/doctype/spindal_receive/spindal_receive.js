frappe.ui.form.on('Spindal Receive', {
    refresh(frm) {
        if (!frm.doc.receive_date) {
            frm.set_value('receive_date', frappe.datetime.get_today());
        }

        frm.set_query('spindal_issue', function() {
            return {
                query: 'jari_core.jari_core.doctype.spindal_receive.spindal_receive.spindal_issue_query'
            };
        });
    },

    spindal_issue(frm) {
        if (!frm.doc.spindal_issue) return;

        frappe.call({
            method: 'jari_core.jari_core.doctype.spindal_receive.spindal_receive.get_spindal_receive_data',
            args: {
                spindal_issue: frm.doc.spindal_issue
            },
            callback(r) {
                let data = r.message;
                if (!data) return;

                frm.set_value('company', data.company);
                frm.set_value('active_batch_no', data.active_batch_no);
                frm.set_value('process_master', data.process_master);
                frm.set_value('quality_code', data.quality_code);
                frm.set_value('operator', data.operator);
                frm.set_value('total_input_weight', data.total_input_weight);

                frm.clear_table('received_peti_items');

                (data.petis || []).forEach(p => {
                    let d = frm.add_child('received_peti_items');
                    d.peti_no = p.name;
                    d.product = data.kasab_product;
                    d.uom = p.uom || 'gram';
                    d.gross_weight = p.gross_weight;
                    d.net_weight = p.net_weight;
                });

                frm.refresh_field('received_peti_items');
            }
        });
    },

    waste_items_add(frm, cdt, cdn) {
        frappe.model.set_value(cdt, cdn, 'uom', 'gram');
    }
});