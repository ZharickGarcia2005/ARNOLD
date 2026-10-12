from datetime import date, datetime

from django.test import SimpleTestCase

from apps.validation.contracts import (
    CellKind,
    DatasetRole,
    PaymentClaim,
    RuleCode,
    Severity,
    ValidationInput,
)
from apps.validation.rules import (
    make_unique_headers,
    normalize_header,
    recognize_schema,
    validate,
)

from .factories import MONTHLY_HEADERS, cell, dataset, record


class HeaderRuleTests(SimpleTestCase):
    databases = []

    def test_normalize_header_removes_accents_and_applies_aliases(self):
        self.assertEqual(normalize_header("  cédula  "), "CEDULA_RUC")
        self.assertEqual(normalize_header("Predio municipal"), "PREDIO_MUN")

    def test_make_unique_headers_keeps_every_original_occurrence(self):
        occurrences = make_unique_headers(("TOTAL EMISION", "TOTAL EMISION"))

        self.assertEqual(occurrences[0].unique_name, "TOTAL_EMISION")
        self.assertEqual(occurrences[1].unique_name, "TOTAL_EMISION__2")
        self.assertEqual(occurrences[1].occurrence, 2)

    def test_recognize_monthly_schema_and_reports_duplicates(self):
        recognition = recognize_schema(MONTHLY_HEADERS + ("TOTAL_EMISION",))

        self.assertEqual(recognition.schema_name, "carteraMensual")
        self.assertTrue(recognition.valid)
        self.assertEqual(recognition.missing, ())
        self.assertEqual(recognition.duplicate_headers, {"TOTAL_EMISION": 2})


