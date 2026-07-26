from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]

PROCESSED_DIRECTORY = (
    PROJECT_ROOT
    / "data"
    / "processed"
)

REMOTIVE_FILE = (
    PROCESSED_DIRECTORY
    / "remotive_jobs_staging.csv"
)

HIMALAYAS_FILE = (
    PROCESSED_DIRECTORY
    / "himalayas_jobs_staging.csv"
)

MASTER_FILE = (
    PROCESSED_DIRECTORY
    / "master_jobs_staging.csv"
)

MASTER_TARGET_FILE = (
    PROCESSED_DIRECTORY
    / "master_target_roles.csv"
)


ALLOWED_ROLE_FAMILIES = {
    "Data Analyst",
    "BI Analyst",
    "BI Developer",
    "Business Analyst",
    "Operations Analyst",
    "Reporting Analyst",
    "Insights Analyst",
    "Product Analyst",
    "Marketing Analyst",
    "Decision Science",
    "Data Scientist",
    "Data Engineer",
    "Analytics Engineer",
    "Machine Learning",
    "Analytics Manager",
    "Other Analytics",
    "Non-target Role",
}


def read_required_csv(
    file_path: Path,
) -> pd.DataFrame:
    """Read a required test dataset."""

    if not file_path.exists():
        pytest.fail(
            f"Required file does not exist: {file_path}"
        )

    return pd.read_csv(
        file_path,
        dtype={
            "source_job_id": "string",
            "source_record_key": "string",
        },
    )


def parse_boolean_series(
    series: pd.Series,
) -> pd.Series:
    """Convert CSV boolean values into real booleans."""

    normalized = (
        series
        .astype("string")
        .str.strip()
        .str.lower()
    )

    mapping = {
        "true": True,
        "false": False,
        "1": True,
        "0": False,
    }

    parsed = normalized.map(mapping)

    invalid_mask = parsed.isna()

    assert not invalid_mask.any(), (
        "Invalid Boolean values found: "
        f"{sorted(normalized[invalid_mask].unique())}"
    )

    return parsed.astype(bool)


@pytest.fixture
def remotive_jobs() -> pd.DataFrame:
    """Load the Remotive staging table."""

    return read_required_csv(
        REMOTIVE_FILE
    )


@pytest.fixture
def himalayas_jobs() -> pd.DataFrame:
    """Load the Himalayas staging table."""

    return read_required_csv(
        HIMALAYAS_FILE
    )

@pytest.fixture
def master_target_jobs() -> pd.DataFrame:
    """Load the target-only master output."""

    return read_required_csv(
        MASTER_TARGET_FILE
    )


@pytest.fixture
def master_jobs() -> pd.DataFrame:
    """Load the integrated master staging table."""

    return read_required_csv(
        MASTER_FILE
    )


def test_master_record_count_matches_sources(
    remotive_jobs: pd.DataFrame,
    himalayas_jobs: pd.DataFrame,
    master_jobs: pd.DataFrame,
) -> None:
    """Ensure integration does not lose or create records."""

    expected_count = (
        len(remotive_jobs)
        + len(himalayas_jobs)
    )

    assert len(master_jobs) == expected_count, (
        f"Expected {expected_count} master records, "
        f"but found {len(master_jobs)}."
    )


def test_source_record_keys_are_unique(
    master_jobs: pd.DataFrame,
) -> None:
    """Ensure every source record has one unique key."""

    keys = (
        master_jobs["source_record_key"]
        .astype("string")
        .str.strip()
    )

    assert not keys.isna().any(), (
        "Missing source_record_key values were found."
    )

    assert not keys.eq("").any(), (
        "Blank source_record_key values were found."
    )

    duplicate_mask = keys.duplicated(
        keep=False
    )

    assert not duplicate_mask.any(), (
        "Duplicate source_record_key values found:\n"
        + master_jobs.loc[
            duplicate_mask,
            [
                "source_record_key",
                "job_title_raw",
            ],
        ].to_string(index=False)
    )


