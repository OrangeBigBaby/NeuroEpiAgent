"""
Test suite for benchmark integrity verification system.

These tests verify that:
1. The sidecar hash generation works correctly
2. The integrity verifier properly validates frozen benchmarks
3. Tampering with benchmark files is detected
4. All validation checks work (task count, unique IDs, schema fields, etc.)
"""

import pytest
import json
import hashlib
import tempfile
import shutil
from pathlib import Path


class TestBenchmarkIntegrity:
    """Test suite for benchmark integrity verification."""

    def test_sidecar_generation(self):
        """Test that SHA-256 sidecar generation works correctly."""
        # Import the sidecar generation module
        import sys
        benchmarks_dir = Path(__file__).parent.parent / "benchmarks"
        sys.path.insert(0, str(benchmarks_dir))

        # Create a temporary test file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.yaml') as f:
            test_content = "test content for hash generation\n"
            f.write(test_content)
            test_file = Path(f.name)

        try:
            # Compute expected hash from actual bytes (handles Windows line endings)
            expected_hash = hashlib.sha256(test_file.read_bytes()).hexdigest()

            # Test the hash computation function
            from generate_sha256_sidecar import compute_sha256
            actual_hash = compute_sha256(test_file)

            assert actual_hash == expected_hash, "Hash computation should match actual file bytes"

        finally:
            test_file.unlink()

    def test_integrity_verifier_missing_sidecar(self):
        """Test verifier handles missing sidecar file correctly."""
        import sys
        benchmarks_dir = Path(__file__).parent.parent / "benchmarks"
        sys.path.insert(0, str(benchmarks_dir))

        from verify_benchmark_integrity import load_sidecar

        with tempfile.NamedTemporaryFile(delete=False) as f:
            sidecar_path = Path(f.name)

        # Delete the temp file to test missing case
        sidecar_path.unlink()

        try:
            with pytest.raises(SystemExit) as exc_info:
                load_sidecar(sidecar_path)
            assert exc_info.value.code == 5, "Should exit with code 5 for missing sidecar"
        finally:
            # Clean up any remaining files
            if sidecar_path.exists():
                sidecar_path.unlink()

    def test_integrity_verifier_invalid_json(self):
        """Test verifier handles invalid JSON in sidecar correctly."""
        import sys
        benchmarks_dir = Path(__file__).parent.parent / "benchmarks"
        sys.path.insert(0, str(benchmarks_dir))

        from verify_benchmark_integrity import load_sidecar

        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            f.write("{ invalid json content")
            sidecar_path = Path(f.name)

        try:
            with pytest.raises(SystemExit) as exc_info:
                load_sidecar(sidecar_path)
            assert exc_info.value.code == 5, "Should exit with code 5 for invalid JSON"
        finally:
            sidecar_path.unlink()

    def test_hash_verification_detects_tampering(self):
        """Test that hash verification detects file tampering."""
        import sys
        benchmarks_dir = Path(__file__).parent.parent / "benchmarks"
        sys.path.insert(0, str(benchmarks_dir))

        from verify_benchmark_integrity import compute_sha256

        # Create original file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.yaml') as f:
            original_content = "original content\n"
            f.write(original_content)
            test_file = Path(f.name)

        try:
            # Compute original hash
            original_hash = compute_sha256(test_file)

            # Tamper with the file
            with open(test_file, 'a') as f:
                f.write("tampered content\n")

            # Compute new hash
            tampered_hash = compute_sha256(test_file)

            # Hashes should be different
            assert original_hash != tampered_hash, "Tampering should change the hash"

        finally:
            test_file.unlink()

    def test_task_count_validation(self):
        """Test task count validation works correctly."""
        import sys
        benchmarks_dir = Path(__file__).parent.parent / "benchmarks"
        sys.path.insert(0, str(benchmarks_dir))

        from verify_benchmark_integrity import verify_task_count

        # Test correct task count
        valid_data = {
            'task_count': 30,
            'tasks': [{}] * 30
        }
        result = verify_task_count(valid_data, verbose=False)
        assert result is True, "Should pass with correct task count"

        # Test incorrect declared count
        invalid_declared = {
            'task_count': 29,
            'tasks': [{}] * 30
        }
        result = verify_task_count(invalid_declared, verbose=False)
        assert result is False, "Should fail with incorrect declared task count"

        # Test incorrect actual count
        invalid_actual = {
            'task_count': 30,
            'tasks': [{}] * 29
        }
        result = verify_task_count(invalid_actual, verbose=False)
        assert result is False, "Should fail with incorrect actual task count"

    def test_unique_ids_validation(self):
        """Test unique task ID validation works correctly."""
        import sys
        benchmarks_dir = Path(__file__).parent.parent / "benchmarks"
        sys.path.insert(0, str(benchmarks_dir))

        from verify_benchmark_integrity import verify_unique_ids

        # Test unique IDs
        valid_data = {
            'tasks': [
                {'id': 'task_1'},
                {'id': 'task_2'},
                {'id': 'task_3'}
            ]
        }
        result = verify_unique_ids(valid_data, verbose=False)
        assert result is True, "Should pass with unique IDs"

        # Test duplicate IDs
        invalid_data = {
            'tasks': [
                {'id': 'task_1'},
                {'id': 'task_1'},  # Duplicate
                {'id': 'task_3'}
            ]
        }
        result = verify_unique_ids(invalid_data, verbose=False)
        assert result is False, "Should fail with duplicate IDs"

    def test_review_status_validation(self):
        """Test review status consistency validation."""
        import sys
        benchmarks_dir = Path(__file__).parent.parent / "benchmarks"
        sys.path.insert(0, str(benchmarks_dir))

        from verify_benchmark_integrity import verify_review_status

        # Test consistent review status
        valid_data = {
            'tasks': [
                {'id': 'task_1', 'review_status': 'needs_expert_review'},
                {'id': 'task_2', 'review_status': 'needs_expert_review'}
            ]
        }
        result = verify_review_status(valid_data, verbose=False)
        assert result is True, "Should pass with consistent review status"

        # Test inconsistent review status
        invalid_data = {
            'tasks': [
                {'id': 'task_1', 'review_status': 'needs_expert_review'},
                {'id': 'task_2', 'review_status': 'expert_validated'}  # Wrong status
            ]
        }
        result = verify_review_status(invalid_data, verbose=False)
        assert result is False, "Should fail with inconsistent review status"

    def test_schema_field_validation(self):
        """Test schema field presence validation."""
        import sys
        benchmarks_dir = Path(__file__).parent.parent / "benchmarks"
        sys.path.insert(0, str(benchmarks_dir))

        from verify_benchmark_integrity import verify_schema_fields

        # Test complete metadata
        valid_data = {
            'schema_version': '1.0',
            'benchmark_name': 'Test Benchmark',
            'benchmark_version': '0.1.0',
            'frozen_timestamp': '2026-06-29T00:00:00Z',
            'status': 'DRAFT',
            'disclaimer': 'Test disclaimer',
            'task_count': 2,
            'domains': ['stroke'],
            'gold_standard_requirements': {},
            'tasks': [
                {
                    'id': 'task_1',
                    'domain': 'stroke',
                    'question': 'Test question',
                    'expected_database': 'NHANES',
                    'expected_feasible': True,
                    'rationale': 'Test rationale'
                }
            ]
        }
        result = verify_schema_fields(valid_data, verbose=False)
        assert result is True, "Should pass with complete schema"

        # Test missing metadata field
        invalid_metadata = {
            'benchmark_name': 'Test Benchmark',
            'tasks': []
            # Missing schema_version and other required fields
        }
        result = verify_schema_fields(invalid_metadata, verbose=False)
        assert result is False, "Should fail with missing metadata fields"

    def test_version_date_validation(self):
        """Test version date correctness validation."""
        import sys
        benchmarks_dir = Path(__file__).parent.parent / "benchmarks"
        sys.path.insert(0, str(benchmarks_dir))

        from verify_benchmark_integrity import verify_version_dates

        # Test correct 2026 date
        valid_data = {
            'frozen_timestamp': '2026-06-29T00:00:00Z',
            'benchmark_version': '0.1.0'
        }
        result = verify_version_dates(valid_data, verbose=False)
        assert result is True, "Should pass with correct 2026 date"

        # Test incorrect 2025 date
        invalid_data = {
            'frozen_timestamp': '2025-06-29T00:00:00Z',
            'benchmark_version': '0.1.0'
        }
        result = verify_version_dates(invalid_data, verbose=False)
        assert result is False, "Should fail with erroneous 2025 date"


