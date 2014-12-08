from openerp.osv import osv, fields

class ResPartner(osv.osv):
    _inherit = 'res.partner'
    _columns = {
	'id': fields.integer('ID'),
        'customer_profile_id': fields.integer('Customer Profile ID'),
        'profile_description': fields.char('Profile Description'),
        'customer_id': fields.integer('Customer ID'),
        'payment_profiles': fields.one2many('payment.profile', 'partner', 'Payment Profiles'),
    }

