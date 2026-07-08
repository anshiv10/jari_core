import frappe
from frappe.utils import flt


def product_tag(product):
    if not product:
        return ""
    return (frappe.db.get_value("Product Master", product, "product_tag") or "").strip().upper()


def product_matches_tag(product, tag):
    return product_tag(product) == tag.upper()


def get_process_doc(process_master):
    if not process_master:
        return None
    return frappe.get_doc("Process Master", process_master)


def get_payout_rate_from_process(process_master, tag):
    """
    Permanent rule:
    payout rate is fetched from Process Master row where selected Product Master has matching Product Tag.
    For YTC row in Spindal payout, tag must be KASAB, as per client.
    """
    p = get_process_doc(process_master)
    if not p:
        return 0

    tables = [
        "input_products",
        "output_products",
        "custom_waste_product_items",
    ]

    for table in tables:
        for row in p.get(table) or []:
            product = getattr(row, "product", None) or getattr(row, "waste_product", None)
            if product_matches_tag(product, tag):
                return flt(
                    getattr(row, "payout_rate", 0)
                    or getattr(row, "rate", 0)
                    or 0
                )

    return 0


def get_expected_waste_percent(process_master, tag):
    p = get_process_doc(process_master)
    if not p:
        return 0

    for row in p.get("custom_waste_product_items") or []:
        if product_matches_tag(getattr(row, "waste_product", None), tag):
            return flt(getattr(row, "expected_percent", 0))

    return 0


def get_issue_weight_by_tag(active_batch_no, tag):
    if not active_batch_no:
        return 0

    rows = frappe.db.sql("""
        SELECT sii.product, sii.weight
        FROM `tabSpindal Issue Item` sii
        INNER JOIN `tabSpindal Issue` si ON si.name = sii.parent
        WHERE si.docstatus = 1
          AND si.active_batch_no = %s
    """, active_batch_no, as_dict=True)

    return sum(flt(r.weight) for r in rows if product_matches_tag(r.product, tag))


def get_received_weight_by_tag(doc, tag):
    total = 0

    for row in doc.get("received_peti_items") or []:
        product = getattr(row, "product", None)
        if product_matches_tag(product, tag):
            total += flt(getattr(row, "net_weight", 0))

    return total


def get_waste_weight_by_tag(doc, tag):
    total = 0

    for row in doc.get("waste_items") or []:
        product = getattr(row, "waste_product", None)
        if product_matches_tag(product, tag):
            total += flt(getattr(row, "weight", 0))

    return total


def amount(diff, rate):
    return flt(diff) * flt(rate)


