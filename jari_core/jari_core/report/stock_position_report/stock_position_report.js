// ─────────────────────────────────────────────────────────────
//  Stock Position Report  —  jari_core
//  Structure matches Image 2: colored border cards + clean table
// ─────────────────────────────────────────────────────────────

frappe.query_reports["Stock Position Report"] = {

    // ── FILTERS ───────────────────────────────────────────────
    filters: [
        {
            fieldname: "company",
            label: __("Company"),
            fieldtype: "Link",
            options: "Company Master",
            reqd: 0
        },
        {
            fieldname: "department",
            label: __("Department"),
            fieldtype: "Link",
            options: "Department Master",
            reqd: 0
        },
        {
            fieldname: "product",
            label: __("Product"),
            fieldtype: "Link",
            options: "Product Master",
            reqd: 0
        }
    ],

    // ── ON LOAD: inject cards after Frappe finishes rendering ─
    onload: function(report) {
        // Store reference so after_refresh can access it
        frappe.query_reports["Stock Position Report"]._report = report;
    },

    // ── AFTER EVERY REFRESH: rebuild the dashboard ────────────
    after_datatable_render: function() {
        // Small delay to let Frappe finish all its own DOM writes
        setTimeout(function() {
            _inject_dashboard();
        }, 120);
    },

    // ── ROW FORMATTER: colour-code key columns ────────────────
    formatter: function(value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        if (!data) return value;

        if (column.fieldname === "current_balance") {
            const bal = parseFloat(data.current_balance) || 0;
            let color, bg;
            if      (bal >= 100) { color = "#166534"; bg = "#dcfce7"; }
            else if (bal >= 20)  { color = "#92400e"; bg = "#fef3c7"; }
            else                 { color = "#991b1b"; bg = "#fee2e2"; }
            return `<span style="
                background:${bg};color:${color};
                border-radius:5px;padding:2px 9px;
                font-weight:700;font-size:12.5px;">
                ${parseFloat(data.current_balance).toFixed(3)} KG
            </span>`;
        }

        if (column.fieldname === "total_in") {
            return `<span style="color:#1d4ed8;font-weight:600;">
                +${parseFloat(data.total_in || 0).toFixed(3)}
            </span>`;
        }

        if (column.fieldname === "total_out") {
            return `<span style="color:#b45309;font-weight:600;">
                -${parseFloat(data.total_out || 0).toFixed(3)}
            </span>`;
        }

        if (column.fieldname === "txn_count") {
            return `<span style="
                background:#ede9fe;color:#5b21b6;
                border-radius:10px;padding:2px 9px;
                font-weight:700;font-size:12px;">
                ${data.txn_count}
            </span>`;
        }

        return value;
    }
};


// ─────────────────────────────────────────────────────────────
//  DASHBOARD INJECTION
// ─────────────────────────────────────────────────────────────

