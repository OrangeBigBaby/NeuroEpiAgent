"""
NeuroSurgEpiAgent Statistics Module

Dependency-light statistics for benchmark evaluation metrics.

Implements:
- Wilson 95% confidence intervals for proportions
- Two-sided exact McNemar test using binomial distribution of discordant pairs
- Paired risk difference with task-level bootstrap 95% CI (fixed seed)
- Holm-Bonferroni correction for multiple testing
- Cohen's kappa with explicit handling of undefined cases
- Benchmark-level paired analysis from evaluation arm outputs

Design principles:
- Preserves exact denominators
- Never emits p = 0.0 (reports p < 1e-10 for extreme values)
- Handles undefined/edge cases explicitly
- Fixed random seed (20260628) for reproducibility
"""

import math
import copy
from typing import List, Dict, Tuple, Any, Optional
from dataclasses import dataclass
import random


@dataclass
class WilsonCI:
    """Wilson score interval for proportion."""
    proportion: float
    ci_lower: float
    ci_upper: float
    n: int

    def __str__(self) -> str:
        return f"{self.proportion:.4f} [{self.ci_lower:.4f}, {self.ci_upper:.ci_upper}]]"


@dataclass
class McNemarResult:
    """McNemar test result for paired binary outcomes."""
    statistic: float  # For exact test: this is the lesser of discordant counts
    p_value: float
    discordant_pairs: int
    table: Dict[str, Dict[str, int]]  # 2x2 contingency table
    notes: str

    def __str__(self) -> str:
        if self.p_value < 1e-10:
            p_str = "p < 1e-10"
        else:
            p_str = f"p = {self.p_value:.4e}"
        return f"McNemar: {p_str}, n_discordant={self.discordant_pairs}"


@dataclass
class RiskDifferenceResult:
    """Risk difference with bootstrap CI."""
    rd: float  # Risk difference
    ci_lower: float
    ci_upper: float
    n_pairs: int
    bootstrap_samples: int
    notes: str


@dataclass
class HolmResult:
    """Holm-Bonferroni correction results."""
    original_p: List[float]
    corrected_p: List[float]
    rejected: List[bool]
    alpha: float
    notes: str


@dataclass
class KappaResult:
    """Cohen's kappa with undefined case handling."""
    kappa: float
    ci_lower: float
    ci_upper: float
    observed_agreement: float
    expected_agreement: float
    n: int
    warning: Optional[str]  # Set if undefined cases encountered


def wilson_ci(num_successes: int, n: int, confidence: float = 0.95) -> WilsonCI:
    """
    Compute Wilson score interval for proportion.

    Args:
        num_successes: Number of successes
        n: Total sample size (exact denominator)
        confidence: Confidence level (default 0.95 for 95% CI)

    Returns:
        WilsonCI with proportion, CI bounds, and n

    References:
        Wilson, E. B. (1927). "Probable inference, the law of succession, and statistical inference".
        Journal of the American Statistical Association.
    """
    if n <= 0:
        raise ValueError(f"Sample size n must be positive, got {n}")

    if num_successes < 0 or num_successes > n:
        raise ValueError(f"num_successes must be in [0, n], got {num_successes} for n={n}")

    p = num_successes / n
    z = 1.96  # 95% CI corresponds to z = 1.96

    denominator = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denominator
    margin = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denominator

    # Clamp to exact [0, 1] bounds with tolerance for numerical precision
    epsilon = 1e-10
    ci_lower = center - margin
    ci_upper = center + margin

    # Ensure exact boundaries at 0.0 and 1.0 for edge cases
    if ci_lower < epsilon:
        ci_lower = 0.0
    if ci_upper > 1.0 - epsilon:
        ci_upper = 1.0

    return WilsonCI(
        proportion=p,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        n=n
    )


