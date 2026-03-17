# -*- coding: utf-8 -*-
from odoo import _, api, models

from odoo.addons.l10n_ec_edi.models.account_move import (
    L10N_EC_VAT_RATES,
    L10N_EC_VAT_SUBTAXES,
)


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _l10n_ec_get_taxes_grouped(self, extra_group='tax_group'):
        """Override para soportar el tipo ICE junto con IVA en el agrupamiento EDI.

        El método padre falla con KeyError cuando existen impuestos ICE
        porque L10N_EC_VAT_SUBTAXES no contiene la clave 'ice'.
        """
        self.ensure_one()

        def group_by(base_line, tax_values):
            tax_id = tax_values['tax_repartition_line'].tax_id
            ec_type = tax_id.tax_group_id.l10n_ec_type

            if ec_type == 'ice':
                product = base_line['record'].product_id
                rate_record = self.env['l10n_ec.ice.rate']._get_rate_for_product(
                    product, self.invoice_date
                )
                values = {
                    'code': 3,  # Código de tipo de impuesto SRI para ICE
                    'code_percentage': rate_record.ice_code,
                    'rate': rate_record.rate_per_liter_pure_alcohol,
                    'is_ice': True,  # Marcador para post-procesamiento de montos base
                }
            else:
                code_percentage = L10N_EC_VAT_SUBTAXES[ec_type]
                values = {
                    'code': self._l10n_ec_map_tax_groups(tax_id),
                    'code_percentage': code_percentage,
                    'rate': L10N_EC_VAT_RATES[code_percentage],
                }

            if extra_group == 'tax_group':
                values['tax_group_id'] = tax_id.tax_group_id.id
            elif extra_group == 'tax_support':
                values['taxsupport'] = tax_id.l10n_ec_code_taxsupport
            return values

        result = self._prepare_edi_tax_details(grouping_key_generator=group_by)

        # Post-proceso: para grupos ICE, reemplazar el base_amount monetario con
        # la base volumétrica (litros de alcohol puro) como requiere el SRI.
        self._l10n_ec_ice_fix_base_amounts(result)

        return result

    def _l10n_ec_ice_fix_base_amounts(self, tax_details):
        """Reemplaza base_amount para grupos ICE con la base volumétrica.

        El SRI requiere que baseImponible del ICE sea el total de litros de
        alcohol puro, no el subtotal monetario de la línea de factura.

        Las claves de agrupación son instancias frozendict con un marcador 'is_ice'.
        """
        # Corregir tax_details globales
        for grouping_key, group_data in tax_details.get('tax_details', {}).items():
            if grouping_key.get('is_ice'):
                ice_base = self._l10n_ec_ice_compute_volumetric_base_from_group(group_data)
                if ice_base is not None:
                    group_data['base_amount'] = ice_base
                    group_data['base_amount_currency'] = ice_base

        # Corregir tax_details por registro
        for record, record_data in tax_details.get('tax_details_per_record', {}).items():
            for grouping_key, group_data in record_data.get('tax_details', {}).items():
                if grouping_key.get('is_ice'):
                    ice_base = self._l10n_ec_ice_compute_volumetric_base_for_line(
                        record, group_data
                    )
                    if ice_base is not None:
                        group_data['base_amount'] = ice_base
                        group_data['base_amount_currency'] = ice_base

    def _l10n_ec_ice_compute_volumetric_base_from_group(self, group_data):
        """Calcula la base volumétrica total de todos los registros de línea de factura en el grupo.

        El conjunto 'records' en group_data contiene registros account.move.line
        que contribuyeron a este grupo de impuestos.
        """
        total_base = 0.0
        for line in group_data.get('records', set()):
            if line.product_id and line.product_id.l10n_ec_ice_applicable:
                product = line.product_id
                alcohol_fraction = (product.l10n_ec_ice_alcohol_degree or 0.0) / 100.0
                volume_liters = (product.l10n_ec_ice_volume_ml or 0.0) / 1000.0
                total_base += alcohol_fraction * volume_liters * abs(line.quantity)
        return total_base if total_base else None

    def _l10n_ec_ice_compute_volumetric_base_for_line(self, line_record, group_data):
        """Calcula la base volumétrica para una línea de factura individual."""
        if line_record.product_id and line_record.product_id.l10n_ec_ice_applicable:
            product = line_record.product_id
            alcohol_fraction = (product.l10n_ec_ice_alcohol_degree or 0.0) / 100.0
            volume_liters = (product.l10n_ec_ice_volume_ml or 0.0) / 1000.0
            return alcohol_fraction * volume_liters * abs(line_record.quantity)
        return None
