frappe.ui.form.on('Spindal Receive', {
    spindal_issue(frm) {
        if (!frm.doc.spindal_issue) return;

        frappe.call({
            method: "jari_core.jari_core.doctype.spindal_receive.spindal_receive.get_spindal_peti_entries",
            args: {
                spindal_issue: frm.doc.spindal_issue
            },
            callback(r) {
                if (!r.message) return;

                frm.clear_table('received_peti_items');

                let total_net_weight = 0;

                r.message.forEach(row => {
                    let child = frm.add_child('received_peti_items');

                    child.spindal_peti_entry = row.name;
                    child.peti_no = row.name;
                    child.batch_no = row.batch_no;
                    child.quality_code = row.quality_code;
                    child.khata_no = row.khata_no;
                    child.gross_weight = row.gross_weight;
                    child.baad_weight = row.baad_weight;
                    child.net_weight = row.net_weight;

                    total_net_weight += flt(row.net_weight);
                });

                frm.refresh_field('received_peti_items');

                if (frm.fields_dict.total_net_weight) {
                    frm.set_value('total_net_weight', total_net_weight);
                }

                if (frm.fields_dict.total_receive_weight) {
                    frm.set_value('total_receive_weight', total_net_weight);
                }
            }
        });
    }
});
