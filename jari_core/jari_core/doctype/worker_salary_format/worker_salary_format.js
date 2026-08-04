frappe.ui.form.on('Worker Salary Format', {
    requires_quality(frm) {
        frm.refresh_field('rate_items');
    }
});
