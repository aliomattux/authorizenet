from openerp.osv import osv, fields

class PaymentMethod(osv.osv):
    _inherit = 'payment.method'
    _columns = {
	'authnet_method': fields.boolean('Authorize.net Payment Method'),
	'mc_journal': fields.many2one('account.journal', 'Mastercard Journal', domain="[('cc_journal', '=', True)]"),
	'amex_journal': fields.many2one('account.journal', 'American Express Journal', domain="[('cc_journal', '=', True)]"),
	'visa_journal': fields.many2one('account.journal', 'Visa Journal', domain="[('cc_journal', '=', True)]"),
	'disc_journal': fields.many2one('account.journal', 'Discovercard Journal', domain="[('cc_journal', '=', True)]"),
    }
