// ─────────────────────────────────────────────────────────────
//  Stock Position Report  —  jari_core
//  Custom visual dashboard: animated cards + chart + styled table
// ─────────────────────────────────────────────────────────────

frappe.query_reports["Stock Position Report"] = {

    // ── FILTERS shown at the top of the report ────────────────
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

    // ── AFTER RENDER: inject full custom dashboard ────────────
    after_datatable_render: function(datatable_obj) {
        const report = frappe.query_report;
        if (!report || !report.data || !report.data.length) return;

        // Remove any previously injected dashboard so refresh works cleanly
        const existing = document.getElementById("jari-stock-dashboard");
        if (existing) existing.remove();

        const rows   = report.data;
        const result = _build_summary(rows);

        // Build and inject the dashboard HTML above the table
        const dashboard_html = _render_dashboard(result);
        const wrapper = document.querySelector(".datatable");
        if (wrapper) {
            wrapper.insertAdjacentHTML("beforebegin", dashboard_html);
            _animate_counters();
            _bind_hover_rows();
        }
    },

    // ── ROW FORMATTER: colour-code balance levels ─────────────
    formatter: function(value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);

        if (column.fieldname === "current_balance" && data) {
            const bal = parseFloat(data.current_balance) || 0;
            let color, bg, icon;

            if (bal >= 100) {
                color = "#166534"; bg = "#dcfce7"; icon = "▲";   // high — green
            } else if (bal >= 20) {
                color = "#92400e"; bg = "#fef3c7"; icon = "●";   // medium — amber
            } else {
                color = "#991b1b"; bg = "#fee2e2"; icon = "▼";   // low — red
            }

            value = `<span style="
                display:inline-flex;
                align-items:center;
                gap:5px;
                background:${bg};
                color:${color};
                border-radius:6px;
                padding:3px 10px;
                font-weight:700;
                font-size:13px;
                letter-spacing:.02em;
            ">${icon} ${parseFloat(data.current_balance).toFixed(3)} KG</span>`;
        }

        if (column.fieldname === "total_in" && data) {
            value = `<span style="color:#1d4ed8;font-weight:600;">
                +${parseFloat(data.total_in || 0).toFixed(3)}
            </span>`;
        }

        if (column.fieldname === "total_out" && data) {
            value = `<span style="color:#b45309;font-weight:600;">
                -${parseFloat(data.total_out || 0).toFixed(3)}
            </span>`;
        }

        if (column.fieldname === "txn_count" && data) {
            value = `<span style="
                background:#ede9fe;
                color:#5b21b6;
                border-radius:12px;
                padding:2px 10px;
                font-weight:700;
                font-size:12px;
            ">${data.txn_count}</span>`;
        }

        return value;
    }
};


// ─────────────────────────────────────────────────────────────
//  PRIVATE HELPERS
// ─────────────────────────────────────────────────────────────

function _build_summary(rows) {
    let total_balance = 0, total_in = 0, total_out = 0,
        total_txns = 0, dept_map = {}, product_map = {};

    rows.forEach(r => {
        total_balance += parseFloat(r.current_balance || 0);
        total_in      += parseFloat(r.total_in        || 0);
        total_out     += parseFloat(r.total_out       || 0);
        total_txns    += parseInt(r.txn_count         || 0);

        const d = r.department || "Unknown";
        const p = r.product    || "Unknown";
        dept_map[d]    = (dept_map[d]    || 0) + parseFloat(r.current_balance || 0);
        product_map[p] = (product_map[p] || 0) + parseFloat(r.current_balance || 0);
    });

    return {
        total_balance, total_in, total_out, total_txns,
        unique_products: Object.keys(product_map).length,
        unique_depts:    Object.keys(dept_map).length,
        dept_map, product_map
    };
}


