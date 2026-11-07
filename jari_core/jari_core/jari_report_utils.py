"""
JARI Core - shared engine for the Jama / Udhar reports.

Used by:
    Party Transaction Tol Wise   (Check Transaction - Tol wise)
    Item Pending In Stock        (Item Stock Report - pending only)
    Item Wise Jama Udhar         (Item Stock Report - all lots)

Design rules (read-only, additive):

* Inventory Ledger is the single source of truth. Nothing is written.
* Only movements of SUBMITTED documents are used. A cancelled document
  and its "Cancellation Reversal" rows share the same reference, so
  excluding cancelled references removes both sides automatically.
* JAMA  = the original inward of one Inventory Stock Source
          (Purchase Inward / Production Output / Waste Generated),
          i.e. one received bundle / row.
* UDHAR = every later movement of that exact Stock Source OUT of the
          department where it was received (Issue, Gilit transfer,
          Jari Sale ...).
* BALANCE = Jama - Udhar = physical stock of that source still lying
          in its receiving department.
* Spindal Receive "Production Output" (KASAB peti rows) is excluded:
  the same Peti KASAB is already posted by Spindal Peti Entry, so
  counting both would double the Jama. Spindal Receive waste rows are
  kept.
"""

import frappe
from frappe.utils import cint, flt, getdate, today


ORIGIN_TRANSACTION_TYPES = (
    "Purchase Inward",
    "Production Output",
    "Waste Generated",
)

ISSUE_DOCTYPES = (
    "Melting Issue",
    "Pavtha Issue",
    "Taniya Issue",
    "Spindal Issue",
    "Gilit Issue",
    "Asarva Issue",
    "YT Issue",
    "Jari Sale",
)

RECEIVE_DOCTYPES = (
    "Purchase Entry",
    "Melting Receive",
    "Pavtha Receive",
    "Taniya Receive",
    "Spindal Peti Entry",
    "Spindal Receive",
    "Gilit Receive",
    "Asarva Receive",
    "YT Receive",
)

# Party (A/c) resolution per document.
#   header : parent-level party fields, in priority order
#   via    : (link field, linked doctype) -> inherit that doc's parties
#   rows   : (child doctype, [party fields]) matched by stock_source
PARTY_CONFIG = {
    "Purchase Entry": {
        "header": [("Jobworker Master", "vendor")],
    },
    "Melting Issue": {
        "header": [("Worker Master", "operator")],
    },
    "Melting Receive": {
        "via": ("melting_issue", "Melting Issue"),
    },
    "Pavtha Issue": {
        "header": [
            ("Jobworker Master", "outsourcer"),
            ("Worker Master", "operator"),
        ],
    },
    "Pavtha Receive": {
        "via": ("pavtha_issue", "Pavtha Issue"),
    },
    "Taniya Issue": {
        "header": [("Worker Master", "operator")],
    },
    "Taniya Receive": {
        "header": [("Worker Master", "operator")],
    },
    "Spindal Issue": {
        "header": [("Worker Master", "operator")],
        "rows": ("Spindal Issue Item", [("Worker Master", "operator_name")]),
    },
    "Spindal Peti Entry": {
        "header": [("Worker Master", "operator")],
    },
    "Spindal Receive": {
        "header": [("Worker Master", "operator")],
    },
    "Gilit Issue": {
        "header": [("Worker Master", "gilit_karigar")],
    },
    "Gilit Receive": {
        "header": [
            ("Worker Master", "operator"),
            ("Worker Master", "flatening_karigar"),
        ],
    },
    "Asarva Issue": {
        "header": [("Jobworker Master", "asarva_outsourcer")],
        "rows": ("Asarva Issue Item", [("Worker Master", "rangrej_operator")]),
    },
    "Asarva Receive": {
        "header": [("Jobworker Master", "asarva_outsourcer")],
    },
    "YT Issue": {
        "rows": ("YT Issue Item", [("Supplier", "supplier")]),
    },
    "YT Receive": {
        "via": ("yt_issue", "YT Issue"),
    },
    "Jari Sale": {
        "header": [("Customer", "customer")],
    },
}

PARTY_TYPES = (
    "Worker Master",
    "Jobworker Master",
    "Customer",
    "Supplier",
)

# Candidate child-row fields used to show Pcs / Gross / Tare for a Jama.
PCS_FIELDS = (
    "quantity",
    "quantity_firka",
    "filled_firki",
    "piece",
)
GROSS_FIELDS = (
    "gross_weight",
    "weight",
)
TARE_FIELDS = (
    "baad_weight",
    "deduction_weight",
)

EPSILON = 0.0005
CHUNK = 500


