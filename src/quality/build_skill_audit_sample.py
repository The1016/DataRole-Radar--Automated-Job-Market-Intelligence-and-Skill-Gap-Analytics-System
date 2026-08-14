from __future__ import annotations

from pathlib import Path
import re

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]

PROCESSED_DIRECTORY = (
    PROJECT_ROOT
    / "data"
    / "processed"
)

REPORTS_DIRECTORY = (
    PROJECT_ROOT
    / "reports"
)

JOBS_FILE = (
    PROCESSED_DIRECTORY
    / "master_target_roles.csv"
)

SKILLS_FILE = (
    PROCESSED_DIRECTORY
    / "skills.csv"
)

JOB_SKILLS_FILE = (
    PROCESSED_DIRECTORY
    / "job_skills.csv"
)

SKILL_SUMMARY_FILE = (
    REPORTS_DIRECTORY
    / "skill_extraction_audit.csv"
)

OUTPUT_FILE = (
    REPORTS_DIRECTORY
    / "skill_match_manual_audit.csv"
)


RISKY_SKILL_KEYS = [
    "dashboarding",
    "data_visualization",
    "communication",
    "problem_solving",
    "business_acumen",
    "apis",
    "microsoft_fabric",
    "statistics",
    "machine_learning",
    "data_quality",
]

SAMPLES_PER_RISKY_SKILL = 2
HIGH_SKILL_COUNT_JOBS = 10
RANDOM_STATE = 42


def clean_text(value: object) -> str:
    """Return a clean string for audit output."""

    if value is None or pd.isna(value):
        return ""

    return re.sub(
        pattern=r"\s+",
        repl=" ",
        string=str(value),
    ).strip()


def create_excerpt(
    job_title: object,
    tags: object,
    description: object,
    matched_aliases: object = "",
) -> str:
    """Create a short excerpt around a detected alias."""

    field_texts = [
        clean_text(job_title),
        clean_text(tags),
        clean_text(description),
    ]

    aliases = [
        alias.strip()
        for alias in clean_text(
            matched_aliases
        ).split("|")
        if alias.strip()
    ]

    for field_text in field_texts:
        if not field_text:
            continue

        for alias in aliases:
            alias_pattern = re.escape(
                alias
            ).replace(
                r"\ ",
                r"\s+",
            )

            match = re.search(
                alias_pattern,
                field_text,
                flags=re.IGNORECASE,
            )

            if match:
                start = max(
                    0,
                    match.start() - 120,
                )

                end = min(
                    len(field_text),
                    match.end() + 180,
                )

                excerpt = field_text[
                    start:end
                ]

                return clean_text(excerpt)

    description_text = clean_text(
        description
    )

    return description_text[:300]


def load_csv(
    file_path: Path,
) -> pd.DataFrame:
    """Load one required CSV file."""

    if not file_path.exists():
        raise FileNotFoundError(
            f"Required file not found: {file_path}"
        )

    return pd.read_csv(
        file_path,
        dtype={
            "source_record_key": "string",
            "source_job_id": "string",
        },
    )


def select_risky_skill_matches(
    relationships: pd.DataFrame,
) -> pd.DataFrame:
    """Select deterministic samples of broad skill matches."""

    samples = []

    for skill_key in RISKY_SKILL_KEYS:
        candidates = relationships[
            relationships["skill_key"]
            == skill_key
        ]

        if candidates.empty:
            continue

        sample_size = min(
            SAMPLES_PER_RISKY_SKILL,
            len(candidates),
        )

        sampled = candidates.sample(
            n=sample_size,
            random_state=RANDOM_STATE,
        )

        samples.append(sampled)

    if not samples:
        return pd.DataFrame()

    return pd.concat(
        samples,
        ignore_index=True,
    )


