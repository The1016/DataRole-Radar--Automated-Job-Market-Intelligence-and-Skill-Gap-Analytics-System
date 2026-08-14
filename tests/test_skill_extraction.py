from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.transform.extract_job_skills import (
    apply_skill_overrides,
    compile_skill_patterns,
    extract_job_skill_relationships,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]

PROCESSED_DIRECTORY = (
    PROJECT_ROOT
    / "data"
    / "processed"
)

REFERENCE_DIRECTORY = (
    PROJECT_ROOT
    / "data"
    / "reference"
)

JOB_SKILLS_FILE = (
    PROCESSED_DIRECTORY
    / "job_skills.csv"
)

SKILLS_FILE = (
    PROCESSED_DIRECTORY
    / "skills.csv"
)

TARGET_JOBS_FILE = (
    PROCESSED_DIRECTORY
    / "master_target_roles.csv"
)

SKILL_OVERRIDES_FILE = (
    REFERENCE_DIRECTORY
    / "skill_match_overrides.csv"
)


def build_skill_dictionary(
    rows: list[dict[str, str]],
) -> pd.DataFrame:
    """Create a small skill dictionary for unit tests."""

    return pd.DataFrame(
        rows,
        columns=[
            "skill_key",
            "skill_name",
            "skill_category",
            "aliases",
        ],
    )


def build_test_job(
    description: str,
    title: str = "Test Data Role",
    tags: str = "",
    source_record_key: str = "test::1",
) -> pd.DataFrame:
    """Create one synthetic job for extractor tests."""

    return pd.DataFrame(
        [
            {
                "source_record_key": source_record_key,
                "source": "Test",
                "source_job_id": "1",
                "job_title_raw": title,
                "company_name": "Test Company",
                "role_family": "Data Analyst",
                "tags": tags,
                "description_text": description,
                "publication_date": "2026-08-01",
            }
        ]
    )


def extract_test_skills(
    jobs: pd.DataFrame,
    skills: pd.DataFrame,
) -> pd.DataFrame:
    """Run the production skill extractor on test data."""

    patterns = compile_skill_patterns(
        skills
    )

    return extract_job_skill_relationships(
        jobs=jobs,
        skills=skills,
        compiled_patterns=patterns,
    )


def test_api_is_not_detected_inside_url() -> None:
    """URLs must not create API false positives."""

    skills = build_skill_dictionary(
        [
            {
                "skill_key": "apis",
                "skill_name": "APIs",
                "skill_category": "Data Engineering",
                "aliases": "API|APIs|REST API|RESTful API",
            }
        ]
    )

    jobs = build_test_job(
        description=(
            "Read the Spark documentation at "
            "https://spark.apache.org/docs/latest/api/python/"
        )
    )

    with pytest.raises(
        ValueError,
        match="No skills were detected",
    ):
        extract_test_skills(
            jobs=jobs,
            skills=skills,
        )


def test_real_api_requirement_is_detected() -> None:
    """Explicit API requirements should still match."""

    skills = build_skill_dictionary(
        [
            {
                "skill_key": "apis",
                "skill_name": "APIs",
                "skill_category": "Data Engineering",
                "aliases": "API|APIs|REST API|RESTful API",
            }
        ]
    )

    jobs = build_test_job(
        description=(
            "Build and maintain REST APIs "
            "for internal data products."
        )
    )

    result = extract_test_skills(
        jobs=jobs,
        skills=skills,
    )

    assert set(
        result["skill_key"]
    ) == {"apis"}


def test_statistics_degree_only_is_not_detected() -> None:
    """Statistics as a degree field is not a skill requirement."""

    skills = build_skill_dictionary(
        [
            {
                "skill_key": "statistics",
                "skill_name": "Statistics",
                "skill_category": "Analytics Method",
                "aliases": (
                    "statistics|statistical analysis|"
                    "statistical modeling|"
                    "hypothesis testing"
                ),
            }
        ]
    )

    jobs = build_test_job(
        description=(
            "Bachelor's degree in Data Science, "
            "Statistics, Computer Science, "
            "Mathematics, or a related field."
        )
    )

    with pytest.raises(
        ValueError,
        match="No skills were detected",
    ):
        extract_test_skills(
            jobs=jobs,
            skills=skills,
        )


def test_applied_statistics_is_detected() -> None:
    """Applied statistical work must remain detectable."""

    skills = build_skill_dictionary(
        [
            {
                "skill_key": "statistics",
                "skill_name": "Statistics",
                "skill_category": "Analytics Method",
                "aliases": (
                    "statistics|statistical analysis|"
                    "statistical modeling|"
                    "hypothesis testing"
                ),
            }
        ]
    )

    jobs = build_test_job(
        description=(
            "Perform statistical analysis and "
            "hypothesis testing to evaluate results."
        )
    )

    result = extract_test_skills(
        jobs=jobs,
        skills=skills,
    )

    assert set(
        result["skill_key"]
    ) == {"statistics"}


def test_explicit_ab_testing_is_detected() -> None:
    """Explicit A/B testing should match."""

    skills = build_skill_dictionary(
        [
            {
                "skill_key": "ab_testing",
                "skill_name": "A/B Testing",
                "skill_category": "Analytics Method",
                "aliases": (
                    "A/B testing|AB testing|"
                    "A B testing|controlled experiment|"
                    "controlled experiments"
                ),
            }
        ]
    )

    jobs = build_test_job(
        description=(
            "Design and analyze A/B testing "
            "for product experiments."
        )
    )

    result = extract_test_skills(
        jobs=jobs,
        skills=skills,
    )

    assert set(
        result["skill_key"]
    ) == {"ab_testing"}