# ---------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------
def chunks(values, size=CHUNK):
    values = list(values)
    for index in range(0, len(values), size):
        yield values[index:index + size]


def doctype_exists(doctype):
    return bool(frappe.db.exists("DocType", doctype))


def get_submitted_references(pairs):
    """Return the set of (doctype, name) that are currently Submitted."""
    by_doctype = {}
    for doctype, name in pairs:
        if doctype and name:
            by_doctype.setdefault(doctype, set()).add(name)

    submitted = set()

    for doctype, names in by_doctype.items():
        if not doctype_exists(doctype):
            continue

        meta = frappe.get_meta(doctype)

        for part in chunks(names):
            if meta.is_submittable:
                found = frappe.get_all(
                    doctype,
                    filters={"name": ["in", part], "docstatus": 1},
                    pluck="name",
                )
            else:
                found = frappe.get_all(
                    doctype,
                    filters={"name": ["in", part]},
                    pluck="name",
                )

            submitted.update((doctype, name) for name in found)

    return submitted


def get_header_values(doctype, names, fieldnames):
    """{name: {field: value}} for existing fields only."""
    if not names or not doctype_exists(doctype):
        return {}

    meta = frappe.get_meta(doctype)
    fields = ["name"] + [f for f in fieldnames if meta.has_field(f)]

    result = {}
    for part in chunks(names):
        for row in frappe.get_all(
            doctype,
            filters={"name": ["in", part]},
            fields=fields,
        ):
            result[row.name] = row

    return result


# ---------------------------------------------------------------------
# Party resolution
# ---------------------------------------------------------------------
def get_doc_parties(doctype, names, include_rows=True, _depth=0):
    """
    Return {doc name: [(party_type, party), ...]} using header fields,
    inherited (via) parties and - when include_rows - all row-level
    parties of the document.
    """
    config = PARTY_CONFIG.get(doctype) or {}
    names = list(set(n for n in names if n))
    result = {name: [] for name in names}

    if not names or not doctype_exists(doctype):
        return result

    header = config.get("header") or []
    via = config.get("via")

    fieldnames = [field for _ptype, field in header]
    if via:
        fieldnames.append(via[0])

    values = get_header_values(doctype, names, fieldnames)

    for name in names:
        row = values.get(name) or {}
        for ptype, field in header:
            party = row.get(field)
            if party and (ptype, party) not in result[name]:
                result[name].append((ptype, party))

    if via and _depth < 2:
        link_field, linked_doctype = via
        linked_names = [
            (values.get(name) or {}).get(link_field)
            for name in names
        ]
        linked = get_doc_parties(
            linked_doctype,
            [n for n in linked_names if n],
            include_rows=True,
            _depth=_depth + 1,
        )
        for name in names:
            link = (values.get(name) or {}).get(link_field)
            for party in linked.get(link) or []:
                if party not in result[name]:
                    result[name].append(party)

    if not include_rows:
        return result

    row_map = get_row_parties(doctype, names)
    for (parent, _source), parties in row_map.items():
        for party in parties:
            if parent in result and party not in result[parent]:
                result[parent].append(party)

    return result


def get_row_parties(doctype, names):
    """Return {(parent, stock_source): [(party_type, party), ...]}."""
    config = PARTY_CONFIG.get(doctype) or {}
    rows_config = config.get("rows")
    result = {}

    if not rows_config or not names:
        return result

    child_doctype, party_fields = rows_config

    if not doctype_exists(child_doctype):
        return result

    meta = frappe.get_meta(child_doctype)
    fields = ["parent", "idx"]
    if meta.has_field("stock_source"):
        fields.append("stock_source")
    fields += [f for _p, f in party_fields if meta.has_field(f)]

    for part in chunks(names):
        for row in frappe.get_all(
            child_doctype,
            filters={
                "parent": ["in", part],
                "parenttype": doctype,
            },
            fields=fields,
            order_by="idx asc",
        ):
            key = (row.parent, row.get("stock_source"))
            bucket = result.setdefault(key, [])
            for ptype, field in party_fields:
                party = row.get(field)
                if party and (ptype, party) not in bucket:
                    bucket.append((ptype, party))

    return result


def merge_parties(first, second):
    """Ordered union: row-level parties first, then header parties."""
    merged = []
    for party in (first or []) + (second or []):
        if party not in merged:
            merged.append(party)
    return merged