class TestBenchmarkTamperingDetection:
    """Test tampering detection with actual file operations."""

    def test_complete_tampering_detection_workflow(self):
        """Test complete workflow: create, hash, tamper, detect."""
        import sys
        benchmarks_dir = Path(__file__).parent.parent / "benchmarks"
        sys.path.insert(0, str(benchmarks_dir))

        from generate_sha256_sidecar import compute_sha256
        from verify_benchmark_integrity import verify_hash

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create test benchmark file
            benchmark_file = temp_path / "test_benchmark.yaml"
            original_content = "# Test Benchmark\nschema_version: '1.0'\ntask_count: 2\n"
            benchmark_file.write_text(original_content)

            # Compute original hash
            original_hash = compute_sha256(benchmark_file)

            # Create sidecar file
            sidecar_file = benchmark_file.with_suffix('.sha256')
            sidecar_data = {
                'sha256': original_hash,
                'benchmark_file': 'test_benchmark.yaml'
            }
            sidecar_file.write_text(json.dumps(sidecar_data))

            # Test 1: Verify original file passes
            result = verify_hash(benchmark_file, original_hash, verbose=False)
            assert result is True, "Original file should pass verification"

            # Test 2: Tamper with file
            tampered_content = original_content + "# TAMPERED CONTENT\n"
            benchmark_file.write_text(tampered_content)

            # Test 3: Verify tampered file fails
            result = verify_hash(benchmark_file, original_hash, verbose=False)
            assert result is False, "Tampered file should fail verification"

    def test_benchmark_copy_and_modify(self):
        """Test that copying and modifying a benchmark is detected."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Copy actual benchmark file
            source_benchmark = Path(__file__).parent.parent / "benchmarks" / "tasks.v0.1.0.yaml"
            if not source_benchmark.exists():
                pytest.skip("Actual benchmark file not found")

            test_benchmark = temp_path / "test_tasks.v0.1.0.yaml"
            shutil.copy(source_benchmark, test_benchmark)

            # Compute hash of copy
            import sys
            benchmarks_dir = Path(__file__).parent.parent / "benchmarks"
            sys.path.insert(0, str(benchmarks_dir))

            from generate_sha256_sidecar import compute_sha256
            original_hash = compute_sha256(test_benchmark)

            # Modify the copy
            with open(test_benchmark, 'a') as f:
                f.write("\n# TAMPERED LINE\n")

            # Verify hash changed
            tampered_hash = compute_sha256(test_benchmark)
            assert original_hash != tampered_hash, "Modified file should have different hash"


class TestSidecarFormat:
    """Test sidecar file format and structure."""

    def test_sidecar_has_required_fields(self):
        """Test that sidecar JSON has all required fields."""
        sidecar_path = Path(__file__).parent.parent / "benchmarks" / "tasks.v0.1.0.sha256"

        if not sidecar_path.exists():
            pytest.skip("Sidecar file not yet generated")

        with open(sidecar_path) as f:
            sidecar_data = json.load(f)

        required_fields = [
            'format',
            'benchmark_file',
            'benchmark_version',
            'sha256',
            'generated_timestamp',
            'expected_task_count',
            'verification_status',
            'verification_instructions',
            'verified_checks'
        ]

        for field in required_fields:
            assert field in sidecar_data, f"Sidecar missing required field: {field}"

    def test_sidecar_sha256_format(self):
        """Test that sidecar SHA-256 hash is valid hex format."""
        sidecar_path = Path(__file__).parent.parent / "benchmarks" / "tasks.v0.1.0.sha256"

        if not sidecar_path.exists():
            pytest.skip("Sidecar file not yet generated")

        with open(sidecar_path) as f:
            sidecar_data = json.load(f)

        sha256_hash = sidecar_data.get('sha256')

        # SHA-256 should be 64 hex characters
        assert len(sha256_hash) == 64, "SHA-256 hash should be 64 characters"
        assert all(c in '0123456789abcdef' for c in sha256_hash), "SHA-256 should be hexadecimal"


class TestTamperSmokeTest:
    """Smoke test for tamper detection."""

    def test_tamper_detection_smoke_test(self):
        """Test that tampering with benchmark file is detected."""
        import sys
        benchmarks_dir = Path(__file__).parent.parent / "benchmarks"
        sys.path.insert(0, str(benchmarks_dir))

        from generate_sha256_sidecar import compute_sha256

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Copy actual benchmark file
            source_benchmark = Path(__file__).parent.parent / "benchmarks" / "tasks.v0.1.0.yaml"
            if not source_benchmark.exists():
                pytest.skip("Actual benchmark file not found")

            test_benchmark = temp_path / "test_tasks.v0.1.0.yaml"
            shutil.copy(source_benchmark, test_benchmark)

            # Compute original hash
            original_hash = compute_sha256(test_benchmark)

            # Create sidecar with original hash
            sidecar_file = test_benchmark.with_suffix('.sha256')
            sidecar_data = {
                'sha256': original_hash,
                'benchmark_file': 'test_tasks.v0.1.0.yaml'
            }
            sidecar_file.write_text(json.dumps(sidecar_data))

            # Verify original passes
            from verify_benchmark_integrity import verify_hash
            result = verify_hash(test_benchmark, original_hash, verbose=False)
            assert result is True, "Original file should pass verification"

            # Tamper with the file (change one byte)
            with open(test_benchmark, 'r+b') as f:
                f.seek(100)  # Skip to middle of file
                original_byte = f.read(1)
                f.seek(100)  # Go back
                # Flip one bit in the byte
                tampered_byte = bytes([original_byte[0] ^ 0x01])
                f.write(tampered_byte)

            # Verify tampered file fails
            tampered_hash = compute_sha256(test_benchmark)
            result = verify_hash(test_benchmark, original_hash, verbose=False)
            assert result is False, "Tampered file should fail verification"

            # Verify hash changed
            assert tampered_hash != original_hash, "Tampered file should have different hash"
