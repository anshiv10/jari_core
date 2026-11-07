// Party Transaction Tol Wise  (client reference: "Check Transaction - Tol wise")
// Debit = issued to party, Credit = received from party, Balance = lying with party.
// UI features (KPI cards, Download, Email, Quick Analytics, Date Presets,
// Clear Filters) come from /assets/jari_core/js/jari_report_kit.js.

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
        jari_ptw_set_single_company(report);
        frappe.require("/assets/jari_core/js/jari_report_kit.js", function () {
            jari_report_kit.setup(report, jari_ptw_config());
        });
    },

    refresh: function (report) {
        if (window.jari_report_kit) {
            jari_report_kit.on_refresh(report);
        }
    },

    after_datatable_render: function () {
        if (window.jari_report_kit) {
            jari_report_kit.draw_kpis(frappe.query_report);
        }
    },

    formatter: function (value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        if (!data) {
            return value;
        }

        if (data.is_group) {
            if (column.fieldname === "description") {
                return `<span style="font-weight:700;font-size:13px;color:#1e3a8a;">👤 ${value}</span>`;
            }
            return value;
        }

        if (data.is_total || data.is_opening) {
            return `<span style="font-weight:700;">${value}</span>`;
        }

        if (column.fieldname === "voucher_type" && data.voucher_type) {
            return jari_ptw_vtype_pill(data.voucher_type);
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

function jari_ptw_set_single_company(report) {
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

function jari_ptw_vtype_pill(vtype) {
    const issue = vtype.indexOf("Issue") !== -1;
    const sale = vtype === "Jari Sale";
    const purchase = vtype === "Purchase Entry";
    const colors = sale
        ? ["#f5f3ff", "#6d28d9", "#c4b5fd"]
        : purchase
          ? ["#eff6ff", "#1d4ed8", "#93c5fd"]
          : issue
            ? ["#fef2f2", "#b91c1c", "#fca5a5"]
            : ["#f0fdf4", "#15803d", "#86efac"];
    return `<span style="background:${colors[0]};color:${colors[1]};border:1px solid ${colors[2]};padding:1px 8px;border-radius:4px;font-weight:600;font-size:11px;">${frappe.utils.escape_html(vtype)}</span>`;
}

function jari_ptw_config() {
    return {
        key: "party-tol",
        title: "Party Transaction Tol Wise",
        file_prefix: "Party_Transaction_Tol_Wise",
        sheet_name: "Party Ledger",
        orientation: "portrait",
        date_filters: { from: "from_date", to: "to_date" },

        on_setup: function (report, fy) {
            if (!report.get_filter_value("from_date")) {
                report.set_filter_value("from_date", fy + "-04-01");
            }
        },

        clear_filters: ["party_type", "party", "product", "department", "from_date", "to_date"],
        clear_defaults: function () {
            return {
                from_date: jari_report_kit.fy_start_year() + "-04-01",
                to_date: frappe.datetime.get_today(),
            };
        },

        is_data_row: function (r) {
            return !!r.voucher_no;
        },

        kpis: function (rows, all, fmt) {
            const s = jari_ptw_stats(rows);
            return [
                { icon: "👥", lbl: "Parties", accent: "#2563eb", val: fmt.num(s.parties), is_count: true, raw: s.parties },
                { icon: "🧾", lbl: "Vouchers", accent: "#0891b2", val: fmt.num(s.vouchers), is_count: true, raw: s.vouchers },
                { icon: "📤", lbl: "Issued (Debit)", accent: "#dc2626", val: fmt.kg(s.debit), tip: "Material issued to parties in the period" },
                { icon: "📥", lbl: "Received (Credit)", accent: "#16a34a", val: fmt.kg(s.credit), tip: "Material received back from parties in the period" },
                { icon: "⚖️", lbl: "Net Issued − Received", accent: "#d97706", val: fmt.kg(s.debit - s.credit), tip: "Debit − Credit inside the selected period" },
                { icon: "🧑‍🏭", lbl: "Parties Holding Material", accent: "#7c3aed", val: fmt.num(s.holding_count), is_count: true, raw: s.holding_count, tip: "Parties with a positive closing balance" },
                { icon: "📦", lbl: "Lying With Parties", accent: "#475569", val: fmt.kg(s.holding_kg), tip: "Sum of positive closing balances (includes opening)" },
                { icon: "🧮", lbl: "Transactions", accent: "#0d9488", val: fmt.num(rows.length), is_count: true, raw: rows.length },
            ];
        },

        analytics: function (rows, all, fmt) {
            const s = jari_ptw_stats(rows);

            const party_keys = Object.keys(s.by_party)
                .sort((a, b) => (s.by_party[b].debit + s.by_party[b].credit) - (s.by_party[a].debit + s.by_party[a].credit))
                .slice(0, 12);

            const months = Object.keys(s.by_month).sort();
            const mix = Object.keys(s.debit_mix).sort((a, b) => s.debit_mix[b] - s.debit_mix[a]).slice(0, 8);
            const holders = Object.keys(s.closing)
                .filter((p) => s.closing[p] > 0.0005)
                .sort((a, b) => s.closing[b] - s.closing[a])
                .slice(0, 12);
            const palette = ["#2563eb", "#dc2626", "#16a34a", "#d97706", "#7c3aed", "#0891b2", "#db2777", "#475569"];
            const kg_tick = { callback: (v) => fmt.kg_short(v) + " kg", font: { size: 10 } };

            return {
                pills: [
                    { icon: "👥", text: s.parties + " Parties", g1: "#1e3a5f", g2: "#2563eb" },
                    { icon: "📤", text: fmt.kg(s.debit) + " Issued", g1: "#7f1d1d", g2: "#dc2626" },
                    { icon: "📥", text: fmt.kg(s.credit) + " Received", g1: "#14532d", g2: "#16a34a" },
                    { icon: "📦", text: fmt.kg(s.holding_kg) + " With Parties", g1: "#3b0764", g2: "#7c3aed" },
                ],
                charts: [
                    {
                        title: "Issued vs Received by Party (kg)",
                        config: {
                            type: "bar",
                            data: {
                                labels: party_keys,
                                datasets: [
                                    { label: "Issued (Debit)", data: party_keys.map((p) => s.by_party[p].debit), backgroundColor: "#dc2626", borderRadius: 5 },
                                    { label: "Received (Credit)", data: party_keys.map((p) => s.by_party[p].credit), backgroundColor: "#16a34a", borderRadius: 5 },
                                ],
                            },
                            options: {
                                responsive: true,
                                interaction: { mode: "index", intersect: false },
                                plugins: { legend: { position: "bottom" }, tooltip: { callbacks: { label: (c) => " " + c.dataset.label + ": " + fmt.kg(c.parsed.y) } } },
                                scales: { y: { beginAtZero: true, ticks: kg_tick }, x: { grid: { display: false } } },
                            },
                        },
                    },
                    {
                        title: "Monthly Issued vs Received (kg)",
                        config: {
                            type: "bar",
                            data: {
                                labels: months.map((m) => fmt.month_label(m + "-01")),
                                datasets: [
                                    { label: "Issued", data: months.map((m) => s.by_month[m].debit), backgroundColor: "#f87171", borderRadius: 6 },
                                    { label: "Received", data: months.map((m) => s.by_month[m].credit), backgroundColor: "#4ade80", borderRadius: 6 },
                                ],
                            },
                            options: {
                                responsive: true,
                                interaction: { mode: "index", intersect: false },
                                plugins: {
                                    legend: { position: "bottom" },
                                    tooltip: {
                                        callbacks: {
                                            label: (c) => " " + c.dataset.label + ": " + fmt.kg(c.parsed.y),
                                            footer: (items) => "Net: " + fmt.kg((items[0] ? items[0].parsed.y : 0) - (items[1] ? items[1].parsed.y : 0)),
                                        },
                                    },
                                },
                                scales: { y: { beginAtZero: true, ticks: kg_tick }, x: { grid: { display: false } } },
                            },
                        },
                    },
                    {
                        title: "Issued Product Mix (kg)",
                        config: {
                            type: "doughnut",
                            data: {
                                labels: mix,
                                datasets: [{ data: mix.map((k) => s.debit_mix[k]), backgroundColor: palette, borderWidth: 3, borderColor: "#fff", hoverOffset: 8 }],
                            },
                            options: {
                                responsive: true,
                                cutout: "60%",
                                plugins: {
                                    legend: { position: "bottom", labels: { usePointStyle: true, font: { size: 11 } } },
                                    tooltip: { callbacks: { label: (c) => " " + c.label + ": " + fmt.kg(c.parsed) + (s.debit ? " (" + Math.round((c.parsed / s.debit) * 100) + "%)" : "") } },
                                },
                            },
                        },
                    },
                    {
                        title: "Material Lying With Party — Closing (kg)",
                        config: {
                            type: "bar",
                            data: {
                                labels: holders,
                                datasets: [{ label: "Closing Balance", data: holders.map((p) => s.closing[p]), backgroundColor: "#7c3aed", borderRadius: 5 }],
                            },
                            options: {
                                indexAxis: "y",
                                responsive: true,
                                plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => " " + fmt.kg(c.parsed.x) } } },
                                scales: { x: { beginAtZero: true, ticks: kg_tick }, y: { grid: { display: false } } },
                            },
                        },
                        empty_text: holders.length ? "" : "No party is holding material.",
                    },
                ],
            };
        },
    };
}

