# -*- coding: utf-8 -*-
import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# Formato del código de producto ICE del SRI: segmentos numéricos separados por guiones
# Ej: 3031-57-001444-013-000750-66-118-000071  (39 chars)
# Ej: 3043-083-026596-003-150015-60-593-000013 (40 chars)
# Validación flexible: solo dígitos y guiones, entre 39 y 45 caracteres
_ICE_PRODUCT_CODE_PATTERN = re.compile(r'^[0-9]+(-[0-9]+){6,8}$')


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    l10n_ec_ice_applicable = fields.Boolean(
        string='Sujeto a ICE',
        default=False,
        help='Activar si este producto está sujeto al ICE (Impuesto a los Consumos Especiales).',
    )
    l10n_ec_ice_alcohol_degree = fields.Float(
        string='Grado Alcohólico (%)',
        digits=(5, 2),
        help='Contenido de alcohol por volumen (ABV) del producto. Ej. 5.0 para 5% de alcohol.',
    )
    l10n_ec_ice_volume_ml = fields.Float(
        string='Volumen del Producto (ml)',
        digits=(10, 2),
        help='Volumen de una unidad en mililitros. Ej. 330 para una botella de 330ml.',
    )
    l10n_ec_ice_product_code = fields.Char(
        string='Código Producto ICE (SRI)',
        size=45,
        help='Código de producto ICE asignado por el SRI para el Anexo 105. '
             'Formato: segmentos numéricos separados por guiones. '
             'Ej: 3043-083-026596-003-150015-60-593-000013',
    )

    @api.constrains('l10n_ec_ice_applicable', 'l10n_ec_ice_alcohol_degree', 'l10n_ec_ice_volume_ml')
    def _check_ice_fields(self):
        for record in self:
            if record.l10n_ec_ice_applicable:
                if not record.l10n_ec_ice_alcohol_degree or record.l10n_ec_ice_alcohol_degree <= 0:
                    raise ValidationError(
                        _("Producto '%s': El grado alcohólico debe ser mayor a 0 cuando el ICE es aplicable.",
                          record.name)
                    )
                if not record.l10n_ec_ice_volume_ml or record.l10n_ec_ice_volume_ml <= 0:
                    raise ValidationError(
                        _("Producto '%s': El volumen del producto (ml) debe ser mayor a 0 cuando el ICE es aplicable.",
                          record.name)
                    )

    @api.constrains('l10n_ec_ice_product_code')
    def _check_ice_product_code_format(self):
        for record in self:
            if record.l10n_ec_ice_product_code:
                code = record.l10n_ec_ice_product_code.strip()
                if not _ICE_PRODUCT_CODE_PATTERN.match(code):
                    raise ValidationError(
                        _("Producto '%s': El código de producto ICE debe contener "
                          "segmentos numéricos separados por guiones. "
                          "Ej: 3043-083-026596-003-150015-60-593-000013",
                          record.name)
                    )