def get_party_labels(parties):
    """{(party_type, party): display label}."""
    labels = {}
    by_type = {}
    for ptype, party in parties:
        by_type.setdefault(ptype, set()).add(party)

    title_fields = {
        "Customer": "customer_name",
        "Supplier": "supplier_name",
    }

    for ptype, names in by_type.items():
        title_field = title_fields.get(ptype)
        titles = {}
        if title_field and doctype_exists(ptype):
            titles = {
                row.name: row.get(title_field)
                for row in get_header_values(
                    ptype, list(names), [title_field]
                ).values()
            }

        for name in names:
            title = titles.get(name)
            labels[(ptype, name)] = (
                f"{name} - {title}"
                if title and title != name
                else name
            )

    return labels


# ---------------------------------------------------------------------
# Product / quality helpers
# ---------------------------------------------------------------------
def get_product_info(products):
    info = {}
    for part in chunks(set(p for p in products if p)):
        for row in frappe.get_all(
            "Product Master",
            filters={"name": ["in", part]},
            fields=["name", "product_name", "metal_type", "unit"],
        ):
            info[row.name] = row
    return info


def get_doc_qualities(pairs):
    """{(doctype, name): quality_code} for docs having quality_code."""
    by_doctype = {}
    for doctype, name in pairs:
        by_doctype.setdefault(doctype, set()).add(name)

    result = {}
    for doctype, names in by_doctype.items():
        values = get_header_values(doctype, list(names), ["quality_code"])
        for name, row in values.items():
            if row.get("quality_code"):
                result[(doctype, name)] = row.quality_code

    return result


def product_label(product, quality, product_info):
    """
    Client style description, e.g. "TAR (KB)".

    Quality is appended only for silver-bearing products, so
    "RESHAM (Pure silk)" keeps its own name.
    """
    info = product_info.get(product) or {}
    name = info.get("product_name") or product or ""

    if quality and (info.get("metal_type") or "") == "Silver":
        return f"{name} ({quality})"

    return name


# ---------------------------------------------------------------------
# Ledger loading
# ---------------------------------------------------------------------
def load_ledger_rows(company, to_date=None, product=None, stock_sources=None):
    conditions = [
        "ledger.company = %(company)s",
    ]
    values = {"company": company}

    if to_date:
        conditions.append("ledger.`date` <= %(to_date)s")
        values["to_date"] = to_date

    if product:
        conditions.append("ledger.product = %(product)s")
        values["product"] = product

    if stock_sources is not None:
        if not stock_sources:
            return []
        conditions.append("ledger.stock_source IN %(stock_sources)s")
        values["stock_sources"] = tuple(stock_sources)

    rows = frappe.db.sql(
        f"""
        SELECT
            ledger.name,
            ledger.`date` AS posting_date,
            ledger.creation,
            ledger.department,
            ledger.product,
            ledger.batch_number,
            ledger.stock_source,
            COALESCE(ledger.in_weight, 0) AS in_weight,
            COALESCE(ledger.out_weight, 0) AS out_weight,
            ledger.transaction_type,
            ledger.reference_doctype,
            ledger.reference_name
        FROM `tabInventory Ledger` ledger
        WHERE {" AND ".join(conditions)}
        ORDER BY ledger.`date` ASC, ledger.creation ASC
        """,
        values,
        as_dict=True,
    )

    submitted = get_submitted_references(
        (row.reference_doctype, row.reference_name)
        for row in rows
    )

    return [
        row for row in rows
        if (row.reference_doctype, row.reference_name) in submitted
    ]


def is_excluded_origin(row):
    """Spindal Receive KASAB output duplicates Spindal Peti Entry."""
    return (
        row.reference_doctype == "Spindal Receive"
        and row.transaction_type == "Production Output"
    )


# ---------------------------------------------------------------------
# Draft reservations (current availability)
# ---------------------------------------------------------------------
def get_draft_reservations(stock_sources):
    """{(stock_source, department): reserved KG in Saved Draft Issues}."""
    from jari_core.jari_core.stock_utils import (
        DRAFT_STOCK_SOURCE_RESERVATION_TABLES,
    )

    result = {}
    if not stock_sources:
        return result

    for config in DRAFT_STOCK_SOURCE_RESERVATION_TABLES:
        parent_doctype = config["parent_doctype"]
        child_doctype = config["child_doctype"]
        qty_field = config["qty_field"]

        if not (doctype_exists(parent_doctype) and doctype_exists(child_doctype)):
            continue

        meta = frappe.get_meta(child_doctype)
        if not (
            meta.has_field("stock_source")
            and meta.has_field("source_department")
            and meta.has_field(qty_field)
        ):
            continue

        for part in chunks(stock_sources):
            for row in frappe.db.sql(
                f"""
                SELECT
                    child_row.stock_source,
                    child_row.source_department,
                    SUM(COALESCE(child_row.`{qty_field}`, 0)) AS reserved
                FROM `tab{child_doctype}` child_row
                INNER JOIN `tab{parent_doctype}` parent_doc
                    ON parent_doc.name = child_row.parent
                WHERE parent_doc.docstatus = 0
                  AND child_row.stock_source IN %(sources)s
                GROUP BY
                    child_row.stock_source,
                    child_row.source_department
                """,
                {"sources": tuple(part)},
                as_dict=True,
            ):
                key = (row.stock_source, row.source_department)
                result[key] = flt(result.get(key)) + flt(row.reserved)

    return result


