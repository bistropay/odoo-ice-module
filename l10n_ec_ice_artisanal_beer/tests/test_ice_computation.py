# -*- coding: utf-8 -*-
from datetime import datetime

from odoo import Command
from odoo.exceptions import ValidationError
from odoo.addons.l10n_ec_edi.tests.common import TestEcEdiCommon
from odoo.tests import tagged
from freezegun import freeze_time


@tagged('post_install_l10n', 'post_install', '-at_install')
class TestIceComputation(TestEcEdiCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # Crear grupo de impuesto ICE
        cls.tax_group_ice = cls.env['account.tax.group'].create({
            'name': 'ICE Cerveza Artesanal',
            'l10n_ec_type': 'ice',
            'sequence': 5,
        })

        # Crear impuesto ICE
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
            'max_alcohol_degree': 0,  # sin límite superior
        })

        # Crear producto cerveza: 5% ABV, 330ml
        cls.product_pale_ale = cls.env['product.product'].create({
            'name': 'Test Pale Ale 330ml',
            'type': 'consu',
            'list_price': 3.50,
            'l10n_ec_ice_applicable': True,
            'l10n_ec_ice_alcohol_degree': 5.0,
            'l10n_ec_ice_volume_ml': 330,
            'property_account_income_id': cls.company_data['default_account_revenue'].id,
            'taxes_id': [Command.set([cls.tax_ice.id])],
        })

        # Crear producto cerveza: 8% ABV, 500ml
        cls.product_stout = cls.env['product.product'].create({
            'name': 'Test Stout 500ml',
            'type': 'consu',
            'list_price': 5.00,
            'l10n_ec_ice_applicable': True,
            'l10n_ec_ice_alcohol_degree': 8.0,
            'l10n_ec_ice_volume_ml': 500,
            'property_account_income_id': cls.company_data['default_account_revenue'].id,
            'taxes_id': [Command.set([cls.tax_ice.id])],
        })

    # ===== PRUEBAS DE CÁLCULO DE IMPUESTO =====

    def test_ice_basic_computation_pale_ale(self):
        """Prueba ICE para: 5° alcohol, 330ml, qty=10
        Esperado: round((5/100) * (330/1000) * 10 * 14.76, 2) = 2.44
        """
        result = self.tax_ice.compute_all(
            price_unit=3.50,
            quantity=10,
            product=self.product_pale_ale,
        )
        expected_ice = round((5.0 / 100.0) * (330 / 1000.0) * 10 * 14.76, 2)
        self.assertAlmostEqual(
            result['taxes'][0]['amount'],
            expected_ice,
            places=2,
            msg="Monto ICE para Pale Ale (5°, 330ml, qty=10) debe ser %.4f" % expected_ice,
        )

    def test_ice_basic_computation_stout(self):
        """Prueba ICE para: 8° alcohol, 500ml, qty=5
        Esperado: round((8/100) * (500/1000) * 5 * 14.76, 2) = 2.95
        """
        result = self.tax_ice.compute_all(
            price_unit=5.00,
            quantity=5,
            product=self.product_stout,
        )
        expected_ice = round((8.0 / 100.0) * (500 / 1000.0) * 5 * 14.76, 2)
        self.assertAlmostEqual(
            result['taxes'][0]['amount'],
            expected_ice,
            places=2,
            msg="Monto ICE para Stout (8°, 500ml, qty=5) debe ser %.4f" % expected_ice,
        )

    def test_ice_single_unit(self):
        """Prueba ICE para una sola unidad de Pale Ale."""
        result = self.tax_ice.compute_all(
            price_unit=3.50,
            quantity=1,
            product=self.product_pale_ale,
        )
        expected_ice = round((5.0 / 100.0) * (330 / 1000.0) * 1 * 14.76, 2)
        self.assertAlmostEqual(
            result['taxes'][0]['amount'],
            expected_ice,
            places=2,
        )

    def test_ice_amount_is_not_zero(self):
        """Prueba crítica: el monto ICE NO debe ser cero para productos válidos."""
        result = self.tax_ice.compute_all(
            price_unit=3.50,
            quantity=10,
            product=self.product_pale_ale,
        )
        self.assertGreater(
            result['taxes'][0]['amount'],
            0,
            "El monto ICE no debe ser 0 para un producto con ICE aplicable",
        )

    def test_ice_total_includes_ice(self):
        """Prueba que total_included = total_excluded + monto ICE."""
        result = self.tax_ice.compute_all(
            price_unit=3.50,
            quantity=10,
            product=self.product_pale_ale,
        )
        expected_ice = round((5.0 / 100.0) * (330 / 1000.0) * 10 * 14.76, 2)
        self.assertAlmostEqual(
            result['total_included'],
            result['total_excluded'] + expected_ice,
            places=2,
        )

    def test_ice_amount_rounded_to_two_decimals(self):
        """Prueba que el monto ICE está redondeado a 2 decimales."""
        result = self.tax_ice.compute_all(
            price_unit=3.50,
            quantity=10,
            product=self.product_pale_ale,
        )
        ice_amount = result['taxes'][0]['amount']
        self.assertEqual(
            ice_amount,
            round(ice_amount, 2),
            "El monto ICE debe estar redondeado a 2 decimales",
        )

    def test_ice_non_applicable_product_fallback(self):
        """Prueba que un producto sin ICE con este impuesto usa el cálculo fijo estándar (0)."""
        non_ice_product = self.env['product.product'].create({
            'name': 'Producto Regular',
            'type': 'consu',
            'list_price': 10.00,
            'l10n_ec_ice_applicable': False,
            'property_account_income_id': self.company_data['default_account_revenue'].id,
        })
        result = self.tax_ice.compute_all(
            price_unit=10.00,
            quantity=5,
            product=non_ice_product,
        )
        # Cae al cálculo estándar de impuesto fijo: qty * amount = 5 * 0 = 0
        self.assertEqual(result['taxes'][0]['amount'], 0.0)

    def test_ice_only_one_repartition_line_per_type(self):
        """Prueba que el impuesto ICE tiene exactamente 1 línea de repartición tipo 'tax' por documento."""
        invoice_tax_lines = self.tax_ice.invoice_repartition_line_ids.filtered(
            lambda l: l.repartition_type == 'tax'
        )
        refund_tax_lines = self.tax_ice.refund_repartition_line_ids.filtered(
            lambda l: l.repartition_type == 'tax'
        )
        self.assertEqual(
            len(invoice_tax_lines), 1,
            "Debe haber exactamente 1 línea de repartición 'tax' para facturas",
        )
        self.assertEqual(
            len(refund_tax_lines), 1,
            "Debe haber exactamente 1 línea de repartición 'tax' para notas de crédito",
        )

    # ===== PRUEBAS DE CONFIGURACIÓN DE TARIFAS =====

    def test_rate_matching(self):
        """Prueba que se encuentra la tarifa correcta para un producto."""
        rate = self.env['l10n_ec.ice.rate']._get_rate_for_product(self.product_pale_ale)
        self.assertEqual(rate.id, self.ice_rate.id)

    def test_rate_tiered_matching(self):
        """Prueba de coincidencia de tarifas con múltiples rangos."""
        low_tier = self.env['l10n_ec.ice.rate'].create({
            'name': 'Rango Bajo Alcohol',
            'ice_code': '3023',
            'rate_per_liter_pure_alcohol': 10.00,
            'min_alcohol_degree': 0,
            'max_alcohol_degree': 6.0,
        })
        high_tier = self.env['l10n_ec.ice.rate'].create({
            'name': 'Rango Alto Alcohol',
            'ice_code': '3023',
            'rate_per_liter_pure_alcohol': 20.00,
            'min_alcohol_degree': 6.0,
            'max_alcohol_degree': 0,
        })
        # Desactivar la tarifa por defecto para evitar conflictos
        self.ice_rate.active = False

        # Producto 5% debe coincidir con rango bajo
        rate_low = self.env['l10n_ec.ice.rate']._get_rate_for_product(self.product_pale_ale)
        self.assertEqual(rate_low.id, low_tier.id)

        # Producto 8% debe coincidir con rango alto
        rate_high = self.env['l10n_ec.ice.rate']._get_rate_for_product(self.product_stout)
        self.assertEqual(rate_high.id, high_tier.id)

        # Restaurar
        self.ice_rate.active = True

    def test_no_rate_raises_error(self):
        """Prueba que la ausencia de tarifa genera ValidationError."""
        self.ice_rate.active = False
        with self.assertRaises(ValidationError):
            self.env['l10n_ec.ice.rate']._get_rate_for_product(self.product_pale_ale)
        self.ice_rate.active = True

    # ===== PRUEBAS DE RESTRICCIONES DE PRODUCTO =====

    def test_product_ice_constraint_no_degree(self):
        """Prueba que producto ICE sin grado alcohólico genera error."""
        with self.assertRaises(ValidationError):
            self.env['product.product'].create({
                'name': 'Cerveza Inválida',
                'type': 'consu',
                'l10n_ec_ice_applicable': True,
                'l10n_ec_ice_alcohol_degree': 0,
                'l10n_ec_ice_volume_ml': 330,
            })

    def test_product_ice_constraint_no_volume(self):
        """Prueba que producto ICE sin volumen genera error."""
        with self.assertRaises(ValidationError):
            self.env['product.product'].create({
                'name': 'Cerveza Inválida',
                'type': 'consu',
                'l10n_ec_ice_applicable': True,
                'l10n_ec_ice_alcohol_degree': 5.0,
                'l10n_ec_ice_volume_ml': 0,
            })

    # ===== PRUEBAS A NIVEL DE FACTURA =====

    def test_ice_on_invoice(self):
        """Prueba que el ICE se calcula correctamente en una factura."""
        with freeze_time(self.frozen_today):
            invoice = self.get_invoice(
                invoice_args={
                    'move_type': 'out_invoice',
                    'partner_id': self.partner_a.id,
                },
                invoice_line_args=[Command.create({
                    'product_id': self.product_pale_ale.id,
                    'price_unit': 3.50,
                    'quantity': 10,
                    'tax_ids': [Command.set([self.tax_ice.id])],
                })],
            )

        expected_ice = round((5.0 / 100.0) * (330 / 1000.0) * 10 * 14.76, 2)
        expected_total = 35.0 + expected_ice  # price_unit * qty + ICE

        self.assertAlmostEqual(invoice.amount_total, expected_total, places=2)

    def test_ice_on_invoice_not_zero(self):
        """Prueba crítica: el ICE en factura NO debe ser cero."""
        with freeze_time(self.frozen_today):
            invoice = self.get_invoice(
                invoice_args={
                    'move_type': 'out_invoice',
                    'partner_id': self.partner_a.id,
                },
                invoice_line_args=[Command.create({
                    'product_id': self.product_pale_ale.id,
                    'price_unit': 3.50,
                    'quantity': 10,
                    'tax_ids': [Command.set([self.tax_ice.id])],
                })],
            )

        # El total debe ser mayor que el subtotal (35.00) porque ICE > 0
        self.assertGreater(
            invoice.amount_total,
            35.0,
            "El total de la factura debe ser mayor al subtotal cuando se aplica ICE",
        )

    def test_ice_rate_constraint_negative(self):
        """Prueba que una tarifa ICE negativa genera error."""
        with self.assertRaises(ValidationError):
            self.env['l10n_ec.ice.rate'].create({
                'name': 'Tarifa Inválida',
                'ice_code': '3023',
                'rate_per_liter_pure_alcohol': -5.0,
                'min_alcohol_degree': 0,
                'max_alcohol_degree': 0,
            })

    def test_ice_rate_constraint_invalid_range(self):
        """Prueba que rango min >= max de grado alcohólico genera error."""
        with self.assertRaises(ValidationError):
            self.env['l10n_ec.ice.rate'].create({
                'name': 'Rango Inválido',
                'ice_code': '3023',
                'rate_per_liter_pure_alcohol': 14.76,
                'min_alcohol_degree': 10.0,
                'max_alcohol_degree': 5.0,
            })