def exact_mcnemar_test(table: Dict[str, Dict[str, int]], two_sided: bool = True) -> McNemarResult:
    """
    Two-sided exact McNemar test using binomial distribution of discordant pairs.

    Args:
        table: 2x2 contingency table as dict:
            {
                'row1': {'col1': a, 'col2': b},
                'row2': {'col1': c, 'col2': d}
            }
            Where a=both positive, b=row1 positive/row2 negative,
            c=row1 negative/row2 positive, d=both negative
        two_sided: If True, use two-sided test (default)

    Returns:
        McNemarResult with p-value and discordant pair count

    References:
        McNemar, Q. (1947). "Note on the sampling error of the difference between
        correlated proportions or percentages". Psychometrika.
    """
    # Extract discordant pairs
    b = table['row1']['col2']  # row1 positive, row2 negative
    c = table['row2']['col1']  # row1 negative, row2 positive
    discordant = b + c

    if discordant == 0:
        # No discordant pairs - perfect agreement
        return McNemarResult(
            statistic=0.0,
            p_value=1.0,
            discordant_pairs=0,
            table=table,
            notes="No discordant pairs (perfect agreement)"
        )

    # For exact McNemar: use binomial distribution of b successes in n=b+c trials
    # Test if b = c (null hypothesis: proportions are equal)
    # Two-sided: 2 * min(P(X <= b), P(X >= b))
    # One-sided: P(X <= b) if b < c, else P(X >= b)

    if two_sided:
        # Two-sided exact test
        # p = 2 * min(P(X <= min(b,c)), P(X >= max(b,c)))
        n_trials = discordant
        p_success = 0.5  # Null hypothesis: b and c are equally likely

        # Calculate binomial probabilities
        # Use symmetry: P(X <= k) = P(X >= n-k) for p=0.5
        min_count = min(b, c)
        max_count = max(b, c)

        # P(X <= min_count) under H0
        cumulative_prob = binomial_cdf(min_count, n_trials, p_success)
        # P(X >= max_count) = 1 - P(X <= max_count - 1)
        upper_prob = 1 - binomial_cdf(max_count - 1, n_trials, p_success)

        p_two_sided = 2 * min(cumulative_prob, upper_prob)
        p_two_sided = min(1.0, p_two_sided)  # Cap at 1.0

        # Use lesser of discordant counts as test statistic
        statistic = float(min_count)

        return McNemarResult(
            statistic=statistic,
            p_value=p_two_sided,
            discordant_pairs=discordant,
            table=table,
            notes=f"Two-sided exact McNemar with {discordant} discordant pairs"
        )
    else:
        # One-sided test
        n_trials = discordant
        p_success = 0.5

        if b < c:
            # P(X <= b) - test if row1 positive rate < row2 positive rate
            p_one_sided = binomial_cdf(b, n_trials, p_success)
        else:
            # P(X >= b) - test if row1 positive rate > row2 positive rate
            p_one_sided = 1 - binomial_cdf(b - 1, n_trials, p_success)

        return McNemarResult(
            statistic=float(b),
            p_value=p_one_sided,
            discordant_pairs=discordant,
            table=table,
            notes=f"One-sided exact McNemar with {discordant} discordant pairs"
        )


def binomial_cdf(k: int, n: int, p: float) -> float:
    """
    Compute cumulative distribution function P(X <= k) for binomial(n, p).

    Uses logarithmic approach to avoid overflow for large n.
    """
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0

    # Sum P(X = i) for i = 0 to k
    # P(X = i) = C(n, i) * p^i * (1-p)^(n-i)
    # Use log-space computation for numerical stability

    cdf = 0.0
    for i in range(k + 1):
        # Log probability: log(C(n,i)) + i*log(p) + (n-i)*log(1-p)
        log_prob = (log_combination(n, i) +
                   i * math.log(p) +
                   (n - i) * math.log(1 - p))
        prob = math.exp(log_prob)
        cdf += prob

    return cdf


def log_combination(n: int, k: int) -> float:
    """Compute log(C(n, k)) = log(n! / (k! * (n-k)!))."""
    if k < 0 or k > n:
        return float('-inf')
    if k == 0 or k == n:
        return 0.0

    # Use symmetry to minimize computations
    k = min(k, n - k)

    # log(C(n, k)) = log(n!) - log(k!) - log((n-k)!)
    # = sum(log(i) for i in (n-k+1) to n) - sum(log(i) for i in 1 to k)
    log_numer = sum(math.log(i) for i in range(n - k + 1, n + 1))
    log_denom = sum(math.log(i) for i in range(1, k + 1))

    return log_numer - log_denom


