"""
Item Pending In Stock

Client reference: "ITEM STOCK REPORT AS ON DATE"
Shows only Jama lots that still have a Balance in stock.

Jama   = one received bundle / row (one Inventory Stock Source)
Udhar  = issues of that exact Stock Source out of its Jama department
Balance= Jama - Udhar (physical stock still lying in that department)

All logic lives in jari_core.jari_core.jari_report_utils (read-only).
"""

from jari_core.jari_core.jari_report_utils import execute_jama_udhar


def execute(filters=None):
    return execute_jama_udhar(filters, pending_only=True)
