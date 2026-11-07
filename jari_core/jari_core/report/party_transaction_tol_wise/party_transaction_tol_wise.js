// Party Transaction Tol Wise  (client reference: "Check Transaction - Tol wise")
// Debit = issued to party, Credit = received from party, Balance = lying with party.

frappe.query_reports["Party Transaction Tol Wise"] = {
    filters: [
        {
            fieldname: "company",
            label: __("Company"),
            fieldtype: "Link",
            options: "Company Master",
            reqd: 1,
        },
        {
            fieldname: "party_type",
            label: __("Party Type"),
            fieldtype: "Select",
            options: ["", "Worker Master", "Jobworker Master", "Customer", "Supplier"],
            on_change: function (report) {
                report.set_filter_value("party", "");
            },
        },
        {
            fieldname: "party",
            label: __("Party (A/c)"),
            fieldtype: "Dynamic Link",
            options: "party_type",
            get_query: function () {
                const party_type = frappe.query_report.get_filter_value("party_type");
                if (!party_type) {
                    frappe.throw(__("Please select Party Type first"));
                }
                return {};
            },
        },
        {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
            default: frappe.datetime.get_today(),
        },
        {
            fieldname: "product",
            label: __("Product"),
            fieldtype: "Link",
            options: "Product Master",
        },
        {
            fieldname: "department",
            label: __("Department"),
            fieldtype: "Link",
            options: "Department Master",
        },
    ],

    onload: function (report) {
        jari_set_single_company(report);
    },

    formatter: function (value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        if (!data) {
            return value;
        }

        if (data.is_group) {
            if (column.fieldname === "description") {
                return `<span style="font-weight:700;font-size:13px;color:#1e3a8a;">${value}</span>`;
            }
            return value;
        }

        if (data.is_total || data.is_opening) {
            return `<span style="font-weight:700;">${value}</span>`;
        }

        if (column.fieldname === "credit" && data.credit) {
            return `<span style="color:#15803d;font-weight:600;">${value}</span>`;
        }

        if (column.fieldname === "debit" && data.debit) {
            return `<span style="color:#b91c1c;font-weight:600;">${value}</span>`;
        }

        if (column.fieldname === "balance") {
            const color = flt(data.balance) >= 0 ? "#1d4ed8" : "#c2410c";
            return `<span style="color:${color};font-weight:600;">${value}</span>`;
        }

        return value;
    },
};

function jari_set_single_company(report) {
    if (report.get_filter_value("company")) {
        return;
    }
    frappe.db
        .get_list("Company Master", { fields: ["name"], filters: { active: 1 }, limit: 2 })
        .then((rows) => {
            if (rows && rows.length === 1) {
                report.set_filter_value("company", rows[0].name);
            }
        });
}
