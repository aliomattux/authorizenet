from openerp.osv import osv, fields


class authorizenet_authorizations(osv.osv):
    _name = 'authorizenet.authorizations'
    _order = 'amount DESC'
    _columns = {
	'sale': fields.many2one('sale.order', 'Sale'),
	'transaction_id': fields.char('Transaction ID', copy=False),
        'payment_profile': fields.many2one('payment.profile', 'Payment Profile', \
                domain="['|',('partner', '=', partner_id), ('id', '=', partner_id)]"
        ),
	'auth_status': fields.selection([
		('void', 'Voided'),
		('refund', 'Refunded'),
		('auth', 'Authorized'),
		('capture', 'Captured'),
		], 'Auth Status'
	),
	'card_number': fields.char('Card Number', copy=False),
	'expiration_date': fields.char('Expiration Date', copy=False),
	'authorization_code': fields.char('Authorization Code', copy=False),
	'amount': fields.float('Amount'),
    }

    def void_authorization(self, cr, uid, ids, context=None):
	#TODO: Implement Void functionality
	auth_obj = self.pool.get('authorizenet.api')
	client, authorization = auth_obj._create_client(cr, uid)
	for auth in self.browse(cr, uid, ids):
	    vals = {'customerProfileId': auth.payment_profile.customer_profile_id,
		'customerPaymentProfileId': auth.payment_profile.profile,
		'amount': 0,
		'transId': auth.transaction_id,
	    }
	    object = client.factory.create('CreateCustomerProfile')
	    auth_obj.void_transaction(cr, uid, authorization, client, object, vals)
	    auth.auth_status = 'void'
	    #Decrement the sale order auathorized amount
	    auth.sale.authorization_amount -= auth.amount

	return True


class SaleOrder(osv.osv):
    _inherit = 'sale.order'
    _columns = {
	'authorizations': fields.one2many('authorizenet.authorizations', 'sale', 'Authorizations'),
    }
