from datetime import datetime, timezone
import json
from pathlib import Path

import requests


API_URL = "https://remotive.com/api/remote-jobs"

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DATA_DIRECTORY = PROJECT_ROOT / "data" / "raw"


def fetch_jobs() -> dict:
    """Request the latest job listings from the Remotive API."""

    headers = {
        "User-Agent": "DataRole-Radar-Portfolio-Project"
    }

    response = requests.get(
        API_URL,
        headers=headers,
        timeout=30,
    )

    response.raise_for_status()

    payload = response.json()

    jobs = payload.get("jobs")

    if not isinstance(jobs, list):
        raise ValueError(
            "The API response does not contain a valid jobs list."
        )

    return payload


def save_raw_snapshot(payload: dict) -> Path:
    """Save the complete API response as a timestamped JSON file."""

    RAW_DATA_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = datetime.now(timezone.utc).strftime(
        "%Y%m%d_%H%M%S"
    )

    output_path = (
        RAW_DATA_DIRECTORY
        / f"remotive_jobs_{timestamp}.json"
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
    """Run the first stage of the extraction pipeline."""

    try:
        payload = fetch_jobs()
        output_path = save_raw_snapshot(payload)

        job_count = len(payload["jobs"])

        print("Extraction completed successfully.")
        print(f"Jobs received: {job_count}")
        print(f"Raw file saved to: {output_path}")

    except requests.RequestException as error:
        print(f"API request failed: {error}")
        raise SystemExit(1) from error

    except (ValueError, json.JSONDecodeError) as error:
        print(f"Invalid API response: {error}")
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()