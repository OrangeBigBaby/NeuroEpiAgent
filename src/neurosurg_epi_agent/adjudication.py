#!/usr/bin/env python
"""
NeuroSurgEpiAgent Human Adjudication Manager

Manages expert rating workflow for benchmark adjudication:
- Creates expert rating CSV templates
- Imports and validates expert ratings
- Computes inter-rater reliability
- Generates consensus reports
- Manages adjudication status

IMPORTANT: This module NEVER fills ratings or reports kappa without actual human data.
All computed statistics require real expert input.
"""

import csv
import json
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from neurosurg_epi_agent.statistics import cohen_kappa, format_p_value


class AdjudicationStatus(Enum):
    """Status of expert adjudication process."""
    NOT_STARTED = "not_started"
    TEMPLATES_CREATED = "templates_created"
    RATINGS_IN_PROGRESS = "ratings_in_progress"
    RATINGS_COMPLETE = "ratings_complete"
    CONSENSUS_IN_PROGRESS = "consensus_in_progress"
    COMPLETE = "complete"


class RatingField(Enum):
    """Standard rating fields for expert evaluation."""
    DATABASE_ROUTING_CORRECT = "database_routing_correct"
    FEASIBILITY_CORRECT = "feasibility_correct"
    PLAN_QUALITY = "plan_quality"
    VARIABLE_CODES_CORRECT = "variable_codes_correct"
    OVERALL_ACCEPTABLE = "overall_acceptable"
    NOTES = "notes"


@dataclass
class RaterInfo:
    """Information about an expert rater."""
    rater_id: str
    name: str
    credentials: str  # e.g., "MD, Neurologist", "PhD, Epidemiologist"
    affiliation: str
    date_rated: Optional[str] = None


@dataclass
class ExpertRating:
    """Individual expert rating for a single task."""
    task_id: str
    rater_id: str
    database_routing_correct: Optional[bool] = None
    feasibility_correct: Optional[bool] = None
    plan_quality: Optional[str] = None  # "excellent", "good", "fair", "poor"
    variable_codes_correct: Optional[bool] = None
    overall_acceptable: Optional[bool] = None
    notes: Optional[str] = None
    date_rated: Optional[str] = None

    def is_complete(self) -> bool:
        """Check if all required ratings are provided."""
        return (
            self.database_routing_correct is not None and
            self.feasibility_correct is not None and
            self.overall_acceptable is not None
        )


@dataclass
class ConsensusRating:
    """Consensus rating after expert discussion."""
    task_id: str
    consensus_date: str
    database_routing_correct: bool
    feasibility_correct: bool
    plan_quality: str
    variable_codes_correct: bool
    overall_acceptable: bool
    notes: str
    disagreements_resolved: List[str] = field(default_factory=list)


