# Part of LetsBot Connector. See LICENSE file for full copyright and licensing details.
{
    "name": "LetsBot WhatsApp AI Inbox",
    "summary": "AI agent and omnichannel inbox powered by your Odoo data: "
               "WhatsApp, Instagram, Messenger, Telegram and email.",
    "version": "18.0.1.0.1",
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
    "images": ["static/description/letsbot_cover.png"],
    "installable": True,
    "application": True,
    "auto_install": False,
}