# ---------------------------------------------------------------------
# Jama row physical details (Pcs / Gross / Tare)
# ---------------------------------------------------------------------
def get_source_row_details(sources):
    """
    {stock_source: {"pcs", "gross", "tare", "issue_receive_type"}}
    read from the exact child row that created the source.
    """
    details = {}
    by_doctype = {}

    for source in sources.values():
        if source.is_legacy or not source.source_doctype or not source.source_row:
            continue
        by_doctype.setdefault(source.source_doctype, {})[
            source.source_row
        ] = source.name

    for doctype, row_map in by_doctype.items():
        if not doctype_exists(doctype):
            continue

        if doctype == "Spindal Peti Entry":
            details.update(get_peti_details(row_map))
            continue

        meta = frappe.get_meta(doctype)
        for table_field in meta.get_table_fields():
            child_doctype = table_field.options
            child_meta = frappe.get_meta(child_doctype)

            pcs_field = next((f for f in PCS_FIELDS if child_meta.has_field(f)), None)
            gross_field = next((f for f in GROSS_FIELDS if child_meta.has_field(f)), None)
            tare_field = next((f for f in TARE_FIELDS if child_meta.has_field(f)), None)

            fields = ["name"]
            for field in (pcs_field, gross_field, tare_field):
                if field and field not in fields:
                    fields.append(field)
            if child_meta.has_field("issue_receive_type"):
                fields.append("issue_receive_type")

            for part in chunks(row_map.keys()):
                for row in frappe.get_all(
                    child_doctype,
                    filters={"name": ["in", part], "parent": ["is", "set"]},
                    fields=fields,
                ):
                    source_name = row_map.get(row.name)
                    if not source_name or source_name in details:
                        continue

                    details[source_name] = {
                        "pcs": cint(row.get(pcs_field)) if pcs_field else 0,
                        "gross": flt(row.get(gross_field)) if gross_field else 0,
                        "tare": flt(row.get(tare_field)) if tare_field else 0,
                        "issue_receive_type": row.get("issue_receive_type"),
                    }

    return details


def get_peti_details(row_map):
    """
    Peti physical values are reduced by Gilit Receive after
    consumption, so prefer the original snapshot stored in
    Gilit Output Item; fall back to the Peti's own values.
    """
    details = {}
    peti_names = list(row_map.keys())

    snapshots = {}
    if doctype_exists("Gilit Output Item"):
        for part in chunks(peti_names):
            for row in frappe.db.sql(
                """
                SELECT
                    item.spindal_peti_entry,
                    item.original_bobbin_count,
                    item.original_gross_weight,
                    item.original_baad_weight
                FROM `tabGilit Output Item` item
                INNER JOIN `tabGilit Receive` parent_doc
                    ON parent_doc.name = item.parent
                WHERE parent_doc.docstatus = 1
                  AND item.spindal_peti_entry IN %(petis)s
                ORDER BY parent_doc.creation ASC
                """,
                {"petis": tuple(part)},
                as_dict=True,
            ):
                snapshots.setdefault(row.spindal_peti_entry, row)

    values = get_header_values(
        "Spindal Peti Entry",
        peti_names,
        ["nang", "bobbin_count", "gross_weight", "baad_weight"],
    )

    for peti, source_name in row_map.items():
        snap = snapshots.get(peti)
        row = values.get(peti) or {}

        if snap and flt(snap.original_gross_weight):
            details[source_name] = {
                "pcs": cint(snap.original_bobbin_count),
                "gross": flt(snap.original_gross_weight),
                "tare": flt(snap.original_baad_weight),
                "issue_receive_type": None,
            }
        else:
            details[source_name] = {
                "pcs": cint(row.get("bobbin_count") or row.get("nang")),
                "gross": flt(row.get("gross_weight")),
                "tare": flt(row.get("baad_weight")),
                "issue_receive_type": None,
            }

    return details


