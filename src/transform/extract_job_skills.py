from __future__ import annotations

from pathlib import Path
import re

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]

PROCESSED_DATA_DIRECTORY = (
    PROJECT_ROOT
    / "data"
    / "processed"
)

REFERENCE_DATA_DIRECTORY = (
    PROJECT_ROOT
    / "data"
    / "reference"
)

REPORTS_DIRECTORY = (
    PROJECT_ROOT
    / "reports"
)

JOBS_INPUT_FILE = (
    PROCESSED_DATA_DIRECTORY
    / "master_target_roles.csv"
)

SKILL_DICTIONARY_FILE = (
    REFERENCE_DATA_DIRECTORY
    / "skill_dictionary.csv"
)

SKILLS_OUTPUT_FILE = (
    PROCESSED_DATA_DIRECTORY
    / "skills.csv"
)

JOB_SKILLS_OUTPUT_FILE = (
    PROCESSED_DATA_DIRECTORY
    / "job_skills.csv"
)

SKILL_AUDIT_OUTPUT_FILE = (
    REPORTS_DIRECTORY
    / "skill_extraction_audit.csv"
)

NO_SKILLS_OUTPUT_FILE = (
    REPORTS_DIRECTORY
    / "jobs_without_detected_skills.csv"
)


SEARCH_FIELDS = [
    "job_title_raw",
    "tags",
    "description_text",
]

SKILL_OVERRIDE_FILE = (
    REFERENCE_DATA_DIRECTORY
    / "skill_match_overrides.csv"
)


