"""
Test suite for statistics module.

Tests for:
- Wilson CI calculation
- McNemar exact test
- Risk difference bootstrap
- Holm correction
- Cohen kappa with undefined cases
- Benchmark paired analysis
"""

import pytest
import math
from typing import Dict, List

from neurosurg_epi_agent.statistics import (
    WilsonCI,
    McNemarResult,
    RiskDifferenceResult,
    HolmResult,
    KappaResult,
    wilson_ci,
    exact_mcnemar_test,
    risk_difference_bootstrap,
    holm_correction,
    cohen_kappa,
    benchmark_paired_analysis,
    format_p_value,
    binomial_cdf,
    log_combination
)


class TestWilsonCI:
    """Test Wilson confidence interval calculations."""

    def test_wilson_ci_basic(self):
        """Test basic Wilson CI calculation."""
        # n=100, k=50 -> p=0.5
        result = wilson_ci(50, 100)

        assert result.proportion == 0.5
        assert result.n == 100
        assert 0.0 < result.ci_lower < 0.5
        assert 0.5 < result.ci_upper < 1.0
        assert result.ci_lower < result.ci_upper

    def test_wilson_ci_edge_cases(self):
        """Test Wilson CI with edge cases."""
        # All successes
        result = wilson_ci(100, 100)
        assert result.proportion == 1.0
        assert result.ci_upper == 1.0
        assert result.ci_lower >= 0.0

        # No successes
        result = wilson_ci(0, 100)
        assert result.proportion == 0.0
        assert result.ci_lower == 0.0
        assert result.ci_upper <= 1.0

    def test_wilson_ci_invalid_input(self):
        """Test Wilson CI with invalid inputs."""
        # Negative successes
        with pytest.raises(ValueError):
            wilson_ci(-1, 100)

        # Successes > n
        with pytest.raises(ValueError):
            wilson_ci(101, 100)

        # Zero sample size
        with pytest.raises(ValueError):
            wilson_ci(0, 0)


class TestMcNemarTest:
    """Test McNemar exact test calculations."""

    def test_mcnemar_perfect_agreement(self):
        """Test McNemar with perfect agreement (no discordant pairs)."""
        table = {
            'row1': {'col1': 50, 'col2': 0},
            'row2': {'col1': 0, 'col2': 50}
        }

        result = exact_mcnemar_test(table, two_sided=True)

        assert result.p_value == 1.0
        assert result.discordant_pairs == 0
        assert "perfect agreement" in result.notes.lower()

    def test_mcnemar_balanced_discordant(self):
        """Test McNemar with balanced discordant pairs (b=c=10)."""
        table = {
            'row1': {'col1': 40, 'col2': 10},
            'row2': {'col1': 10, 'col2': 40}
        }

        result = exact_mcnemar_test(table, two_sided=True)

        assert result.discordant_pairs == 20
        assert result.p_value > 0.5  # Should not be significant with balanced discordants
        assert result.statistic == 10.0  # min(b, c) = 10

    def test_mcnemar_asymmetric_discordant(self):
        """Test McNemar with asymmetric discordant pairs (b=5, c=15)."""
        table = {
            'row1': {'col1': 40, 'col2': 5},
            'row2': {'col1': 15, 'col2': 40}
        }

        result = exact_mcnemar_test(table, two_sided=True)

        assert result.discordant_pairs == 20
        assert result.statistic == 5.0  # min(b, c) = 5
        assert result.p_value < 0.1  # Should be significant

    def test_mcnemar_one_sided(self):
        """Test one-sided McNemar test."""
        table = {
            'row1': {'col1': 40, 'col2': 5},
            'row2': {'col1': 15, 'col2': 40}
        }

        result_one_sided = exact_mcnemar_test(table, two_sided=False)
        result_two_sided = exact_mcnemar_test(table, two_sided=True)

        # One-sided should be half (approximately) of two-sided
        assert result_one_sided.p_value < result_two_sided.p_value


