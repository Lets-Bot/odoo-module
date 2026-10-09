# Part of LetsBot Connector. See LICENSE file for full copyright and licensing details.
from datetime import timedelta

import requests

from odoo import fields
from odoo.tests import tagged

from odoo.addons.letsbot_connector.models import letsbot_tools as lt

from .common import P, LetsbotCase, FakeResponse, mock_post


@tagged("post_install", "-at_install", "letsbot")
class TestQueueRetry(LetsbotCase):

    def _make_due(self, events):
        events.write({"next_attempt_at": fields.Datetime.now() - timedelta(seconds=1)})

    def test_nothing_queued_when_disconnected(self):
        self.Params.set_param(P + "status", False)
        self.Params.set_param(P + "models", "res.partner")
        partner = self.env["res.partner"].create({"name": "Nobody"})
        self.assertFalse(self._events(model="res.partner", res_id=partner.id))

    def test_unwatched_model_not_queued(self):
        self._connect(models="sale.order")
        partner = self.env["res.partner"].create({"name": "Not watched"})
        self.assertFalse(self._events(model="res.partner", res_id=partner.id))

    def test_enqueue_is_transactional_and_deduplicated(self):
        self._connect()
        with mock_post(AssertionError("network I/O inside the user transaction")) as rec:
            partner = self.env["res.partner"].create({"name": "Dedupe"})
            partner.write({"name": "Dedupe 2"})
            partner.write({"comment": "x"})
        self.assertFalse(rec.calls, "enqueueing must never call LetsBot synchronously")
        events = self._events(model="res.partner", res_id=partner.id)
        self.assertEqual(len(events), 1, "unsent events for the same record are collapsed")
        self.assertEqual(events.event, "res.partner.created")
        self.assertEqual(events.state, "pending")
        cron = self.env.ref("letsbot_connector.ir_cron_letsbot_webhook_dispatch")
        self.assertTrue(self.env["ir.cron.trigger"].sudo().search([("cron_id", "=", cron.id)]),
                        "the dispatcher cron is triggered (runs after commit)")

    def test_context_opt_out(self):
        self._connect()
        partner = self.env["res.partner"].with_context(letsbot_no_webhook=True).create({"name": "Quiet"})
        self.assertFalse(self._events(model="res.partner", res_id=partner.id))

    def test_backoff_then_success(self):
        self._connect()
        partner = self.env["res.partner"].create({"name": "Retry"})
        event = self._events(model="res.partner", res_id=partner.id)
        before = fields.Datetime.now()
        with mock_post(FakeResponse(500, text="boom")):
            self.Events._cron_dispatch()
        self.assertEqual(event.state, "pending")
        self.assertEqual(event.attempts, 1)
        self.assertEqual(event.last_status_code, 500)
        self.assertIn("HTTP 500", event.last_error)
        self.assertGreaterEqual(event.next_attempt_at, before + timedelta(minutes=lt.BACKOFF_MINUTES[0]) - timedelta(seconds=2))
        # not due yet -> the cron leaves it alone
        with mock_post(FakeResponse(200)) as rec:
            self.Events._cron_dispatch()
        self.assertFalse(rec.calls)
        # a network error also backs off (2nd delay)
        self._make_due(event)
        with mock_post(requests.ConnectionError("refused")):
            self.Events._cron_dispatch()
        self.assertEqual((event.state, event.attempts, event.last_status_code), ("pending", 2, 0))
        self.assertGreater(event.next_attempt_at, fields.Datetime.now() + timedelta(minutes=lt.BACKOFF_MINUTES[1] - 1))
        # a new write while a retry is pending creates a fresh event (the old one keeps its delivery id)
        partner.write({"name": "Retry 2"})
        self.assertEqual(len(self._events(model="res.partner", res_id=partner.id)), 2)
        self._make_due(event)
        with mock_post(FakeResponse(200)) as rec:
            self.Events._cron_dispatch()
        self.assertEqual(event.state, "sent")
        self.assertEqual(event.attempts, 3)
        self.assertEqual(rec.calls[0]["headers"]["X-LetsBot-Delivery"], event.uid_token)
        self.assertTrue(self.Params.get_param(P + "last_ping"))

    def test_gives_up_after_max_attempts(self):
        self._connect()
        partner = self.env["res.partner"].create({"name": "Dead"})
        event = self._events(model="res.partner", res_id=partner.id)
        with mock_post(FakeResponse(503)) as rec:
            for _i in range(lt.MAX_ATTEMPTS):
                self._make_due(event)
                self.Events._cron_dispatch()
        self.assertEqual(len(rec.calls), lt.MAX_ATTEMPTS)
        self.assertEqual(event.state, "dead")
        self.assertEqual(event.attempts, lt.MAX_ATTEMPTS)
        event.action_retry()
        self.assertEqual((event.state, event.attempts), ("pending", 0))

    def test_gone_marks_connection_revoked(self):
        self._connect()
        partner = self.env["res.partner"].create({"name": "Gone"})
        event = self._events(model="res.partner", res_id=partner.id)
        with mock_post(FakeResponse(410)):
            self.Events._cron_dispatch()
        self.assertEqual(event.state, "dead")
        self.assertEqual(self.Params.get_param(P + "status"), "revoked")
        partner.write({"name": "Gone 2"})
        self.assertEqual(len(self._events(model="res.partner", res_id=partner.id)), 1, "no new events once revoked")

    def test_deleted_event(self):
        self._connect()
        partner = self.env["res.partner"].create({"name": "To delete"})
        pid = partner.id
        partner.unlink()
        event = self._events(model="res.partner", res_id=pid)
        self.assertEqual(event.event, "res.partner.deleted")

    def test_disconnected_queue_is_not_sent(self):
        self._connect()
        partner = self.env["res.partner"].create({"name": "Late"})
        event = self._events(model="res.partner", res_id=partner.id)
        self.Params.set_param(P + "status", "disconnected")
        with mock_post(FakeResponse(200)) as rec:
            self.Events._cron_dispatch()
        self.assertFalse(rec.calls)
        self.assertEqual(event.state, "dead")
