from openerp.osv import osv, fields

class PaymentProfile(osv.osv):
    _name = 'payment.profile'
    _rec_name = 'card_number'


    def name_get(self, cr, uid, ids, context=None):
        if isinstance(ids, (list, tuple)) and not len(ids):
            return []
        if isinstance(ids, (long, int)):
            ids = [ids]
        reads = self.read(cr, uid, ids, ['card_type','card_number'], context=context)
        res = []
        for record in reads:
            name = record['card_type']
	    #If card type is blank
	    if not name:
		name = 'None'

            if record['card_number']:
                name = name+'/'+record['card_number']
            res.append((record['id'], name))
        return res


    _columns = {
	'partner': fields.many2one('res.partner', 'Name', domain="[('parent_id', '=', False)]"),
        'customer_profile_id': fields.integer('Customer Profile ID', copy=False),
        'profile_description': fields.char('Profile Description', copy=False),
        'customer_id': fields.integer('Customer ID', copy=False),
	'profile': fields.integer('Profile ID', copy=False),
	'payment_type': fields.selection([
			('creditcard', 'Credit Card'),
			('bank', 'Bank Account'),
	], 'Payment Type'),
	'card_number': fields.char('Card Number', copy=False),
	'card_type': fields.selection([
			('amex', 'American Express'),
			('visa', 'Visa'),
			('mc', 'Master Card'),
			('disc', 'Discover Card'),
	], 'Card Type'),
	'expiration_date': fields.char('Expiration Date'),
    }


