from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
from pathlib import Path


import pandas as pd
from bs4 import BeautifulSoup

from src.transform.role_taxonomy import (
    apply_role_classification,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]

RAW_DATA_DIRECTORY = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "himalayas"
)

PROCESSED_DATA_DIRECTORY = (
    PROJECT_ROOT
    / "data"
    / "processed"
)

STAGING_OUTPUT_PATH = (
    PROCESSED_DATA_DIRECTORY
    / "himalayas_jobs_staging.csv"
)

TARGET_OUTPUT_PATH = (
    PROCESSED_DATA_DIRECTORY
    / "himalayas_target_roles.csv"
)

ROLE_OVERRIDES_PATH = (
    PROJECT_ROOT
    / "data"
    / "reference"
    / "role_classification_overrides.csv"
)




def normalize_whitespace(value: object) -> str:
    """Remove unnecessary spaces and line breaks."""

    if value is None:
        return ""

    text = str(value)

    return re.sub(
        pattern=r"\s+",
        repl=" ",
        string=text,
    ).strip()


def clean_html(value: object) -> str:
    """Convert an HTML description into plain text."""

    if value is None:
        return ""

    soup = BeautifulSoup(
        str(value),
        "html.parser",
    )

    return normalize_whitespace(
        soup.get_text(separator=" ")
    )


def normalize_string_list(value: object) -> str:
    """Convert a list of strings into a canonical pipe-separated value."""

    if not isinstance(value, list):
        return ""

    cleaned_values = {
        normalize_whitespace(item)
        for item in value
        if normalize_whitespace(item)
    }

    return "|".join(
        sorted(
            cleaned_values,
            key=str.casefold,
        )
    )


def normalize_locations(value: object) -> str:
    """Convert Himalayas location objects into country names."""

    if not isinstance(value, list):
        return ""

    if not value:
        return "Worldwide"

    location_names = set()

    for location in value:
        if isinstance(location, dict):
            location_name = normalize_whitespace(
                location.get("name")
            )
        else:
            location_name = normalize_whitespace(
                location
            )

        if location_name:
            location_names.add(location_name)

    return "|".join(
        sorted(
            location_names,
            key=str.casefold,
        )
    )


def combine_query_names(values: pd.Series) -> str:
    """Combine the searches in which the same job appeared."""

    cleaned_queries = {
        normalize_whitespace(value)
        for value in values
        if normalize_whitespace(value)
    }

    return "|".join(
        sorted(
            cleaned_queries,
            key=str.casefold,
        )
    )



def build_fingerprint(
    company_name: object,
    job_title: object,
    location: object,
) -> str:
    """Create a hash-based duplicate candidate key."""

    fingerprint_text = "|".join(
        [
            normalize_whitespace(
                company_name
            ).lower(),
            normalize_whitespace(
                job_title
            ).lower(),
            normalize_whitespace(
                location
            ).lower(),
        ]
    )

    return hashlib.sha256(
        fingerprint_text.encode("utf-8")
    ).hexdigest()[:20]


def format_salary_number(value: object) -> str:
    """Format one numeric salary value for display."""

    if pd.isna(value):
        return ""

    numeric_value = float(value)

    if numeric_value.is_integer():
        return f"{int(numeric_value):,}"

    return f"{numeric_value:,.2f}"


def build_salary_text(row: pd.Series) -> str:
    """Build a readable salary range from structured salary fields."""

    minimum_salary = row["salary_min"]
    maximum_salary = row["salary_max"]

    currency = normalize_whitespace(
        row["salary_currency"]
    )

    period = normalize_whitespace(
        row["salary_period"]
    ).lower()

    minimum_text = format_salary_number(
        minimum_salary
    )

    maximum_text = format_salary_number(
        maximum_salary
    )

    if not minimum_text and not maximum_text:
        return ""

    if minimum_text and maximum_text:
        amount_text = (
            f"{minimum_text}–{maximum_text}"
        )
    elif minimum_text:
        amount_text = f"From {minimum_text}"
    else:
        amount_text = f"Up to {maximum_text}"

    components = [amount_text]

    if currency:
        components.append(currency)

    if period:
        components.append(f"per {period}")

    return " ".join(components)


