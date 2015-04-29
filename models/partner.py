from openerp.osv import osv, fields
#Why would OpenERP remove firstname and lastname fields? There are so many reasons to have these
#But to me it makes sense to make an idiotic decision, because thats what ive learned to expect from OpenERP

class ResPartner(osv.osv):
    _inherit = 'res.partner'
    _columns = {
	'id': fields.integer('ID'),
        'firstname': fields.char('Firstname'),
        'lastname': fields.char('Lastname'),
        'payment_profiles': fields.one2many('payment.profile', 'partner', 'Payment Profiles'),
    }


