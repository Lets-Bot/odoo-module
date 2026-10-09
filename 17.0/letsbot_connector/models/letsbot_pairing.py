# Part of LetsBot Connector. See LICENSE file for full copyright and licensing details.
"""One-click pairing between this Odoo database and a LetsBot workspace.

Flow (details in LETSBOT-CONTRACT.md):

1. An administrator clicks *Connect*.  We create (or reuse) the integration
   user, mint a standard ``res.users.apikeys`` key for it and POST the
   pairing payload (signed ``state`` + db, base_url, version, login, key,
   expiry, company) **server-to-server** to the LetsBot connect URL.
   The key never transits through the browser.
2. LetsBot answers with a ``redirect_url`` on its own domain; the browser is
   sent there so the merchant picks the LetsBot workspace.
3. LetsBot verifies the key and calls back ``letsbot.pairing /
   letsbot_confirm_pairing`` over the external API *as the integration user*
   with the ``state`` and the webhook URL/secret it minted.
"""
import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from datetime import timedelta

import requests

from odoo import _, api, fields, models, release
from odoo.exceptions import AccessError, UserError

from . import letsbot_tools as lt

_logger = logging.getLogger(__name__)
P = lt.PARAM_PREFIX

OPTIONAL_GROUPS = (
    "base.group_user",
    "base.group_partner_manager",
    "sales_team.group_sale_salesman_all_leads",
    "account.group_account_invoice",
    "stock.group_stock_user",
)


def _b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text):
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


