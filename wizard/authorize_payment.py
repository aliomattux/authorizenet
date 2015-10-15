from openerp.osv import osv, fields
from pprint import pprint as pp

class SaleAuthorizePayment(osv.osv_memory):
    _name = 'sale.authorize.payment'
    _columns = {
	'sale': fields.many2one('sale.order', 'Sale'),
	'partner_id': fields.many2one('res.partner', 'Partner'),
        'payment_profile': fields.many2one('payment.profile', 'Payment Profile', \
                domain="['|',('partner', '=', partner_id), ('id', '=', partner_id)]"
        ),
        'billing_address': fields.many2one('res.partner', 'Selected Billing Address', \
                domain="['|',('parent_id', '=', partner_id), ('id', '=', partner_id)]"
        ),
        'card_number': fields.char('Card Number', copy=False),
        'expiration_date': fields.char('Expiration Date', copy=False),
        'cvv_code': fields.char('CVV Code', copy=False),
	'amount': fields.float('Amount'),
	'amount_total': fields.float('Total Amount Due'),
	'difference_amount': fields.float('Difference Amount'),
	'street': fields.char('Street'),
	'street2': fields.char('Street2'),
	'state': fields.many2one('res.country.state', 'State'),
	'country': fields.many2one('res.country', 'Country'),
	'zip': fields.char('Zip'),
	'amount_preauthorized': fields.float('Amount Already Authorized'),
    }


    def onchange_payment_profile(self, cr, uid, ids, profile_id, context=None):
	if not profile_id:
	    return {'value': {}}

	profile = self.pool.get('payment.profile').browse(cr, uid, profile_id)
	return {'value': {'card_number': profile.card_number}}


    def default_get(self, cr, uid, fields, context=None):
        if context is None: context = {}
        sale_ids = context.get('active_ids', [])
        sale = self.pool.get('sale.order').browse(cr, uid, sale_ids[0])
	address = sale.partner_invoice_id
	charge_amount = sale.amount_total - sale.authorization_amount
        res = {'sale': sale.id,
		'amount_total': sale.amount_total,
		'amount_preauthorized': sale.authorization_amount,
		'difference_amount': charge_amount,
		'amount': charge_amount,
		'partner_id': sale.partner_id.id,
		'billing_address': sale.partner_invoice_id.id,
		'payment_profile': sale.payment_profile.id,
		'street': address.street,
		'street2': address.street2,
		'state': address.state_id.id,
		'country': address.country_id.id,
		'zip': address.zip,
        }

	if sale.payment_profile:
	    res.update({
		'payment_profile': sale.payment_profile.id,
	    })

        return res


    def authorize_payment(self, cr, uid, ids, context=None):
        wizard = self.browse(cr, uid, ids[0])
	auth_obj = self.pool.get('authorizenet.api')
	profile_info = auth_obj.authorize_sale_order(cr, uid, wizard, wizard.sale)
	pp(profile_info)

	return True
