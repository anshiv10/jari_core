import traceback

import frappe
from frappe.utils import flt, now_datetime, today


SAVEPOINT = "asarva_automated_smoke_test"


def assert_equal(actual, expected, message):
    if actual != expected:
        frappe.throw(
            f"{message}<br>"
            f"Expected: <b>{expected}</b><br>"
            f"Actual: <b>{actual}</b>"
        )


def assert_float(actual, expected, message):
    if abs(flt(actual) - flt(expected)) > 0.001:
        frappe.throw(
            f"{message}<br>"
            f"Expected: <b>{flt(expected, 3)}</b><br>"
            f"Actual: <b>{flt(actual, 3)}</b>"
        )


def execute():
    frappe.db.savepoint(SAVEPOINT)

    suffix = now_datetime().strftime("%Y%m%d%H%M%S")

    created = {
        "process": None,
        "jobworker": None,
        "worker": None,
        "issue": None,
        "receive_1": None,
        "receive_2": None,
    }

    try:
        validate_prerequisites()

        company = frappe.db.get_value(
            "Company Master",
            {},
            "name",
        )

        product = frappe.db.get_value(
            "Product Master",
            {},
            "name",
        )

        quality = frappe.db.get_value(
            "Quality Master",
            {},
            "name",
        )

        # -------------------------------------------------
        # Temporary Process Master
        # -------------------------------------------------

        process = frappe.get_doc({
            "doctype": "Process Master",
            "process_name": f"Asarva Smoke Test {suffix}",
            "process_code": f"AST{suffix[-4:]}",
            "department": "Rangrej/Asarva",
            "from_department": "Taniya",
            "to_department": "Rangrej/Asarva",
            "flow_type": "Real",
            "is_outsourced": 1,
        })

        process.insert(ignore_permissions=True)
        created["process"] = process.name

        print("\nTEMPORARY PROCESS CREATED")
        print({
            "name": process.name,
            "from_department": process.from_department,
            "to_department": process.to_department,
            "is_outsourced": process.is_outsourced,
        })

        # -------------------------------------------------
        # Temporary Jobworker Master
        # -------------------------------------------------

        jobworker = frappe.get_doc({
            "doctype": "Jobworker Master",
            "jobworker_name":
                f"Asarva Smoke Outsourcer {suffix}",
            "process_master": process.name,
        })

        jobworker.insert(ignore_permissions=True)
        created["jobworker"] = jobworker.name

        print("\nTEMPORARY JOBWORKER CREATED")
        print({
            "name": jobworker.name,
            "process_master": jobworker.process_master,
        })

        # -------------------------------------------------
        # Temporary Worker Master
        # -------------------------------------------------

        worker = frappe.get_doc({
            "doctype": "Worker Master",
            "employee":
                f"Asarva Smoke Operator {suffix}",
            "payroll_type": "Hourly",
            "rate": 1,
            "department": "Rangrej/Asarva",
            "process_master": process.name,
            "active": 1,
        })

        worker.insert(ignore_permissions=True)
        created["worker"] = worker.name

        print("\nTEMPORARY WORKER CREATED")
        print({
            "name": worker.name,
            "employee": worker.employee,
            "department": worker.department,
            "process_master": worker.process_master,
        })

        # -------------------------------------------------
        # Asarva Issue
        # -------------------------------------------------

        issue = frappe.get_doc({
            "doctype": "Asarva Issue",
            "issue_date": today(),
            "company": company,
            "asarva_outsourcer": jobworker.name,
            "issued_by": frappe.session.user,
            "from_department": "Taniya",
            "to_department": "Rangrej/Asarva",
            "batch_no": f"ASARVA-SMOKE-{suffix}",
            "process_master": process.name,
            "quality_code": quality,
            "expected_receive_percent": 75,
            "issue_items": [
                {
                    "doctype": "Asarva Issue Item",
                    "issue_date": today(),
                    "product": product,
                    "product_quality": quality,
                    "rangrej_operator": worker.name,
                    "colour": "Limboi",
                    "issued_weight": 100,
                    "uom": "KG",
                }
            ],
        })

        issue.insert(ignore_permissions=True)
        created["issue"] = issue.name

        assert_float(
            issue.total_issued_weight,
            100,
            "Total Issued Weight calculation failed.",
        )

        assert_float(
            issue.expected_received_weight,
            75,
            "Expected Received Weight calculation failed.",
        )

        assert_float(
            issue.total_received_weight,
            0,
            "New Issue should have zero Received Weight.",
        )

        issue.submit()
        issue.reload()

        assert_equal(
            issue.status,
            "Issued",
            "Submitted Issue status is incorrect.",
        )

        print("\nASARVA ISSUE PASSED")
        print({
            "name": issue.name,
            "total_issued_weight":
                issue.total_issued_weight,
            "expected_received_weight":
                issue.expected_received_weight,
            "status": issue.status,
        })

        # -------------------------------------------------
        # First Draft Receive: 40 - 4 = 36
        # -------------------------------------------------

        receive_1 = frappe.get_doc({
            "doctype": "Asarva Receive",
            "asarva_issue": issue.name,
            "receive_date": today(),
        })

        receive_1.insert(ignore_permissions=True)
        created["receive_1"] = receive_1.name

        if not receive_1.receive_items:
            frappe.throw(
                "Asarva Receive rows were not copied "
                "from the selected Issue."
            )

        first_row = receive_1.receive_items[0]

        first_row.quantity_firka = 10
        first_row.lot_no = "LOT-SMOKE-1"
        first_row.gross_weight = 40
        first_row.baad_weight = 4

        receive_1.save(ignore_permissions=True)
        receive_1.reload()
        issue.reload()

        assert_float(
            receive_1.total_gross_weight,
            40,
            "First Receive Gross Weight is incorrect.",
        )

        assert_float(
            receive_1.total_baad_weight,
            4,
            "First Receive Baad Weight is incorrect.",
        )

        assert_float(
            receive_1.total_received_weight,
            36,
            "First Receive Weight must equal 40 - 4.",
        )

        assert_float(
            issue.total_received_weight,
            36,
            "Draft Receive was not included in Issue total.",
        )

        assert_float(
            issue.balance_expected_weight,
            39,
            "Issue Balance Expected Weight should be 39.",
        )

        assert_equal(
            issue.status,
            "Partially Received",
            "Issue status should be Partially Received.",
        )

        print("\nFIRST DRAFT RECEIVE PASSED")
        print({
            "receive": receive_1.name,
            "gross_weight":
                receive_1.total_gross_weight,
            "baad_weight":
                receive_1.total_baad_weight,
            "received_weight":
                receive_1.total_received_weight,
            "issue_total_received":
                issue.total_received_weight,
            "issue_balance":
                issue.balance_expected_weight,
            "issue_status":
                issue.status,
        })

        # -------------------------------------------------
        # Second Draft Receive: 45 - 5 = 40
        # Combined = 76
        # -------------------------------------------------

        receive_2 = frappe.get_doc({
            "doctype": "Asarva Receive",
            "asarva_issue": issue.name,
            "receive_date": today(),
        })

        receive_2.insert(ignore_permissions=True)
        created["receive_2"] = receive_2.name

        if not receive_2.receive_items:
            frappe.throw(
                "Second Asarva Receive rows were not copied."
            )

        second_row = receive_2.receive_items[0]

        second_row.quantity_firka = 10
        second_row.lot_no = "LOT-SMOKE-2"
        second_row.gross_weight = 45
        second_row.baad_weight = 5

        receive_2.save(ignore_permissions=True)
        receive_2.reload()
        issue.reload()

        assert_float(
            receive_2.total_received_weight,
            40,
            "Second Receive Weight must equal 45 - 5.",
        )

        assert_float(
            issue.total_received_weight,
            76,
            "Combined received total should be 76.",
        )

        assert_float(
            issue.balance_expected_weight,
            0,
            "Expected balance should be zero.",
        )

        assert_equal(
            issue.status,
            "Received",
            "Issue status should be Received.",
        )

        print("\nSECOND DRAFT RECEIVE PASSED")
        print({
            "receive": receive_2.name,
            "received_weight":
                receive_2.total_received_weight,
            "issue_total_received":
                issue.total_received_weight,
            "issue_balance":
                issue.balance_expected_weight,
            "issue_status":
                issue.status,
        })

        # -------------------------------------------------
        # Delete second Receive and verify reversal
        # -------------------------------------------------

        receive_2.delete(ignore_permissions=True)
        issue.reload()

        assert_float(
            issue.total_received_weight,
            36,
            "Issue total did not reverse after deletion.",
        )

        assert_float(
            issue.balance_expected_weight,
            39,
            "Issue balance did not reverse after deletion.",
        )

        assert_equal(
            issue.status,
            "Partially Received",
            "Issue status did not reverse correctly.",
        )

        print("\nRECEIVE DELETION REVERSAL PASSED")
        print({
            "issue_total_received":
                issue.total_received_weight,
            "issue_balance":
                issue.balance_expected_weight,
            "issue_status":
                issue.status,
        })

        print("\n" + "=" * 70)
        print("ASARVA AUTOMATED SMOKE TEST PASSED")
        print("=" * 70)

    except Exception:
        print("\n" + "=" * 70)
        print("ASARVA AUTOMATED SMOKE TEST FAILED")
        print("=" * 70)
        traceback.print_exc()
        raise

    finally:
        frappe.db.rollback(
            save_point=SAVEPOINT
        )

        print("\nROLLBACK COMPLETED")
        print("No Process, Jobworker, Worker, Issue, or Receive")
        print("created by this test was retained.")


def validate_prerequisites():
    required_doctypes = [
        "Asarva Issue",
        "Asarva Issue Item",
        "Asarva Receive",
        "Asarva Receive Item",
        "Process Master",
        "Jobworker Master",
        "Worker Master",
        "Company Master",
        "Product Master",
        "Department Master",
    ]

    for doctype in required_doctypes:
        if not frappe.db.exists(
            "DocType",
            doctype,
        ):
            frappe.throw(
                f"Required DocType is missing: {doctype}"
            )

    if not frappe.db.exists(
        "Department Master",
        "Rangrej/Asarva",
    ):
        frappe.throw(
            "Department Rangrej/Asarva does not exist."
        )

    if not frappe.db.exists(
        "Department Master",
        "Taniya",
    ):
        frappe.throw(
            "Source Department Taniya does not exist."
        )

    if not frappe.db.exists(
        "Company Master",
        {},
    ):
        frappe.throw(
            "At least one Company Master record is required."
        )

    if not frappe.db.exists(
        "Product Master",
        {},
    ):
        frappe.throw(
            "At least one Product Master record is required."
        )
