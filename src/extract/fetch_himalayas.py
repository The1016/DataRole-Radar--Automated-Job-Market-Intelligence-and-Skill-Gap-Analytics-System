from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import time

import requests


API_URL = "https://himalayas.app/jobs/api/search"

SEARCH_QUERIES = (
    "data analyst",
    "business intelligence",
    "power bi",
    "data scientist",
    "data engineer",
    "analytics engineer",
)

MAX_PAGES_PER_QUERY = 3
REQUEST_DELAY_SECONDS = 1.5

PROJECT_ROOT = Path(__file__).resolve().parents[2]

RAW_DATA_DIRECTORY = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "himalayas"
)


def create_query_slug(query: str) -> str:
    """Convert a search query into a safe filename component."""

    normalized_query = query.strip().lower()

    slug = re.sub(
        pattern=r"[^a-z0-9]+",
        repl="_",
        string=normalized_query,
    )

    return slug.strip("_")


def fetch_jobs(
    query: str,
    page: int,
) -> dict:
    """Request one page of filtered Himalayas jobs."""

    parameters = {
        "q": query,
        "sort": "recent",
        "page": page,
    }

    headers = {
        "User-Agent": (
            "DataRole-Radar-Portfolio-Project/1.0"
        )
    }

    response = requests.get(
        API_URL,
        params=parameters,
        headers=headers,
        timeout=30,
    )

    response.raise_for_status()

    payload = response.json()

    jobs = payload.get("jobs")

    if not isinstance(jobs, list):
        raise ValueError(
            f"Invalid jobs field for "
            f"query='{query}', page={page}."
        )

    return payload


def extract_job_ids(
    jobs: list[dict],
    query: str,
    page: int,
) -> set[str]:
    """Validate and return the GUIDs from one response page."""

    job_ids = set()
    missing_guid_count = 0

    for job in jobs:
        if not isinstance(job, dict):
            continue

        guid = job.get("guid")

        if guid is None or not str(guid).strip():
            missing_guid_count += 1
            continue

        job_ids.add(str(guid).strip())

    if missing_guid_count:
        raise ValueError(
            f"{missing_guid_count} jobs were missing GUIDs "
            f"for query='{query}', page={page}."
        )

    return job_ids


def save_raw_snapshot(
    query: str,
    page: int,
    payload: dict,
    run_timestamp: str,
) -> Path:
    """Save one unmodified search-response page."""

    RAW_DATA_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    query_slug = create_query_slug(query)

    output_path = (
        RAW_DATA_DIRECTORY
        / (
            f"himalayas_{query_slug}_"
            f"page_{page:03d}_"
            f"{run_timestamp}.json"
        )
    )

    with output_path.open(
        mode="w",
        encoding="utf-8",
    ) as output_file:
        json.dump(
            payload,
            output_file,
            ensure_ascii=False,
            indent=2,
        )

    return output_path


def main() -> None:
    """Collect a bounded number of pages for each search query."""

    run_timestamp = datetime.now(
        timezone.utc
    ).strftime("%Y%m%d_%H%M%S")

    all_job_ids: set[str] = set()

    total_records_received = 0
    pages_saved = 0
    requests_completed = 0

    print("HIMALAYAS PAGINATED EXTRACTION")
    print("=" * 65)

    for query_number, query in enumerate(
        SEARCH_QUERIES,
        start=1,
    ):
        query_job_ids: set[str] = set()
        query_records = 0
        query_pages = 0

        print(
            f"\nQUERY {query_number}: {query}"
        )
        print("-" * 65)

        for page in range(
            1,
            MAX_PAGES_PER_QUERY + 1,
        ):
            if requests_completed > 0:
                time.sleep(
                    REQUEST_DELAY_SECONDS
                )

            try:
                payload = fetch_jobs(
                    query=query,
                    page=page,
                )

                requests_completed += 1

                jobs = payload["jobs"]

                if not jobs:
                    print(
                        f"Page {page}: no records; "
                        "stopping this query."
                    )
                    break

                page_job_ids = extract_job_ids(
                    jobs=jobs,
                    query=query,
                    page=page,
                )

                new_query_ids = (
                    page_job_ids
                    - query_job_ids
                )

                if not new_query_ids:
                    print(
                        f"Page {page}: all records "
                        "already appeared on an earlier "
                        "page; stopping this query."
                    )
                    break

                output_path = save_raw_snapshot(
                    query=query,
                    page=page,
                    payload=payload,
                    run_timestamp=run_timestamp,
                )

                query_job_ids.update(
                    page_job_ids
                )

                all_job_ids.update(
                    page_job_ids
                )

                query_records += len(jobs)
                total_records_received += len(jobs)

                query_pages += 1
                pages_saved += 1

                total_count = payload.get(
                    "totalCount",
                    "Unknown",
                )

                print(
                    f"Page {page}: "
                    f"{len(jobs)} records"
                )

                print(
                    f"Total matching jobs: "
                    f"{total_count}"
                )

                print(
                    f"Saved to: {output_path}"
                )

            except requests.RequestException as error:
                print(
                    f"Request failed on page "
                    f"{page}: {error}"
                )
                break

            except (
                ValueError,
                json.JSONDecodeError,
            ) as error:
                print(
                    f"Invalid response on page "
                    f"{page}: {error}"
                )
                break

        print(
            f"Query pages saved: {query_pages}"
        )

        print(
            f"Records received for query: "
            f"{query_records}"
        )

        print(
            f"Unique IDs for query: "
            f"{len(query_job_ids)}"
        )

    repeated_records = (
        total_records_received
        - len(all_job_ids)
    )

    print("\nEXTRACTION SUMMARY")
    print("=" * 65)

    print(
        f"Configured search queries: "
        f"{len(SEARCH_QUERIES)}"
    )

    print(
        f"Maximum pages per query: "
        f"{MAX_PAGES_PER_QUERY}"
    )

    print(
        f"Requests completed: "
        f"{requests_completed}"
    )

    print(
        f"Raw page files saved: "
        f"{pages_saved}"
    )

    print(
        f"Records received across pages: "
        f"{total_records_received}"
    )

    print(
        f"Unique job IDs observed: "
        f"{len(all_job_ids)}"
    )

    print(
        f"Repeated records across "
        f"queries/pages: {repeated_records}"
    )


if __name__ == "__main__":
    main()