class AdjudicationManager:
    """
    Manages expert adjudication workflow.

    Features:
    - CSV template generation for expert raters
    - Rating import and validation
    - Inter-rater reliability computation
    - Consensus meeting support
    - Status tracking
    """

    def __init__(self, benchmark_path: Path, output_dir: Path):
        self.benchmark_path = benchmark_path
        self.output_dir = output_dir
        self.raters: Dict[str, RaterInfo] = {}
        self.ratings: Dict[str, List[ExpertRating]] = {}  # task_id -> list of ratings
        self.consensus_ratings: Dict[str, ConsensusRating] = {}
        self.status = AdjudicationStatus.NOT_STARTED
        self.template_path = self.output_dir / "expert_rating_template.csv"
        self.ratings_dir = self.output_dir / "expert_ratings"
        self.consensus_path = self.output_dir / "consensus_ratings.csv"

        # Create output directories
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.ratings_dir.mkdir(exist_ok=True)

    def create_rating_templates(self, rater_info: List[RaterInfo]) -> Dict[str, Path]:
        """
        Create CSV rating templates for expert raters.

        Args:
            rater_info: List of rater information

        Returns:
            Dict mapping rater_id to template file path
        """
        # Load benchmark tasks
        tasks = self._load_benchmark_tasks()

        # Create template for each rater
        template_paths = {}

        for rater in rater_info:
            # Register rater
            self.raters[rater.rater_id] = rater

            # Create individual CSV file
            rater_template_path = self.ratings_dir / f"rating_template_{rater.rater_id}.csv"

            with open(rater_template_path, 'w', newline='') as f:
                writer = csv.writer(f)

                # Write header with instructions
                writer.writerow(["# Expert Rating Template"])
                writer.writerow([f"# Rater: {rater.name} ({rater.credentials})"])
                writer.writerow([f"# Affiliation: {rater.affiliation}"])
                writer.writerow([f"# Date: {datetime.now().strftime('%Y-%m-%d')}"])
                writer.writerow([])
                writer.writerow(["# INSTRUCTIONS:"])
                writer.writerow(["# 1. Rate each task on the specified criteria"])
                writer.writerow(["# 2. Use TRUE/FALSE for binary correctness questions"])
                writer.writerow(["# 3. Use excellent/good/fair/poor for plan quality"])
                writer.writerow(["# 4. Add optional notes in the notes column"])
                writer.writerow(["# 5. Save this file with your ratings when complete"])
                writer.writerow([])
                writer.writerow([
                    "task_id",
                    "domain",
                    "question",
                    "database_routing_correct",
                    "feasibility_correct",
                    "plan_quality",
                    "variable_codes_correct",
                    "overall_acceptable",
                    "notes"
                ])

                # Write tasks
                for task in tasks:
                    writer.writerow([
                        task.get('id'),
                        task.get('domain'),
                        task.get('question', '')[:100],  # Truncate long questions
                        "",  # database_routing_correct (empty for rater to fill)
                        "",  # feasibility_correct
                        "",  # plan_quality
                        "",  # variable_codes_correct
                        "",  # overall_acceptable
                        ""   # notes
                    ])

            template_paths[rater.rater_id] = rater_template_path

        self.status = AdjudicationStatus.TEMPLATES_CREATED
        return template_paths

    def import_ratings(self, rater_id: str, csv_path: Path) -> int:
        """
        Import expert ratings from CSV file.

        Args:
            rater_id: ID of the rater
            csv_path: Path to rating CSV file

        Returns:
            Number of ratings imported
        """
        if rater_id not in self.raters:
            raise ValueError(f"Unknown rater_id: {rater_id}")

        imported_count = 0

        with open(csv_path) as f:
            reader = csv.DictReader(f)

            for row in reader:
                # Skip instruction lines
                if row.get('task_id', '').startswith('#'):
                    continue

                task_id = row.get('task_id')
                if not task_id:
                    continue

                # Create rating
                rating = ExpertRating(
                    task_id=task_id,
                    rater_id=rater_id,
                    database_routing_correct=self._parse_bool(row.get('database_routing_correct')),
                    feasibility_correct=self._parse_bool(row.get('feasibility_correct')),
                    plan_quality=row.get('plan_quality'),
                    variable_codes_correct=self._parse_bool(row.get('variable_codes_correct')),
                    overall_acceptable=self._parse_bool(row.get('overall_acceptable')),
                    notes=row.get('notes'),
                    date_rated=datetime.now().isoformat()
                )

                # Store rating
                if task_id not in self.ratings:
                    self.ratings[task_id] = []

                self.ratings[task_id].append(rating)
                imported_count += 1

        self.status = AdjudicationStatus.RATINGS_IN_PROGRESS
        return imported_count

    def validate_ratings(self) -> Dict[str, Any]:
        """
        Validate imported expert ratings.

        Returns:
            Validation report with errors, warnings, and statistics
        """
        validation_report = {
            'valid': True,
            'errors': [],
            'warnings': [],
            'statistics': {}
        }

        # Check for missing raters
        expected_raters = set(self.raters.keys())
        actual_raters = set()
        for task_ratings in self.ratings.values():
            for rating in task_ratings:
                actual_raters.add(rating.rater_id)

        missing_raters = expected_raters - actual_raters
        if missing_raters:
            validation_report['warnings'].append(
                f"Missing ratings from raters: {missing_raters}"
            )

        # Check for incomplete ratings
        incomplete_count = 0
        for task_id, task_ratings in self.ratings.items():
            for rating in task_ratings:
                if not rating.is_complete():
                    incomplete_count += 1
                    validation_report['warnings'].append(
                        f"Incomplete rating: task={task_id}, rater={rating.rater_id}"
                    )

        # Check for task coverage
        expected_tasks = 30  # From benchmark
        actual_tasks = len(self.ratings)
        if actual_tasks < expected_tasks:
            validation_report['warnings'].append(
                f"Only {actual_tasks}/{expected_tasks} tasks have ratings"
            )

        # Statistics
        validation_report['statistics'] = {
            'total_ratings': sum(len(ratings) for ratings in self.ratings.values()),
            'tasks_with_ratings': len(self.ratings),
            'raters_participating': len(actual_raters),
            'incomplete_ratings': incomplete_count
        }

        # Determine validity
        validation_report['valid'] = (
            len(validation_report['errors']) == 0 and
            incomplete_count == 0
        )

        return validation_report

    def compute_inter_rater_reliability(self) -> Dict[str, Any]:
        """
        Compute inter-rater reliability statistics.

        Returns:
            Dictionary with kappa statistics and agreement metrics

        Note: This only computes real statistics if human data exists.
        Returns error if no human ratings available.
        """
        if not self.ratings:
            return {
                'error': 'No ratings available for inter-rater reliability analysis',
            'note': 'Inter-rater reliability requires actual human data from expert raters'
            }

        reliability_results = {
            'tasks_analyzed': 0,
            'kappa_by_field': {},
            'raw_agreement': {}
        }

        # Compute reliability for each rating field
        fields_to_analyze = [
            ('database_routing_correct', 'binary'),
            ('feasibility_correct', 'binary'),
            ('overall_acceptable', 'binary')
        ]

        for field_name, field_type in fields_to_analyze:
            # Extract paired ratings
            ratings1 = []
            ratings2 = []

            for task_id, task_ratings in self.ratings.items():
                if len(task_ratings) >= 2:
                    # Get first two raters
                    ratings1.append(task_ratings[0].__dict__.get(field_name))
                    ratings2.append(task_ratings[1].__dict__.get(field_name))

            if not ratings1:
                reliability_results['kappa_by_field'][field_name] = {
                    'error': 'Insufficient paired ratings for analysis',
                    'note': 'Requires at least 2 raters per task'
                }
                continue

            # Compute Cohen's kappa
            kappa_result = cohen_kappa(ratings1, ratings2)

            reliability_results['kappa_by_field'][field_name] = {
                'kappa': kappa_result.kappa,
                'ci_lower': kappa_result.ci_lower,
                'ci_upper': kappa_result.ci_upper,
                'observed_agreement': kappa_result.observed_agreement,
                'expected_agreement': kappa_result.expected_agreement,
                'n_valid': kappa_result.n,
                'warning': kappa_result.warning
            }

            reliability_results['tasks_analyzed'] = kappa_result.n

        return reliability_results

    def create_consensus_template(self) -> Path:
        """
        Create CSV template for consensus meeting.

        Returns:
            Path to consensus template file
        """
        tasks = self._load_benchmark_tasks()

        with open(self.consensus_path, 'w', newline='') as f:
            writer = csv.writer(f)

            # Write header
            writer.writerow(["# Expert Consensus Rating Template"])
            writer.writerow([f"# Date: {datetime.now().strftime('%Y-%m-%d')}"])
            writer.writerow([f"# Participants: {', '.join(r.name for r in self.raters.values())}"])
            writer.writerow([])
            writer.writerow(["# INSTRUCTIONS:"])
            writer.writerow(["# 1. Discuss each task and reach consensus on ratings"])
            writer.writerow(["# 2. Fill in the consensus ratings below"])
            writer.writerow(["# 3. Document any disagreements resolved in notes"])
            writer.writerow([])

            # Write column headers
            writer.writerow([
                "task_id",
                "consensus_date",
                "database_routing_correct",
                "feasibility_correct",
                "plan_quality",
                "variable_codes_correct",
                "overall_acceptable",
                "notes",
                "disagreements_resolved"
            ])

            # Write tasks with existing ratings for reference
            for task in tasks:
                task_id = task.get('id')

                # Get existing ratings for reference
                task_notes = []
                if task_id in self.ratings:
                    for rating in self.ratings[task_id]:
                        rater = self.raters.get(rating.rater_id)
                        if rater:
                            task_notes.append(f"{rater.name}: {rating.notes or 'No notes'}")

                writer.writerow([
                    task_id,
                    "",  # consensus_date (to be filled)
                    "",  # database_routing_correct
                    "",  # feasibility_correct
                    "",  # plan_quality
                    "",  # variable_codes_correct
                    "",  # overall_acceptable
                    "",  # notes
                    " | ".join(task_notes)  # Pre-populate with existing notes
                ])

        self.status = AdjudicationStatus.CONSENSUS_IN_PROGRESS
        return self.consensus_path

    def import_consensus_ratings(self, csv_path: Path) -> int:
        """
        Import consensus ratings from CSV file.

        Args:
            csv_path: Path to consensus CSV file

        Returns:
            Number of consensus ratings imported
        """
        imported_count = 0

        with open(csv_path) as f:
            reader = csv.DictReader(f)

            for row in reader:
                # Skip instruction lines
                if row.get('task_id', '').startswith('#'):
                    continue

                task_id = row.get('task_id')
                if not task_id:
                    continue

                consensus = ConsensusRating(
                    task_id=task_id,
                    consensus_date=row.get('consensus_date', datetime.now().isoformat()),
                    database_routing_correct=self._parse_bool(row.get('database_routing_correct')),
                    feasibility_correct=self._parse_bool(row.get('feasibility_correct')),
                    plan_quality=row.get('plan_quality', 'good'),
                    variable_codes_correct=self._parse_bool(row.get('variable_codes_correct')),
                    overall_acceptable=self._parse_bool(row.get('overall_acceptable')),
                    notes=row.get('notes', ''),
                    disagreements_resolved=row.get('disagreements_resolved', '').split('|') if row.get('disagreements_resolved') else []
                )

                self.consensus_ratings[task_id] = consensus
                imported_count += 1

        self.status = AdjudicationStatus.COMPLETE
        return imported_count

    def generate_adjudication_report(self) -> Dict[str, Any]:
        """
        Generate comprehensive adjudication report.

        Returns:
            Dictionary with adjudication status, statistics, and recommendations
        """
        validation = self.validate_ratings()
        reliability = self.compute_inter_rater_reliability()

        return {
            'status': self.status.value,
            'validation': validation,
            'inter_rater_reliability': reliability,
            'raters': {
                rater_id: {
                    'name': rater.name,
                    'credentials': rater.credentials,
                    'affiliation': rater.affiliation
                }
                for rater_id, rater in self.raters.items()
            },
            'tasks_with_consensus': len(self.consensus_ratings),
            'recommendations': self._generate_recommendations()
        }

    def _load_benchmark_tasks(self) -> List[Dict[str, Any]]:
        """Load tasks from benchmark file."""
        try:
            import yaml
            with open(self.benchmark_path) as f:
                data = yaml.safe_load(f)
                return data.get('tasks', [])
        except ImportError:
            raise ImportError("PyYAML required to load benchmark tasks")

    def _parse_bool(self, value: Optional[str]) -> Optional[bool]:
        """Parse boolean value from string."""
        if value is None or value == '':
            return None

        value_lower = value.lower().strip()
        if value_lower in ['true', 'yes', '1', 'correct']:
            return True
        elif value_lower in ['false', 'no', '0', 'incorrect']:
            return False
        else:
            return None

    def _generate_recommendations(self) -> List[str]:
        """Generate recommendations based on adjudication status."""
        recommendations = []

        if self.status == AdjudicationStatus.NOT_STARTED:
            recommendations.append("Begin by creating rating templates for expert raters")

        elif self.status == AdjudicationStatus.TEMPLATES_CREATED:
            recommendations.append("Distribute rating templates to expert raters")
            recommendations.append("Schedule rating completion deadline")

        elif self.status == AdjudicationStatus.RATINGS_IN_PROGRESS:
            validation = self.validate_ratings()
            if not validation['valid']:
                recommendations.append("Address incomplete ratings before consensus meeting")
            else:
                recommendations.append("Proceed to consensus meeting once all ratings are complete")

        elif self.status == AdjudicationStatus.CONSENSUS_IN_PROGRESS:
            recommendations.append("Complete consensus meeting and document final ratings")

        elif self.status == AdjudicationStatus.COMPLETE:
            recommendations.append("Adjudication complete - consensus ratings ready for use")
            recommendations.append("Update benchmark status to 'expert_validated'")

        return recommendations


def create_adjudication_manager(benchmark_path: str, output_dir: str) -> AdjudicationManager:
    """
    Create adjudication manager instance.

    Args:
        benchmark_path: Path to benchmark YAML file
        output_dir: Directory for adjudication outputs

    Returns:
        Configured AdjudicationManager
    """
    return AdjudicationManager(
        benchmark_path=Path(benchmark_path),
        output_dir=Path(output_dir)
    )
