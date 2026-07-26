from __future__ import annotations

from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]

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

REPORTS_DIRECTORY = (
    PROJECT_ROOT
    / "reports"
)

METRICS_OUTPUT_FILE = (
    REPORTS_DIRECTORY
    / "role_classifier_metrics.csv"
)

MISMATCH_OUTPUT_FILE = (
    REPORTS_DIRECTORY
    / "role_classifier_mismatches.csv"
)


def clean_text_column(
    dataframe: pd.DataFrame,
    column: str,
) -> None:
    """Standardize text values used in comparisons."""

    dataframe[column] = (
        dataframe[column]
        .fillna("")
        .astype(str)
        .str.strip()
    )


def safe_divide(
    numerator: int,
    denominator: int,
) -> float:
    """Return zero when a metric denominator is zero."""

    if denominator == 0:
        return 0.0

    return numerator / denominator


def load_evaluation_data() -> pd.DataFrame:
    """Match reviewed labels to their automated predictions."""

    if not STAGING_FILE.exists():
        raise FileNotFoundError(
            f"Staging file not found: {STAGING_FILE}"
        )

    if not OVERRIDE_FILE.exists():
        raise FileNotFoundError(
            f"Override file not found: {OVERRIDE_FILE}"
        )

    staging = pd.read_csv(
        STAGING_FILE,
        dtype={
            "source_job_id": "string",
        },
    )

    overrides = pd.read_csv(
        OVERRIDE_FILE,
        dtype={
            "source_job_id": "string",
        },
    )

    required_staging_columns = {
        "source",
        "source_job_id",
        "job_title_raw",
        "company_name",
        "automated_role_family",
        "role_family",
        "classification_method",
    }

    missing_staging_columns = (
        required_staging_columns
        - set(staging.columns)
    )

    if missing_staging_columns:
        raise ValueError(
            "Staging file is missing columns: "
            f"{sorted(missing_staging_columns)}"
        )

    required_override_columns = {
        "source_job_id",
        "correct_role_family",
        "manual_decision",
    }

    missing_override_columns = (
        required_override_columns
        - set(overrides.columns)
    )

    if missing_override_columns:
        raise ValueError(
            "Override file is missing columns: "
            f"{sorted(missing_override_columns)}"
        )

    if "source" not in overrides.columns:
        overrides["source"] = "Himalayas"

    staging_text_columns = [
        "source",
        "source_job_id",
        "automated_role_family",
        "role_family",
    ]

    for column in staging_text_columns:
        clean_text_column(
            dataframe=staging,
            column=column,
        )

    override_text_columns = [
        "source",
        "source_job_id",
        "correct_role_family",
        "manual_decision",
    ]

    for column in override_text_columns:
        clean_text_column(
            dataframe=overrides,
            column=column,
        )

    duplicate_override_keys = overrides.duplicated(
        subset=[
            "source",
            "source_job_id",
        ],
        keep=False,
    )

    if duplicate_override_keys.any():
        duplicate_rows = overrides.loc[
            duplicate_override_keys,
            [
                "source",
                "source_job_id",
            ],
        ]

        raise ValueError(
            "Duplicate override keys found:\n"
            f"{duplicate_rows.to_string(index=False)}"
        )

    override_labels = overrides[
        [
            "source",
            "source_job_id",
            "correct_role_family",
            "manual_decision",
        ]
    ].copy()

    evaluation = override_labels.merge(
        staging[
            [
                "source",
                "source_job_id",
                "job_title_raw",
                "company_name",
                "automated_role_family",
                "role_family",
                "classification_method",
            ]
        ],
        how="left",
        on=[
            "source",
            "source_job_id",
        ],
        validate="one_to_one",
        indicator=True,
    )

    unmatched_rows = evaluation[
        evaluation["_merge"]
        != "both"
    ]

    if not unmatched_rows.empty:
        unmatched_ids = unmatched_rows[
            "source_job_id"
        ].tolist()

        raise ValueError(
            "Some reviewed jobs were not found "
            f"in staging: {unmatched_ids}"
        )

    evaluation = evaluation.drop(
        columns=["_merge"]
    )

    return evaluation


