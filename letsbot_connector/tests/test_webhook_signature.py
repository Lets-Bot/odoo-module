# Part of LetsBot Connector. See LICENSE file for full copyright and licensing details.
import hashlib
import hmac
import json

from odoo.tests import tagged

from odoo.addons.letsbot_connector.models import letsbot_tools as lt

from .common import SECRET, WEBHOOK_URL, LetsbotCase, FakeResponse, mock_post


@tagged("post_install", "-at_install", "letsbot")
class TestWebhookSignature(LetsbotCase):

    def test_known_vector(self):
        body = b'{"a":1}'
        expected = hmac.new(b"topsecret", b'1700000000.{"a":1}', hashlib.sha256).hexdigest()
        self.assertEqual(lt.compute_signature("topsecret", body, 1700000000), expected)
        self.assertEqual(lt.signature_header("topsecret", body, 1700000000), "t=1700000000,v1=" + expected)

    def test_verify_roundtrip_and_tampering(self):
        body = lt.dumps({"event": "sale.order.updated", "res_id": 7})
        header = lt.signature_header(SECRET, body, 1700000000)
        self.assertTrue(lt.verify_signature(SECRET, body, header, now=1700000100))
        self.assertFalse(lt.verify_signature(SECRET, body + b" ", header, now=1700000100), "tampered body")
        self.assertFalse(lt.verify_signature("other" * 10, body, header, now=1700000100), "wrong secret")
        self.assertFalse(lt.verify_signature(SECRET, body, header, now=1700000000 + 301), "replay window")
        self.assertFalse(lt.verify_signature(SECRET, body, "garbage", now=1700000000))
        self.assertFalse(lt.verify_signature(SECRET, body, "", now=1700000000))
        rotated = "t=1700000000,v1=%s,v1=%s" % ("0" * 64, lt.compute_signature(SECRET, body, 1700000000))
        self.assertTrue(lt.verify_signature(SECRET, body, rotated, now=1700000000), "any v1 may match")

    def test_canonical_json(self):
        self.assertEqual(lt.dumps({"b": 1, "a": "\u0645"}), '{"a":"\u0645","b":1}'.encode("utf-8"))

    def test_post_signs_the_exact_body(self):
        with mock_post(FakeResponse(204)) as rec:
            code, error = self.Events._letsbot_post(WEBHOOK_URL, SECRET, {"event": "connector.ping", "id": "x1"})
        self.assertEqual((code, error), (204, False))
        call = rec.calls[0]
        self.assertEqual(call["url"], WEBHOOK_URL)
        self.assertFalse(call["allow_redirects"])
        self.assertTrue(call["timeout"])
        headers = call["headers"]
        self.assertTrue(lt.verify_signature(SECRET, call["data"], headers["X-LetsBot-Signature"]))
        self.assertRegex(headers["X-LetsBot-Signature"], r"^t=\d+,v1=[0-9a-f]{64}$")
        self.assertEqual(headers["X-LetsBot-Event"], "connector.ping")
        self.assertEqual(headers["X-LetsBot-Delivery"], "x1")
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertEqual(json.loads(call["data"]), {"event": "connector.ping", "id": "x1"})

    def test_payload_carries_ids_and_state_only(self):
        self._connect()
        partner = self.env["res.partner"].create({"name": "Secret Customer", "email": "vip@example.com",
                                                  "phone": "+20 100 123 4567"})
        event = self._events(model="res.partner", res_id=partner.id)
        self.assertEqual(len(event), 1)
        with mock_post(FakeResponse(200)) as rec:
            self.Events._cron_dispatch()
        body = rec.calls[0]["data"]
        payload = json.loads(body)
        self.assertEqual(set(payload), {"api_version", "id", "event", "model", "res_id", "write_date",
                                        "values", "company_id", "db", "attempt", "created_at"})
        self.assertEqual(payload["event"], "res.partner.created")
        self.assertEqual(payload["res_id"], partner.id)
        self.assertEqual(payload["db"], self.env.cr.dbname)
        self.assertEqual(payload["values"], {})
        for leaked in (b"Secret Customer", b"vip@example.com", b"123 4567"):
            self.assertNotIn(leaked, body)
        self.assertTrue(lt.verify_signature(SECRET, body, rec.calls[0]["headers"]["X-LetsBot-Signature"]))

    def test_url_guard(self):
        self.assertEqual(lt.check_url(" https://letsbot.net/x "), "https://letsbot.net/x")
        for bad in ("http://letsbot.net/x", "ftp://letsbot.net", "https://user:pw@letsbot.net/", "", None,
                    "javascript:alert(1)"):
            with self.assertRaises(ValueError):
                lt.check_url(bad)
        self.assertEqual(lt.check_url("http://localhost:8000/x", allow_http=True), "http://localhost:8000/x")
        self.assertTrue(lt.same_site("https://acme.letsbot.net/a", "https://letsbot.net/odoo/connect"))
        self.assertTrue(lt.same_site("https://letsbot.net/a", "https://www.letsbot.net/odoo/connect"))
        self.assertFalse(lt.same_site("https://letsbot.net.evil.com/a", "https://letsbot.net/odoo/connect"))
        self.assertFalse(lt.same_site("https://evilletsbot.net/a", "https://letsbot.net/odoo/connect"))
