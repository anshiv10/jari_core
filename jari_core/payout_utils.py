import frappe
from frappe.utils import flt


def get_product_tag(product):
    if not product:
        return ""
    return (frappe.db.get_value("Product Master", product, "product_tag") or "").strip()


def get_rate(doc, tag):
    if not doc.get("payout_format"):
        return 0
    pf = frappe.get_doc("Payout Format Master", doc.payout_format)
    for row in pf.rate_items or []:
        if (row.product_tag or "").strip() == tag:
            return flt(row.rate)
    return 0


def get_expected_percent(process_master, tag):
    if not process_master:
        return 0
    pm = frappe.get_doc("Process Master", process_master)
    for row in pm.custom_waste_product_items or []:
        if get_product_tag(row.waste_product) == tag:
            return flt(row.expected_percent)
    return 0


def sum_issue_by_tag(issue_doc, tag):
    total = 0
    for row in issue_doc.issue_items or []:
        if get_product_tag(row.product) == tag:
            total += flt(row.weight)
    return total


def sum_receive_by_tag(doc, tag):
    total = 0
    for row in doc.get("output_items") or []:
        if get_product_tag(row.product) == tag:
            total += flt(row.weight)
    for row in doc.get("waste_items") or []:
        if get_product_tag(row.waste_product) == tag:
            total += flt(row.weight)
    for row in doc.get("received_peti_items") or []:
        if get_product_tag(row.product) == tag:
            total += flt(row.net_weight)
    return total


def calculate_pavtha_payout(doc):
    if not doc.get("pavtha_issue"):
        return

    issue = frappe.get_doc("Pavtha Issue", doc.pavtha_issue)

    total_receive = flt(doc.total_output_weight) + flt(doc.total_waste_weight)
    total_issue = flt(issue.total_issue_weight)
    difference = total_receive - total_issue

    given_silver = sum_issue_by_tag(issue, "SILVER")
    kachi_goti = sum_issue_by_tag(issue, "KACHI GOTI") + sum_receive_by_tag(doc, "GOTI")
    badla_goti = sum_issue_by_tag(issue, "BADLA GOTI")
    bg_gms = badla_goti - (badla_goti * flt(doc.bg_deduction_percent or 7) / 100)

    mel_factor = (flt(doc.mel) + 1000) / 1000 if flt(doc.mel) else 1
    net = total_receive - flt(doc.return_weight) - kachi_goti - bg_gms
    used_silver = net / mel_factor if mel_factor else 0
    balance_silver = given_silver - used_silver
    remaining_tar = balance_silver * mel_factor

    doc.given_silver = given_silver
    doc.used_silver = used_silver
    doc.balance_silver = balance_silver
    doc.remaining_tar = remaining_tar
    doc.calculated_payout_amount = flt(doc.payout_given or doc.payout_suggestion)

    doc.payout_summary = (
        f"Total Receive: {total_receive}\n"
        f"Total Issue: {total_issue}\n"
        f"Difference Receive - Issue: {difference}\n"
        f"Return: {flt(doc.return_weight)}\n"
        f"Total Kachi Goti: {kachi_goti}\n"
        f"Badla Goti: {badla_goti}\n"
        f"B.G. Gms after deduction: {bg_gms}\n"
        f"Net: {net}\n"
        f"Used Silver: {used_silver}\n"
        f"Given Silver: {given_silver}\n"
        f"Balance Silver: {balance_silver}\n"
        f"Remaining TAR: {remaining_tar}"
    )


def calculate_taniya_payout(doc):
    if not doc.get("batch_no"):
        return

    issues = frappe.get_all(
        "Taniya Issue",
        filters={"batch_no": doc.batch_no, "docstatus": 1},
        pluck="name"
    )

    total_issue = 0
    for name in issues:
        total_issue += flt(frappe.db.get_value("Taniya Issue", name, "total_issue_weight"))

    goti_percent = get_expected_percent(doc.process_master, "GOTI")
    estimated_goti = total_issue * goti_percent / 100
    estimated_aur = total_issue - estimated_goti

    if not flt(doc.majoori_rate) and doc.get("payout_format"):
        pf = frappe.get_doc("Payout Format Master", doc.payout_format)
        doc.majoori_rate = flt(pf.majoori_rate)

    majoori_on = estimated_aur * flt(doc.majoori_rate)

    tar_received = sum_receive_by_tag(doc, "TAR") + sum_receive_by_tag(doc, "TAR (Y)")
    goti_received = sum_receive_by_tag(doc, "GOTI")

    tar_diff = tar_received - estimated_aur
    goti_diff = goti_received - estimated_goti

    tar_amt = abs(tar_diff) * get_rate(doc, "TAR")
    goti_amt = abs(goti_diff) * get_rate(doc, "GOTI")

    doc.estimated_goti = estimated_goti
    doc.estimated_aur = estimated_aur
    doc.majoori_on = majoori_on
    doc.calculated_payout_amount = majoori_on + tar_amt + goti_amt

    doc.payout_summary = (
        f"Total Issue: {total_issue}\n"
        f"Estimated Goti %: {goti_percent}\n"
        f"Estimated Goti: {estimated_goti}\n"
        f"Estimated AUR: {estimated_aur}\n"
        f"Majoori On: {estimated_aur} x {flt(doc.majoori_rate)} = {majoori_on}\n\n"
        f"TAR Received: {tar_received}, Estimated: {estimated_aur}, Difference: {tar_diff}, Amount: {tar_amt}\n"
        f"GOTI Received: {goti_received}, Estimated: {estimated_goti}, Difference: {goti_diff}, Amount: {goti_amt}\n"
        f"Total Payout: {doc.calculated_payout_amount}"
    )


