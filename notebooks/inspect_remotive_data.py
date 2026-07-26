import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DATA_DIRECTORY = PROJECT_ROOT / "data" / "raw"

json_files = sorted(
    RAW_DATA_DIRECTORY.glob("remotive_jobs_*.json")
)

if not json_files:
    raise FileNotFoundError("No Remotive JSON files were found.")

latest_file = json_files[-1]

with latest_file.open("r", encoding="utf-8") as file:
    payload = json.load(file)

jobs = payload.get("jobs", [])

print(f"File: {latest_file.name}")
print(f"Top-level fields: {list(payload.keys())}")
print(f"Number of jobs: {len(jobs)}")

if jobs:
    print("\nFields in one job record:")
    for field in jobs[0].keys():
        print(f"- {field}")

    print("\nFirst job:")
    print(f"Title: {jobs[0].get('title')}")
    print(f"Company: {jobs[0].get('company_name')}")
    print(f"Location: {jobs[0].get('candidate_required_location')}")
    print(f"URL: {jobs[0].get('url')}")