#!/usr/bin/env bash
# Live end-to-end smoke against REAL Odoo HTTP + cron and a fake LetsBot (scripts/fake_letsbot.py):
#   install -> Connect (server-to-server handoff) -> "browser" landing -> LetsBot verifies key + confirms via JSON-RPC
#   -> confirm a sale order -> cron delivers signed webhooks -> Disconnect -> key no longer authenticates.
# Usage: scripts/e2e_live.sh 18      (uses network dev_default + service db; throwaway containers lbodoo/lbhook)
set -euo pipefail
MAJOR="${1:-18}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
NET="${LB_DOCKER_NETWORK:-dev_default}"
DB="letsbot_e2e${MAJOR}"
IMG="odoo:${MAJOR}"
ADDONS="/mnt/letsbot,/usr/lib/python3/dist-packages/odoo/addons"
DBARGS=(--db_host db --db_user odoo --db_password odoo)
INSTALL_EXTRA=(--load-language=ar_001 --without-demo=all)
[ "$MAJOR" -ge 19 ] && INSTALL_EXTRA=()   # 19: no demo by default; languages via `odoo i18n loadlang`
cleanup() { docker rm -f lbodoo lbhook >/dev/null 2>&1 || true; }
trap cleanup EXIT
cleanup

shell() {  # run python (stdin) in `odoo shell` against $DB
  docker run --rm -i --network "$NET" -v "$HERE/${MAJOR}.0:/mnt/letsbot:ro" --entrypoint odoo "$IMG" \
    shell "${DBARGS[@]}" --addons-path="$ADDONS" -d "$DB" --no-http --log-level=warn 2>/dev/null
}

echo "## 1. fresh DB with sale_management + letsbot_connector (+ Arabic on 17/18)"
docker exec dev-db-1 dropdb -U odoo --if-exists "$DB"
docker run --rm --network "$NET" -v "$HERE/${MAJOR}.0:/mnt/letsbot:ro" --entrypoint odoo "$IMG" \
  "${DBARGS[@]}" --addons-path="$ADDONS" -d "$DB" -i sale_management,letsbot_connector \
  "${INSTALL_EXTRA[@]}" --stop-after-init --log-level=warn

echo "## 2. start fake LetsBot (lbhook) + Odoo server with 1 cron thread (lbodoo)"
docker run -d --name lbhook --network "$NET" -v "$HERE/scripts:/s:ro" -e ODOO_URL_OVERRIDE=http://lbodoo:8069 \
  --entrypoint python3 "$IMG" -u /s/fake_letsbot.py >/dev/null
docker run -d --name lbodoo --network "$NET" -v "$HERE/${MAJOR}.0:/mnt/letsbot:ro" --entrypoint odoo "$IMG" \
  "${DBARGS[@]}" --addons-path="$ADDONS" -d "$DB" --db-filter="^${DB}\$" --max-cron-threads=1 --workers=0 >/dev/null
for _ in $(seq 1 60); do
  docker exec lbhook python3 -c "import urllib.request;urllib.request.urlopen('http://lbodoo:8069/web/login',timeout=2)" 2>/dev/null && break
  sleep 1
done

echo "## 3. admin clicks Connect (server-to-server handoff)"
REDIRECT=$(shell <<'PY' | grep '^REDIRECT=' | cut -d= -f2-
P = 'letsbot_connector.'
ICP = env['ir.config_parameter'].sudo()
ICP.set_param(P + 'connect_url', 'http://lbhook:8765/odoo/connect')
ICP.set_param(P + 'allow_insecure_http', '1')
ICP.set_param(P + 'models', 'sale.order,account.move,stock.picking,crm.lead')
admin = env.ref('base.user_admin')
action = env['letsbot.pairing'].with_user(admin).action_start_pairing()
env.cr.commit()
print('REDIRECT=' + action['url'])
PY
)
echo "redirect_url: $REDIRECT"

echo "## 4. merchant's browser lands on LetsBot -> LetsBot authenticates the key and confirms via JSON-RPC"
docker exec lbhook python3 -c "import urllib.request,sys;print(urllib.request.urlopen(sys.argv[1],timeout=60).read().decode())" "$REDIRECT"

echo "## 5. business change: create + confirm a sale order (cron delivers after commit)"
shell <<'PY'
P = 'letsbot_connector.'
print('status:', env['ir.config_parameter'].sudo().get_param(P + 'status'))
partner = env['res.partner'].create({'name': 'E2E WhatsApp Customer', 'phone': '+966501234567'})
product = env['product.product'].create({'name': 'E2E product', 'list_price': 10})
so = env['sale.order'].create({'partner_id': partner.id, 'order_line': [(0, 0, {'product_id': product.id})]})
env.cr.commit()
so.action_confirm()
env.cr.commit()
print('sale.order', so.id, so.state)
PY
for _ in $(seq 1 45); do
  N=$(docker exec lbhook python3 -c "import json,urllib.request;print(sum(1 for e in json.load(urllib.request.urlopen('http://localhost:8765/_log')) if e['kind']=='webhook'))")
  [ "$N" -ge 1 ] && sleep 3 && break
  sleep 2
done

echo "## 6. queue state in Odoo"
shell <<'PY'
for e in env['letsbot.webhook.event'].search([], order='id'):
    print(e.id, e.event, e.res_id, e.state, 'attempts=%s' % e.attempts, 'http=%s' % e.last_status_code, e.values_json)
PY

echo "## 7. Disconnect from Odoo (revokes key, notifies LetsBot)"
KEYCHECK=$(shell <<'PY' | grep '^KEY'
env['letsbot.pairing'].with_user(env.ref('base.user_admin')).action_disconnect()
env.cr.commit()
keys = env['res.users.apikeys'].sudo().search([('name', '=', 'LetsBot Connector')])
print('KEYS_LEFT=%d' % len(keys))
PY
)
echo "$KEYCHECK"

echo "## 8. fake LetsBot log"
docker exec lbhook python3 -c "
import json,urllib.request
log=json.load(urllib.request.urlopen('http://localhost:8765/_log'))
for e in log:
    if e['kind']=='webhook':
        print('webhook', e['headers']['X-LetsBot-Event'], 'valid_signature=%s' % e['valid_signature'], json.dumps(e['body'], sort_keys=True))
    else:
        print(e['kind'], json.dumps({k: v for k, v in e.items() if k != 'kind'}, sort_keys=True)[:400])
bad=[e for e in log if e['kind']=='webhook' and not e['valid_signature']]
print('RESULT: %d webhooks, %d with invalid signature' % (sum(e['kind']=='webhook' for e in log), len(bad)))
"
