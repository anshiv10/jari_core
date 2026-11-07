// Item Pending In Stock  (client reference: "ITEM STOCK REPORT AS ON DATE")
// JAMA = received lot, UDHAR = issue of that exact lot, BALANCE = still in stock.

frappe.query_reports["Item Pending In Stock"] = {
    filters: [
        {
            fieldname: "company",
            label: __("Company"),
            fieldtype: "Link",
            options: "Company Master",
            reqd: 1,
        },
        {
            fieldname: "as_on_date",
            label: __("As On Date"),
            fieldtype: "Date",
            default: frappe.datetime.get_today(),
        },
        {
            fieldname: "product",
            label: __("Item"),
            fieldtype: "Link",
            options: "Product Master",
        },
        {
            fieldname: "department",
            label: __("Department"),
            fieldtype: "Link",
            options: "Department Master",
        },
        {
            fieldname: "quality",
            label: __("Quality"),
            fieldtype: "Link",
            options: "Quality Master",
        },
        {
            fieldname: "party_type",
            label: __("Jama Party Type"),
            fieldtype: "Select",
            options: ["", "Worker Master", "Jobworker Master", "Customer", "Supplier"],
            on_change: function (report) {
                report.set_filter_value("party", "");
            },
        },
        {
            fieldname: "party",
            label: __("Jama A/c"),
            fieldtype: "Dynamic Link",
            options: "party_type",
        },
        {
            fieldname: "from_date",
            label: __("Jama From Date"),
            fieldtype: "Date",
        },
        {
            fieldname: "to_date",
            label: __("Jama To Date"),
            fieldtype: "Date",
        },

    ],

    onload: function (report) {
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
    },

    formatter: function (value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        if (!data) {
            return value;
        }

        const field = column.fieldname;

        if (data.is_group) {
            if (field === "item") {
                return `<span style="font-weight:800;font-size:13.5px;color:#1e3a8a;letter-spacing:.3px;">${value}</span>`;
            }
            return value;
        }

        if (data.is_total) {
            const color = data.is_grand_total ? "#7c2d12" : "#111827";
            return `<span style="font-weight:800;color:${color};">${value}</span>`;
        }

        if (field.startsWith("jama_") && field !== "jama_voucher_type") {
            return `<span style="color:#166534;">${value}</span>`;
        }

        if (field.startsWith("udhar_") && field !== "udhar_voucher_type") {
            return `<span style="color:#991b1b;">${value}</span>`;
        }

        if (field === "lot_no" && data.is_return) {
            return `<span style="background:#fef3c7;color:#92400e;border-radius:4px;padding:1px 6px;font-weight:700;">RET</span>`;
        }

        if (field === "balance_kgs" || field === "balance_pcs") {
            const pending = flt(data.balance_kgs) > 0.0005;
            const style = pending
                ? "color:#1d4ed8;font-weight:700;"
                : "color:#9ca3af;";
            return `<span style="${style}">${value}</span>`;
        }

        if (field === "age_days" && data.age_days !== null && data.age_days !== undefined) {
            const days = cint(data.age_days);
            const bg = days > 30 ? "#fee2e2" : days > 15 ? "#fef3c7" : "#dcfce7";
            const fg = days > 30 ? "#991b1b" : days > 15 ? "#92400e" : "#166534";
            return `<span style="background:${bg};color:${fg};border-radius:4px;padding:1px 7px;font-weight:700;">${value}</span>`;
        }

        if (field === "reserved_kgs" && flt(data.reserved_kgs) > 0) {
            return `<span style="color:#7c3aed;font-weight:600;">${value}</span>`;
        }

        return value;
    },
};
