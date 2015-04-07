from openerp.osv import osv, fields
from openerp.tools.translate import _
from suds.client import Client


PROD_URL = 'https://api.authorize.net/soap/v1/Service.asmx'
TEST_URL = 'https://apitest.authorize.net/soap/v1/Service.asmx'
WSDL_URL = 'https://api.authorize.net/soap/v1/Service.asmx?WSDL'


class AuthorizeNetAPI(osv.osv_memory):
    _name = 'authorizenet.api'


    def _get_authentication_data(self, cr, uid, context=None):
        config_obj = self.pool.get('authorize.config')
	config_id = config_obj.search(cr, uid, [('active', '=', True)], limit=1)

	if not config_id:
	    raise osv.except_osv(_('Config Error'), _('Authorize.net is not set up!'))

	config = config_obj.browse(cr, uid, config_id[0])
	return {
		'wsdl': WSDL_URL,
		'merchant_id': config.merchant_id,
		'url': PROD_URL if config.gateway_mode == 'live' else TEST_URL,
		'transaction_key': config.transaction_key,
	}


    def _create_client(self, cr, uid):
	auth = self._get_authentication_data(cr, uid)
	merchant_key = {'name': auth['merchant_id'], 'transactionKey': auth['transaction_key']}
	return (Client(url=auth['wsdl'], location=auth['url']), merchant_key)


    def upsert_external_payment_transaction(self, cr, uid, voucher, journal, context=None):
	client, auth = self._create_client(cr, uid)
	#Create a base payment transaction
	transaction = self.create_transaction_vals(cr, uid, voucher)
	object = client.factory.create('CreateCustomerProfileTransaction')

	#If this is collecting a payment
	if voucher.invoice.type == 'out_invoice':
	    #If the voucher has a pre-authorization
	    if voucher.authorization_code:

                self.capture_prior_auth_transaction(cr, uid, auth, client, \
                    object, voucher, transaction
                )

		#If the paid amount is greather than the authorized amount
		if round(voucher.amount, 2) > round(voucher.preauthorized_amount, 2):
		    self.capture_transaction(cr, uid, auth, client, \
			voucher
		    )

	    #This is a brand new payment
	    ####  This functionality to be deprecated  ####
	    else:
		if voucher.payment_profile:
		    self.authorize_and_capture_transaction(cr, uid, auth, client, object, transaction)

		else:
		    raise osv.except_osv(_('System Error'), _("You should not be able to get this far"))
		    profile_info = self.prepare_and_create_payment_profile(cr, uid, \
			auth, client, voucher
		    )

		    self.authorize_and_capture_transaction(cr, uid, auth,\
			 client, object, transaction, profile_info
		    )

	#Process a refund
	elif voucher.invoice.type == 'out_refund':
	    self.refund_transaction(cr, uid, auth, client, object, transaction)

	else:
	    #What happens here?
	    raise

	return True


    def create_transaction_vals(self, cr, uid, voucher, context=None):
        transaction = {
                        'amount': round(voucher.amount, 2),
        }

	if voucher.partner_id.customer_profile_id:
	    transaction['customerProfileId'] = \
		voucher.partner_id.customer_profile_id

	if voucher.payment_profile:
	    transaction['customerPaymentProfileId'] = voucher.payment_profile.profile

        #Not Implemented
#       if voucher.tax_line:
#           transaction['tax'] = self.prepare_transaction_taxes(
#               cr, uid, voucher.tax_line
#           )

        return transaction


    def prepare_transaction_tax_vals(self, cr, uid, tax_lines, context=None):
	taxes = {}
#	for tax in taxes:
	    

	#Not Implemented
