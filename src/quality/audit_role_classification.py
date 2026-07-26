from __future__ import annotations

from pathlib import Path
import re

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]

INPUT_FILE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "himalayas_jobs_staging.csv"
)

REPORTS_DIRECTORY = (
    PROJECT_ROOT
    / "reports"
)

OUTPUT_FILE = (
    REPORTS_DIRECTORY
    / "role_classification_audit.csv"
)


AMBIGUOUS_ROLE_FAMILIES = {
    "Other Analytics",
    "Business Analyst",
    "Power BI",
    "Analytics Manager",
}


RELEVANT_TITLE_PATTERN = re.compile(
    pattern=(
        r"\bdata\b|"
        r"\banalyst\b|"
        r"\banalytics?\b|"
        r"\bdecision\s+science\b|"
        r"\bbusiness\s+intelligence\b|"
        r"\bbi\b|"
        r"\binsights?\b|"
        r"\breporting\b|"
        r"\bpower\s*bi\b|"
        r"\btableau\b"
    ),
    flags=re.IGNORECASE,
)


def determine_review_reason(
    row: pd.Series,
) -> str:
    """Explain why a classified job needs manual review."""

    reasons = []

    role_family = str(
        row["role_family"]
    )

    job_title = str(
        row["job_title_raw"]
    )

    if role_family in AMBIGUOUS_ROLE_FAMILIES:
        reasons.append(
            "Ambiguous standardized role"
        )

    if (
        role_family == "Non-target Role"
        and RELEVANT_TITLE_PATTERN.search(
            job_title
        )
    ):
        reasons.append(
            "Possible false negative"
        )

    if (
        role_family != "Non-target Role"
        and not RELEVANT_TITLE_PATTERN.search(
            job_title
        )
    ):
        reasons.append(
            "Possible false positive"
        )

    return " | ".join(reasons)


def determine_review_priority(
    review_reason: str,
) -> str:
    """Assign a review priority based on the suspected issue."""

    if "Possible false negative" in review_reason:
        return "High"

    if "Possible false positive" in review_reason:
        return "High"

    if "Ambiguous standardized role" in review_reason:
        return "Medium"

    return "No review"


def main() -> None:
    """Create a manual audit file for role classifications."""

    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Staging file not found: {INPUT_FILE}"
        )

    dataframe = pd.read_csv(
        INPUT_FILE
    )

    required_columns = [
        "source_job_id",
        "job_title_raw",
        "role_family",
        "is_target_data_role",
        "company_name",
        "search_queries",
        "job_url",
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in dataframe.columns
    ]

    if missing_columns:
        raise ValueError(
            f"Missing columns: {missing_columns}"
        )

    audit = dataframe.copy()

    audit["review_reason"] = audit.apply(
        determine_review_reason,
        axis=1,
    )

    audit["review_priority"] = (
        audit["review_reason"]
        .apply(determine_review_priority)
    )

    audit = audit[
        audit["review_priority"]
        != "No review"
    ].copy()

    priority_order = {
        "High": 1,
        "Medium": 2,
    }

    audit["priority_order"] = (
        audit["review_priority"]
        .map(priority_order)
    )

    audit["manual_decision"] = ""
    audit["correct_role_family"] = ""
    audit["review_notes"] = ""

    output_columns = [
        "review_priority",
        "review_reason",
        "source_job_id",
        "job_title_raw",
        "role_family",
        "is_target_data_role",
        "company_name",
        "search_queries",
        "manual_decision",
        "correct_role_family",
        "review_notes",
        "job_url",
    ]

    audit = (
        audit
        .sort_values(
            by=[
                "priority_order",
                "role_family",
                "job_title_raw",
            ]
        )
        [output_columns]
        .reset_index(drop=True)
    )

    REPORTS_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    audit.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    print("ROLE CLASSIFICATION AUDIT")
    print("=" * 70)

    print(
        f"Total staging jobs: "
        f"{len(dataframe)}"
    )

    print(
        f"Jobs requiring review: "
        f"{len(audit)}"
    )

    print("\nREVIEW PRIORITY")
    print("-" * 70)

    print(
        audit["review_priority"]
        .value_counts()
        .to_string()
    )

    print("\nREVIEW REASONS")
    print("-" * 70)

    print(
        audit["review_reason"]
        .value_counts()
        .to_string()
    )

    print("\nJOBS REQUIRING REVIEW")
    print("-" * 70)

    display_columns = [
        "review_priority",
        "job_title_raw",
        "role_family",
        "review_reason",
    ]

    print(
        audit[
            display_columns
        ].to_string(index=False)
    )

    print("\nFILE CREATED")
    print("-" * 70)
    print(OUTPUT_FILE)


if __name__ == "__main__":
    main()