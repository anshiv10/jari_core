frappe.ui.form.on('Pavtha Issue', {
    refresh(frm) {
        frm.set_query('process_master', function() {
            return { filters: { department: 'Pavtha' } };
        });
    }
});