function _render_dashboard(d) {

    // ── 6 animated summary cards ──────────────────────────────
    const cards = [
        {
            icon: "⚖️", label: "Total Stock",
            value: d.total_balance.toFixed(3), suffix: "KG",
            bg: "linear-gradient(135deg,#1e3a5f,#2563eb)",
            glow: "rgba(37,99,235,.35)"
        },
        {
            icon: "📥", label: "Total Inward",
            value: d.total_in.toFixed(3), suffix: "KG",
            bg: "linear-gradient(135deg,#064e3b,#059669)",
            glow: "rgba(5,150,105,.35)"
        },
        {
            icon: "📤", label: "Total Outward",
            value: d.total_out.toFixed(3), suffix: "KG",
            bg: "linear-gradient(135deg,#78350f,#d97706)",
            glow: "rgba(217,119,6,.35)"
        },
        {
            icon: "🔄", label: "Transactions",
            value: d.total_txns, suffix: "",
            bg: "linear-gradient(135deg,#4c1d95,#7c3aed)",
            glow: "rgba(124,58,237,.35)"
        },
        {
            icon: "📦", label: "Active Products",
            value: d.unique_products, suffix: "",
            bg: "linear-gradient(135deg,#0e7490,#06b6d4)",
            glow: "rgba(6,182,212,.35)"
        },
        {
            icon: "🏭", label: "Departments",
            value: d.unique_depts, suffix: "",
            bg: "linear-gradient(135deg,#065f46,#10b981)",
            glow: "rgba(16,185,129,.35)"
        },
    ];

    const cards_html = cards.map((c, i) => `
        <div class="jari-card" data-target="${c.value}"
             style="
                background:${c.bg};
                box-shadow:0 8px 32px ${c.glow};
                border-radius:16px;
                padding:22px 20px 18px;
                color:#fff;
                position:relative;
                overflow:hidden;
                cursor:default;
                transition:transform .25s ease, box-shadow .25s ease;
                animation: cardFadeIn .5s ease both;
                animation-delay:${i * 80}ms;
             "
             onmouseenter="this.style.transform='translateY(-6px) scale(1.03)';
                           this.style.boxShadow='0 18px 48px ${c.glow}'"
             onmouseleave="this.style.transform='translateY(0) scale(1)';
                           this.style.boxShadow='0 8px 32px ${c.glow}'"
        >
            <div style="font-size:28px;margin-bottom:6px;">${c.icon}</div>
            <div class="jari-count"
                 style="font-size:28px;font-weight:900;letter-spacing:-.5px;
                        font-family:monospace;">
                0
            </div>
            <div style="font-size:11px;font-weight:700;letter-spacing:.12em;
                        text-transform:uppercase;opacity:.8;margin-top:4px;">
                ${c.label}${c.suffix ? " · " + c.suffix : ""}
            </div>
            <div style="
                position:absolute;right:-18px;bottom:-18px;
                width:80px;height:80px;border-radius:50%;
                background:rgba(255,255,255,.07);
            "></div>
        </div>
    `).join("");

    // ── Department breakdown bars ─────────────────────────────
    const dept_entries = Object.entries(d.dept_map)
          .sort((a, b) => b[1] - a[1]);
    const max_val = dept_entries.length ? dept_entries[0][1] : 1;

    const dept_bars = dept_entries.map(([dept, bal], i) => {
        const pct  = max_val > 0 ? (bal / max_val * 100).toFixed(1) : 0;
        const hue  = (i * 47) % 360;
        return `
            <div style="margin-bottom:14px;
                        animation:barSlideIn .5s ease both;
                        animation-delay:${200 + i * 60}ms;"
                 onmouseenter="this.querySelector('.jari-bar-fill').style.filter='brightness(1.2)'"
                 onmouseleave="this.querySelector('.jari-bar-fill').style.filter='brightness(1)'">
                <div style="display:flex;justify-content:space-between;
                            margin-bottom:5px;font-size:13px;font-weight:600;
                            color:#374151;">
                    <span>🏭 ${dept}</span>
                    <span style="color:#6b7280;font-weight:700;">
                        ${bal.toFixed(3)} KG
                    </span>
                </div>
                <div style="background:#f1f5f9;border-radius:99px;
                            height:10px;overflow:hidden;">
                    <div class="jari-bar-fill" style="
                        width:0%;
                        height:100%;
                        border-radius:99px;
                        background:linear-gradient(90deg,
                            hsl(${hue},70%,45%),
                            hsl(${(hue+30)%360},80%,60%));
                        transition:width .9s cubic-bezier(.4,0,.2,1),
                                   filter .2s ease;
                        data-width:${pct}%;
                    " data-pct="${pct}"></div>
                </div>
            </div>
        `;
    }).join("");

    // ── Full dashboard wrapper ────────────────────────────────
    return `
        <style>
            @keyframes cardFadeIn {
                from { opacity:0; transform:translateY(16px) scale(.97); }
                to   { opacity:1; transform:translateY(0)    scale(1);   }
            }
            @keyframes barSlideIn {
                from { opacity:0; transform:translateX(-20px); }
                to   { opacity:1; transform:translateX(0);     }
            }
            @keyframes shimmer {
                0%   { background-position: -400px 0; }
                100% { background-position:  400px 0; }
            }
            .jari-card:active {
                transform: scale(.98) !important;
            }
            .datatable .dt-row:hover td {
                background: #eff6ff !important;
                transition: background .15s ease;
            }
        </style>

        <div id="jari-stock-dashboard" style="
            padding: 24px 4px 8px;
            font-family: -apple-system, BlinkMacSystemFont,
                         'Segoe UI', sans-serif;
        ">
            <!-- Header -->
            <div style="display:flex;align-items:center;gap:12px;
                        margin-bottom:20px;">
                <div style="
                    width:4px;height:32px;border-radius:2px;
                    background:linear-gradient(180deg,#2563eb,#7c3aed);
                "></div>
                <div>
                    <div style="font-size:18px;font-weight:800;
                                color:#111827;letter-spacing:-.3px;">
                        Stock Position Dashboard
                    </div>
                    <div style="font-size:12px;color:#6b7280;margin-top:2px;">
                        Live inventory snapshot · JARI Manufacturing Group
                    </div>
                </div>
                <div style="margin-left:auto;background:#f0fdf4;
                            border:1px solid #bbf7d0;border-radius:8px;
                            padding:6px 14px;font-size:12px;font-weight:700;
                            color:#166534;">
                    ● LIVE
                </div>
            </div>

            <!-- Summary Cards Grid -->
            <div style="
                display:grid;
                grid-template-columns:repeat(auto-fit,minmax(170px,1fr));
                gap:14px;
                margin-bottom:24px;
            ">
                ${cards_html}
            </div>

            <!-- Department Breakdown Panel -->
            <div style="
                background:#fff;
                border:1px solid #e5e7eb;
                border-radius:16px;
                padding:20px 24px;
                margin-bottom:20px;
                box-shadow:0 1px 4px rgba(0,0,0,.06);
            ">
                <div style="font-size:14px;font-weight:700;color:#111827;
                            margin-bottom:16px;display:flex;
                            align-items:center;gap:8px;">
                    📊 Department-wise Stock Distribution
                    <span style="font-size:11px;font-weight:400;
                                 color:#6b7280;margin-left:auto;">
                        Sorted by balance · highest first
                    </span>
                </div>
                ${dept_bars || '<p style="color:#6b7280;font-size:13px;">No data</p>'}
            </div>

            <!-- Divider before table -->
            <div style="font-size:13px;font-weight:700;color:#374151;
                        margin-bottom:10px;padding-left:2px;
                        display:flex;align-items:center;gap:8px;">
                📋 Detailed Stock Ledger
                <span style="font-size:11px;font-weight:400;
                             color:#9ca3af;">
                    Colour: 🟢 ≥100 KG &nbsp;|&nbsp;
                            🟡 20–99 KG &nbsp;|&nbsp;
                            🔴 &lt;20 KG
                </span>
            </div>
        </div>
    `;
}