def test_source_record_keys_are_constructed_correctly(
    master_jobs: pd.DataFrame,
) -> None:
    """Check the source-qualified business-key format."""

    expected_keys = (
        master_jobs["source"]
        .astype(str)
        .str.strip()
        .str.lower()
        + "::"
        + master_jobs["source_job_id"]
        .astype("string")
        .str.strip()
    )

    actual_keys = (
        master_jobs["source_record_key"]
        .astype("string")
        .str.strip()
    )

    mismatch_mask = (
        actual_keys != expected_keys
    )

    assert not mismatch_mask.any(), (
        "Incorrect source_record_key values found:\n"
        + master_jobs.loc[
            mismatch_mask,
            [
                "source",
                "source_job_id",
                "source_record_key",
            ],
        ].to_string(index=False)
    )


def test_target_flag_matches_final_role_family(
    master_jobs: pd.DataFrame,
) -> None:
    """Ensure target flags agree with final classifications."""

    actual_target_flags = parse_boolean_series(
        master_jobs[
            "is_target_data_role"
        ]
    )

    expected_target_flags = (
        master_jobs["role_family"]
        .astype(str)
        .str.strip()
        .ne("Non-target Role")
    )

    mismatch_mask = (
        actual_target_flags
        != expected_target_flags
    )

    assert not mismatch_mask.any(), (
        "Target flags disagree with role families:\n"
        + master_jobs.loc[
            mismatch_mask,
            [
                "job_title_raw",
                "role_family",
                "is_target_data_role",
            ],
        ].to_string(index=False)
    )


def test_role_families_are_valid(
    master_jobs: pd.DataFrame,
) -> None:
    """Ensure every job uses an approved role family."""

    actual_roles = set(
        master_jobs["role_family"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    invalid_roles = (
        actual_roles
        - ALLOWED_ROLE_FAMILIES
    )

    assert not invalid_roles, (
        "Invalid role families found: "
        f"{sorted(invalid_roles)}"
    )


def test_expected_sources_are_present(
    master_jobs: pd.DataFrame,
) -> None:
    """Ensure both configured API sources were integrated."""

    actual_sources = set(
        master_jobs["source"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    expected_sources = {
        "Remotive",
        "Himalayas",
    }

    assert actual_sources == expected_sources, (
        f"Expected sources {sorted(expected_sources)}, "
        f"but found {sorted(actual_sources)}."
    )


def test_critical_fields_are_complete(
    master_jobs: pd.DataFrame,
) -> None:
    """Ensure essential business fields are populated."""

    critical_text_columns = [
        "source",
        "source_job_id",
        "source_record_key",
        "job_title_raw",
        "company_name",
        "role_family",
        "job_url",
        "description_text",
    ]

    problems = []

    for column in critical_text_columns:
        values = (
            master_jobs[column]
            .fillna("")
            .astype(str)
            .str.strip()
        )

        missing_count = values.eq("").sum()

        if missing_count:
            problems.append(
                f"{column}: {missing_count} missing"
            )

    publication_dates = pd.to_datetime(
        master_jobs["publication_date"],
        errors="coerce",
        utc=True,
        format="mixed",
    )

    missing_dates = publication_dates.isna().sum()

    if missing_dates:
        problems.append(
            f"publication_date: "
            f"{missing_dates} missing"
        )

    assert not problems, (
        "Critical-field completeness failures: "
        + "; ".join(problems)
    )


def test_target_output_matches_master_subset(
    master_jobs: pd.DataFrame,
    master_target_jobs: pd.DataFrame,
) -> None:
    """Ensure the target output exactly matches the master target subset."""

    target_flags = parse_boolean_series(
        master_jobs["is_target_data_role"]
    )

    expected_keys = set(
        master_jobs.loc[
            target_flags,
            "source_record_key",
        ]
        .astype("string")
        .str.strip()
    )

    actual_keys = set(
        master_target_jobs[
            "source_record_key"
        ]
        .astype("string")
        .str.strip()
    )

    assert actual_keys == expected_keys, (
        "master_target_roles.csv does not match "
        "the target rows in master_jobs_staging.csv."
    )