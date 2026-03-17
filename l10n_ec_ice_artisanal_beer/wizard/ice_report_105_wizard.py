# -*- coding: utf-8 -*-
import calendar
from collections import defaultdict
from datetime import date

from lxml import etree

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_CONSUMIDOR_FINAL_VAT = '9999999999999'

# Años disponibles para selección (desde 2008 según XSD del SRI)
_YEAR_SELECTION = [(str(y), str(y)) for y in range(2020, 2036)]


class IceReport105Wizard(models.TransientModel):
    _name = 'l10n_ec.ice.report105.wizard'
    _description = 'Asistente Reporte ICE 105'

    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        default=lambda self: self.env.company,
        required=True,
    )
    period_type = fields.Selection(
        selection=[
            ('week', 'Semana'),
            ('month', 'Mes'),
            ('year', 'Año'),
        ],
        string='Tipo de Periodo',
        default='month',
        required=True,
    )
    year = fields.Selection(
        selection=_YEAR_SELECTION,
        string='Año',
        default=lambda self: str(fields.Date.context_today(self).year),
        required=True,
    )
    month = fields.Selection(
        selection=[
            ('01', 'Enero'), ('02', 'Febrero'), ('03', 'Marzo'),
            ('04', 'Abril'), ('05', 'Mayo'), ('06', 'Junio'),
            ('07', 'Julio'), ('08', 'Agosto'), ('09', 'Septiembre'),
            ('10', 'Octubre'), ('11', 'Noviembre'), ('12', 'Diciembre'),
        ],
        string='Mes',
        default=lambda self: '%02d' % fields.Date.context_today(self).month,
    )
    week_number = fields.Integer(
        string='Número de Semana',
        default=1,
        help='Número de semana dentro del mes seleccionado (1-5).',
    )
    date_from = fields.Date(string='Desde', compute='_compute_dates', store=True)
    date_to = fields.Date(string='Hasta', compute='_compute_dates', store=True)

    @api.depends('period_type', 'year', 'month', 'week_number')
    def _compute_dates(self):
        for wizard in self:
            if not wizard.year:
                wizard.date_from = wizard.date_to = False
                continue

            yr = int(wizard.year)

            if wizard.period_type == 'year':
                wizard.date_from = date(yr, 1, 1)
                wizard.date_to = date(yr, 12, 31)
            elif wizard.period_type == 'month' and wizard.month:
                m = int(wizard.month)
                last_day = calendar.monthrange(yr, m)[1]
                wizard.date_from = date(yr, m, 1)
                wizard.date_to = date(yr, m, last_day)
            elif wizard.period_type == 'week' and wizard.month:
                m = int(wizard.month)
                first_of_month = date(yr, m, 1)
                last_of_month_day = calendar.monthrange(yr, m)[1]
                week_num = max(1, min(wizard.week_number or 1, 5))
                # Calcular inicio de semana N dentro del mes
                monday_offset = (7 - first_of_month.weekday()) % 7
                if week_num == 1:
                    w_start_day = 1
                else:
                    w_start_day = 1 + monday_offset + (week_num - 2) * 7
                w_start_day = min(w_start_day, last_of_month_day)
                w_end_day = min(w_start_day + 6, last_of_month_day)
                wizard.date_from = date(yr, m, w_start_day)
                wizard.date_to = date(yr, m, w_end_day)
            else:
                wizard.date_from = wizard.date_to = False

    # ──────────────────────────────────────────────
    # Recolección de datos
    # ──────────────────────────────────────────────

    def _get_ice_invoice_lines(self):
        """Obtiene las líneas de factura con impuesto ICE en el periodo seleccionado."""
        self.ensure_one()
        domain = [
            ('move_id.state', '=', 'posted'),
            ('move_id.company_id', '=', self.company_id.id),
            ('move_id.invoice_date', '>=', self.date_from),
            ('move_id.invoice_date', '<=', self.date_to),
            ('move_id.move_type', 'in', ['out_invoice', 'out_refund']),
            ('display_type', '=', 'product'),
            ('tax_ids.tax_group_id.l10n_ec_type', '=', 'ice'),
        ]
        return self.env['account.move.line'].search(domain)

    def _get_partner_type_id(self, partner):
        """Mapea el tipo de identificación del partner al código SRI.

        Usa los XML IDs de l10n_ec para determinar el tipo:
        - l10n_ec.ec_ruc → R (RUC)
        - l10n_ec.ec_dni → C (Cédula)
        - Otros → P (Pasaporte)
        - Consumidor final → F
        """
        if not partner.vat or partner.vat == _CONSUMIDOR_FINAL_VAT:
            return 'F', _CONSUMIDOR_FINAL_VAT

        vat = partner.vat.strip()
        l10n_latam_type = partner.l10n_latam_identification_type_id

        if l10n_latam_type:
            # Comparar con XML IDs conocidos de l10n_ec
            ruc_type = self.env.ref('l10n_ec.ec_ruc', raise_if_not_found=False)
            dni_type = self.env.ref('l10n_ec.ec_dni', raise_if_not_found=False)

            if ruc_type and l10n_latam_type.id == ruc_type.id:
                return 'R', vat
            if dni_type and l10n_latam_type.id == dni_type.id:
                return 'C', vat
            # Cualquier otro tipo se trata como pasaporte
            return 'P', vat

        # Fallback por longitud del VAT
        if len(vat) == 13 and vat.endswith('001'):
            return 'R', vat
        if len(vat) == 10 and vat.isdigit():
            return 'C', vat
        return 'P', vat

    def _get_sale_type(self, partner):
        """Determina tipo de venta ICE: 1=Nacional, 2=Exportación."""
        if partner.country_id and partner.country_id.code != 'EC':
            return '2'
        return '1'

    def _get_report_data(self):
        """Genera los datos agrupados para el reporte 105.

        Agrupa solo por codProdICE (código de producto ICE del SRI).
        Suma cantidades de ventas y devoluciones por producto.
        """
        self.ensure_one()
        lines = self._get_ice_invoice_lines()

        grouped = defaultdict(lambda: {
            'ventaICE': 0,
            'devICE': 0,
            'cantProdBajaICE': 0,
            'codProdICE': '',
            'product_name': '',
        })

        for line in lines:
            product = line.product_id
            if not product or not product.l10n_ec_ice_applicable:
                continue

            cod_prod = product.l10n_ec_ice_product_code or ''
            key = cod_prod
            qty = int(abs(line.quantity))

            if line.move_id.move_type == 'out_refund':
                grouped[key]['devICE'] += qty
            else:
                grouped[key]['ventaICE'] += qty

            grouped[key]['codProdICE'] = cod_prod
            grouped[key]['product_name'] = product.display_name

        return list(grouped.values())

    # ──────────────────────────────────────────────
    # Reporte PDF
    # ──────────────────────────────────────────────

    def action_generate_pdf(self):
        """Genera el reporte PDF del Anexo 105."""
        self.ensure_one()
        self._validate_wizard()
        return self.env.ref(
            'l10n_ec_ice_artisanal_beer.action_report_ice_105'
        ).report_action(self)

    # ──────────────────────────────────────────────
    # Generación XML (Esquema SRI)
    # ──────────────────────────────────────────────

    def action_download_xml(self):
        """Genera y descarga el XML del Anexo 105 conforme al esquema del SRI."""
        self.ensure_one()
        self._validate_wizard()

        xml_content = self._generate_xml()
        filename = 'ICE_105_%s_%s_%s.xml' % (
            self.company_id.vat or 'SIN_RUC',
            self.year,
            self.month or '00',
        )

        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'raw': xml_content,
            'mimetype': 'application/xml',
        })

        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%d?download=true' % attachment.id,
            'close': True,
        }

    def _generate_xml(self):
        """Construye el XML del Anexo 105 conforme al XSD del SRI."""
        self.ensure_one()
        company = self.company_id

        root = etree.Element('ice')

        etree.SubElement(root, 'TipoIDInformante').text = 'R'
        etree.SubElement(root, 'IdInformante').text = company.vat or ''
        etree.SubElement(root, 'razonSocial').text = (
            company.l10n_ec_legal_name or company.name or ''
        )
        etree.SubElement(root, 'Anio').text = self.year
        etree.SubElement(root, 'Mes').text = self.month or '01'
        etree.SubElement(root, 'actImport').text = '01'  # Sin importaciones
        etree.SubElement(root, 'codigoOperativo').text = 'ICE'

        # Módulo 1: Detalle Ventas
        report_data = self._get_report_data()
        ventas_elem = etree.SubElement(root, 'ventas')

        for row in report_data:
            cod_prod = row['codProdICE']
            if not cod_prod:
                continue  # No se puede reportar al SRI sin código de producto

            vta = etree.SubElement(ventas_elem, 'vta')
            etree.SubElement(vta, 'codProdICE').text = cod_prod
            etree.SubElement(vta, 'gramoAzucar').text = '0.00'
            # Para el XML agrupado por producto, usamos consumidor final genérico
            etree.SubElement(vta, 'tipoIdCliente').text = 'F'
            etree.SubElement(vta, 'idCliente').text = _CONSUMIDOR_FINAL_VAT
            etree.SubElement(vta, 'tipoVentaICE').text = '1'
            etree.SubElement(vta, 'ventaICE').text = str(row['ventaICE'])
            etree.SubElement(vta, 'devICE').text = str(row['devICE'])
            etree.SubElement(vta, 'cantProdBajaICE').text = str(row['cantProdBajaICE'])

        # Módulo 2: Importaciones (vacío para cervecerías artesanales locales)
        etree.SubElement(root, 'importaciones')

        return etree.tostring(
            root,
            xml_declaration=True,
            encoding='UTF-8',
            pretty_print=True,
        )

    # ──────────────────────────────────────────────
    # Validación
    # ──────────────────────────────────────────────

    def _validate_wizard(self):
        """Valida los datos del asistente antes de generar el reporte."""
        self.ensure_one()
        if not self.date_from or not self.date_to:
            raise UserError(_("Debe seleccionar un periodo válido."))
        if not self.company_id.vat:
            raise UserError(
                _("La compañía '%s' no tiene configurado un número de RUC.",
                  self.company_id.display_name)
            )
        if self.period_type in ('month', 'week') and not self.month:
            raise UserError(_("Debe seleccionar un mes."))
