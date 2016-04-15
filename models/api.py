from openerp.osv import osv, fields
from openerp.tools.translate import _
from datetime import datetime
from suds.client import Client
from pprint import pprint as pp

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
	    already_captured = False
	    capture_complete = False
	    #If the sale order contains pre-authorizations
	    if voucher.invoice.sale_order.authorizations:
	        total_amount_due = round(voucher.amount, 2)
		captured_authorization = False
		for authorization in voucher.invoice.sale_order.authorizations:
		    amount_to_process = round(authorization.amount, 2)
		    if authorization.auth_status != 'auth':
			if authorization.auth_status == 'capture':
			    total_amount_due -= amount_to_process
			    captured_authorization = authorization
			continue

		    #Determine if the next authorization will exceed the remaining amount due
		    remaining_amount = total_amount_due - amount_to_process
		    if round(remaining_amount, 2) <= 0:
			amount_to_process = total_amount_due
			capture_complete = True

		    else:
			print 'Did not Trigger Voucher Amount', amount_to_process


                    self.capture_multiple_prior_auth_transaction(cr, uid, auth, client, \
                        object, voucher, transaction, authorization, amount_to_process
                    )

		    #Update the authorization state to captured
		    authorization.auth_status = 'capture'
		    captured_authorization = authorization
		    total_amount_due -= amount_to_process
		    if round(total_amount_due, 2) <= 0:
			break

	        if not capture_complete and round(total_amount_due, 2) > 0 and voucher.payment_profile:
                    self.capture_transaction(cr, uid, auth, client, voucher, total_amount_due, captured_authorization)

	    #If the voucher has a pre-authorization
	    elif voucher.authorization_code:
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
		    self.authorize_and_capture_transaction(cr, uid, auth, client, object, voucher, transaction)

		else:
		    raise osv.except_osv(_('System Error'), _("You should not be able to get this far"))
		    profile_info = self.prepare_and_create_payment_profile(cr, uid, \
			auth, client, voucher
		    )

		    self.authorize_and_capture_transaction(cr, uid, auth,\
			 client, object, transaction, profile_info
		    )

	#Process a refund
	#When you refund a payment you must refund an exisitng paid transaction
	#This might not be in context when the user presses refund, or there may be multiple authorizations
	#That need to be refunded individually
	elif voucher.invoice.type == 'out_refund':
	    self.find_and_process_refund_vouchers(cr, uid, auth, client, \
		voucher, object, transaction
	    )

	else:
	    print 'Unexpected Invoice Type'
	    #What happens here?
	    raise

	return True


    def create_transaction_vals(self, cr, uid, object, context=None):
	""" In order to call this method your object must contain the fields
	    amount and payment_profile (payment.profile)
	"""
        transaction = {
                        'amount': round(object.amount, 2),
        }

	transaction['customerProfileId'] = \
		object.payment_profile.customer_profile_id

	transaction['customerPaymentProfileId'] = object.payment_profile.profile

        #Not Implemented
