#!/usr/bin/env python
"""Simple hash computation without subprocess calls."""
import hashlib

# Read the frozen benchmark file
with open("benchmarks/tasks.v0.1.0.yaml", "rb") as f:
    content = f.read()

# Compute SHA-256
sha256_hash = hashlib.sha256(content).hexdigest()

print("SHA-256 Hash of Frozen Benchmark:")
print("=" * 64)
print(sha256_hash)
print("=" * 64)

# Store hash for reference
with open("benchmarks/tasks.v0.1.0.sha256", "w") as f:
    f.write(f"{sha256_hash}  tasks.v0.1.0.yaml\n")

print(f"\nHash saved to benchmarks/tasks.v0.1.0.sha256")
print("\nUpdate BENCHMARK_CARD.md with this hash value")
