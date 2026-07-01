#!/usr/bin/env python
"""
Generate SHA-256 sidecar file for the frozen benchmark.

This script computes the SHA-256 hash of the frozen benchmark file and
creates a sidecar .sha256 file with the hash and metadata.
"""

import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone


def compute_sha256(file_path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            sha256.update(chunk)
    return sha256.hexdigest()


def main():
    # Paths
    benchmark_path = Path("benchmarks/tasks.v0.1.0.yaml")
    sidecar_path = Path("benchmarks/tasks.v0.1.0.sha256")

    # Compute hash
    print(f"Computing SHA-256 hash of {benchmark_path}...")
    sha256_hash = compute_sha256(benchmark_path)
    print(f"SHA-256: {sha256_hash}")

    # Create sidecar data
    sidecar_data = {
        "format": "NeuroSurgEpiAgent-Benchmark-Integrity-v1",
        "benchmark_file": "tasks.v0.1.0.yaml",
        "benchmark_version": "0.1.0",
        "sha256": sha256_hash,
        "generated_timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        "expected_task_count": 30,
        "verification_status": "DRAFT - AUTHORED GOLD ASSERTIONS PENDING INDEPENDENT EXPERT ADJUDICATION",
        "verification_instructions": (
            "Use benchmarks/verify_benchmark_integrity.py to verify integrity. "
            "Exit code 0 indicates all checks passed."
        ),
        "verified_checks": [
            "sha256_hash_match",
            "task_count_equals_30",
            "unique_task_ids",
            "declared_task_count_matches_actual",
            "review_status_consistency",
            "schema_field_presence",
            "version_date_correctness"
        ]
    }

    # Write sidecar file
    with open(sidecar_path, 'w') as f:
        json.dump(sidecar_data, f, indent=2)

    print(f"Sidecar file written to: {sidecar_path}")
    print()
    print("To verify integrity:")
    print(f"  python benchmarks/verify_benchmark_integrity.py --verbose")
    print()
    print("To verify manually:")
    print(f"  sha256sum {benchmark_path}")
    print(f"  Expected: {sha256_hash}")


if __name__ == "__main__":
    main()