#!/usr/bin/env python3
"""Minimal *fake LetsBot* implementing LETSBOT-CONTRACT.md (stdlib only).

Dev and E2E tool, not production code. It shows the Laravel side what to do:

  POST /odoo/connect            pairing handoff -> {"redirect_url": ".../odoo/connect?code=..."}
  GET  /odoo/connect?code=...   "browser landing": verify key via JSON-RPC, confirm pairing in Odoo
  POST /odoo-webhook/<token>    verify X-LetsBot-Signature, log the event (410 for unknown tokens)
  GET  /_log                    JSON log of everything (for assertions)

Env: PORT (8765), PUBLIC_URL (http://lbhook:8765), ODOO_URL_OVERRIDE (rewrite base_url, e.g. http://lbodoo:8069)
"""
import hashlib
import hmac
import json
import os
import secrets
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

PORT = int(os.environ.get("PORT", "8765"))
PUBLIC = os.environ.get("PUBLIC_URL", "http://lbhook:%d" % PORT)
ODOO_OVERRIDE = os.environ.get("ODOO_URL_OVERRIDE")
PENDING, CONNECTIONS, LOG = {}, {}, []


def verify(secret, body, header, tolerance=300):
    parts = {}
    for item in (header or "").split(","):
        k, _, v = item.strip().partition("=")
        parts.setdefault(k, []).append(v)
    try:
        ts = int(parts["t"][0])
    except (KeyError, ValueError):
        return False
    if abs(time.time() - ts) > tolerance:
        return False
    expected = hmac.new(secret.encode(), str(ts).encode() + b"." + body, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, c) for c in parts.get("v1", []))


def jsonrpc(base, service, method, *args):
    req = urllib.request.Request(base + "/jsonrpc", data=json.dumps({
        "jsonrpc": "2.0", "method": "call", "id": 1,
        "params": {"service": service, "method": method, "args": list(args)}}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        path = urlsplit(self.path).path
        if path == "/odoo/connect":
            data = json.loads(raw)
            ok = data.get("protocol") == 1 and data.get("type") == "odoo.pairing" and len(data.get("key", "")) == 40
            if not ok:
                return self._send(422, {"error": "invalid handoff"})
            code = "pc_" + secrets.token_urlsafe(16)
            PENDING[code] = data  # NOTE: must NOT call Odoo here (key not committed yet)
            LOG.append({"kind": "handoff", "db": data["db"], "version": data["version"], "login": data["login"],
                        "key_expires_at": data["key_expires_at"], "company": data["company"]["name"]})
            return self._send(201, {"redirect_url": PUBLIC + "/odoo/connect?code=" + code})
        if path.startswith("/odoo-webhook/"):
            token = path.rsplit("/", 1)[-1]
            conn = CONNECTIONS.get(token)
            if not conn:
                return self._send(410, {"error": "gone"})
            valid = verify(conn["secret"], raw, self.headers.get("X-LetsBot-Signature"))
            LOG.append({"kind": "webhook", "valid_signature": valid, "headers": {
                k: self.headers.get(k) for k in ("X-LetsBot-Event", "X-LetsBot-Delivery", "X-Odoo-Database")},
                "body": json.loads(raw)})
            return self._send(200 if valid else 401, {"ok": valid})
        self._send(404, {})

    def do_GET(self):
        url = urlsplit(self.path)
        if url.path == "/_log":
            return self._send(200, LOG)
        if url.path == "/odoo/connect":
            code = parse_qs(url.query).get("code", [""])[0]
            data = PENDING.pop(code, None)
            if not data:
                return self._send(404, {"error": "unknown code"})
            base = ODOO_OVERRIDE or data["base_url"]
            uid = jsonrpc(base, "common", "authenticate", data["db"], data["login"], data["key"], {}).get("result")
            token, secret = secrets.token_urlsafe(30), secrets.token_hex(32)
            CONNECTIONS[token] = {"secret": secret, "db": data["db"]}
            confirm = jsonrpc(base, "object", "execute_kw", data["db"], uid, data["key"], "letsbot.pairing",
                              "letsbot_confirm_pairing", [data["state"], PUBLIC + "/odoo-webhook/" + token, secret],
                              {"account_label": "Fake LetsBot", "conversation_url": PUBLIC + "/inbox?phone={phone}"})
            ping = jsonrpc(base, "object", "execute_kw", data["db"], uid, data["key"], "letsbot.pairing",
                           "letsbot_ping", [], {})
            LOG.append({"kind": "confirm", "uid": uid, "confirm": confirm, "ping": ping})
            return self._send(200, {"authenticated_uid": uid, "confirm": confirm, "return_url": data["return_url"]})
        self._send(404, {})

    def log_message(self, fmt, *args):
        print("fake-letsbot:", fmt % args, flush=True)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