def build_audit_file() -> pd.DataFrame:
    """Create a manageable manual skill-audit sample."""

    jobs = load_csv(JOBS_FILE)
    skills = load_csv(SKILLS_FILE)
    job_skills = load_csv(
        JOB_SKILLS_FILE
    )
    skill_summary = load_csv(
        SKILL_SUMMARY_FILE
    )

    job_columns = [
        "source_record_key",
        "source",
        "source_job_id",
        "job_title_raw",
        "company_name",
        "role_family",
        "tags",
        "description_text",
        "job_url",
    ]

    relationships = (
        job_skills
        .merge(
            skills,
            how="left",
            on="skill_key",
            validate="many_to_one",
        )
        .merge(
            jobs[job_columns],
            how="left",
            on="source_record_key",
            validate="many_to_one",
        )
    )

    if relationships[
        "skill_name"
    ].isna().any():
        raise ValueError(
            "Some job-skill records do not "
            "match the skill dimension."
        )

    risky_matches = (
        select_risky_skill_matches(
            relationships
        )
    )

    risky_rows = []

    for _, row in risky_matches.iterrows():
        risky_rows.append(
            {
                "audit_type": (
                    "Potentially Ambiguous Match"
                ),
                "source_record_key": (
                    row["source_record_key"]
                ),
                "source": row["source"],
                "source_job_id": (
                    row["source_job_id"]
                ),
                "job_title_raw": (
                    row["job_title_raw"]
                ),
                "company_name": (
                    row["company_name"]
                ),
                "role_family": (
                    row["role_family"]
                ),
                "skill_key": (
                    row["skill_key"]
                ),
                "skill_name": (
                    row["skill_name"]
                ),
                "evidence_source": (
                    row["evidence_source"]
                ),
                "matched_aliases": (
                    row["matched_aliases"]
                ),
                "detected_skill_count": "",
                "detected_skills": "",
                "evidence_excerpt": (
                    create_excerpt(
                        job_title=(
                            row["job_title_raw"]
                        ),
                        tags=row["tags"],
                        description=(
                            row[
                                "description_text"
                            ]
                        ),
                        matched_aliases=(
                            row[
                                "matched_aliases"
                            ]
                        ),
                    )
                ),
                "job_url": row["job_url"],
            }
        )

    summary_with_jobs = (
        skill_summary
        .merge(
            jobs[
                [
                    "source_record_key",
                    "tags",
                    "description_text",
                    "job_url",
                ]
            ],
            how="left",
            on="source_record_key",
            validate="one_to_one",
        )
    )

    high_count_jobs = (
        summary_with_jobs
        .sort_values(
            by="detected_skill_count",
            ascending=False,
        )
        .head(HIGH_SKILL_COUNT_JOBS)
    )

    high_count_rows = []

    for _, row in high_count_jobs.iterrows():
        high_count_rows.append(
            {
                "audit_type": (
                    "High Detected Skill Count"
                ),
                "source_record_key": (
                    row["source_record_key"]
                ),
                "source": row["source"],
                "source_job_id": (
                    row["source_job_id"]
                ),
                "job_title_raw": (
                    row["job_title_raw"]
                ),
                "company_name": (
                    row["company_name"]
                ),
                "role_family": (
                    row["role_family"]
                ),
                "skill_key": "",
                "skill_name": "",
                "evidence_source": "",
                "matched_aliases": "",
                "detected_skill_count": (
                    row[
                        "detected_skill_count"
                    ]
                ),
                "detected_skills": (
                    row["detected_skills"]
                ),
                "evidence_excerpt": (
                    create_excerpt(
                        job_title=(
                            row["job_title_raw"]
                        ),
                        tags=row["tags"],
                        description=(
                            row[
                                "description_text"
                            ]
                        ),
                    )
                ),
                "job_url": row["job_url"],
            }
        )

    no_skill_jobs = summary_with_jobs[
        summary_with_jobs[
            "detected_skill_count"
        ].eq(0)
    ]

    no_skill_rows = []

    for _, row in no_skill_jobs.iterrows():
        no_skill_rows.append(
            {
                "audit_type": (
                    "No Skills Detected"
                ),
                "source_record_key": (
                    row["source_record_key"]
                ),
                "source": row["source"],
                "source_job_id": (
                    row["source_job_id"]
                ),
                "job_title_raw": (
                    row["job_title_raw"]
                ),
                "company_name": (
                    row["company_name"]
                ),
                "role_family": (
                    row["role_family"]
                ),
                "skill_key": "",
                "skill_name": "",
                "evidence_source": "",
                "matched_aliases": "",
                "detected_skill_count": 0,
                "detected_skills": "",
                "evidence_excerpt": (
                    create_excerpt(
                        job_title=(
                            row["job_title_raw"]
                        ),
                        tags=row["tags"],
                        description=(
                            row[
                                "description_text"
                            ]
                        ),
                    )
                ),
                "job_url": row["job_url"],
            }
        )

    audit = pd.DataFrame(
        risky_rows
        + high_count_rows
        + no_skill_rows
    )

    audit = audit.drop_duplicates(
        subset=[
            "audit_type",
            "source_record_key",
            "skill_key",
        ],
        keep="first",
    )

    audit["manual_decision"] = ""
    audit["correct_skill_or_action"] = ""
    audit["review_notes"] = ""

    output_columns = [
        "audit_type",
        "source_record_key",
        "source",
        "source_job_id",
        "job_title_raw",
        "company_name",
        "role_family",
        "skill_key",
        "skill_name",
        "evidence_source",
        "matched_aliases",
        "detected_skill_count",
        "detected_skills",
        "evidence_excerpt",
        "manual_decision",
        "correct_skill_or_action",
        "review_notes",
        "job_url",
    ]

    return audit[
        output_columns
    ].reset_index(drop=True)


def main() -> None:
    """Create the manual skill-extraction audit file."""

    audit = build_audit_file()

    REPORTS_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    audit.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    print("SKILL MATCH AUDIT PREPARATION")
    print("=" * 65)

    print(
        f"Audit rows created: "
        f"{len(audit)}"
    )

    print("\nROWS BY AUDIT TYPE")
    print("-" * 65)

    print(
        audit["audit_type"]
        .value_counts()
        .to_string()
    )

    print("\nFILE CREATED")
    print("-" * 65)
    print(OUTPUT_FILE)


if __name__ == "__main__":
    main()