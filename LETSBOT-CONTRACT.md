# LetsBot ⇄ `letsbot_connector` contract (protocol v1)

What the LetsBot side (Laravel, `packages/odoo`) has to implement so the official Odoo module works.
The source of truth is the module code: `src/letsbot_connector/models/{letsbot_pairing,webhook_event,letsbot_tools}.py`.
The tests in `src/letsbot_connector/tests/` pin every rule below.

There are three interactions:

| # | Direction | What | LetsBot work |
|---|---|---|---|
| A | Odoo → LetsBot, server-to-server | **Pairing handoff** `POST /odoo/connect` (JSON) | new endpoint |
| B | Browser → LetsBot → Odoo external API | **Merchant lands on LetsBot, LetsBot confirms** via `letsbot.pairing.letsbot_confirm_pairing` | new page + one RPC call |
| C | Odoo → LetsBot, server-to-server | **Signed webhooks** `POST <webhook_url>` (e.g. `/odoo-webhook/{token}`) | add signature check to the receiver |

---

## A. Pairing handoff: `POST https://letsbot.net/odoo/connect`

The URL is configurable in Odoo (Settings → LetsBot WhatsApp → Advanced → *LetsBot Connect URL*,
param `letsbot_connector.connect_url`). The default is `https://letsbot.net/odoo/connect`. The same path serves two methods:
`POST` (JSON) is the server-to-server handoff, and `GET ?code=…` is the browser landing page.

The module requires `https`. `http` is allowed only when the Odoo system parameter
`letsbot_connector.allow_insecure_http = 1` is set, which is meant for local dev.

### Request (sent by the Odoo server, not the browser)

```
POST /odoo/connect
Content-Type: application/json
Accept: application/json
User-Agent: LetsBot-Odoo-Connector (Odoo 18.0-20260926)
```
```json
{
  "protocol": 1,
  "type": "odoo.pairing",
  "state": "eyJkYiI6ImxiX2RlbW8iLC4uLn0.6c1f…(64 hex)",
  "db": "lb_demo",
  "base_url": "https://acme.odoo.com",
  "version": "18.0",
  "server_version": "18.0-20260926",
  "module_version": "18.0.1.0.0",
  "login": "letsbot-integration",
  "uid": 7,
  "key": "<40 hex chars: a standard res.users.apikeys key, scope=null (rpc)>",
  "key_expires_at": "2027-01-06 12:00:00",
  "company": {"id": 1, "name": "Acme", "currency": "SAR", "country_code": "SA"},
  "companies": [{"id": 1, "name": "Acme", "currency": "SAR", "country_code": "SA"}],
  "lang": "ar_001",
  "tz": "Asia/Riyadh",
  "admin": {"name": "Mitchell Admin", "email": "admin@acme.com"},
  "return_url": "https://acme.odoo.com/web#action=base_setup.action_general_configuration",
  "confirm": {"model": "letsbot.pairing", "method": "letsbot_confirm_pairing"},
  "pairing_ttl": 900
}
```

- `key_expires_at` is a naive UTC string `YYYY-MM-DD HH:MM:SS`. It is **`null` on Odoo 17**, where keys don't expire.
  On 18/19 the default is 90 days, and the merchant can set 1–365.
- `state` is opaque to LetsBot. Store it and echo it back unchanged in step B. It is signed with the Odoo database secret,
  single-use, and bound to the db and the integration user. It expires after `pairing_ttl` seconds (15 min).
- `login`/`uid` belong to the dedicated *LetsBot Integration* internal user (or a user the admin picked). It is never a
  system admin unless the admin picks one. Groups: Internal User, Contact Creation, plus (when installed) Sales: All
  Documents, Invoicing: Billing, Inventory: User.
- `base_url` is Odoo's `web.base.url`. Run it through the existing `OdooEndpointGuard` (SSRF rules from plan §5) before any call.

### LetsBot must

1. Validate the shape. `protocol == 1`, `type == "odoo.pairing"`. Apply size limits and check that `key` matches `^[0-9a-f]{40}$`.
   Rate-limit per source IP.
2. **Do NOT call Odoo with the key inside this request.** The key is created in the same Odoo transaction that is
   waiting for your answer, so it is not committed yet. Verify it in step B.
3. Persist a *pending pairing* (encrypted `key`, plus all the fields above) under a random one-time `code`
   (≥128 bits, TTL = `pairing_ttl`, single use).
4. Answer **200 or 201** with JSON:
   ```json
   {"redirect_url": "https://letsbot.net/odoo/connect?code=pc_9f3…"}
   ```
   `redirect_url` must be `https` and its host must be the connect-URL host or one of its subdomains
   (`letsbot.net`, `*.letsbot.net`). Otherwise the module refuses it (open-redirect guard).
   Any other status, or a non-JSON body, makes Odoo show an error and **roll back the key**.