#	if voucher.tax_line:
#	    transaction['tax'] = self.prepare_transaction_taxes(
#		cr, uid, voucher.tax_line
#	    )		

	return taxes


    def capture_prior_auth_transaction(self, cr, uid, auth, client, \
		object, voucher, trans_vals
	):

	trans_vals['transId'] = voucher.transaction_id
	if round(voucher.amount, 2) > round(voucher.preauthorized_amount, 2):
	    trans_vals['amount'] = round(voucher.preauthorized_amount, 2)

	object.transaction = {'profileTransPriorAuthCapture': trans_vals}

	try:
	    response = client.service.CreateCustomerProfileTransaction(auth, object.transaction)
	    print 'SENT', client.last_sent()
	except Exception, e:
	    response = str(e)

	return self.process_authnet_response(cr, uid, response)


    def capture_transaction(self, cr, uid, auth, client, voucher):

	#We must create a brand new transaction
	object = client.factory.create('CreateCustomerProfileTransaction')
	trans_vals = self.create_transaction_vals(cr, uid, voucher)
	trans_vals['amount'] = round(voucher.amount, 2) - round(voucher.preauthorized_amount, 2)

	trans_vals['approvalCode'] = voucher.authorization_code

	object.transaction = {'profileTransCaptureOnly': trans_vals}

	try:
            response = client.service.CreateCustomerProfileTransaction(auth, object.transaction)
	    print 'SENT', client.last_sent()
	except Exception, e:
	    response = str(e)

	return self.process_authnet_response(cr, uid, response)


    #Please help me improve this. Currently I dont know how to parse crap suds response
    #I know the try except, and parsing here and other places is not good
    #I want to ensure there is no uncaptured error when dealing with money
    #So I over ensure that we know exactly what happened and tell the user
    def process_authnet_response(self, cr, uid, response):
	message = False

	if not response:
	    message = 'Generic Error 1. No Response'

	try:
	    code = response.resultCode

	except Exception, e:
	    message = 'Could not get Response Code for: ' + str(response)
	    raise osv.except_osv(_('Gateway Error'), _(message))

	if code == 'Ok':
	    return True

	elif code == 'Error':
	    try:
		messages = response.messages
	    except Exception, e:
		message = 'Response and code but no message for: ' + str(response)

	    for error in messages:
		try:
		    message = str(error[1][0].code) + ' ' + str(error[1][0].text)
		except Exception, e:
		    message = 'Couldnt Parse Message: ' + str(error)

		break

	else:
	    message = 'Unexpected Response Code: ' + str(response)


	if message:
	    raise osv.except_osv(_('Gateway Error'), _(message))

	print 'DEBUG', response
	return True


    def authorize_transaction(self, cr, uid, auth, client, object, trans_vals):
	print 'Call Authorize only'
	object.transaction = {'profileTransAuthOnly': trans_vals}
	try:
	    response = client.service.CreateCustomerProfileTransaction(auth, object.transaction)
	except Exception, e:
	    response = str(e)
	return self.process_authnet_response(cr, uid, response)


    def authorize_and_capture_transaction(self, cr, uid, auth, client, \
		object, trans_vals, customer_data=False):

	if customer_data:
	    trans_vals['customerProfileId'] = customer_data['customer_profile_id']
	    trans_vals['customerPaymentProfileId'] = customer_data['payment_profile']

	object.transaction = {'profileTransAuthCapture': trans_vals}

	try:
	    response = client.service.CreateCustomerProfileTransaction(auth, object.transaction)
	    print 'SENT', client.last_sent()
	except Exception, e:
	    response = str(e)

	return self.process_authnet_response(cr, uid, response)


    def refund_transaction(self, cr, uid, auth, client, object, trans_vals):
	print 'Calling Refund'
	trans_vals['transId'] = voucher.transaction_id
	object.transaction = {'profileTransRefund': trans_vals}

	try:
	    response = client.service.CreateCustomerProfileTransaction(auth, object.transaction)
	    print 'SENT', client.last_sent()
	except Exception, e:
	    response = str(e)

	return self.process_authnet_response(cr, uid, response)


    def void_transaction(self, cr, uid, auth, client, object, trans_vals):
	trans_vals['transId'] = voucher.transaction_id
	object.transaction = {'profileTransVoid': trans_vals}

	try:
	    response = client.service.CreateCustomerProfileTransaction(auth, object.transaction)
	    print 'SENT', client.last_sent()
	except Exception, e:
	    response = str(e)

	return self.process_authnet_response(cr, uid, response)


    def handle_duplicate_record_response(self, cr, uid, vals, record_id):
        return True


    def prepare_and_create_payment_profile(self, cr, uid, auth, client, voucher):
	print 'Creating Customer/Payment Profile'
	vals = self.prepare_payment_profile(cr, uid, client, voucher)

	try:
	    response = self.create_payment_profile(cr, uid, auth, client, vals)
	    print 'SENT', client.last_sent()
	    print 'RESPONSE', response
	except Exception, e:
	    response = str(e)

	#Check the response to ensure no error happened
	self.process_authnet_response(cr, uid, response)

	print 'PAYMENT RESULT', response
	for id in response.customerPaymentProfileIdList:
	    payment_id = id[1][0]
	    break

	card_hidden = voucher.card_number[-5:]

	vals = {
		'partner': voucher.partner_id.id,
		'expiration_date': voucher.expiration_date,
		'card_type': 'visa',
		'payment_type': 'creditcard',
		'profile': payment_id,
		'card_number': card_hidden
	}

	self.pool.get('res.partner').write(cr, uid, voucher.partner_id.id, \
		{'customer_profile_id': response.customerProfileId})

	odoo_payment_id = self.create_odoo_payment_profile(cr, uid, vals)
	return {'payment_profile': payment_id, 
		'odoo_payment_id': odoo_payment_id,
		'customer_profile_id': response.customerProfileId,
		'card_number': card_hidden,
	}


    def create_odoo_payment_profile(self, cr, uid, vals):
	profile_obj = self.pool.get('payment.profile')
	profile_id = profile_obj.create(cr, uid, vals)
	return profile_id
	

    def prepare_payment_profile(self, cr, uid, client, voucher):
	address = voucher.billing_address
	partner = voucher.partner_id
	object = client.factory.create('CreateCustomerProfile')
	if voucher.partner_id.customer_profile_id:
	    print 'Only Creating new Payment Profile'
	else:
	    print 'Creating Customer and Payment Profile'

	#Some sloppy solution due to sloppy decision to remove firstname/lastname fields
	if not partner.firstname:
	    firstname = partner.name.split(' ')[0]
	else:
	    firstname = partner.firstname

	billTo = {
	    'firstName': firstname,
	    'lastName': partner.lastname or firstname,
	    'address': address.street,
	    'city': address.city,
	    'state': address.state_id.name,
	    'zip': address.zip,
	    'country': address.country_id.code,
	    'phoneNumber': address.phone or '9999999999',
	}

	creditCard = {
	    'cardNumber': voucher.card_number,
	    'expirationDate': voucher.expiration_date,
	    'cardCode': voucher.cvv_code,
	}

	data = {'customerType': 'individual',
	'billTo': billTo,
	'payment': {'creditCard': creditCard}
	}

        object.profile.paymentProfiles.CustomerPaymentProfileType.append(data)
	#Do some sequence?
	object.profile.merchantCustomerId = 'OD_' + str(address.id)

	return object


    def create_payment_profile(self, cr, uid, auth, client, object):
	return client.service.CreateCustomerProfile(auth, object.profile, 'none')
