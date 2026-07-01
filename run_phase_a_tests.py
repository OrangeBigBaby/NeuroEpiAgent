#!/usr/bin/env python
"""
Run all PHASE A tests to verify implementation.

This script runs all tests for the newly implemented components:
- Benchmark integrity tests
- Statistics module tests
- Ablation framework tests
- Adjudication system tests

Usage:
    python run_phase_a_tests.py
"""

import subprocess
import sys
from pathlib import Path

def run_tests(test_file, description):
    """Run tests for a specific module."""
    print(f"\n{'='*70}")
    print(f"Running: {description}")
    print(f"{'='*70}")

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", test_file, "-v", "--tb=short"],
            capture_output=True,
            text=True,
            timeout=120
        )

        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)

        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print(f"Tests timed out for {description}")
        return False
    except Exception as e:
        print(f"Error running tests for {description}: {e}")
        return False

def main():
    """Run all PHASE A tests."""
    print("="*70)
    print("NEUROSURGEPIAGENT PHASE A TEST SUITE")
    print("="*70)
    print("\nThis will run all tests for PHASE A implementation:")
    print("  - Benchmark integrity (15 tests)")
    print("  - Statistics module (31 tests)")
    print("  - Ablation framework (25 tests)")
    print("  - Adjudication system (20 tests)")
    print("\nTotal: 91 comprehensive tests")

    # Test files
    test_files = [
        ("tests/test_benchmark_integrity.py", "Benchmark Integrity Tests"),
        ("tests/test_statistics.py", "Statistics Module Tests"),
        ("tests/test_ablation.py", "Ablation Framework Tests"),
        ("tests/test_adjudication.py", "Adjudication System Tests"),
    ]

    results = {}
    for test_file, description in test_files:
        if Path(test_file).exists():
            results[description] = run_tests(test_file, description)
        else:
            print(f"\n❌ Test file not found: {test_file}")
            results[description] = False

    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)

    for description, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{status}: {description}")

    total_passed = sum(1 for p in results.values() if p)
    total_tests = len(results)

    print(f"\nTotal: {total_passed}/{total_tests} test suites passed")

    if total_passed == total_tests:
        print("\n🎉 ALL TESTS PASSED - PHASE A IMPLEMENTATION VERIFIED")
        return 0
    else:
        print("\n⚠️  SOME TESTS FAILED - REVIEW OUTPUT ABOVE")
        return 1

if __name__ == "__main__":
    sys.exit(main())