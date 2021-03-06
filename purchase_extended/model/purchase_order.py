# -*- coding: utf-8 -*-

from openerp.osv import fields, orm
from openerp import netsvc
from openerp.tools.translate import _
from openerp import SUPERUSER_ID


class PurchaseOrder(orm.Model):
    _inherit = "purchase.order"

    STATE_SELECTION = [
        ('draft', 'Draft RFQ'),
        ('sent', 'RFQ Sent'),
        ('draftbid', 'Draft Bid'),  # added
        ('bid', 'Bid Encoded'),  # Bid Received renamed into Bid Encoded
        ('bid_selected', 'Bid selected'), # added
        ('draftpo', 'Draft PO'),  # added
        ('confirmed', 'Waiting Approval'),
        ('approved', 'Purchase Confirmed'),
        ('except_picking', 'Shipping Exception'),
        ('except_invoice', 'Invoice Exception'),
        ('done', 'Done'),
        ('cancel', 'Canceled')
    ]
    TYPE_SELECTION = [
        ('rfq', 'Request for Quotation'),
        ('bid', 'Bid'),
        ('purchase', 'Purchase Order')
    ]

    _columns = {
        'state': fields.selection(STATE_SELECTION, 'Status', readonly=True, select=True,
            help="The status of the purchase order or the quotation request. A "
                 "quotation is a purchase order in a 'Draft' status. Then the order "
                 "has to be confirmed by the user, the status switch to 'Confirmed'. "
                 "Then the supplier must confirm the order to change the status to "
                 "'Approved'. When the purchase order is paid and received, the "
                 "status becomes 'Done'. If a cancel action occurs in the invoice or "
                 "in the reception of goods, the status becomes in exception."),
        'type': fields.selection(TYPE_SELECTION, 'Type', required=True, readonly=True),
        'consignee_id': fields.many2one('res.partner', 'Consignee', help="the person to whom the shipment is to be delivered"),
        'incoterm_address': fields.char(
            'Incoterms Place',
            help="Incoterms Place of Delivery. "
                 "International Commercial Terms are a series of "
                 "predefined commercial terms used in "
                 "international transactions."),
        'cancel_reason_id': fields.many2one('purchase.cancelreason', 'Reason for Cancellation', readonly=True),
    }
    _defaults = {
        'state': lambda self, cr, uid, context: 'draftpo' if context.get('draft_po')
                                          else 'draftbid' if context.get('draft_bid')
                                          else 'draft',
        'type': lambda self, cr, uid, context: 'purchase' if context.get('draft_po')
                                          else 'bid' if context.get('draft_bid')
                                          else 'rfq',
    }

    def create(self, cr, uid, vals, context=None):
        # Document can be created as Draft RFQ or Draft PO. We need to log the right message.
        if context is None:
            context = {}
        description = self._description
        if context.get('draft_bid'):
            self._description = 'Draft Bid'
        elif not context.get('draft_po'):
            self._description = 'Request for Quotation'
        id = super(PurchaseOrder, self).create(cr, uid, vals, context=context)
        self._description = description
        if context.get('draft_bid'):
            wf_service = netsvc.LocalService("workflow")
            wf_service.trg_validate(uid, 'purchase.order', id, 'draft_bid', cr)
        if context.get('draft_po'):
            wf_service = netsvc.LocalService("workflow")
            wf_service.trg_validate(uid, 'purchase.order', id, 'draft_po', cr)
        return id

    def copy(self, cr, uid, id, default=None, context=None):
        newid = super(PurchaseOrder, self).copy(cr, uid, id, default=default, context=context)
        po = self.read(cr, SUPERUSER_ID, newid, ['type', 'order_line'], context=context, load='_classic_write')
        if po['type'] == 'rfq' and po['order_line']:
            self.pool.get('purchase.order.line').write(cr, SUPERUSER_ID, po['order_line'], {'price_unit': 0}, context=context)
        return newid

    def wkf_draft_po(self, cr, uid, ids, context=None):
        self.message_post(cr, uid, ids, body=_("Converted to draft Purchase Order"), subtype="mail.mt_comment", context=context)
        return self.write(cr, uid, ids, {'state': 'draftpo', 'type': 'purchase'}, context=context)

    def action_cancel(self, cr, uid, ids, context=None):
        """ Ask a cancel reason
        """
        if context is None:
            context = {}
        context['action'] = 'action_cancel_ok'
        view_id = self.pool.get('ir.model.data').get_object_reference(cr, SUPERUSER_ID, 'purchase_extended', 'action_modal_cancel_reason')[1]
        #TODO: filter based on po type
        return {
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'purchase.action_modal_cancelreason',
            'view_id': view_id,
            'views': [(view_id, 'form')],
            'target': 'new',
            'context': context,
        }

    def action_cancel_no_reason(self, cr, uid, ids, context=None):
        return super(PurchaseOrder, self).action_cancel(cr, uid, ids,
                                                        context=context)

    def action_cancel_ok(self, cr, uid, ids, context=None):
        reason_id = self.pool.get('purchase.action_modal_cancelreason').read(cr, uid,
                                context['active_id'], ['reason_id'], context=context,
                                load='_classic_write')['reason_id']
        self.write(cr, uid, ids, {'cancel_reason_id': reason_id}, context=context)
        return super(PurchaseOrder, self).action_cancel(cr, uid, ids, context=context)

    def purchase_cancel(self, cr, uid, ids, context=None):
        """ Ask a cancel reason
        """
        if context is None:
            context = {}
        ctx = context.copy()
        ctx['action'] = 'purchase_cancel_ok'
        for e in ('active_model', 'active_ids', 'active_id'):  # those will be set by the web layer unless they are already defined
            if e in ctx:
                del ctx[e]
        view_id = self.pool.get('ir.model.data').get_object_reference(cr, SUPERUSER_ID, 'purchase_extended', 'action_modal_cancel_reason')[1]
        #TODO: filter based on po type
        return {
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'purchase.action_modal_cancelreason',
            'view_id': view_id,
            'views': [(view_id, 'form')],
            'target': 'new',
            'context': ctx,
        }

    def purchase_cancel_ok(self, cr, uid, ids, context=None):
        reason_id = self.pool.get('purchase.action_modal_cancelreason').read(cr, uid,
                                context['active_id'], ['reason_id'], context=context,
                                load='_classic_write')['reason_id']
        self.write(cr, uid, ids, {'cancel_reason_id': reason_id}, context=context)
        for id in ids:
            wf_service = netsvc.LocalService("workflow")
            wf_service.trg_validate(uid, 'purchase.order', id, 'purchase_cancel', cr)
        return {}

    def wkf_action_cancel(self, cr, uid, ids, context=None):
        for element in self.browse(cr, uid, ids, context=context):
            if element.state in ('draft', 'sent'):
                message = _("Request for Quotation")
            elif element.state == 'bid':
                message = _("Bid")
            else:
                message = self._description
            message += " " + _("canceled")
            self.message_post(cr, uid, [element.id], body=message, subtype="mail.mt_comment", context=context)
        return super(PurchaseOrder, self).wkf_action_cancel(cr, uid, ids, context=context)

    def bid_received(self, cr, uid, ids, context=None):
        assert len(ids) == 1, 'This action should only be used for a single id at a time'
        if context is None:
            context = {}
        order = self.read(cr, uid, ids[0], ['bid_date'], context=context)
        ctx = context.copy()
        ctx.update({
            'action': 'bid_received_ok',
            'default_datetime': order['bid_date'] or fields.date.context_today(self, cr, uid, context=context),
        })
        for e in ('active_model', 'active_ids', 'active_id'):  # those will be set by the web layer unless they are already defined
            if e in ctx:
                del ctx[e]
        view_id = self.pool.get('ir.model.data').get_object_reference(cr, SUPERUSER_ID, 'purchase_extended', 'action_modal_bid_date')[1]
        return {
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'purchase.action_modal_datetime',
            'view_id': view_id,
            'views': [(view_id, 'form')],
            'target': 'new',
            'context': ctx,
        }

    def bid_received_ok(self, cr, uid, ids, context=None):
        # TODO: send warning if not all lines have a price
        value = self.pool.get('purchase.action_modal_datetime').read(cr, uid, context['active_id'], ['datetime'], context=context)['datetime']
        self.write(cr, uid, ids, {'bid_date': value}, context=context)
        self.message_post(cr, uid, ids, body=_("Bid received and encoded"), subtype="mail.mt_comment", context=context)
        for id in ids:
            wf_service = netsvc.LocalService("workflow")
            wf_service.trg_validate(uid, 'purchase.order', id, 'bid_received', cr)
        return {}

    def wkf_bid_received(self, cr, uid, ids, context=None):
        return self.write(cr, uid, ids, {'state': 'bid', 'type': 'bid'}, context=context)

    def _has_lines(self, cr, uid, ids, context=None):
        for rfq in self.browse(cr, uid, ids, context=context):
            if not rfq.order_line:
                return False
        return True

    def wkf_send_rfq(self, cr, uid, ids, context=None):
        if not self._has_lines(cr, uid, ids, context=context):
            raise orm.except_orm(_('Error!'), _('You cannot send a Request for Quotation without any product line.'))
        return super(PurchaseOrder, self).wkf_send_rfq(cr, uid, ids, context=context)

    def print_quotation(self, cr, uid, ids, context=None):
        if not self._has_lines(cr, uid, ids, context=context):
            raise orm.except_orm(_('Error!'), _('You cannot print a Request for Quotation without any product line.'))
        self.message_post(cr, uid, ids, body=_("Request for Quotation printed"), subtype="mail.mt_comment", context=context)
        return super(PurchaseOrder, self).print_quotation(cr, uid, ids, context=context)

    def onchange_dest_address_id_mod(self, cr, uid, ids, dest_address_id,
                                     warehouse_id, context=None):
        value = self.onchange_dest_address_id(cr, uid, ids, dest_address_id)
        warehouse_obj = self.pool.get('stock.warehouse')
        dest_ids = warehouse_obj.search(cr, uid,
                                        [('partner_id', '=', dest_address_id)],
                                        context=context)
        if dest_ids:
            if warehouse_id not in dest_ids:
                warehouse_id = dest_ids[0]
        else:
            warehouse_id = False
        value['value']['warehouse_id'] = warehouse_id
        return value

    def onchange_warehouse_id(self, cr, uid, ids, warehouse_id, context=None):
        value = super(PurchaseOrder, self).onchange_warehouse_id(cr, uid, ids, warehouse_id)
        if not warehouse_id:
            return {}
        warehouse_obj = self.pool.get('stock.warehouse')
        dest_id = warehouse_obj.browse(cr, uid, warehouse_id, context=context).partner_id.id
        value['value']['dest_address_id'] = dest_id
        return value

    def po_tender_requisition_selected(self, cr, uid, ids, context=None):
        """Workflow function that write state 'bid selected'"""
        return self.write(cr, uid, ids, {'state': 'bid_selected'},
                          context=context)


class purchase_order_line(orm.Model):
    _inherit = 'purchase.order.line'

    def onchange_product_id(self, cr, uid, ids, pricelist_id, product_id, qty, uom_id,
            partner_id, date_order=False, fiscal_position_id=False, date_planned=False,
            name=False, price_unit=False, context=None, state='draftpo', type='purchase', **kwargs):
        res = super(purchase_order_line, self).onchange_product_id(cr, uid, ids,
                pricelist_id, product_id, qty, uom_id, partner_id, date_order,
                fiscal_position_id, date_planned, name, price_unit, context)
        if state == 'draft' and type == 'rfq':
            res['value'].update({'price_unit': 0})
        elif state in ('sent', 'draftbid', 'bid'):
            if 'price_unit' in res['value']:
                del res['value']['price_unit']
        return res
