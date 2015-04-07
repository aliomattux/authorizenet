from openerp.osv import osv, fields

class AuthorizeConfig(osv.osv):
    _name = 'authorize.config'
    _rec_name = 'merchant_id'
    _columns = {
	'active': fields.boolean('Active'),
	'gateway_mode': fields.selection([
		('test', 'Test Mode'),
		('live', 'Production Mode'),
	], 'Gateway Mode'),
        'validation_mode': fields.selection([
                ('testMode', 'Test Mode'),
                ('liveMode', 'Live Mode'),
		('none', 'No Validation'),
        ], 'Validation Mode'),
	'merchant_id': fields.char('Merchant ID'),
	'transaction_key': fields.char('Transaction Key'),
    }

    _defaults = {
	'active': True,
    }
