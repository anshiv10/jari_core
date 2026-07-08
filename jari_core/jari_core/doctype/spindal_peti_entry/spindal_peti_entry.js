frappe.ui.form.on('Spindal Peti Entry', {
    refresh(frm) {
        frm.set_query('spindal_issue', function() {
            return {
                query: 'jari_core.jari_core.doctype.spindal_receive.spindal_receive.spindal_issue_for_peti_query'
            };
        });
    }
});
