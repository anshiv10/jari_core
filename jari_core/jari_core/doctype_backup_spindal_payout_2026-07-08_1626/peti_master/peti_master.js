frappe.ui.form.on('Peti Master', {
    gross_weight(frm) {
        calculate_net_weight(frm);
    },
    baad(frm) {
        calculate_net_weight(frm);
    }
});

function calculate_net_weight(frm) {
    let gross = frm.doc.gross_weight || 0;
    let baad = frm.doc.baad || 0;
    frm.set_value('net_weight', gross - baad);
}