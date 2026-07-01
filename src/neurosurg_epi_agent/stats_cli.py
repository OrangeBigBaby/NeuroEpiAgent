#!/usr/bin/env python
"""
NeuroSurgEpiAgent Statistics CLI

Command-line interface for statistical analysis of benchmark evaluations.
Provides tools for:
- Computing confidence intervals
- Running McNemar tests
- Performing risk difference analysis
- Applying Holm correction
- Computing Cohen's kappa
- Running benchmark paired analysis

Usage:
    python -m neurosurg_epi_agent.stats_cli <command> [options]
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Any

from neurosurg_epi_agent.statistics import (
    wilson_ci,
    exact_mcnemar_test,
    risk_difference_bootstrap,
    holm_correction,
    cohen_kappa,
    benchmark_paired_analysis,
    format_p_value
)


def command_wilson_ci(args) -> Dict[str, Any]:
    """Compute Wilson confidence interval."""
    result = wilson_ci(args.successes, args.n, args.confidence)

    output = {
        'method': 'wilson_ci',
        'parameters': {
            'successes': args.successes,
            'n': args.n,
            'confidence': args.confidence
        },
        'results': {
            'proportion': result.proportion,
            'ci_lower': result.ci_lower,
            'ci_upper': result.ci_upper,
            'n': result.n
        }
    }

    return output


def command_mcnemar(args) -> Dict[str, Any]:
    """Run McNemar test."""
    # Build 2x2 table
    table = {
        'row1': {'col1': args.a, 'col2': args.b},
        'row2': {'col1': args.c, 'col2': args.d}
    }

    result = exact_mcnemar_test(table, two_sided=args.two_sided)

    output = {
        'method': 'mcnemar_exact',
        'parameters': {
            'table': table,
            'two_sided': args.two_sided
        },
        'results': {
            'p_value': result.p_value,
            'p_value_formatted': format_p_value(result.p_value),
            'discordant_pairs': result.discordant_pairs,
            'statistic': result.statistic,
            'notes': result.notes
        }
    }

    return output


def command_risk_difference(args) -> Dict[str, Any]:
    """Compute risk difference with bootstrap CI."""
    # Load outcome files if provided
    if args.arm1_file and args.arm2_file:
        with open(args.arm1_file) as f:
            arm1_data = json.load(f)
        with open(args.arm2_file) as f:
            arm2_data = json.load(f)

        # Extract outcomes (assume list of bool/int or dict with 'outcome' key)
        outcomes1 = []
        for item in arm1_data:
            if isinstance(item, dict):
                outcomes1.append(item.get(args.outcome_field, False))
            else:
                outcomes1.append(item)

        outcomes2 = []
        for item in arm2_data:
            if isinstance(item, dict):
                outcomes2.append(item.get(args.outcome_field, False))
            else:
                outcomes2.append(item)
    else:
        # Use command-line arguments (comma-separated binary list)
        outcomes1 = [int(x.strip()) for x in args.arm1_outcomes.split(',')]
        outcomes2 = [int(x.strip()) for x in args.arm2_outcomes.split(',')]

    result = risk_difference_bootstrap(
        outcomes1,
        outcomes2,
        confidence=args.confidence,
        bootstrap_samples=args.bootstrap_samples,
        seed=args.seed
    )

    output = {
        'method': 'risk_difference_bootstrap',
        'parameters': {
            'n_pairs': len(outcomes1),
            'confidence': args.confidence,
            'bootstrap_samples': args.bootstrap_samples,
            'seed': args.seed
        },
        'results': {
            'risk_difference': result.rd,
            'ci_lower': result.ci_lower,
            'ci_upper': result.ci_upper,
            'notes': result.notes
        }
    }

    return output


def command_holm(args) -> Dict[str, Any]:
    """Apply Holm-Bonferroni correction."""
    # Load p-values from file or command line
    if args.p_file:
        with open(args.p_file) as f:
            data = json.load(f)
            p_values = data.get('p_values', [])
    else:
        p_values = [float(x.strip()) for x in args.p_values.split(',')]

    result = holm_correction(p_values, alpha=args.alpha)

    output = {
        'method': 'holm_bonferroni',
        'parameters': {
            'n_tests': len(p_values),
            'alpha': args.alpha
        },
        'results': {
            'original_p': result.original_p,
            'corrected_p': result.corrected_p,
            'rejected': result.rejected,
            'notes': result.notes
        }
    }

    return output


def command_kappa(args) -> Dict[str, Any]:
    """Compute Cohen's kappa."""
    # Load ratings from file
    if args.ratings1_file and args.ratings2_file:
        with open(args.ratings1_file) as f:
            data1 = json.load(f)
        with open(args.ratings2_file) as f:
            data2 = json.load(f)

        # Extract ratings
        ratings1 = data1.get('ratings', data1)
        ratings2 = data2.get('ratings', data2)
    else:
        # Parse command-line ratings (comma-separated)
        ratings1 = args.ratings1.split(',')
        ratings2 = args.ratings2.split(',')

    result = cohen_kappa(ratings1, ratings2, confidence=args.confidence)

    output = {
        'method': 'cohen_kappa',
        'parameters': {
            'n_total': len(ratings1),
            'confidence': args.confidence
        },
        'results': {
            'kappa': result.kappa,
            'ci_lower': result.ci_lower,
            'ci_upper': result.ci_upper,
            'observed_agreement': result.observed_agreement,
            'expected_agreement': result.expected_agreement,
            'n_valid': result.n,
            'warning': result.warning
        }
    }

    return output


