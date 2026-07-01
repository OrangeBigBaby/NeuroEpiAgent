"""
Test suite for human adjudication system.

Tests for:
- Expert rating template generation
- Rating import and validation
- Inter-rater reliability computation
- Consensus process management
- Report generation

CRITICAL: All tests verify that no ratings or kappa statistics are generated without actual human data.
"""

import pytest
import tempfile
import csv
from pathlib import Path
from datetime import datetime

from neurosurg_epi_agent.adjudication import (
    AdjudicationManager,
    AdjudicationStatus,
    RaterInfo,
    ExpertRating,
    ConsensusRating,
    create_adjudication_manager
)


class TestAdjudicationManagerInit:
    """Test adjudication manager initialization."""

    def test_manager_initialization(self):
        """Test manager initializes with correct defaults."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = AdjudicationManager(
                benchmark_path=Path("test.yaml"),
                output_dir=Path(temp_dir)
            )

            assert manager.status == AdjudicationStatus.NOT_STARTED
            assert len(manager.raters) == 0
            assert len(manager.ratings) == 0
            assert len(manager.consensus_ratings) == 0

    def test_output_directory_creation(self):
        """Test that output directories are created."""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "adjudication"
            manager = AdjudicationManager(
                benchmark_path=Path("test.yaml"),
                output_dir=output_path
            )

            assert output_path.exists()
            assert manager.ratings_dir.exists()


class TestRatingTemplateGeneration:
    """Test expert rating template generation."""

    def test_create_single_rater_template(self):
        """Test creating template for single rater."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a minimal benchmark file
            benchmark_path = Path(temp_dir) / "tasks.yaml"
            benchmark_path.write_text("""
tasks:
  - id: test_task_1
    domain: stroke
    question: Test question 1
  - id: test_task_2
    domain: tbi
    question: Test question 2
""")

            manager = AdjudicationManager(
                benchmark_path=benchmark_path,
                output_dir=Path(temp_dir)
            )

            rater_info = [RaterInfo(
                rater_id="rater_01",
                name="Dr. Test",
                credentials="MD, Neurologist",
                affiliation="Test University"
            )]

            template_paths = manager.create_rating_templates(rater_info)

            assert "rater_01" in template_paths
            assert template_paths["rater_01"].exists()

            # Check template content
            with open(template_paths["rater_01"]) as f:
                content = f.read()

            assert "Dr. Test" in content
            assert "test_task_1" in content
            assert "test_task_2" in content
            assert "database_routing_correct" in content

    def test_create_multiple_rater_templates(self):
        """Test creating templates for multiple raters."""
        with tempfile.TemporaryDirectory() as temp_dir:
            benchmark_path = Path(temp_dir) / "tasks.yaml"
            benchmark_path.write_text("tasks:\n  - id: task1\n    domain: stroke\n    question: Test\n")

            manager = AdjudicationManager(
                benchmark_path=benchmark_path,
                output_dir=Path(temp_dir)
            )

            rater_info = [
                RaterInfo("rater_01", "Dr. Smith", "MD", "Hospital A"),
                RaterInfo("rater_02", "Dr. Jones", "PhD", "University B")
            ]

            template_paths = manager.create_rating_templates(rater_info)

            assert len(template_paths) == 2
            assert all(path.exists() for path in template_paths.values())

    def test_template_status_update(self):
        """Test that template creation updates manager status."""
        with tempfile.TemporaryDirectory() as temp_dir:
            benchmark_path = Path(temp_dir) / "tasks.yaml"
            benchmark_path.write_text("tasks:\n  - id: task1\n    domain: stroke\n    question: Test\n")

            manager = AdjudicationManager(
                benchmark_path=benchmark_path,
                output_dir=Path(temp_dir)
            )

            rater_info = [RaterInfo("rater_01", "Dr. Test", "MD", "Test")]

            manager.create_rating_templates(rater_info)

            assert manager.status == AdjudicationStatus.TEMPLATES_CREATED