class TestRiskDifferenceBootstrap:
    """Test risk difference with bootstrap CI."""

    def test_risk_difference_basic(self):
        """Test basic risk difference calculation."""
        arm1 = [True] * 10 + [False] * 10  # p1 = 0.5
        arm2 = [True] * 5 + [False] * 15  # p2 = 0.25

        result = risk_difference_bootstrap(arm1, arm2, bootstrap_samples=1000, seed=20260628)

        assert result.rd == pytest.approx(0.25, abs=0.01)  # 0.5 - 0.25 = 0.25
        assert result.n_pairs == 20
        assert result.bootstrap_samples == 1000
        assert result.ci_lower < result.rd < result.ci_upper

    def test_risk_difference_no_difference(self):
        """Test risk difference when arms are identical."""
        arm1 = [True] * 8 + [False] * 12  # p = 0.4
        arm2 = [True] * 8 + [False] * 12  # p = 0.4

        result = risk_difference_bootstrap(arm1, arm2, bootstrap_samples=1000, seed=20260628)

        assert result.rd == pytest.approx(0.0, abs=0.05)
        # CI should include 0
        assert result.ci_lower <= 0.0 <= result.ci_upper

    def test_risk_difference_mismatched_lengths(self):
        """Test error handling for mismatched arm lengths."""
        arm1 = [True, False, True]
        arm2 = [True, False]  # Shorter

        with pytest.raises(ValueError):
            risk_difference_bootstrap(arm1, arm2)

    def test_risk_difference_reproducibility(self):
        """Test that same seed produces identical results."""
        arm1 = [True] * 10 + [False] * 10
        arm2 = [True] * 5 + [False] * 15

        result1 = risk_difference_bootstrap(arm1, arm2, bootstrap_samples=100, seed=42)
        result2 = risk_difference_bootstrap(arm1, arm2, bootstrap_samples=100, seed=42)

        assert result1.rd == result2.rd
        assert result1.ci_lower == result2.ci_lower
        assert result1.ci_upper == result2.ci_upper


class TestHolmCorrection:
    """Test Holm-Bonferroni correction."""

    def test_holm_basic(self):
        """Test basic Holm correction."""
        p_values = [0.001, 0.01, 0.05, 0.10, 0.20]

        result = holm_correction(p_values, alpha=0.05)

        assert len(result.corrected_p) == 5
        assert len(result.rejected) == 5

        # First should be rejected (p < alpha/5)
        assert result.rejected[0] is True
        # Last should not be rejected (p > alpha)
        assert result.rejected[4] is False

    def test_holm_all_significant(self):
        """Test Holm when all p-values are significant."""
        p_values = [0.001, 0.002, 0.003, 0.004, 0.005]

        result = holm_correction(p_values, alpha=0.05)

        # All should be rejected
        assert all(result.rejected)

    def test_holm_none_significant(self):
        """Test Holm when no p-values are significant."""
        p_values = [0.10, 0.15, 0.20, 0.25, 0.30]

        result = holm_correction(p_values, alpha=0.05)

        # None should be rejected
        assert not any(result.rejected)

    def test_holm_empty_input(self):
        """Test Holm with empty input."""
        result = holm_correction([], alpha=0.05)

        assert len(result.corrected_p) == 0
        assert len(result.rejected) == 0


class TestCohenKappa:
    """Test Cohen's kappa calculations."""

    def test_kappa_perfect_agreement(self):
        """Test kappa with perfect agreement."""
        ratings1 = ['A', 'A', 'B', 'B']
        ratings2 = ['A', 'A', 'B', 'B']

        result = cohen_kappa(ratings1, ratings2)

        assert result.kappa == pytest.approx(1.0, abs=0.01)
        assert result.observed_agreement == 1.0
        assert result.warning is None

    def test_kappa_no_agreement(self):
        """Test kappa with no agreement beyond chance."""
        ratings1 = ['A', 'A', 'A', 'A']
        ratings2 = ['B', 'B', 'B', 'B']

        result = cohen_kappa(ratings1, ratings2)

        assert result.kappa == pytest.approx(0.0, abs=0.01)
        assert result.observed_agreement == 0.0

    def test_kappa_with_undefined_values(self):
        """Test kappa with None/undefined values."""
        ratings1 = ['A', 'A', None, 'B']
        ratings2 = ['A', 'B', 'B', 'B']

        result = cohen_kappa(ratings1, ratings2)

        assert result.n == 3  # 3 valid pairs (None excluded)
        assert result.warning is not None
        assert "undefined" in result.warning.lower()

    def test_kappa_all_undefined(self):
        """Test kappa when all pairs are undefined."""
        ratings1 = [None, None, None]
        ratings2 = [None, None, None]

        result = cohen_kappa(ratings1, ratings2)

        assert math.isnan(result.kappa)
        assert result.n == 0
        assert result.warning is not None

    def test_kappa_single_category(self):
        """Test kappa when only one category exists."""
        ratings1 = ['A', 'A', 'A']
        ratings2 = ['A', 'A', 'A']

        result = cohen_kappa(ratings1, ratings2)

        assert math.isnan(result.kappa)
        assert result.warning is not None
        assert "category" in result.warning.lower()

    def test_kappa_chance_agreement_one(self):
        """Test kappa when chance agreement is 1.0."""
        # All ratings are the same category -> expected agreement = 1.0
        ratings1 = ['A'] * 100
        ratings2 = ['A'] * 100

        result = cohen_kappa(ratings1, ratings2)

        assert math.isnan(result.kappa)
        assert result.expected_agreement == 1.0
        assert result.warning is not None