def extract_file_metadata(
    file_path: Path,
) -> tuple[str, int, str, str]:
    """Extract query, page, batch timestamp, and collection time."""

    paginated_match = re.fullmatch(
        pattern=(
            r"himalayas_(.+)_"
            r"page_(\d{3})_"
            r"(\d{8}_\d{6})"
        ),
        string=file_path.stem,
    )

    if paginated_match:
        query_slug = paginated_match.group(1)
        page = int(
            paginated_match.group(2)
        )
        timestamp_text = (
            paginated_match.group(3)
        )

    else:
        # Backward compatibility with the old page-1 format.
        legacy_match = re.fullmatch(
            pattern=(
                r"himalayas_(.+)_"
                r"(\d{8}_\d{6})"
            ),
            string=file_path.stem,
        )

        if not legacy_match:
            raise ValueError(
                f"Invalid Himalayas filename: "
                f"{file_path.name}"
            )

        query_slug = legacy_match.group(1)
        page = 1
        timestamp_text = legacy_match.group(2)

    query = query_slug.replace("_", " ")

    collected_at = datetime.strptime(
        timestamp_text,
        "%Y%m%d_%H%M%S",
    ).replace(
        tzinfo=timezone.utc
    ).isoformat()

    return (
        query,
        page,
        timestamp_text,
        collected_at,
    )

def find_latest_batch_files() -> list[Path]:
    """Return every raw file belonging to the newest extraction run."""

    json_files = list(
        RAW_DATA_DIRECTORY.glob(
            "himalayas_*.json"
        )
    )

    if not json_files:
        raise FileNotFoundError(
            "No Himalayas JSON files were found."
        )

    file_metadata = []

    for file_path in json_files:
        query, page, timestamp, collected_at = (
            extract_file_metadata(file_path)
        )

        file_metadata.append(
            {
                "file_path": file_path,
                "query": query,
                "page": page,
                "timestamp": timestamp,
                "collected_at": collected_at,
            }
        )

    latest_timestamp = max(
        item["timestamp"]
        for item in file_metadata
    )

    latest_files = [
        item["file_path"]
        for item in file_metadata
        if item["timestamp"] == latest_timestamp
    ]

    return sorted(latest_files)


def load_latest_batch(
    file_paths: list[Path],
) -> pd.DataFrame:
    """Load all search responses from one extraction batch."""

    records = []

    for file_path in file_paths:
        query, page, timestamp, collected_at = (
            extract_file_metadata(file_path)
        )

        with file_path.open(
            mode="r",
            encoding="utf-8",
        ) as input_file:
            payload = json.load(input_file)

        jobs = payload.get("jobs")

        if not isinstance(jobs, list):
            raise ValueError(
                f"Invalid jobs field in "
                f"{file_path.name}"
            )

        for job in jobs:
            if not isinstance(job, dict):
                continue

            record = job.copy()

            record["_source_query"] = query
            record["_collected_at"] = (
                collected_at
            )
            record["_source_page"] = page
            record["_source_file"] = (
                file_path.name
            )

            records.append(record)

    if not records:
        raise ValueError(
            "The latest Himalayas batch "
            "contains no job records."
        )

    return pd.DataFrame(records)


def parse_api_datetime(
    series: pd.Series,
) -> pd.Series:
    """Parse either epoch milliseconds or ISO datetime strings."""

    numeric_values = pd.to_numeric(
        series,
        errors="coerce",
    )

    parsed = pd.Series(
        pd.NaT,
        index=series.index,
        dtype="datetime64[ns, UTC]",
    )

    numeric_mask = numeric_values.notna()

    parsed.loc[numeric_mask] = pd.to_datetime(
        numeric_values.loc[numeric_mask],
        unit="ms",
        errors="coerce",
        utc=True,
    )

    text_mask = (
        ~numeric_mask
        & series.notna()
    )

    parsed.loc[text_mask] = pd.to_datetime(
        series.loc[text_mask],
        errors="coerce",
        utc=True,
        format="mixed",
    )

    return parsed