#       if voucher.tax_line:
#           transaction['tax'] = self.prepare_transaction_taxes(
#               cr, uid, voucher.tax_line
#           )

        return transaction


    def find_and_process_refund_vouchers(self, cr, uid, auth, client, voucher, object, transaction):
	refund_amount = voucher.amount
	if voucher.invoice.sale_order.authorizations:
	    total_refund_amount = voucher.amount
	    b = False
	    for authorization in voucher.invoice.sale_order.authorizations:
		if authorization.auth_status != 'capture':
		    continue
		amount_to_refund = authorization.amount
		remaining_amount = total_refund_amount - amount_to_refund
		if remaining_amount < 0:
		    b = True
		    amount_to_refund = total_refund_amount

		transaction['transId'] = authorization.transaction_id
		transaction['amount'] = amount_to_refund
		self.refund_transaction(cr, uid, auth, client, False, voucher, object, transaction, authorization=authorization)
		total_refund_amount -= amount_to_refund
		authorization.auth_status = 'refund'
		if b:
		    break
	    if not b:
		raise osv.except_osv(_('System Error'), _("Your refund will not be processed in Authorize.net because no payments could be found to refund."))
	else:
	    eligible_refund_vouchers = self.find_eligible_refund_vouchers(cr, uid, voucher)

	    if not eligible_refund_vouchers:
	        raise osv.except_osv(_('User Error'), _('You are trying to process a refund but there are no eligible payments to refund. Please manually refund this transaction in Authorize.net'))

	    done = False
	    for eligible_voucher in self.pool.get('account.voucher').browse(cr, uid, eligible_refund_vouchers):

	        transaction['transId'] = eligible_voucher.transaction_id

	        if round(refund_amount, 2) > round(eligible_voucher.amount, 2):
		    transaction['amount'] = round(eligible_voucher.amount, 2)
		    refund_amount -= round(eligible_voucher.amount, 2)

	        else:
		    transaction['amount'] = round(refund_amount, 2)
		    done = True

	        self.refund_transaction(cr, uid, auth, client, eligible_voucher, voucher, object, transaction)

	        if done:
		    break

	return True


    def find_eligible_refund_vouchers(self, cr, uid, voucher, context=None):
        sale = self.find_sale_reference(cr, uid, voucher)
	voucher_obj = self.pool.get('account.voucher')
	if not sale:
	    raise osv.except_osv(_('User Error'), _('You are trying to process a refund but there is no sale attached to this invoice for which a refund can be made'))

	checkable_vouchers = []
        for invoice in sale.invoice_ids:
	    if invoice.type != 'out_invoice' or invoice.state == 'draft':
		continue

            voucher_ids = voucher_obj.search(cr, uid, [
                       ('state', '=', 'posted'),
                       ('type', '=', 'receipt'),
                       ('invoice', '=', invoice.id),
		       ('transaction_id', '!=', False),
            ])
	    #There is not a valid 'not in' operator in the ORM. If you have a boolean field
	    #That contains at least 1 null, you cannot use a domain because all results
	    #Will be null. The only solution is to use not in.
	    for v in voucher_obj.browse(cr, uid, voucher_ids):
		if v.refunded:
		    voucher_ids.remove(v.id)
		else:
		    v.refunded = True

	    checkable_vouchers.extend(voucher_ids)

        if checkable_vouchers:
	    #Check that the total amount is at least enough to satisfy the refund request
	    query = "SELECT SUM(amount) FROM account_voucher WHERE id "
	    if len(checkable_vouchers) > 1:
	        query += "IN %s" % (tuple(checkable_vouchers,))
	    else:
		query += "= %s" % checkable_vouchers[0]

	    cr.execute(query)
	    number = cr.fetchone()[0]
	    if round(voucher.amount,2) > round(float(number),2):
		raise osv.except_osv(_('User Error'), _('The refund amount is greater than the amount already charged. You must refund this transaction manually in Authorize.net'))

	    return checkable_vouchers


    def find_sale_reference(self, cr, uid, voucher, context=None):
	if voucher.invoice.sale_order:
	    return voucher.invoice.sale_order

	return False


    def prepare_transaction_tax_vals(self, cr, uid, tax_lines, context=None):
	taxes = {}
#	for tax in taxes:


	#Not Implemented
#	if voucher.tax_line:
#	    transaction['tax'] = self.prepare_transaction_taxes(
#		cr, uid, voucher.tax_line
#	    )

	return taxes


    def capture_multiple_prior_auth_transaction(self, cr, uid, auth, client, \
                object, voucher, trans_vals, authorization, amount_to_process
        ):

	#TODO: Review
        trans_vals['transId'] = authorization.transaction_id
        trans_vals['amount'] = round(amount_to_process, 2)
	pp(trans_vals)
        object.transaction = {'profileTransPriorAuthCapture': trans_vals}

        try:
            response = client.service.CreateCustomerProfileTransaction(auth, object.transaction)
#           print 'SENT', client.last_sent()
        except Exception, e:
            response = str(e)

        return self.process_authnet_response(cr, uid, response)


    #This method to become deprecated
    def capture_prior_auth_transaction(self, cr, uid, auth, client, \
		object, voucher, trans_vals
	):

	trans_vals['transId'] = voucher.transaction_id
	if round(voucher.amount, 2) > round(voucher.preauthorized_amount, 2):
	    trans_vals['amount'] = round(voucher.preauthorized_amount, 2)

	object.transaction = {'profileTransPriorAuthCapture': trans_vals}

	try:
	    response = client.service.CreateCustomerProfileTransaction(auth, object.transaction)
