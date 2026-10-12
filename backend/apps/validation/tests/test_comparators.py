from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase

from apps.validation.comparators import (
    ConsolidationStatus,
    canonical_key,
    compare_months,
    compare_order_traceability,
    exact_row_fingerprint,
    group_by_key,
    reconcile_consolidated,
)
from apps.validation.contracts import DatasetRole

from .factories import cell, dataset, record


class ComparatorTests(SimpleTestCase):
    databases = []

    def test_canonical_key_preserves_leading_zeroes(self):
        item = record("actual-2", 2, clave="000123", ciu="000987")

        self.assertEqual(canonical_key(item, ("CLAVE", "CIU")), ("000123", "000987"))

    def test_canonical_key_requires_every_component(self):
        item = record("actual-2", 2, clave="", ciu="000987")

        self.assertIsNone(canonical_key(item, ("CLAVE", "CIU")))

    def test_canonical_key_rejects_non_finite_identifier(self):
        item = record("actual-2", 2, clave=float("nan"))

        self.assertIsNone(canonical_key(item, ("CLAVE",)))

    def test_group_by_key_keeps_distinct_titles_for_the_same_person(self):
        first = record("actual-2", 2, clave="000101")
        second = record("actual-3", 3, clave="000102")

        groups = group_by_key((first, second), ("CLAVE",))

        self.assertEqual(set(groups), {("000101",), ("000102",)})
        self.assertEqual(sum(len(items) for items in groups.values()), 2)

    def test_exact_row_fingerprint_depends_on_cells_not_record_identity(self):
        first = record("actual-2", 2)
        same_values = record("actual-99", 99)
        changed = record("actual-3", 3, total_emision=Decimal("101.00"))

        self.assertEqual(exact_row_fingerprint(first), exact_row_fingerprint(same_values))
        self.assertNotEqual(exact_row_fingerprint(first), exact_row_fingerprint(changed))

    def test_compare_months_classifies_new_and_missing_without_calling_them_paid(self):
        current = dataset(
            record("actual-2", 2, clave="000200"),
            dataset_id="actual",
        )
        reference = dataset(
            record("referencia-2", 2, dataset_id="referencia", clave="000100"),
            dataset_id="referencia",
            role=DatasetRole.REFERENCE,
        )

        comparison = compare_months(current, reference)

        self.assertEqual([item.text("CLAVE") for item in comparison.new_records], ["000200"])
        self.assertEqual(
            [item.text("CLAVE") for item in comparison.missing_records], ["000100"]
        )
        self.assertFalse(hasattr(comparison, "paid_records"))

    def test_compare_months_detects_identity_changes_for_the_same_title(self):
        current = dataset(
            record("actual-2", 2, clave="000123", ciu="000999"),
            dataset_id="actual",
        )
        reference = dataset(
            record(
                "referencia-2",
                2,
                dataset_id="referencia",
                clave="000123",
                ciu="000987",
            ),
            dataset_id="referencia",
            role=DatasetRole.REFERENCE,
        )

        comparison = compare_months(current, reference)

        self.assertEqual(len(comparison.identity_changes), 1)
        self.assertEqual(comparison.identity_changes[0].changes[0].field_name, "CIU")
        self.assertEqual(comparison.identity_changes[0].changes[0].previous, "000987")
        self.assertEqual(comparison.identity_changes[0].changes[0].current, "000999")

    def test_compare_months_applies_one_cent_tolerance_to_amounts(self):
        reference = dataset(
            record(
                "referencia-2",
                2,
                dataset_id="referencia",
                total_emision=Decimal("100.00"),
            ),
            dataset_id="referencia",
            role=DatasetRole.REFERENCE,
        )
        within_tolerance = dataset(
            record("actual-2", 2, total_emision=Decimal("100.01")),
            dataset_id="actual",
        )
        outside_tolerance = dataset(
            record("actual-2", 2, total_emision=Decimal("100.02")),
            dataset_id="actual",
        )

        self.assertEqual(compare_months(within_tolerance, reference).amount_changes, ())
        changed = compare_months(outside_tolerance, reference).amount_changes
        self.assertEqual(len(changed), 1)
        self.assertEqual(changed[0].changes[0].field_name, "TOTAL_EMISION")

    def test_compare_months_handles_non_finite_amount_without_crashing(self):
        reference = dataset(
            record(
                "referencia-2",
                2,
                dataset_id="referencia",
                total_emision=Decimal("100.00"),
            ),
            dataset_id="referencia",
            role=DatasetRole.REFERENCE,
        )
        current = dataset(
            record("actual-2", 2, total_emision=Decimal("NaN")),
            dataset_id="actual",
        )

        comparison = compare_months(current, reference)

        self.assertEqual(len(comparison.amount_changes), 1)
        self.assertIsNone(comparison.amount_changes[0].changes[0].current)

    def test_compare_months_rejects_non_finite_tolerance(self):
        current = dataset(record("actual-2", 2))
        reference = dataset(
            record("referencia-2", 2, dataset_id="referencia"),
            dataset_id="referencia",
            role=DatasetRole.REFERENCE,
        )

        with self.assertRaisesRegex(ValueError, "tolerancia"):
            compare_months(current, reference, tolerance=Decimal("NaN"))

    def test_compare_months_rejects_equal_or_future_reference_period(self):
        current = dataset(record("actual-2", 2), period=date(2026, 8, 1))
        reference = dataset(
            record("referencia-2", 2, dataset_id="referencia"),
            dataset_id="referencia",
            role=DatasetRole.REFERENCE,
            period=date(2026, 8, 1),
        )

        with self.assertRaisesRegex(ValueError, "anterior"):
            compare_months(current, reference)

    def test_compare_months_rejects_unknown_periods(self):
        current = dataset(record("actual-2", 2), period=None)
        reference = dataset(
            record("referencia-2", 2, dataset_id="referencia"),
            dataset_id="referencia",
            role=DatasetRole.REFERENCE,
            period=None,
        )

        with self.assertRaisesRegex(ValueError, "declarar su periodo"):
            compare_months(current, reference)

    def test_compare_months_does_not_choose_arbitrarily_between_duplicate_keys(self):
        current = dataset(
            record("actual-2", 2, clave="000123"),
            record("actual-3", 3, clave="000123"),
            dataset_id="actual",
        )
        reference = dataset(
            record("referencia-2", 2, dataset_id="referencia", clave="000123"),
            dataset_id="referencia",
            role=DatasetRole.REFERENCE,
        )

        comparison = compare_months(current, reference)

        self.assertEqual(comparison.matched, ())
        self.assertEqual(len(comparison.ambiguous), 1)
        self.assertEqual(comparison.ambiguous[0].key, ("000123",))
        self.assertEqual(len(comparison.ambiguous[0].current), 2)

    def test_two_valid_titles_for_one_person_match_independently(self):
        current = dataset(
            record("actual-2", 2, clave="000101"),
            record("actual-3", 3, clave="000102"),
            dataset_id="actual",
        )
        reference = dataset(
            record("referencia-2", 2, dataset_id="referencia", clave="000101"),
            record("referencia-3", 3, dataset_id="referencia", clave="000102"),
            dataset_id="referencia",
            role=DatasetRole.REFERENCE,
        )

        comparison = compare_months(current, reference)

        self.assertEqual(len(comparison.matched), 2)
        self.assertEqual(comparison.ambiguous, ())
        self.assertEqual(comparison.new_records, ())
        self.assertEqual(comparison.missing_records, ())

    @staticmethod
    def _consolidated_record(
        record_id: str,
        row: int,
        *,
        cedula_ruc: str = "0912345678",
        ciu: str = "000987",
        emision: str = "100.00",
        interes: str = "10.00",
        coactiva: str = "5.00",
        recargo: str = "2.00",
    ):
        return record(
            record_id,
            row,
            dataset_id="consolidado",
            cedula_ruc=cedula_ruc,
            ciu=ciu,
            extra={
                "EMISION": cell(emision),
                "INTERES": cell(interes),
                "COACTIVA": cell(coactiva),
                "TOTAL_RECARGO": cell(recargo),
            },
        )

    def test_reconcile_consolidated_matches_one_source_row(self):
        source = dataset(record("actual-2", 2))
        consolidated = dataset(
            self._consolidated_record("consolidado-2", 2),
            dataset_id="consolidado",
            role=DatasetRole.CONSOLIDATED,
        )

        comparison = reconcile_consolidated(source, consolidated)

        self.assertEqual(
            [fact.status for fact in comparison.facts],
            [ConsolidationStatus.MATCHED],
        )

    def test_reconcile_consolidated_reports_missing_and_orphan_groups(self):
        source = dataset(record("actual-2", 2))
        consolidated = dataset(
            self._consolidated_record(
                "consolidado-2",
                2,
                cedula_ruc="0999999999",
                ciu="009999",
            ),
            dataset_id="consolidado",
            role=DatasetRole.CONSOLIDATED,
        )

        statuses = {fact.status for fact in reconcile_consolidated(source, consolidated).facts}

        self.assertEqual(
            statuses,
            {
                ConsolidationStatus.MISSING_CONSOLIDATED,
                ConsolidationStatus.NO_SOURCE,
            },
        )

    def test_reconcile_consolidated_distinguishes_mismatch_from_implicit_sum(self):
        source = dataset(
            record("actual-2", 2, clave="000101", total_emision="100.00"),
            record("actual-3", 3, clave="000102", total_emision="50.00"),
        )
        summed = dataset(
            self._consolidated_record(
                "consolidado-2",
                2,
                emision="150.00",
                interes="20.00",
                coactiva="10.00",
                recargo="4.00",
            ),
            dataset_id="consolidado",
            role=DatasetRole.CONSOLIDATED,
        )
        mismatch = dataset(
            self._consolidated_record("consolidado-2", 2, emision="999.00"),
            dataset_id="consolidado",
            role=DatasetRole.CONSOLIDATED,
        )

        summed_status = reconcile_consolidated(source, summed).facts[0].status
        mismatch_status = reconcile_consolidated(source, mismatch).facts[0].status

        self.assertEqual(summed_status, ConsolidationStatus.SUMMED_NOT_ALLOWED)
        self.assertEqual(mismatch_status, ConsolidationStatus.NO_MATCH)

    def test_reconcile_consolidated_rejects_more_than_one_row_per_group(self):
        source = dataset(record("actual-2", 2))
        consolidated = dataset(
            self._consolidated_record("consolidado-2", 2),
            self._consolidated_record("consolidado-3", 3),
            dataset_id="consolidado",
            role=DatasetRole.CONSOLIDATED,
        )

        facts = reconcile_consolidated(source, consolidated).facts

        self.assertEqual(len(facts), 2)
        self.assertTrue(
            all(
                fact.status == ConsolidationStatus.DUPLICATE_CONSOLIDATED
                for fact in facts
            )
        )

    def test_reconcile_consolidated_rejects_ambiguous_source_amount_match(self):
        source = dataset(
            record("actual-2", 2, clave="TITULO-A"),
            record("actual-3", 3, clave="TITULO-B"),
        )
        consolidated = dataset(
            self._consolidated_record("consolidado-2", 2),
            dataset_id="consolidado",
            role=DatasetRole.CONSOLIDATED,
        )

        facts = reconcile_consolidated(source, consolidated).facts

        self.assertEqual(len(facts), 1)
        self.assertEqual(
            facts[0].status,
            ConsolidationStatus.AMBIGUOUS_SOURCE_MATCH,
        )
        self.assertIsNone(facts[0].matched_record)

    def test_reconcile_consolidated_reports_rows_without_group_key(self):
        source = dataset(record("actual-2", 2, cedula_ruc=""))
        consolidated = dataset(
            self._consolidated_record("consolidado-2", 2, cedula_ruc=""),
            dataset_id="consolidado",
            role=DatasetRole.CONSOLIDATED,
        )

        facts = reconcile_consolidated(source, consolidated).facts

        self.assertEqual(len(facts), 2)
        self.assertTrue(
            all(fact.status == ConsolidationStatus.MISSING_GROUP_KEY for fact in facts)
        )

    def test_order_traceability_uses_title_and_person_identity(self):
        source = dataset(
            record("actual-2", 2, clave="TITULO-A"),
            record("actual-3", 3, clave="TITULO-B"),
        )
        exact_order = dataset(
            record("orden-2", 2, dataset_id="ordenes", clave="TITULO-A"),
            dataset_id="ordenes",
            role=DatasetRole.ORDERS,
        )
        wrong_title = dataset(
            record("orden-3", 3, dataset_id="ordenes-2", clave="TITULO-C"),
            dataset_id="ordenes-2",
            role=DatasetRole.ORDERS,
        )

        exact = compare_order_traceability(exact_order, source)
        missing = compare_order_traceability(wrong_title, source)

        self.assertEqual(len(exact.matched), 1)
        self.assertEqual(exact.ambiguous, ())
        self.assertEqual(len(missing.missing), 1)