def risk_difference_bootstrap(
    outcomes_arm1: List[bool],
    outcomes_arm2: List[bool],
    confidence: float = 0.95,
    bootstrap_samples: int = 10000,
    seed: int = 20260628
) -> RiskDifferenceResult:
    """
    Compute paired risk difference with bootstrap confidence interval.

    Args:
        outcomes_arm1: Binary outcomes for arm 1 (list of bool/int)
        outcomes_arm2: Binary outcomes for arm 2 (list of bool/int)
        confidence: Confidence level (default 0.95)
        bootstrap_samples: Number of bootstrap samples (default 10000)
        seed: Random seed for reproducibility (default 20260628)

    Returns:
        RiskDifferenceResult with RD and bootstrap CI
    """
    if len(outcomes_arm1) != len(outcomes_arm2):
        raise ValueError(f"Arms must have same length: arm1={len(outcomes_arm1)}, arm2={len(outcomes_arm2)}")

    n_pairs = len(outcomes_arm1)
    if n_pairs == 0:
        return RiskDifferenceResult(
            rd=0.0,
            ci_lower=0.0,
            ci_upper=0.0,
            n_pairs=0,
            bootstrap_samples=bootstrap_samples,
            notes="No paired observations"
        )

    # Convert to int (True=1, False=0)
    arm1_ints = [int(bool(x)) for x in outcomes_arm1]
    arm2_ints = [int(bool(x)) for x in outcomes_arm2]

    # Compute point estimate
    p1 = sum(arm1_ints) / n_pairs
    p2 = sum(arm2_ints) / n_pairs
    rd_point = p1 - p2

    # Bootstrap CI
    rng = random.Random(seed)
    bootstrap_rds = []

    for _ in range(bootstrap_samples):
        # Resample with replacement
        indices = [rng.randint(0, n_pairs - 1) for _ in range(n_pairs)]

        # Compute bootstrap RD
        arm1_boot = [arm1_ints[i] for i in indices]
        arm2_boot = [arm2_ints[i] for i in indices]

        p1_boot = sum(arm1_boot) / n_pairs
        p2_boot = sum(arm2_boot) / n_pairs
        rd_boot = p1_boot - p2_boot

        bootstrap_rds.append(rd_boot)

    # Compute CI percentiles
    alpha = 1 - confidence
    lower_percentile = (alpha / 2) * 100
    upper_percentile = (1 - alpha / 2) * 100

    bootstrap_rds.sort()
    ci_lower = bootstrap_rds[int(lower_percentile * bootstrap_samples / 100)]
    ci_upper = bootstrap_rds[int(upper_percentile * bootstrap_samples / 100)]

    return RiskDifferenceResult(
        rd=rd_point,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        n_pairs=n_pairs,
        bootstrap_samples=bootstrap_samples,
        notes=f"Bootstrap CI with {bootstrap_samples} samples, seed={seed}"
    )


def holm_correction(p_values: List[float], alpha: float = 0.05) -> HolmResult:
    """
    Holm-Bonferroni correction for multiple testing.

    Args:
        p_values: List of p-values to correct
        alpha: Family-wise error rate (default 0.05)

    Returns:
        HolmResult with corrected p-values and rejection decisions

    References:
        Holm, S. (1979). "A simple sequentially rejective multiple test procedure".
        Scandinavian Journal of Statistics.
    """
    n_tests = len(p_values)

    if n_tests == 0:
        return HolmResult(
            original_p=[],
            corrected_p=[],
            rejected=[],
            alpha=alpha,
            notes="No p-values provided"
        )

    # Create list of (original_p, original_index)
    p_with_indices = [(p, i) for i, p in enumerate(p_values)]

    # Sort by p-value (ascending)
    p_sorted = sorted(p_with_indices, key=lambda x: x[0])

    # Apply Holm correction
    corrected = []
    rejected_sorted = []

    for rank, (p_orig, orig_idx) in enumerate(p_sorted):
        # Holm correction: compare p to alpha / (n - rank)
        # where rank is 1-indexed
        corrected_alpha = alpha / (n_tests - rank)

        corrected_p = min(1.0, p_orig * (n_tests - rank))  # Adjusted p-value
        is_rejected = p_orig <= corrected_alpha

        corrected.append((corrected_p, orig_idx, is_rejected))

    # Sort back to original order
    corrected_sorted = sorted(corrected, key=lambda x: x[1])
    final_corrected_p = [cp for cp, _, _ in corrected_sorted]
    final_rejected = [r for _, _, r in corrected_sorted]

    return HolmResult(
        original_p=p_values,
        corrected_p=final_corrected_p,
        rejected=final_rejected,
        alpha=alpha,
        notes=f"Holm correction applied to {n_tests} tests at alpha={alpha}"
    )


