# Part of LetsBot Connector. See LICENSE file for full copyright and licensing details.
"""Change capture on the real business models (skipped when the app is not installed)."""
from odoo.tests import tagged

from .common import LetsbotCase

ALL = "sale.order,account.move,stock.picking,crm.lead,product.template"


@tagged("post_install", "-at_install", "letsbot")
class TestBusinessModels(LetsbotCase):

    def setUp(self):
        super().setUp()
        self._connect(models=ALL)
        self.partner = self.env["res.partner"].create({"name": "WhatsApp Customer"})

    def _need(self, model):
        if model not in self.env:
            self.skipTest("%s not installed" % model)

    def _values(self, record):
        import json
        event = self._events(model=record._name, res_id=record.id)
        self.assertEqual(len(event), 1, "exactly one queued event for %s" % record)
        return event, json.loads(event.values_json)

    def test_sale_order(self):
        self._need("sale.order")
        order = self.env["sale.order"].create({"partner_id": self.partner.id})
        event, values = self._values(order)
        self.assertEqual(event.event, "sale.order.created")
        self.assertEqual(values, {"state": "draft"})
        self.assertEqual(event.company_id, order.company_id)

    def test_customer_invoice_only(self):
        self._need("account.move")
        journal = self.env["account.journal"].search([("type", "=", "sale"), ("company_id", "=", self.env.company.id)], limit=1)
        purchase = self.env["account.journal"].search([("type", "=", "purchase"), ("company_id", "=", self.env.company.id)], limit=1)
        if not journal or not purchase:
            self.skipTest("no chart of accounts on this company")
        invoice = self.env["account.move"].create({"move_type": "out_invoice", "partner_id": self.partner.id,
                                                   "journal_id": journal.id})
        bill = self.env["account.move"].create({"move_type": "in_invoice", "partner_id": self.partner.id,
                                                "journal_id": purchase.id})
        event, values = self._values(invoice)
        self.assertEqual(values["state"], "draft")
        self.assertIn("payment_state", values)
        self.assertFalse(self._events(model="account.move", res_id=bill.id), "vendor bills are ignored")

    def test_outgoing_pickings_only(self):
        self._need("stock.picking")
        out_type = self.env["stock.picking.type"].search(
            [("code", "=", "outgoing"), ("company_id", "=", self.env.company.id)], limit=1)
        in_type = self.env["stock.picking.type"].search(
            [("code", "=", "incoming"), ("company_id", "=", self.env.company.id)], limit=1)
        if not out_type or not in_type:
            self.skipTest("no warehouse")
        def vals(ptype):
            return {"picking_type_id": ptype.id, "partner_id": self.partner.id,
                    "location_id": (ptype.default_location_src_id or self.env.ref("stock.stock_location_suppliers")).id,
                    "location_dest_id": (ptype.default_location_dest_id or self.env.ref("stock.stock_location_customers")).id}
        delivery = self.env["stock.picking"].create(vals(out_type))
        receipt = self.env["stock.picking"].create(vals(in_type))
        _event, values = self._values(delivery)
        self.assertIn("state", values)
        self.assertFalse(self._events(model="stock.picking", res_id=receipt.id), "receipts are ignored")

    def test_crm_lead(self):
        self._need("crm.lead")
        lead = self.env["crm.lead"].create({"name": "From WhatsApp", "partner_id": self.partner.id})
        _event, values = self._values(lead)
        self.assertEqual(values["stage_id"], lead.stage_id.id or False)
        self.assertTrue(values["active"])

    def test_product_template(self):
        self._need("product.template")
        product = self.env["product.template"].create({"name": "Watched product"})
        _event, values = self._values(product)
        self.assertEqual(values, {"active": True})
