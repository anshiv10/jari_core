import frappe
from frappe.utils import flt


def product_tag(product):
    return (frappe.db.get_value("Product Master", product, "product_tag") or "").strip().upper() if product else ""


def product_matches_tag(product, tag):
    return product_tag(product) == tag.upper()


def get_process_doc(process_master):
    return frappe.get_doc("Process Master", process_master) if process_master else None


def get_payout_rate_from_process(process_master, tag):
    p = get_process_doc(process_master)
    if not p:
        return 0

    for table in ["input_products", "output_products", "custom_waste_product_items"]:
        for row in p.get(table) or []:
            product = getattr(row, "product", None) or getattr(row, "waste_product", None)
            if product_matches_tag(product, tag):
                return flt(getattr(row, "payout_rate", 0) or getattr(row, "rate", 0) or 0)

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
    return sum(
        flt(row.net_weight)
        for row in doc.get("received_peti_items") or []
        if product_matches_tag(getattr(row, "product", None), tag)
    )


def get_waste_weight_by_tag(doc, tag):
    return sum(
        flt(row.weight)
        for row in doc.get("waste_items") or []
        if product_matches_tag(getattr(row, "waste_product", None), tag)
    )


def calculate_spindal_payout(doc):
    pm = doc.process_master
    batch = doc.active_batch_no

    issued_polyster = get_issue_weight_by_tag(batch, "POLYSTER")
    issued_tar = get_issue_weight_by_tag(batch, "TAR")
    issued_kachi_goti = get_issue_weight_by_tag(batch, "KACHI GOTI")

    received_badla = get_waste_weight_by_tag(doc, "BADLA GOTI") + get_received_weight_by_tag(doc, "BADLA GOTI")
    received_kapan = get_waste_weight_by_tag(doc, "KAPAN") + get_received_weight_by_tag(doc, "KAPAN")
    received_ducho = get_waste_weight_by_tag(doc, "DUCHO") + get_received_weight_by_tag(doc, "DUCHO")
    received_ytc = get_received_weight_by_tag(doc, "KASAB")

    gross_tar = flt(issued_tar) - flt(issued_kachi_goti)

    badla_percent = get_expected_waste_percent(pm, "BADLA GOTI")
    kapan_percent = get_expected_waste_percent(pm, "KAPAN")
    ducho_percent = get_expected_waste_percent(pm, "DUCHO")

    estimated_badla = gross_tar * badla_percent / 100
    badlu = issued_tar - estimated_badla
    estimated_polyster = badlu / flt(doc.bethak_ratio) if flt(doc.bethak_ratio) else 0

    ytc_goods = badlu + estimated_polyster
    estimated_kapan = ytc_goods * kapan_percent / 100
    estimated_ducho = estimated_polyster * ducho_percent / 100
    estimated_ytc = ytc_goods - estimated_kapan - estimated_ducho
    labour_on = estimated_ytc - estimated_polyster

    a1 = estimated_polyster - issued_polyster
    a2 = received_badla - estimated_badla
    a3 = received_kapan - estimated_kapan
    a4 = received_ducho - estimated_ducho
    a5 = gross_tar - issued_tar
    a6 = received_ytc - estimated_ytc

    rates = {
        "POLYSTER": get_payout_rate_from_process(pm, "POLYSTER"),
        "BADLA GOTI": get_payout_rate_from_process(pm, "BADLA GOTI"),
        "KAPAN": get_payout_rate_from_process(pm, "KAPAN"),
        "DUCHO": get_payout_rate_from_process(pm, "DUCHO"),
        "TAR": get_payout_rate_from_process(pm, "TAR"),
        "YTC": get_payout_rate_from_process(pm, "KASAB"),
        "LABOUR": flt(doc.labour_rate)
    }

    amounts = {
        "POLYSTER": a1 * rates["POLYSTER"],
        "BADLA GOTI": a2 * rates["BADLA GOTI"],
        "KAPAN": a3 * rates["KAPAN"],
        "DUCHO": a4 * rates["DUCHO"],
        "TAR": a5 * rates["TAR"],
        "YTC": a6 * rates["YTC"],
        "LABOUR": labour_on * rates["LABOUR"]
    }

    total = sum(flt(v) for v in amounts.values())

    doc.gross_tar = gross_tar
    doc.estimated_badla_goti = estimated_badla
    doc.badlu = badlu
    doc.estimated_polyster = estimated_polyster
    doc.ytc_goods = ytc_goods
    doc.estimated_kapan = estimated_kapan
    doc.estimated_ducho = estimated_ducho
    doc.estimated_ytc = estimated_ytc
    doc.labour_on = labour_on
    doc.actual_ytc_received = received_ytc
    doc.ytc_difference = a6
    doc.ytc_payout_rate = rates["YTC"]
    doc.ytc_amount = amounts["YTC"]
    doc.calculated_payout_amount = total

    doc.payout_summary = f"""
<table class="table table-bordered">
<tr><th>Item</th><th>Difference</th><th>Rate</th><th>Amount</th></tr>
<tr><td>POLYSTER</td><td>{a1:.3f}</td><td>{rates["POLYSTER"]:.2f}</td><td>{amounts["POLYSTER"]:.2f}</td></tr>
<tr><td>BADLA GOTI</td><td>{a2:.3f}</td><td>{rates["BADLA GOTI"]:.2f}</td><td>{amounts["BADLA GOTI"]:.2f}</td></tr>
<tr><td>KAPAN</td><td>{a3:.3f}</td><td>{rates["KAPAN"]:.2f}</td><td>{amounts["KAPAN"]:.2f}</td></tr>
<tr><td>DUCHO</td><td>{a4:.3f}</td><td>{rates["DUCHO"]:.2f}</td><td>{amounts["DUCHO"]:.2f}</td></tr>
<tr><td>TAR</td><td>{a5:.3f}</td><td>{rates["TAR"]:.2f}</td><td>{amounts["TAR"]:.2f}</td></tr>
<tr><td>YTC / KASAB</td><td>{a6:.3f}</td><td>{rates["YTC"]:.2f}</td><td>{amounts["YTC"]:.2f}</td></tr>
<tr><td>LABOUR</td><td>{labour_on:.3f}</td><td>{rates["LABOUR"]:.2f}</td><td>{amounts["LABOUR"]:.2f}</td></tr>
<tr><th colspan="3">Total Majoori</th><th>{total:.2f}</th></tr>
</table>

<b>Calculation Details</b><br>
Gross TAR: {gross_tar:.3f}<br>
Estimated Badla Goti: {estimated_badla:.3f}<br>
Badlu: {badlu:.3f}<br>
Estimated Polyster: {estimated_polyster:.3f}<br>
YTC Goods: {ytc_goods:.3f}<br>
Estimated Kapan: {estimated_kapan:.3f}<br>
Estimated Ducho: {estimated_ducho:.3f}<br>
Estimated YTC: {estimated_ytc:.3f}<br>
Actual YTC Received from KASAB: {received_ytc:.3f}<br>
""".strip()

    return doc