# ---------------------------------------------------------------------
# JAMA / UDHAR builder
# ---------------------------------------------------------------------
def build_jama_udhar(filters):
    """
    Return a list of Jama dicts, each containing its Udhar lines and
    Balance, already filtered and sorted.
    """
    company = filters.get("company")
    as_on_date = getdate(filters.get("as_on_date") or today())
    product_filter = filters.get("product")

    ledger = load_ledger_rows(
        company,
        to_date=as_on_date,
        product=product_filter,
    )

    source_names = {row.stock_source for row in ledger if row.stock_source}

    # Legacy opening sources have no origin ledger row.
    legacy_filters = {"company": company, "is_legacy": 1}
    if product_filter:
        legacy_filters["product"] = product_filter
    for name in frappe.get_all(
        "Inventory Stock Source",
        filters=legacy_filters,
        pluck="name",
    ):
        source_names.add(name)

    sources = {}
    for part in chunks(source_names):
        for row in frappe.get_all(
            "Inventory Stock Source",
            filters={"name": ["in", part]},
            fields=[
                "name",
                "source_type",
                "product",
                "source_doctype",
                "source_name",
                "source_row",
                "source_date",
                "batch_number",
                "is_legacy",
                "opening_department",
                "opening_weight",
                "creation",
            ],
        ):
            sources[row.name] = row

    # ---- Jama (origin) --------------------------------------------
    jama_map = {}

    for row in ledger:
        source = sources.get(row.stock_source)
        if (
            not source
            or source.is_legacy
            or row.transaction_type not in ORIGIN_TRANSACTION_TYPES
            or flt(row.in_weight) <= 0
            or row.reference_doctype != source.source_doctype
            or row.reference_name != source.source_name
            or is_excluded_origin(row)
            or row.stock_source in jama_map
        ):
            continue

        jama_map[row.stock_source] = frappe._dict({
            "stock_source": row.stock_source,
            "product": row.product,
            "department": row.department,
            "posting_date": row.posting_date,
            "creation": row.creation,
            "voucher_type": row.reference_doctype,
            "voucher_no": row.reference_name,
            "batch_no": row.batch_number or source.batch_number,
            "net": flt(row.in_weight, 6),
            "origin_ledger": row.name,
            "is_legacy": 0,
        })

    for source in sources.values():
        if not source.is_legacy or source.name in jama_map:
            continue
        if source.source_date and getdate(source.source_date) > as_on_date:
            continue
        jama_map[source.name] = frappe._dict({
            "stock_source": source.name,
            "product": source.product,
            "department": source.opening_department,
            "posting_date": source.source_date,
            "creation": source.creation,
            "voucher_type": "Inventory Stock Source",
            "voucher_no": source.name,
            "batch_no": source.batch_number or "LEGACY",
            "net": flt(source.opening_weight, 6),
            "origin_ledger": None,
            "is_legacy": 1,
        })

    if not jama_map:
        return []

    # ---- Udhar (movements of the source out of its Jama dept) -----
    udhar_map = {}

    for row in ledger:
        jama = jama_map.get(row.stock_source)
        if not jama:
            continue
        if row.name == jama.origin_ledger:
            continue
        if row.department != jama.department:
            continue

        movement = flt(row.out_weight) - flt(row.in_weight)
        if abs(movement) <= 0.0000001:
            continue

        key = (row.stock_source, row.reference_doctype, row.reference_name)
        line = udhar_map.get(key)
        if not line:
            line = frappe._dict({
                "stock_source": row.stock_source,
                "posting_date": row.posting_date,
                "creation": row.creation,
                "voucher_type": row.reference_doctype,
                "voucher_no": row.reference_name,
                "batch_no": row.batch_number,
                "net": 0,
                "transaction_type": row.transaction_type,
            })
            udhar_map[key] = line

        line.net = flt(line.net + movement, 6)

    # ---- Parties, qualities, physical details ---------------------
    doc_pairs = {(j.voucher_type, j.voucher_no) for j in jama_map.values() if not j.is_legacy}
    doc_pairs |= {(u.voucher_type, u.voucher_no) for u in udhar_map.values()}

    by_doctype = {}
    for doctype, name in doc_pairs:
        by_doctype.setdefault(doctype, set()).add(name)

    doc_parties = {}
    header_parties = {}
    row_parties = {}
    for doctype, names in by_doctype.items():
        for name, parties in get_doc_parties(doctype, list(names)).items():
            doc_parties[(doctype, name)] = parties
        for name, parties in get_doc_parties(
            doctype, list(names), include_rows=False
        ).items():
            header_parties[(doctype, name)] = parties
        for (parent, source), parties in get_row_parties(doctype, list(names)).items():
            row_parties[(doctype, parent, source)] = parties

    all_parties = {p for plist in doc_parties.values() for p in plist}
    all_parties |= {p for plist in row_parties.values() for p in plist}
    party_labels = get_party_labels(all_parties)

    qualities = get_doc_qualities(doc_pairs)
    product_info = get_product_info(j.product for j in jama_map.values())
    row_details = get_source_row_details(
        {name: sources[name] for name in jama_map if name in sources}
    )

    reservations = {}
    if as_on_date >= getdate(today()):
        reservations = get_draft_reservations(list(jama_map.keys()))

    # ---- Filters on the Jama side ---------------------------------
    department_filter = filters.get("department")
    quality_filter = filters.get("quality")
    party_type_filter = filters.get("party_type")
    party_filter = filters.get("party")
    from_date = getdate(filters.get("from_date")) if filters.get("from_date") else None
    to_date = getdate(filters.get("to_date")) if filters.get("to_date") else None
    show_fully_issued = cint(filters.get("show_fully_issued"))

    lines_by_source = {}
    for line in udhar_map.values():
        lines_by_source.setdefault(line.stock_source, []).append(line)

    result = []

    for jama in jama_map.values():
        if department_filter and jama.department != department_filter:
            continue

        jama_date = getdate(jama.posting_date) if jama.posting_date else None
        if from_date and jama_date and jama_date < from_date:
            continue
        if to_date and jama_date and jama_date > to_date:
            continue

        quality = qualities.get((jama.voucher_type, jama.voucher_no))
        if quality_filter and quality != quality_filter:
            continue

        parties = doc_parties.get((jama.voucher_type, jama.voucher_no)) or []
        if party_filter:
            wanted = (party_type_filter, party_filter) if party_type_filter else None
            if wanted:
                if wanted not in parties:
                    continue
            elif party_filter not in [p for _t, p in parties]:
                continue

        detail = row_details.get(jama.stock_source) or {}
        net = flt(jama.net, 6)
        gross = flt(detail.get("gross")) or net
        tare = flt(detail.get("tare"))
        if not tare and gross > net:
            tare = flt(gross - net, 6)
        pcs = cint(detail.get("pcs"))

        jama.update({
            "quality": quality,
            "party": party_labels.get(parties[0]) if parties else "",
            "pcs": pcs,
            "gross": gross,
            "tare": tare,
            "is_return": (detail.get("issue_receive_type") == "Return"),
            "description": product_label(jama.product, quality, product_info),
        })

        lines = sorted(
            lines_by_source.get(jama.stock_source) or [],
            key=lambda line: (getdate(line.posting_date), line.creation),
        )

        issued_net = 0
        issued_pcs = 0
        udhar_lines = []

        for line in lines:
            ratio = (line.net / net) if net else 0
            if abs(ratio - 1) <= 0.000001:
                line_pcs, line_gross, line_tare = pcs, gross, tare
            else:
                line_pcs = int(round(pcs * ratio)) if pcs else 0
                line_gross = flt(gross * ratio, 3)
                line_tare = flt(tare * ratio, 3)

            line_parties = merge_parties(
                row_parties.get(
                    (line.voucher_type, line.voucher_no, line.stock_source)
                ),
                header_parties.get((line.voucher_type, line.voucher_no)),
            )

            line.update({
                "pcs": line_pcs,
                "gross": line_gross,
                "tare": line_tare,
                "party": party_labels.get(line_parties[0]) if line_parties else "",
            })

            issued_net += line.net
            issued_pcs += line_pcs
            udhar_lines.append(line)

        balance_kgs = flt(net - issued_net, 6)
        balance_pcs = max(0, pcs - issued_pcs) if pcs else 0
        if abs(balance_kgs) <= EPSILON:
            balance_kgs = 0
            balance_pcs = 0

        if not show_fully_issued and balance_kgs <= EPSILON:
            continue

        reserved = flt(
            reservations.get((jama.stock_source, jama.department)),
            6,
        )

        jama.update({
            "udhar": udhar_lines,
            "balance_kgs": balance_kgs,
            "balance_pcs": balance_pcs,
            "reserved_kgs": reserved,
            "free_kgs": max(0, flt(balance_kgs - reserved, 6)),
            "age_days": (
                (as_on_date - jama_date).days
                if jama_date and balance_kgs > EPSILON
                else None
            ),
        })
        result.append(jama)

    result.sort(
        key=lambda j: (
            j.description or "",
            getdate(j.posting_date) if j.posting_date else getdate("1900-01-01"),
            j.creation,
        )
    )

    return result


