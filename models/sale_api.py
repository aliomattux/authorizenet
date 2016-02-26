from openerp.osv import osv, fields
from openerp.tools.translate import _
from datetime import datetime
from suds.client import Client
from pprint import pprint as pp

PROD_URL = 'https://api.authorize.net/soap/v1/Service.asmx'
TEST_URL = 'https://apitest.authorize.net/soap/v1/Service.asmx'
WSDL_URL = 'https://api.authorize.net/soap/v1/Service.asmx?WSDL'


class AuthorizeNetAPI(osv.osv_memory):
    _inherit = 'authorizenet.api'

    def authorize_sale_order(self, cr, uid, sale_wizard, context=None):

        client, auth = self._create_client(cr, uid)
	profile_info = False

	#Do not allow them to continue if the amount is nothing
	amount_total = sale_wizard.sale.amount_total
	if not amount_total or amount_total and amount_total < 0.01:
	    raise osv.except_osv(_('Value Error'), _('Total amount must be greater than 0.00!'))
	    
	if not sale_wizard.payment_profile:
            profile_info = self.prepare_and_create_payment_profile(cr, uid, \
                auth, client, 'sale', sale_wizard
            )

	    #Update the sale order to have the customers profile
	    sale_wizard.sale.payment_profile = profile_info['odoo_payment_id']
	    #If the payment profile is created but the rest of the script fails, the profile creation cannot be rolled
	    #back in the external system so we must commit
	    cr.commit()

        transaction = self.create_sale_transaction_vals(cr, uid, sale_wizard, sale_wizard.sale)
        object = client.factory.create('CreateCustomerProfileTransaction')

	self.authorize_transaction(cr, uid, auth, client, object, transaction, profile_info, sale_wizard, sale_wizard.sale)

        return profile_info


    def create_sale_transaction_vals(self, cr, uid, sale_wizard, sale, context=None):
        transaction = {
                        'amount': round(sale_wizard.amount, 2),
			'order': {'invoiceNumber': sale.name or 'none'}
        }

        transaction['customerProfileId'] = \
                sale.payment_profile.customer_profile_id

        transaction['customerPaymentProfileId'] = sale.payment_profile.profile

        #Not Implemented
#       if voucher.tax_line:
#           transaction['tax'] = self.prepare_transaction_taxes(
#               cr, uid, voucher.tax_line
#           )

        return transaction


    def prepare_sale_payment_profile(self, cr, uid, client, sale_wizard):
        address = sale_wizard.billing_address
        partner = sale_wizard.partner_id
        object = client.factory.create('CreateCustomerProfile')
#       if voucher.partner_id.customer_profile_id:
#           print 'Only Creating new Payment Profile'
#       else:
#           print 'Creating Customer and Payment Profile'

        billTo = self.prepare_payment_profile_address(cr, uid, partner, address)

        creditCard = {
            'cardNumber': sale_wizard.card_number,
            'expirationDate': sale_wizard.expiration_date,
            'cardCode': sale_wizard.cvv_code,
        }

        data = {'customerType': 'individual',
                'billTo': billTo,
                'payment': {'creditCard': creditCard}
        }

        object.profile.paymentProfiles.CustomerPaymentProfileType.append(data)
        next_number = self.pool.get('ir.sequence').get(cr, uid, 'payment.profile.seq')
        object.profile.merchantCustomerId = 'OD_' + next_number

        return object


    def prepare_and_create_payment_profile(self, cr, uid, auth, client, object_type, object):
	print 'Creating Customer/Payment Profile'
	card_hidden = object.card_number[-5:]

	if object_type == 'voucher':
	    profile_object = self.prepare_voucher_payment_profile(cr, uid, client, object)

	else:
	    profile_object = self.prepare_sale_payment_profile(cr, uid, client, object)

	try:
	    response = self.create_payment_profile(cr, uid, auth, client, profile_object)
	    print 'SENT', client.last_sent()
#	    print 'RESPONSE', response
	except Exception, e:
	    response = str(e)

	#Check the response to ensure no error happened
	self.process_authnet_response(cr, uid, response)

	for id in response.customerPaymentProfileIdList:
	    payment_id = id[1][0]
	    break

	#TODO: Card type is hardcoded
	vals = {
		'partner': object.partner_id.id,
		'expiration_date': object.expiration_date,
		'card_type': 'visa',
		'customer_profile_id': response.customerProfileId,
		'payment_type': 'creditcard',
		'profile': payment_id,
		'card_number': card_hidden
	}


	#TODO: Review
#	self.pool.get('res.partner').write(cr, uid, object.partner_id.id, \
#		{'customer_profile_id': response.customerProfileId})

	odoo_payment_id = self.create_odoo_payment_profile(cr, uid, vals)

	return {'payment_profile': payment_id,
		'odoo_payment_id': odoo_payment_id,
		'customer_profile_id': response.customerProfileId,
		'card_number': card_hidden,
	}


    def authorize_transaction(self, cr, uid, auth, client, object, trans_vals, customer_data, sale_wizard, sale):
#       print 'Call Authorize only'

        if customer_data:
            trans_vals['customerProfileId'] = customer_data['customer_profile_id']
            trans_vals['customerPaymentProfileId'] = customer_data['payment_profile']


        object.transaction = {'profileTransAuthOnly': trans_vals}

        try:
            response = client.service.CreateCustomerProfileTransaction(auth, object.transaction)
	    print 'SENT', client.last_sent()
	    print 'RESPONSE', response
        except Exception, e:
            response = str(e)

        self.process_authnet_response(cr, uid, response)


	#TODO: Review
	try:
	    data = response.directResponse
            details = data.split(',')
	    auth_id = details[4]
            transaction_id = details[6]
	    sale.payment_auth_code = auth_id
	    sale.payment_transaction_id = transaction_id
	    sale.authorization_amount = sale_wizard.amount_preauthorized + sale_wizard.difference_amount

	    auth_obj = self.pool.get('authorizenet.authorizations')
	    vals = {
		'sale': sale.id,
		'transaction_id': transaction_id,
		'payment_profile': sale.payment_profile.id, 
		'card_number':  sale.payment_profile.card_number,
		'authorization_code': auth_id,
		'amount': sale_wizard.amount,
		'auth_status': 'auth',
	    }
	    i = auth_obj.create(cr, uid, vals)
	    print 'Created Auth', i
	except Exception, e:
	    #TODO
	    print e

	return True

