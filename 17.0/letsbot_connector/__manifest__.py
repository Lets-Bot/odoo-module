# Part of LetsBot Connector. See LICENSE file for full copyright and licensing details.
{
    "name": "LetsBot WhatsApp Connector",
    "summary": "Connect Odoo to LetsBot (WhatsApp AI inbox) in one click: "
               "secure pairing and signed real-time webhooks.",
    "version": "17.0.1.0.0",
    "category": "Sales",
    "author": "LetsBot",
    "website": "https://letsbot.net",
    "maintainer": "LetsBot",
    "support": "support@letsbot.net",
    "license": "LGPL-3",
    "depends": ["base_setup", "mail"],
    "data": [
        "security/letsbot_security.xml",
        "security/ir.model.access.csv",
        "data/ir_cron.xml",
        "views/webhook_event_views.xml",
        "views/res_config_settings_views.xml",
        "views/res_partner_views.xml",
    ],
    "images": ["static/description/banner.png"],
    "installable": True,
    "application": True,
    "auto_install": False,
}
