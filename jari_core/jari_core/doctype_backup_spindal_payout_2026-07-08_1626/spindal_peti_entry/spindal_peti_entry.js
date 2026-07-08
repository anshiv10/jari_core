frappe.ui.form.on('Spindal Peti Entry', {
    refresh(frm) {
        frm.toggle_display('bobbin_count', false);
        frm.toggle_display('remaining_bobbin', false);

        frm.set_query('spindal_issue', function() {
            return {
                query: 'jari_core.jari_core.doctype.spindal_receive.spindal_receive.spindal_issue_for_peti_query'
            };
        });
    },

    gross_weight(frm) {
        calculate_net_weight(frm);
    },

    baad_weight(frm) {
        calculate_net_weight(frm);
    }
});

function calculate_net_weight(frm) {
    let gross = flt(frm.doc.gross_weight);
    let baad = flt(frm.doc.baad_weight);

    if (gross > 0) {
        frm.set_value('net_weight', gross - baad);
    }
}