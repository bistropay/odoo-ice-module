# -*- coding: utf-8 -*-
from datetime import datetime
from lxml import etree

from odoo import Command
from odoo.addons.l10n_ec_edi.tests.common import TestEcEdiCommon
from odoo.tests import tagged
from freezegun import freeze_time


@tagged('post_install_l10n', 'post_install', '-at_install')
class TestIceEdi(TestEcEdiCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # Crear grupo de impuesto ICE
        cls.tax_group_ice = cls.env['account.tax.group'].create({
            'name': 'ICE Cerveza Artesanal',
            'l10n_ec_type': 'ice',
            'sequence': 5,
        })

        # Crear impuesto ICE para ventas
        cls.tax_ice = cls.env['account.tax'].create({
            'name': 'ICE Cerveza Artesanal (Test)',
            'type_tax_use': 'sale',
            'amount_type': 'fixed',
            'amount': 0,
            'sequence': 5,
            'tax_group_id': cls.tax_group_ice.id,
            'include_base_amount': True,
        })

        # Crear tarifa ICE
        cls.ice_rate = cls.env['l10n_ec.ice.rate'].create({
            'name': 'Cerveza Artesanal - Test',
            'ice_code': '3023',
            'rate_per_liter_pure_alcohol': 14.76,
            'min_alcohol_degree': 0,
            'max_alcohol_degree': 0,
        })

        # Obtener IVA 12%
        cls.tax_vat_12 = cls._get_tax_by_xml_id('tax_vat_510_sup_01')

        # Crear producto cerveza con impuestos ICE + IVA
        cls.product_beer = cls.env['product.product'].create({
            'name': 'Test Cerveza Artesanal 330ml',
            'type': 'consu',
            'list_price': 3.50,
            'l10n_ec_ice_applicable': True,
            'l10n_ec_ice_alcohol_degree': 5.0,
            'l10n_ec_ice_volume_ml': 330,
            'property_account_income_id': cls.company_data['default_account_revenue'].id,
            'taxes_id': [Command.set([cls.tax_ice.id, cls.tax_vat_12.id])],
        })

    # ===== PRUEBAS DE AGRUPAMIENTO DE IMPUESTOS EDI =====

    def test_taxes_grouped_includes_ice(self):
        """Prueba que _l10n_ec_get_taxes_grouped maneja correctamente impuestos ICE."""
        with freeze_time(self.frozen_today):
            invoice = self.get_invoice(
                invoice_args={
                    'move_type': 'out_invoice',
                    'partner_id': self.partner_a.id,
                },
                invoice_line_args=[Command.create({
                    'product_id': self.product_beer.id,
                    'price_unit': 3.50,
                    'quantity': 10,
                    'tax_ids': [Command.set([self.tax_ice.id, self.tax_vat_12.id])],
                })],
            )

        tax_details = invoice._l10n_ec_get_taxes_grouped()

        # Verificar que tenemos tanto ICE como IVA en los detalles de impuestos
        tax_codes = set()
        for grouping_key in tax_details['tax_details']:
            tax_codes.add(grouping_key.get('code'))

        self.assertIn(3, tax_codes, "El código de impuesto ICE (3) debe estar presente en los impuestos agrupados")
        self.assertIn(2, tax_codes, "El código de impuesto IVA (2) debe estar presente en los impuestos agrupados")

    def test_taxes_grouped_ice_code_percentage(self):
        """Prueba que el codigoPorcentaje del ICE se establece correctamente desde la tarifa."""
        with freeze_time(self.frozen_today):
            invoice = self.get_invoice(
                invoice_args={
                    'move_type': 'out_invoice',
                    'partner_id': self.partner_a.id,
                },
                invoice_line_args=[Command.create({
                    'product_id': self.product_beer.id,
                    'price_unit': 3.50,
                    'quantity': 10,
                    'tax_ids': [Command.set([self.tax_ice.id, self.tax_vat_12.id])],
                })],
            )

        tax_details = invoice._l10n_ec_get_taxes_grouped()

        for grouping_key, group_data in tax_details['tax_details'].items():
            if grouping_key.get('code') == 3:  # ICE
                self.assertEqual(
                    grouping_key.get('code_percentage'),
                    '3023',
                    "El codigoPorcentaje del ICE debe ser '3023' para cerveza artesanal"
                )

    def test_taxes_grouped_ice_base_is_volumetric(self):
        """Prueba que el base_amount del ICE es la base volumétrica, no monetaria."""
        with freeze_time(self.frozen_today):
            invoice = self.get_invoice(
                invoice_args={
                    'move_type': 'out_invoice',
                    'partner_id': self.partner_a.id,
                },
                invoice_line_args=[Command.create({
                    'product_id': self.product_beer.id,
                    'price_unit': 3.50,
                    'quantity': 10,
                    'tax_ids': [Command.set([self.tax_ice.id, self.tax_vat_12.id])],
                })],
            )

        tax_details = invoice._l10n_ec_get_taxes_grouped()

        # Base volumétrica esperada: (5/100) * (330/1000) * 10 = 0.165
        expected_base = (5.0 / 100.0) * (330 / 1000.0) * 10

        for grouping_key, group_data in tax_details['tax_details'].items():
            if grouping_key.get('code') == 3:  # ICE
                self.assertAlmostEqual(
                    group_data['base_amount'],
                    expected_base,
                    places=4,
                    msg="El base_amount del ICE debe ser volumétrico (litros de alcohol puro)"
                )

    def test_taxes_grouped_ice_tax_amount(self):
        """Prueba que el tax_amount (valor) del ICE se calcula correctamente."""
        with freeze_time(self.frozen_today):
            invoice = self.get_invoice(
                invoice_args={
                    'move_type': 'out_invoice',
                    'partner_id': self.partner_a.id,
                },
                invoice_line_args=[Command.create({
                    'product_id': self.product_beer.id,
                    'price_unit': 3.50,
                    'quantity': 10,
                    'tax_ids': [Command.set([self.tax_ice.id, self.tax_vat_12.id])],
                })],
            )

        tax_details = invoice._l10n_ec_get_taxes_grouped()

        # Monto ICE esperado: round((5/100) * (330/1000) * 10 * 14.76, 2)
        expected_tax = round((5.0 / 100.0) * (330 / 1000.0) * 10 * 14.76, 2)

        for grouping_key, group_data in tax_details['tax_details'].items():
            if grouping_key.get('code') == 3:  # ICE
                self.assertAlmostEqual(
                    abs(group_data['tax_amount']),
                    expected_tax,
                    places=2,
                    msg="El tax_amount del ICE debe coincidir con la fórmula volumétrica"
                )

    # ===== PRUEBAS DE VALIDACIÓN EDI =====

    def test_check_move_configuration_ice_valid(self):
        """Prueba que una factura con configuración ICE válida pasa la validación."""
        with freeze_time(self.frozen_today):
            invoice = self.get_invoice(
                invoice_args={
                    'move_type': 'out_invoice',
                    'partner_id': self.partner_a.id,
                },
                invoice_line_args=[Command.create({
                    'product_id': self.product_beer.id,
                    'price_unit': 3.50,
                    'quantity': 10,
                    'tax_ids': [Command.set([self.tax_ice.id, self.tax_vat_12.id])],
                })],
            )

        edi_format = self.env.ref('l10n_ec_edi.ecuadorian_edi_format')
        errors = edi_format._check_move_configuration(invoice)

        # Filtrar solo errores relacionados con ICE
        ice_errors = [e for e in errors if 'ICE' in str(e) or 'ice' in str(e).lower()]
        self.assertEqual(
            len(ice_errors), 0,
            "Configuración ICE válida no debe producir errores relacionados con ICE: %s" % ice_errors
        )

    def test_check_move_configuration_ice_no_product(self):
        """Prueba que impuesto ICE en línea sin producto genera error."""
        with freeze_time(self.frozen_today):
            invoice = self.get_invoice(
                invoice_args={
                    'move_type': 'out_invoice',
                    'partner_id': self.partner_a.id,
                },
                invoice_line_args=[Command.create({
                    'name': 'Cerveza sin producto',
                    'price_unit': 3.50,
                    'quantity': 10,
                    'tax_ids': [Command.set([self.tax_ice.id])],
                })],
            )

        edi_format = self.env.ref('l10n_ec_edi.ecuadorian_edi_format')
        errors = edi_format._check_move_configuration(invoice)
        ice_errors = [e for e in errors if 'ICE' in str(e)]
        self.assertTrue(
            len(ice_errors) > 0,
            "Impuesto ICE en línea sin producto debe producir un error de validación"
        )

    def test_check_move_configuration_ice_not_applicable(self):
        """Prueba que impuesto ICE en producto no marcado como aplicable genera error."""
        non_ice_product = self.env['product.product'].create({
            'name': 'Producto Regular',
            'type': 'consu',
            'list_price': 10.00,
            'l10n_ec_ice_applicable': False,
            'property_account_income_id': self.company_data['default_account_revenue'].id,
        })
        with freeze_time(self.frozen_today):
            invoice = self.get_invoice(
                invoice_args={
                    'move_type': 'out_invoice',
                    'partner_id': self.partner_a.id,
                },
                invoice_line_args=[Command.create({
                    'product_id': non_ice_product.id,
                    'price_unit': 10.00,
                    'quantity': 5,
                    'tax_ids': [Command.set([self.tax_ice.id])],
                })],
            )

        edi_format = self.env.ref('l10n_ec_edi.ecuadorian_edi_format')
        errors = edi_format._check_move_configuration(invoice)
        ice_errors = [e for e in errors if 'ICE' in str(e) or 'Sujeto a ICE' in str(e)]
        self.assertTrue(
            len(ice_errors) > 0,
            "Impuesto ICE en producto no aplicable debe producir un error de validación"
        )

    # ===== PRUEBAS DE IMPUESTOS MIXTOS =====

    def test_ice_plus_vat_invoice_total(self):
        """Prueba que ICE + IVA se calculan correctamente juntos.

        ICE tiene include_base_amount=True, así que la base del IVA incluye el ICE.
        subtotal línea = 3.50 * 10 = 35.00
        ICE = round((5/100) * (330/1000) * 10 * 14.76, 2) = 2.44
        base IVA = 35.00 + 2.44 = 37.44
        IVA = 37.44 * 12% = 4.4928 ≈ 4.49
        Total = 35.00 + 2.44 + 4.49 = 41.93
        """
        with freeze_time(self.frozen_today):
            invoice = self.get_invoice(
                invoice_args={
                    'move_type': 'out_invoice',
                    'partner_id': self.partner_a.id,
                },
                invoice_line_args=[Command.create({
                    'product_id': self.product_beer.id,
                    'price_unit': 3.50,
                    'quantity': 10,
                    'tax_ids': [Command.set([self.tax_ice.id, self.tax_vat_12.id])],
                })],
            )

        line_subtotal = 35.00
        expected_ice = round((5.0 / 100.0) * (330.0 / 1000.0) * 10 * 14.76, 2)
        expected_vat_base = line_subtotal + expected_ice
        expected_vat = expected_vat_base * 0.12
        expected_total = line_subtotal + expected_ice + expected_vat

        self.assertAlmostEqual(
            invoice.amount_total,
            expected_total,
            places=2,
            msg="El total debe ser subtotal + ICE + IVA(con ICE en la base)"
        )

    def test_vat_only_invoice_still_works(self):
        """Prueba que una factura solo con IVA sigue funcionando después de nuestros overrides."""
        with freeze_time(self.frozen_today):
            invoice = self.get_invoice(
                invoice_args={
                    'move_type': 'out_invoice',
                    'partner_id': self.partner_a.id,
                },
                invoice_line_args=self.get_invoice_line_vals(),
            )

        # Estándar: 100 * 5 * (1 - 20%) = 400, IVA = 48, Total = 448
        self.assertAlmostEqual(invoice.amount_untaxed, 400.0, places=2)
        self.assertAlmostEqual(invoice.amount_total, 448.0, places=2)

    def test_vat_only_invoice_tax_grouping_no_crash(self):
        """Prueba que _l10n_ec_get_taxes_grouped no falla para facturas solo con IVA."""
        with freeze_time(self.frozen_today):
            invoice = self.get_invoice(
                invoice_args={
                    'move_type': 'out_invoice',
                    'partner_id': self.partner_a.id,
                },
                invoice_line_args=self.get_invoice_line_vals(),
            )

        # No debe generar KeyError
        tax_details = invoice._l10n_ec_get_taxes_grouped()
        self.assertIn('tax_details', tax_details)