# ---------------------------------------------------------------------
# Report rows / columns for the Jama-Udhar reports
# ---------------------------------------------------------------------
def execute_jama_udhar(filters, pending_only):
    from frappe import _

    filters = frappe._dict(filters or {})

    if not filters.get("company"):
        frappe.throw(_("Please select Company."))

    if filters.get("party") and not filters.get("party_type"):
        frappe.throw(_("Please select Party Type."))

    filters.show_fully_issued = 0 if pending_only else cint(
        filters.get("show_fully_issued", 1)
    )

    jamas = build_jama_udhar(filters)
    data = build_jama_udhar_rows(jamas)

    # KPI cards are drawn client-side by jari_report_kit.js, so the
    # server report_summary strip is not returned (avoids duplicates).
    return get_jama_udhar_columns(pending_only), data


def build_jama_udhar_rows(jamas):
    """
    Client layout:

        [ITEM HEADER]   e.g. TAR (KB)
        Jama line  + first Udhar line + Balance
                     further Udhar lines (Jama columns blank)
        ...
        [ITEM TOTAL]    [Pcs] [Kgs]
    """
    data = []
    groups = []
    current = None

    for jama in jamas:
        if not current or current["label"] != jama.description:
            current = {"label": jama.description, "jamas": []}
            groups.append(current)
        current["jamas"].append(jama)

    grand = {"jama_pcs": 0, "jama_net": 0, "udhar_pcs": 0,
             "udhar_net": 0, "balance_pcs": 0, "balance_kgs": 0,
             "reserved_kgs": 0, "free_kgs": 0}

    for group in groups:
        data.append({
            "item": group["label"],
            "is_group": 1,
            "indent": 0,
        })

        totals = {key: 0 for key in grand}

        for jama in group["jamas"]:
            udhar_lines = jama.udhar or [None]

            for index, line in enumerate(udhar_lines):
                row = {
                    "indent": 1,
                    "stock_source": jama.stock_source,
                    "item_label": group["label"],
                }

                if index == 0:
                    row.update({
                        "jama_date": jama.posting_date,
                        "jama_voucher_type": jama.voucher_type,
                        "jama_voucher": jama.voucher_no,
                        "jama_party": jama.party,
                        "jama_pcs": jama.pcs or None,
                        "jama_gross": jama.gross,
                        "jama_tare": jama.tare,
                        "jama_net": jama.net,
                        "lot_no": ("RET" if jama.is_return else jama.batch_no),
                        "is_return": 1 if jama.is_return else 0,
                        "balance_pcs": jama.balance_pcs,
                        "balance_kgs": jama.balance_kgs,
                        "reserved_kgs": jama.reserved_kgs or None,
                        "free_kgs": jama.free_kgs if jama.balance_kgs else None,
                        "age_days": jama.age_days,
                        "department": jama.department,
                        "quality": jama.quality,
                    })
                    totals["jama_pcs"] += cint(jama.pcs)
                    totals["jama_net"] += flt(jama.net)
                    totals["balance_pcs"] += cint(jama.balance_pcs)
                    totals["balance_kgs"] += flt(jama.balance_kgs)
                    totals["reserved_kgs"] += flt(jama.reserved_kgs)
                    totals["free_kgs"] += flt(jama.free_kgs) if jama.balance_kgs else 0

                if line:
                    row.update({
                        "udhar_date": line.posting_date,
                        "udhar_voucher_type": line.voucher_type,
                        "udhar_voucher": line.voucher_no,
                        "udhar_party": line.party,
                        "udhar_pcs": line.pcs or None,
                        "udhar_gross": line.gross,
                        "udhar_tare": line.tare,
                        "udhar_net": line.net,
                        "udhar_lot": line.batch_no,
                    })
                    totals["udhar_pcs"] += cint(line.pcs)
                    totals["udhar_net"] += flt(line.net)

                data.append(row)

        data.append({
            "item": f"Total - {group['label']}",
            "is_total": 1,
            "indent": 0,
            "jama_pcs": totals["jama_pcs"],
            "jama_net": flt(totals["jama_net"], 3),
            "udhar_pcs": totals["udhar_pcs"],
            "udhar_net": flt(totals["udhar_net"], 3),
            "balance_pcs": totals["balance_pcs"],
            "balance_kgs": flt(totals["balance_kgs"], 3),
            "reserved_kgs": flt(totals["reserved_kgs"], 3),
            "free_kgs": flt(totals["free_kgs"], 3),
        })

        for key in grand:
            grand[key] += totals[key]

    if len(groups) > 1:
        data.append({
            "item": "GRAND TOTAL",
            "is_total": 1,
            "is_grand_total": 1,
            "indent": 0,
            **{key: (flt(value, 3) if isinstance(value, float) else value)
               for key, value in grand.items()},
        })

    return data


