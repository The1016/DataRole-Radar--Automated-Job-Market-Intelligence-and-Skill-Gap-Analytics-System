from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.transform.role_taxonomy import (
    apply_role_classification,
    classify_role,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]

STAGING_FILE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "himalayas_jobs_staging.csv"
)

OVERRIDE_FILE = (
    PROJECT_ROOT
    / "data"
    / "reference"
    / "role_classification_overrides.csv"
)


@pytest.fixture
def staging_jobs() -> pd.DataFrame:
    """Load the current Himalayas staging dataset."""

    if not STAGING_FILE.exists():
        pytest.fail(
            f"Staging file does not exist: {STAGING_FILE}"
        )

    return pd.read_csv(
        STAGING_FILE,
        dtype={
            "source_job_id": "string",
        },
    )


@pytest.fixture
def verified_overrides() -> pd.DataFrame:
    """Load the verified human labels."""

    if not OVERRIDE_FILE.exists():
        pytest.fail(
            f"Override file does not exist: {OVERRIDE_FILE}"
        )

    overrides = pd.read_csv(
        OVERRIDE_FILE,
        dtype={
            "source_job_id": "string",
        },
    )

    if "source" not in overrides.columns:
        overrides["source"] = "Himalayas"

    return overrides


def test_basic_automated_title_rules() -> None:
    """Check several unambiguous title classifications."""

    cases = {
        "Senior Data Analyst": "Data Analyst",
        "Lead Data Engineer": "Data Engineer",
        "Senior Data Scientist": "Data Scientist",
        "Analytics Engineer": "Analytics Engineer",
        "Power BI Developer": "BI Developer",
        "Business Intelligence Analyst": "BI Analyst",
        "Business Analyst": "Business Analyst",
        "Analytics Director": "Analytics Manager",
        "Backend Software Engineer": "Non-target Role",
    }

    for job_title, expected_role in cases.items():
        actual_role = classify_role(job_title)

        assert actual_role == expected_role, (
            f"Title '{job_title}' was classified as "
            f"'{actual_role}' instead of '{expected_role}'."
        )


def test_verified_overrides_have_required_values(
    verified_overrides: pd.DataFrame,
) -> None:
    """Ensure every verified label has the required identifying fields."""

    required_columns = [
        "source",
        "source_job_id",
        "job_title_raw",
        "correct_role_family",
    ]

    problems = []

    for column in required_columns:
        values = (
            verified_overrides[column]
            .fillna("")
            .astype(str)
            .str.strip()
        )

        missing_count = values.eq("").sum()

        if missing_count:
            problems.append(
                f"{column}: {missing_count} blank"
            )

    assert not problems, (
        "Incomplete verified override records: "
        + "; ".join(problems)
    )


def test_manual_overrides_produce_verified_roles(
    staging_jobs: pd.DataFrame,
    verified_overrides: pd.DataFrame,
) -> None:
    """Ensure final classifications match all verified labels."""

    classification_input = verified_overrides[
        [
            "source",
            "source_job_id",
            "job_title_raw",
        ]
    ].copy()

    classified = apply_role_classification(
        dataframe=classification_input,
        override_file=OVERRIDE_FILE,
    )

    expected = verified_overrides[
        [
            "source",
            "source_job_id",
            "correct_role_family",
        ]
    ].copy()

    expected["source"] = (
        expected["source"]
        .astype(str)
        .str.strip()
    )

    expected["source_job_id"] = (
        expected["source_job_id"]
        .astype("string")
        .str.strip()
    )

    actual = classified.merge(
        expected,
        how="inner",
        on=[
            "source",
            "source_job_id",
        ],
        validate="one_to_one",
    )

    mismatches = actual[
        actual["role_family"]
        != actual["correct_role_family"]
    ]

    assert mismatches.empty, (
        "Final classifications do not match verified labels:\n"
        + mismatches[
            [
                "source_job_id",
                "job_title_raw",
                "role_family",
                "correct_role_family",
            ]
        ].to_string(index=False)
    )


def test_verified_non_target_roles_are_excluded(
    staging_jobs: pd.DataFrame,
    verified_overrides: pd.DataFrame,
) -> None:
    """Ensure verified non-target jobs receive a False target flag."""

    non_target_overrides = verified_overrides[
        verified_overrides["correct_role_family"]
        == "Non-target Role"
    ]

    if non_target_overrides.empty:
        pytest.skip(
            "No verified non-target records are available."
        )

    classification_input = verified_overrides[
        [
            "source",
            "source_job_id",
            "job_title_raw",
        ]
    ].copy()

    classified = apply_role_classification(
        dataframe=classification_input,
        override_file=OVERRIDE_FILE,
    )

    checked = classified.merge(
        non_target_overrides[
            [
                "source",
                "source_job_id",
            ]
        ],
        how="inner",
        on=[
            "source",
            "source_job_id",
        ],
        validate="one_to_one",
    )

    assert not checked[
        "is_target_data_role"
    ].any(), (
        "A verified non-target job was still marked "
        "as a target role."
    )


def test_override_keys_are_unique(
    verified_overrides: pd.DataFrame,
) -> None:
    """Ensure one verified classification exists per source job."""

    duplicate_mask = verified_overrides.duplicated(
        subset=[
            "source",
            "source_job_id",
        ],
        keep=False,
    )

    duplicates = verified_overrides[
        duplicate_mask
    ]

    assert duplicates.empty, (
        "Duplicate override keys were found:\n"
        + duplicates[
            [
                "source",
                "source_job_id",
                "job_title_raw",
            ]
        ].to_string(index=False)
    )