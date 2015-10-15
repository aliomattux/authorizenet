from openerp.osv import osv, fields

class SaleOrder(osv.osv):
    _inherit = 'sale.order'
    _columns = {
	'payment_profile': fields.many2one('payment.profile', 'Payment Profile', \
		domain="[('partner', '=', partner_id)]"
	),
	'payment_auth_code': fields.char('Authorization Code', copy=False),
	'payment_transaction_id': fields.char('Transaction ID', copy=False),
        'authnet_method': fields.related('payment_method', 'authnet_method', \
                type="boolean", string="Authorizenet Method"
        ),
	'authorization_amount': fields.float('Authorization Amount', copy=False),
	'auth_type': fields.selection([
				       ('auth_only', 'Authorization Only'),
				       ('auth_capture', 'Authorization w/ Auto Capture'),
	], 'Authorization Type'),
	'card_type': fields.related('payment_profile', 'card_type', type="char", \
		string='Card Type', copy=False
	),
	'card_expiration_date': fields.related('payment_profile', 'expiration_date', \
		type="char", string='Expiration Date'
	),
    }
	
    def onchange_payment_method(self, cr, uid, ids, payment_method, context=None):
        method_obj = self.pool.get('payment.method')
        if payment_method:
            method = method_obj.browse(cr, uid, payment_method)
            vals = {'authnet_method': method.authnet_method}
        else:
            vals = {}

        return {'value': vals}

    def onchange_payment_profile(self, cr, uid, ids, profile_id, context=None):
        vals = {
                'card_number': False,
		'card_type': False,
                'expiration_date': False,
                'cvv_code': False,
        }
        if profile_id:
            profile = self.pool.get('payment.profile').browse(cr, uid, profile_id)
            vals.update({
		'card_type': profile.card_type,
                'card_number': profile.card_number,
                'card_expiration_date': profile.expiration_date,
            })

        return {'value': vals}


    def action_invoice_create(self, cr, uid, ids, grouped=False, states=None, \
	date_invoice = False, context=None
        ):

	invoice_id = super(SaleOrder, self).action_invoice_create(cr, uid, ids, grouped=False, \
		states=None, date_invoice = False, context=None
        )

	if type(invoice_id) != list and len(ids) == 1:
	    invoice = self.pool.get('account.invoice').browse(cr, uid, invoice_id)
	    sale = self.browse(cr, uid, ids[0])
	    invoice.sale_order = sale.id

	    if sale.payment_profile:
		invoice.payment_profile = sale.payment_profile

	    if sale.payment_auth_code:
	        invoice.preauthorization_code = sale.payment_auth_code
		invoice.preauthorization_transaction_id = sale.payment_transaction_id
		invoice.preauthorized_amount = sale.authorization_amount

	return invoice_id