def clean_text(value: object) -> str:
    """Normalize text and remove URLs before skill matching."""

    if value is None or pd.isna(value):
        return ""

    text = str(value)

    # Remove URLs so terms such as "/api/"
    # cannot create false skill matches.
    text = re.sub(
        r"https?://\S+|www\.\S+",
        " ",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()

def is_statistics_education_only(
    text: str,
    match: re.Match[str],
) -> bool:
    """Detect Statistics mentions that only describe education fields."""

    context_start = max(
        0,
        match.start() - 120,
    )

    context_end = min(
        len(text),
        match.end() + 120,
    )

    context = text[
        context_start:context_end
    ].lower()

    education_terms = [
        "degree in",
        "degree from",
        "bachelor",
        "bachelor's",
        "masters",
        "master's",
        "phd",
        "field of study",
        "related field",
    ]

    applied_statistics_terms = [
        "statistical analysis",
        "statistical analyses",
        "statistical modeling",
        "statistical modelling",
        "hypothesis testing",
        "statistical methods",
        "statistical techniques",
        "statistical reasoning",
    ]

    has_education_context = any(
        term in context
        for term in education_terms
    )

    has_applied_context = any(
        term in context
        for term in applied_statistics_terms
    )

    return (
        has_education_context
        and not has_applied_context
    )


def build_alias_pattern(
    alias: str,
) -> re.Pattern[str]:
    """Build a case-insensitive whole-term regex pattern."""

    escaped_alias = re.escape(
        alias.strip()
    )

    # Allow one or more spaces wherever the alias
    # contains a normal space.
    escaped_alias = escaped_alias.replace(
        r"\ ",
        r"\s+",
    )

    return re.compile(
        pattern=(
            rf"(?<![A-Za-z0-9_])"
            rf"{escaped_alias}"
            rf"(?![A-Za-z0-9_])"
        ),
        flags=re.IGNORECASE,
    )


def load_skill_dictionary() -> pd.DataFrame:
    """Load and validate the canonical skill dictionary."""

    if not SKILL_DICTIONARY_FILE.exists():
        raise FileNotFoundError(
            "Skill dictionary not found: "
            f"{SKILL_DICTIONARY_FILE}"
        )

    skills = pd.read_csv(
        SKILL_DICTIONARY_FILE
    )

    required_columns = [
        "skill_key",
        "skill_name",
        "skill_category",
        "aliases",
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in skills.columns
    ]

    if missing_columns:
        raise ValueError(
            "Skill dictionary is missing columns: "
            f"{missing_columns}"
        )

    for column in required_columns:
        skills[column] = (
            skills[column]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    blank_rows = skills[
        skills[required_columns]
        .eq("")
        .any(axis=1)
    ]

    if not blank_rows.empty:
        raise ValueError(
            "The skill dictionary contains "
            "blank required values:\n"
            + blank_rows.to_string(index=False)
        )

    duplicate_keys = skills[
        "skill_key"
    ].duplicated(
        keep=False
    )

    if duplicate_keys.any():
        raise ValueError(
            "Duplicate skill keys found:\n"
            + skills.loc[
                duplicate_keys,
                [
                    "skill_key",
                    "skill_name",
                ],
            ].to_string(index=False)
        )

    duplicate_names = (
        skills["skill_name"]
        .str.casefold()
        .duplicated(
            keep=False
        )
    )

    if duplicate_names.any():
        raise ValueError(
            "Duplicate skill names found:\n"
            + skills.loc[
                duplicate_names,
                [
                    "skill_key",
                    "skill_name",
                ],
            ].to_string(index=False)
        )

    return skills

def load_skill_overrides() -> pd.DataFrame:
    """Load verified manual job-skill exceptions."""

    columns = [
        "source_record_key",
        "skill_key",
        "override_action",
        "reason",
    ]

    if not SKILL_OVERRIDE_FILE.exists():
        return pd.DataFrame(
            columns=columns
        )

    overrides = pd.read_csv(
        SKILL_OVERRIDE_FILE,
        dtype={
            "source_record_key": "string",
            "skill_key": "string",
        },
    )

    missing_columns = [
        column
        for column in columns
        if column not in overrides.columns
    ]

    if missing_columns:
        raise ValueError(
            "Skill override file is missing columns: "
            f"{missing_columns}"
        )

    for column in columns:
        overrides[column] = (
            overrides[column]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    allowed_actions = {
        "exclude",
    }

    invalid_actions = set(
        overrides["override_action"]
    ) - allowed_actions

    if invalid_actions:
        raise ValueError(
            "Invalid skill override actions: "
            f"{sorted(invalid_actions)}"
        )

    duplicate_mask = overrides.duplicated(
        subset=[
            "source_record_key",
            "skill_key",
        ],
        keep=False,
    )

    if duplicate_mask.any():
        raise ValueError(
            "Duplicate skill overrides found:\n"
            + overrides.loc[
                duplicate_mask,
                [
                    "source_record_key",
                    "skill_key",
                ],
            ].to_string(index=False)
        )

    return overrides

def apply_skill_overrides(
    job_skills: pd.DataFrame,
    overrides: pd.DataFrame,
) -> tuple[pd.DataFrame, int]:
    """Remove manually verified false-positive relationships."""

    if overrides.empty:
        return job_skills.copy(), 0

    exclusions = overrides[
        overrides["override_action"]
        == "exclude"
    ][
        [
            "source_record_key",
            "skill_key",
        ]
    ].copy()

    if exclusions.empty:
        return job_skills.copy(), 0

    reviewed = job_skills.merge(
        exclusions.assign(
            _manual_exclusion=True
        ),
        how="left",
        on=[
            "source_record_key",
            "skill_key",
        ],
        validate="one_to_one",
    )

    exclusion_mask = (
        reviewed["_manual_exclusion"]
        .fillna(False)
        .astype(bool)
    )

    removed_count = int(
        exclusion_mask.sum()
    )

    final_relationships = (
        reviewed.loc[
            ~exclusion_mask,
            job_skills.columns,
        ]
        .copy()
        .reset_index(drop=True)
    )

    return (
        final_relationships,
        removed_count,
    )



def compile_skill_patterns(
    skills: pd.DataFrame,
) -> dict[str, list[tuple[str, re.Pattern[str]]]]:
    """Compile every skill alias into reusable regex patterns."""

    compiled_patterns = {}

    for skill in skills.itertuples(
        index=False
    ):
        aliases = [
            alias.strip()
            for alias in skill.aliases.split("|")
            if alias.strip()
        ]

        if not aliases:
            raise ValueError(
                f"No aliases found for "
                f"skill: {skill.skill_name}"
            )

        compiled_patterns[
            skill.skill_key
        ] = [
            (
                alias,
                build_alias_pattern(alias),
            )
            for alias in aliases
        ]

    return compiled_patterns


def validate_jobs(
    jobs: pd.DataFrame,
) -> None:
    """Validate fields required for skill extraction."""

    required_columns = {
        "source_record_key",
        "source",
        "source_job_id",
        "job_title_raw",
        "company_name",
        "role_family",
        "tags",
        "description_text",
        "publication_date",
    }

    missing_columns = (
        required_columns
        - set(jobs.columns)
    )

    if missing_columns:
        raise ValueError(
            "Target-job data is missing columns: "
            f"{sorted(missing_columns)}"
        )

    duplicate_keys = jobs[
        "source_record_key"
    ].duplicated(
        keep=False
    )

    if duplicate_keys.any():
        raise ValueError(
            "Duplicate source_record_key values "
            "were found in the target-job data."
        )


def extract_job_skill_relationships(
    jobs: pd.DataFrame,
    skills: pd.DataFrame,
    compiled_patterns: dict[
        str,
        list[
            tuple[
                str,
                re.Pattern[str],
            ]
        ],
    ],
) -> pd.DataFrame:
    """Create one relationship per detected job and skill."""

    relationships = []

    skill_records = skills.to_dict(
        orient="records"
    )

    for _, job in jobs.iterrows():
        searchable_fields = {
            field: clean_text(job[field])
            for field in SEARCH_FIELDS
        }

        for skill in skill_records:
            skill_key = skill["skill_key"]

            evidence_fields = set()
            matched_aliases = set()

            for field_name, field_text in (
                searchable_fields.items()
            ):
                if not field_text:
                    continue

                for (
                    alias,
                    pattern,
                ) in compiled_patterns[
                    skill_key
                ]:
                    match = pattern.search(
                        field_text
                    )

                    if match:
                        if (
                                skill_key == "statistics"
                                and is_statistics_education_only(
                            field_text,
                            match,
                        )
                        ):
                            continue

                        evidence_fields.add(
                            field_name
                        )

                        matched_aliases.add(
                            alias
                        )

            if not evidence_fields:
                continue

            relationships.append(
                {
                    "source_record_key": (
                        job[
                            "source_record_key"
                        ]
                    ),
                    "skill_key": skill_key,
                    "evidence_source": (
                        "|".join(
                            sorted(
                                evidence_fields
                            )
                        )
                    ),
                    "matched_aliases": (
                        "|".join(
                            sorted(
                                matched_aliases,
                                key=str.casefold,
                            )
                        )
                    ),
                    "evidence_field_count": (
                        len(evidence_fields)
                    ),
                }
            )

    job_skills = pd.DataFrame(
        relationships,
        columns=[
            "source_record_key",
            "skill_key",
            "evidence_source",
            "matched_aliases",
            "evidence_field_count",
        ],
    )

    if job_skills.empty:
        raise ValueError(
            "No skills were detected in any target job."
        )

    duplicate_relationships = (
        job_skills.duplicated(
            subset=[
                "source_record_key",
                "skill_key",
            ],
            keep=False,
        )
    )

    if duplicate_relationships.any():
        raise ValueError(
            "Duplicate job-skill relationships "
            "were created."
        )

    return job_skills


def build_skill_audit(
    jobs: pd.DataFrame,
    skills: pd.DataFrame,
    job_skills: pd.DataFrame,
) -> pd.DataFrame:
    """Create one auditable skill summary for each job."""

    named_relationships = (
        job_skills.merge(
            skills[
                [
                    "skill_key",
                    "skill_name",
                ]
            ],
            how="left",
            on="skill_key",
            validate="many_to_one",
        )
    )

    skill_summary = (
        named_relationships
        .groupby(
            "source_record_key",
            as_index=False,
        )
        .agg(
            detected_skill_count=(
                "skill_key",
                "nunique",
            ),
            detected_skills=(
                "skill_name",
                lambda values: "|".join(
                    sorted(
                        set(values),
                        key=str.casefold,
                    )
                ),
            ),
        )
    )

    audit_columns = [
        "source_record_key",
        "source",
        "source_job_id",
        "job_title_raw",
        "company_name",
        "role_family",
        "publication_date",
    ]

    audit = jobs[
        audit_columns
    ].merge(
        skill_summary,
        how="left",
        on="source_record_key",
        validate="one_to_one",
    )

    audit[
        "detected_skill_count"
    ] = (
        audit[
            "detected_skill_count"
        ]
        .fillna(0)
        .astype(int)
    )

    audit["detected_skills"] = (
        audit["detected_skills"]
        .fillna("")
    )

    return (
        audit
        .sort_values(
            by=[
                "detected_skill_count",
                "role_family",
                "job_title_raw",
            ],
            ascending=[
                True,
                True,
                True,
            ],
        )
        .reset_index(drop=True)
    )


def print_skill_report(
    jobs: pd.DataFrame,
    skills: pd.DataFrame,
    job_skills: pd.DataFrame,
    audit: pd.DataFrame,
    overrides_applied: int,
) -> None:
    """Print skill-extraction coverage and frequency metrics."""

    jobs_with_skills = (
        audit[
            "detected_skill_count"
        ]
        .gt(0)
        .sum()
    )

    jobs_without_skills = (
        len(audit)
        - jobs_with_skills
    )

    coverage_rate = (
        jobs_with_skills / len(audit)
        if len(audit)
        else 0.0
    )

    average_skills_per_job = (
        len(job_skills) / len(jobs)
        if len(jobs)
        else 0.0
    )

    named_relationships = (
        job_skills.merge(
            skills[
                [
                    "skill_key",
                    "skill_name",
                    "skill_category",
                ]
            ],
            how="left",
            on="skill_key",
            validate="many_to_one",
        )
    )

    print("SKILL EXTRACTION REPORT")
    print("=" * 65)

    print(
        f"Target jobs processed: "
        f"{len(jobs)}"
    )

    print(
        f"Skills in dictionary: "
        f"{len(skills)}"
    )

    print(
        f"Job-skill relationships created: "
        f"{len(job_skills)}"
    )

    print(
        f"Jobs with detected skills: "
        f"{jobs_with_skills}"
    )

    print(
        f"Jobs without detected skills: "
        f"{jobs_without_skills}"
    )

    print(
        f"Skill coverage rate: "
        f"{coverage_rate:.2%}"
    )

    print(
        f"Average skills per job: "
        f"{average_skills_per_job:.2f}"
    )

    print("\nTOP 15 DETECTED SKILLS")
    print("-" * 65)

    skill_counts = (
        named_relationships[
            "skill_name"
        ]
        .value_counts()
        .head(15)
    )

    print(
        skill_counts.to_string()
    )

    print("\nRELATIONSHIPS BY SKILL CATEGORY")
    print("-" * 65)

    category_counts = (
        named_relationships[
            "skill_category"
        ]
        .value_counts()
    )

    print(
        category_counts.to_string()
    )


def main() -> None:
    """Extract structured skills from target job advertisements."""

    if not JOBS_INPUT_FILE.exists():
        raise FileNotFoundError(
            "Target jobs file not found: "
            f"{JOBS_INPUT_FILE}"
        )

    jobs = pd.read_csv(
        JOBS_INPUT_FILE,
        dtype={
            "source_job_id": "string",
            "source_record_key": "string",
        },
    )

    validate_jobs(jobs)

    skills = load_skill_dictionary()

    compiled_patterns = (
        compile_skill_patterns(
            skills
        )
    )

    job_skills = (
        extract_job_skill_relationships(
            jobs=jobs,
            skills=skills,
            compiled_patterns=(
                compiled_patterns
            ),
        )
    )

    skill_overrides = (
        load_skill_overrides()
    )

    job_skills, overrides_applied = (
        apply_skill_overrides(
            job_skills=job_skills,
            overrides=skill_overrides,
        )
    )

    audit = build_skill_audit(
        jobs=jobs,
        skills=skills,
        job_skills=job_skills,
    )

    jobs_without_skills = audit[
        audit[
            "detected_skill_count"
        ]
        .eq(0)
    ].copy()

    PROCESSED_DATA_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    REPORTS_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    skills[
        [
            "skill_key",
            "skill_name",
            "skill_category",
        ]
    ].to_csv(
        SKILLS_OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    job_skills.to_csv(
        JOB_SKILLS_OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    audit.to_csv(
        SKILL_AUDIT_OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    jobs_without_skills.to_csv(
        NO_SKILLS_OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    print_skill_report(
        jobs=jobs,
        skills=skills,
        job_skills=job_skills,
        audit=audit,
        overrides_applied=overrides_applied,
    )

    print("\nFILES CREATED")
    print("-" * 65)
    print(SKILLS_OUTPUT_FILE)
    print(JOB_SKILLS_OUTPUT_FILE)
    print(SKILL_AUDIT_OUTPUT_FILE)
    print(
        f"Verified skill overrides applied: "
        f"{overrides_applied}"
    )
    print(NO_SKILLS_OUTPUT_FILE)


if __name__ == "__main__":
    main()