function _inject_dashboard() {

    // Remove previous dashboard on re-render
    var old = document.getElementById("jari-spr-dashboard");
    if (old) old.remove();

    // Get data from the active report
    var report = frappe.query_report;
    if (!report || !report.data || !report.data.length) return;

    var rows = report.data;

    // ── Calculate summary numbers ──────────────────────────
    var total_balance   = 0;
    var total_in        = 0;
    var total_out       = 0;
    var total_txns      = 0;
    var products        = {};
    var departments     = {};
    var dept_balances   = {};

    rows.forEach(function(r) {
        total_balance += parseFloat(r.current_balance || 0);
        total_in      += parseFloat(r.total_in        || 0);
        total_out     += parseFloat(r.total_out       || 0);
        total_txns    += parseInt(r.txn_count         || 0);
        products[r.product]       = 1;
        departments[r.department] = 1;
        var d = r.department || "Unknown";
        dept_balances[d] = (dept_balances[d] || 0) + parseFloat(r.current_balance || 0);
    });

    var unique_products = Object.keys(products).length;
    var unique_depts    = Object.keys(departments).length;

    // ── Card definitions matching Image 2 style ───────────
    // White bg, colored top border, colored number
    var cards = [
        {
            label: "TOTAL STOCK",
            value: total_balance.toFixed(3),
            suffix: "KG",
            color: "#2490ef",   // blue
            border: "#2490ef"
        },
        {
            label: "TOTAL INWARD",
            value: total_in.toFixed(3),
            suffix: "KG",
            color: "#28a745",   // green
            border: "#28a745"
        },
        {
            label: "TOTAL OUTWARD",
            value: total_out.toFixed(3),
            suffix: "KG",
            color: "#f59e0b",   // amber
            border: "#f59e0b"
        },
        {
            label: "TRANSACTIONS",
            value: total_txns,
            suffix: "",
            color: "#7c3aed",   // purple
            border: "#7c3aed"
        },
        {
            label: "ACTIVE PRODUCTS",
            value: unique_products,
            suffix: "",
            color: "#0d9488",   // teal
            border: "#0d9488"
        },
        {
            label: "DEPARTMENTS",
            value: unique_depts,
            suffix: "",
            color: "#dc2626",   // red
            border: "#dc2626"
        }
    ];

    // ── Build cards HTML ───────────────────────────────────
    var cards_html = cards.map(function(c, i) {
        return `
            <div class="jari-spr-card"
                 data-final="${c.value}"
                 data-is-float="${String(c.value).includes('.')}"
                 style="
                    background:#fff;
                    border:1px solid #e5e7eb;
                    border-top:4px solid ${c.border};
                    border-radius:6px;
                    padding:16px 20px 14px;
                    cursor:default;
                    transition:box-shadow .2s ease, transform .2s ease;
                    animation:jariCardIn .35s ease both;
                    animation-delay:${i * 55}ms;
                 "
                 onmouseenter="
                    this.style.boxShadow='0 4px 16px rgba(0,0,0,.10)';
                    this.style.transform='translateY(-3px)';
                 "
                 onmouseleave="
                    this.style.boxShadow='none';
                    this.style.transform='translateY(0)';
                 "
            >
                <div style="
                    font-size:11px;
                    font-weight:700;
                    letter-spacing:.1em;
                    color:#6b7280;
                    margin-bottom:8px;
                    text-transform:uppercase;
                ">
                    ${c.label}
                </div>
                <div class="jari-spr-num" style="
                    font-size:26px;
                    font-weight:800;
                    color:${c.color};
                    letter-spacing:-.5px;
                    line-height:1;
                ">
                    0
                </div>
                ${c.suffix ? `<div style="font-size:11px;color:#9ca3af;margin-top:4px;font-weight:600;">${c.suffix}</div>` : ""}
            </div>
        `;
    }).join("");

    // ── Build dept bar rows ───────────────────────────────
    var dept_entries = Object.entries(dept_balances)
        .sort(function(a, b) { return b[1] - a[1]; });
    var max_val = dept_entries.length ? dept_entries[0][1] : 1;

    var dept_colors = [
        "#2490ef","#28a745","#f59e0b","#7c3aed","#0d9488","#dc2626","#ec4899"
    ];

    var bars_html = dept_entries.map(function(entry, i) {
        var dept = entry[0];
        var bal  = entry[1];
        var pct  = max_val > 0 ? (bal / max_val * 100).toFixed(1) : 0;
        var col  = dept_colors[i % dept_colors.length];
        return `
            <div style="
                display:flex;
                align-items:center;
                gap:12px;
                padding:7px 0;
                border-bottom:1px solid #f3f4f6;
                animation:jariBarIn .4s ease both;
                animation-delay:${300 + i * 50}ms;
            ">
                <div style="
                    width:130px;
                    font-size:12.5px;
                    font-weight:600;
                    color:#374151;
                    flex-shrink:0;
                    white-space:nowrap;
                    overflow:hidden;
                    text-overflow:ellipsis;
                ">
                    ${dept}
                </div>
                <div style="
                    flex:1;
                    background:#f1f5f9;
                    border-radius:99px;
                    height:8px;
                    overflow:hidden;
                ">
                    <div class="jari-bar-fill"
                         data-pct="${pct}"
                         style="
                            width:0%;
                            height:100%;
                            border-radius:99px;
                            background:${col};
                            transition:width .8s cubic-bezier(.4,0,.2,1);
                         ">
                    </div>
                </div>
                <div style="
                    width:90px;
                    text-align:right;
                    font-size:12.5px;
                    font-weight:700;
                    color:#374151;
                    flex-shrink:0;
                ">
                    ${bal.toFixed(3)} KG
                </div>
            </div>
        `;
    }).join("");

    // ── Assemble full dashboard ────────────────────────────
    var dashboard_html = `
        <style>
            @keyframes jariCardIn {
                from { opacity:0; transform:translateY(10px); }
                to   { opacity:1; transform:translateY(0);    }
            }
            @keyframes jariBarIn {
                from { opacity:0; transform:translateX(-12px); }
                to   { opacity:1; transform:translateX(0);     }
            }
            .jari-spr-card:active {
                transform: scale(.98) !important;
            }
        </style>

        <div id="jari-spr-dashboard" style="
            margin-bottom: 0px;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        ">
            <!-- ── Summary Cards Row ── -->
            <div style="
                display:grid;
                grid-template-columns:repeat(6,1fr);
                gap:10px;
                margin-bottom:16px;
            ">
                ${cards_html}
            </div>

            <!-- ── Department Breakdown ── -->
            <div style="
                background:#fff;
                border:1px solid #e5e7eb;
                border-radius:6px;
                padding:16px 20px;
                margin-bottom:16px;
            ">
                <div style="
                    display:flex;
                    align-items:center;
                    justify-content:space-between;
                    margin-bottom:10px;
                ">
                    <div style="
                        font-size:12px;
                        font-weight:700;
                        letter-spacing:.08em;
                        text-transform:uppercase;
                        color:#374151;
                    ">
                        Department-wise Stock Balance
                    </div>
                    <div style="
                        font-size:11px;
                        color:#9ca3af;
                        font-weight:500;
                    ">
                        Sorted highest → lowest
                    </div>
                </div>
                ${bars_html || '<div style="color:#9ca3af;font-size:13px;padding:8px 0;">No department data</div>'}
            </div>

            <!-- ── Legend strip above table ── -->
            <div style="
                display:flex;
                align-items:center;
                gap:16px;
                margin-bottom:8px;
                padding:0 2px;
                font-size:12px;
                color:#6b7280;
                font-weight:500;
            ">
                <span>Balance levels:</span>
                <span style="background:#dcfce7;color:#166534;
                             border-radius:4px;padding:2px 8px;
                             font-weight:700;">
                    ≥ 100 KG  High
                </span>
                <span style="background:#fef3c7;color:#92400e;
                             border-radius:4px;padding:2px 8px;
                             font-weight:700;">
                    20–99 KG  Medium
                </span>
                <span style="background:#fee2e2;color:#991b1b;
                             border-radius:4px;padding:2px 8px;
                             font-weight:700;">
                    &lt; 20 KG  Low
                </span>
            </div>
        </div>
    `;

    // ── Find the correct injection point ──────────────────
    // Frappe renders: .page-content > .frappe-card > .report-wrapper
    // The datatable sits inside .report-wrapper
    // We inject BEFORE the datatable, INSIDE the report wrapper

    var inject_target = (
        document.querySelector(".report-wrapper .datatable") ||
        document.querySelector(".datatable-wrapper") ||
        document.querySelector(".datatable")
    );

    if (!inject_target) {
        // Fallback: inject before the filter area
        var fallback = document.querySelector(".filter-section");
        if (fallback) {
            fallback.insertAdjacentHTML("afterend", dashboard_html);
        }
        return;
    }

    inject_target.insertAdjacentHTML("beforebegin", dashboard_html);

    // ── Animate counters ──────────────────────────────────
    var card_els = document.querySelectorAll(".jari-spr-card");
    card_els.forEach(function(card) {
        var final_val = parseFloat(card.dataset.final) || 0;
        var is_float  = card.dataset.isFloat === "true";
        var num_el    = card.querySelector(".jari-spr-num");
        if (!num_el) return;

        var duration  = 800;
        var start_ts  = null;

        function animate(ts) {
            if (!start_ts) start_ts = ts;
            var elapsed = ts - start_ts;
            var progress = Math.min(elapsed / duration, 1);
            // ease-out cubic
            var eased = 1 - Math.pow(1 - progress, 3);
            var current = final_val * eased;
            num_el.textContent = is_float
                ? current.toFixed(3)
                : Math.round(current);
            if (progress < 1) requestAnimationFrame(animate);
        }
        requestAnimationFrame(animate);
    });

    // ── Animate progress bars ──────────────────────────────
    setTimeout(function() {
        document.querySelectorAll(".jari-bar-fill").forEach(function(bar) {
            bar.style.width = (bar.dataset.pct || 0) + "%";
        });
    }, 100);
}