def calculate_metrics(
    evaluation: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Calculate family-level and binary target-role metrics."""

    evaluation = evaluation.copy()

    evaluation["exact_family_match"] = (
        evaluation["automated_role_family"]
        == evaluation["correct_role_family"]
    )

    evaluation["predicted_is_target"] = (
        evaluation["automated_role_family"]
        != "Non-target Role"
    )

    evaluation["actual_is_target"] = (
        evaluation["correct_role_family"]
        != "Non-target Role"
    )

    true_positive = (
        evaluation["predicted_is_target"]
        & evaluation["actual_is_target"]
    ).sum()

    false_positive = (
        evaluation["predicted_is_target"]
        & ~evaluation["actual_is_target"]
    ).sum()

    false_negative = (
        ~evaluation["predicted_is_target"]
        & evaluation["actual_is_target"]
    ).sum()

    true_negative = (
        ~evaluation["predicted_is_target"]
        & ~evaluation["actual_is_target"]
    ).sum()

    reviewed_records = len(evaluation)

    exact_matches = (
        evaluation["exact_family_match"]
        .sum()
    )

    family_accuracy = safe_divide(
        exact_matches,
        reviewed_records,
    )

    precision = safe_divide(
        true_positive,
        true_positive + false_positive,
    )

    recall = safe_divide(
        true_positive,
        true_positive + false_negative,
    )

    f1_score = safe_divide(
        2 * precision * recall,
        precision + recall,
    )

    metrics = pd.DataFrame(
        [
            {
                "reviewed_records": reviewed_records,
                "exact_role_family_matches": exact_matches,
                "exact_role_family_mismatches": (
                    reviewed_records - exact_matches
                ),
                "role_family_accuracy": family_accuracy,
                "true_positive": int(true_positive),
                "false_positive": int(false_positive),
                "false_negative": int(false_negative),
                "true_negative": int(true_negative),
                "target_precision": precision,
                "target_recall": recall,
                "target_f1_score": f1_score,
            }
        ]
    )

    mismatches = evaluation[
        ~evaluation["exact_family_match"]
    ].copy()

    mismatch_columns = [
        "source_job_id",
        "job_title_raw",
        "company_name",
        "automated_role_family",
        "correct_role_family",
        "manual_decision",
        "predicted_is_target",
        "actual_is_target",
    ]

    mismatches = (
        mismatches[
            mismatch_columns
        ]
        .sort_values(
            by=[
                "correct_role_family",
                "job_title_raw",
            ]
        )
        .reset_index(drop=True)
    )

    return metrics, mismatches


def print_report(
    metrics: pd.DataFrame,
    mismatches: pd.DataFrame,
) -> None:
    """Display the classifier evaluation results."""

    row = metrics.iloc[0]

    print("ROLE CLASSIFIER EVALUATION")
    print("=" * 65)

    print(
        f"Reviewed records: "
        f"{int(row['reviewed_records'])}"
    )

    print(
        f"Exact role-family matches: "
        f"{int(row['exact_role_family_matches'])}"
    )

    print(
        f"Exact role-family mismatches: "
        f"{int(row['exact_role_family_mismatches'])}"
    )

    print(
        f"Role-family accuracy: "
        f"{row['role_family_accuracy']:.2%}"
    )

    print("\nTARGET-ROLE DETECTION")
    print("-" * 65)

    print(
        f"True positives: "
        f"{int(row['true_positive'])}"
    )

    print(
        f"False positives: "
        f"{int(row['false_positive'])}"
    )

    print(
        f"False negatives: "
        f"{int(row['false_negative'])}"
    )

    print(
        f"True negatives: "
        f"{int(row['true_negative'])}"
    )

    print(
        f"Precision: "
        f"{row['target_precision']:.2%}"
    )

    print(
        f"Recall: "
        f"{row['target_recall']:.2%}"
    )

    print(
        f"F1 score: "
        f"{row['target_f1_score']:.2%}"
    )

    print("\nAUTOMATED FAMILY MISMATCHES")
    print("-" * 65)

    if mismatches.empty:
        print(
            "No automated family mismatches were found."
        )
    else:
        display_columns = [
            "job_title_raw",
            "automated_role_family",
            "correct_role_family",
        ]

        print(
            mismatches[
                display_columns
            ].to_string(index=False)
        )


def main() -> None:
    """Evaluate automated classifications against verified labels."""

    evaluation = load_evaluation_data()

    metrics, mismatches = calculate_metrics(
        evaluation
    )

    REPORTS_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    metrics.to_csv(
        METRICS_OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    mismatches.to_csv(
        MISMATCH_OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    print_report(
        metrics=metrics,
        mismatches=mismatches,
    )

    print("\nFILES CREATED")
    print("-" * 65)
    print(METRICS_OUTPUT_FILE)
    print(MISMATCH_OUTPUT_FILE)


if __name__ == "__main__":
    main()