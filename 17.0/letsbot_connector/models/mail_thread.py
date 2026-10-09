# Part of LetsBot Connector. See LICENSE file for full copyright and licensing details.
"""Change capture for every watched model.

sale.order, account.move, stock.picking, crm.lead and product.template all
inherit ``mail.thread``; extending the mixin here (instead of depending on
sale/account/stock/crm) keeps the module installable on any database and
only activates for apps that are actually installed.
"""
from odoo import api, models

from . import letsbot_tools as lt


class MailThread(models.AbstractModel):
    _inherit = "mail.thread"

    def _letsbot_watched(self):
        if self.env.context.get("letsbot_no_webhook") or not self.env.registry.ready:
            return False
        Params = self.env["ir.config_parameter"].sudo()
        if Params.get_param(lt.PARAM_PREFIX + "status") != "connected":
            return False
        watched = Params.get_param(lt.PARAM_PREFIX + "models", lt.DEFAULT_MODELS) or ""
        return self._name in {m.strip() for m in watched.split(",") if m.strip()}

    def _letsbot_filter(self):
        """Only business documents LetsBot cares about."""
        if self._name == "account.move" and "move_type" in self._fields:
            return self.filtered(lambda m: m.move_type in ("out_invoice", "out_refund"))
        if self._name == "stock.picking" and "picking_type_code" in self._fields:
            return self.filtered(lambda p: p.picking_type_code == "outgoing")
        return self

    def _letsbot_notify(self, action):
        records = self._letsbot_filter()
        if records:
            self.env["letsbot.webhook.event"].sudo()._letsbot_enqueue(records.sudo(), action)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if records and records._letsbot_watched():
            records._letsbot_notify("created")
        return records

    def write(self, vals):
        res = super().write(vals)
        if self and set(vals) - lt.NOISE_FIELDS and self._letsbot_watched():
            self._letsbot_notify("updated")
        return res

    def unlink(self):
        if self and self._letsbot_watched():
            self._letsbot_notify("deleted")
        return super().unlink()