def test_generic_experimentation_does_not_mean_ab_testing() -> None:
    """Generic experimentation must not imply A/B testing."""

    skills = build_skill_dictionary(
        [
            {
                "skill_key": "ab_testing",
                "skill_name": "A/B Testing",
                "skill_category": "Analytics Method",
                "aliases": (
                    "A/B testing|AB testing|"
                    "A B testing|controlled experiment|"
                    "controlled experiments"
                ),
            }
        ]
    )

    jobs = build_test_job(
        description=(
            "Support experimentation initiatives "
            "across the analytics organization."
        )
    )

    with pytest.raises(
        ValueError,
        match="No skills were detected",
    ):
        extract_test_skills(
            jobs=jobs,
            skills=skills,
        )


def test_manual_skill_override_removes_false_positive() -> None:
    """Verified manual exclusions must remove relationships."""

    job_skills = pd.DataFrame(
        [
            {
                "source_record_key": "remotive::2091047",
                "skill_key": "machine_learning",
                "evidence_source": "description_text",
                "matched_aliases": "machine learning",
                "evidence_field_count": 1,
            },
            {
                "source_record_key": "test::2",
                "skill_key": "machine_learning",
                "evidence_source": "description_text",
                "matched_aliases": "machine learning",
                "evidence_field_count": 1,
            },
        ]
    )

    overrides = pd.DataFrame(
        [
            {
                "source_record_key": "remotive::2091047",
                "skill_key": "machine_learning",
                "override_action": "exclude",
                "reason": "Verified false positive",
            }
        ]
    )

    result, removed_count = (
        apply_skill_overrides(
            job_skills=job_skills,
            overrides=overrides,
        )
    )

    assert removed_count == 1

    assert (
        "remotive::2091047"
        not in set(
            result[
                "source_record_key"
            ]
        )
    )

    assert len(result) == 1


def test_job_skill_relationships_are_unique() -> None:
    """One job must have at most one row per skill."""

    job_skills = pd.read_csv(
        JOB_SKILLS_FILE,
        dtype={
            "source_record_key": "string",
            "skill_key": "string",
        },
    )

    duplicate_mask = (
        job_skills.duplicated(
            subset=[
                "source_record_key",
                "skill_key",
            ],
            keep=False,
        )
    )

    assert not duplicate_mask.any(), (
        "Duplicate job-skill relationships found:\n"
        + job_skills.loc[
            duplicate_mask,
            [
                "source_record_key",
                "skill_key",
            ],
        ].to_string(index=False)
    )


def test_every_job_skill_uses_valid_job_and_skill_keys() -> None:
    """Bridge-table foreign keys must resolve."""

    job_skills = pd.read_csv(
        JOB_SKILLS_FILE,
        dtype={
            "source_record_key": "string",
            "skill_key": "string",
        },
    )

    jobs = pd.read_csv(
        TARGET_JOBS_FILE,
        dtype={
            "source_record_key": "string",
        },
    )

    skills = pd.read_csv(
        SKILLS_FILE,
        dtype={
            "skill_key": "string",
        },
    )

    valid_job_keys = set(
        jobs[
            "source_record_key"
        ]
        .astype("string")
        .str.strip()
    )

    valid_skill_keys = set(
        skills[
            "skill_key"
        ]
        .astype("string")
        .str.strip()
    )

    invalid_job_keys = (
        set(
            job_skills[
                "source_record_key"
            ]
        )
        - valid_job_keys
    )

    invalid_skill_keys = (
        set(
            job_skills[
                "skill_key"
            ]
        )
        - valid_skill_keys
    )

    assert not invalid_job_keys, (
        "Unknown source_record_key values found: "
        f"{sorted(invalid_job_keys)}"
    )

    assert not invalid_skill_keys, (
        "Unknown skill_key values found: "
        f"{sorted(invalid_skill_keys)}"
    )


def test_verified_skill_override_is_absent_from_output() -> None:
    """The audited TELUS ML false positive must stay removed."""

    job_skills = pd.read_csv(
        JOB_SKILLS_FILE,
        dtype={
            "source_record_key": "string",
            "skill_key": "string",
        },
    )

    forbidden_match = (
        (
            job_skills[
                "source_record_key"
            ]
            == "remotive::2091047"
        )
        & (
            job_skills[
                "skill_key"
            ]
            == "machine_learning"
        )
    )

    assert not forbidden_match.any(), (
        "Verified false-positive Machine Learning "
        "relationship has reappeared."
    )


def test_skill_override_file_has_unique_keys() -> None:
    """Manual skill exceptions must be uniquely identified."""

    overrides = pd.read_csv(
        SKILL_OVERRIDES_FILE,
        dtype={
            "source_record_key": "string",
            "skill_key": "string",
        },
    )

    duplicate_mask = overrides.duplicated(
        subset=[
            "source_record_key",
            "skill_key",
        ],
        keep=False,
    )

    assert not duplicate_mask.any(), (
        "Duplicate skill override keys found:\n"
        + overrides.loc[
            duplicate_mask,
            [
                "source_record_key",
                "skill_key",
            ],
        ].to_string(index=False)
    )