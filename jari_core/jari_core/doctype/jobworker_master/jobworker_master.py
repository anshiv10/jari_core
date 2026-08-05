from frappe.model.document import Document

from jari_core.jari_core.doctype.process_master.process_master import (
    sync_legacy_process_assignment,
    validate_master_process_assignments,
)


class JobworkerMaster(Document):

    def validate(self):
        validate_master_process_assignments(self)
        sync_legacy_process_assignment(self)
