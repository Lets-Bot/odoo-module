# Odoo Apps Store submission checklist: `letsbot_connector`

Status: code ready for 17.0, 18.0 and 19.0. The GitHub repo is **not created yet** (owner action). Nothing in this
folder has been git-initialised or pushed.

## 1. Repository layout (owner creates it)

The Apps Store scans **one Git repository with one branch per Odoo series**. Each branch's root holds the addon folders.

| Branch | Content to commit at repo root |
|---|---|
| `17.0` | `17.0/letsbot_connector/` + `17.0/LICENSE` |
| `18.0` | `18.0/letsbot_connector/` + `18.0/LICENSE` |
| `19.0` | `19.0/letsbot_connector/` + `19.0/LICENSE` |

Suggested repo: `github.com/Lets-Bot/odoo-apps` (public, or private with read access granted to the Odoo
Apps bot, see below). Steps per branch:
```bash
python3 build.py                              # render all series from src/
git checkout --orphan 17.0 && cp -R 17.0/* <repo>/ && git add letsbot_connector LICENSE && git commit
# repeat for 18.0, 19.0 (orphan branches, root = module folder)
```
- The manifest `version` must start with the branch series (`17.0.1.0.0`, `18.0.1.0.0`, `19.0.1.0.0`). The build does this.
- Bump `x.y.z` in `src/letsbot_connector/__manifest__.py` (via the `@@SERIES@@.1.0.0` token) for every release.
  The store only re-publishes when the version changes.
- Run `python3 build.py --check` in CI to make sure the rendered trees match `src/`.

## 2. Register on apps.odoo.com

1. Log in at https://apps.odoo.com with the LetsBot company account (the publisher name becomes "LetsBot").
2. *Upload* → **Add a repository**: `ssh://git@github.com/Lets-Bot/odoo-apps.git#17.0`, then the same with `#18.0` and `#19.0`.
   For a private repo, add Odoo's deploy key (shown on that page) to the GitHub repo's *Deploy keys* (read-only).
3. The scanner imports every module found in the branch. Wait for the "scan done" e-mail, then check the app page.

## 3. Listing fields (taken from the manifest + static/description)

| Field | Value | Source |
|---|---|---|
| Technical name | `letsbot_connector` | folder |
| Name | LetsBot WhatsApp Connector | `name` |
| Summary | Connect Odoo to LetsBot (WhatsApp AI inbox) in one click: secure pairing and signed real-time webhooks. | `summary` |
| Category | Sales | `category` (alternative: Discuss) |
| License | LGPL-3 | `license` + LICENSE file |
| Price | **Free** (no `price`/`currency` keys in the manifest) | decision 11.1 #2 |
| Author / website / support | LetsBot / https://letsbot.net / support@letsbot.net | manifest |
| Depends | `base_setup`, `mail` (Community-compatible; no Enterprise dependency) | manifest |
| Icon | `static/description/icon.png` (140×140) | done |
| Main image | `static/description/banner.png` (1024×500, `images` key) | done (generated placeholder, replace with a designed one if wanted) |
| Description page | `static/description/index.html` (English, no JS, inline styles only) | done |
| README | `README.rst` | done |
| Translations | `i18n/letsbot_connector.pot`, `ar.po`, `es.po`, `pt.po` | done |

## 4. Screenshots to produce before publishing (owner/design)

Save them under `static/description/` and reference them from `index.html` (`<img src="screenshot_1.png">`):
1. `screenshot_settings_disconnected.png`: Settings → LetsBot WhatsApp with the **Connect to LetsBot** button.
2. `screenshot_letsbot_pick_workspace.png`: the LetsBot landing page (needs the LetsBot `/odoo/connect` page first).
3. `screenshot_settings_connected.png`: status *Connected*, workspace, last contact, event toggles.
4. `screenshot_partner_button.png`: contact form with the **WhatsApp (LetsBot)** smart button.
5. `screenshot_whatsapp_answer.png`: a WhatsApp chat where the AI answers an order-status question from Odoo data.
6. Optional: `screenshot_queue.png` (Technical → LetsBot Webhook Events).

Use 1280×800+ PNG with no customer PII (use the `lb_demo` data). Capture them in English. Arabic versions are optional.

## 5. Pre-submission QA (per series)

- [x] `scripts/test_in_docker.sh <17|18|19>`: installs in a fresh DB and runs the module tests (see the README for results).
- [x] `scripts/test_in_docker.sh <17|18|19> full`: same, with sale_management/account/stock/crm installed.
- [x] `scripts/e2e_live.sh <17|18|19>`: live pairing → JSON-RPC confirm → sale order → cron-delivered signed webhook → disconnect (fake LetsBot).
- [ ] Manual: install from the Apps menu on a clean DB, connect against a staging LetsBot, confirm, send a test event,
      confirm an order → webhook received, disconnect → key revoked in *Preferences → Account Security*.
- [ ] Uninstall test: uninstall the module → no errors, settings disappear.
- [ ] Odoo.sh: the module runs there unchanged (the `requests` lib is present and outbound HTTPS is allowed).
- [ ] **Odoo Online (SaaS) cannot install custom modules.** Those merchants keep using the manual connect wizard (URL +
      login + API key). Say so on the listing ("on-premise and Odoo.sh").

## 6. Store review notes (what reviewers look for, and how this module handles it)

- No `eval`/`exec`, no external Python packages, no JS assets, no remote assets in the description.
- No data sent without admin action. Webhooks start only after an admin pairs, carry ids/status only, and are signed.
- Admin-only configuration (`base.group_system`). Secrets are in `ir.config_parameter`, which only admins can read.
- The cron is light: every minute, no-op when the queue is empty, plus `_trigger()` after commits that queued events.
  Sent/failed rows are purged after 7 days (`@api.autovacuum`).
- No monkey-patching. Change capture is an `_inherit = "mail.thread"` override.
- Integration user: a new internal user can count as a billed user on Enterprise. The listing and README mention that an
  existing user can be chosen instead (Settings → Advanced → Integration User).

## 7. After publishing

- Add the store URL to the LetsBot Odoo connect wizard ("Install our Odoo app for one-click connect").
- Watch apps.odoo.com messages and ratings. The support e-mail in the manifest receives them.
