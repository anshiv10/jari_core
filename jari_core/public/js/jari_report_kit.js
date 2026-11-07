/* ═══════════════════════════════════════════════════════════════════════
   JARI REPORT KIT  —  shared UI features for JARI Core Script Reports
   ───────────────────────────────────────────────────────────────────────
   Loaded on demand by each report:
       frappe.require("/assets/jari_core/js/jari_report_kit.js", ...)

   Features (configured per report):
     • KPI card panel (accent bar, icon, hover, tooltip, count-up)
     • ⬇ Download  → Excel (SheetJS, + Summary sheet) / PDF (client layout)
     • ✉ Email Report dialog
     • 📊 Quick Analytics dialog (summary pills + Chart.js charts)
     • 📅 Date Presets (Indian FY: April → March)
     • ✕ Clear Filters

   Read-only: never writes data. Server calculations are untouched.
   ═══════════════════════════════════════════════════════════════════════ */

(function () {
    if (window.jari_report_kit) {
        return;
    }

    const CHART_JS_URL = "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js";
    const SHEET_JS_URL = "https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.18.5/xlsx.full.min.js";

    const configs = {};
    let chart_seq = 0;

    /* ── formatting helpers ─────────────────────────────────────────── */
    const fmt = {
        kg(v) {
            const n = parseFloat(v) || 0;
            return n.toLocaleString("en-IN", { minimumFractionDigits: 3, maximumFractionDigits: 3 }) + " kg";
        },
        kg_short(v) {
            const n = parseFloat(v) || 0;
            return n.toLocaleString("en-IN", { maximumFractionDigits: 1 });
        },
        num(v) {
            return (parseInt(v, 10) || 0).toLocaleString("en-IN");
        },
        esc(s) {
            return String(s === undefined || s === null ? "" : s)
                .replace(/&/g, "&amp;").replace(/</g, "&lt;")
                .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
        },
        strip(s) {
            return String(s === undefined || s === null ? "" : s).replace(/<[^>]*>/g, "").trim();
        },
        month_label(date_str) {
            if (!date_str) {
                return "";
            }
            const p = String(date_str).substring(0, 10).split("-");
            const names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
            return p.length === 3 ? names[parseInt(p[1], 10) - 1] + " " + p[0] : String(date_str);
        },
        month_key(date_str) {
            return date_str ? String(date_str).substring(0, 7) : "";
        },
    };

    /* ── styles ─────────────────────────────────────────────────────── */
    function inject_styles() {
        if (document.getElementById("jrk-styles")) {
            return;
        }
        const s = document.createElement("style");
        s.id = "jrk-styles";
        s.textContent =
            ".jrk-kpi-wrap{padding:6px 0 6px;border-bottom:1px solid #e9ecef;margin-bottom:10px;}" +
            ".jrk-kpi-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;padding:14px 2px 8px;}" +
            "@media (max-width: 992px){.jrk-kpi-grid{grid-template-columns:repeat(2,1fr);}}" +
            ".jrk-kpi-card{background:#fff;border:1px solid #d1d8dd;border-radius:12px;padding:18px 14px 16px;" +
            "text-align:center;position:relative;overflow:hidden;cursor:default;" +
            "transition:transform .18s ease,box-shadow .18s ease,border-color .18s ease;box-shadow:0 1px 4px rgba(0,0,0,.06);}" +
            ".jrk-kpi-card::before{content:'';position:absolute;top:0;left:0;right:0;height:4px;" +
            "background:var(--card-accent,#2490ef);border-radius:12px 12px 0 0;}" +
            ".jrk-kpi-card:hover{transform:translateY(-3px);box-shadow:0 6px 18px rgba(0,0,0,.12);border-color:#b0bec5;}" +
            ".jrk-kpi-icon{font-size:18px;line-height:1;margin:2px 0 6px;}" +
            ".jrk-kpi-val{font-size:19px;font-weight:700;line-height:1.2;margin-bottom:6px;letter-spacing:-.2px;}" +
            ".jrk-kpi-lbl{font-size:10px;font-weight:600;color:#6c757d;text-transform:uppercase;letter-spacing:.5px;" +
            "white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}" +
            ".jrk-pill{display:inline-flex;align-items:center;gap:6px;color:#fff;padding:7px 16px;border-radius:30px;" +
            "font-size:12px;font-weight:700;box-shadow:0 3px 10px rgba(0,0,0,.2);margin:3px;}" +
            ".jrk-chart-box{background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:14px 16px;}" +
            ".jrk-chart-title{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.6px;color:#64748b;" +
            "margin-bottom:10px;text-align:center;}";
        document.head.appendChild(s);
    }

    /* ── data access ────────────────────────────────────────────────── */
    function all_rows() {
        const r = frappe.query_report;
        return r && Array.isArray(r.data) ? r.data.filter(Boolean) : [];
    }

    function data_rows(cfg) {
        return all_rows().filter((row) => cfg.is_data_row(row));
    }

    function no_data() {
        frappe.msgprint({ title: __("No Data"), message: __("Run the report first."), indicator: "orange" });
    }

    function load_script(url, test, cb, name) {
        if (test()) {
            cb();
            return;
        }
        const s = document.createElement("script");
        s.src = url;
        s.onload = () => cb();
        s.onerror = () => frappe.msgprint({
            title: __("Error"),
            message: __("Failed to load {0}. Check the internet connection.", [name]),
            indicator: "red",
        });
        document.head.appendChild(s);
    }

    /* ── KPI panel ──────────────────────────────────────────────────── */
    function kpi_wrapper(report, cfg) {
        inject_styles();
        const id = "jrk-kpi-" + cfg.key;
        const main = report && report.page && report.page.main ? report.page.main[0] : null;
        let el = main ? main.querySelector("#" + id) : null;
        if (el) {
            return el;
        }
        el = document.createElement("div");
        el.id = id;
        el.className = "jrk-kpi-wrap";
        try {
            const form = report.page.main.find(".frappe-form")[0];
            if (form) {
                form.parentNode.insertBefore(el, form.nextSibling);
            } else if (main) {
                main.insertBefore(el, main.firstChild);
            }
        } catch (e) {
            if (main) {
                main.insertBefore(el, main.firstChild);
            }
        }
        return el;
    }

    function count_up(el, target, accent) {
        let cur = 0;
        const step = Math.max(1, Math.ceil(target / 40));
        el.textContent = "0";
        if (accent) {
            el.style.color = accent;
        }
        const t = setInterval(() => {
            cur += step;
            if (cur >= target) {
                el.textContent = fmt.num(target);
                clearInterval(t);
            } else {
                el.textContent = fmt.num(cur);
            }
        }, 30);
    }

    function draw_kpis(report) {
        report = report || frappe.query_report;
        if (!report) {
            return;
        }
        const cfg = configs[report.report_name];
        if (!cfg) {
            return;
        }
        const wrapper = kpi_wrapper(report, cfg);
        if (!wrapper) {
            return;
        }
        let cards = [];
        try {
            cards = cfg.kpis(data_rows(cfg), all_rows(), fmt) || [];
        } catch (e) {
            console.error("JARI KPI error", e);
        }
        let html = '<div class="jrk-kpi-grid">';
        cards.forEach((c) => {
            html += '<div class="jrk-kpi-card" style="--card-accent:' + c.accent + ';"' +
                (c.tip ? ' title="' + fmt.esc(c.tip) + '"' : "") + ">" +
                '<div class="jrk-kpi-icon">' + c.icon + "</div>" +
                '<div class="jrk-kpi-val" style="color:' + c.accent + ';">' + fmt.esc(c.val) + "</div>" +
                '<div class="jrk-kpi-lbl">' + fmt.esc(c.lbl) + "</div></div>";
        });
        html += "</div>";
        wrapper.innerHTML = html;

        const vals = wrapper.querySelectorAll(".jrk-kpi-val");
        cards.forEach((c, i) => {
            if (c.is_count && c.raw > 0 && vals[i]) {
                count_up(vals[i], c.raw, c.accent);
            }
        });
        cfg._last_kpis = cards;
    }

    function init_kpis(report, cfg) {
        kpi_wrapper(report, cfg);
        let attempts = 0;
        const poll = setInterval(() => {
            attempts++;
            if (all_rows().length > 0 || attempts > 30) {
                clearInterval(poll);
                draw_kpis(report);
            }
        }, 200);
    }

    /* ── Excel ──────────────────────────────────────────────────────── */
    function download_excel(cfg) {
        const rows = all_rows();
        if (!rows.length) {
            no_data();
            return;
        }
        frappe.show_alert({ message: __("Preparing Excel…"), indicator: "blue" }, 2);
        load_script(SHEET_JS_URL, () => !!window.XLSX, () => {
            const cols = frappe.query_report.columns || [];
            const sheet = [cols.map((c) => c.label || c.fieldname)];
            rows.forEach((r) => {
                sheet.push(cols.map((c) => {
                    const v = r[c.fieldname];
                    if (v === undefined || v === null || v === "") {
                        return "";
                    }
                    const ft = (c.fieldtype || "").toLowerCase();
                    if (ft === "float" || ft === "currency" || ft === "percent") {
                        return parseFloat(v) || 0;
                    }
                    if (ft === "int") {
                        return parseInt(v, 10) || 0;
                    }
                    return fmt.strip(v);
                }));
            });

            const wb = XLSX.utils.book_new();
            const ws = XLSX.utils.aoa_to_sheet(sheet);
            ws["!cols"] = sheet[0].map((_, ci) => ({
                wch: Math.min(40, sheet.reduce((m, row) => Math.max(m, String(row[ci] || "").length), 10) + 2),
            }));
            XLSX.utils.book_append_sheet(wb, ws, cfg.sheet_name || "Report");

            const summary = [["KPI", "Value"]];
            (cfg._last_kpis || []).forEach((k) => summary.push([k.lbl, fmt.strip(k.val)]));
            const fv = filter_values();
            summary.push([], ["Filter", "Value"]);
            Object.keys(fv).forEach((k) => {
                if (fv[k]) {
                    summary.push([k.replace(/_/g, " "), String(fv[k])]);
                }
            });
            const ws2 = XLSX.utils.aoa_to_sheet(summary);
            ws2["!cols"] = [{ wch: 30 }, { wch: 30 }];
            XLSX.utils.book_append_sheet(wb, ws2, "Summary");

            const fname = cfg.file_prefix + "_" + frappe.datetime.nowdate() + ".xlsx";
            XLSX.writeFile(wb, fname);
            frappe.show_alert({ message: __("Downloaded: {0}", [fname]), indicator: "green" }, 4);
        }, "SheetJS");
    }

    function filter_values() {
        try {
            return frappe.query_report.get_filter_values() || {};
        } catch (e) {
            return {};
        }
    }

    /* ── PDF (client print layout) ──────────────────────────────────── */
    function download_pdf(cfg) {
        const rows = all_rows();
        if (!rows.length) {
            no_data();
            return;
        }
        const report = frappe.query_report;
        const template = report.report_settings && report.report_settings.html_format;
        let body = "";

        if (template) {
            try {
                body = frappe.render_template(template, {
                    data: rows,
                    original_data: rows,
                    filters: filter_values(),
                    columns: report.columns || [],
                    title: cfg.title,
                });
            } catch (e) {
                console.error("JARI print template error", e);
                body = "";
            }
        }
        if (!body) {
            body = generic_table_html(cfg, rows, false);
        }

        const html = "<!DOCTYPE html><html><head><meta charset='utf-8'><title>" + fmt.esc(cfg.title) + "</title>" +
            "<style>body{margin:10mm;}@page{size:A4 " + (cfg.orientation || "landscape") +
            ";margin:8mm;}@media print{body{margin:0;}thead{display:table-header-group;}tr{page-break-inside:avoid;}}</style>" +
            "</head><body>" + body +
            "<script>window.onload=function(){document.title='" + cfg.file_prefix + "_" + frappe.datetime.nowdate() +
            "';setTimeout(function(){window.print();},400);};<\/script></body></html>";

        const win = window.open("", "_blank");
        if (!win) {
            frappe.msgprint({ title: __("Popup Blocked"), message: __("Allow popups, then click PDF again."), indicator: "orange" });
            return;
        }
        win.document.open();
        win.document.write(html);
        win.document.close();
    }

    /* ── generic table (email / PDF fallback) ───────────────────────── */
    function generic_table_html(cfg, rows, inline) {
        const cols = (frappe.query_report.columns || []).filter((c) => !c.hidden);
        const th = inline
            ? 'style="padding:7px 9px;background:#1e3a5f;color:#fff;font-size:11px;font-weight:600;border:1px solid #2563eb;white-space:nowrap;"'
            : 'style="background:#1e3a5f;color:#fff;padding:5px 6px;font-size:9px;border:1px solid #2563eb;white-space:nowrap;"';
        let h = '<div style="font-family:Arial,sans-serif;"><div style="font-size:15px;font-weight:700;color:#1e3a5f;">' +
            fmt.esc(cfg.title) + "</div>" +
            '<div style="font-size:10px;color:#64748b;margin:3px 0 10px;">Generated ' + frappe.datetime.now_datetime() + "</div>" +
            '<table cellpadding="0" cellspacing="0" style="width:100%;border-collapse:collapse;"><tr>';
        cols.forEach((c) => {
            h += "<th " + th + ">" + fmt.esc(c.label || c.fieldname) + "</th>";
        });
        h += "</tr>";
        rows.forEach((r, i) => {
            const strong = r.is_group || r.is_total;
            const bg = r.is_group ? "#eef2ff" : r.is_total ? "#f1f5f9" : (i % 2 ? "#ffffff" : "#f8fafc");
            h += '<tr style="background:' + bg + ";" + (strong ? "font-weight:700;" : "") + '">';
            cols.forEach((c) => {
                let v = r[c.fieldname];
                const ft = (c.fieldtype || "").toLowerCase();
                if ((ft === "float" || ft === "currency") && v !== undefined && v !== null && v !== "") {
                    v = (parseFloat(v) || 0).toFixed(c.precision || 3);
                }
                h += '<td style="padding:4px 7px;border:1px solid #e2e8f0;font-size:' + (inline ? "11px" : "9px") +
                    ';color:#1e293b;white-space:nowrap;">' + fmt.esc(fmt.strip(v)) + "</td>";
            });
            h += "</tr>";
        });
        return h + "</table></div>";
    }

    /* ── Email ──────────────────────────────────────────────────────── */
    function open_email_dialog(cfg) {
        const rows = all_rows();
        if (!rows.length) {
            no_data();
            return;
        }
        const dlg = new frappe.ui.Dialog({
            title: "✉ " + __("Email Report") + " — " + cfg.title,
            fields: [
                { fieldname: "recipient", fieldtype: "Data", label: __("Recipient Email"), options: "Email", reqd: 1 },
                { fieldname: "subject", fieldtype: "Data", label: __("Subject"), default: cfg.title + " — " + frappe.datetime.nowdate() },
                { fieldname: "note", fieldtype: "Small Text", label: __("Additional Note (optional)") },
            ],
            primary_action_label: __("Send Email"),
            primary_action(vals) {
                let content = "";
                if (vals.note) {
                    content += '<p style="font-family:Arial,sans-serif;font-size:12px;">' + frappe.utils.escape_html(vals.note) + "</p>";
                }
                const kpis = cfg._last_kpis || [];
                if (kpis.length) {
                    content += '<table cellpadding="0" cellspacing="0" style="border-collapse:collapse;margin-bottom:12px;font-family:Arial,sans-serif;"><tr>';
                    kpis.forEach((k) => {
                        content += '<td style="padding:8px 12px;border:1px solid #e2e8f0;border-top:3px solid ' + k.accent + ';text-align:center;">' +
                            '<div style="font-size:14px;font-weight:700;color:' + k.accent + ';">' + fmt.esc(k.val) + "</div>" +
                            '<div style="font-size:9px;color:#6c757d;text-transform:uppercase;">' + fmt.esc(k.lbl) + "</div></td>";
                    });
                    content += "</tr></table>";
                }
                content += generic_table_html(cfg, rows, true);

                const btn = dlg.get_primary_btn();
                btn.prop("disabled", true).text(__("Sending…"));
                frappe.call({
                    method: "frappe.core.doctype.communication.email.make",
                    args: {
                        recipients: vals.recipient,
                        subject: vals.subject || cfg.title,
                        content: content,
                        send_email: 1,
                    },
                    callback() {
                        dlg.hide();
                        frappe.show_alert({ message: __("Email sent to {0}", [vals.recipient]), indicator: "green" }, 5);
                    },
                    error() {
                        btn.prop("disabled", false).text(__("Send Email"));
                        frappe.show_alert({ message: __("Failed to send."), indicator: "red" }, 5);
                    },
                });
            },
        });
        dlg.show();
    }

    /* ── Quick Analytics ────────────────────────────────────────────── */
    function open_analytics(cfg) {
        const rows = data_rows(cfg);
        if (!rows.length) {
            no_data();
            return;
        }
        let spec;
        try {
            spec = cfg.analytics(rows, all_rows(), fmt);
        } catch (e) {
            console.error("JARI analytics error", e);
            frappe.msgprint(__("Could not build analytics for this data."));
            return;
        }

        chart_seq++;
        const ids = spec.charts.map((_, i) => "jrk-chart-" + chart_seq + "-" + i);

        let html = '<div style="padding:6px 2px 0;"><div style="display:flex;flex-wrap:wrap;gap:4px;margin-bottom:18px;justify-content:center;">';
        (spec.pills || []).forEach((p) => {
            html += '<span class="jrk-pill" style="background:linear-gradient(135deg,' + p.g1 + "," + p.g2 + ');">' +
                p.icon + " " + fmt.esc(p.text) + "</span>";
        });
        html += '</div><div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;">';
        spec.charts.forEach((c, i) => {
            html += '<div class="jrk-chart-box"><div class="jrk-chart-title">' + fmt.esc(c.title) +
                '</div><canvas id="' + ids[i] + '" style="max-height:250px;"></canvas>' +
                (c.empty_text ? '<div style="text-align:center;color:#94a3b8;font-size:11px;">' + fmt.esc(c.empty_text) + "</div>" : "") +
                "</div>";
        });
        html += "</div></div>";

        inject_styles();
        const dlg = new frappe.ui.Dialog({
            title: "📊 " + cfg.title + " — " + __("Quick Analytics"),
            size: "extra-large",
            fields: [{ fieldname: "charts_html", fieldtype: "HTML", options: html }],
        });
        dlg.show();

        load_script(CHART_JS_URL, () => !!(window.Chart && typeof window.Chart.register === "function"), () => {
            setTimeout(() => {
                spec.charts.forEach((c, i) => {
                    const canvas = document.getElementById(ids[i]);
                    if (!canvas) {
                        return;
                    }
                    const existing = typeof Chart.getChart === "function" ? Chart.getChart(canvas) : null;
                    if (existing) {
                        existing.destroy();
                    }
                    try {
                        new Chart(canvas, c.config);
                    } catch (e) {
                        console.error("JARI chart error", e);
                    }
                });
            }, 400);
        }, "Chart.js");
    }

    /* ── Date presets / clear filters ───────────────────────────────── */
    function fy_start_year() {
        const now = new Date();
        return now.getMonth() >= 3 ? now.getFullYear() : now.getFullYear() - 1;
    }

    function add_date_presets(report, cfg) {
        if (!cfg.date_filters) {
            return;
        }
        const from_f = cfg.date_filters.from;
        const to_f = cfg.date_filters.to;
        const today = frappe.datetime.get_today();
        const now = new Date();
        const fy = fy_start_year();
        const last_month = frappe.datetime.add_months(today, -1);
        const q_start_month = Math.floor(now.getMonth() / 3) * 3 + 1;

        [
            { label: __("Today"), from: today, to: today },
            { label: __("This Month"), from: frappe.datetime.month_start(), to: frappe.datetime.month_end() },
            { label: __("Last Month"), from: frappe.datetime.month_start(last_month), to: frappe.datetime.month_end(last_month) },
            { label: __("This Quarter"), from: now.getFullYear() + "-" + String(q_start_month).padStart(2, "0") + "-01", to: today },
            { label: __("This FY"), from: fy + "-04-01", to: today },
            { label: __("Full This FY"), from: fy + "-04-01", to: (fy + 1) + "-03-31" },
            { label: __("Last FY"), from: (fy - 1) + "-04-01", to: fy + "-03-31" },
            { label: __("All Dates"), from: "", to: "" },
        ].forEach((p) => {
            report.page.add_inner_button(p.label, () => {
                report.set_filter_value(from_f, p.from);
                report.set_filter_value(to_f, p.to);
            }, "📅 " + __("Date Presets"));
        });
    }

    function add_clear_filters(report, cfg) {
        report.page.add_inner_button("✕ " + __("Clear Filters"), () => {
            const defaults = cfg.clear_defaults ? cfg.clear_defaults() : {};
            (cfg.clear_filters || []).forEach((f) => {
                report.set_filter_value(f, defaults[f] !== undefined ? defaults[f] : "");
            });
        });
    }

    /* ── public API ─────────────────────────────────────────────────── */
    function setup(report, cfg) {
        cfg.is_data_row = cfg.is_data_row || ((r) => !r.is_group && !r.is_total && !r.is_opening);
        configs[report.report_name] = cfg;
        inject_styles();

        if (cfg.on_setup) {
            cfg.on_setup(report, fy_start_year());
        }

        report.page.add_inner_button(__("Excel"), () => download_excel(cfg), "⬇ " + __("Download"));
        report.page.add_inner_button(__("PDF"), () => download_pdf(cfg), "⬇ " + __("Download"));
        report.page.add_inner_button("✉ " + __("Email Report"), () => open_email_dialog(cfg));
        report.page.add_inner_button("📊 " + __("Quick Analytics"), () => open_analytics(cfg));
        add_date_presets(report, cfg);
        add_clear_filters(report, cfg);

        init_kpis(report, cfg);
    }

    function on_refresh(report) {
        report = report || frappe.query_report;
        const cfg = report && configs[report.report_name];
        if (!cfg) {
            return;
        }
        const w = kpi_wrapper(report, cfg);
        if (w) {
            w.innerHTML = '<div style="padding:20px;text-align:center;color:#94a3b8;font-size:13px;">↻ ' + __("Loading…") + "</div>";
        }
        setTimeout(() => draw_kpis(report), 800);
        setTimeout(() => draw_kpis(report), 2500);
    }

    window.jari_report_kit = {
        setup: setup,
        draw_kpis: draw_kpis,
        on_refresh: on_refresh,
        fmt: fmt,
        fy_start_year: fy_start_year,
    };
})();
