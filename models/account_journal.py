from openerp.osv import osv, fields


class AccountJournal(osv.osv):
    _inherit = 'account.journal'
    _columns = {
	'cc_journal': fields.boolean('Credit Card Journal'),
    }
