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

    def name_get(self, cr, uid, ids, context=None):
        if context is None:
            context = {}
        if isinstance(ids, (int, long)):
            ids = [ids]
        res = []
        for record in self.browse(cr, uid, ids, context=context):
            name = record.name
            if record.parent_id and not record.is_company:
                name =  "%s, %s" % (record.parent_id.name, name)
            if context.get('show_address_only'):
		name = self._display_address(cr, uid, record, without_company=True, context=context)
            if context.get('show_address'):
		name = name + "\n" + self._display_address(cr, uid, record, without_company=True, context=context)

	    if context.get('creditcard_address'):
		name = "%s, %s" % (record.name, record.street or record.name)

            name = name.replace('\n\n','\n')
            name = name.replace('\n\n','\n')
            if context.get('show_email') and record.email:
                name = "%s <%s>" % (name, record.email)
            res.append((record.id, name))
        return res