def cohen_kappa(
    ratings1: List[Any],
    ratings2: List[Any],
    weights: Optional[List[List[float]]] = None,
    confidence: float = 0.95
) -> KappaResult:
    """
    Compute Cohen's kappa with explicit handling of undefined cases.

    Args:
        ratings1: Ratings from rater 1
        ratings2: Ratings from rater 2 (must be same length as ratings1)
        weights: Weight matrix for weighted kappa (None for unweighted)
        confidence: Confidence level for CI (default 0.95)

    Returns:
        KappaResult with kappa, CI, observed/expected agreement, and warnings

    References:
        Cohen, J. (1960). "A coefficient of agreement for nominal scales".
        Educational and Psychological Measurement.
    """
    if len(ratings1) != len(ratings2):
        raise ValueError(f"Rating lists must have same length: {len(ratings1)} vs {len(ratings2)}")

    n = len(ratings1)

    if n == 0:
        return KappaResult(
            kappa=0.0,
            ci_lower=0.0,
            ci_upper=0.0,
            observed_agreement=0.0,
            expected_agreement=0.0,
            n=0,
            warning="No paired ratings provided"
        )

    # Handle undefined/missing values
    # Create mask of valid (non-None) paired observations
    valid_mask = [(r1 is not None) and (r2 is not None) for r1, r2 in zip(ratings1, ratings2)]
    n_valid = sum(valid_mask)

    if n_valid < n:
        warning = f"{n - n_valid} pairs with undefined values excluded from analysis"

    if n_valid == 0:
        return KappaResult(
            kappa=float('nan'),
            ci_lower=0.0,
            ci_upper=0.0,
            observed_agreement=0.0,
            expected_agreement=0.0,
            n=0,
            warning="No valid paired ratings (all undefined)"
        )

    # Filter to valid pairs
    r1_valid = [r1 for r1, r2, valid in zip(ratings1, ratings2, valid_mask) if valid]
    r2_valid = [r2 for r1, r2, valid in zip(ratings1, ratings2, valid_mask) if valid]

    # Get unique categories
    categories = sorted(set(r1_valid + r2_valid))
    k = len(categories)

    if k < 2:
        return KappaResult(
            kappa=float('nan'),
            ci_lower=0.0,
            ci_upper=0.0,
            observed_agreement=1.0,
            expected_agreement=1.0,
            n=n_valid,
            warning=f"Only {k} category found - kappa undefined"
        )

    # Build confusion matrix
    confusion = {}
    for cat1 in categories:
        confusion[cat1] = {}
        for cat2 in categories:
            confusion[cat1][cat2] = 0

    for r1, r2 in zip(r1_valid, r2_valid):
        confusion[r1][r2] += 1

    # Calculate observed agreement
    observed_agreement = sum(confusion[cat][cat] for cat in categories) / n_valid

    # Calculate expected agreement (chance)
    expected_agreement = 0.0
    for cat in categories:
        # Row marginal (rater 1)
        row_total = sum(confusion[cat].values())
        # Column marginal (rater 2)
        col_total = sum(confusion[r1][cat] for r1 in categories)

        # Expected joint frequency under independence
        expected = (row_total * col_total) / n_valid
        expected_agreement += expected / n_valid

    # Calculate kappa
    if expected_agreement == 1.0:
        # Perfect chance agreement - kappa undefined
        return KappaResult(
            kappa=float('nan'),
            ci_lower=0.0,
            ci_upper=0.0,
            observed_agreement=observed_agreement,
            expected_agreement=expected_agreement,
            n=n_valid,
            warning="Perfect chance agreement (expected=1.0) - kappa undefined"
        )

    kappa = (observed_agreement - expected_agreement) / (1 - expected_agreement)

    # Compute standard error for CI
    # Using asymptotic variance formula
    se_kappa = math.sqrt(
        (observed_agreement * (1 - observed_agreement)) /
        (n_valid * (1 - expected_agreement)**2)
    )

    z = 1.96  # 95% CI
    ci_lower = kappa - z * se_kappa
    ci_upper = kappa + z * se_kappa

    # Clamp to [-1, 1]
    ci_lower = max(-1.0, ci_lower)
    ci_upper = min(1.0, ci_upper)

    return KappaResult(
        kappa=kappa,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        observed_agreement=observed_agreement,
        expected_agreement=expected_agreement,
        n=n_valid,
        warning=warning if n_valid < n else None
    )


