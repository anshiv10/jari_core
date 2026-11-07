// Item Pending In Stock  (client reference: "ITEM STOCK REPORT AS ON DATE")
// JAMA = received lot, UDHAR = issue of that exact lot, BALANCE = still in stock.
// UI features (KPI cards, Download, Email, Quick Analytics, Date Presets,
// Clear Filters) come from /assets/jari_core/js/jari_report_kit.js.

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
        jari_ipis_set_single_company(report);
        frappe.require("/assets/jari_core/js/jari_report_kit.js", function () {
            jari_report_kit.setup(report, jari_ipis_config());
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

        const field = column.fieldname;

        if (data.is_group) {
            if (field === "item") {
                return `<span style="font-weight:800;font-size:13.5px;color:#1e3a8a;letter-spacing:.3px;">📦 ${value}</span>`;
            }
            return value;
        }

        if (data.is_total) {
            const color = data.is_grand_total ? "#7c2d12" : "#111827";
            return `<span style="font-weight:800;color:${color};">${value}</span>`;
        }

        if ((field === "jama_voucher_type" || field === "udhar_voucher_type") && data[field]) {
            return jari_ipis_vtype_pill(data[field]);
        }

        if (field.startsWith("jama_")) {
            return `<span style="color:#166534;">${value}</span>`;
        }

        if (field.startsWith("udhar_")) {
            return `<span style="color:#991b1b;">${value}</span>`;
        }

        if (field === "lot_no" && data.is_return) {
            return `<span style="background:#fef3c7;color:#92400e;border-radius:4px;padding:1px 6px;font-weight:700;">RET</span>`;
        }

        if (field === "balance_kgs" || field === "balance_pcs") {
            const pending = flt(data.balance_kgs) > 0.0005;
            const style = pending ? "color:#1d4ed8;font-weight:700;" : "color:#9ca3af;";
            return `<span style="${style}">${value}</span>`;
        }

        if (field === "age_days" && data.age_days !== null && data.age_days !== undefined) {
            const days = cint(data.age_days);
            const bg = days > 30 ? "#fee2e2" : days > 15 ? "#fef3c7" : "#dcfce7";
            const fg = days > 30 ? "#991b1b" : days > 15 ? "#92400e" : "#166534";
            return `<span style="background:${bg};color:${fg};border-radius:20px;padding:1px 9px;font-weight:700;">${value}</span>`;
        }

        if (field === "reserved_kgs" && flt(data.reserved_kgs) > 0) {
            return `<span style="color:#7c3aed;font-weight:600;">${value}</span>`;
        }

        return value;
    },
};