def get_payout_format_rate(doc, tag):
    """
    Return the configured payout rate for a Product Tag from the
    selected Payout Format Master.
    """
    if not doc.get("payout_format"):
        return 0

    payout_format = frappe.get_doc(
        "Payout Format Master",
        doc.payout_format,
    )

    wanted_tag = (tag or "").strip().upper()

    for row in payout_format.rate_items or []:
        row_tag = (
            row.product_tag
            or ""
        ).strip().upper()

        if row_tag == wanted_tag:
            return flt(row.rate)

    return 0


def get_taniya_expected_percent(process_master, tag):
    """
    Return expected waste percentage from Process Master using the
    Product Master product_tag classification.
    """
    if not process_master:
        return 0

    process = frappe.get_doc(
        "Process Master",
        process_master,
    )

    wanted_tag = (tag or "").strip().upper()

    for row in process.custom_waste_product_items or []:
        if product_tag(row.waste_product) == wanted_tag:
            return flt(row.expected_percent)

    return 0


def sum_taniya_receive_by_tag(doc, tag):
    """
    Sum Taniya Receive output and waste rows matching Product Tag.
    """
    wanted_tag = (tag or "").strip().upper()
    total = 0

    for row in doc.get("output_items") or []:
        if product_tag(
            getattr(row, "product", None)
        ) == wanted_tag:
            total += flt(row.weight)

    for row in doc.get("waste_items") or []:
        if product_tag(
            getattr(row, "waste_product", None)
        ) == wanted_tag:
            total += flt(row.weight)

    return total


