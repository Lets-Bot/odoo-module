# Part of LetsBot Connector. See LICENSE file for full copyright and licensing details.
"""Pure helpers shared by the connector (no ORM state, unit-testable).

Signature scheme (identical to what LetsBot verifies, see LETSBOT-CONTRACT.md):

    X-LetsBot-Signature: t=<unix seconds>,v1=<hex HMAC-SHA256(secret, "<t>.<raw body>")>
"""
import hashlib
import hmac
import json
import time
from urllib.parse import urlsplit

PARAM_PREFIX = "letsbot_connector."
DEFAULT_CONNECT_URL = "https://letsbot.net/odoo/connect"
DEFAULT_MODELS = "sale.order,account.move,stock.picking,crm.lead"
API_KEY_NAME = "LetsBot Connector"
INTEGRATION_LOGIN = "letsbot-integration"
PROTOCOL_VERSION = 1
SIGNATURE_TOLERANCE = 300  # seconds
PAIRING_TTL = 15 * 60  # seconds
HTTP_TIMEOUT = 10  # seconds
# Retry schedule in minutes after the 1st, 2nd, ... failure (~1.9 days total).
BACKOFF_MINUTES = (1, 5, 15, 60, 180, 360, 720, 1440)
MAX_ATTEMPTS = len(BACKOFF_MINUTES)

# Watched models -> the only "state-like" fields we put in the payload.
# Everything else is re-read by LetsBot through the external API.
STATE_FIELDS = {
    "sale.order": ("state",),
    "account.move": ("state", "payment_state"),
    "stock.picking": ("state",),
    "crm.lead": ("stage_id", "active"),
    "product.template": ("active",),
}
# Writes touching only these fields never produce an event (pure noise).
NOISE_FIELDS = frozenset({
    "access_token", "message_main_attachment_id", "message_follower_ids",
    "message_ids", "activity_ids", "website_message_ids", "write_date",
    "write_uid", "message_is_follower", "message_partner_ids", "rating_ids",
    "is_move_sent", "invoice_pdf_report_id", "invoice_pdf_report_file",
})


def compute_signature(secret, body, timestamp):
    """Return the hex HMAC-SHA256 of ``"<timestamp>.<body>"``.

    :param str secret: shared webhook secret
    :param bytes body: the exact bytes sent as HTTP body
    :param int timestamp: unix seconds
    """
    if isinstance(body, str):
        body = body.encode("utf-8")
    message = str(int(timestamp)).encode("ascii") + b"." + body
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def signature_header(secret, body, timestamp=None):
    timestamp = int(time.time() if timestamp is None else timestamp)
    return "t=%d,v1=%s" % (timestamp, compute_signature(secret, body, timestamp))


def verify_signature(secret, body, header, tolerance=SIGNATURE_TOLERANCE, now=None):
    """Reference verifier (the algorithm LetsBot must implement)."""
    if not secret or not header:
        return False
    parts = {}
    for item in header.split(","):
        key, sep, value = item.strip().partition("=")
        if sep:
            parts.setdefault(key, []).append(value)
    try:
        timestamp = int(parts["t"][0])
    except (KeyError, ValueError, IndexError):
        return False
    now = int(time.time() if now is None else now)
    if abs(now - timestamp) > tolerance:
        return False
    expected = compute_signature(secret, body, timestamp)
    return any(hmac.compare_digest(expected, candidate) for candidate in parts.get("v1", []))


def dumps(payload):
    """Canonical compact JSON bytes (the bytes that get signed)."""
    return json.dumps(payload, separators=(",", ":"), sort_keys=True, ensure_ascii=False).encode("utf-8")


def check_url(url, allow_http=False):
    """Return a normalized URL or raise ValueError. https only unless allow_http."""
    if not url or not isinstance(url, str):
        raise ValueError("empty URL")
    url = url.strip()
    parts = urlsplit(url)
    allowed = ("https", "http") if allow_http else ("https",)
    if parts.scheme not in allowed:
        raise ValueError("URL must use https")
    if not parts.hostname or parts.username or parts.password:
        raise ValueError("URL must have a host and no credentials")
    if any(ch in url for ch in (" ", "\\", "\n", "\r")):
        raise ValueError("URL contains forbidden characters")
    return url


def same_site(url, reference_url):
    """True if url's host equals reference host or is one of its subdomains."""
    host = (urlsplit(url).hostname or "").lower()
    ref = (urlsplit(reference_url).hostname or "").lower()
    if not host or not ref:
        return False
    if ref.startswith("www."):
        ref = ref[4:]
    return host == ref or host.endswith("." + ref) or host == "www." + ref


def hash_token(value):
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()