def benchmark_paired_analysis(
    arm1_results: List[Dict[str, Any]],
    arm2_results: List[Dict[str, Any]],
    metrics: List[str] = ['database_routing_correct', 'feasibility_correct', 'hard_error_free']
) -> Dict[str, Any]:
    """
    Benchmark-level paired analysis comparing two experimental arms.

    Args:
        arm1_results: List of evaluation results from arm 1 (each dict with task_id + metric fields)
        arm2_results: List of evaluation results from arm 2 (same structure)
        metrics: List of metric names to analyze (must exist in result dicts)

    Returns:
        Dict with analysis results for each metric:
        - McNemar test for binary metrics
        - Risk difference with bootstrap CI
        - Wilson CIs for each arm
        - Holm-corrected p-values across metrics
    """
    # Ensure tasks are aligned by task_id
    arm1_by_id = {r['task_id']: r for r in arm1_results}
    arm2_by_id = {r['task_id']: r for r in arm2_results}

    common_tasks = set(arm1_by_id.keys()) & set(arm2_by_id.keys())

    if not common_tasks:
        return {
            'error': 'No common tasks between arms',
            'n_common': 0
        }

    analysis = {
        'n_common': len(common_tasks),
        'metrics': {}
    }

    # Collect p-values for Holm correction
    p_values = []

    # Analyze each metric
    for metric in metrics:
        # Extract binary outcomes
        outcomes1 = []
        outcomes2 = []

        for task_id in sorted(common_tasks):
            result1 = arm1_by_id[task_id]
            result2 = arm2_by_id[task_id]

            # Get metric value (assume bool/int 0/1)
            val1 = result1.get(metric, False)
            val2 = result2.get(metric, False)

            outcomes1.append(bool(val1))
            outcomes2.append(bool(val2))

        # Build 2x2 table for McNemar
        a = sum(1 for o1, o2 in zip(outcomes1, outcomes2) if o1 and o2)  # Both correct
        b = sum(1 for o1, o2 in zip(outcomes1, outcomes2) if o1 and not o2)  # Arm1 correct, Arm2 wrong
        c = sum(1 for o1, o2 in zip(outcomes1, outcomes2) if not o1 and o2)  # Arm1 wrong, Arm2 correct
        d = sum(1 for o1, o2 in zip(outcomes1, outcomes2) if not o1 and not o2)  # Both wrong

        table = {
            'row1': {'col1': a, 'col2': b},
            'row2': {'col1': c, 'col2': d}
        }

        # McNemar test
        mcnemar = exact_mcnemar_test(table, two_sided=True)
        p_values.append(mcnemar.p_value)

        # Wilson CI for each arm
        n1_correct = sum(outcomes1)
        n2_correct = sum(outcomes2)
        n_total = len(outcomes1)

        wilson1 = wilson_ci(n1_correct, n_total)
        wilson2 = wilson_ci(n2_correct, n_total)

        # Risk difference with bootstrap CI
        rd_result = risk_difference_bootstrap(outcomes1, outcomes2, seed=20260628)

        analysis['metrics'][metric] = {
            'mcnemar': {
                'p_value': mcnemar.p_value,
                'discordant_pairs': mcnemar.discordant_pairs,
                'table': table,
                'notes': mcnemar.notes
            },
            'arm1': {
                'proportion': wilson1.proportion,
                'ci_lower': wilson1.ci_lower,
                'ci_upper': wilson1.ci_upper,
                'n_correct': n1_correct,
                'n_total': n_total
            },
            'arm2': {
                'proportion': wilson2.proportion,
                'ci_lower': wilson2.ci_lower,
                'ci_upper': wilson2.ci_upper,
                'n_correct': n2_correct,
                'n_total': n_total
            },
            'risk_difference': {
                'rd': rd_result.rd,
                'ci_lower': rd_result.ci_lower,
                'ci_upper': rd_result.ci_upper,
                'notes': rd_result.notes
            }
        }

    # Apply Holm correction
    holm = holm_correction(p_values, alpha=0.05)

    # Add corrected p-values to results
    for i, metric in enumerate(metrics):
        if metric in analysis['metrics']:
            analysis['metrics'][metric]['mcnemar']['p_value_holm'] = holm.corrected_p[i]
            analysis['metrics'][metric]['mcnemar']['rejected_holm'] = holm.rejected[i]

    analysis['holm_correction'] = {
        'alpha': holm.alpha,
        'n_tests': len(p_values),
        'notes': holm.notes
    }

    return analysis


# Format p-values for display (avoid p = 0.0)
def format_p_value(p: float) -> str:
    """Format p-value, avoiding exact zero."""
    if p < 1e-10:
        return "p < 1e-10"
    elif p < 0.001:
        return f"p = {p:.4e}"
    else:
        return f"p = {p:.4f}"