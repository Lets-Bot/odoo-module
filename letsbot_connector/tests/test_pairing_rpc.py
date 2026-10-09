# Part of LetsBot Connector. See LICENSE file for full copyright and licensing details.
"""End-to-end: LetsBot confirms the pairing through Odoo's real external API
with the handed-off key (JSON-RPC on every series, JSON-2 on 19+)."""
import json

from odoo import release
from odoo.tests import HttpCase, tagged

from .common import CONNECT_URL, P, SECRET, WEBHOOK_URL, FakeResponse, mock_post


@tagged("post_install", "-at_install", "letsbot")
class TestPairingRpc(HttpCase):

    def _pair(self):
        Params = self.env["ir.config_parameter"].sudo()
        Params.set_param(P + "connect_url", CONNECT_URL)
        admin = self.env.ref("base.user_admin")
        with mock_post(FakeResponse(201, {"redirect_url": CONNECT_URL + "?code=x"})) as rec:
            self.env["letsbot.pairing"].with_user(admin).action_start_pairing()
        return json.loads(rec.calls[0]["data"])

    def _jsonrpc(self, service, method, *args):
        response = self.url_open("/jsonrpc", data=json.dumps({
            "jsonrpc": "2.0", "method": "call", "id": 1,
            "params": {"service": service, "method": method, "args": list(args)},
        }), headers={"Content-Type": "application/json"})
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_confirm_over_jsonrpc(self):
        payload = self._pair()
        db, key = payload["db"], payload["key"]
        uid = self._jsonrpc("common", "authenticate", db, payload["login"], key, {})["result"]
        self.assertEqual(uid, payload["uid"])
        result = self._jsonrpc("object", "execute_kw", db, uid, key, "letsbot.pairing", "letsbot_confirm_pairing",
                               [payload["state"], WEBHOOK_URL, SECRET], {"account_label": "Acme"})
        self.assertNotIn("error", result, result.get("error"))
        self.assertTrue(result["result"]["ok"])
        self.assertEqual(self.env["ir.config_parameter"].sudo().get_param(P + "status"), "connected")
        ping = self._jsonrpc("object", "execute_kw", db, uid, key, "letsbot.pairing", "letsbot_ping", [], {})
        self.assertEqual(ping["result"]["status"], "connected")
        # the key cannot touch admin-only data (it is not a system user)
        denied = self._jsonrpc("object", "execute_kw", db, uid, key, "ir.config_parameter", "search_read",
                               [[["key", "=", P + "webhook_secret"]]], {"fields": ["value"]})
        self.assertIn("error", denied)

    def test_confirm_over_json2(self):
        if release.version_info[0] < 19:
            self.skipTest("JSON-2 API exists from Odoo 19")
        payload = self._pair()
        response = self.url_open(
            "/json/2/letsbot.pairing/letsbot_confirm_pairing",
            data=json.dumps({"state": payload["state"], "webhook_url": WEBHOOK_URL, "webhook_secret": SECRET}),
            headers={"Content-Type": "application/json", "Authorization": "bearer " + payload["key"],
                     "X-Odoo-Database": payload["db"]})
        self.assertEqual(response.status_code, 200, response.text[:500])
        self.assertTrue(response.json()["ok"])
