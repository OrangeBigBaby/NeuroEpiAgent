#!/usr/bin/env python
"""Compute SHA-256 hash of the frozen benchmark file."""
import hashlib
from pathlib import Path

def compute_sha256(file_path):
    """Compute SHA-256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            sha256.update(chunk)
    return sha256.hexdigest()

if __name__ == "__main__":
    frozen_path = Path("benchmarks/tasks.v0.1.0.yaml")
    hash_value = compute_sha256(frozen_path)

    print(f"SHA-256 hash of {frozen_path}:")
    print(hash_value)
    print()
    print("Add this hash to:")
    print("  - benchmarks/BENCHMARK_CARD.md (update SHA-256 field)")
    print("  - Evaluation runs (task_set_hash field)")