#	    print 'SENT', client.last_sent()
	except Exception, e:
	    response = str(e)

	return self.process_authnet_response(cr, uid, response)


    def capture_transaction(self, cr, uid, auth, client, voucher, amount, authorization):

	voucher_obj = self.pool.get('account.voucher')
	#We must create a brand new transaction
	object = client.factory.create('CreateCustomerProfileTransaction')
	trans_vals = self.create_transaction_vals(cr, uid, voucher)
	trans_vals['amount'] = amount

	trans_vals['approvalCode'] = authorization.authorization_code
	object.transaction = {'profileTransCaptureOnly': trans_vals}

	try:
            response = client.service.CreateCustomerProfileTransaction(auth, object.transaction)
#	    print 'SENT', client.last_sent()
	except Exception, e:
	    response = str(e)

	#Check if any error is raised
	self.process_authnet_response(cr, uid, response)

	#Get the new transaction id and amount so it can be used later if a refund is required
	try:
	    capture_details = response.directResponse
	    details = capture_details.split(',')
	    capture_transaction_id = details[6]
	    voucher_obj.write(cr, uid, voucher.id, {'capture_transaction_id': capture_transaction_id,
					'capture_addl_amount': amount,
	    })
	except Exception, e:
	    pass

	return True


    #Please help me improve this. Currently I dont know how to parse crap suds response
    #I know the try except, and parsing here and other places is not good
    #I want to ensure there is no uncaptured error when dealing with money
    #So I over ensure that we know exactly what happened and tell the user
    def process_authnet_response(self, cr, uid, response, void=False):
	message = False

	if not response:
	    message = 'Generic Error 1. No Response'

	try:
	    code = response.resultCode

	except Exception, e:
	    message = 'Could not get Response Code for: ' + str(response)
	    if void:
		return False
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
	    if message and not void:
	        raise osv.except_osv(_('Gateway Error'), _(message))
	    if message and void:
		return False
#	print 'DEBUG', response
	return True



    def authorize_and_capture_transaction(self, cr, uid, auth, client, \
		object, voucher, trans_vals, customer_data=False):

	if customer_data:
	    trans_vals['customerProfileId'] = customer_data['customer_profile_id']
	    trans_vals['customerPaymentProfileId'] = customer_data['payment_profile']

	object.transaction = {'profileTransAuthCapture': trans_vals}

	try:
	    response = client.service.CreateCustomerProfileTransaction(auth, object.transaction)
