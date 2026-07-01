#!/usr/bin/env python
"""
NeuroSurgEpiAgent Benchmark Integrity Verifier

This script verifies the integrity of the frozen benchmark file against its sidecar SHA-256 hash.
It validates:
- Exact byte-for-byte match (SHA-256)
- Task count = 30
- Unique task IDs
- Declared task_count matches actual
- Review status consistency
- Schema-relevant fields

Usage:
    python benchmarks/verify_benchmark_integrity.py [--verbose] [--benchmark-path PATH]

Exit codes:
    0: Verification passed
    1: Hash mismatch
    2: Task count mismatch
    3: Duplicate task IDs
    4: Schema validation failed
    5: Sidecar file missing or invalid
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Dict, List, Any


def compute_sha256(file_path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            sha256.update(chunk)
    return sha256.hexdigest()


def load_sidecar(sidecar_path: Path) -> Dict[str, Any]:
    """Load the sidecar hash file."""
    try:
        with open(sidecar_path, 'r') as f:
            data = json.load(f)
        return data
    except FileNotFoundError:
        print(f"ERROR: Sidecar file not found: {sidecar_path}")
        sys.exit(5)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in sidecar file: {e}")
        sys.exit(5)


def verify_hash(file_path: Path, expected_hash: str, verbose: bool = False) -> bool:
    """Verify SHA-256 hash matches expected."""
    actual_hash = compute_sha256(file_path)
    if verbose:
        print(f"Expected hash: {expected_hash}")
        print(f"Actual hash:   {actual_hash}")

    if actual_hash != expected_hash:
        print(f"FAILED: Hash mismatch!")
        print(f"  Expected: {expected_hash}")
        print(f"  Actual:   {actual_hash}")
        return False
    if verbose:
        print("PASSED: SHA-256 hash matches")
    return True


def load_yaml(file_path: Path) -> Dict[str, Any]:
    """Load YAML file."""
    try:
        import yaml
        with open(file_path, 'r') as f:
            return yaml.safe_load(f)
    except ImportError:
        print("ERROR: PyYAML not installed. Install with: pip install pyyaml")
        sys.exit(10)
    except FileNotFoundError:
        print(f"ERROR: Benchmark file not found: {file_path}")
        sys.exit(5)


def verify_task_count(benchmark_data: Dict[str, Any], expected_count: int = 30, verbose: bool = False) -> bool:
    """Verify task count matches expected."""
    actual_count = benchmark_data.get('task_count')
    tasks = benchmark_data.get('tasks', [])
    actual_tasks_count = len(tasks)

    if verbose:
        print(f"Declared task_count: {actual_count}")
        print(f"Actual tasks in list: {actual_tasks_count}")

    if actual_count != expected_count:
        print(f"FAILED: Declared task_count mismatch!")
        print(f"  Expected: {expected_count}")
        print(f"  Actual: {actual_count}")
        return False

    if actual_tasks_count != expected_count:
        print(f"FAILED: Actual task list size mismatch!")
        print(f"  Expected: {expected_count}")
        print(f"  Actual: {actual_tasks_count}")
        return False

    if verbose:
        print(f"PASSED: Task count = {expected_count}")
    return True


def verify_unique_ids(benchmark_data: Dict[str, Any], verbose: bool = False) -> bool:
    """Verify all task IDs are unique."""
    tasks = benchmark_data.get('tasks', [])
    task_ids = [t.get('id') for t in tasks if t.get('id')]

    if verbose:
        print(f"Total tasks: {len(tasks)}")
        print(f"Tasks with IDs: {len(task_ids)}")

    unique_ids = set(task_ids)
    if len(task_ids) != len(unique_ids):
        duplicates = [id for id in unique_ids if task_ids.count(id) > 1]
        print(f"FAILED: Duplicate task IDs found: {duplicates}")
        return False

    if verbose:
        print(f"PASSED: All {len(unique_ids)} task IDs are unique")
    return True


def verify_review_status(benchmark_data: Dict[str, Any], verbose: bool = False) -> bool:
    """Verify review status consistency."""
    tasks = benchmark_data.get('tasks', [])
    expected_status = "needs_expert_review"

    tasks_with_status = [t for t in tasks if t.get('review_status')]

    if verbose:
        print(f"Tasks with review_status: {len(tasks_with_status)}/{len(tasks)}")

    mismatches = []
    for task in tasks:
        review_status = task.get('review_status')
        if review_status and review_status != expected_status:
            mismatches.append((task.get('id'), review_status))

    if mismatches:
        print(f"FAILED: Review status mismatches found:")
        for task_id, status in mismatches:
            print(f"  {task_id}: {status} (expected: {expected_status})")
        return False

    if verbose:
        print(f"PASSED: All tasks have consistent review_status={expected_status}")
    return True


def verify_schema_fields(benchmark_data: Dict[str, Any], verbose: bool = False) -> bool:
    """Verify required schema fields are present."""
    required_metadata = [
        'schema_version',
        'benchmark_name',
        'benchmark_version',
        'frozen_timestamp',
        'status',
        'disclaimer',
        'task_count',
        'domains',
        'gold_standard_requirements',
        'tasks'
    ]

    missing = []
    for field in required_metadata:
        if field not in benchmark_data:
            missing.append(field)

    if missing:
        print(f"FAILED: Missing required metadata fields: {missing}")
        return False

    # Verify required task fields
    tasks = benchmark_data.get('tasks', [])
    required_task_fields = [
        'id',
        'domain',
        'question',
        'expected_database',
        'expected_feasible',
        'rationale'
    ]

    task_field_issues = []
    for i, task in enumerate(tasks):
        missing_fields = [f for f in required_task_fields if f not in task]
        if missing_fields:
            task_field_issues.append(f"Task {i} ({task.get('id', 'UNKNOWN')}): missing {missing_fields}")

    if task_field_issues:
        print(f"FAILED: Task schema validation failed:")
        for issue in task_field_issues:
            print(f"  {issue}")
        return False

    if verbose:
        print("PASSED: All required schema fields present")
    return True


def verify_version_dates(benchmark_data: Dict[str, Any], verbose: bool = False) -> bool:
    """Verify version dates are correct (2026-06-29, not 2025)."""
    frozen_timestamp = benchmark_data.get('frozen_timestamp', '')
    benchmark_version = benchmark_data.get('benchmark_version', '')

    if verbose:
        print(f"Frozen timestamp: {frozen_timestamp}")
        print(f"Benchmark version: {benchmark_version}")

    # Check for erroneous 2025 dates
    if '2025' in frozen_timestamp:
        print(f"FAILED: Erroneous 2025 date in frozen_timestamp")
        print(f"  Found: {frozen_timestamp}")
        print(f"  Expected: 2026-06-29")
        return False

    # Verify it's 2026-06-29
    if '2026-06-29' not in frozen_timestamp:
        print(f"WARNING: frozen_timestamp does not contain 2026-06-29: {frozen_timestamp}")
        # This is a warning, not a failure

    if verbose:
        print("PASSED: Version dates are correct (2026-06-29)")
    return True


def main():
    parser = argparse.ArgumentParser(description='Verify NeuroSurgEpiAgent benchmark integrity')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    parser.add_argument('--benchmark-path', type=Path, default=Path('benchmarks/tasks.v0.1.0.yaml'),
                        help='Path to frozen benchmark file')
    parser.add_argument('--sidecar-path', type=Path, default=None,
                        help='Path to sidecar hash file (default: benchmark_path + .sha256)')

    args = parser.parse_args()

    # Determine sidecar path
    if args.sidecar_path is None:
        args.sidecar_path = args.benchmark_path.with_suffix('.sha256')

    if args.verbose:
        print("=" * 70)
        print("NEUROSURGEPIAGENT BENCHMARK INTEGRITY VERIFICATION")
        print("=" * 70)
        print(f"Benchmark file: {args.benchmark_path}")
        print(f"Sidecar file:   {args.sidecar_path}")
        print()

    # Load sidecar
    sidecar_data = load_sidecar(args.sidecar_path)
    expected_hash = sidecar_data.get('sha256')
    if not expected_hash:
        print(f"ERROR: Sidecar file missing 'sha256' field")
        sys.exit(5)

    if args.verbose:
        print(f"Expected SHA-256: {expected_hash}")
        print()

    # Verify hash
    if not verify_hash(args.benchmark_path, expected_hash, args.verbose):
        sys.exit(1)
    print()

    # Load benchmark
    benchmark_data = load_yaml(args.benchmark_path)

    # Verify task count
    if not verify_task_count(benchmark_data, verbose=args.verbose):
        sys.exit(2)
    print()

    # Verify unique IDs
    if not verify_unique_ids(benchmark_data, verbose=args.verbose):
        sys.exit(3)
    print()

    # Verify review status
    if not verify_review_status(benchmark_data, verbose=args.verbose):
        sys.exit(4)
    print()

    # Verify schema fields
    if not verify_schema_fields(benchmark_data, verbose=args.verbose):
        sys.exit(4)
    print()

    # Verify version dates
    if not verify_version_dates(benchmark_data, verbose=args.verbose):
        sys.exit(4)
    print()

    # All checks passed
    print("=" * 70)
    print("VERIFICATION PASSED")
    print("=" * 70)
    print(f"Benchmark file: {args.benchmark_path}")
    print(f"SHA-256: {expected_hash}")
    print(f"Task count: {benchmark_data.get('task_count')}")
    print(f"Version: {benchmark_data.get('benchmark_version')}")
    print(f"Status: {benchmark_data.get('status')}")

    return 0


if __name__ == "__main__":
    sys.exit(main())