Redirects are not followed (`allow_redirects=False`), and the timeout is 10 s.

## B. Browser landing + confirmation

1. The Odoo admin's browser is sent to `redirect_url`. LetsBot authenticates the merchant (login or sign-up) and lets them
   pick the workspace/tenant. Only `manage-odoo` / super-admin can do this.
2. LetsBot now verifies the key exactly like the existing connect wizard (`OdooClient`): detect the version via
   `POST {base_url}/web/webclient/version_info`, then `common.authenticate(db, login, key)` (JSON-RPC) or JSON-2 on 19.
   Store the connection (key encrypted, `key_expires_at`, `version`, company) with `source = 'odoo_app'`.
3. Mint the webhook credentials for that connection:
   - `webhook_url`: the tenant receiver, e.g. `https://acme.letsbot.net/odoo-webhook/{token}` (40-char random token,
     stored hashed, as in plan §5). It must be `https`.
   - `webhook_secret`: ≥ 32 chars (recommend 64 hex chars from 32 random bytes), stored encrypted.
4. Call Odoo **with the handed-off key, as the integration user**:

   JSON-RPC (17/18/19):
   ```json
   POST {base_url}/jsonrpc
   {"jsonrpc":"2.0","method":"call","id":1,"params":{"service":"object","method":"execute_kw",
     "args":["<db>", <uid>, "<key>", "letsbot.pairing", "letsbot_confirm_pairing",
             ["<state>", "<webhook_url>", "<webhook_secret>"],
             {"account_label": "Acme Store (LetsBot)",
              "conversation_url": "https://acme.letsbot.net/panel/v2/inbox?phone={phone}"}]}}
   ```
   JSON-2 (19), using named args:
   ```
   POST {base_url}/json/2/letsbot.pairing/letsbot_confirm_pairing
   Authorization: bearer <key>
   X-Odoo-Database: <db>
   {"state":"…","webhook_url":"…","webhook_secret":"…","account_label":"…","conversation_url":"…"}
   ```
   On success it returns `{"ok": true, "db": "...", "version": "18.0", "module_version": "18.0.1.0.0",
   "models": ["sale.order","account.move","stock.picking","crm.lead"]}`.
   The JSON-2 response is the bare object. JSON-RPC wraps it in `result`.

   Errors, mapped by exception name (see SPIKE-REPORT §3):
   | name | meaning |
   |---|---|
   | `odoo.exceptions.AccessError` | bad, expired, replayed or superseded `state`, or the call was not made with the integration user's key → restart pairing |
   | `odoo.exceptions.UserError` | `webhook_url`/`conversation_url` is not https, or the secret is shorter than 32 characters |
   | `AccessDenied` / 401 | key invalid (should not happen) |

   `state` is single-use. A second confirm returns `AccessError`. If the admin clicked *Connect* again, only the latest
   `state` is valid. On confirm, Odoo **revokes every older "LetsBot Connector" key** of that user, which rotates the key on
   reconnect. Optional `conversation_url` placeholders are `{phone}` (E.164 digits without `+`) and `{partner_id}`. The URL is
   used by the *WhatsApp (LetsBot)* button on contacts.
5. Redirect the browser to the `return_url` from step A (the Odoo settings page). The page now shows **Connected**.
   On failure, show the human-readable error in LetsBot and offer *Try again*, which just links to `return_url`.

### Other RPC methods (integration user's key)

| method | args | returns / effect |
|---|---|---|
| `letsbot.pairing.letsbot_ping` | – | `{"ok":true,"status":"connected","version":"18.0","module_version":…,"models":[…],"queue_pending":0}`. It also updates *Last contact* in Odoo. Call it from the hourly health check: it detects that the module is installed and which version. |
| `letsbot.pairing.letsbot_disconnect` | – | Revokes the key and stops webhooks. Call it when the merchant disconnects in LetsBot, **before** discarding the key. Plan §5: "on disconnect delete the key". |

Key renewal on 18/19: when `key_expires_at` gets close, send the merchant to Odoo → *Reconnect*. Step A runs again
and rotates the key. The module never extends a key silently.

## C. Signed webhooks

### Request

```
POST <webhook_url>
Content-Type: application/json
User-Agent: LetsBot-Odoo-Connector/18.0.1.0.0 (Odoo 18.0-20260926)
X-LetsBot-Signature: t=1791484583,v1=5d41402abc4b2a76b9719d911017c592…(64 hex)
X-LetsBot-Event: sale.order.updated
X-LetsBot-Delivery: 0b6c3f0e-6a59-4e0e-9a1b-0d4bb0c7c2a1
X-Odoo-Database: lb_demo
```
Body (compact JSON, keys sorted; these exact bytes are signed):
```json
{"api_version":1,"attempt":1,"company_id":1,"created_at":"2026-10-08 14:00:31","db":"lb_demo",
 "event":"sale.order.updated","id":"0b6c3f0e-6a59-4e0e-9a1b-0d4bb0c7c2a1","model":"sale.order",
 "res_id":41,"values":{"state":"sale"},"write_date":"2026-10-08 14:00:31"}
```