def validate_source_schema(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """Validate mandatory fields and add absent optional fields."""

    required_columns = [
        "guid",
        "title",
        "companyName",
        "description",
        "pubDate",
        "applicationLink",
        "_source_query",
        "_collected_at",
    ]

    missing_required_columns = [
        column
        for column in required_columns
        if column not in dataframe.columns
    ]

    if missing_required_columns:
        raise ValueError(
            "Missing mandatory Himalayas fields: "
            f"{missing_required_columns}"
        )

    optional_columns = [
        "companyLogo",
        "employmentType",
        "minSalary",
        "maxSalary",
        "salaryPeriod",
        "seniority",
        "currency",
        "locationRestrictions",
        "timezoneRestrictions",
        "categories",
        "parentCategories",
        "expiryDate",
    ]

    validated = dataframe.copy()

    for column in optional_columns:
        if column not in validated.columns:
            validated[column] = None

    return validated


def transform_jobs(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """Transform raw Himalayas records into standardized staging data."""

    transformed = validate_source_schema(
        dataframe
    )

    transformed["source"] = "Himalayas"

    transformed["source_job_id"] = (
        transformed["guid"]
        .astype("string")
        .str.strip()
    )

    missing_ids = (
        transformed["source_job_id"]
        .isna()
        | transformed["source_job_id"].eq("")
    )

    if missing_ids.any():
        raise ValueError(
            "One or more Himalayas jobs "
            "are missing a GUID."
        )

    transformed["search_queries"] = (
        transformed
        .groupby("source_job_id")[
            "_source_query"
        ]
        .transform(combine_query_names)
    )

    transformed["job_title_raw"] = (
        transformed["title"]
        .apply(normalize_whitespace)
    )

    transformed["company_name"] = (
        transformed["companyName"]
        .apply(normalize_whitespace)
    )

    transformed["company_logo_url"] = (
        transformed["companyLogo"]
        .apply(normalize_whitespace)
    )

    transformed["category"] = (
        transformed["parentCategories"]
        .apply(normalize_string_list)
    )

    transformed["tags"] = (
        transformed["categories"]
        .apply(normalize_string_list)
    )

    transformed["job_type"] = (
        transformed["employmentType"]
        .apply(normalize_whitespace)
        .str.lower()
    )

    transformed["seniority_raw"] = (
        transformed["seniority"]
        .apply(normalize_string_list)
    )

    transformed["location_raw"] = (
        transformed["locationRestrictions"]
        .apply(normalize_locations)
    )

    transformed["timezone_raw"] = (
        transformed["timezoneRestrictions"]
        .apply(normalize_string_list)
    )

    transformed["is_worldwide"] = (
        transformed["locationRestrictions"]
        .apply(
            lambda value: (
                isinstance(value, list)
                and len(value) == 0
            )
        )
    )

    transformed["salary_min"] = pd.to_numeric(
        transformed["minSalary"],
        errors="coerce",
    )

    transformed["salary_max"] = pd.to_numeric(
        transformed["maxSalary"],
        errors="coerce",
    )

    transformed["salary_currency"] = (
        transformed["currency"]
        .apply(normalize_whitespace)
        .str.upper()
    )

    transformed["salary_period"] = (
        transformed["salaryPeriod"]
        .apply(normalize_whitespace)
        .str.lower()
    )

    transformed["salary_raw"] = (
        transformed.apply(
            build_salary_text,
            axis=1,
        )
    )

    transformed["publication_date"] = (
        parse_api_datetime(
            transformed["pubDate"]
        )
    )

    transformed["expiry_date"] = (
        parse_api_datetime(
            transformed["expiryDate"]
        )
    )

    transformed["description_text"] = (
        transformed["description"]
        .apply(clean_html)
    )

    transformed["job_url"] = (
        transformed["applicationLink"]
        .apply(normalize_whitespace)
    )

    transformed = apply_role_classification(
        dataframe=transformed,
        override_file=ROLE_OVERRIDES_PATH,
    )

    transformed["job_fingerprint"] = (
        transformed.apply(
            lambda row: build_fingerprint(
                company_name=(
                    row["company_name"]
                ),
                job_title=(
                    row["job_title_raw"]
                ),
                location=(
                    row["location_raw"]
                ),
            ),
            axis=1,
        )
    )

    transformed["collected_at"] = (
        transformed["_collected_at"]
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

    transformed = transformed[
        output_columns
    ]

    transformed = (
        transformed
        .drop_duplicates(
            subset=[
                "source",
                "source_job_id",
            ],
            keep="first",
        )
        .sort_values(
            by="publication_date",
            ascending=False,
            na_position="last",
        )
        .reset_index(drop=True)
    )

    return transformed


def print_quality_report(
    raw_jobs: pd.DataFrame,
    transformed_jobs: pd.DataFrame,
    batch_files: list[Path],
) -> None:
    """Print coverage, duplication, and completeness metrics."""

    target_jobs = transformed_jobs[
        transformed_jobs[
            "is_target_data_role"
        ]
    ]

    repeated_records = (
        len(raw_jobs)
        - len(transformed_jobs)
    )

    salary_missing = (
        transformed_jobs["salary_min"].isna()
        & transformed_jobs["salary_max"].isna()
    ).sum()

    duplicate_fingerprints = (
        transformed_jobs[
            "job_fingerprint"
        ]
        .duplicated()
        .sum()
    )

    print("\nHIMALAYAS STAGING REPORT")
    print("=" * 60)

    print(
        f"Files in latest batch: "
        f"{len(batch_files)}"
    )

    print(
        f"Records across query files: "
        f"{len(raw_jobs)}"
    )

    print(
        f"Unique jobs after GUID deduplication: "
        f"{len(transformed_jobs)}"
    )

    print(
        f"Repeated records across queries: "
        f"{repeated_records}"
    )

    print(
        f"Target data roles: "
        f"{len(target_jobs)}"
    )
    print(
        f"Verified role overrides applied: "
        f"{transformed_jobs['role_override_applied'].sum()}"
    )

    print(
        f"Potential duplicate fingerprints: "
        f"{duplicate_fingerprints}"
    )

    print(
        f"Worldwide jobs: "
        f"{transformed_jobs['is_worldwide'].sum()}"
    )

    changed_predictions = (
            transformed_jobs["automated_role_family"]
            != transformed_jobs["role_family"]
    ).sum()

    print(
        f"Automated predictions changed: "
        f"{changed_predictions}"
    )

    print(
        f"Jobs without salary ranges: "
        f"{salary_missing}"
    )

    print(
        f"Missing publication dates: "
        f"{transformed_jobs['publication_date'].isna().sum()}"
    )

    print(
        f"Missing expiry dates: "
        f"{transformed_jobs['expiry_date'].isna().sum()}"
    )

    print("\nROLE FAMILY DISTRIBUTION")
    print("-" * 60)

    print(
        transformed_jobs[
            "role_family"
        ]
        .value_counts()
        .to_string()
    )

    print("\nSEARCH-QUERY OVERLAP")
    print("-" * 60)

    overlapping_jobs = transformed_jobs[
        transformed_jobs[
            "search_queries"
        ].str.contains(
            r"\|",
            regex=True,
            na=False,
        )
    ]

    if overlapping_jobs.empty:
        print(
            "No jobs appeared in more than one search."
        )
    else:
        overlap_columns = [
            "job_title_raw",
            "company_name",
            "search_queries",
        ]

        print(
            overlapping_jobs[
                overlap_columns
            ].to_string(index=False)
        )


def main() -> None:
    """Build the standardized Himalayas staging datasets."""

    batch_files = find_latest_batch_files()

    raw_jobs = load_latest_batch(
        batch_files
    )

    transformed_jobs = transform_jobs(
        raw_jobs
    )

    target_jobs = transformed_jobs[
        transformed_jobs[
            "is_target_data_role"
        ]
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
        raw_jobs=raw_jobs,
        transformed_jobs=transformed_jobs,
        batch_files=batch_files,
    )

    print("\nFILES CREATED")
    print("-" * 60)
    print(STAGING_OUTPUT_PATH)
    print(TARGET_OUTPUT_PATH)


if __name__ == "__main__":
    main()