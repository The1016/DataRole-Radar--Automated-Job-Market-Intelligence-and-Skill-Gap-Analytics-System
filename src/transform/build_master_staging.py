from __future__ import annotations

from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]

PROCESSED_DATA_DIRECTORY = (
    PROJECT_ROOT
    / "data"
    / "processed"
)

REPORTS_DIRECTORY = (
    PROJECT_ROOT
    / "reports"
)

REMOTIVE_INPUT_FILE = (
    PROCESSED_DATA_DIRECTORY
    / "remotive_jobs_staging.csv"
)

HIMALAYAS_INPUT_FILE = (
    PROCESSED_DATA_DIRECTORY
    / "himalayas_jobs_staging.csv"
)

MASTER_OUTPUT_FILE = (
    PROCESSED_DATA_DIRECTORY
    / "master_jobs_staging.csv"
)

TARGET_OUTPUT_FILE = (
    PROCESSED_DATA_DIRECTORY
    / "master_target_roles.csv"
)

DUPLICATE_REPORT_FILE = (
    REPORTS_DIRECTORY
    / "master_duplicate_candidates.csv"
)

RECONCILIATION_REPORT_FILE = (
    REPORTS_DIRECTORY
    / "master_source_reconciliation.csv"
)



BASE_REQUIRED_COLUMNS = {
    "source",
    "source_job_id",
    "job_fingerprint",
    "job_title_raw",
    "automated_role_family",
    "role_family",
    "is_target_data_role",
    "classification_method",
    "role_override_applied",
    "override_decision",
    "company_name",
    "company_logo_url",
    "category",
    "tags",
    "job_type",
    "publication_date",
    "location_raw",
    "salary_raw",
    "description_text",
    "job_url",
    "collected_at",
}


MASTER_COLUMNS = [
    "source_record_key",
    "source",
    "source_job_id",
    "job_fingerprint",
    "job_title_raw",
    "automated_role_family",
    "role_family",
    "is_target_data_role",
    "classification_method",
    "role_override_applied",
    "override_decision",
    "company_name",
    "company_logo_url",
    "category",
    "tags",
    "job_type",
    "seniority_raw",
    "publication_date",
    "expiry_date",
    "location_raw",
    "timezone_raw",
    "is_worldwide",
    "salary_min",
    "salary_max",
    "salary_currency",
    "salary_period",
    "salary_raw",
    "description_text",
    "job_url",
    "search_queries",
    "collected_at",
]


DATE_COLUMNS = [
    "publication_date",
    "expiry_date",
    "collected_at",
]


BOOLEAN_COLUMNS = [
    "is_target_data_role",
    "role_override_applied",
    "is_worldwide",
]


def clean_text_series(
    series: pd.Series,
) -> pd.Series:
    """Standardize text while preserving blank values."""

    return (
        series
        .fillna("")
        .astype(str)
        .str.strip()
    )


def convert_nullable_boolean(
    series: pd.Series,
) -> pd.Series:
    """Convert common text representations into nullable booleans."""

    normalized = (
        series
        .astype("string")
        .str.strip()
        .str.lower()
    )

    boolean_mapping = {
        "true": True,
        "false": False,
        "1": True,
        "0": False,
        "yes": True,
        "no": False,
    }

    return (
        normalized
        .map(boolean_mapping)
        .astype("boolean")
    )


def validate_source_file(
    dataframe: pd.DataFrame,
    expected_source: str,
    file_path: Path,
) -> None:
    """Validate the minimum schema and source identity."""

    missing_columns = (
        BASE_REQUIRED_COLUMNS
        - set(dataframe.columns)
    )

    if missing_columns:
        raise ValueError(
            f"{file_path.name} is missing columns: "
            f"{sorted(missing_columns)}"
        )

    source_values = set(
        clean_text_series(
            dataframe["source"]
        )
    )

    if source_values != {expected_source}:
        raise ValueError(
            f"{file_path.name} contains unexpected "
            f"source values: {sorted(source_values)}"
        )


