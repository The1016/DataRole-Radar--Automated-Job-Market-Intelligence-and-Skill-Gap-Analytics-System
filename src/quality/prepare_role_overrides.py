from __future__ import annotations

from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]

INPUT_FILE = (
    PROJECT_ROOT
    / "reports"
    / "role_classification_audit.csv"
)

OUTPUT_FILE = (
    PROJECT_ROOT
    / "data"
    / "reference"
    / "role_classification_overrides.csv"
)


ALLOWED_DECISIONS = {
    "Correct",
    "False Positive",
    "False Negative",
    "Incorrect Role Family",
    "Needs New Category",
    "Unverified",
}


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


DECISION_ALIASES = {
    "Expired link": "Unverified",
}


ROLE_ALIASES = {
    "Analytics engineer": "Analytics Engineer",
}


def clean_text_column(
    dataframe: pd.DataFrame,
    column: str,
) -> None:
    """Strip spaces and safely convert missing text to blanks."""

    dataframe[column] = (
        dataframe[column]
        .fillna("")
        .astype(str)
        .str.strip()
    )


def main() -> None:
    """Validate the manual audit and create the override table."""

    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Audit file not found: {INPUT_FILE}"
        )

    audit = pd.read_csv(INPUT_FILE)

    required_columns = [
        "source_job_id",
        "job_title_raw",
        "manual_decision",
        "correct_role_family",
        "review_notes",
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in audit.columns
    ]

    if missing_columns:
        raise ValueError(
            f"Audit file is missing columns: "
            f"{missing_columns}"
        )

    text_columns = [
        "source_job_id",
        "job_title_raw",
        "manual_decision",
        "correct_role_family",
        "review_notes",
    ]

    for column in text_columns:
        clean_text_column(
            dataframe=audit,
            column=column,
        )

    audit["manual_decision"] = (
        audit["manual_decision"]
        .replace(DECISION_ALIASES)
    )

    audit["correct_role_family"] = (
        audit["correct_role_family"]
        .replace(ROLE_ALIASES)
    )

    invalid_decisions = sorted(
        set(audit["manual_decision"])
        - ALLOWED_DECISIONS
    )

    if invalid_decisions:
        raise ValueError(
            "Invalid manual decisions found: "
            f"{invalid_decisions}"
        )

    verified_mask = (
        audit["manual_decision"]
        != "Unverified"
    )

    verified_audit = audit[
        verified_mask
    ].copy()

    blank_role_rows = verified_audit[
        verified_audit[
            "correct_role_family"
        ].eq("")
    ]

    if not blank_role_rows.empty:
        titles = blank_role_rows[
            "job_title_raw"
        ].tolist()

        raise ValueError(
            "Verified rows are missing a correct "
            f"role family: {titles}"
        )

    invalid_roles = sorted(
        set(
            verified_audit[
                "correct_role_family"
            ]
        )
        - ALLOWED_ROLE_FAMILIES
    )

    if invalid_roles:
        raise ValueError(
            "Invalid role families found: "
            f"{invalid_roles}"
        )

    duplicate_ids = verified_audit[
        "source_job_id"
    ].duplicated(
        keep=False
    )

    if duplicate_ids.any():
        duplicate_values = (
            verified_audit.loc[
                duplicate_ids,
                "source_job_id",
            ]
            .unique()
            .tolist()
        )

        raise ValueError(
            "Duplicate reviewed job IDs found: "
            f"{duplicate_values}"
        )

    verified_audit[
        "is_target_data_role_override"
    ] = (
        verified_audit[
            "correct_role_family"
        ]
        != "Non-target Role"
    )

    override_columns = [
        "source_job_id",
        "job_title_raw",
        "manual_decision",
        "correct_role_family",
        "is_target_data_role_override",
        "review_notes",
    ]

    overrides = (
        verified_audit[
            override_columns
        ]
        .sort_values(
            by=[
                "correct_role_family",
                "job_title_raw",
            ]
        )
        .reset_index(drop=True)
    )

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    overrides.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    print("ROLE OVERRIDE PREPARATION")
    print("=" * 60)

    print(
        f"Audit rows received: "
        f"{len(audit)}"
    )

    print(
        f"Verified override rows: "
        f"{len(overrides)}"
    )

    print(
        f"Unverified rows excluded: "
        f"{(~verified_mask).sum()}"
    )

    print(
        f"Target-role overrides: "
        f"{overrides['is_target_data_role_override'].sum()}"
    )

    print(
        f"Non-target overrides: "
        f"{(
            ~overrides[
                'is_target_data_role_override'
            ]
        ).sum()}"
    )

    print("\nOVERRIDES BY ROLE FAMILY")
    print("-" * 60)

    print(
        overrides[
            "correct_role_family"
        ]
        .value_counts()
        .to_string()
    )

    print("\nFILE CREATED")
    print("-" * 60)
    print(OUTPUT_FILE)


if __name__ == "__main__":
    main()