def get_jama_udhar_summary(jamas, pending_only):
    from frappe import _

    if not jamas:
        return []

    balance = sum(flt(j.balance_kgs) for j in jamas)
    pcs = sum(cint(j.balance_pcs) for j in jamas)
    jama_net = sum(flt(j.net) for j in jamas)
    udhar_net = sum(flt(u.net) for j in jamas for u in (j.udhar or []))
    pending_lots = len([j for j in jamas if flt(j.balance_kgs) > EPSILON])

    summary = [
        {"label": _("Jama KG"), "value": flt(jama_net, 3), "datatype": "Float", "indicator": "Green"},
        {"label": _("Udhar KG"), "value": flt(udhar_net, 3), "datatype": "Float", "indicator": "Red"},
        {"label": _("Balance Pcs"), "value": pcs, "datatype": "Int", "indicator": "Blue"},
        {"label": _("Balance KG"), "value": flt(balance, 3), "datatype": "Float", "indicator": "Blue"},
        {"label": _("Pending Lots"), "value": pending_lots, "datatype": "Int", "indicator": "Orange"},
    ]

    if pending_only:
        reserved = sum(flt(j.reserved_kgs) for j in jamas)
        summary.append(
            {"label": _("Reserved in Drafts KG"), "value": flt(reserved, 3), "datatype": "Float", "indicator": "Grey"}
        )

    return summary


