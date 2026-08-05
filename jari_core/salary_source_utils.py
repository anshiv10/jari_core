import frappe
from frappe.utils import flt


FIRKI_RILING_FORMAT = (
    "UMIYA JARI - Firki Riling Worker"
)


def get_salary_source_data(
    worker,
    salary_format,
    period_start,
    period_end,
):
    """
    Return automatic transaction quantities for a salary format.

    Unknown or not-yet-mapped salary formats return None so their
    existing manual calculation behavior remains unchanged.
    """
    if salary_format == FIRKI_RILING_FORMAT:
        return get_firki_riling_source(
            worker,
            period_start,
            period_end,
        )

    return None


def get_firki_riling_source(
    worker,
    period_start,
    period_end,
):
    """
    Firki Riling Worker salary source:

    Submitted Gilit Receive
    Worker   = flatening_karigar
    Quality  = quality_code
    Quantity = filled_firki
    """
    rows = frappe.db.sql(
        """
        SELECT
            quality_code,
            SUM(COALESCE(filled_firki, 0))
                AS source_quantity,
            GROUP_CONCAT(
                name
                ORDER BY receive_date, name
                SEPARATOR ', '
            ) AS source_documents
        FROM `tabGilit Receive`
        WHERE docstatus = 1
          AND receive_date
              BETWEEN %(period_start)s
                  AND %(period_end)s
          AND flatening_karigar = %(worker)s
          AND COALESCE(filled_firki, 0) > 0
        GROUP BY quality_code
        ORDER BY quality_code
        """,
        {
            "worker": worker,
            "period_start": period_start,
            "period_end": period_end,
        },
        as_dict=True,
    )

    quality_rows = []
    references = []
    total_quantity = 0

    for row in rows:
        quantity = flt(
            row.source_quantity,
            4,
        )

        if quantity <= 0:
            continue

        quality_rows.append({
            "quality_code": row.quality_code,
            "source_quantity": quantity,
        })

        total_quantity += quantity

        if row.source_documents:
            references.append(
                row.source_documents
            )

    return {
        "source_quantity": flt(
            total_quantity,
            4,
        ),
        "quality_rows": quality_rows,
        "source_reference": (
            "Gilit Receive: "
            + "; ".join(references)
            if references
            else (
                "No submitted Gilit Receive found for "
                "the Worker and salary period."
            )
        ),
    }