class TestRatingImport:
    """Test expert rating import functionality."""

    def test_import_valid_ratings(self):
        """Test importing valid expert ratings."""
        with tempfile.TemporaryDirectory() as temp_dir:
            benchmark_path = Path(temp_dir) / "tasks.yaml"
            benchmark_path.write_text("tasks:\n  - id: task1\n    domain: stroke\n    question: Test\n")

            manager = AdjudicationManager(
                benchmark_path=benchmark_path,
                output_dir=Path(temp_dir)
            )

            # Register rater
            manager.raters["rater_01"] = RaterInfo("rater_01", "Dr. Test", "MD", "Test")

            # Create rating CSV
            rating_file = Path(temp_dir) / "ratings.csv"
            with open(rating_file, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    "task_id", "domain", "question",
                    "database_routing_correct", "feasibility_correct",
                    "plan_quality", "variable_codes_correct",
                    "overall_acceptable", "notes"
                ])
                writer.writerow([
                    "task1", "stroke", "Test question",
                    "TRUE", "TRUE", "good", "TRUE", "TRUE", "Looks good"
                ])

            # Import ratings
            count = manager.import_ratings("rater_01", rating_file)

            assert count == 1
            assert "task1" in manager.ratings
            assert len(manager.ratings["task1"]) == 1
            assert manager.ratings["task1"][0].database_routing_correct is True
            assert manager.status == AdjudicationStatus.RATINGS_IN_PROGRESS

    def test_import_invalid_rater_id(self):
        """Test import fails with invalid rater ID."""
        with tempfile.TemporaryDirectory() as temp_dir:
            benchmark_path = Path(temp_dir) / "tasks.yaml"
            benchmark_path.write_text("tasks:\n  - id: task1\n    domain: stroke\n    question: Test\n")

            manager = AdjudicationManager(
                benchmark_path=benchmark_path,
                output_dir=Path(temp_dir)
            )

            rating_file = Path(temp_dir) / "ratings.csv"
            rating_file.write_text("task_id,domain,question\ntask1,stroke,Test\n")

            with pytest.raises(ValueError, match="Unknown rater_id"):
                manager.import_ratings("unknown_rater", rating_file)

    def test_rating_completeness_check(self):
        """Test rating completeness validation."""
        # Complete rating
        complete_rating = ExpertRating(
            task_id="task1",
            rater_id="rater_01",
            database_routing_correct=True,
            feasibility_correct=True,
            overall_acceptable=True
        )
        assert complete_rating.is_complete() is True

        # Incomplete rating (missing field)
        incomplete_rating = ExpertRating(
            task_id="task1",
            rater_id="rater_01",
            database_routing_correct=True,
            feasibility_correct=True
            # Missing overall_acceptable
        )
        assert incomplete_rating.is_complete() is False


class TestRatingValidation:
    """Test rating validation functionality."""

    def test_validate_complete_ratings(self):
        """Test validation passes with complete ratings."""
        with tempfile.TemporaryDirectory() as temp_dir:
            benchmark_path = Path(temp_dir) / "tasks.yaml"
            benchmark_path.write_text("tasks:\n  - id: task1\n    domain: stroke\n    question: Test\n")

            manager = AdjudicationManager(
                benchmark_path=benchmark_path,
                output_dir=Path(temp_dir)
            )

            # Add complete ratings
            manager.ratings["task1"] = [
                ExpertRating("task1", "rater_01", True, True, "good", True, True),
                ExpertRating("task1", "rater_02", True, True, "good", True, True)
            ]
            manager.raters["rater_01"] = RaterInfo("rater_01", "Dr. A", "MD", "A")
            manager.raters["rater_02"] = RaterInfo("rater_02", "Dr. B", "PhD", "B")

            validation = manager.validate_ratings()

            assert validation['valid'] is True
            assert len(validation['errors']) == 0

    def test_validate_incomplete_ratings(self):
        """Test validation detects incomplete ratings."""
        with tempfile.TemporaryDirectory() as temp_dir:
            benchmark_path = Path(temp_dir) / "tasks.yaml"
            benchmark_path.write_text("tasks:\n  - id: task1\n    domain: stroke\n    question: Test\n")

            manager = AdjudicationManager(
                benchmark_path=benchmark_path,
                output_dir=Path(temp_dir)
            )

            # Add incomplete rating
            manager.ratings["task1"] = [
                ExpertRating("task1", "rater_01", True, None, "good", True, True)
            ]
            manager.raters["rater_01"] = RaterInfo("rater_01", "Dr. A", "MD", "A")

            validation = manager.validate_ratings()

            assert validation['valid'] is False
            assert len(validation['warnings']) > 0
            assert any("incomplete" in w.lower() for w in validation['warnings'])


