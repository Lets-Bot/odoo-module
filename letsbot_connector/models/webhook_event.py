# Part of LetsBot Connector. See LICENSE file for full copyright and licensing details.
import logging
import uuid
from datetime import timedelta

import requests

from odoo import api, fields, models, release

from . import letsbot_tools as lt

_logger = logging.getLogger(__name__)


class LetsbotWebhookEvent(models.Model):
    """Outbox of lightweight change notifications sent to LetsBot.

    Rows are written inside the business transaction (so a rolled back
    transaction never notifies) and delivered by a cron *after* commit,
    which keeps user transactions free of any network I/O.
    """

    _name = "letsbot.webhook.event"
    _description = "LetsBot Webhook Event"
    _order = "id desc"
    _rec_name = "event"

    uid_token = fields.Char("Delivery ID", required=True, readonly=True, index=True, copy=False,
                            default=lambda self: str(uuid.uuid4()))
    event = fields.Char(required=True, readonly=True)
    model = fields.Char("Model", required=True, readonly=True, index=True)
    res_id = fields.Integer("Record ID", required=True, readonly=True, index=True)
    record_write_date = fields.Datetime("Record Last Update", readonly=True)
    values_json = fields.Char("State Values", readonly=True)
    company_id = fields.Many2one("res.company", readonly=True, index=True)
    state = fields.Selection(
        [("pending", "Pending"), ("sent", "Sent"), ("dead", "Failed")],
        default="pending", required=True, readonly=True, index=True)
    # explicit default: 17.0 stores NULL otherwise and ('attempts', '=', 0) would not match it
    attempts = fields.Integer(default=0, readonly=True)
    next_attempt_at = fields.Datetime("Next Attempt", default=fields.Datetime.now, readonly=True, index=True)
    sent_at = fields.Datetime(readonly=True)
    last_status_code = fields.Integer("Last HTTP Status", readonly=True)
    last_error = fields.Char(readonly=True)

    # ------------------------------------------------------------------
    # Enqueue (called from mail.thread hooks, always in sudo)
    # ------------------------------------------------------------------
    @api.model
    def _letsbot_enqueue(self, records, action):
        """Queue one event per record, collapsing still-unsent duplicates."""
        records = records.exists() if action != "deleted" else records
        if not records:
            return self.browse()
        model = records._name
        state_fields = [f for f in lt.STATE_FIELDS.get(model, ()) if f in records._fields]
        pending = self.search([
            ("model", "=", model), ("res_id", "in", records.ids),
            ("state", "=", "pending"), ("attempts", "=", 0),
        ])
        pending_by_id = {ev.res_id: ev for ev in pending}
        vals_list = []
        for record in records:
            values = {}
            if action != "deleted":
                for fname in state_fields:
                    value = record[fname]
                    if isinstance(value, models.BaseModel):
                        value = value.id or False
                    values[fname] = value
            company = record["company_id"].id if "company_id" in record._fields else False
            vals = {
                "record_write_date": record.write_date if action != "deleted" else fields.Datetime.now(),
                "values_json": lt.dumps(values).decode("utf-8"),
                "company_id": company or False,
            }
            existing = pending_by_id.get(record.id)
            if existing:
                if action == "deleted" or existing.event.endswith(".updated"):
                    vals["event"] = "%s.%s" % (model, action)
                existing.write(vals)
                continue
            vals.update({"event": "%s.%s" % (model, action), "model": model, "res_id": record.id})
            vals_list.append(vals)
        created = self.create(vals_list) if vals_list else self.browse()
        if created:
            cron = self.env.ref("letsbot_connector.ir_cron_letsbot_webhook_dispatch", raise_if_not_found=False)
            if cron:
                cron.sudo()._trigger()
        return created

    # ------------------------------------------------------------------
    # Delivery
    # ------------------------------------------------------------------
    def _letsbot_payload(self):
        self.ensure_one()
        import json
        return {
            "api_version": lt.PROTOCOL_VERSION,
            "id": self.uid_token,
            "event": self.event,
            "model": self.model,
            "res_id": self.res_id,
            "write_date": fields.Datetime.to_string(self.record_write_date) if self.record_write_date else None,
            "values": json.loads(self.values_json or "{}"),
            "company_id": self.company_id.id or None,
            "db": self.env.cr.dbname,
            "attempt": self.attempts + 1,
            "created_at": fields.Datetime.to_string(self.create_date) if self.create_date else None,
        }

    @api.model
    def _letsbot_post(self, url, secret, payload, timeout=lt.HTTP_TIMEOUT):
        """POST a signed JSON payload. Returns (status_code, error_message)."""
        body = lt.dumps(payload)
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "LetsBot-Odoo-Connector/%s (Odoo %s)" % (self._letsbot_module_version(), release.version),
            "X-LetsBot-Signature": lt.signature_header(secret, body),
            "X-LetsBot-Event": payload.get("event", ""),
            "X-LetsBot-Delivery": payload.get("id", ""),
            "X-Odoo-Database": self.env.cr.dbname,
        }
        try:
            response = requests.post(url, data=body, headers=headers, timeout=timeout, allow_redirects=False)
        except requests.RequestException as exc:
            return 0, str(exc)[:250]
        if 200 <= response.status_code < 300:
            return response.status_code, False
        return response.status_code, ("HTTP %s: %s" % (response.status_code, (response.text or "")[:200]))

    @api.model
    def _letsbot_module_version(self):
        module = self.env["ir.module.module"].sudo().search([("name", "=", "letsbot_connector")], limit=1)
        return module.latest_version or module.installed_version or "unknown"

    def _letsbot_send(self):
        """Deliver self (one event); updates state/backoff. Never raises."""
        self.ensure_one()
        Params = self.env["ir.config_parameter"].sudo()
        url = Params.get_param(lt.PARAM_PREFIX + "webhook_url")
        secret = Params.get_param(lt.PARAM_PREFIX + "webhook_secret")
        if Params.get_param(lt.PARAM_PREFIX + "status") != "connected" or not url or not secret:
            self.write({"state": "dead", "last_error": "LetsBot is not connected"})
            return False
        code, error = self._letsbot_post(url, secret, self._letsbot_payload())
        now = fields.Datetime.now()
        if not error:
            self.write({"state": "sent", "sent_at": now, "attempts": self.attempts + 1,
                        "last_status_code": code, "last_error": False})
            Params.set_param(lt.PARAM_PREFIX + "last_ping", fields.Datetime.to_string(now))
            return True
        attempts = self.attempts + 1
        vals = {"attempts": attempts, "last_status_code": code, "last_error": error}
        if code == 410:
            # LetsBot says this webhook endpoint is gone (tenant disconnected).
            vals["state"] = "dead"
            Params.set_param(lt.PARAM_PREFIX + "status", "revoked")
        elif attempts >= lt.MAX_ATTEMPTS:
            vals["state"] = "dead"
        else:
            vals["next_attempt_at"] = now + timedelta(minutes=lt.BACKOFF_MINUTES[attempts - 1])
        self.write(vals)
        _logger.info("LetsBot webhook %s (%s #%s) failed, attempt %s: %s",
                     self.uid_token, self.model, self.res_id, attempts, error)
        return False

    @api.model
    def _cron_dispatch(self, limit=200, commit=False):
        """Deliver due events. The scheduled action passes ``commit=True`` so each
        delivery is its own transaction (crash safe); tests call it without."""
        events = self.search([
            ("state", "=", "pending"), ("next_attempt_at", "<=", fields.Datetime.now()),
        ], order="id asc", limit=limit)
        for event in events:
            event._letsbot_send()
            if commit:
                self.env.cr.commit()
        return len(events)

    def action_retry(self):
        self.filtered(lambda ev: ev.state != "sent").write(
            {"state": "pending", "attempts": 0, "next_attempt_at": fields.Datetime.now()})
        cron = self.env.ref("letsbot_connector.ir_cron_letsbot_webhook_dispatch", raise_if_not_found=False)
        if cron:
            cron._trigger()

    @api.autovacuum
    def _gc_letsbot_events(self):
        limit = fields.Datetime.now() - timedelta(days=7)
        self.search([("state", "in", ("sent", "dead")), ("create_date", "<", limit)]).unlink()
