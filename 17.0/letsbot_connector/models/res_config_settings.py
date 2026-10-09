# Part of LetsBot Connector. See LICENSE file for full copyright and licensing details.
from odoo import _, api, fields, models

from . import letsbot_tools as lt

P = lt.PARAM_PREFIX
WATCH_FIELDS = {
    "letsbot_watch_sale": "sale.order",
    "letsbot_watch_invoice": "account.move",
    "letsbot_watch_picking": "stock.picking",
    "letsbot_watch_lead": "crm.lead",
    "letsbot_watch_product": "product.template",
}


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    letsbot_connect_url = fields.Char(
        "LetsBot Connect URL", config_parameter=P + "connect_url", default=lt.DEFAULT_CONNECT_URL,
        groups="base.group_system")
    letsbot_user_id = fields.Many2one(
        "res.users", "Integration User", config_parameter=P + "user_id",
        domain=[("share", "=", False)], groups="base.group_system",
        help="User whose API key LetsBot uses. Leave empty to let the connector create a "
             "dedicated 'LetsBot Integration' user (recommended).")
    letsbot_key_days = fields.Integer(
        "API Key Validity (days)", config_parameter=P + "key_days", default=90, groups="base.group_system",
        help="Odoo 18+ only: the API key generated for LetsBot expires after this many days (1-365).")
    letsbot_status = fields.Selection(
        [("disconnected", "Not connected"), ("pending", "Waiting for LetsBot"),
         ("connected", "Connected"), ("revoked", "Disconnected by LetsBot")],
        "LetsBot Status", compute="_compute_letsbot_info", groups="base.group_system")
    letsbot_last_ping = fields.Datetime("Last Contact", compute="_compute_letsbot_info", groups="base.group_system")
    letsbot_account_label = fields.Char("LetsBot Workspace", compute="_compute_letsbot_info",
                                        groups="base.group_system")
    letsbot_last_error = fields.Char("Last Error", compute="_compute_letsbot_info", groups="base.group_system")
    letsbot_queue_pending = fields.Integer("Pending Events", compute="_compute_letsbot_info",
                                           groups="base.group_system")
    letsbot_watch_sale = fields.Boolean("Sales Orders", groups="base.group_system")
    letsbot_watch_invoice = fields.Boolean("Customer Invoices", groups="base.group_system")
    letsbot_watch_picking = fields.Boolean("Deliveries", groups="base.group_system")
    letsbot_watch_lead = fields.Boolean("CRM Leads", groups="base.group_system")
    letsbot_watch_product = fields.Boolean("Products", groups="base.group_system")

    @api.depends("company_id")
    def _compute_letsbot_info(self):
        Params = self.env["ir.config_parameter"].sudo()
        pending = self.env["letsbot.webhook.event"].sudo().search_count([("state", "=", "pending")])
        for record in self:
            record.letsbot_status = Params.get_param(P + "status") or "disconnected"
            record.letsbot_last_ping = Params.get_param(P + "last_ping") or False
            record.letsbot_account_label = Params.get_param(P + "account_label") or False
            record.letsbot_last_error = Params.get_param(P + "last_error") or False
            record.letsbot_queue_pending = pending

    @api.model
    def get_values(self):
        res = super().get_values()
        watched = (self.env["ir.config_parameter"].sudo().get_param(P + "models", lt.DEFAULT_MODELS) or "").split(",")
        for fname, model in WATCH_FIELDS.items():
            res[fname] = model in watched
        return res

    def set_values(self):
        super().set_values()
        if self.env.user.has_group("base.group_system"):
            models_csv = ",".join(model for fname, model in WATCH_FIELDS.items() if self[fname])
            self.env["ir.config_parameter"].sudo().set_param(P + "models", models_csv)

    def action_letsbot_connect(self):
        self.execute()  # persist the URL / user / validity first
        return self.env["letsbot.pairing"].action_start_pairing()

    def action_letsbot_disconnect(self):
        self.env["letsbot.pairing"].action_disconnect()
        return {"type": "ir.actions.client", "tag": "reload"}

    def action_letsbot_test(self):
        self.env["letsbot.pairing"].action_send_test()
        return {
            "type": "ir.actions.client", "tag": "display_notification",
            "params": {"type": "success", "title": _("LetsBot"),
                       "message": _("Test event delivered."), "sticky": False},
        }

    def action_letsbot_open_queue(self):
        return self.env["ir.actions.act_window"]._for_xml_id("letsbot_connector.action_letsbot_webhook_event")
