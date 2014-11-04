from openerp.osv import osv, fields


class StockPicking(osv.osv):
    _inherit = 'stock.picking'
 

    def action_invoice_create(self, cr, uid, ids, journal_id, group=False, \
	type='out_invoice', context=None
	):

        invoices = super(StockPicking, self).action_invoice_create(cr, uid, ids, journal_id, \
                group=False, type='out_invoice', context=None
        )

        print 'INVOICES', invoices

	return invoices
