#!/usr/bin/env python
"""
Test verification script for PHASE A repairs.
Run this script to verify all 215 tests pass after repairs.
"""

import subprocess
import sys

def main():
    print("PHASE A Test Verification")
    print("=" * 70)
    print("Running pytest to verify all tests pass...")
    print()

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q"],
            cwd="C:\\Users\\KlisSu123\\Desktop\\Nhance\\NeuroSurgEpiAgent",
            capture_output=True,
            text=True,
            timeout=120  # 2 minute timeout
        )

        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)

        print()
        print("=" * 70)
        if result.returncode == 0:
            print("✅ ALL TESTS PASSED")
            return 0
        else:
            print(f"❌ TESTS FAILED (exit code: {result.returncode})")
            return 1

    except subprocess.TimeoutExpired:
        print("❌ TEST TIMEOUT (> 2 minutes)")
        return 1
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())