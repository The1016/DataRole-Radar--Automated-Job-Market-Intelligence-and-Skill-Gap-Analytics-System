from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import re
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

from src.transform.role_taxonomy import (
    apply_role_classification,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DATA_DIRECTORY = PROJECT_ROOT / "data" / "raw"
PROCESSED_DATA_DIRECTORY = PROJECT_ROOT / "data" / "processed"

STAGING_OUTPUT_PATH = (
    PROCESSED_DATA_DIRECTORY / "remotive_jobs_staging.csv"
)

TARGET_OUTPUT_PATH = (
    PROCESSED_DATA_DIRECTORY / "remotive_target_roles.csv"
)

ROLE_OVERRIDES_PATH = (
    PROJECT_ROOT
    / "data"
    / "reference"
    / "role_classification_overrides.csv"
)




def find_latest_raw_file() -> Path:
    """Return the most recently named Remotive JSON snapshot."""

    json_files = sorted(
        RAW_DATA_DIRECTORY.glob("remotive_jobs_*.json")
    )

    if not json_files:
        raise FileNotFoundError(
            "No Remotive JSON snapshots were found in data/raw."
        )

    return json_files[-1]


def normalize_whitespace(value: object) -> str:
    """Remove unnecessary spaces and line breaks."""

    if value is None:
        return ""

    text = str(value)

    return re.sub(r"\s+", " ", text).strip()


def clean_html(value: object) -> str:
    """Convert an HTML job description into plain text."""

    if value is None:
        return ""

    soup = BeautifulSoup(str(value), "html.parser")

    return normalize_whitespace(
        soup.get_text(separator=" ")
    )


def normalize_tags(value: object) -> str:
    """Convert a list of tags into a pipe-separated string."""

    if not isinstance(value, list):
        return ""

    cleaned_tags = {
        normalize_whitespace(tag)
        for tag in value
        if normalize_whitespace(tag)
    }

    return "|".join(sorted(cleaned_tags))



def build_fingerprint(
    company_name: object,
    job_title: object,
    location: object,
) -> str:
    """Create a repeatable identifier for duplicate detection."""

    fingerprint_text = "|".join(
        [
            normalize_whitespace(company_name).lower(),
            normalize_whitespace(job_title).lower(),
            normalize_whitespace(location).lower(),
        ]
    )

    return hashlib.sha256(
        fingerprint_text.encode("utf-8")
    ).hexdigest()[:20]


def extract_collection_timestamp(file_path: Path) -> str:
    """Extract the collection datetime from the snapshot filename."""

    match = re.search(
        r"remotive_jobs_(\d{8}_\d{6})",
        file_path.stem,
    )

    if not match:
        return datetime.now(timezone.utc).isoformat()

    collected_at = datetime.strptime(
        match.group(1),
        "%Y%m%d_%H%M%S",
    ).replace(tzinfo=timezone.utc)

    return collected_at.isoformat()


def load_raw_jobs(file_path: Path) -> tuple[pd.DataFrame, dict]:
    """Read the raw JSON snapshot and return jobs and metadata."""

    payload = pd.read_json(
        file_path,
        typ="series",
    ).to_dict()

    jobs = payload.get("jobs", [])

    if not isinstance(jobs, list):
        raise ValueError(
            "The raw file does not contain a valid jobs list."
        )

    dataframe = pd.DataFrame(jobs)

    metadata = {
        "job_count": payload.get("job-count"),
        "total_job_count": payload.get(
            "total-job-count"
        ),
    }

    return dataframe, metadata


def transform_jobs(
    dataframe: pd.DataFrame,
    collected_at: str,
) -> pd.DataFrame:
    """Clean and standardize raw Remotive job records."""

    required_columns = [
        "id",
        "url",
        "title",
        "company_name",
        "company_logo",
        "category",
        "tags",
        "job_type",
        "publication_date",
        "candidate_required_location",
        "salary",
        "description",
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in dataframe.columns
    ]

    if missing_columns:
        raise ValueError(
            f"Missing required columns: {missing_columns}"
        )

    transformed = dataframe.copy()

    transformed["source"] = "Remotive"

    transformed["source_job_id"] = (
        transformed["id"]
        .astype("string")
    )

    transformed["job_title_raw"] = (
        transformed["title"]
        .apply(normalize_whitespace)
    )

    transformed["company_name"] = (
        transformed["company_name"]
        .apply(normalize_whitespace)
    )

    transformed["category"] = (
        transformed["category"]
        .apply(normalize_whitespace)
    )

    transformed["job_type"] = (
        transformed["job_type"]
        .apply(normalize_whitespace)
        .str.lower()
    )

    transformed["location_raw"] = (
        transformed["candidate_required_location"]
        .apply(normalize_whitespace)
    )

    transformed["salary_raw"] = (
        transformed["salary"]
        .apply(normalize_whitespace)
    )

    transformed["tags"] = (
        transformed["tags"]
        .apply(normalize_tags)
    )

    transformed["description_text"] = (
        transformed["description"]
        .apply(clean_html)
    )

    transformed["publication_date"] = pd.to_datetime(
        transformed["publication_date"],
        errors="coerce",
        utc=True,
    )

    transformed = apply_role_classification(
    dataframe=transformed,
    override_file=ROLE_OVERRIDES_PATH,
)

    transformed["job_fingerprint"] = transformed.apply(
        lambda row: build_fingerprint(
            company_name=row["company_name"],
            job_title=row["job_title_raw"],
            location=row["location_raw"],
        ),
        axis=1,
    )

    transformed["collected_at"] = collected_at

    transformed = transformed.rename(
        columns={
            "url": "job_url",
            "company_logo": "company_logo_url",
        }
    )

    output_columns = [
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
    ]

    transformed = transformed[output_columns]

    transformed = transformed.drop_duplicates(
        subset=["source", "source_job_id"],
        keep="last",
    )

    transformed = transformed.sort_values(
        by="publication_date",
        ascending=False,
        na_position="last",
    )

    return transformed


def print_quality_report(
    transformed: pd.DataFrame,
    metadata: dict,
    source_file: Path,
) -> None:
    """Print a basic data-quality and coverage report."""

    target_jobs = transformed[
        transformed["is_target_data_role"]
    ]

    print("\nREMOTIVE STAGING REPORT")
    print("=" * 50)

    print(f"Source file: {source_file.name}")
    print(
        f"API job-count: "
        f"{metadata.get('job_count')}"
    )
    print(
        f"API total-job-count: "
        f"{metadata.get('total_job_count')}"
    )
    print(f"Processed records: {len(transformed)}")
    print(f"Target data roles: {len(target_jobs)}")
    print(
        f"Verified role overrides applied: "
        f"{transformed['role_override_applied'].sum()}"
    )
    changed_predictions = (
            transformed["automated_role_family"]
            != transformed["role_family"]
    ).sum()

    print(
        f"Automated predictions changed: "
        f"{changed_predictions}"
    )

    duplicate_fingerprints = (
        transformed["job_fingerprint"]
        .duplicated()
        .sum()
    )

    print(
        f"Duplicate fingerprints: "
        f"{duplicate_fingerprints}"
    )

    print(
        f"Missing job titles: "
        f"{transformed['job_title_raw'].eq('').sum()}"
    )

    print(
        f"Missing companies: "
        f"{transformed['company_name'].eq('').sum()}"
    )

    print(
        f"Missing publication dates: "
        f"{transformed['publication_date'].isna().sum()}"
    )

    print(
        f"Missing salary information: "
        f"{transformed['salary_raw'].eq('').sum()}"
    )

    print("\nJOBS BY CATEGORY")
    print("-" * 50)

    category_counts = (
        transformed["category"]
        .value_counts(dropna=False)
    )

    print(category_counts.to_string())

    print("\nTARGET ROLE FAMILIES")
    print("-" * 50)

    if target_jobs.empty:
        print("No target data roles were identified.")
    else:
        role_counts = (
            target_jobs["role_family"]
            .value_counts()
        )

        print(role_counts.to_string())

        print("\nTARGET JOB TITLES")
        print("-" * 50)

        for title in target_jobs["job_title_raw"]:
            print(f"- {title}")


def main() -> None:
    """Build the first cleaned Remotive staging dataset."""

    source_file = find_latest_raw_file()

    raw_jobs, metadata = load_raw_jobs(
        source_file
    )

    collected_at = extract_collection_timestamp(
        source_file
    )

    transformed_jobs = transform_jobs(
        dataframe=raw_jobs,
        collected_at=collected_at,
    )

    target_jobs = transformed_jobs[
        transformed_jobs["is_target_data_role"]
    ].copy()

    PROCESSED_DATA_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    transformed_jobs.to_csv(
        STAGING_OUTPUT_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    target_jobs.to_csv(
        TARGET_OUTPUT_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    print_quality_report(
        transformed=transformed_jobs,
        metadata=metadata,
        source_file=source_file,
    )

    print("\nFILES CREATED")
    print("-" * 50)
    print(STAGING_OUTPUT_PATH)
    print(TARGET_OUTPUT_PATH)


if __name__ == "__main__":
    main()