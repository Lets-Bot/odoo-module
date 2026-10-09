# Part of LetsBot Connector. See LICENSE file for full copyright and licensing details.
import json
from contextlib import contextmanager
from unittest.mock import patch

import requests

from odoo.tests.common import TransactionCase

from odoo.addons.letsbot_connector.models import letsbot_tools as lt

P = lt.PARAM_PREFIX
WEBHOOK_URL = "https://acme.letsbot.net/odoo-webhook/tok_abc"
SECRET = "s" * 48
CONNECT_URL = "https://letsbot.net/odoo/connect"


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text or (json.dumps(payload) if payload is not None else "")

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class Recorder:
    """Stands in for requests.post and records every call."""

    def __init__(self, *responses):
        self.responses = list(responses) or [FakeResponse(200, {})]
        self.calls = []

    def __call__(self, url, data=None, headers=None, timeout=None, allow_redirects=True, **kw):
        self.calls.append({"url": url, "data": data, "headers": headers or {}, "timeout": timeout,
                           "allow_redirects": allow_redirects})
        response = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(response, Exception):
            raise response
        return response


@contextmanager
def mock_post(*responses):
    recorder = Recorder(*responses)
    with patch.object(requests, "post", recorder):
        yield recorder


class LetsbotCase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Params = cls.env["ir.config_parameter"].sudo()
        cls.admin = cls.env.ref("base.user_admin")
        cls.Events = cls.env["letsbot.webhook.event"].sudo()

    def _connect(self, models="res.partner"):
        for key, value in (("status", "connected"), ("webhook_url", WEBHOOK_URL),
                           ("webhook_secret", SECRET), ("models", models)):
            self.Params.set_param(P + key, value)

    def _events(self, **domain):
        dom = [(k, "=", v) for k, v in domain.items()]
        return self.Events.search(dom)