function jari_ptw_stats(rows) {
    const s = {
        parties: 0, vouchers: 0, debit: 0, credit: 0,
        holding_count: 0, holding_kg: 0,
        by_party: {}, by_month: {}, debit_mix: {}, closing: {},
    };
    const vouchers = {};

    rows.forEach((r) => {
        const party = r.party || "-";
        const debit = flt(r.debit);
        const credit = flt(r.credit);
        const month = String(r.posting_date || "").substring(0, 7);

        s.debit += debit;
        s.credit += credit;
        vouchers[(r.voucher_type || "") + "|" + r.voucher_no] = 1;

        s.by_party[party] = s.by_party[party] || { debit: 0, credit: 0 };
        s.by_party[party].debit += debit;
        s.by_party[party].credit += credit;

        if (month) {
            s.by_month[month] = s.by_month[month] || { debit: 0, credit: 0 };
            s.by_month[month].debit += debit;
            s.by_month[month].credit += credit;
        }

        if (debit) {
            const label = r.description || r.product || "-";
            s.debit_mix[label] = (s.debit_mix[label] || 0) + debit;
        }

        // rows are in date order per party, so the last one is the closing
        s.closing[party] = flt(r.balance);
    });

    s.parties = Object.keys(s.by_party).length;
    s.vouchers = Object.keys(vouchers).length;
    Object.keys(s.closing).forEach((p) => {
        if (s.closing[p] > 0.0005) {
            s.holding_count += 1;
            s.holding_kg += s.closing[p];
        }
    });
    return s;
}
