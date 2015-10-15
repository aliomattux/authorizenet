from openerp.osv import osv, fields
from openerp.tools.translate import _


class AccountInvoice(osv.osv):
    _inherit = 'account.invoice'
    _columns = {
	'preauthorization_code': fields.char('Authorization Code', copy=False),
	'preauthorization_transaction_id': fields.char('Authorization Transaction ID', copy=False),
	'preauthorized_amount': fields.float('Pre Authorized Amount', copy=False),
    }


    def get_cc_payment_journal(self, cr, uid, invoice, context=None):
	if not invoice.sale_order:
	    return False

	sale = invoice.sale_order

	if sale.card_type:
	    journal = sale.payment_method[sale.card_type + '_journal']
	    return journal.id

	return False


    def get_payment_profile(self, cr, uid, invoice, context=None):
        if invoice.sale_order and invoice.sale_order.payment_profile:
            return invoice.sale_order.payment_profile

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


	default_vals = {
		'default_invoice': invoice.id,
		'default_invoice_type': invoice.type,
	}

#	if invoice.purchase_order:
#	    default_vals['default_supplier_payment'] = True

	journal = self.get_cc_payment_journal(cr, uid, invoice)
	if journal:
	    default_vals['default_journal_id'] = journal

	payment_profile = self.get_payment_profile(cr, uid, invoice)
	print 'Profile', payment_profile
	if payment_profile:
	    default_vals.update({
		'default_payment_profile': payment_profile.id,
		'default_card_number': payment_profile.card_number,
		'default_expiration_date': payment_profile.expiration_date,

	    })
	
	if invoice.sale_order and invoice.sale_order.payment_method:

	    card_vals = {
		'default_billing_address': invoice.sale_order.partner_invoice_id.id,
	    }

	    if invoice.preauthorization_transaction_id:
	        card_vals.update({
			'default_transaction_id': invoice.preauthorization_transaction_id,
			'default_preauthorized_amount': invoice.preauthorized_amount,
		})
		
	        if invoice.preauthorization_code:
	            card_vals['default_authorization_code'] = invoice.preauthorization_code


	    vals['context'].update(card_vals)
	vals['context'].update(default_vals)
	return vals