| event | model | `values` (only these) | filter |
|---|---|---|---|
| `sale.order.{created,updated,deleted}` | sale.order | `state` | all |
| `account.move.{…}` | account.move | `state`, `payment_state` | `move_type ∈ {out_invoice, out_refund}` only |
| `stock.picking.{…}` | stock.picking | `state` | `picking_type_code = outgoing` only |
| `crm.lead.{…}` | crm.lead | `stage_id` (int), `active` | all |
| `product.template.{…}` | product.template | `active` | off by default |
| `connector.ping` | – | – | sent by the *Send test event* button. Body is `{"api_version","id","event","db"}` |
| `connector.disconnected` | – | – | best effort, sent when the admin clicks *Disconnect* in Odoo. Mark the connection disconnected and stop calling Odoo. |

On `deleted`, `values` is `{}`. Datetimes are naive UTC. `write_date` is the record's `write_date`, which can be `null` for deleted rows.
**No names, amounts, phones or e-mails are ever sent.** Each event is a "re-fetch `model`/`res_id`" signal, the same as plan §2,
so the existing `OdooWebhookEvent` + re-read pipeline applies unchanged.

### Verification algorithm (LetsBot MUST implement exactly this)

```
header  = request.header("X-LetsBot-Signature")          # "t=<int>,v1=<hex>[,v1=<hex>…]"
parse comma-separated k=v pairs; t = int(first "t"); candidates = all "v1"
reject if |now - t| > 300 s                                # replay window
expected = hex(HMAC_SHA256(key = webhook_secret (utf-8), msg = "<t>." + raw_body_bytes))
accept if any(hash_equals(expected, c) for c in candidates)
```
Use the **raw** request body. Never re-encode the parsed JSON. PHP:
```php
[$t, $sigs] = parseHeader($request->header('X-LetsBot-Signature'));
$ok = abs(time() - $t) <= 300 && collect($sigs)->contains(
    fn ($s) => hash_equals(hash_hmac('sha256', $t.'.'.$request->getContent(), $secret), $s));
```
Multiple `v1` values let the secret rotate: during rotation, check both secrets. A reference implementation and test vectors
live in `letsbot_tools.verify_signature` and `tests/test_webhook_signature.py`. For example,
`HMAC_SHA256("topsecret", '1700000000.{"a":1}')` → header `t=1700000000,v1=<that hex>`.

### Receiver behaviour → module behaviour

| LetsBot answers | module does |
|---|---|
| any **2xx** (return fast. Queue the re-read, don't do it inline) | marks the event *sent* and updates *Last contact* |
| **410 Gone** | marks the event dead and sets the connection status to **revoked**. Stops queueing. The admin sees "Disconnected by LetsBot" and must reconnect. Use this when the token is unknown or the tenant is disconnected. |
| 401/403 (bad signature), 404, 429, 5xx, timeout (10 s), network error | retries with backoff of 1 m, 5 m, 15 m, 1 h, 3 h, 6 h, 12 h, 24 h. After 8 attempts the event is dead (visible in Settings → Technical → LetsBot Webhook Events, with a *Retry* button). |

Idempotency: dedupe on `id`, which is stable across retries; `attempt` grows. Also dedupe on `(model, res_id, write_date)`.
Unsent events for the same record are collapsed in Odoo, so expect at most roughly one event per record per minute under load.
Ordering is not guaranteed. Always re-read the record.

Rate: the cron sends at most 200 events per run and runs every minute. It is also triggered right after each commit that
queued something, so latency is usually under a few seconds when the Odoo cron workers are running.

---

## Summary for the Laravel side (`packages/odoo`)

1. `POST /odoo/connect`: unauthenticated JSON handoff. Validate the payload, store a pending pairing with a one-time `code`,
   return `{redirect_url}`. Throttle it. Never call Odoo here.
2. `GET /odoo/connect?code=…`: auth + workspace picker. Then `OdooClient` verify, create the `OdooConnection`, mint
   `webhook_url`/`webhook_secret`, `execute_kw letsbot.pairing.letsbot_confirm_pairing`, and redirect to `return_url`.
3. `/odoo-webhook/{token}`: when the connection has a `webhook_secret`, require a valid `X-LetsBot-Signature`
   (rule above). Answer 410 for unknown or disconnected tokens. Keep accepting the unsigned base_automation payload only
   for connections without a secret (the manual-key wizard path).
4. Disconnect in LetsBot: call `letsbot_disconnect`, then delete the key.
