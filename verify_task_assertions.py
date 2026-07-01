#!/usr/bin/env python3
"""
Assertion script to verify tasks.draft.yaml meets Phase-2 acceptance criteria.

This script verifies:
1. Exactly 30 tasks
2. All required fields present
3. All tasks have review_status: needs_expert_review
4. At least 2 pituitary tasks
5. All required domains are covered
"""

import yaml
import sys
from pathlib import Path

def verify_tasks():
    """Verify tasks.draft.yaml meets all Phase-2 acceptance criteria."""

    # Load the tasks file
    tasks_file = Path("benchmarks/tasks.draft.yaml")
    if not tasks_file.exists():
        print(f"ERROR: {tasks_file} not found")
        return False

    with open(tasks_file) as f:
        data = yaml.safe_load(f)

    tasks = data.get("tasks", [])

    # Verify task count
    if len(tasks) != 30:
        print(f"ERROR: Expected 30 tasks, found {len(tasks)}")
        return False
    print(f"[OK] Task count: {len(tasks)}")

    # Verify required fields for each task
    required_fields = [
        "id", "domain", "question", "expected_database",
        "expected_feasible", "rationale", "review_status"
    ]

    for i, task in enumerate(tasks):
        for field in required_fields:
            if field not in task:
                print(f"ERROR: Task {i} missing required field: {field}")
                return False

        # Verify review_status is needs_expert_review
        if task["review_status"] != "needs_expert_review":
            print(f"ERROR: Task {task['id']} has review_status: {task['review_status']}")
            return False
    print(f"[OK] All tasks have required fields")
    print(f"[OK] All tasks have review_status: needs_expert_review")

    # Verify pituitary coverage (at least 2 tasks)
    pituitary_count = sum(1 for task in tasks if task["domain"] == "pituitary")
    if pituitary_count < 2:
        print(f"ERROR: Expected at least 2 pituitary tasks, found {pituitary_count}")
        return False
    print(f"[OK] Pituitary coverage: {pituitary_count} tasks")

    # Verify all required domains are covered
    required_domains = [
        "stroke", "tbi", "tumor", "sah", "hydrocephalus",
        "spine", "disparities", "global_burden", "pituitary"
    ]

    found_domains = set(task["domain"] for task in tasks)
    missing_domains = set(required_domains) - found_domains

    if missing_domains:
        print(f"ERROR: Missing required domains: {missing_domains}")
        return False

    print(f"[OK] All required domains covered: {sorted(found_domains)}")

    # Print domain breakdown
    domain_counts = {}
    for task in tasks:
        domain = task["domain"]
        domain_counts[domain] = domain_counts.get(domain, 0) + 1

    print("\nDomain breakdown:")
    for domain in sorted(domain_counts.keys()):
        print(f"  {domain}: {domain_counts[domain]}")

    return True

if __name__ == "__main__":
    success = verify_tasks()
    sys.exit(0 if success else 1)