def calculate_taniya_payout(doc):
    """
    Calculate outsourced Taniya payout.

    Historical business formula restored from the later Taniya
    implementation, adapted to the current payout_utils architecture.

    This function must be called only when Process Master.is_outsourced
    is enabled.
    """
    if not doc.get("batch_no"):
        return doc

    if not doc.get("payout_format"):
        frappe.throw(
            "Payout Format is required for an outsourced Taniya process."
        )

    issues = frappe.get_all(
        "Taniya Issue",
        filters={
            "batch_no": doc.batch_no,
            "docstatus": ["in", [0, 1]],
        },
        pluck="name",
    )

    total_issue = 0

    for issue_name in issues:
        total_issue += flt(
            frappe.db.get_value(
                "Taniya Issue",
                issue_name,
                "total_issue_weight",
            )
        )

    goti_percent = get_taniya_expected_percent(
        doc.process_master,
        "GOTI",
    )

    estimated_goti = (
        total_issue
        * goti_percent
        / 100
    )

    estimated_aur = (
        total_issue
        - estimated_goti
    )

    if not flt(doc.majoori_rate):
        payout_format = frappe.get_doc(
            "Payout Format Master",
            doc.payout_format,
        )

        doc.majoori_rate = flt(
            payout_format.majoori_rate
        )

    majoori_on = (
        estimated_aur
        * flt(doc.majoori_rate)
    )

    tar_received = (
        sum_taniya_receive_by_tag(doc, "TAR")
        + sum_taniya_receive_by_tag(doc, "TAR (Y)")
    )

    goti_received = sum_taniya_receive_by_tag(
        doc,
        "GOTI",
    )

    total_receive = (
        tar_received
        + goti_received
    )

    tar_diff = (
        tar_received
        - estimated_aur
    )

    goti_diff = (
        goti_received
        - estimated_goti
    )

    # Client-approved Taniya payout rule:
    # TAR and GOTI rates come from the linked Process Master
    # product rows, matched using Product Master.product_tag.
    tar_rate = get_payout_rate_from_process(
        doc.process_master,
        "TAR",
    )

    goti_rate = get_payout_rate_from_process(
        doc.process_master,
        "GOTI",
    )

    tar_amount = (
        tar_diff
        * tar_rate
    )

    goti_amount = (
        goti_diff
        * goti_rate
    )

    doc.estimated_goti = estimated_goti
    doc.estimated_aur = estimated_aur
    doc.majoori_on = majoori_on

    doc.calculated_payout_amount = (
        majoori_on
        + tar_amount
        + goti_amount
    )

    doc.payout_summary = (
        f"Total Issue: {total_issue:.3f}\n"
        f"Total Receive: {total_receive:.3f}\n"
        f"Estimated Goti %: {goti_percent:.3f}\n"
        f"Estimated Goti: {estimated_goti:.3f}\n"
        f"Estimated AUR: {estimated_aur:.3f}\n"
        f"Majoori On: {estimated_aur:.3f} x "
        f"{flt(doc.majoori_rate):.2f} = {majoori_on:.2f}\n\n"
        f"TAR Received: {tar_received:.3f}, "
        f"Estimated: {estimated_aur:.3f}, "
        f"Difference: {tar_diff:.3f}, "
        f"Rate: {tar_rate:.2f}, "
        f"Amount: {tar_amount:.2f}\n"
        f"GOTI Received: {goti_received:.3f}, "
        f"Estimated: {estimated_goti:.3f}, "
        f"Difference: {goti_diff:.3f}, "
        f"Rate: {goti_rate:.2f}, "
        f"Amount: {goti_amount:.2f}\n"
        f"Total Payout: {flt(doc.calculated_payout_amount):.2f}"
    )

    return doc
