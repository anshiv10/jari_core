import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, today


class CompanyExpense(Document):

    def validate(self):
        self.set_defaults()
        self.validate_company()
        self.validate_amount()
        self.validate_accounts()

    def before_submit(self):
        self.validate_company()
        self.validate_amount()
        self.validate_accounts()

    def set_defaults(self):
        if not self.expense_date:
            self.expense_date = today()

        if self.docstatus == 0 and not self.journal_entry:
            self.posting_status = "Draft"

    def get_erpnext_company(self):
        if not self.company:
            frappe.throw(
                _("Company is required.")
            )

        company_master = frappe.db.get_value(
            "Company Master",
            self.company,
            [
                "company_name",
                "active",
            ],
            as_dict=True,
        )

        if not company_master:
            frappe.throw(
                _(
                    "Company Master {0} does not exist."
                ).format(
                    frappe.bold(self.company)
                )
            )

        if not company_master.active:
            frappe.throw(
                _(
                    "Company {0} is inactive."
                ).format(
                    frappe.bold(self.company)
                )
            )

        # Prefer an exact-name mapping.
        if frappe.db.exists(
            "Company",
            self.company,
        ):
            return self.company

        erpnext_company = frappe.db.get_value(
            "Company",
            {
                "company_name":
                    company_master.company_name,
            },
            "name",
        )

        if not erpnext_company:
            frappe.throw(
                _(
                    "No ERPNext Company is mapped to "
                    "Company Master {0}."
                ).format(
                    frappe.bold(self.company)
                )
            )

        return erpnext_company

    def validate_company(self):
        self.get_erpnext_company()

    def validate_amount(self):
        if flt(self.amount) <= 0:
            frappe.throw(
                _("Amount must be greater than zero.")
            )

    def get_account_details(
        self,
        account,
        label,
    ):
        if not account:
            frappe.throw(
                _("{0} is required.").format(label)
            )

        values = frappe.db.get_value(
            "Account",
            account,
            [
                "company",
                "account_name",
                "account_type",
                "root_type",
                "account_currency",
                "is_group",
                "disabled",
            ],
            as_dict=True,
        )

        if not values:
            frappe.throw(
                _(
                    "{0} {1} does not exist."
                ).format(
                    label,
                    frappe.bold(account),
                )
            )

        return values

    def validate_accounts(self):
        erp_company = self.get_erpnext_company()

        expense = self.get_account_details(
            self.expense_account,
            "Expense Account",
        )

        paid_from = self.get_account_details(
            self.paid_from_account,
            "Paid From Account",
        )

        if expense.company != erp_company:
            frappe.throw(
                _(
                    "Expense Account {0} does not belong "
                    "to Company {1}."
                ).format(
                    frappe.bold(
                        self.expense_account
                    ),
                    frappe.bold(
                        erp_company
                    ),
                )
            )

        if expense.root_type != "Expense":
            frappe.throw(
                _(
                    "Expense Account {0} must be an "
                    "Expense account."
                ).format(
                    frappe.bold(
                        self.expense_account
                    )
                )
            )

        if expense.is_group:
            frappe.throw(
                _(
                    "Expense Account {0} cannot be "
                    "a group account."
                ).format(
                    frappe.bold(
                        self.expense_account
                    )
                )
            )

        if expense.disabled:
            frappe.throw(
                _(
                    "Expense Account {0} is disabled."
                ).format(
                    frappe.bold(
                        self.expense_account
                    )
                )
            )

        if paid_from.company != erp_company:
            frappe.throw(
                _(
                    "Paid From Account {0} does not belong "
                    "to Company {1}."
                ).format(
                    frappe.bold(
                        self.paid_from_account
                    ),
                    frappe.bold(
                        erp_company
                    ),
                )
            )

        if paid_from.account_type not in (
            "Cash",
            "Bank",
        ):
            frappe.throw(
                _(
                    "Paid From Account {0} must be "
                    "a Cash or Bank account."
                ).format(
                    frappe.bold(
                        self.paid_from_account
                    )
                )
            )

        if paid_from.is_group:
            frappe.throw(
                _(
                    "Paid From Account {0} cannot be "
                    "a group account."
                ).format(
                    frappe.bold(
                        self.paid_from_account
                    )
                )
            )

        if paid_from.disabled:
            frappe.throw(
                _(
                    "Paid From Account {0} is disabled."
                ).format(
                    frappe.bold(
                        self.paid_from_account
                    )
                )
            )

        if self.expense_account == self.paid_from_account:
            frappe.throw(
                _(
                    "Expense Account and Paid From "
                    "Account cannot be the same."
                )
            )

        expense_currency = (
            expense.account_currency
            or ""
        )

        paid_currency = (
            paid_from.account_currency
            or ""
        )

        company_currency = frappe.db.get_value(
            "Company",
            erp_company,
            "default_currency",
        )

        if (
            expense_currency
            and company_currency
            and expense_currency != company_currency
        ):
            frappe.throw(
                _(
                    "Expense Account currency must match "
                    "the Company currency."
                )
            )

        if (
            paid_currency
            and company_currency
            and paid_currency != company_currency
        ):
            frappe.throw(
                _(
                    "Paid From Account currency must match "
                    "the Company currency."
                )
            )

    def get_cost_center(self):
        erp_company = self.get_erpnext_company()

        cost_center = frappe.db.get_value(
            "Cost Center",
            {
                "company":
                    erp_company,
                "is_group":
                    0,
                "disabled":
                    0,
            },
            "name",
            order_by="name asc",
        )

        if not cost_center:
            frappe.throw(
                _(
                    "No active leaf Cost Center exists "
                    "for Company {0}."
                ).format(
                    frappe.bold(
                        erp_company
                    )
                )
            )

        return cost_center

    def get_voucher_type(self):
        account_type = frappe.db.get_value(
            "Account",
            self.paid_from_account,
            "account_type",
        )

        if account_type == "Cash":
            return "Cash Entry"

        if account_type == "Bank":
            return "Bank Entry"

        return "Journal Entry"

    def on_submit(self):
        if self.journal_entry:
            existing_status = frappe.db.get_value(
                "Journal Entry",
                self.journal_entry,
                "docstatus",
            )

            if existing_status == 1:
                self.db_set(
                    "posting_status",
                    "Posted",
                    update_modified=False,
                )
                return

            frappe.throw(
                _(
                    "Journal Entry {0} is already linked "
                    "but is not submitted."
                ).format(
                    frappe.bold(
                        self.journal_entry
                    )
                )
            )

        erp_company = self.get_erpnext_company()
        cost_center = self.get_cost_center()

        journal = frappe.get_doc({
            "doctype":
                "Journal Entry",

            "voucher_type":
                self.get_voucher_type(),

            "company":
                erp_company,

            "posting_date":
                self.expense_date,

            "user_remark":
                (
                    f"Company Expense {self.name}"
                    + (
                        f" - {self.description}"
                        if self.description
                        else ""
                    )
                ),
        })

        journal.append(
            "accounts",
            {
                "account":
                    self.expense_account,

                "debit_in_account_currency":
                    flt(self.amount),

                "cost_center":
                    cost_center,
            },
        )

        journal.append(
            "accounts",
            {
                "account":
                    self.paid_from_account,

                "credit_in_account_currency":
                    flt(self.amount),
            },
        )

        journal.flags.ignore_permissions = True

        journal.insert(
            ignore_permissions=True
        )

        journal.flags.ignore_permissions = True
        journal.submit()

        self.db_set(
            "journal_entry",
            journal.name,
            update_modified=False,
        )

        self.db_set(
            "posting_status",
            "Posted",
            update_modified=False,
        )

    def on_cancel(self):
        if not self.journal_entry:
            self.db_set(
                "posting_status",
                "Cancelled",
                update_modified=False,
            )
            return

        if not frappe.db.exists(
            "Journal Entry",
            self.journal_entry,
        ):
            frappe.throw(
                _(
                    "Linked Journal Entry {0} "
                    "does not exist."
                ).format(
                    frappe.bold(
                        self.journal_entry
                    )
                )
            )

        journal = frappe.get_doc(
            "Journal Entry",
            self.journal_entry,
        )

        if journal.docstatus == 1:
            journal.flags.ignore_permissions = True
            journal.cancel()

        elif journal.docstatus == 0:
            frappe.throw(
                _(
                    "Linked Journal Entry {0} is still "
                    "Draft and cannot be automatically "
                    "cancelled."
                ).format(
                    frappe.bold(
                        journal.name
                    )
                )
            )

        self.db_set(
            "posting_status",
            "Cancelled",
            update_modified=False,
        )