def calculate_spindal_payout(doc):
    """
    Spindal payout as per client PDF.
    Important correction:
    YTC received = SUM received peti/output rows where Product Tag = KASAB.
    YTC payout rate = payout rate of KASAB labelled product from Process Master.
    """

    process_master = doc.process_master
    batch = doc.active_batch_no

    issued_polyster = get_issue_weight_by_tag(batch, "POLYSTER")
    issued_tar = get_issue_weight_by_tag(batch, "TAR")
    issued_kachi_goti = get_issue_weight_by_tag(batch, "KACHI GOTI")

    received_badla_goti = get_waste_weight_by_tag(doc, "BADLA GOTI") + get_received_weight_by_tag(doc, "BADLA GOTI")
    received_kapan = get_waste_weight_by_tag(doc, "KAPAN") + get_received_weight_by_tag(doc, "KAPAN")
    received_ducho = get_waste_weight_by_tag(doc, "DUCHO") + get_received_weight_by_tag(doc, "DUCHO")

    # Client correction:
    # YTC received means KASAB labelled received/output item total.
    received_ytc = get_received_weight_by_tag(doc, "KASAB")

    gross_tar = flt(issued_tar) - flt(issued_kachi_goti)

    badla_percent = get_expected_waste_percent(process_master, "BADLA GOTI")
    kapan_percent = get_expected_waste_percent(process_master, "KAPAN")
    ducho_percent = get_expected_waste_percent(process_master, "DUCHO")

    estimated_badla_goti = flt(gross_tar) * flt(badla_percent) / 100
    badlu = flt(issued_tar) - flt(estimated_badla_goti)

    bethak_ratio = flt(doc.bethak_ratio)
    estimated_polyster = flt(badlu) / bethak_ratio if bethak_ratio else 0

    ytc_goods = flt(badlu) + flt(estimated_polyster)
    estimated_kapan = flt(ytc_goods) * flt(kapan_percent) / 100
    estimated_ducho = flt(estimated_polyster) * flt(ducho_percent) / 100
    estimated_ytc = flt(ytc_goods) - flt(estimated_kapan) - flt(estimated_ducho)

    labour_on = flt(estimated_ytc) - flt(estimated_polyster)

    a1 = flt(estimated_polyster) - flt(issued_polyster)
    a2 = flt(received_badla_goti) - flt(estimated_badla_goti)
    a3 = flt(received_kapan) - flt(estimated_kapan)
    a4 = flt(received_ducho) - flt(estimated_ducho)
    a5 = flt(gross_tar) - flt(issued_tar)

    # Client correction:
    # A6 = KASAB labelled received item total - Estimated YTC
    a6 = flt(received_ytc) - flt(estimated_ytc)

    rate_polyster = get_payout_rate_from_process(process_master, "POLYSTER")
    rate_badla = get_payout_rate_from_process(process_master, "BADLA GOTI")
    rate_kapan = get_payout_rate_from_process(process_master, "KAPAN")
    rate_ducho = get_payout_rate_from_process(process_master, "DUCHO")
    rate_tar = get_payout_rate_from_process(process_master, "TAR")

    # Client correction:
    # YTC row payout rate must come from KASAB labelled product in Process Master.
    rate_ytc = get_payout_rate_from_process(process_master, "KASAB")

    labour_rate = flt(doc.labour_rate)

    amt_polyster = amount(a1, rate_polyster)
    amt_badla = amount(a2, rate_badla)
    amt_kapan = amount(a3, rate_kapan)
    amt_ducho = amount(a4, rate_ducho)
    amt_tar = amount(a5, rate_tar)
    amt_ytc = amount(a6, rate_ytc)
    amt_labour = amount(labour_on, labour_rate)

    total = (
        flt(amt_polyster)
        + flt(amt_badla)
        + flt(amt_kapan)
        + flt(amt_ducho)
        + flt(amt_tar)
        + flt(amt_ytc)
        + flt(amt_labour)
    )

    doc.gross_tar = gross_tar
    doc.estimated_badla_goti = estimated_badla_goti
    doc.badlu = badlu
    doc.estimated_polyster = estimated_polyster
    doc.estimated_kapan = estimated_kapan
    doc.estimated_ducho = estimated_ducho
    doc.estimated_ytc = estimated_ytc
    doc.labour_on = labour_on

    if hasattr(doc, "actual_ytc_received"):
        doc.actual_ytc_received = received_ytc
    if hasattr(doc, "ytc_difference"):
        doc.ytc_difference = a6
    if hasattr(doc, "ytc_payout_rate"):
        doc.ytc_payout_rate = rate_ytc
    if hasattr(doc, "ytc_amount"):
        doc.ytc_amount = amt_ytc

    doc.calculated_payout_amount = total

    doc.payout_summary = f"""
Spindal Payout Calculation

Given / Used:
POLYSTER Given: {issued_polyster}
POLYSTER Used / Estimated: {estimated_polyster}
A1 Difference: {a1}
Rate: {rate_polyster}
Amount: {amt_polyster}

TAR Given: {issued_tar}
Gross TAR Used: {gross_tar}
A5 Difference: {a5}
Rate: {rate_tar}
Amount: {amt_tar}

Remaining Goods:
BADLA GOTI Received: {received_badla_goti}
BADLA GOTI Estimated: {estimated_badla_goti}
A2 Difference: {a2}
Rate: {rate_badla}
Amount: {amt_badla}

KAPAN Received: {received_kapan}
KAPAN Estimated: {estimated_kapan}
A3 Difference: {a3}
Rate: {rate_kapan}
Amount: {amt_kapan}

DUCHO Received: {received_ducho}
DUCHO Estimated: {estimated_ducho}
A4 Difference: {a4}
Rate: {rate_ducho}
Amount: {amt_ducho}

YTC / KASAB:
YTC Received from KASAB labelled output: {received_ytc}
Estimated YTC: {estimated_ytc}
A6 Difference: {a6}
YTC Payout Rate from KASAB labelled Process Master product: {rate_ytc}
YTC Amount: {amt_ytc}

Labour:
Labour On: {labour_on}
Labour Rate: {labour_rate}
Labour Amount: {amt_labour}

Total Majoori: {total}
""".strip()

    return doc
