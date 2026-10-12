from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase

from apps.validation.contracts import (
    ENGINE_VERSION,
    DatasetRole,
    FieldCell,
    PaymentClaim,
    RuleCode,
    RuleResult,
    Severity,
    SubjectRef,
    ValidationInput,
    ValidationReport,
)

from .factories import dataset, record


class ContractTests(SimpleTestCase):
    databases = []

    def test_record_keeps_identifiers_with_leading_zeroes(self):
        item = record("fila-2", 2, clave="000123", ciu="000987")

        self.assertEqual(item.text("clave"), "000123")
        self.assertEqual(item.text("ciu"), "000987")

    def test_field_cell_rejects_mutable_runtime_values(self):
        with self.assertRaisesRegex(TypeError, "escalar"):
            FieldCell(value=["dato mutable"])

    def test_record_requires_a_positive_source_row(self):
        with self.assertRaisesRegex(ValueError, "source_row"):
            record("fila-invalida", 0)

    def test_record_rejects_non_finite_decimals(self):
        item = record("fila-2", 2, total_emision=Decimal("NaN"))

        self.assertIsNone(item.decimal("TOTAL_EMISION"))

    def test_dataset_rejects_records_from_another_dataset(self):
        foreign_record = record("fila-2", 2, dataset_id="otro")

        with self.assertRaisesRegex(ValueError, "dataset"):
            dataset(foreign_record, dataset_id="actual")

    def test_contracts_are_immutable(self):
        item = record("fila-2", 2)

        with self.assertRaises(FrozenInstanceError):
            item.source_row = 99
        with self.assertRaises(TypeError):
            item.fields["CLAVE"] = item.cell("CLAVE")

    def test_rule_catalog_exposes_the_eleven_agreed_codes(self):
        self.assertEqual(
            {code.value for code in RuleCode},
            {
                "SCHEMA-001",
                "SCHEMA-002",
                "KEY-001",
                "KEY-002",
                "DUP-001",
                "CAT-001",
                "FORMULA-001",
                "MONTH-001",
                "PAYMENT-001",
                "ORDER-001",
                "ORDER-002",
            },
        )

    def test_fingerprint_is_stable_when_evidence_order_changes(self):
        subject = SubjectRef.from_record(
            record("fila-2", 2),
            dataset(record("fila-2", 2)),
        )
        common = {
            "rule_code": RuleCode.KEY_001,
            "severity": Severity.CRITICAL,
            "blocking": True,
            "requires_review": True,
            "subject": subject,
        }

        first = RuleResult(**common, evidence={"actual": "A", "anterior": "B"})
        second = RuleResult(**common, evidence={"anterior": "B", "actual": "A"})

        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_fingerprint_changes_with_material_evidence(self):
        current = dataset(record("fila-2", 2))
        subject = SubjectRef.from_record(current.records[0], current)
        first = RuleResult(
            RuleCode.KEY_001,
            Severity.CRITICAL,
            True,
            True,
            subject,
            evidence={"clave": "000123"},
        )
        changed = RuleResult(
            RuleCode.KEY_001,
            Severity.CRITICAL,
            True,
            True,
            subject,
            evidence={"clave": "000124"},
        )

        self.assertNotEqual(first.fingerprint, changed.fingerprint)

    def test_fingerprint_changes_with_material_decision_flags(self):
        current = dataset(record("fila-2", 2))
        subject = SubjectRef.from_record(current.records[0], current)
        warning = RuleResult(
            RuleCode.KEY_002,
            Severity.WARNING,
            False,
            True,
            subject,
            evidence={"tipo": "conflicto"},
        )
        blocking = RuleResult(
            RuleCode.KEY_002,
            Severity.CRITICAL,
            True,
            True,
            subject,
            evidence={"tipo": "conflicto"},
        )

        self.assertNotEqual(warning.fingerprint, blocking.fingerprint)

    def test_payment_claim_cannot_target_reference_dataset(self):
        current_record = record("actual-2", 2)
        current = dataset(current_record)
        reference_record = record(
            "referencia-2",
            2,
            dataset_id="referencia",
        )
        reference = dataset(
            reference_record,
            dataset_id="referencia",
            role=DatasetRole.REFERENCE,
        )
        claim = PaymentClaim(
            record=reference_record,
            requested_status="PAGADO",
            requested_by="analista-1",
        )

        with self.assertRaisesRegex(ValueError, "cartera actual"):
            ValidationInput(
                current=current,
                reference=reference,
                payment_claims=(claim,),
            )

    def test_nested_evidence_is_copied_and_deeply_immutable(self):
        current = dataset(record("fila-2", 2))
        subject = SubjectRef.from_record(current.records[0], current)
        source = {"cambios": [{"campo": "CIU", "actual": "000987"}]}
        issue = RuleResult(
            RuleCode.KEY_002,
            Severity.WARNING,
            False,
            True,
            subject,
            evidence=source,
        )
        fingerprint = issue.fingerprint

        source["cambios"][0]["actual"] = "ALTERADO"

        self.assertEqual(issue.evidence["cambios"][0]["actual"], "000987")
        self.assertEqual(issue.fingerprint, fingerprint)
        with self.assertRaises(TypeError):
            issue.evidence["cambios"][0]["actual"] = "NO PERMITIDO"

    def test_payment_claim_must_reference_a_record_in_the_validation_input(self):
        current = dataset(record("fila-2", 2))
        foreign = record("externo-2", 2, dataset_id="externo")
        claim = PaymentClaim(
            record=foreign,
            requested_status="PAGADO",
            requested_by="analista-1",
        )

        with self.assertRaisesRegex(ValueError, "cartera actual"):
            ValidationInput(current=current, payment_claims=(claim,))

    def test_payment_claim_cannot_substitute_record_with_same_identifier(self):
        current = dataset(record("fila-2", 2, clave="000123"))
        altered = record("fila-2", 2, clave="ALTERADA")
        claim = PaymentClaim(
            record=altered,
            requested_status="PAGADO",
            requested_by="analista-1",
        )

        with self.assertRaisesRegex(ValueError, "cartera actual"):
            ValidationInput(current=current, payment_claims=(claim,))

    def test_validation_rejects_duplicate_dataset_identifiers(self):
        current = dataset(
            record("fila-2", 2, dataset_id="compartido"),
            dataset_id="compartido",
        )
        reference = dataset(
            record("referencia-2", 2, dataset_id="compartido"),
            dataset_id="compartido",
            role=DatasetRole.REFERENCE,
        )

        with self.assertRaisesRegex(ValueError, "dataset_id"):
            ValidationInput(current=current, reference=reference)

    def test_validation_requires_an_earlier_reference_period(self):
        current = dataset(record("actual-2", 2), period=date(2026, 8, 1))
        reference = dataset(
            record("referencia-2", 2, dataset_id="referencia"),
            dataset_id="referencia",
            role=DatasetRole.REFERENCE,
            period=date(2026, 9, 1),
        )

        with self.assertRaisesRegex(ValueError, "anterior"):
            ValidationInput(current=current, reference=reference)

    def test_validation_rejects_reference_with_different_schema(self):
        current = dataset(record("actual-2", 2))
        reference = dataset(
            record("referencia-2", 2, dataset_id="referencia"),
            dataset_id="referencia",
            role=DatasetRole.REFERENCE,
            schema_name="carteraUnificada",
        )

        with self.assertRaisesRegex(ValueError, "mismo esquema"):
            ValidationInput(current=current, reference=reference)

    def test_report_counts_blocking_issues_and_filters_by_rule(self):
        current = dataset(record("fila-2", 2))
        subject = SubjectRef.from_record(current.records[0], current)
        blocking = RuleResult(
            RuleCode.KEY_001,
            Severity.CRITICAL,
            True,
            True,
            subject,
        )
        informational = RuleResult(
            RuleCode.MONTH_001,
            Severity.INFO,
            False,
            False,
            subject,
        )
        report = ValidationReport(
            engine_version=ENGINE_VERSION,
            current_dataset_id=current.dataset_id,
            reference_dataset_id=None,
            issues=(blocking, informational),
            executed_rules=(RuleCode.KEY_001, RuleCode.MONTH_001),
        )

        self.assertEqual(report.blocking_count, 1)
        self.assertEqual(report.issues_for(RuleCode.MONTH_001), (informational,))
        self.assertEqual(current.role, DatasetRole.CURRENT)