class LetsbotPairing(models.AbstractModel):
    _name = "letsbot.pairing"
    _description = "LetsBot Pairing Service"

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    @api.model
    def _params(self):
        return self.env["ir.config_parameter"].sudo()

    @api.model
    def _get(self, key, default=False):
        return self._params().get_param(P + key, default)

    @api.model
    def _set(self, key, value):
        # falsy -> the parameter row is removed (ir.config_parameter.value is required)
        self._params().set_param(P + key, value or False)

    @api.model
    def _check_admin(self):
        if not self.env.is_superuser() and not self.env.user.has_group("base.group_system"):
            raise AccessError(_("Only administrators can manage the LetsBot connection."))

    @api.model
    def _allow_http(self):
        return self._get("allow_insecure_http") in ("1", "True", "true")

    @api.model
    def _connect_url(self):
        return self._get("connect_url") or lt.DEFAULT_CONNECT_URL

    @api.model
    def _integration_user(self):
        user_id = self._get("user_id")
        user = self.env["res.users"].sudo().browse(int(user_id)) if user_id and str(user_id).isdigit() else None
        return user if user and user.exists() else self.env["res.users"]

    @api.model
    def _groups_field(self):
        return "group_ids" if "group_ids" in self.env["res.users"]._fields else "groups_id"

    @api.model
    def _has_key_expiration(self):
        return "expiration_date" in self.env["res.users.apikeys"]._fields

    @api.model
    def _sign(self, message):
        secret = self._params().get_param("database.secret") or ""
        return hmac.new(secret.encode(), ("letsbot_connector.pairing:" + message).encode(),
                        hashlib.sha256).hexdigest()

    # ------------------------------------------------------------------
    # integration user + api key
    # ------------------------------------------------------------------
    @api.model
    def _ensure_integration_user(self):
        user = self._integration_user()
        if user and user.active:
            return user
        Users = self.env["res.users"].sudo().with_context(active_test=False, no_reset_password=True)
        user = Users.search([("login", "=", lt.INTEGRATION_LOGIN)], limit=1)
        groups = [self.env.ref(xmlid, raise_if_not_found=False) for xmlid in OPTIONAL_GROUPS]
        group_ids = [g.id for g in groups if g]
        if user:
            user.write({"active": True, self._groups_field(): [(4, gid) for gid in group_ids]})
        else:
            user = Users.create({
                "name": "LetsBot Integration",
                "login": lt.INTEGRATION_LOGIN,
                "company_id": self.env.company.id,
                "company_ids": [(6, 0, self.env.user.company_ids.ids or [self.env.company.id])],
                self._groups_field(): [(6, 0, group_ids)],
            })
        self._set("user_id", str(user.id))
        self._set("managed_user_id", str(user.id))
        return user

    @api.model
    def _key_days(self):
        try:
            days = int(self._get("key_days", "90") or 90)
        except ValueError:
            days = 90
        return max(1, min(days, 365))

    @api.model
    def _generate_key(self, user):
        """Mint a key owned by ``user`` through the standard mechanism.

        17.0 has no expiration column; 18.0/19.0 do and cap the duration for
        non-system users, so we generate in sudo (allowed by the API) with an
        explicit, bounded expiry.
        """
        Keys = self.env["res.users.apikeys"].with_user(user).sudo()
        expiration = False
        if self._has_key_expiration():
            expiration = fields.Datetime.now() + timedelta(days=self._key_days())
            key = Keys._generate(None, lt.API_KEY_NAME, expiration)
        else:
            key = Keys._generate(None, lt.API_KEY_NAME)
        record = self.env["res.users.apikeys"].sudo().search(
            [("user_id", "=", user.id), ("name", "=", lt.API_KEY_NAME)], order="id desc", limit=1)
        return key, record, expiration

    @api.model
    def _revoke_keys(self, user, keep=None):
        if not user:
            return 0
        keys = self.env["res.users.apikeys"].sudo().search(
            [("user_id", "=", user.id), ("name", "=", lt.API_KEY_NAME)])
        if keep:
            keys -= keep
        count = len(keys)
        if keys:
            keys._remove()
        return count

    # ------------------------------------------------------------------
    # state token
    # ------------------------------------------------------------------
    @api.model
    def _make_state(self, integration_user, nonce):
        payload = {
            "n": nonce, "db": self.env.cr.dbname, "u": self.env.uid,
            "i": integration_user.id, "exp": int(time.time()) + lt.PAIRING_TTL,
        }
        body = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
        return body + "." + self._sign(body)

    @api.model
    def _read_state(self, state):
        """Return the decoded state or raise AccessError."""
        try:
            body, signature = (state or "").split(".", 1)
            if not hmac.compare_digest(self._sign(body), signature):
                raise ValueError("bad signature")
            payload = json.loads(_unb64(body))
        except (ValueError, TypeError) as exc:
            raise AccessError(_("Invalid pairing state.")) from exc
        if payload.get("exp", 0) < time.time():
            raise AccessError(_("The pairing request has expired. Click Connect again in Odoo."))
        if payload.get("db") != self.env.cr.dbname:
            raise AccessError(_("Invalid pairing state."))
        if not hmac.compare_digest(lt.hash_token(payload.get("n")), self._get("pairing_nonce_hash") or ""):
            raise AccessError(_("This pairing request was replaced or already used."))
        return payload

    # ------------------------------------------------------------------
    # step 1: admin clicks Connect
    # ------------------------------------------------------------------
    @api.model
    def _company_info(self, company):
        return {
            "id": company.id,
            "name": company.name,
            "currency": company.currency_id.name or None,
            "country_code": company.country_id.code or None,
        }

    @api.model
    def _build_handoff(self, user, key, expiration, state):
        base_url = (self._params().get_param("web.base.url") or "").rstrip("/")
        admin = self.env.user
        return {
            "protocol": lt.PROTOCOL_VERSION,
            "type": "odoo.pairing",
            "state": state,
            "db": self.env.cr.dbname,
            "base_url": base_url,
            "version": release.series,
            "server_version": release.version,
            "module_version": self.env["letsbot.webhook.event"]._letsbot_module_version(),
            "login": user.login,
            "uid": user.id,
            "key": key,
            "key_expires_at": fields.Datetime.to_string(expiration) if expiration else None,
            "company": self._company_info(self.env.company),
            "companies": [self._company_info(c) for c in self.env.user.company_ids],
            "lang": admin.lang or None,
            "tz": admin.tz or None,
            "admin": {"name": admin.name, "email": admin.email or None},
            "return_url": base_url + "/web#action=base_setup.action_general_configuration",
            "confirm": {"model": "letsbot.pairing", "method": "letsbot_confirm_pairing"},
            "pairing_ttl": lt.PAIRING_TTL,
        }

    @api.model
    def action_start_pairing(self):
        """Create user + key, hand them to LetsBot, return the browser redirect action."""
        self._check_admin()
        try:
            connect_url = lt.check_url(self._connect_url(), self._allow_http())
        except ValueError as exc:
            raise UserError(_("The LetsBot connect URL is invalid: %s", exc)) from exc
        user = self._ensure_integration_user()
        # drop a previous, never confirmed pairing key
        pending_key = self._get("pending_key_id")
        if pending_key and str(pending_key).isdigit():
            stale = self.env["res.users.apikeys"].sudo().browse(int(pending_key)).exists()
            if stale and stale.user_id == user:
                stale._remove()
        key, key_record, expiration = self._generate_key(user)
        nonce = secrets.token_urlsafe(32)
        state = self._make_state(user, nonce)
        payload = self._build_handoff(user, key, expiration, state)
        body = lt.dumps(payload)
        try:
            response = requests.post(
                connect_url, data=body, timeout=lt.HTTP_TIMEOUT, allow_redirects=False,
                headers={"Content-Type": "application/json", "Accept": "application/json",
                         "User-Agent": "LetsBot-Odoo-Connector (Odoo %s)" % release.version})
        except requests.RequestException as exc:
            _logger.warning("LetsBot pairing handoff failed: %s", exc)
            raise UserError(_("Could not reach LetsBot. Check the server's internet access and try again.")) from exc
        if response.status_code not in (200, 201):
            raise UserError(_("LetsBot refused the connection request (HTTP %s).", response.status_code))
        try:
            redirect_url = lt.check_url(response.json().get("redirect_url"), self._allow_http())
        except (ValueError, AttributeError) as exc:
            raise UserError(_("LetsBot returned an invalid answer.")) from exc
        if not lt.same_site(redirect_url, connect_url):
            raise UserError(_("LetsBot returned a redirect to an unexpected domain."))
        # Everything above runs in this transaction: any exception rolls back
        # the new key, so a failed handoff never leaves a usable credential.
        self._set("pairing_nonce_hash", lt.hash_token(nonce))
        self._set("pending_key_id", str(key_record.id))
        if self._get("status") != "connected":
            self._set("status", "pending")
        self._set("last_error", "")
        return {"type": "ir.actions.act_url", "url": redirect_url, "target": "self"}

    # ------------------------------------------------------------------
    # step 3: LetsBot calls back (external API, as the integration user)
    # ------------------------------------------------------------------
    @api.model
    def letsbot_confirm_pairing(self, state, webhook_url, webhook_secret,
                                account_label=None, conversation_url=None):
        payload = self._read_state(state)
        user = self._integration_user()
        if not user or self.env.uid != user.id or payload.get("i") != user.id:
            raise AccessError(_("Pairing must be confirmed with the LetsBot integration key."))
        try:
            webhook_url = lt.check_url(webhook_url, self._allow_http())
            if conversation_url:
                conversation_url = lt.check_url(conversation_url, self._allow_http())
        except ValueError as exc:
            raise UserError(_("Invalid URL from LetsBot: %s", exc)) from exc
        if not webhook_secret or len(webhook_secret) < 32:
            raise UserError(_("The webhook secret must be at least 32 characters."))
        pending_key = self._get("pending_key_id")
        keep = self.env["res.users.apikeys"].sudo().browse(int(pending_key)).exists() \
            if pending_key and str(pending_key).isdigit() else None
        # the newly paired key replaces any older LetsBot key of that user
        self._revoke_keys(user, keep=keep)
        now = fields.Datetime.to_string(fields.Datetime.now())
        for key, value in (
            ("webhook_url", webhook_url), ("webhook_secret", webhook_secret),
            ("account_label", (account_label or "")[:120]), ("conversation_url", conversation_url or ""),
            ("status", "connected"), ("paired_at", now), ("last_ping", now),
            ("pairing_nonce_hash", ""), ("pending_key_id", ""), ("last_error", ""),
        ):
            self._set(key, value)
        return {
            "ok": True,
            "db": self.env.cr.dbname,
            "version": release.series,
            "module_version": self.env["letsbot.webhook.event"].sudo()._letsbot_module_version(),
            "models": [m for m in (self._get("models", lt.DEFAULT_MODELS) or "").split(",") if m in self.env],
        }

    @api.model
    def _check_integration_caller(self):
        user = self._integration_user()
        if self.env.is_superuser() or self.env.user.has_group("base.group_system"):
            return
        if not user or self.env.uid != user.id:
            raise AccessError(_("Only the LetsBot integration user can call this method."))

    @api.model
    def letsbot_ping(self):
        """Health check called by LetsBot; also records the last contact time."""
        self._check_integration_caller()
        if self._get("status") == "connected":
            self._set("last_ping", fields.Datetime.to_string(fields.Datetime.now()))
        Events = self.env["letsbot.webhook.event"].sudo()
        return {
            "ok": True,
            "status": self._get("status") or "disconnected",
            "version": release.series,
            "module_version": Events._letsbot_module_version(),
            "models": [m for m in (self._get("models", lt.DEFAULT_MODELS) or "").split(",") if m in self.env],
            "queue_pending": Events.search_count([("state", "=", "pending")]),
        }

    @api.model
    def letsbot_disconnect(self):
        """LetsBot-initiated disconnect: revokes the key and stops webhooks."""
        self._check_integration_caller()
        self._disconnect(notify=False)
        return {"ok": True}

    # ------------------------------------------------------------------
    # disconnect / test
    # ------------------------------------------------------------------
    @api.model
    def _disconnect(self, notify=True):
        url, secret = self._get("webhook_url"), self._get("webhook_secret")
        if notify and url and secret and self._get("status") == "connected":
            self.env["letsbot.webhook.event"].sudo()._letsbot_post(url, secret, {
                "api_version": lt.PROTOCOL_VERSION, "id": secrets.token_hex(16),
                "event": "connector.disconnected", "db": self.env.cr.dbname,
            }, timeout=5)
        user = self._integration_user()
        self._revoke_keys(user)
        managed = self._get("managed_user_id")
        if user and managed and str(managed) == str(user.id) and user.id != self.env.uid:
            user.sudo().write({"active": False})
        self.env["letsbot.webhook.event"].sudo().search([("state", "=", "pending")]).unlink()
        for key in ("webhook_url", "webhook_secret", "account_label", "conversation_url",
                    "pairing_nonce_hash", "pending_key_id", "paired_at"):
            self._set(key, "")
        self._set("status", "disconnected")

    @api.model
    def action_disconnect(self):
        self._check_admin()
        self._disconnect(notify=True)
        return True

    @api.model
    def action_send_test(self):
        self._check_admin()
        url, secret = self._get("webhook_url"), self._get("webhook_secret")
        if self._get("status") != "connected" or not url or not secret:
            raise UserError(_("Connect LetsBot first."))
        code, error = self.env["letsbot.webhook.event"].sudo()._letsbot_post(url, secret, {
            "api_version": lt.PROTOCOL_VERSION, "id": secrets.token_hex(16),
            "event": "connector.ping", "db": self.env.cr.dbname,
        })
        if error:
            self._set("last_error", error)
            raise UserError(_("LetsBot did not accept the test event: %s", error))
        self._set("last_ping", fields.Datetime.to_string(fields.Datetime.now()))
        self._set("last_error", "")
        return code
