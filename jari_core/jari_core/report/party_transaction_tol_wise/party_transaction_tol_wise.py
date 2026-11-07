"""
Party Transaction Tol Wise
(client reference: "Check Transaction - Tol wise")

Weight ledger of one party (karigar / jobworker / customer / supplier):

    Debit  (Udhar) = material ISSUED to the party      (KG)
    Credit (Jama)  = material RECEIVED from the party  (KG)
    Balance        = running Debit - Credit
                     = material currently lying with the party

Source: submitted Inventory Ledger movements only (read-only).
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, today

from jari_core.jari_core.jari_report_utils import (
    ISSUE_DOCTYPES,
    ORIGIN_TRANSACTION_TYPES,
    RECEIVE_DOCTYPES,
    get_doc_parties,
    get_doc_qualities,
    get_party_labels,
    get_product_info,
    get_row_parties,
    is_excluded_origin,
    load_ledger_rows,
    merge_parties,
    product_label,
)


def execute(filters=None):
    filters = frappe._dict(filters or {})

    if not filters.get("company"):
        frappe.throw(_("Please select Company."))

    if filters.get("party") and not filters.get("party_type"):
        frappe.throw(_("Please select Party Type."))

    from_date = getdate(filters.from_date) if filters.get("from_date") else None
    to_date = getdate(filters.get("to_date") or today())

    if from_date and from_date > to_date:
        frappe.throw(_("From Date cannot be after To Date."))

    entries = get_party_entries(filters, to_date)
    data = build_rows(entries, from_date, filters)

    # KPI cards are drawn client-side by jari_report_kit.js.
    return get_columns(), data


# ---------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------
def get_party_entries(filters, to_date):
    ledger = load_ledger_rows(
        filters.company,
        to_date=to_date,
        product=filters.get("product"),
    )

    movements = []
    for row in ledger:
        if (
            row.reference_doctype in ISSUE_DOCTYPES
            and flt(row.out_weight) > 0
            and row.transaction_type != "Cancellation Reversal"
        ):
            row.debit = flt(row.out_weight, 6)
            row.credit = 0
            movements.append(row)

        elif (
            row.reference_doctype in RECEIVE_DOCTYPES
            and row.transaction_type in ORIGIN_TRANSACTION_TYPES
            and flt(row.in_weight) > 0
            and not is_excluded_origin(row)
        ):
            row.debit = 0
            row.credit = flt(row.in_weight, 6)
            movements.append(row)

    if filters.get("department"):
        movements = [m for m in movements if m.department == filters.department]

    by_doctype = {}
    for row in movements:
        by_doctype.setdefault(row.reference_doctype, set()).add(row.reference_name)

    header_parties = {}
    row_parties = {}
    for doctype, names in by_doctype.items():
        for name, parties in get_doc_parties(
            doctype, list(names), include_rows=False
        ).items():
            header_parties[(doctype, name)] = parties
        for (parent, source), parties in get_row_parties(doctype, list(names)).items():
            row_parties[(doctype, parent, source)] = parties

    pairs = {(m.reference_doctype, m.reference_name) for m in movements}
    qualities = get_doc_qualities(pairs)
    product_info = get_product_info(m.product for m in movements)

    wanted_type = filters.get("party_type")
    wanted_party = filters.get("party")

    entries = []
    for row in movements:
        # Header parties of the document + the row-level party of the
        # exact Stock Source row (e.g. Spindal row operator, YT supplier).
        parties = merge_parties(
            row_parties.get(
                (row.reference_doctype, row.reference_name, row.stock_source)
            ),
            header_parties.get((row.reference_doctype, row.reference_name)),
        )

        for party in parties:
            if wanted_type and party[0] != wanted_type:
                continue
            if wanted_party and party[1] != wanted_party:
                continue

            quality = qualities.get((row.reference_doctype, row.reference_name))
            entries.append(frappe._dict({
                "party": party,
                "posting_date": getdate(row.posting_date),
                "creation": row.creation,
                "voucher_type": row.reference_doctype,
                "voucher_no": row.reference_name,
                "product": row.product,
                "quality": quality,
                "description": product_label(row.product, quality, product_info),
                "batch_no": row.batch_number,
                "department": row.department,
                "credit": row.credit,
                "debit": row.debit,
            }))

    labels = get_party_labels({e.party for e in entries})
    for entry in entries:
        entry.party_label = labels.get(entry.party) or entry.party[1]

    entries.sort(key=lambda e: (e.party_label, e.posting_date, e.creation))
    return entries


def build_rows(entries, from_date, filters):
    data = []
    groups = {}
    for entry in entries:
        groups.setdefault(entry.party, []).append(entry)

    for party, party_entries in groups.items():
        label = party_entries[0].party_label

        opening = sum(
            e.debit - e.credit
            for e in party_entries
            if from_date and e.posting_date < from_date
        )
        period = [
            e for e in party_entries
            if not from_date or e.posting_date >= from_date
        ]

        data.append({
            "description": label,
            "party_type": party[0],
            "party": party[1],
            "is_group": 1,
            "indent": 0,
        })

        balance = flt(opening, 6)

        if from_date:
            data.append({
                "posting_date": from_date,
                "description": _("Opening Balance"),
                "balance": balance,
                "is_opening": 1,
                "indent": 1,
            })

        total_credit = 0
        total_debit = 0

        for entry in period:
            balance = flt(balance + entry.debit - entry.credit, 6)
            total_credit += entry.credit
            total_debit += entry.debit

            data.append({
                "posting_date": entry.posting_date,
                "voucher_type": entry.voucher_type,
                "voucher_no": entry.voucher_no,
                "description": entry.description,
                "product": entry.product,
                "batch_no": entry.batch_no,
                "department": entry.department,
                "credit": entry.credit or None,
                "debit": entry.debit or None,
                "balance": balance,
                "party_type": party[0],
                "party": party[1],
                "indent": 1,
            })

        data.append({
            "description": _("Total - {0}").format(label),
            "credit": flt(total_credit, 3),
            "debit": flt(total_debit, 3),
            "balance": balance,
            "is_total": 1,
            "indent": 0,
        })

    return data


def get_summary(entries, from_date):
    if not entries:
        return []

    period = [e for e in entries if not from_date or e.posting_date >= from_date]
    credit = sum(e.credit for e in period)
    debit = sum(e.debit for e in period)
    parties = len({e.party for e in entries})

    return [
        {"label": _("Parties"), "value": parties, "datatype": "Int", "indicator": "Blue"},
        {"label": _("Issued (Debit) KG"), "value": flt(debit, 3), "datatype": "Float", "indicator": "Red"},
        {"label": _("Received (Credit) KG"), "value": flt(credit, 3), "datatype": "Float", "indicator": "Green"},
        {"label": _("Net With Party KG"), "value": flt(debit - credit, 3), "datatype": "Float", "indicator": "Orange"},
    ]


def get_columns():
    return [
        {"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
        {"label": _("Voucher Type"), "fieldname": "voucher_type", "fieldtype": "Data", "width": 125},
        {"label": _("V.No."), "fieldname": "voucher_no", "fieldtype": "Dynamic Link", "options": "voucher_type", "width": 160},
        {"label": _("Description"), "fieldname": "description", "fieldtype": "Data", "width": 240},
        {"label": _("Lot / Batch"), "fieldname": "batch_no", "fieldtype": "Data", "width": 110},
        {"label": _("Department"), "fieldname": "department", "fieldtype": "Link", "options": "Department Master", "width": 120},
        {"label": _("Credit (Jama) KG"), "fieldname": "credit", "fieldtype": "Float", "precision": 3, "width": 130},
        {"label": _("Debit (Udhar) KG"), "fieldname": "debit", "fieldtype": "Float", "precision": 3, "width": 130},
        {"label": _("Balance With Party KG"), "fieldname": "balance", "fieldtype": "Float", "precision": 3, "width": 155},
        {"label": _("Product"), "fieldname": "product", "fieldtype": "Link", "options": "Product Master", "width": 110},
        {"label": _("Party Type"), "fieldname": "party_type", "fieldtype": "Data", "width": 110},
        {"label": _("Party"), "fieldname": "party", "fieldtype": "Dynamic Link", "options": "party_type", "width": 140},
    ]
