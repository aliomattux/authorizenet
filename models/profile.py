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
            if record['card_number']:
                name = name+'/'+record['card_number']
            res.append((record['id'], name))
        return res


    _columns = {
	'partner': fields.many2one('res.partner', 'Name', domain="[('parent_id', '=', False)]"),
	'profile': fields.integer('Profile ID'),
	'payment_type': fields.selection([
			('creditcard', 'Credit Card'),
			('bank', 'Bank Account'),
	], 'Payment Type'),
	'card_number': fields.char('Card Number'),
	'card_type': fields.selection([
			('amex', 'American Express'),
			('visa', 'Visa'),
			('mc', 'Master Card'),
			('disc', 'Discover Card'),
	], 'Card Type'),
	'expiration_date': fields.char('Expiration Date'),
    }

