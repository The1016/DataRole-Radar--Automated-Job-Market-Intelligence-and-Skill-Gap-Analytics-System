from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]

STAGING_FILE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "remotive_jobs_staging.csv"
)


def main() -> None:
    """Display records sharing the same job fingerprint."""

    dataframe = pd.read_csv(STAGING_FILE)

    duplicate_rows = dataframe[
        dataframe.duplicated(
            subset=["job_fingerprint"],
            keep=False,
        )
    ].copy()

    if duplicate_rows.empty:
        print("No duplicate fingerprints were found.")
        return

    duplicate_rows = duplicate_rows.sort_values(
        by=[
            "job_fingerprint",
            "company_name",
            "job_title_raw",
        ]
    )

    columns_to_display = [
        "job_fingerprint",
        "source_job_id",
        "company_name",
        "job_title_raw",
        "location_raw",
        "publication_date",
        "job_url",
    ]

    print("POTENTIAL DUPLICATE RECORDS")
    print("=" * 150)

    print(
        duplicate_rows[
            columns_to_display
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()