class TestInterRaterReliability:
    """Test inter-rater reliability computation."""

    def test_reliability_without_human_data(self):
        """Test that reliability requires actual human data."""
        with tempfile.TemporaryDirectory() as temp_dir:
            benchmark_path = Path(temp_dir) / "tasks.yaml"
            benchmark_path.write_text("tasks:\n  - id: task1\n    domain: stroke\n    question: Test\n")

            manager = AdjudicationManager(
                benchmark_path=benchmark_path,
                output_dir=Path(temp_dir)
            )

            reliability = manager.compute_inter_rater_reliability()

            assert 'error' in reliability
            assert 'no ratings available' in reliability['error'].lower()
            assert 'note' in reliability
            assert 'human data' in reliability['note'].lower()

    def test_reliability_with_insufficient_data(self):
        """Test reliability with insufficient paired ratings."""
        with tempfile.TemporaryDirectory() as temp_dir:
            benchmark_path = Path(temp_dir) / "tasks.yaml"
            benchmark_path.write_text("tasks:\n  - id: task1\n    domain: stroke\n    question: Test\n")

            manager = AdjudicationManager(
                benchmark_path=benchmark_path,
                output_dir=Path(temp_dir)
            )

            # Add only one rater (insufficient for reliability)
            manager.ratings["task1"] = [
                ExpertRating("task1", "rater_01", True, True, "good", True, True)
            ]

            reliability = manager.compute_inter_rater_reliability()

            # Should report insufficient data
            assert reliability['tasks_analyzed'] == 0

    def test_reliability_never_fabricates_data(self):
        """Test that reliability computation never creates fake ratings."""
        with tempfile.TemporaryDirectory() as temp_dir:
            benchmark_path = Path(temp_dir) / "tasks.yaml"
            benchmark_path.write_text("tasks:\n  - id: task1\n    domain: stroke\n    question: Test\n")

            manager = AdjudicationManager(
                benchmark_path=benchmark_path,
                output_dir=Path(temp_dir)
            )

            # Empty ratings
            reliability = manager.compute_inter_rater_reliability()

            # Should return error, not fabricated kappa
            assert 'error' in reliability
            assert 'kappa' not in reliability or 'kappa_by_field' not in reliability.get('kappa', {})


class TestConsensusProcess:
    """Test consensus meeting functionality."""

    def test_create_consensus_template(self):
        """Test creating consensus meeting template."""
        with tempfile.TemporaryDirectory() as temp_dir:
            benchmark_path = Path(temp_dir) / "tasks.yaml"
            benchmark_path.write_text("tasks:\n  - id: task1\n    domain: stroke\n    question: Test\n")

            manager = AdjudicationManager(
                benchmark_path=benchmark_path,
                output_dir=Path(temp_dir)
            )

            # Add some raters and ratings
            manager.raters["rater_01"] = RaterInfo("rater_01", "Dr. A", "MD", "A")
            manager.raters["rater_02"] = RaterInfo("rater_02", "Dr. B", "PhD", "B")
            manager.ratings["task1"] = [
                ExpertRating("task1", "rater_01", True, True, "good", True, True, "Good plan"),
                ExpertRating("task1", "rater_02", True, True, "excellent", True, True, "Excellent plan")
            ]

            template_path = manager.create_consensus_template()

            assert template_path.exists()
            assert manager.status == AdjudicationStatus.CONSENSUS_IN_PROGRESS

            # Check template includes existing notes
            with open(template_path) as f:
                content = f.read()

            assert "Good plan" in content or "Excellent plan" in content

    def test_import_consensus_ratings(self):
        """Test importing consensus ratings."""
        with tempfile.TemporaryDirectory() as temp_dir:
            benchmark_path = Path(temp_dir) / "tasks.yaml"
            benchmark_path.write_text("tasks:\n  - id: task1\n    domain: stroke\n    question: Test\n")

            manager = AdjudicationManager(
                benchmark_path=benchmark_path,
                output_dir=Path(temp_dir)
            )

            # Create consensus CSV
            consensus_file = Path(temp_dir) / "consensus.csv"
            with open(consensus_file, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    "task_id", "consensus_date", "database_routing_correct",
                    "feasibility_correct", "plan_quality", "variable_codes_correct",
                    "overall_acceptable", "notes", "disagreements_resolved"
                ])
                writer.writerow([
                    "task1", "2026-06-29", "TRUE", "TRUE", "good", "TRUE", "TRUE",
                    "Consensus reached", ""
                ])

            count = manager.import_consensus_ratings(consensus_file)

            assert count == 1
            assert "task1" in manager.consensus_ratings
            assert manager.consensus_ratings["task1"].database_routing_correct is True
            assert manager.status == AdjudicationStatus.COMPLETE