def calculate_spindal_payout(doc):
    if not doc.get("active_batch_no"):
        return

    issues = frappe.get_all(
        "Spindal Issue",
        filters={"active_batch_no": doc.active_batch_no, "docstatus": 1},
        pluck="name"
    )

    polyster = tar = kachi_goti = 0

    for name in issues:
        issue = frappe.get_doc("Spindal Issue", name)
        polyster += sum_issue_by_tag(issue, "POLYSTER")
        tar += sum_issue_by_tag(issue, "TAR")
        kachi_goti += sum_issue_by_tag(issue, "KACHI GOTI")

    gross_tar = tar - kachi_goti
    badla_percent = get_expected_percent(doc.process_master, "BADLA GOTI")
    kapan_percent = get_expected_percent(doc.process_master, "KAPAN")
    ducho_percent = get_expected_percent(doc.process_master, "DUCHO")

    estimated_badla_goti = gross_tar * badla_percent / 100
    badlu = tar - estimated_badla_goti
    estimated_polyster = badlu / flt(doc.bethak_ratio) if flt(doc.bethak_ratio) else 0
    ytc_goods = badlu + estimated_polyster
    estimated_kapan = ytc_goods * kapan_percent / 100
    estimated_ducho = estimated_polyster * ducho_percent / 100
    estimated_ytc = ytc_goods - estimated_kapan - estimated_ducho
    labour_on = estimated_ytc - estimated_polyster

    actual_badla = sum_receive_by_tag(doc, "BADLA GOTI")
    actual_kapan = sum_receive_by_tag(doc, "KAPAN")
    actual_ducho = sum_receive_by_tag(doc, "DUCHO")
    actual_ytc = sum_receive_by_tag(doc, "YTC") or flt(doc.total_received_weight)

    diffs = {
        "POLYSTER": estimated_polyster - polyster,
        "BADLA GOTI": actual_badla - estimated_badla_goti,
        "KAPAN": actual_kapan - estimated_kapan,
        "DUCHO": actual_ducho - estimated_ducho,
        "TAR": gross_tar - tar,
        "YTC": actual_ytc - estimated_ytc,
    }

    if not flt(doc.labour_rate) and doc.get("payout_format"):
        pf = frappe.get_doc("Payout Format Master", doc.payout_format)
        doc.labour_rate = flt(pf.labour_rate)

    total = labour_on * flt(doc.labour_rate)

    lines = []
    for tag, diff in diffs.items():
        rate = get_rate(doc, tag)
        amount = abs(diff) * rate
        total += amount
        lines.append(f"{tag}: Difference {diff}, Rate {rate}, Amount {amount}")

    doc.gross_tar = gross_tar
    doc.estimated_badla_goti = estimated_badla_goti
    doc.badlu = badlu
    doc.estimated_polyster = estimated_polyster
    doc.estimated_kapan = estimated_kapan
    doc.estimated_ducho = estimated_ducho
    doc.estimated_ytc = estimated_ytc
    doc.labour_on = labour_on
    doc.calculated_payout_amount = total

    doc.payout_summary = (
        f"Polyster Given: {polyster}\n"
        f"TAR Given: {tar}\n"
        f"Kachi Goti Given: {kachi_goti}\n"
        f"Gross TAR: {gross_tar}\n"
        f"Estimated Badla Goti: {estimated_badla_goti}\n"
        f"Badlu: {badlu}\n"
        f"Estimated Polyster: {estimated_polyster}\n"
        f"YTC Goods: {ytc_goods}\n"
        f"Estimated Kapan: {estimated_kapan}\n"
        f"Estimated Ducho: {estimated_ducho}\n"
        f"Estimated YTC: {estimated_ytc}\n"
        f"Labour On: {labour_on}, Labour Rate: {flt(doc.labour_rate)}\n\n"
        + "\n".join(lines)
        + f"\nTotal Majoori: {total}"
    )
