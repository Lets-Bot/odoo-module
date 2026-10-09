==========================
LetsBot WhatsApp Connector
==========================

Connects Odoo to `LetsBot <https://letsbot.net>`_, the WhatsApp AI inbox.

Features
========

* **One-click pairing** (Settings > LetsBot WhatsApp > *Connect to LetsBot*). The module creates a
  dedicated *LetsBot Integration* user (or uses the user you choose), generates a standard Odoo API key
  for it (with an expiry date on Odoo 18+), and sends it to LetsBot server-to-server. The key never
  goes through the browser and is never shown to anyone.
* **Signed real-time webhooks** for sales orders, customer invoices/credit notes, outgoing deliveries,
  CRM leads and (optionally) products. Payloads only contain the model, record id, last update time and
  status fields. LetsBot re-reads the record through the API.
* **Reliable delivery**: events are stored in an outbox inside the business transaction and delivered
  by a scheduled action after commit, with retries (1 min, 5 min, 15 min, 1 h, 3 h, 6 h, 12 h, 24 h).
  Unsent duplicates for the same record are collapsed.
* **WhatsApp (LetsBot)** button on contacts, opening the conversation in LetsBot.
* **Disconnect** revokes the API key, archives the dedicated user and stops all notifications.

Configuration
=============

Only administrators (*Settings* access) can see or change the configuration. Secrets are stored in
system parameters (``letsbot_connector.*``) that are only readable by administrators.

Webhook signature
=================

Every request carries ``X-LetsBot-Signature: t=<unix seconds>,v1=<hex>`` where ``v1`` is
``HMAC-SHA256(secret, "<t>.<raw body>")``. See ``LETSBOT-CONTRACT.md`` in the source repository.

Technical notes
===============

* No external Python dependency (uses ``requests``, shipped with Odoo).
* Change capture extends ``mail.thread`` so the module only depends on ``base_setup`` and ``mail``
  and works whether or not Sales, Invoicing, Inventory or CRM are installed.
* Pass ``letsbot_no_webhook=True`` in the context to silence notifications (e.g. mass imports).

Credits
=======

Author: LetsBot (https://letsbot.net). License: LGPL-3.
