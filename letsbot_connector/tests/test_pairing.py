# Part of LetsBot Connector. See LICENSE file for full copyright and licensing details.
import json
import time
from datetime import timedelta
from unittest.mock import patch

from odoo import fields, release
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from odoo.addons.letsbot_connector.models import letsbot_tools as lt

from .common import CONNECT_URL, P, WEBHOOK_URL, SECRET, LetsbotCase, FakeResponse, mock_post

REDIRECT = "https://letsbot.net/odoo/connect?code=pc_123"


@tagged("post_install", "-at_install", "letsbot")
class TestPairing(LetsbotCase):

    def setUp(self):
        super().setUp()
        self.Params.set_param(P + "connect_url", CONNECT_URL)
        self.Pairing = self.env["letsbot.pairing"].with_user(self.admin)
        self.Keys = self.env["res.users.apikeys"].sudo()

    def _start(self, response=None):
        with mock_post(response or FakeResponse(201, {"redirect_url": REDIRECT})) as rec:
            action = self.Pairing.action_start_pairing()
        return action, json.loads(rec.calls[0]["data"]), rec.calls[0]

    def _user(self):
        return self.env["res.users"].browse(int(self.Params.get_param(P + "user_id")))

    def _confirm(self, state, user=None, **kw):
        args = dict(webhook_url=WEBHOOK_URL, webhook_secret=SECRET, account_label="Acme Store",
                    conversation_url="https://acme.letsbot.net/inbox?phone={phone}")
        args.update(kw)
        return self.env["letsbot.pairing"].with_user(user or self._user()).letsbot_confirm_pairing(state, **args)

    def _authenticates(self, key, user):
        return self.Keys._check_credentials(scope="rpc", key=key) == user.id

    def test_handoff_payload_and_key(self):
        action, payload, call = self._start()
        self.assertEqual(action, {"type": "ir.actions.act_url", "url": REDIRECT, "target": "self"})
        self.assertEqual(call["url"], CONNECT_URL)
        self.assertFalse(call["allow_redirects"])
        user = self._user()
        self.assertEqual(user.login, lt.INTEGRATION_LOGIN)
        self.assertTrue(user.has_group("base.group_user"))
        self.assertFalse(user.has_group("base.group_system"), "integration user is never an admin")
        for key in ("protocol", "state", "db", "base_url", "version", "server_version", "login", "uid",
                    "key", "key_expires_at", "company", "return_url", "confirm"):
            self.assertIn(key, payload)
        self.assertEqual(payload["db"], self.env.cr.dbname)
        self.assertEqual(payload["version"], release.series)
        self.assertEqual(payload["login"], user.login)
        self.assertEqual(payload["uid"], user.id)
        self.assertEqual(payload["company"]["id"], self.env.company.id)
        self.assertEqual(payload["confirm"], {"model": "letsbot.pairing", "method": "letsbot_confirm_pairing"})
        self.assertTrue(self._authenticates(payload["key"], user), "the handed-off key is a real Odoo API key")
        key_rec = self.Keys.search([("user_id", "=", user.id), ("name", "=", lt.API_KEY_NAME)])
        self.assertEqual(len(key_rec), 1)
        if "expiration_date" in self.Keys._fields:  # 18.0 / 19.0
            self.assertTrue(payload["key_expires_at"])
            delta = key_rec.expiration_date - fields.Datetime.now()
            self.assertTrue(timedelta(days=89) < delta <= timedelta(days=90))
        else:  # 17.0
            self.assertIsNone(payload["key_expires_at"])
        self.assertEqual(self.Params.get_param(P + "status"), "pending")

    def test_handoff_failures_leave_no_key(self):
        for response in (FakeResponse(500, text="down"),
                         FakeResponse(200, {"redirect_url": "https://evil.example.com/steal"}),
                         FakeResponse(200, {"redirect_url": "http://letsbot.net/odoo/connect"}),
                         FakeResponse(200, None, text="<html>")):
            with self.assertRaises(UserError):
                self._start(response)
        user = self.env["res.users"].with_context(active_test=False).search([("login", "=", lt.INTEGRATION_LOGIN)])
        self.assertFalse(self.Keys.search([("user_id", "in", user.ids), ("name", "=", lt.API_KEY_NAME)]),
                         "a failed handoff rolls the key back")

    def test_insecure_connect_url_refused(self):
        self.Params.set_param(P + "connect_url", "http://letsbot.net/odoo/connect")
        with mock_post(FakeResponse(200, {"redirect_url": REDIRECT})) as rec:
            with self.assertRaises(UserError):
                self.Pairing.action_start_pairing()
        self.assertFalse(rec.calls)

    def test_confirm_connects_and_is_single_use(self):
        _action, payload, _call = self._start()
        result = self._confirm(payload["state"])
        self.assertTrue(result["ok"])
        self.assertEqual(self.Params.get_param(P + "status"), "connected")
        self.assertEqual(self.Params.get_param(P + "webhook_url"), WEBHOOK_URL)
        self.assertEqual(self.Params.get_param(P + "webhook_secret"), SECRET)
        self.assertEqual(self.Params.get_param(P + "account_label"), "Acme Store")
        with self.assertRaises(AccessError):
            self._confirm(payload["state"])

    def test_confirm_rejections(self):
        _action, payload, _call = self._start()
        state = payload["state"]
        with self.assertRaises(AccessError):  # wrong caller (admin is not the integration user)
            self._confirm(state, user=self.admin)
        body, sig = state.split(".")
        with self.assertRaises(AccessError):  # tampered signature
            self._confirm(body + "." + ("0" * len(sig)))
        with self.assertRaises(UserError):  # http webhook
            self._confirm(state, webhook_url="http://acme.letsbot.net/hook")
        with self.assertRaises(UserError):  # weak secret
            self._confirm(state, webhook_secret="short")
        with patch.object(time, "time", lambda: 4102444800.0):  # year 2100: expired
            with self.assertRaises(AccessError):
                self._confirm(state)
        self.assertEqual(self.Params.get_param(P + "status"), "pending")
        self.assertTrue(self._confirm(state)["ok"])

    def test_reconnect_rotates_key(self):
        _a, first, _c = self._start()
        self._confirm(first["state"])
        _a, second, _c = self._start()
        user = self._user()
        self.assertTrue(self._authenticates(first["key"], user), "old key stays valid until LetsBot confirms")
        self._confirm(second["state"])
        self.assertFalse(self._authenticates(first["key"], user))
        self.assertTrue(self._authenticates(second["key"], user))
        self.assertEqual(self.Keys.search_count([("user_id", "=", user.id), ("name", "=", lt.API_KEY_NAME)]), 1)

    def test_disconnect_revokes_everything(self):
        _a, payload, _c = self._start()
        self._confirm(payload["state"])
        user = self._user()
        self.Params.set_param(P + "models", "res.partner")
        self.env["res.partner"].create({"name": "Pending event"})
        with mock_post(FakeResponse(200)) as rec:
            self.Pairing.action_disconnect()
        self.assertEqual(json.loads(rec.calls[0]["data"])["event"], "connector.disconnected")
        self.assertFalse(self._authenticates(payload["key"], user))
        self.assertFalse(user.active, "the dedicated user is archived")
        self.assertEqual(self.Params.get_param(P + "status"), "disconnected")
        self.assertFalse(self.Params.get_param(P + "webhook_secret"))
        self.assertFalse(self.Events.search([("state", "=", "pending")]))
        # reconnecting reactivates the same dedicated user
        _a, again, _c = self._start()
        self.assertEqual(again["uid"], user.id)
        self.assertTrue(user.active)

    def test_only_admins(self):
        groups_field = "group_ids" if "group_ids" in self.env["res.users"]._fields else "groups_id"
        clerk = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Clerk", "login": "letsbot_clerk", groups_field: [(6, 0, [self.env.ref("base.group_user").id])]})
        with mock_post(FakeResponse(201, {"redirect_url": REDIRECT})) as rec:
            with self.assertRaises(AccessError):
                self.env["letsbot.pairing"].with_user(clerk).action_start_pairing()
            with self.assertRaises(AccessError):
                self.env["letsbot.pairing"].with_user(clerk).action_disconnect()
            with self.assertRaises(AccessError):
                self.env["letsbot.pairing"].with_user(clerk).letsbot_ping()
        self.assertFalse(rec.calls)

    def test_ping_and_partner_button(self):
        _a, payload, _c = self._start()
        self._confirm(payload["state"])
        result = self.env["letsbot.pairing"].with_user(self._user()).letsbot_ping()
        self.assertEqual((result["ok"], result["status"], result["version"]), (True, "connected", release.series))
        partner = self.env["res.partner"].create({"name": "Chat", "phone": "+20 100 123 4567"})
        self.assertTrue(partner.letsbot_chat_available)
        action = partner.action_open_letsbot_chat()
        self.assertEqual(action["url"].split("phone=")[0], "https://acme.letsbot.net/inbox?")
        self.assertTrue(action["url"].endswith("201001234567"))
        self.assertFalse(self.env["res.partner"].create({"name": "No phone"}).letsbot_chat_available)

    def test_settings_roundtrip(self):
        settings = self.env["res.config.settings"].with_user(self.admin).create({
            "letsbot_watch_sale": True, "letsbot_watch_invoice": False, "letsbot_watch_picking": False,
            "letsbot_watch_lead": True, "letsbot_watch_product": False})
        settings.execute()
        self.assertEqual(self.Params.get_param(P + "models"), "sale.order,crm.lead")
        fresh = self.env["res.config.settings"].with_user(self.admin).create({})
        self.assertTrue(fresh.letsbot_watch_sale)
        self.assertFalse(fresh.letsbot_watch_invoice)
        self.assertEqual(fresh.letsbot_status, "disconnected")