def get_jama_udhar_columns(pending_only):
    from frappe import _

    columns = [
        {"label": _("Item"), "fieldname": "item", "fieldtype": "Data", "width": 170},
        # ---- JAMA ----
        {"label": _("Jama Date"), "fieldname": "jama_date", "fieldtype": "Date", "width": 95},
        {"label": _("Jama Type"), "fieldname": "jama_voucher_type", "fieldtype": "Data", "width": 110},
        {"label": _("Jama V.No."), "fieldname": "jama_voucher", "fieldtype": "Dynamic Link", "options": "jama_voucher_type", "width": 145},
        {"label": _("Jama A/c"), "fieldname": "jama_party", "fieldtype": "Data", "width": 110},
        {"label": _("Pcs"), "fieldname": "jama_pcs", "fieldtype": "Int", "width": 55},
        {"label": _("Gross"), "fieldname": "jama_gross", "fieldtype": "Float", "precision": 3, "width": 85},
        {"label": _("Tare"), "fieldname": "jama_tare", "fieldtype": "Float", "precision": 3, "width": 80},
        {"label": _("Net"), "fieldname": "jama_net", "fieldtype": "Float", "precision": 3, "width": 85},
        {"label": _("Lot #"), "fieldname": "lot_no", "fieldtype": "Data", "width": 95},
        # ---- UDHAR ----
        {"label": _("Udhar Date"), "fieldname": "udhar_date", "fieldtype": "Date", "width": 95},
        {"label": _("Udhar Type"), "fieldname": "udhar_voucher_type", "fieldtype": "Data", "width": 110},
        {"label": _("Udhar V.No."), "fieldname": "udhar_voucher", "fieldtype": "Dynamic Link", "options": "udhar_voucher_type", "width": 145},
        {"label": _("Udhar A/c"), "fieldname": "udhar_party", "fieldtype": "Data", "width": 110},
        {"label": _("Pcs"), "fieldname": "udhar_pcs", "fieldtype": "Int", "width": 55},
        {"label": _("Gross"), "fieldname": "udhar_gross", "fieldtype": "Float", "precision": 3, "width": 85},
        {"label": _("Tare"), "fieldname": "udhar_tare", "fieldtype": "Float", "precision": 3, "width": 80},
        {"label": _("Net"), "fieldname": "udhar_net", "fieldtype": "Float", "precision": 3, "width": 85},
        {"label": _("Udhar Lot"), "fieldname": "udhar_lot", "fieldtype": "Data", "width": 95},
        # ---- BALANCE ----
        {"label": _("Bal. Pcs"), "fieldname": "balance_pcs", "fieldtype": "Int", "width": 70},
        {"label": _("Bal. Kgs"), "fieldname": "balance_kgs", "fieldtype": "Float", "precision": 3, "width": 90},
    ]

    if pending_only:
        columns += [
            {"label": _("Reserved (Draft) KG"), "fieldname": "reserved_kgs", "fieldtype": "Float", "precision": 3, "width": 120},
            {"label": _("Free KG"), "fieldname": "free_kgs", "fieldtype": "Float", "precision": 3, "width": 90},
            {"label": _("Age (Days)"), "fieldname": "age_days", "fieldtype": "Int", "width": 85},
        ]

    columns += [
        {"label": _("Department"), "fieldname": "department", "fieldtype": "Link", "options": "Department Master", "width": 115},
        {"label": _("Quality"), "fieldname": "quality", "fieldtype": "Link", "options": "Quality Master", "width": 90},
    ]

    return columns