class TestReportGeneration:
    """Test adjudication report generation."""

    def test_report_includes_all_sections(self):
        """Test report contains all required sections."""
        with tempfile.TemporaryDirectory() as temp_dir:
            benchmark_path = Path(temp_dir) / "tasks.yaml"
            benchmark_path.write_text("tasks:\n  - id: task1\n    domain: stroke\n    question: Test\n")

            manager = AdjudicationManager(
                benchmark_path=benchmark_path,
                output_dir=Path(temp_dir)
            )

            # Add minimal data
            manager.raters["rater_01"] = RaterInfo("rater_01", "Dr. A", "MD", "A")
            manager.ratings["task1"] = [
                ExpertRating("task1", "rater_01", True, True, "good", True, True)
            ]

            report = manager.generate_adjudication_report()

            assert 'status' in report
            assert 'validation' in report
            assert 'inter_rater_reliability' in report
            assert 'raters' in report
            assert 'recommendations' in report

    def test_report_recommendations_by_status(self):
        """Test recommendations are appropriate for status."""
        with tempfile.TemporaryDirectory() as temp_dir:
            benchmark_path = Path(temp_dir) / "tasks.yaml"
            benchmark_path.write_text("tasks:\n  - id: task1\n    domain: stroke\n    question: Test\n")

            manager = AdjudicationManager(
                benchmark_path=benchmark_path,
                output_dir=Path(temp_dir)
            )

            # Test NOT_STARTED recommendations
            report = manager.generate_adjudication_report()
            assert any("templates" in rec.lower() for rec in report['recommendations'])

            # Test TEMPLATES_CREATED status
            manager.status = AdjudicationStatus.TEMPLATES_CREATED
            report = manager.generate_adjudication_report()
            assert any("distribute" in rec.lower() for rec in report['recommendations'])


class TestSafetyGuards:
    """Test safety guards for human data requirements."""

    def test_never_generate_fake_ratings(self):
        """Test system never generates fake expert ratings."""
        with tempfile.TemporaryDirectory() as temp_dir:
            benchmark_path = Path(temp_dir) / "tasks.yaml"
            benchmark_path.write_text("tasks:\n  - id: task1\n    domain: stroke\n    question: Test\n")

            manager = AdjudicationManager(
                benchmark_path=benchmark_path,
                output_dir=Path(temp_dir)
            )

            # Empty manager
            assert len(manager.ratings) == 0

            # Try to get reliability
            reliability = manager.compute_inter_rater_reliability()

            # Should return error, not fake data
            assert 'error' in reliability
            assert reliability.get('tasks_analyzed', 0) == 0

    def test_never_report_kappa_without_human_data(self):
        """Test kappa is never reported without actual human ratings."""
        with tempfile.TemporaryDirectory() as temp_dir:
            benchmark_path = Path(temp_dir) / "tasks.yaml"
            benchmark_path.write_text("tasks:\n  - id: task1\n    domain: stroke\n    question: Test\n")

            manager = AdjudicationManager(
                benchmark_path=benchmark_path,
                output_dir=Path(temp_dir)
            )

            # No human ratings
            reliability = manager.compute_inter_rater_reliability()

            # Should not have kappa statistics
            if 'kappa_by_field' in reliability:
                # If field exists, all entries should have errors
                for field, stats in reliability['kappa_by_field'].items():
                    assert 'error' in stats or stats.get('n_valid', 0) == 0

    def test_validation_detects_missing_raters(self):
        """Test validation detects when expected raters haven't submitted."""
        with tempfile.TemporaryDirectory() as temp_dir:
            benchmark_path = Path(temp_dir) / "tasks.yaml"
            benchmark_path.write_text("tasks:\n  - id: task1\n    domain: stroke\n    question: Test\n")

            manager = AdjudicationManager(
                benchmark_path=benchmark_path,
                output_dir=Path(temp_dir)
            )

            # Register 2 raters
            manager.raters["rater_01"] = RaterInfo("rater_01", "Dr. A", "MD", "A")
            manager.raters["rater_02"] = RaterInfo("rater_02", "Dr. B", "PhD", "B")

            # Only one rater submitted
            manager.ratings["task1"] = [
                ExpertRating("task1", "rater_01", True, True, "good", True, True)
            ]

            validation = manager.validate_ratings()

            # Should warn about missing rater
            assert any("rater" in warning.lower() for warning in validation['warnings'])