def load_and_harmonize_source(
    file_path: Path,
    expected_source: str,
) -> pd.DataFrame:
    """Load one staging file and conform it to the master schema."""

    if not file_path.exists():
        raise FileNotFoundError(
            f"Source staging file not found: "
            f"{file_path}"
        )

    dataframe = pd.read_csv(
        file_path,
        dtype={
            "source_job_id": "string",
        },
    )

    validate_source_file(
        dataframe=dataframe,
        expected_source=expected_source,
        file_path=file_path,
    )

    harmonized = dataframe.copy()

    harmonized["source"] = clean_text_series(
        harmonized["source"]
    )

    harmonized["source_job_id"] = (
        harmonized["source_job_id"]
        .astype("string")
        .str.strip()
    )

    missing_source_ids = (
        harmonized["source_job_id"].isna()
        | harmonized["source_job_id"].eq("")
    )

    if missing_source_ids.any():
        raise ValueError(
            f"{expected_source} contains jobs "
            "without source_job_id values."
        )

    # These columns exist in the master schema but may not
    # be available from every API source.
    for column in MASTER_COLUMNS:
        if (
            column not in harmonized.columns
            and column != "source_record_key"
        ):
            harmonized[column] = pd.NA

    harmonized["source_record_key"] = (
        harmonized["source"]
        .str.lower()
        + "::"
        + harmonized["source_job_id"]
    )

    for column in BOOLEAN_COLUMNS:
        harmonized[column] = (
            convert_nullable_boolean(
                harmonized[column]
            )
        )

    for column in DATE_COLUMNS:
        harmonized[column] = pd.to_datetime(
            harmonized[column],
            errors="coerce",
            utc=True,
        )

    harmonized["salary_min"] = pd.to_numeric(
        harmonized["salary_min"],
        errors="coerce",
    )

    harmonized["salary_max"] = pd.to_numeric(
        harmonized["salary_max"],
        errors="coerce",
    )

    return harmonized[MASTER_COLUMNS]


def validate_master_keys(
    master_jobs: pd.DataFrame,
) -> None:
    """Ensure every source record has one unique master key."""

    duplicate_keys = master_jobs.duplicated(
        subset=["source_record_key"],
        keep=False,
    )

    if duplicate_keys.any():
        duplicate_rows = master_jobs.loc[
            duplicate_keys,
            [
                "source_record_key",
                "source",
                "source_job_id",
                "job_title_raw",
            ],
        ]

        raise ValueError(
            "Duplicate source record keys found:\n"
            + duplicate_rows.to_string(
                index=False
            )
        )


def build_duplicate_report(
    master_jobs: pd.DataFrame,
) -> pd.DataFrame:
    """Create a review report for repeated job fingerprints."""

    valid_fingerprint_mask = (
        master_jobs["job_fingerprint"]
        .fillna("")
        .astype(str)
        .str.strip()
        .ne("")
    )

    fingerprint_summary = (
        master_jobs[
            valid_fingerprint_mask
        ]
        .groupby(
            "job_fingerprint",
            as_index=False,
        )
        .agg(
            record_count=(
                "source_record_key",
                "size",
            ),
            source_count=(
                "source",
                "nunique",
            ),
        )
    )

    duplicate_groups = fingerprint_summary[
        fingerprint_summary["record_count"]
        > 1
    ].copy()

    if duplicate_groups.empty:
        return pd.DataFrame(
            columns=[
                "duplicate_scope",
                "job_fingerprint",
                "record_count",
                "source_count",
                "source",
                "source_job_id",
                "company_name",
                "job_title_raw",
                "location_raw",
                "publication_date",
                "job_url",
            ]
        )

    duplicate_candidates = master_jobs.merge(
        duplicate_groups,
        how="inner",
        on="job_fingerprint",
        validate="many_to_one",
    )

    duplicate_candidates[
        "duplicate_scope"
    ] = duplicate_candidates[
        "source_count"
    ].apply(
        lambda value: (
            "Cross-source"
            if value > 1
            else "Within-source"
        )
    )

    output_columns = [
        "duplicate_scope",
        "job_fingerprint",
        "record_count",
        "source_count",
        "source",
        "source_job_id",
        "company_name",
        "job_title_raw",
        "location_raw",
        "publication_date",
        "job_url",
    ]

    return (
        duplicate_candidates[
            output_columns
        ]
        .sort_values(
            by=[
                "duplicate_scope",
                "job_fingerprint",
                "source",
            ]
        )
        .reset_index(drop=True)
    )


def build_source_reconciliation(
    master_jobs: pd.DataFrame,
) -> pd.DataFrame:
    """Summarize record counts and completeness by source."""

    summaries = []

    for source, source_jobs in master_jobs.groupby(
        "source"
    ):
        target_mask = (
            source_jobs[
                "is_target_data_role"
            ]
            .fillna(False)
            .astype(bool)
        )

        override_mask = (
            source_jobs[
                "role_override_applied"
            ]
            .fillna(False)
            .astype(bool)
        )

        salary_disclosed_mask = (
            source_jobs["salary_raw"]
            .fillna("")
            .astype(str)
            .str.strip()
            .ne("")
        )

        summaries.append(
            {
                "source": source,
                "total_records": len(
                    source_jobs
                ),
                "target_roles": int(
                    target_mask.sum()
                ),
                "non_target_roles": int(
                    (~target_mask).sum()
                ),
                "overrides_applied": int(
                    override_mask.sum()
                ),
                "salary_disclosed": int(
                    salary_disclosed_mask.sum()
                ),
                "missing_salary": int(
                    (
                        ~salary_disclosed_mask
                    ).sum()
                ),
                "missing_publication_dates": int(
                    source_jobs[
                        "publication_date"
                    ]
                    .isna()
                    .sum()
                ),
            }
        )

    return pd.DataFrame(summaries)


