import frappe

def execute():
	frappe.db.sql('''update `tabCommunication` set sender=owner
		where comment_type='Relinked' and sender is null''')
