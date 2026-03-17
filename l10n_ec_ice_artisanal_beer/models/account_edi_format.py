# -*- coding: utf-8 -*-
from odoo import _, models

from odoo.addons.l10n_ec_edi.models.account_move import (
    L10N_EC_VAT_SUBTAXES,
)

# Tipos de grupo de impuesto soportados (tipos IVA + ICE vía este módulo)
_SUPPORTED_NON_VAT_TYPES = {'ice'}


class AccountEdiFormat(models.Model):
    _inherit = 'account.edi.format'

    def _check_move_configuration(self, move):
        """Override para prevenir crash cuando existen impuestos ICE en facturas.

        El método padre en l10n_ec_edi/models/account_edi_format.py:118-126
        hace L10N_EC_VAT_SUBTAXES[l.tax_group_id.l10n_ec_type] lo cual genera
        KeyError para 'ice'. Interceptamos y manejamos las líneas ICE por separado.
        """
        if self.code != 'ecuadorian_edi' or move.country_code != 'EC':
            return super()._check_move_configuration(move)

        # Replicamos la validación completa de l10n_ec_edi en lugar de llamar
        # super(), porque el padre falla con KeyError en líneas de impuesto ICE.
        # El base account_edi._check_move_configuration solo retorna [].
        errors = []

        if not (move.move_type in ('out_invoice', 'out_refund')
                or move.l10n_latam_document_type_id.internal_type == 'purchase_liquidation'
                or move.journal_id.l10n_ec_withhold_type == 'in_withhold'):
            return errors

        journal = move.journal_id
        address = journal.l10n_ec_emission_address_id

        if not move.company_id.vat:
            errors.append(_("Debe establecer un número de RUC/CI para la compañía %s", move.company_id.display_name))

        if not address:
            errors.append(_("Debe establecer una dirección de emisión en el diario %s", journal.display_name))

        if address and not address.street:
            errors.append(_(
                "Debe establecer una dirección en el contacto %s, el campo Calle debe estar lleno",
                address.display_name
            ))

        if address and not address.commercial_partner_id.street:
            errors.append(_(
                "Debe establecer una dirección de la matriz en el contacto %s, el campo Calle debe estar lleno",
                address.commercial_partner_id.display_name
            ))

        if not move.commercial_partner_id.vat:
            errors.append(_("Debe establecer un número de RUC/CI para el cliente %s", move.commercial_partner_id.display_name))

        if not move.l10n_ec_sri_payment_id and move.move_type in ['out_invoice', 'in_invoice']:
            errors.append(_("Debe establecer la Forma de Pago SRI en el documento %s", move.display_name))

        if not move.l10n_latam_document_number:
            errors.append(_("Debe establecer el Número de Documento en el documento %s", move.display_name))

        if move._l10n_ec_is_withholding():
            for line in move.l10n_ec_withhold_line_ids:
                if not line.l10n_ec_withhold_invoice_id.l10n_ec_sri_payment_id:
                    errors.append(_(
                        "Debe establecer la Forma de Pago SRI en el documento %s",
                        line.l10n_ec_withhold_invoice_id.name
                    ))
                if not line.l10n_ec_withhold_invoice_id:
                    errors.append(_("Por favor use el asistente en la factura para generar la retención."))
                code = move._l10n_ec_wth_map_tax_code(line)
                if not code:
                    errors.append(_("Impuesto incorrecto (%s) para el documento %s", line.tax_ids[0].name, move.display_name))
        else:
            # === BLOQUE CORREGIDO ===
            # El código original falla aquí porque L10N_EC_VAT_SUBTAXES no contiene 'ice'
            unsupported_tax_types = set()
            for line in move.line_ids.filtered(lambda l: l.tax_group_id.l10n_ec_type):
                ec_type = line.tax_group_id.l10n_ec_type
                if ec_type in _SUPPORTED_NON_VAT_TYPES:
                    continue
                if ec_type not in L10N_EC_VAT_SUBTAXES or not move._l10n_ec_map_tax_groups(line):
                    unsupported_tax_types.add(ec_type)
            for tax_type in unsupported_tax_types:
                errors.append(_("Tipo de impuesto no soportado: %s", tax_type))

            # Validaciones específicas del ICE
            for line in move.invoice_line_ids.filtered(lambda l: l.display_type == 'product'):
                ice_taxes = line.tax_ids.filtered(
                    lambda t: t.tax_group_id.l10n_ec_type == 'ice'
                )
                if not ice_taxes:
                    continue
                product = line.product_id
                if not product:
                    errors.append(_(
                        "La línea de factura con impuesto ICE debe tener un producto asignado."
                    ))
                elif not product.l10n_ec_ice_applicable:
                    errors.append(_(
                        "El producto '%s' tiene un impuesto ICE aplicado pero no está marcado como 'Sujeto a ICE'.",
                        product.display_name
                    ))
                elif not product.l10n_ec_ice_alcohol_degree or not product.l10n_ec_ice_volume_ml:
                    errors.append(_(
                        "El producto '%s' no tiene configurado el grado alcohólico o volumen para el cálculo del ICE.",
                        product.display_name
                    ))
                else:
                    # Verificar que exista una tarifa ICE correspondiente
                    try:
                        self.env['l10n_ec.ice.rate']._get_rate_for_product(
                            product, move.invoice_date
                        )
                    except Exception:
                        errors.append(_(
                            "No se encontró una tarifa ICE configurada para el producto '%s' "
                            "(grado alcohólico: %.2f%%). "
                            "Configure una en Contabilidad > Configuración > Tarifas ICE.",
                            product.display_name, product.l10n_ec_ice_alcohol_degree
                        ))

        if not move.company_id.sudo().l10n_ec_edi_certificate_id and not move.company_id._l10n_ec_is_demo_environment():
            errors.append(_(
                "Debe seleccionar un certificado válido en la configuración de la compañía %s",
                move.company_id.name
            ))

        if not move.company_id.l10n_ec_legal_name:
            errors.append(_(
                "Debe definir una razón social en la configuración de la compañía %s",
                move.company_id.name
            ))

        if not move.commercial_partner_id.country_id:
            errors.append(_("Debe establecer un País para el cliente: %s", move.commercial_partner_id.name))

        if move.move_type == "out_refund" and not move.reversed_entry_id:
            errors.append(_(
                "La Nota de Crédito %s debe tener una factura original relacionada, "
                "intente 'Agregar Nota de Crédito' desde la factura",
                move.display_name
            ))

        if move.l10n_latam_document_type_id.internal_type == 'debit_note' and not move.debit_origin_id:
            errors.append(_(
                "La Nota de Débito %s debe tener una factura original relacionada, "
                "intente 'Agregar Nota de Débito' desde la factura",
                move.display_name
            ))

        return errors