#	    print 'SENT', client.last_sent()
	except Exception, e:
	    response = str(e)

	#Check the response for errors
	self.process_authnet_response(cr, uid, response)

        #Get the new transaction id and amount so it can be used later if a refund is required
        try:
            capture_details = response.directResponse
            details = capture_details.split(',')
            transaction_id = details[6]
            voucher_obj.write(cr, uid, voucher.id, {'transaction_id': transaction_id
            })
        except Exception, e:
            pass

	return True


    def refund_transaction(self, cr, uid, auth, client, original_voucher, voucher, object, trans_vals, authorization=False):

	#TODO: Verify functionality. does amount need to be negative?
	if not original_voucher and authorization:
	    self.send_refund_transaction(cr, uid, auth, client, object, original_voucher, authorization, trans_vals)
	    return True

	#If the voucher being refunded contains multiple transactions
	if original_voucher.capture_transaction_id:
	    capture_vals = trans_vals

	    refund_total = trans_vals['amount'] * -1
	    charge_amount = round(original_voucher.amount, 2) - round(original_voucher.capture_addl_amount, 2)
	    capture_amount = round(original_voucher.capture_addl_amount, 2)

	    #The refund amount is greater than the additional capture amount
	    #In this case we need to do 2 calls. Refund the original charge
	    #And the extra charge we captured
	    if refund_total > capture_amount:
		capture_vals['amount'] = capture_amount
	        capture_vals['transId'] = original_voucher.capture_transaction_id
	        self.send_refund_transaction(cr, uid, auth, client, object, original_voucher, original_voucher, capture_vals)

		#Once we refund the captured amount, refund the original charge - captured amount.
		trans_vals['amount'] = refund_total - capture_amount
		self.send_refund_transaction(cr, uid, auth, client, object, original_voucher, original_voucher, trans_vals)
		return True

	    #The additional captured amount is less or equal to the amount required for refund
	    else:
		capture_vals['transId'] = original_voucher.capture_transaction_id
		self.send_refund_transaction(cr, uid, auth, client, object, original_voucher, original_voucher, capture_vals)
		return True

	#There is no additional captures on the voucher
	else:
	    self.send_refund_transaction(cr, uid, auth, client, object, original_voucher, original_voucher, trans_vals)


    def send_refund_transaction(self, cr, uid, auth, client, object, original_voucher, multi_object, vals):
	if vals['amount'] < 0.1:
	    vals['amount'] = vals['amount'] * -1
	voucher_date = multi_object.create_date.split('-')
	now = datetime.utcnow().strftime('%Y-%m-%d')
	month = voucher_date[1]
	day = voucher_date[2].split(' ')[0]
	#If the transaction was created before settlement it needs to be voided
	if now.split('-')[-2:] == [month, day]:
	    return self.void_transaction(cr, uid, auth, client, object, vals)

	pp(vals)
	if original_voucher and original_voucher.invoice:
	    ref = original_voucher.invoice.number
	    if len(ref) > 20:
		ref = ref[0:20]
		object.refId = ref

	object.transaction = {'profileTransRefund': vals}

	try:
	    response = client.service.CreateCustomerProfileTransaction(auth, object.transaction)
	except Exception, e:
	    response = str(e)

	refunded = self.process_authnet_response(cr, uid, response, void=True)
	if not refunded:
	    return self.void_transaction(cr, uid, auth, client, object, vals)


    def void_transaction(self, cr, uid, auth, client, object, trans_vals):
	#If this is a void, we dont send amount
	del trans_vals['amount']

	object.transaction = {'profileTransVoid': trans_vals}

	try:
	    response = client.service.CreateCustomerProfileTransaction(auth, object.transaction)
	except Exception, e:
	    response = str(e)
	pp(response)
	return self.process_authnet_response(cr, uid, response)


    def handle_duplicate_record_response(self, cr, uid, vals, record_id):
        return True


    #This function deprecated pending removal
    def prepare_and_create_payment_profile_deprecated(self, cr, uid, auth, client, voucher):
	vals = self.prepare_voucher_payment_profile(cr, uid, client, voucher)

	try:
	    response = self.create_payment_profile(cr, uid, auth, client, vals)
#	    print 'RESPONSE', response
	except Exception, e:
	    response = str(e)

	#Check the response to ensure no error happened
	self.process_authnet_response(cr, uid, response)

	for id in response.customerPaymentProfileIdList:
	    payment_id = id[1][0]
	    break

	card_hidden = voucher.card_number[-5:]

	vals = {
		'partner': voucher.partner_id.id,
		'expiration_date': voucher.expiration_date,
		'card_type': 'visa',
		'customer_profile_id': response.customerProfileId,
		'payment_type': 'creditcard',
		'profile': payment_id,
		'card_number': card_hidden
	}

	#TODO: This does not work
#	self.pool.get('res.partner').write(cr, uid, voucher.partner_id.id, \
#		{'customer_profile_id': response.customerProfileId})

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


    def prepare_voucher_payment_profile(self, cr, uid, client, voucher):
	address = voucher.billing_address
	partner = voucher.partner_id
	object = client.factory.create('CreateCustomerProfile')
#	if voucher.partner_id.customer_profile_id:
#	    print 'Only Creating new Payment Profile'
#	else:
#	    print 'Creating Customer and Payment Profile'

	billTo = self.prepare_payment_profile_address(cr, uid, partner, address)

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
	next_number = self.pool.get('ir.sequence').get(cr, uid, 'payment.profile.seq')
	object.profile.merchantCustomerId = 'OD_' + next_number

	return object


    def prepare_payment_profile_address(self, cr, uid, partner, address):
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
            'state': address.state_id.name or None,
            'zip': address.zip,
            'country': address.country_id.code,
            'phoneNumber': address.phone or '9999999999',
        }

	return billTo


    def create_payment_profile(self, cr, uid, auth, client, object):
	return client.service.CreateCustomerProfile(auth, object.profile, 'none')
