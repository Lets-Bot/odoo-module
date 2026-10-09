#!/usr/bin/env bash
# Install letsbot_connector in a FRESH database and run its tests inside a
# throwaway container of the official odoo:<major> image, using the dev
# postgres (packages/odoo/dev, service "db"). Never touches existing DBs.
#
#   scripts/test_in_docker.sh 18            # module only (base_setup + mail)
#   scripts/test_in_docker.sh 18 full       # + sale_management, account, stock, crm
set -euo pipefail
MAJOR="${1:?usage: $0 <17|18|19> [full]}"
MODE="${2:-min}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
NETWORK="${LB_DOCKER_NETWORK:-dev_default}"
DB="letsbot_mod_test${MAJOR}${MODE/min/}"
DB="${DB/full/_full}"
INSTALL="letsbot_connector"
[ "$MODE" = "full" ] && INSTALL="sale_management,account,stock,crm,letsbot_connector"
[ -n "${SKIP_BUILD:-}" ] || python3 "$HERE/build.py" >/dev/null
docker run --rm --network "$NETWORK" \
  -e HOST=db -e USER=odoo -e PASSWORD=odoo \
  -v "$HERE/${MAJOR}.0:/mnt/letsbot:ro" \
  "odoo:${MAJOR}" odoo \
  --addons-path="/mnt/letsbot,/usr/lib/python3/dist-packages/odoo/addons" \
  -d "$DB" -i "$INSTALL" --test-enable --test-tags "/letsbot_connector" \
  --stop-after-init --log-level=test --workers=0 --max-cron-threads=0