function _animate_counters() {
    // Animate number cards from 0 to their target value
    document.querySelectorAll(".jari-card").forEach(card => {
        const raw    = card.dataset.target;
        const target = parseFloat(raw) || 0;
        const el     = card.querySelector(".jari-count");
        const isFloat= raw.includes(".");
        const dur    = 900;
        const start  = performance.now();

        function tick(now) {
            const pct = Math.min((now - start) / dur, 1);
            // ease-out cubic
            const ease = 1 - Math.pow(1 - pct, 3);
            const cur  = target * ease;
            el.textContent = isFloat ? cur.toFixed(3) : Math.round(cur);
            if (pct < 1) requestAnimationFrame(tick);
        }
        requestAnimationFrame(tick);
    });

    // Animate department progress bars after a short delay
    setTimeout(() => {
        document.querySelectorAll(".jari-bar-fill").forEach(bar => {
            bar.style.width = bar.dataset.pct + "%";
        });
    }, 150);
}


function _bind_hover_rows() {
    // Extra hover effect: highlight entire row on hover
    // Frappe's datatable replaces DOM on sort/filter so
    // we use event delegation on the wrapper instead
    const wrapper = document.querySelector(".datatable");
    if (!wrapper) return;

    wrapper.addEventListener("mouseover", e => {
        const row = e.target.closest(".dt-row");
        if (row) row.style.background = "#eff6ff";
    });
    wrapper.addEventListener("mouseout", e => {
        const row = e.target.closest(".dt-row");
        if (row) row.style.background = "";
    });
}
