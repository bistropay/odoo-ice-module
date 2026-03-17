# -*- coding: utf-8 -*-
import math

from odoo import models


class AccountTax(models.Model):
    _inherit = 'account.tax'

    def _compute_amount(self, base_amount, price_unit, quantity=1.0, product=None, partner=None, fixed_multiplicator=1):
        """Override para calcular el ICE usando la fórmula volumétrica para cerveza artesanal.

        Para impuestos ICE sobre productos con ice_applicable=True:
            base_ice = (grado_alcohol / 100) * (volumen_ml / 1000) * cantidad
            monto_ice = base_ice * tarifa_por_litro_alcohol_puro

        Para los demás impuestos, delega al cálculo estándar de Odoo.
        """
        self.ensure_one()
        if (
            self.tax_group_id.l10n_ec_type == 'ice'
            and product
            and product.l10n_ec_ice_applicable
        ):
            alcohol_fraction = (product.l10n_ec_ice_alcohol_degree or 0.0) / 100.0
            volume_liters = (product.l10n_ec_ice_volume_ml or 0.0) / 1000.0
            ice_base = alcohol_fraction * volume_liters * abs(quantity)

            rate_record = self.env['l10n_ec.ice.rate']._get_rate_for_product(product)
            ice_amount = round(ice_base * rate_record.rate_per_liter_pure_alcohol, 2)

            # Respetar convenciones de signo (mismo patrón que impuesto fijo en account_tax.py:596)
            if base_amount:
                return math.copysign(ice_amount, base_amount)
            return ice_amount * (1 if fixed_multiplicator >= 0 else -1)

        return super()._compute_amount(
            base_amount, price_unit, quantity, product, partner, fixed_multiplicator
        )
