import frappe
from frappe.utils import flt, getdate


def get_columns():
    return [
        {
            "label": "Stock Summary",
            "fieldname": "stock_summary",
            "fieldtype": "Data",
            "width": 300,
        },
        {
            "label": "Company",
            "fieldname": "company",
            "fieldtype": "Link",
            "options": "Company Master",
            "width": 160,
        },
        {
            "label": "Department",
            "fieldname": "department",
            "fieldtype": "Link",
            "options": "Department Master",
            "width": 160,
        },
        {
            "label": "Product",
            "fieldname": "product",
            "fieldtype": "Link",
            "options": "Product Master",
            "width": 160,
        },
        {
            "label": "Current Balance (KG)",
            "fieldname": "current_balance",
            "fieldtype": "Float",
            "width": 170,
        },
        {
            "label": "Total In (KG)",
            "fieldname": "total_in",
            "fieldtype": "Float",
            "width": 130,
        },
        {
            "label": "Consumed / Used (KG)",
            "fieldname": "total_out",
            "fieldtype": "Float",
            "width": 160,
        },
        {
            "label": "Transactions",
            "fieldname": "txn_count",
            "fieldtype": "Int",
            "width": 110,
        },
        {
            "label": "Last Updated",
            "fieldname": "last_updated",
            "fieldtype": "Date",
            "width": 130,
        },
    ]


def execute(filters=None):
    """
    Stock Position Report.

    Backward compatibility:
        With no From Date / To Date, preserve the existing all-time
        Stock Position Report calculation exactly.

    Date-filter mode:
        Total In / Total Out / Transactions
            = movements inside the requested date window.

        Current Balance
            = closing physical stock as of To Date.

        If only From Date is supplied, Current Balance remains the
        present closing stock while movement metrics begin From Date.

        If only To Date is supplied, movement metrics and closing stock
        are both calculated up to To Date.
    """
    filters = frappe._dict(filters or {})

    from_date = _optional_date(
        filters.get("from_date")
    )

    to_date = _optional_date(
        filters.get("to_date")
    )

    if (
        from_date
        and to_date
        and from_date > to_date
    ):
        frappe.throw(
            "From Date cannot be after To Date."
        )

    if not from_date and not to_date:
        data = _get_current_report_data(
            filters
        )
    else:
        data = _get_date_filtered_data(
            filters,
            from_date,
            to_date,
        )

    _format_rows(
        data
    )

    return get_columns(), data


def _optional_date(value):
    if not value:
        return None

    return getdate(
        value
    )


def _get_dimension_conditions(filters):
    conditions = [
        "1 = 1"
    ]

    values = {}

    if filters.get("company"):
        conditions.append(
            "company = %(company)s"
        )

        values["company"] = (
            filters.get("company")
        )

    if filters.get("department"):
        conditions.append(
            "department = %(department)s"
        )

        values["department"] = (
            filters.get("department")
        )

    if filters.get("product"):
        conditions.append(
            "product = %(product)s"
        )

        values["product"] = (
            filters.get("product")
        )

    return (
        " AND ".join(conditions),
        values,
    )


def _get_current_report_data(filters):
    """
    Preserve the report's original all-time behaviour exactly.

    This deliberately keeps the existing calculation:

        total_out = total_in - latest.current_balance

    so introducing optional date filters does not change the report
    when users leave both Date filters blank.
    """
    conditions = [
        "latest.current_balance > 0"
    ]

    values = {}

    if filters.get("company"):
        conditions.append(
            "latest.company = %(company)s"
        )

        values["company"] = (
            filters["company"]
        )

    if filters.get("department"):
        conditions.append(
            "latest.department = %(department)s"
        )

        values["department"] = (
            filters["department"]
        )

    if filters.get("product"):
        conditions.append(
            "latest.product = %(product)s"
        )

        values["product"] = (
            filters["product"]
        )

    where_clause = " AND ".join(
        conditions
    )

    return frappe.db.sql(
        """
        SELECT
            latest.company,
            latest.department,
            latest.product,
            latest.current_balance,
            agg.total_in,

            CASE
                WHEN agg.total_in
                     >= latest.current_balance
                THEN
                    agg.total_in
                    - latest.current_balance
                ELSE 0
            END AS total_out,

            agg.txn_count,
            latest.date AS last_updated

        FROM `tabInventory Ledger` latest

        INNER JOIN (
            SELECT
                company,
                department,
                product,

                SUM(
                    CASE
                        WHEN in_weight > 0
                        THEN in_weight
                        ELSE 0
                    END
                ) AS total_in,

                COUNT(*) AS txn_count,

                MAX(creation) AS max_creation

            FROM `tabInventory Ledger`

            GROUP BY
                company,
                department,
                product
        ) agg

            ON latest.company
                = agg.company

            AND latest.department
                = agg.department

            AND latest.product
                = agg.product

            AND latest.creation
                = agg.max_creation

        WHERE {where_clause}

        ORDER BY
            latest.product,
            latest.department
        """.format(
            where_clause=where_clause
        ),
        values,
        as_dict=True,
    )


