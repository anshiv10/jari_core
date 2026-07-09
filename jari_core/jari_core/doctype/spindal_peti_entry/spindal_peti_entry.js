frappe.ui.form.on('Spindal Peti Entry', {
    refresh(frm) {
        frm.set_query('spindal_issue', function() {
            return {
                filters: {
                    docstatus: ['!=', 1]
                }
            };
        });
    }
});