def command_paired_analysis(args) -> Dict[str, Any]:
    """Run benchmark paired analysis between two arms."""
    # Load evaluation results
    with open(args.arm1_results) as f:
        arm1_results = json.load(f)
    with open(args.arm2_results) as f:
        arm2_results = json.load(f)

    # Get metrics to analyze
    if args.metrics_file:
        with open(args.metrics_file) as f:
            metrics_data = json.load(f)
            metrics = metrics_data.get('metrics', [])
    else:
        metrics = args.metrics.split(',')

    result = benchmark_paired_analysis(arm1_results, arm2_results, metrics=metrics)

    output = {
        'method': 'benchmark_paired_analysis',
        'parameters': {
            'n_common': result.get('n_common', 0),
            'metrics': metrics
        },
        'results': result
    }

    return output


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description='NeuroSurgEpiAgent Statistics CLI',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Wilson CI
  python -m neurosurg_epi_agent.stats_cli wilson-ci --successes 25 --n 100

  # McNemar test
  python -m neurosurg_epi_agent.stats_cli mcnemar --a 45 --b 5 --c 10 --d 40

  # Risk difference
  python -m neurosurg_epi_agent.stats_cli risk-diff --arm1-file arm1.json --arm2-file arm2.json

  # Holm correction
  python -m neurosurg_epi_agent.stats_cli holm --p-values 0.01,0.05,0.10,0.20

  # Cohen's kappa
  python -m neurosurg_epi_agent.stats_cli kappa --ratings1-file rater1.json --ratings2-file rater2.json

  # Paired analysis
  python -m neurosurg_epi_agent.stats_cli paired --arm1-results eval1.json --arm2-results eval2.json
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Wilson CI command
    wilson_parser = subparsers.add_parser('wilson-ci', help='Compute Wilson confidence interval')
    wilson_parser.add_argument('--successes', type=int, required=True, help='Number of successes')
    wilson_parser.add_argument('--n', type=int, required=True, help='Total sample size')
    wilson_parser.add_argument('--confidence', type=float, default=0.95, help='Confidence level (default: 0.95)')
    wilson_parser.add_argument('--output', '-o', type=str, help='Output JSON file path')

    # McNemar command
    mcnemar_parser = subparsers.add_parser('mcnemar', help='Run McNemar exact test')
    mcnemar_parser.add_argument('--a', type=int, required=True, help='Cell a (both positive)')
    mcnemar_parser.add_argument('--b', type=int, required=True, help='Cell b (row1+, row2-)')
    mcnemar_parser.add_argument('--c', type=int, required=True, help='Cell c (row1-, row2+)')
    mcnemar_parser.add_argument('--d', type=int, required=True, help='Cell d (both negative)')
    mcnemar_parser.add_argument('--one-sided', action='store_true', help='Use one-sided test')
    mcnemar_parser.add_argument('--output', '-o', type=str, help='Output JSON file path')

    # Risk difference command
    rd_parser = subparsers.add_parser('risk-diff', help='Compute risk difference with bootstrap CI')
    rd_parser.add_argument('--arm1-file', type=str, help='JSON file with arm1 outcomes')
    rd_parser.add_argument('--arm2-file', type=str, help='JSON file with arm2 outcomes')
    rd_parser.add_argument('--arm1-outcomes', type=str, help='Comma-separated binary outcomes for arm1')
    rd_parser.add_argument('--arm2-outcomes', type=str, help='Comma-separated binary outcomes for arm2')
    rd_parser.add_argument('--outcome-field', type=str, default='outcome', help='Field name for outcome in JSON')
    rd_parser.add_argument('--confidence', type=float, default=0.95, help='Confidence level (default: 0.95)')
    rd_parser.add_argument('--bootstrap-samples', type=int, default=10000, help='Bootstrap samples (default: 10000)')
    rd_parser.add_argument('--seed', type=int, default=20260628, help='Random seed (default: 20260628)')
    rd_parser.add_argument('--output', '-o', type=str, help='Output JSON file path')

    # Holm correction command
    holm_parser = subparsers.add_parser('holm', help='Apply Holm-Bonferroni correction')
    holm_parser.add_argument('--p-values', type=str, help='Comma-separated p-values')
    holm_parser.add_argument('--p-file', type=str, help='JSON file with p_values array')
    holm_parser.add_argument('--alpha', type=float, default=0.05, help='Family-wise error rate (default: 0.05)')
    holm_parser.add_argument('--output', '-o', type=str, help='Output JSON file path')

    # Kappa command
    kappa_parser = subparsers.add_parser('kappa', help='Compute Cohen\'s kappa')
    kappa_parser.add_argument('--ratings1', type=str, help='Comma-separated ratings from rater 1')
    kappa_parser.add_argument('--ratings2', type=str, help='Comma-separated ratings from rater 2')
    kappa_parser.add_argument('--ratings1-file', type=str, help='JSON file with ratings1')
    kappa_parser.add_argument('--ratings2-file', type=str, help='JSON file with ratings2')
    kappa_parser.add_argument('--confidence', type=float, default=0.95, help='Confidence level (default: 0.95)')
    kappa_parser.add_argument('--output', '-o', type=str, help='Output JSON file path')

    # Paired analysis command
    paired_parser = subparsers.add_parser('paired', help='Run benchmark paired analysis')
    paired_parser.add_argument('--arm1-results', type=str, required=True, help='JSON file with arm1 evaluation results')
    paired_parser.add_argument('--arm2-results', type=str, required=True, help='JSON file with arm2 evaluation results')
    paired_parser.add_argument('--metrics', type=str, default='database_routing_correct,feasibility_correct,hard_error_free', help='Comma-separated metrics to analyze')
    paired_parser.add_argument('--metrics-file', type=str, help='JSON file with metrics array')
    paired_parser.add_argument('--output', '-o', type=str, help='Output JSON file path')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Route to appropriate command handler
    command_handlers = {
        'wilson-ci': command_wilson_ci,
        'mcnemar': command_mcnemar,
        'risk-diff': command_risk_difference,
        'holm': command_holm,
        'kappa': command_kappa,
        'paired': command_paired_analysis
    }

    handler = command_handlers.get(args.command)
    if not handler:
        parser.error(f"Unknown command: {args.command}")

    # Fix McNemar two-sided argument
    if args.command == 'mcnemar':
        args.two_sided = not args.one_sided

    try:
        result = handler(args)

        # Output result
        if args.output:
            with open(args.output, 'w') as f:
                json.dump(result, f, indent=2)
            print(f"Results written to: {args.output}")
        else:
            print(json.dumps(result, indent=2))

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()