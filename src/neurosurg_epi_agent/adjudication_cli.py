#!/usr/bin/env python
"""
NeuroSurgEpiAgent Adjudication CLI

Command-line interface for managing expert adjudication workflow.
Provides tools for:
- Creating expert rating templates
- Importing and validating expert ratings
- Computing inter-rater reliability
- Managing consensus process
- Generating adjudication reports

Usage:
    python -m neurosurg_epi_agent.adjudication_cli <command> [options]
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Any

from neurosurg_epi_agent.adjudication import (
    AdjudicationManager,
    RaterInfo,
    create_adjudication_manager
)


def command_create_templates(args) -> Dict[str, Any]:
    """Create expert rating templates."""
    manager = create_adjudication_manager(args.benchmark, args.output_dir)

    # Create rater info from command line args
    rater_info = []
    for i, name in enumerate(args.rater_names):
        rater_id = f"rater_{i+1:02d}"
        credentials = args.credentials[i] if i < len(args.credentials) else "Expert"
        affiliation = args.affiliations[i] if i < len(args.affiliations) else "Institution"

        rater = RaterInfo(
            rater_id=rater_id,
            name=name,
            credentials=credentials,
            affiliation=affiliation
        )
        rater_info.append(rater)

    # Create templates
    template_paths = manager.create_rating_templates(rater_info)

    output = {
        'command': 'create_templates',
        'status': manager.status.value,
        'raters': len(rater_info),
        'template_paths': {rater_id: str(path) for rater_id, path in template_paths.items()},
        'instructions': [
            'Distribute template files to expert raters',
            'Raters should fill in their ratings and return files',
            f'Use import command when ratings are complete: python -m neurosurg_epi_agent.adjudication_cli import --rater-id <ID> --file <PATH>'
        ]
    }

    return output


def command_import_ratings(args) -> Dict[str, Any]:
    """Import expert ratings from CSV file."""
    manager = create_adjudication_manager(args.benchmark, args.output_dir)

    count = manager.import_ratings(args.rater_id, Path(args.file))

    # Run validation
    validation = manager.validate_ratings()

    output = {
        'command': 'import_ratings',
        'rater_id': args.rater_id,
        'file': args.file,
        'ratings_imported': count,
        'validation': validation,
        'status': manager.status.value
    }

    return output


def command_validate(args) -> Dict[str, Any]:
    """Validate imported expert ratings."""
    manager = create_adjudication_manager(args.benchmark, args.output_dir)

    validation = manager.validate_ratings()

    output = {
        'command': 'validate',
        'validation': validation,
        'status': manager.status.value
    }

    return output


def command_reliability(args) -> Dict[str, Any]:
    """Compute inter-rater reliability statistics."""
    manager = create_adjudication_manager(args.benchmark, args.output_dir)

    reliability = manager.compute_inter_rater_reliability()

    output = {
        'command': 'inter_rater_reliability',
        'reliability': reliability,
        'status': manager.status.value
    }

    return output


def command_consensus(args) -> Dict[str, Any]:
    """Create consensus template or import consensus ratings."""
    manager = create_adjudication_manager(args.benchmark, args.output_dir)

    if args.create:
        # Create consensus template
        template_path = manager.create_consensus_template()

        output = {
            'command': 'create_consensus_template',
            'template_path': str(template_path),
            'instructions': [
                'Hold consensus meeting with expert raters',
                'Fill in consensus ratings in template file',
                f'Import consensus with: python -m neurosurg_epi_agent.adjudication_cli consensus --import --file {template_path}'
            ],
            'status': manager.status.value
        }

    elif args.import_consensus:
        # Import consensus ratings
        count = manager.import_consensus_ratings(Path(args.file))

        output = {
            'command': 'import_consensus',
            'file': args.file,
            'consensus_imported': count,
            'status': manager.status.value
        }

    else:
        output = {
            'error': 'Must specify --create or --import with consensus command'
        }

    return output


def command_report(args) -> Dict[str, Any]:
    """Generate comprehensive adjudication report."""
    manager = create_adjudication_manager(args.benchmark, args.output_dir)

    report = manager.generate_adjudication_report()

    output = {
        'command': 'generate_report',
        'report': report
    }

    return output


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description='NeuroSurgEpiAgent Expert Adjudication CLI',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create rating templates for 2 experts
  python -m neurosurg_epi_agent.adjudication_cli create-templates \\
    --benchmark benchmarks/tasks.v0.1.0.yaml \\
    --rater-names "Dr. Smith" "Dr. Jones" \\
    --credentials "MD, Neurologist" "PhD, Epidemiologist"

  # Import ratings from first expert
  python -m neurosurg_epi_agent.adjudication_cli import \\
    --benchmark benchmarks/tasks.v0.1.0.yaml \\
    --rater-id rater_01 \\
    --file expert_ratings/rating_template_rater_01.csv

  # Validate all imported ratings
  python -m neurosurg_epi_agent.adjudication_cli validate \\
    --benchmark benchmarks/tasks.v0.1.0.yaml

  # Compute inter-rater reliability
  python -m neurosurg_epi_agent.adjudication_cli reliability \\
    --benchmark benchmarks/tasks.v0.1.0.yaml

  # Create consensus template
  python -m neurosurg_epi_agent.adjudication_cli consensus --create \\
    --benchmark benchmarks/tasks.v0.1.0.yaml

  # Generate full adjudication report
  python -m neurosurg_epi_agent.adjudication_cli report \\
    --benchmark benchmarks/tasks.v0.1.0.yaml
        """
    )

    parser.add_argument('--benchmark', type=str, default='benchmarks/tasks.v0.1.0.yaml',
                       help='Path to benchmark YAML file')
    parser.add_argument('--output-dir', type=str, default='expert_adjudication',
                       help='Output directory for adjudication files')

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Create templates command
    create_parser = subparsers.add_parser('create-templates', help='Create expert rating templates')
    create_parser.add_argument('--rater-names', nargs='+', required=True, help='Expert rater names')
    create_parser.add_argument('--credentials', nargs='+', help='Professional credentials (e.g., "MD, Neurologist")')
    create_parser.add_argument('--affiliations', nargs='+', help='Institutional affiliations')
    create_parser.add_argument('--output', '-o', type=str, help='Output JSON file path')

    # Import ratings command
    import_parser = subparsers.add_parser('import', help='Import expert ratings from CSV')
    import_parser.add_argument('--rater-id', type=str, required=True, help='Rater identifier (e.g., rater_01)')
    import_parser.add_argument('--file', type=str, required=True, help='Path to rating CSV file')
    import_parser.add_argument('--output', '-o', type=str, help='Output JSON file path')

    # Validate command
    validate_parser = subparsers.add_parser('validate', help='Validate imported ratings')
    validate_parser.add_argument('--output', '-o', type=str, help='Output JSON file path')

    # Reliability command
    reliability_parser = subparsers.add_parser('reliability', help='Compute inter-rater reliability')
    reliability_parser.add_argument('--output', '-o', type=str, help='Output JSON file path')

    # Consensus command
    consensus_parser = subparsers.add_parser('consensus', help='Manage consensus process')
    consensus_parser.add_argument('--create', action='store_true', help='Create consensus template')
    consensus_parser.add_argument('--import', action='store_true', dest='import_consensus',
                                 help='Import consensus ratings')
    consensus_parser.add_argument('--file', type=str, help='Path to consensus CSV file')
    consensus_parser.add_argument('--output', '-o', type=str, help='Output JSON file path')

    # Report command
    report_parser = subparsers.add_parser('report', help='Generate adjudication report')
    report_parser.add_argument('--output', '-o', type=str, help='Output JSON file path')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Set benchmark and output dir from args
    args.benchmark = args.benchmark
    args.output_dir = args.output_dir

    # Route to appropriate command handler
    command_handlers = {
        'create-templates': command_create_templates,
        'import': command_import_ratings,
        'validate': command_validate,
        'reliability': command_reliability,
        'consensus': command_consensus,
        'report': command_report
    }

    handler = command_handlers.get(args.command)
    if not handler:
        parser.error(f"Unknown command: {args.command}")

    try:
        result = handler(args)

        # Output result
        if hasattr(args, 'output') and args.output:
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