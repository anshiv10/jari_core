frappe.ui.form.on('Pavtha Receive', {
    refresh(frm) {
        frm.set_query('pavtha_issue', function() {
            return {
                filters: {
                    docstatus: 1,
                    status: ['!=', 'Received']
                }
            };
        });
    }
});
