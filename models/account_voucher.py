from openerp.osv import osv, fields
from openerp.tools.translate import _


class AccountVoucher(osv.osv):
    _inherit = 'account.voucher'
    _columns = {
	'invoice': fields.many2one('account.invoice', 'Invoice'),
	'cc_view_enable': fields.boolean('Hidden Field Enables/Disables Credit Card View'),
	'preauthorized_amount': fields.float('Preauthorized Amount'),
	'authorization_code': fields.char('Authorization Code'),
	'billing_address': fields.many2one('res.partner', 'Billing Address', \
		domain="[('parent_id', '=', partner_id)]"
	),
	'transaction_id': fields.char('Authorize.net Transaction ID'),
	'payment_profile': fields.many2one('payment.profile', 'Payment Profile', \
		domain="[('partner', '=', partner_id)]"
	),
	'card_number': fields.char('Card Number'),
        'expiration_date': fields.char('Expiration Date'),
	'cvv_code': fields.char('CVV Code'),
    }



    def action_move_line_create(self, cr, uid, ids, context=None):
	#Process the voucher first. If there is an error here we can easily rollback
	#If we process the external payment and encounter a voucher problem
	#we cannot rollback the payment
	res = super(AccountVoucher, self).action_move_line_create(cr, uid, ids, context)
	processor_obj = self.pool.get('authorizenet.api')
	voucher = self.browse(cr, uid, ids[0])
	journal = voucher.journal_id

	#If this payment requires an external api call (Credit Card Capture)
	if journal.cc_journal:
	    processor_obj.upsert_external_payment_transaction(cr, uid, voucher, journal)	    


	return res


    def onchange_payment_profile(self, cr, uid, ids, profile_id, context=None):
	vals = {
		'card_number': False,
		'expiration_date': False,
		'cvv_code': False,
	}
        if profile_id:
	    profile = self.pool.get('payment.profile').browse(cr, uid, profile_id)
	    vals.update({
                'card_number': profile.card_number,
                'expiration_date': profile.expiration_date,
	    })

	return {'value': vals}


    #This method is overridden instead of calling super to reduce the amount of sql queries performed in an already slow design
    def onchange_journal(self, cr, uid, ids, journal_id, line_ids, tax_id, partner_id, date, amount, ttype, company_id, context=None):
        if context is None:
            context = {}
        if not journal_id:
            return False
        journal_pool = self.pool.get('account.journal')
        journal = journal_pool.browse(cr, uid, journal_id, context=context)
        account_id = journal.default_credit_account_id or journal.default_debit_account_id
        tax_id = False
        if account_id and account_id.tax_ids:
            tax_id = account_id.tax_ids[0].id

        vals = {'value':{} }
        if ttype in ('sale', 'purchase'):
            vals = self.onchange_price(cr, uid, ids, line_ids, tax_id, partner_id, context)
            vals['value'].update({'tax_id':tax_id,'amount': amount})
        currency_id = False
        if journal.currency:
            currency_id = journal.currency.id
        else:
            currency_id = journal.company_id.currency_id.id
        vals['value'].update({'currency_id': currency_id})
        #in case we want to register the payment directly from an invoice, it's confusing to allow to switch the journal
        #without seeing that the amount is expressed in the journal currency, and not in the invoice currency. So to avoid
        #this common mistake, we simply reset the amount to 0 if the currency is not the invoice currency.
        if context.get('payment_expected_currency') and currency_id != context.get('payment_expected_currency'):
            vals['value']['amount'] = 0
            amount = 0
        if partner_id:
            res = self.onchange_partner_id(cr, uid, ids, partner_id, journal_id, amount, currency_id, ttype, date, context)
            for key in res.keys():
                vals[key].update(res[key])


	#####  CC Functionality  ########

	if journal.cc_journal:
	    vals['value']['cc_view_enable'] = True
	else:
	    vals['value']['cc_view_enable'] = False

        return vals