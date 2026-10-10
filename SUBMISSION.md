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
| Name | LetsBot WhatsApp AI Inbox (25 characters, the store maximum; was "LetsBot WhatsApp Connector" up to 1.0.0) | `name` |
| Summary | AI agent and omnichannel inbox powered by your Odoo data: WhatsApp, Instagram, Messenger, Telegram and email. | `summary` |
| Category | Sales | `category` (alternative: Discuss) |
| License | LGPL-3 | `license` + LICENSE file |
| Price | **Free** (no `price`/`currency` keys in the manifest) | decision 11.1 #2 |
| Author / website / support | LetsBot / https://letsbot.net / support@letsbot.net | manifest |
| Depends | `base_setup`, `mail` (Community-compatible; no Enterprise dependency) | manifest |
| Icon | `static/description/icon.png` (256×256, white LetsBot mark on brand purple #6517ab) | done |
| Main image | `static/description/letsbot_cover.png` (2240×1120, 2:1, `images` key) | done |
| Feature images | `static/description/feature_01_…08_*.png` (2560×1600, 16:10, < 300 KB each) used by `index.html` | done |
| Description page | `static/description/index.html` (English, no JS, inline styles only, Bootstrap grid classes; external links are stripped by the store, so only `mailto:` is linked) | done |
| README | `README.rst` | done |
| Translations | `i18n/letsbot_connector.pot`, `ar.po`, `es.po`, `pt.po` | done |

## 4. Listing images (done in 1.0.1)

All images live in `static/description/` and are referenced relatively from `index.html`:

| File | Content |
|---|---|
| `letsbot_cover.png` | Store cover: headline, live chat with the Odoo panel, WhatsApp AI answer |
| `feature_01_ai_agent.png` | AI agent answering on WhatsApp from Odoo (product, stock, order status) |
| `feature_02_customer_360.png` | Customer 360 (Odoo tab) inside LetsBot live chat |
| `feature_03_odoo_panel.png` | Odoo overview and product catalog in LetsBot |
| `feature_04_invoices.png` | Invoices with WhatsApp payment reminders |
| `feature_05_automations.png` | WhatsApp automations triggered by Odoo events |
| `feature_06_connect.png` | Odoo Settings → LetsBot WhatsApp (real Odoo 19 screenshot, disconnected + connected) |
| `feature_07_omnichannel.png` | LetsBot suite: one inbox for every channel, WhatsApp calls, apps |
| `feature_08_suite.png` | LetsBot suite: AI agents, CRM, campaigns, tickets, automations, analytics |

Rules kept: English only, demo data only (no customer PII), PNG, each < 500 KB, whole folder < 6 MB.
To change an image, re-render the HTML compositions and re-optimise (libimagequant), then bump the version.

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