class ValidationRuleTests(SimpleTestCase):
    databases = []

    def test_missing_required_column_is_blocking(self):
        headers = tuple(name for name in MONTHLY_HEADERS if name != "CLAVE")
        current = dataset(record("actual-2", 2), headers=headers)

        report = validate(ValidationInput(current), (RuleCode.SCHEMA_001,))

        self.assertEqual(len(report.issues), 1)
        issue = report.issues[0]
        self.assertEqual(issue.rule_code, RuleCode.SCHEMA_001)
        self.assertEqual(issue.severity, Severity.CRITICAL)
        self.assertTrue(issue.blocking)
        self.assertIn("CLAVE", issue.evidence["faltantes"])

    def test_duplicate_headers_are_blocking_without_explicit_profile(self):
        duplicated = MONTHLY_HEADERS + (
            "TOTAL_EMISION",
            "TOTAL_INTERES",
            "TOTAL_COACTIVA",
            "TOTAL_RECARGO",
        )
        current = dataset(record("actual-2", 2), headers=duplicated)

        report = validate(ValidationInput(current), (RuleCode.SCHEMA_002,))

        self.assertEqual(len(report.issues), 1)
        self.assertEqual(report.issues[0].rule_code, RuleCode.SCHEMA_002)
        self.assertTrue(report.issues[0].blocking)

    def test_confirmed_july_profile_selects_duplicate_monetary_block_explicitly(self):
        duplicated = MONTHLY_HEADERS + (
            "TOTAL_EMISION",
            "TOTAL_INTERES",
            "TOTAL_COACTIVA",
            "TOTAL_RECARGO",
        )
        current = dataset(
            record("actual-2", 2),
            period=date(2026, 7, 1),
            headers=duplicated,
            profile_id="julio_2026_confirmado",
            selected_occurrences={
                "TOTAL_EMISION": 2,
                "TOTAL_INTERES": 2,
                "TOTAL_COACTIVA": 2,
                "TOTAL_RECARGO": 2,
            },
        )

        report = validate(ValidationInput(current), (RuleCode.SCHEMA_002,))

        self.assertEqual(report.issues, ())
        self.assertIn(RuleCode.SCHEMA_002, report.executed_rules)

    def test_declaring_july_profile_without_applying_occurrences_is_blocking(self):
        duplicated = MONTHLY_HEADERS + (
            "TOTAL_EMISION",
            "TOTAL_INTERES",
            "TOTAL_COACTIVA",
            "TOTAL_RECARGO",
        )
        current = dataset(
            record("actual-2", 2),
            period=date(2026, 7, 1),
            headers=duplicated,
            profile_id="julio_2026_confirmado",
        )

        report = validate(ValidationInput(current), (RuleCode.SCHEMA_002,))

        self.assertEqual(len(report.issues), 1)
        self.assertTrue(report.issues[0].blocking)
        self.assertEqual(report.issues[0].evidence["apariciones_aplicadas"], {})

    def test_july_profile_rejects_an_unexpected_third_occurrence(self):
        duplicated = MONTHLY_HEADERS + (
            "TOTAL_EMISION",
            "TOTAL_INTERES",
            "TOTAL_COACTIVA",
            "TOTAL_RECARGO",
            "TOTAL_EMISION",
        )
        current = dataset(
            record("actual-2", 2),
            period=date(2026, 7, 1),
            headers=duplicated,
            profile_id="julio_2026_confirmado",
            selected_occurrences={
                "TOTAL_EMISION": 2,
                "TOTAL_INTERES": 2,
                "TOTAL_COACTIVA": 2,
                "TOTAL_RECARGO": 2,
            },
        )

        report = validate(ValidationInput(current), (RuleCode.SCHEMA_002,))

        self.assertEqual(len(report.issues), 1)
        self.assertTrue(report.issues[0].blocking)

    def test_blank_and_repeated_titles_are_blocking(self):
        current = dataset(
            record("actual-2", 2, clave=""),
            record("actual-3", 3, clave="000123"),
            record("actual-4", 4, clave="000123"),
        )

        report = validate(ValidationInput(current), (RuleCode.KEY_001,))

        self.assertEqual(len(report.issues), 3)
        self.assertTrue(all(issue.blocking for issue in report.issues))
        self.assertEqual({issue.subject.source_row for issue in report.issues}, {2, 3, 4})

    def test_large_duplicate_group_caps_embedded_relations(self):
        current = dataset(
            *(record(f"actual-{row}", row, clave="000123") for row in range(2, 62))
        )

        report = validate(ValidationInput(current), (RuleCode.KEY_001,))

        self.assertEqual(len(report.issues), 60)
        self.assertTrue(all(len(issue.related) <= 50 for issue in report.issues))
        self.assertEqual(report.issues[0].evidence["cantidad_total"], 60)
        self.assertEqual(report.issues[0].evidence["cantidad_omitida"], 10)

    def test_identity_change_between_months_requires_review(self):
        current = dataset(record("actual-2", 2, ciu="000999"))
        reference = dataset(
            record("referencia-2", 2, dataset_id="referencia", ciu="000987"),
            dataset_id="referencia",
            role=DatasetRole.REFERENCE,
        )

        report = validate(
            ValidationInput(current=current, reference=reference),
            (RuleCode.KEY_002,),
        )

        self.assertEqual(len(report.issues), 1)
        issue = report.issues[0]
        self.assertEqual(issue.rule_code, RuleCode.KEY_002)
        self.assertEqual(issue.severity, Severity.WARNING)
        self.assertFalse(issue.blocking)
        self.assertTrue(issue.requires_review)

    def test_exact_duplicate_rows_generate_catalog_issues(self):
        current = dataset(
            record("actual-2", 2),
            record("actual-3", 3),
        )

        report = validate(ValidationInput(current), (RuleCode.CAT_001,))

        self.assertEqual(len(report.issues), 2)
        self.assertEqual({issue.subject.source_row for issue in report.issues}, {2, 3})

    def test_consolidation_mismatch_generates_dup_issue(self):
        current = dataset(record("actual-2", 2))
        consolidated_record = record(
            "consolidado-2",
            2,
            dataset_id="consolidado",
            extra={
                "EMISION": cell("999.00"),
                "INTERES": cell("10.00"),
                "COACTIVA": cell("5.00"),
                "TOTAL_RECARGO": cell("2.00"),
            },
        )
        consolidated = dataset(
            consolidated_record,
            dataset_id="consolidado",
            role=DatasetRole.CONSOLIDATED,
            parent_dataset_id="actual",
        )

        report = validate(
            ValidationInput(current=current, consolidated=consolidated),
            (RuleCode.DUP_001,),
        )

        self.assertEqual(len(report.issues), 1)
        self.assertEqual(report.issues[0].evidence["estado"], "no_match")
        self.assertFalse(report.issues[0].blocking)

    def test_formula_and_excel_error_generate_separate_blocking_issues(self):
        current = dataset(
            record(
                "actual-2",
                2,
                extra={
                    "TOTAL_EMISION": cell(
                        None, raw="=SUM(A1:A2)", kind=CellKind.FORMULA
                    ),
                    "TOTAL_INTERES": cell(
                        "#N/A", raw="#N/A", kind=CellKind.ERROR
                    ),
                },
            )
        )

        report = validate(ValidationInput(current), (RuleCode.FORMULA_001,))

        self.assertEqual(len(report.issues), 2)
        self.assertEqual(
            {issue.field_name for issue in report.issues},
            {"TOTAL_EMISION", "TOTAL_INTERES"},
        )
        self.assertTrue(all(issue.blocking for issue in report.issues))

    def test_formula_in_reference_is_warning_without_blocking_current_batch(self):
        current = dataset(record("actual-2", 2))
        reference = dataset(
            record(
                "referencia-2",
                2,
                dataset_id="referencia",
                extra={
                    "TOTAL_EMISION": cell(
                        None, raw="=SUM(A1:A2)", kind=CellKind.FORMULA
                    )
                },
            ),
            dataset_id="referencia",
            role=DatasetRole.REFERENCE,
        )

        report = validate(
            ValidationInput(current=current, reference=reference),
            (RuleCode.FORMULA_001,),
        )

        self.assertEqual(len(report.issues), 1)
        self.assertEqual(report.issues[0].severity, Severity.WARNING)
        self.assertFalse(report.issues[0].blocking)

    def test_invalid_non_finite_amount_is_blocking_schema_issue(self):
        current = dataset(record("actual-2", 2, total_emision="NaN"))

        report = validate(ValidationInput(current), (RuleCode.SCHEMA_001,))

        self.assertEqual(len(report.issues), 1)
        self.assertEqual(report.issues[0].evidence["tipo"], "importe_invalido")
        self.assertTrue(report.issues[0].blocking)

    def test_blank_amount_is_invalid_but_zero_is_valid(self):
        blank = dataset(
            record(
                "actual-2",
                2,
                extra={"TOTAL_EMISION": cell(None, kind=CellKind.BLANK)},
            )
        )
        zero = dataset(record("actual-2", 2, total_emision="0"))

        blank_report = validate(ValidationInput(blank), (RuleCode.SCHEMA_001,))
        zero_report = validate(ValidationInput(zero), (RuleCode.SCHEMA_001,))

        self.assertEqual(len(blank_report.issues), 1)
        self.assertEqual(blank_report.issues[0].field_name, "TOTAL_EMISION")
        self.assertEqual(zero_report.issues, ())

    def test_blank_required_identity_is_blocking_schema_issue(self):
        current = dataset(record("actual-2", 2, cedula_ruc=""))

        report = validate(ValidationInput(current), (RuleCode.SCHEMA_001,))

        self.assertEqual(len(report.issues), 1)
        self.assertEqual(report.issues[0].field_name, "CEDULA_RUC")
        self.assertEqual(report.issues[0].evidence["tipo"], "campo_requerido_vacio")
        self.assertTrue(report.issues[0].blocking)

    def test_non_finite_required_identifier_is_treated_as_blank(self):
        current = dataset(record("actual-2", 2, cedula_ruc=float("nan")))

        report = validate(ValidationInput(current), (RuleCode.SCHEMA_001,))

        self.assertEqual(len(report.issues), 1)
        self.assertEqual(report.issues[0].field_name, "CEDULA_RUC")
        self.assertEqual(report.issues[0].evidence["tipo"], "campo_requerido_vacio")

    def test_auxiliary_formula_does_not_block_full_validation(self):
        current = dataset(record("actual-2", 2))
        reference = dataset(
            record(
                "referencia-2",
                2,
                dataset_id="referencia",
                extra={
                    "TOTAL_EMISION": cell(
                        None, raw="=SUM(A1:A2)", kind=CellKind.FORMULA
                    )
                },
            ),
            dataset_id="referencia",
            role=DatasetRole.REFERENCE,
        )

        report = validate(ValidationInput(current=current, reference=reference))

        self.assertEqual(report.blocking_count, 0)
        self.assertTrue(report.issues_for(RuleCode.SCHEMA_001))
        self.assertTrue(report.issues_for(RuleCode.FORMULA_001))
        self.assertTrue(
            all(
                issue.severity == Severity.WARNING
                for issue in report.issues_for(RuleCode.SCHEMA_001)
                + report.issues_for(RuleCode.FORMULA_001)
            )
        )

    def test_monthly_absence_never_becomes_a_payment_issue(self):
        current = dataset(record("actual-2", 2, clave="000200"))
        reference = dataset(
            record("referencia-2", 2, dataset_id="referencia", clave="000100"),
            dataset_id="referencia",
            role=DatasetRole.REFERENCE,
        )

        report = validate(
            ValidationInput(current=current, reference=reference),
            (RuleCode.MONTH_001, RuleCode.PAYMENT_001),
        )

        self.assertEqual(len(report.issues_for(RuleCode.MONTH_001)), 2)
        self.assertEqual(report.issues_for(RuleCode.PAYMENT_001), ())
        absence = next(
            issue
            for issue in report.issues_for(RuleCode.MONTH_001)
            if issue.evidence["tipo"] == "ausencia"
        )
        self.assertFalse(absence.evidence["implica_pago"])
        self.assertFalse(absence.blocking)

    def test_monthly_amount_change_is_reported_as_informational_review(self):
        current = dataset(record("actual-2", 2, total_emision="101.00"))
        reference = dataset(
            record(
                "referencia-2",
                2,
                dataset_id="referencia",
                total_emision="100.00",
            ),
            dataset_id="referencia",
            role=DatasetRole.REFERENCE,
        )

        report = validate(
            ValidationInput(current=current, reference=reference),
            (RuleCode.MONTH_001,),
        )

        self.assertEqual(len(report.issues), 1)
        issue = report.issues[0]
        self.assertEqual(issue.evidence["tipo"], "cambio_importe")
        self.assertEqual(issue.severity, Severity.INFO)
        self.assertFalse(issue.evidence["implica_pago"])

    def test_month_rules_are_explicitly_skipped_without_reference(self):
        report = validate(
            ValidationInput(dataset(record("actual-2", 2))),
            (RuleCode.KEY_002, RuleCode.MONTH_001),
        )

        self.assertEqual(report.executed_rules, ())
        self.assertEqual(set(report.skipped_rules), {RuleCode.KEY_002, RuleCode.MONTH_001})

    def test_payment_without_evidence_and_double_control_is_blocking(self):
        item = record("actual-2", 2)
        current = dataset(item)
        claim = PaymentClaim(
            record=item,
            requested_status="CANCELADO",
            requested_by="analista-1",
            evidence_id=None,
            authorized_source=False,
        )

        report = validate(
            ValidationInput(current=current, payment_claims=(claim,)),
            (RuleCode.PAYMENT_001,),
        )

        self.assertEqual(len(report.issues), 1)
        self.assertTrue(report.issues[0].blocking)

    def test_requester_cannot_approve_own_payment_change(self):
        item = record("actual-2", 2)
        current = dataset(item)
        claim = PaymentClaim(
            record=item,
            requested_status="PAGADO",
            requested_by="analista-1",
            evidence_id="comprobante-ficticio-1",
            authorized_source=True,
            approved_by="analista-1",
            approved_at=datetime(2026, 10, 9, 9, 0),
        )

        report = validate(
            ValidationInput(current=current, payment_claims=(claim,)),
            (RuleCode.PAYMENT_001,),
        )

        self.assertEqual(len(report.issues), 1)
        self.assertTrue(report.issues[0].blocking)

    def test_payment_double_control_normalizes_users_and_rejects_blank_evidence(self):
        item = record("actual-2", 2)
        current = dataset(item)
        claim = PaymentClaim(
            record=item,
            requested_status="PAGADO",
            requested_by="analista-1",
            evidence_id="   ",
            authorized_source=True,
            approved_by=" ANALISTA-1 ",
            approved_at=datetime(2026, 10, 9, 9, 0),
        )

        report = validate(
            ValidationInput(current=current, payment_claims=(claim,)),
            (RuleCode.PAYMENT_001,),
        )

        self.assertEqual(len(report.issues), 1)
        self.assertTrue(report.issues[0].blocking)

    def test_payment_claim_with_unknown_status_fails_closed(self):
        item = record("actual-2", 2)
        claim = PaymentClaim(
            record=item,
            requested_status="ESTADO-NUEVO",
            requested_by="analista-1",
            evidence_id="comprobante-1",
            authorized_source=True,
            approved_by="jefe-1",
            approved_at=datetime(2026, 10, 9, 9, 0),
        )

        report = validate(
            ValidationInput(current=dataset(item), payment_claims=(claim,)),
            (RuleCode.PAYMENT_001,),
        )

        self.assertEqual(len(report.issues), 1)
        self.assertEqual(report.issues[0].evidence["tipo"], "estado_no_reconocido")
        self.assertTrue(report.issues[0].blocking)

    def test_authorized_evidence_with_a_different_approver_passes(self):
        item = record("actual-2", 2)
        current = dataset(item)
        claim = PaymentClaim(
            record=item,
            requested_status="PAGADO",
            requested_by="analista-1",
            evidence_id="comprobante-ficticio-1",
            authorized_source=True,
            approved_by="jefe-1",
            approved_at=datetime(2026, 10, 9, 9, 0),
        )

        report = validate(
            ValidationInput(current=current, payment_claims=(claim,)),
            (RuleCode.PAYMENT_001,),
        )

        self.assertEqual(report.issues, ())

    def test_order_rejects_non_numeric_amount(self):
        current = dataset(record("actual-2", 2))
        order = record(
            "orden-2",
            2,
            dataset_id="ordenes",
            extra={
                "ID_PLAN": cell("PLAN-1"),
                "EMISION": cell("100.00"),
                "INTERES": cell("10.00"),
                "RECARGO": cell("2.00"),
                "TOTAL": cell("abc"),
            },
        )
        orders = dataset(
            order,
            dataset_id="ordenes",
            role=DatasetRole.ORDERS,
            schema_name="ordenPreliminar",
            parent_dataset_id="actual",
        )

        report = validate(
            ValidationInput(current=current, orders=orders),
            (RuleCode.ORDER_002,),
        )

        self.assertEqual(len(report.issues), 1)
        self.assertEqual(report.issues[0].field_name, "TOTAL")
        self.assertEqual(report.issues[0].evidence["tipo"], "importe_invalido")

    def test_order_traces_to_consolidated_without_optional_title_key(self):
        current = dataset(record("actual-2", 2))
        consolidated = dataset(
            record(
                "consolidado-2",
                2,
                dataset_id="consolidado",
                clave="",
                extra={"PREDIO_MUN": cell("PREDIO-001")},
            ),
            dataset_id="consolidado",
            role=DatasetRole.CONSOLIDATED,
            schema_name="carteraUnificada",
            parent_dataset_id="actual",
        )
        orders = dataset(
            record(
                "orden-2",
                2,
                dataset_id="ordenes",
                clave="TITULO-ORDEN",
                extra={"PREDIO_MUN": cell("PREDIO-001")},
            ),
            dataset_id="ordenes",
            role=DatasetRole.ORDERS,
            schema_name="ordenPreliminar",
            parent_dataset_id="consolidado",
        )

        report = validate(
            ValidationInput(
                current=current,
                consolidated=consolidated,
                orders=orders,
            ),
            (RuleCode.ORDER_001,),
        )

        self.assertEqual(report.issues, ())

    def test_catalog_uses_new_key_or_legacy_key_per_record(self):
        current = dataset(record("actual-2", 2))
        catalog = dataset(
            record(
                "catalogo-2",
                2,
                dataset_id="catalogo",
                clave="VIEJA-A",
                extra={"CLAVE_NUEV": cell("NUEVA-A")},
            ),
            record(
                "catalogo-3",
                3,
                dataset_id="catalogo",
                clave="VIEJA-X",
                cedula_ruc="0911111111",
                extra={"CLAVE_NUEV": cell("")},
            ),
            record(
                "catalogo-4",
                4,
                dataset_id="catalogo",
                clave="VIEJA-X",
                cedula_ruc="0922222222",
                extra={"CLAVE_NUEV": cell("")},
            ),
            dataset_id="catalogo",
            role=DatasetRole.CATALOG,
        )

        report = validate(
            ValidationInput(current=current, catalog=catalog),
            (RuleCode.CAT_001,),
        )

        self.assertEqual(len(report.issues), 2)
        self.assertEqual(
            {issue.subject.record_id for issue in report.issues},
            {"catalogo-3", "catalogo-4"},
        )

    def test_one_row_can_accumulate_independent_issues(self):
        current = dataset(
            record(
                "actual-2",
                2,
                clave="",
                extra={
                    "TOTAL_EMISION": cell(
                        None, raw="=1+1", kind=CellKind.FORMULA
                    )
                },
            )
        )

        report = validate(
            ValidationInput(current),
            (RuleCode.KEY_001, RuleCode.FORMULA_001),
        )

        self.assertEqual(
            {issue.rule_code for issue in report.issues},
            {RuleCode.KEY_001, RuleCode.FORMULA_001},
        )
        self.assertEqual({issue.subject.source_row for issue in report.issues}, {2})
