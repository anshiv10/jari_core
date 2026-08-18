import frappe


def execute():
    setup_yt_department()
    enable_jari_pack_sale_types()


def setup_yt_department():
    if frappe.db.exists(
        "Department Master",
        "YT Department",
    ):
        frappe.db.set_value(
            "Department Master",
            "YT Department",
            {
                "flow_type":
                    "Imitation",
                "active":
                    1,
            },
            update_modified=False,
        )
        return

    frappe.get_doc({
        "doctype":
            "Department Master",
        "department_name":
            "YT Department",
        "flow_type":
            "Imitation",
        "active":
            1,
    }).insert(
        ignore_permissions=True
    )


def enable_jari_pack_sale_types():
    meta = frappe.get_meta(
        "Product Master"
    )

    required_fields = {
        "allow_marks_sale",
        "allow_firki_sale",
    }

    if not all(
        meta.has_field(fieldname)
        for fieldname in required_fields
    ):
        return

    frappe.db.sql(
        """
        UPDATE `tabProduct Master`
        SET
            allow_marks_sale = 1,
            allow_firki_sale = 1
        WHERE product_tag = 'JARI'
        """
    )
