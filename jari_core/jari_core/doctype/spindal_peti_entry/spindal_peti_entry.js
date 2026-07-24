frappe.ui.form.on('Spindal Peti Entry', {
    refresh(frm) {
        frm.set_query('spindal_issue', function() {
            return {
                query: 'jari_core.jari_core.doctype.spindal_receive.spindal_receive.spindal_issue_for_peti_query'
            };
        });

        calculate_net_weight(frm);
    },

    gross_weight(frm) {
        calculate_net_weight(frm);
    },

    baad_weight(frm) {
        calculate_net_weight(frm);
    }
});


function calculate_net_weight(frm) {
    const gross_weight = flt(frm.doc.gross_weight);
    const baad_weight = flt(frm.doc.baad_weight);

    if (!gross_weight && !baad_weight) {
        frm.set_value('net_weight', 0);
        return;
    }

    const net_weight = gross_weight - baad_weight;

    if (net_weight < 0) {
        frm.set_value('net_weight', 0);

        frappe.show_alert({
            message: __('Baad Weight cannot be greater than Gross Weight.'),
            indicator: 'red'
        });

        return;
    }

    frm.set_value('net_weight', net_weight);
}