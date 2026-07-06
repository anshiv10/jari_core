import frappe
from frappe.model.document import Document
from frappe.utils import flt


class PetiMaster(Document):

    def validate(self):
        self.calculate_net_weight()

    def calculate_net_weight(self):
        self.net_weight = flt(self.gross_weight) - flt(self.baad)