def print_master_report(
    remotive_jobs: pd.DataFrame,
    himalayas_jobs: pd.DataFrame,
    master_jobs: pd.DataFrame,
    target_jobs: pd.DataFrame,
    duplicate_report: pd.DataFrame,
    reconciliation: pd.DataFrame,
) -> None:
    """Print integration and reconciliation metrics."""

    expected_records = (
        len(remotive_jobs)
        + len(himalayas_jobs)
    )

    duplicate_groups = (
        duplicate_report[
            "job_fingerprint"
        ].nunique()
        if not duplicate_report.empty
        else 0
    )

    cross_source_groups = (
        duplicate_report.loc[
            duplicate_report[
                "duplicate_scope"
            ]
            == "Cross-source",
            "job_fingerprint",
        ].nunique()
        if not duplicate_report.empty
        else 0
    )

    within_source_groups = (
        duplicate_report.loc[
            duplicate_report[
                "duplicate_scope"
            ]
            == "Within-source",
            "job_fingerprint",
        ].nunique()
        if not duplicate_report.empty
        else 0
    )

    print("MASTER STAGING REPORT")
    print("=" * 65)

    print(
        f"Remotive records received: "
        f"{len(remotive_jobs)}"
    )

    print(
        f"Himalayas records received: "
        f"{len(himalayas_jobs)}"
    )

    print(
        f"Expected combined records: "
        f"{expected_records}"
    )

    print(
        f"Master records created: "
        f"{len(master_jobs)}"
    )

    print(
        f"Record-count difference: "
        f"{len(master_jobs) - expected_records}"
    )

    print(
        f"Target data roles: "
        f"{len(target_jobs)}"
    )

    print(
        f"Non-target roles: "
        f"{len(master_jobs) - len(target_jobs)}"
    )

    print(
        f"Manual overrides applied: "
        f"{master_jobs['role_override_applied'].fillna(False).sum()}"
    )

    print(
        f"Duplicate fingerprint groups: "
        f"{duplicate_groups}"
    )

    print(
        f"Cross-source duplicate groups: "
        f"{cross_source_groups}"
    )

    print(
        f"Within-source duplicate groups: "
        f"{within_source_groups}"
    )

    print("\nSOURCE RECONCILIATION")
    print("-" * 65)

    print(
        reconciliation.to_string(
            index=False
        )
    )

    print("\nMASTER ROLE DISTRIBUTION")
    print("-" * 65)

    print(
        master_jobs[
            "role_family"
        ]
        .value_counts()
        .to_string()
    )


def main() -> None:
    """Build the conformed multi-source master staging layer."""

    remotive_jobs = load_and_harmonize_source(
        file_path=REMOTIVE_INPUT_FILE,
        expected_source="Remotive",
    )

    himalayas_jobs = load_and_harmonize_source(
        file_path=HIMALAYAS_INPUT_FILE,
        expected_source="Himalayas",
    )

    master_jobs = pd.concat(
        [
            remotive_jobs,
            himalayas_jobs,
        ],
        ignore_index=True,
    )

    validate_master_keys(
        master_jobs
    )

    master_jobs = (
        master_jobs
        .sort_values(
            by=[
                "publication_date",
                "source",
                "job_title_raw",
            ],
            ascending=[
                False,
                True,
                True,
            ],
            na_position="last",
        )
        .reset_index(drop=True)
    )

    target_jobs = master_jobs[
        master_jobs[
            "is_target_data_role"
        ]
        .fillna(False)
    ].copy()

    duplicate_report = build_duplicate_report(
        master_jobs
    )

    reconciliation = (
        build_source_reconciliation(
            master_jobs
        )
    )

    PROCESSED_DATA_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    REPORTS_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    master_jobs.to_csv(
        MASTER_OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig",
        date_format="%Y-%m-%dT%H:%M:%SZ",
    )

    target_jobs.to_csv(
        TARGET_OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig",
        date_format="%Y-%m-%dT%H:%M:%SZ",
    )

    duplicate_report.to_csv(
        DUPLICATE_REPORT_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    reconciliation.to_csv(
        RECONCILIATION_REPORT_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    print_master_report(
        remotive_jobs=remotive_jobs,
        himalayas_jobs=himalayas_jobs,
        master_jobs=master_jobs,
        target_jobs=target_jobs,
        duplicate_report=duplicate_report,
        reconciliation=reconciliation,
    )

    print("\nFILES CREATED")
    print("-" * 65)
    print(MASTER_OUTPUT_FILE)
    print(TARGET_OUTPUT_FILE)
    print(DUPLICATE_REPORT_FILE)
    print(RECONCILIATION_REPORT_FILE)


if __name__ == "__main__":
    main()