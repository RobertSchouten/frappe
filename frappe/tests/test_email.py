# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# MIT License. See license.txt

from __future__ import unicode_literals

import unittest, frappe, re

from frappe.test_runner import make_test_records
make_test_records("User")
make_test_records("Email Account")

class TestEmail(unittest.TestCase):
	def setUp(self):
		frappe.db.sql("""delete from `tabEmail Unsubscribe`""")
		frappe.db.sql("""delete from `tabEmail Queue`""")
		frappe.db.sql("""delete from `tabEmail Queue Recipient`""")

	def test_email_queue(self, send_after=None):
		frappe.sendmail(recipients = ['test@example.com', 'test1@example.com'],
			sender="admin@example.com",
			reference_doctype='User', reference_name='Administrator',
			subject='Testing Queue', message='This mail is queued!',
			unsubscribe_message="Unsubscribe", send_after=send_after)

		email_queue = frappe.db.sql("""select name,message from `tabEmail Queue` where status='Not Sent'""", as_dict=1)
		self.assertEquals(len(email_queue), 1)
		queue_recipients = [r.recipient for r in frappe.db.sql("""SELECT recipient FROM `tabEmail Queue Recipient` 
			WHERE status='Not Sent'""", as_dict=1)]
		self.assertTrue('test@example.com' in queue_recipients)
		self.assertTrue('test1@example.com' in queue_recipients)
		self.assertEquals(len(queue_recipients), 2)
		self.assertTrue('<!--unsubscribe url-->' in email_queue[0]['message'])

	def test_send_after(self):
		self.test_email_queue(send_after = 1)
		from frappe.email.queue import flush
		flush(from_test=True)
		email_queue = frappe.db.sql("""select name from `tabEmail Queue` where status='Sent'""", as_dict=1)
		self.assertEquals(len(email_queue), 0)

	def test_flush(self):
		self.test_email_queue()
		from frappe.email.queue import flush
		flush(from_test=True)
		email_queue = frappe.db.sql("""select name from `tabEmail Queue` where status='Sent'""", as_dict=1)
		self.assertEquals(len(email_queue), 1)
		queue_recipients = [r.recipient for r in frappe.db.sql("""select recipient from `tabEmail Queue Recipient` 
			where status='Sent'""", as_dict=1)]
		self.assertTrue('test@example.com' in queue_recipients)
		self.assertTrue('test1@example.com' in queue_recipients)
		self.assertEquals(len(queue_recipients), 2)
		self.assertTrue('Unsubscribe' in frappe.flags.sent_mail)

	def test_cc(self):
		#test if sending with cc's makes it into header
		frappe.sendmail(recipients=['test@example.com'],
			cc=['test1@example.com'],
			sender="admin@example.com",
			reference_doctype='User', reference_name="Administrator",
			subject='Testing Email Queue', message='This is mail is queued!', unsubscribe_message="Unsubscribe", expose_recipients=True)
		email_queue = frappe.db.sql("""select name from `tabEmail Queue` where status='Not Sent'""", as_dict=1)
		self.assertEquals(len(email_queue), 1)
		queue_recipients = [r.recipient for r in frappe.db.sql("""select recipient from `tabEmail Queue Recipient` 
			where status='Not Sent'""", as_dict=1)]
		self.assertTrue('test@example.com' in queue_recipients)
		self.assertTrue('test1@example.com' in queue_recipients)

		message = frappe.db.sql("""select message from `tabEmail Queue` 
			where status='Not Sent'""", as_dict=1)[0].message
		self.assertTrue('To: test@example.com' in message)
		self.assertTrue('CC: test1@example.com' in message)

	def test_expose(self):
		frappe.sendmail(recipients=['test@example.com'],
			cc=['test1@example.com'],
			sender="admin@example.com",
			reference_doctype='User', reference_name="Administrator",
			subject='Testing Email Queue', message='This is mail is queued!', unsubscribe_message="Unsubscribe", now=True)
		email_queue = frappe.db.sql("""select name from `tabEmail Queue` where status='Sent'""", as_dict=1)
		self.assertEquals(len(email_queue), 1)
		queue_recipients = [r.recipient for r in frappe.db.sql("""select recipient from `tabEmail Queue Recipient` 
			where status='Sent'""", as_dict=1)]
		self.assertTrue('test@example.com' in queue_recipients)
		self.assertTrue('test1@example.com' in queue_recipients)
		
		message = frappe.db.sql("""select message from `tabEmail Queue` 
			where status='Sent'""", as_dict=1)[0].message
		self.assertTrue('<!--recipient-->' in message)

		frappe.local.flags.signed_query_string = re.search('(?<=/api/method/frappe.email.queue.unsubscribe\?).*(?=\n)', frappe.flags.sent_mail).group(0)
		from frappe.utils.verified_command import verify_request
		self.assertTrue(verify_request())

	def test_expired(self):
		self.test_email_queue()
		frappe.db.sql("update `tabEmail Queue` set modified=DATE_SUB(curdate(), interval 8 day)")
		from frappe.email.queue import clear_outbox
		clear_outbox()
		email_queue = frappe.db.sql("""select name from `tabEmail Queue` where status='Expired'""", as_dict=1)
		self.assertEquals(len(email_queue), 1)
		queue_recipients = [r.recipient for r in frappe.db.sql("""select recipient from `tabEmail Queue Recipient` 
			where parent = %s""",email_queue[0].name, as_dict=1)]
		self.assertTrue('test@example.com' in queue_recipients)
		self.assertTrue('test1@example.com' in queue_recipients)
		self.assertEquals(len(queue_recipients), 2)

	def test_unsubscribe(self):
		from frappe.email.queue import unsubscribe, send
		unsubscribe(doctype="User", name="Administrator", email="test@example.com")

		self.assertTrue(frappe.db.get_value("Email Unsubscribe",
			{"reference_doctype": "User", "reference_name": "Administrator", "email": "test@example.com"}))

		before = frappe.db.sql("""select count(name) from `tabEmail Queue` where status='Not Sent'""")[0][0]

		send(recipients = ['test@example.com', 'test1@example.com'],
			sender="admin@example.com",
			reference_doctype='User', reference_name= "Administrator",
			subject='Testing Email Queue', message='This is mail is queued!', unsubscribe_message="Unsubscribe")

		# this is sent async (?)

		email_queue = frappe.db.sql("""select name from `tabEmail Queue` where status='Not Sent'""",
			as_dict=1)
		self.assertEquals(len(email_queue), before + 1)
		queue_recipients = [r.recipient for r in frappe.db.sql("""select recipient from `tabEmail Queue Recipient` 
			where status='Not Sent'""", as_dict=1)]
		self.assertFalse('test@example.com' in queue_recipients)
		self.assertTrue('test1@example.com' in queue_recipients)
		self.assertEquals(len(queue_recipients), 1)
		self.assertTrue('Unsubscribe' in frappe.flags.sent_mail)

	def test_email_queue_limit(self):
		from frappe.email.queue import send, EmailLimitCrossedError
		self.assertRaises(EmailLimitCrossedError, send,
			recipients=['test@example.com']*1000,
			sender="admin@example.com",
			reference_doctype = "User", reference_name="Administrator",
			subject='Testing Email Queue', message='This email is queued!')

	def test_image_parsing(self):
		import re
		email_account = frappe.get_doc('Email Account', '_Test Email Account 1')

		with open(frappe.get_app_path('frappe', 'tests', 'data', 'email_with_image.txt'), 'r') as raw:
			communication = email_account.insert_communication(raw.read())

		#print communication.content
		self.assertTrue(re.search('''<img[^>]*src=["']/private/files/rtco1.png[^>]*>''', communication.content))
		self.assertTrue(re.search('''<img[^>]*src=["']/private/files/rtco2.png[^>]*>''', communication.content))


if __name__=='__main__':
	frappe.connect()
	unittest.main()