function jari_ipis_set_single_company(report) {
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

function jari_ipis_vtype_pill(vtype) {
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

function jari_ipis_stats(rows) {
    const s = {
        lots: 0, pending: 0, fully_issued: 0,
        jama_kg: 0, udhar_kg: 0, balance_kg: 0, balance_pcs: 0,
        reserved_kg: 0, oldest: 0,
        by_item: {}, by_party: {}, ageing: [0, 0, 0, 0],
        jama_month: {}, udhar_month: {},
    };

    rows.forEach((r) => {
        if (r.udhar_voucher) {
            const net = flt(r.udhar_net);
            s.udhar_kg += net;
            const m = String(r.udhar_date || "").substring(0, 7);
            if (m) {
                s.udhar_month[m] = (s.udhar_month[m] || 0) + net;
            }
        }

        if (!r.jama_voucher) {
            return;
        }

        const jama = flt(r.jama_net);
        const bal = flt(r.balance_kgs);
        s.lots += 1;
        s.jama_kg += jama;
        s.balance_kg += bal;
        s.balance_pcs += cint(r.balance_pcs);
        s.reserved_kg += flt(r.reserved_kgs);

        const jm = String(r.jama_date || "").substring(0, 7);
        if (jm) {
            s.jama_month[jm] = (s.jama_month[jm] || 0) + jama;
        }

        if (bal > 0.0005) {
            s.pending += 1;
            const age = cint(r.age_days);
            s.oldest = Math.max(s.oldest, age);
            const bucket = age <= 15 ? 0 : age <= 30 ? 1 : age <= 60 ? 2 : 3;
            s.ageing[bucket] += bal;

            const item = r.item_label || "-";
            s.by_item[item] = (s.by_item[item] || 0) + bal;

            const party = r.jama_party || "-";
            s.by_party[party] = (s.by_party[party] || 0) + bal;
        } else {
            s.fully_issued += 1;
        }
    });

    return s;
}

function jari_ipis_config() {
    return {
        key: "item-pending",
        title: "Item Pending In Stock",
        file_prefix: "Item_Pending_In_Stock",
        sheet_name: "Jama Udhar",
        orientation: "landscape",
        date_filters: { from: "from_date", to: "to_date" },

        clear_filters: ["product", "department", "quality", "party_type", "party", "from_date", "to_date", "as_on_date"],
        clear_defaults: function () {
            return { as_on_date: frappe.datetime.get_today() };
        },

        is_data_row: function (r) {
            return !r.is_group && !r.is_total;
        },

        kpis: function (rows, all, fmt) {
            const s = jari_ipis_stats(rows);
            return [
                { icon: "📦", lbl: "Lots (Jama)", accent: "#2563eb", val: fmt.num(s.lots), is_count: true, raw: s.lots },
                { icon: "⏳", lbl: "Pending Lots", accent: "#d97706", val: fmt.num(s.pending), is_count: true, raw: s.pending },
                { icon: "📥", lbl: "Jama", accent: "#16a34a", val: fmt.kg(s.jama_kg), tip: "Total received weight of the listed lots" },
                { icon: "📤", lbl: "Udhar", accent: "#dc2626", val: fmt.kg(s.udhar_kg), tip: "Total issued weight against the listed lots" },
                { icon: "⚖️", lbl: "Balance In Stock", accent: "#1d4ed8", val: fmt.kg(s.balance_kg), tip: "Jama − Udhar still lying in the Jama department" },
                { icon: "🧮", lbl: "Balance Pcs", accent: "#0891b2", val: fmt.num(s.balance_pcs), is_count: true, raw: s.balance_pcs },
                { icon: "🔒", lbl: "Reserved in Drafts", accent: "#7c3aed", val: fmt.kg(s.reserved_kg), tip: "Pending stock already reserved by Saved Draft Issues" },
                { icon: "🕰️", lbl: "Oldest Pending (Days)", accent: s.oldest > 30 ? "#b91c1c" : s.oldest > 15 ? "#92400e" : "#15803d", val: fmt.num(s.oldest), is_count: true, raw: s.oldest },
            ];
        },

        analytics: function (rows, all, fmt) {
            const s = jari_ipis_stats(rows);
            const palette = ["#2563eb", "#16a34a", "#d97706", "#7c3aed", "#dc2626", "#0891b2", "#db2777", "#475569"];
            const kg_tick = { callback: (v) => fmt.kg_short(v) + " kg", font: { size: 10 } };

            const items = Object.keys(s.by_item).sort((a, b) => s.by_item[b] - s.by_item[a]).slice(0, 8);
            const parties = Object.keys(s.by_party).sort((a, b) => s.by_party[b] - s.by_party[a]).slice(0, 12);
            const months = Array.from(new Set(Object.keys(s.jama_month).concat(Object.keys(s.udhar_month)))).sort();

            return {
                pills: [
                    { icon: "📦", text: s.lots + " Lots", g1: "#1e3a5f", g2: "#2563eb" },
                    { icon: "⏳", text: s.pending + " Pending", g1: "#78350f", g2: "#d97706" },
                    { icon: "⚖️", text: fmt.kg(s.balance_kg) + " Balance", g1: "#1e3a8a", g2: "#1d4ed8" },
                    { icon: "🕰️", text: "Oldest " + s.oldest + " days", g1: "#7f1d1d", g2: "#dc2626" },
                ],
                charts: [
                    {
                        title: "Pending Balance by Item (kg)",
                        config: {
                            type: "doughnut",
                            data: {
                                labels: items,
                                datasets: [{ data: items.map((k) => s.by_item[k]), backgroundColor: palette, borderWidth: 3, borderColor: "#fff", hoverOffset: 8 }],
                            },
                            options: {
                                responsive: true,
                                cutout: "60%",
                                plugins: {
                                    legend: { position: "bottom", labels: { usePointStyle: true, font: { size: 11 } } },
                                    tooltip: { callbacks: { label: (c) => " " + c.label + ": " + fmt.kg(c.parsed) + (s.balance_kg ? " (" + Math.round((c.parsed / s.balance_kg) * 100) + "%)" : "") } },
                                },
                            },
                        },
                        empty_text: items.length ? "" : "No pending balance.",
                    },
                    {
                        title: "Pending Ageing (kg)",
                        config: {
                            type: "bar",
                            data: {
                                labels: ["0–15 days", "16–30 days", "31–60 days", "60+ days"],
                                datasets: [{ label: "Pending kg", data: s.ageing, backgroundColor: ["#16a34a", "#d97706", "#ea580c", "#b91c1c"], borderRadius: 7 }],
                            },
                            options: {
                                responsive: true,
                                plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => " " + fmt.kg(c.parsed.y) } } },
                                scales: { y: { beginAtZero: true, ticks: kg_tick }, x: { grid: { display: false } } },
                            },
                        },
                    },
                    {
                        title: "Monthly Jama vs Udhar (kg)",
                        config: {
                            type: "bar",
                            data: {
                                labels: months.map((m) => fmt.month_label(m + "-01")),
                                datasets: [
                                    { label: "Jama", data: months.map((m) => s.jama_month[m] || 0), backgroundColor: "#4ade80", borderRadius: 6 },
                                    { label: "Udhar", data: months.map((m) => s.udhar_month[m] || 0), backgroundColor: "#f87171", borderRadius: 6 },
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
                        title: "Pending by Jama A/c (kg)",
                        config: {
                            type: "bar",
                            data: {
                                labels: parties,
                                datasets: [{ label: "Pending kg", data: parties.map((p) => s.by_party[p]), backgroundColor: "#7c3aed", borderRadius: 5 }],
                            },
                            options: {
                                indexAxis: "y",
                                responsive: true,
                                plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => " " + fmt.kg(c.parsed.x) } } },
                                scales: { x: { beginAtZero: true, ticks: kg_tick }, y: { grid: { display: false } } },
                            },
                        },
                        empty_text: parties.length ? "" : "No pending balance.",
                    },
                ],
            };
        },
    };
}