class TestBenchmarkPairedAnalysis:
    """Test benchmark-level paired analysis."""

    def test_paired_analysis_basic(self):
        """Test basic paired analysis between two arms."""
        arm1_results = [
            {'task_id': 'task1', 'database_routing_correct': True, 'feasibility_correct': True},
            {'task_id': 'task2', 'database_routing_correct': True, 'feasibility_correct': False},
            {'task_id': 'task3', 'database_routing_correct': False, 'feasibility_correct': True},
        ]

        arm2_results = [
            {'task_id': 'task1', 'database_routing_correct': True, 'feasibility_correct': True},
            {'task_id': 'task2', 'database_routing_correct': False, 'feasibility_correct': False},
            {'task_id': 'task3', 'database_routing_correct': True, 'feasibility_correct': False},
        ]

        result = benchmark_paired_analysis(arm1_results, arm2_results)

        assert result['n_common'] == 3
        assert 'metrics' in result
        assert 'database_routing_correct' in result['metrics']
        assert 'feasibility_correct' in result['metrics']

        # Check McNemar test is present
        assert 'mcnemar' in result['metrics']['database_routing_correct']
        assert 'p_value' in result['metrics']['database_routing_correct']['mcnemar']

    def test_paired_analysis_no_common_tasks(self):
        """Test paired analysis with no common tasks."""
        arm1_results = [
            {'task_id': 'task1', 'database_routing_correct': True},
        ]

        arm2_results = [
            {'task_id': 'task2', 'database_routing_correct': True},
        ]

        result = benchmark_paired_analysis(arm1_results, arm2_results)

        assert result['n_common'] == 0
        assert 'error' in result

    def test_paired_analysis_holm_correction(self):
        """Test that Holm correction is applied across metrics."""
        arm1_results = [
            {'task_id': 'task1', 'metric1': True, 'metric2': True},
            {'task_id': 'task2', 'metric1': True, 'metric2': False},
        ]

        arm2_results = [
            {'task_id': 'task1', 'metric1': True, 'metric2': False},
            {'task_id': 'task2', 'metric1': False, 'metric2': True},
        ]

        result = benchmark_paired_analysis(arm1_results, arm2_results,
                                          metrics=['metric1', 'metric2'])

        # Check Holm correction metadata
        assert 'holm_correction' in result
        assert result['holm_correction']['n_tests'] == 2

        # Check corrected p-values are present
        assert 'p_value_holm' in result['metrics']['metric1']['mcnemar']
        assert 'rejected_holm' in result['metrics']['metric1']['mcnemar']


class TestUtilityFunctions:
    """Test utility functions."""

    def test_format_p_value_extreme(self):
        """Test p-value formatting for extreme values."""
        # Very small p-value
        assert format_p_value(1e-15) == "p < 1e-10"

        # Small but not extreme
        assert format_p_value(0.0005) == "p = 5.0000e-04"

        # Regular p-value
        assert format_p_value(0.045) == "p = 0.0450"

    def test_binomial_cdf(self):
        """Test binomial CDF calculation."""
        # P(X <= 0) for Binomial(10, 0.5) should be (0.5)^10
        result = binomial_cdf(0, 10, 0.5)
        expected = 0.5 ** 10
        assert result == pytest.approx(expected, rel=0.01)

        # P(X <= 10) should be 1.0
        result = binomial_cdf(10, 10, 0.5)
        assert result == 1.0

    def test_log_combination(self):
        """Test log combination calculation."""
        # log(C(5, 2)) = log(10)
        result = log_combination(5, 2)
        expected = math.log(10)
        assert result == pytest.approx(expected, rel=0.01)

        # C(n, 0) = 1, so log(1) = 0
        result = log_combination(5, 0)
        assert result == 0.0

        # C(n, n) = 1, so log(1) = 0
        result = log_combination(5, 5)
        assert result == 0.0


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_inputs(self):
        """Test functions with empty inputs."""
        # Wilson CI with n=0
        with pytest.raises(ValueError):
            wilson_ci(0, 0)

        # McNemar with zero discordant
        table = {'row1': {'col1': 10, 'col2': 0}, 'row2': {'col1': 0, 'col2': 10}}
        result = exact_mcnemar_test(table)
        assert result.p_value == 1.0

    def test_preserve_denominators(self):
        """Test that exact denominators are preserved."""
        # Test with specific n values
        for n in [10, 30, 50, 100]:
            result = wilson_ci(n//2, n)
            assert result.n == n

    def test_never_p_equals_zero(self):
        """Test that p = 0.0 is never returned."""
        # Create extreme case
        table = {'row1': {'col1': 100, 'col2': 0}, 'row2': {'col1': 0, 'col2': 100}}

        result = exact_mcnemar_test(table)

        # Should be exactly 1.0 for perfect agreement, not 0.0
        assert result.p_value >= 1e-10 or result.p_value == 1.0