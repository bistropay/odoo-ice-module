# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class L10nEcIceRate(models.Model):
    _name = 'l10n_ec.ice.rate'
    _description = 'Configuración de Tarifas ICE Ecuador'
    _order = 'min_alcohol_degree'

    name = fields.Char(
        string='Nombre',
        required=True,
        help='Nombre descriptivo para esta tarifa ICE, ej. "Cerveza artesanal 0-75 grados"',
    )
    ice_code = fields.Char(
        string='Código SRI (codigoPorcentaje)',
        required=True,
        help='Código SRI para esta categoría ICE, ej. 3023 para cerveza artesanal',
    )
    rate_per_liter_pure_alcohol = fields.Float(
        string='Tarifa por Litro de Alcohol Puro (USD)',
        required=True,
        digits=(12, 4),
        help='Tarifa específica del ICE en USD por litro de alcohol puro',
    )
    min_alcohol_degree = fields.Float(
        string='Grado Alcohólico Mínimo (%)',
        digits=(5, 2),
        help='Grado alcohólico mínimo para este rango (inclusive)',
    )
    max_alcohol_degree = fields.Float(
        string='Grado Alcohólico Máximo (%)',
        digits=(5, 2),
        help='Grado alcohólico máximo para este rango (exclusive). 0 = sin límite superior.',
    )
    date_from = fields.Date(
        string='Vigente Desde',
        help='Fecha de inicio de vigencia. Dejar vacío si no tiene límite inferior.',
    )
    date_to = fields.Date(
        string='Vigente Hasta',
        help='Fecha de fin de vigencia. Dejar vacío si no tiene límite superior.',
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Compañía',
        default=lambda self: self.env.company,
    )
    active = fields.Boolean(default=True)

    @api.constrains('min_alcohol_degree', 'max_alcohol_degree')
    def _check_alcohol_range(self):
        for record in self:
            if record.max_alcohol_degree and record.min_alcohol_degree >= record.max_alcohol_degree:
                raise ValidationError(
                    _("El grado alcohólico mínimo debe ser menor al grado alcohólico máximo.")
                )

    @api.constrains('rate_per_liter_pure_alcohol')
    def _check_rate_positive(self):
        for record in self:
            if record.rate_per_liter_pure_alcohol < 0:
                raise ValidationError(_("La tarifa ICE debe ser un valor no negativo."))

    @api.model
    def _get_rate_for_product(self, product, date=None):
        """Busca la tarifa ICE correspondiente para un producto según su grado alcohólico y fecha.

        :param product: recordset product.product o product.template
        :param date: fecha opcional para filtrar por periodo de vigencia
        :returns: registro l10n_ec.ice.rate
        :raises ValidationError: si no se encuentra una tarifa correspondiente
        """
        alcohol_degree = product.l10n_ec_ice_alcohol_degree or 0.0
        domain = [
            ('min_alcohol_degree', '<=', alcohol_degree),
            '|',
            ('max_alcohol_degree', '=', 0),
            ('max_alcohol_degree', '>', alcohol_degree),
        ]
        if date:
            domain += [
                '|', ('date_from', '=', False), ('date_from', '<=', date),
                '|', ('date_to', '=', False), ('date_to', '>=', date),
            ]
        if product.company_id:
            domain += [
                '|',
                ('company_id', '=', product.company_id.id),
                ('company_id', '=', False),
            ]
        rate = self.search(domain, order='min_alcohol_degree desc', limit=1)
        if not rate:
            raise ValidationError(
                _("No se encontró una tarifa ICE configurada para grado alcohólico %.2f%%. "
                  "Configure una tarifa en Contabilidad > Configuración > Tarifas ICE.",
                  alcohol_degree)
            )
        return rate
