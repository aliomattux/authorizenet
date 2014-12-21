from openerp.osv import osv, fields
from openerp.tools.translate import _


class AccountInvoice(osv.osv):
    _inherit = 'account.invoice'
    _columns = {
	'preauthorization_code': fields.char('Authorization Code', copy=False),
	'preauthorization_transaction_id': fields.char('Authorization Transaction ID', copy=False),
	'preauthorized_amount': fields.float('Pre Authorized Amount', copy=False),
    }


    def get_cc_payment_journal(self, cr, uid, sale, context=None):
	vals = {}
	if sale.card_type:
	    journal = sale.payment_method[sale.card_type + '_journal']
	    return journal.id

	return False

    #TODO: This method returns vals so there is no reason to override it
    #Replace with simple super and update vals
    def invoice_pay_customer(self, cr, uid, ids, context=None):
        if not ids: return []
        dummy, view_id = self.pool.get('ir.model.data').get_object_reference(cr, uid, 'account_voucher', 'view_vendor_receipt_dialog_form')

        invoice = self.browse(cr, uid, ids[0], context=context)
        vals = {
            'name':_("Pay Invoice"),
            'view_mode': 'form',
            'view_id': view_id,
            'view_type': 'form',
            'res_model': 'account.voucher',
            'type': 'ir.actions.act_window',
            'nodestroy': True,
            'target': 'new',
            'domain': '[]',
            'context': {
                'payment_expected_currency': invoice.currency_id.id,
                'default_partner_id': self.pool.get('res.partner')._find_accounting_partner(invoice.partner_id).id,
                'default_amount': invoice.type in ('out_refund', 'in_refund') and -invoice.residual or invoice.residual,
                'default_reference': invoice.name,
                'close_after_process': True,
                'invoice_type': invoice.type,
                'invoice_id': invoice.id,
                'default_type': invoice.type in ('out_invoice','out_refund') and 'receipt' or 'payment',
                'type': invoice.type in ('out_invoice','out_refund') and 'receipt' or 'payment'
            }
        }


	vals['context']['default_invoice'] = invoice.id
	
	if invoice.sale_order and invoice.sale_order.payment_method:

	    journal = self.get_cc_payment_journal(cr, uid, invoice.sale_order)
	    payment_profile = invoice.sale_order.payment_profile

	    card_vals = {
                'default_journal_id': journal,
		'default_billing_address': invoice.sale_order.partner_invoice_id.id,
	    }

	    if payment_profile:
	        card_vals.update({
			'default_payment_profile': payment_profile.id,
			'default_card_number': payment_profile.card_number,
			'default_transaction_id': invoice.preauthorization_transaction_id,
			'default_preauthorized_amount': invoice.preauthorized_amount,
			'default_expiration_date': payment_profile.expiration_date,
		})
		
	        if invoice.preauthorization_code:
	            card_vals['default_authorization_code'] = invoice.preauthorization_code


	    vals['context'].update(card_vals)

	return vals
