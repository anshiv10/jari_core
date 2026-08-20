frappe.ui.form.on('Company Expense', {
    setup(frm) {
        frm.set_query(
            'expense_account',
            function () {
                return {
                    filters: {
                        company:
                            frm.doc.company || '',
                        root_type:
                            'Expense',
                        is_group:
                            0,
                        disabled:
                            0
                    }
                };
            }
        );

        frm.set_query(
            'paid_from_account',
            function () {
                return {
                    filters: {
                        company:
                            frm.doc.company || '',
                        account_type:
                            [
                                'in',
                                [
                                    'Cash',
                                    'Bank'
                                ]
                            ],
                        is_group:
                            0,
                        disabled:
                            0
                    }
                };
            }
        );
    },

    company(frm) {
        frm.set_value(
            'expense_account',
            null
        );

        frm.set_value(
            'paid_from_account',
            null
        );
    }
});
