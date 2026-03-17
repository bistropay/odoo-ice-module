# -*- coding: utf-8 -*-
{
    "name": "Ecuador ICE Tax - Beer",
    "summary": "ICE tax computation, SRI Form 105 reporting and EDI integration for artisanal breweries in Ecuador",
    "version": "17.0.1.0.0",
    "countries": ["ec"],
    "category": "Accounting/Localizations",
    "author": "BistroPay",
    "website": "https://www.bistro-pay.com",
    "support": "soporte@bistro-pay.com",
    "license": "OPL-1",
    "price": 285.99,
    "currency": "USD",
    "depends": [
        "l10n_ec_edi",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/ice_tax_data.xml",
        "report/ice_report_105_template.xml",
        "wizard/ice_report_105_wizard_views.xml",
        "views/ice_rate_views.xml",
        "views/product_views.xml",
        "views/menuitems.xml",
    ],
    "demo": [
        "demo/demo_data.xml",
    ],
    "images": [
        "static/description/icon.png",
    ],
    "installable": True,
    "auto_install": False,
    "application": False,
}