def _get_date_filtered_data(
    filters,
    from_date,
    to_date,
):
    """
    Historical/date-window mode.

    Closing stock:
        cumulative IN - OUT up to To Date.

    Period activity:
        direct IN / OUT / transaction count inside the requested
        inclusive date range.

    A group remains visible when either:
        - it has positive closing stock, or
        - it had transactions inside the selected period.

    The second rule is important for date-wise transaction tracking:
    material fully consumed during a period must not disappear from
    the report simply because its closing balance is zero.
    """
    (
        dimension_conditions,
        values,
    ) = _get_dimension_conditions(
        filters
    )

    balance_date_condition = ""

    period_date_conditions = []

    if from_date:
        values["from_date"] = (
            from_date
        )

        period_date_conditions.append(
            "`date` >= %(from_date)s"
        )

    if to_date:
        values["to_date"] = (
            to_date
        )

        balance_date_condition = (
            " AND `date` <= %(to_date)s "
        )

        period_date_conditions.append(
            "`date` <= %(to_date)s"
        )

    period_date_clause = ""

    if period_date_conditions:
        period_date_clause = (
            " AND "
            + " AND ".join(
                period_date_conditions
            )
        )

    return frappe.db.sql(
        """
        SELECT
            stock_groups.company,
            stock_groups.department,
            stock_groups.product,

            COALESCE(
                balance.current_balance,
                0
            ) AS current_balance,

            COALESCE(
                period.total_in,
                0
            ) AS total_in,

            COALESCE(
                period.total_out,
                0
            ) AS total_out,

            COALESCE(
                period.txn_count,
                0
            ) AS txn_count,

            balance.last_updated

        FROM (

            SELECT
                company,
                department,
                product

            FROM `tabInventory Ledger`

            WHERE
                {dimension_conditions}
                {balance_date_condition}

            GROUP BY
                company,
                department,
                product

            UNION

            SELECT
                company,
                department,
                product

            FROM `tabInventory Ledger`

            WHERE
                {dimension_conditions}
                {period_date_clause}

            GROUP BY
                company,
                department,
                product

        ) stock_groups

        LEFT JOIN (

            SELECT
                company,
                department,
                product,

                SUM(
                    COALESCE(in_weight, 0)
                    -
                    COALESCE(out_weight, 0)
                ) AS current_balance,

                MAX(`date`) AS last_updated

            FROM `tabInventory Ledger`

            WHERE
                {dimension_conditions}
                {balance_date_condition}

            GROUP BY
                company,
                department,
                product

        ) balance

            ON balance.company
                = stock_groups.company

            AND balance.department
                = stock_groups.department

            AND balance.product
                = stock_groups.product

        LEFT JOIN (

            SELECT
                company,
                department,
                product,

                SUM(
                    CASE
                        WHEN in_weight > 0
                        THEN in_weight
                        ELSE 0
                    END
                ) AS total_in,

                SUM(
                    CASE
                        WHEN out_weight > 0
                        THEN out_weight
                        ELSE 0
                    END
                ) AS total_out,

                COUNT(*) AS txn_count

            FROM `tabInventory Ledger`

            WHERE
                {dimension_conditions}
                {period_date_clause}

            GROUP BY
                company,
                department,
                product

        ) period

            ON period.company
                = stock_groups.company

            AND period.department
                = stock_groups.department

            AND period.product
                = stock_groups.product

        WHERE
            (
                COALESCE(
                    balance.current_balance,
                    0
                ) > 0.000001
            )
            OR
            (
                COALESCE(
                    period.txn_count,
                    0
                ) > 0
            )

        ORDER BY
            stock_groups.product,
            stock_groups.department
        """.format(
            dimension_conditions=
                dimension_conditions,

            balance_date_condition=
                balance_date_condition,

            period_date_clause=
                period_date_clause,
        ),
        values,
        as_dict=True,
    )


def _format_rows(data):
    for row in data:
        row.current_balance = flt(
            row.current_balance,
            3,
        )

        row.total_in = flt(
            row.total_in,
            3,
        )

        row.total_out = flt(
            row.total_out,
            3,
        )

        row.txn_count = int(
            row.txn_count or 0
        )

        row.stock_summary = (
            row.product
            + " - "
            + str(
                row.current_balance
            )
            + " KG - "
            + row.department
        )
