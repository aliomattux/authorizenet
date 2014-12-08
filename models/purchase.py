from openerp.osv import osv, fields


class PurchaseOrder(osv.osv):
    _inherit = 'purchase.order'

    def action_invoice_create(self, cr, uid, ids, context=None):
	if not context:
	    context = {}
        invoice_id = super(PurchaseOrder, self).action_invoice_create(cr, uid, ids, context)

        if type(invoice_id) != list and len(ids) == 1:
            invoice = self.pool.get('account.invoice').browse(cr, uid, invoice_id)
            invoice.purchase_order = ids[0]


        return invoice_id
