# Part of LetsBot Connector. See LICENSE file for full copyright and licensing details.
import re
from urllib.parse import quote

from odoo import _, fields, models
from odoo.exceptions import UserError

from . import letsbot_tools as lt


class ResPartner(models.Model):
    _inherit = "res.partner"

    letsbot_chat_available = fields.Boolean(compute="_compute_letsbot_chat_available")

    def _letsbot_phone_digits(self):
        self.ensure_one()
        phone = ""
        for fname in ("phone_sanitized", "mobile", "phone"):
            if fname in self._fields and self[fname]:
                phone = self[fname]
                break
        return re.sub(r"\D", "", phone or "")

    def _compute_letsbot_chat_available(self):
        Params = self.env["ir.config_parameter"].sudo()
        enabled = Params.get_param(lt.PARAM_PREFIX + "status") == "connected" and \
            bool(Params.get_param(lt.PARAM_PREFIX + "conversation_url"))
        for partner in self:
            partner.letsbot_chat_available = enabled and bool(partner._letsbot_phone_digits())

    def action_open_letsbot_chat(self):
        self.ensure_one()
        template = self.env["ir.config_parameter"].sudo().get_param(lt.PARAM_PREFIX + "conversation_url")
        digits = self._letsbot_phone_digits()
        if not template or not digits:
            raise UserError(_("No LetsBot conversation is available for this contact."))
        url = template.replace("{phone}", quote(digits)).replace("{partner_id}", str(self.id))
        return {"type": "ir.actions.act_url", "url": url, "target": "new"}
