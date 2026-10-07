from __future__ import annotations

import os
import sqlite3
import uuid

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]

PROCESSED_DIRECTORY = (
    PROJECT_ROOT
    / "data"
    / "processed"
)

DATABASE_DIRECTORY = (
    PROJECT_ROOT
    / "data"
    / "database"
)

SQL_DIRECTORY = (
    PROJECT_ROOT
    / "sql"
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

DATABASE_FILE = (
    DATABASE_DIRECTORY
    / "datarole_radar.db"
)

TEMP_DATABASE_FILE = (
    DATABASE_DIRECTORY
    / "datarole_radar.tmp.db"
)

ANALYTICAL_VIEWS_FILE = (
    SQL_DIRECTORY
    / "analytical_views.sql"
)


EXPECTED_JOB_COLUMNS = [
    "source_record_key",
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

EXPECTED_SKILL_COLUMNS = [
    "skill_key",
    "skill_name",
    "skill_category",
]

EXPECTED_JOB_SKILL_COLUMNS = [
    "source_record_key",
    "skill_key",
    "evidence_source",
    "matched_aliases",
    "evidence_field_count",
]

EXPECTED_ANALYTICAL_VIEWS = {
    "vw_skill_demand",
    "vw_role_summary",
    "vw_role_skill_demand",
    "vw_skill_cooccurrence",
    "vw_role_skill_cooccurrence",
    "vw_salary_by_role",
}


def validate_schema(
    dataframe: pd.DataFrame,
    expected_columns: list[str],
    dataset_name: str,
) -> None:
    """Fail immediately if an upstream CSV schema changes."""

    actual_columns = list(
        dataframe.columns
    )

    if actual_columns != expected_columns:
        raise ValueError(
            f"{dataset_name} schema mismatch.\n"
            f"Expected: {expected_columns}\n"
            f"Actual:   {actual_columns}"
        )


def normalize_text(
    value: object,
) -> str | None:
    """Convert blank/NaN values into SQLite NULL."""

    if value is None or pd.isna(value):
        return None

    text = str(value).strip()

    if not text:
        return None

    return text


def normalize_float(
    value: object,
) -> float | None:
    """Convert numeric CSV values to float or NULL."""

    if value is None or pd.isna(value):
        return None

    return float(value)


def normalize_integer(
    value: object,
) -> int | None:
    """Convert numeric CSV values to integer or NULL."""

    if value is None or pd.isna(value):
        return None

    return int(value)


def normalize_boolean(
    value: object,
) -> int | None:
    """Convert boolean-like CSV values to SQLite 0/1."""

    if value is None or pd.isna(value):
        return None

    normalized = (
        str(value)
        .strip()
        .lower()
    )

    true_values = {
        "true",
        "1",
        "yes",
        "y",
    }

    false_values = {
        "false",
        "0",
        "no",
        "n",
    }

    if normalized in true_values:
        return 1

    if normalized in false_values:
        return 0

    raise ValueError(
        f"Cannot convert value to boolean: {value!r}"
    )


def load_input_data() -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
]:
    """Load and validate the three warehouse input datasets."""

    jobs = pd.read_csv(
        JOBS_FILE,
        dtype={
            "source_record_key": "string",
            "source": "string",
            "source_job_id": "string",
        },
    )

    skills = pd.read_csv(
        SKILLS_FILE,
        dtype={
            "skill_key": "string",
        },
    )

    job_skills = pd.read_csv(
        JOB_SKILLS_FILE,
        dtype={
            "source_record_key": "string",
            "skill_key": "string",
        },
    )

    validate_schema(
        jobs,
        EXPECTED_JOB_COLUMNS,
        "master_target_roles.csv",
    )

    validate_schema(
        skills,
        EXPECTED_SKILL_COLUMNS,
        "skills.csv",
    )

    validate_schema(
        job_skills,
        EXPECTED_JOB_SKILL_COLUMNS,
        "job_skills.csv",
    )

    return (
        jobs,
        skills,
        job_skills,
    )


def validate_input_data(
    jobs: pd.DataFrame,
    skills: pd.DataFrame,
    job_skills: pd.DataFrame,
) -> None:
    """Validate relational assumptions before database loading."""

    if jobs["source_record_key"].isna().any():
        raise ValueError(
            "Jobs contain missing source_record_key values."
        )

    if jobs["source_record_key"].duplicated().any():
        raise ValueError(
            "Jobs contain duplicate source_record_key values."
        )

    if skills["skill_key"].isna().any():
        raise ValueError(
            "Skills contain missing skill_key values."
        )

    if skills["skill_key"].duplicated().any():
        raise ValueError(
            "Skills contain duplicate skill_key values."
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
            "Duplicate job-skill relationships found."
        )

    valid_job_keys = set(
        jobs["source_record_key"]
        .dropna()
        .astype(str)
    )

    valid_skill_keys = set(
        skills["skill_key"]
        .dropna()
        .astype(str)
    )

    relationship_job_keys = set(
        job_skills["source_record_key"]
        .dropna()
        .astype(str)
    )

    relationship_skill_keys = set(
        job_skills["skill_key"]
        .dropna()
        .astype(str)
    )

    missing_job_keys = (
        relationship_job_keys
        - valid_job_keys
    )

    missing_skill_keys = (
        relationship_skill_keys
        - valid_skill_keys
    )

    if missing_job_keys:
        raise ValueError(
            "job_skills contains unknown job keys: "
            f"{sorted(missing_job_keys)}"
        )

    if missing_skill_keys:
        raise ValueError(
            "job_skills contains unknown skill keys: "
            f"{sorted(missing_skill_keys)}"
        )

    target_values = (
        jobs["is_target_data_role"]
        .map(normalize_boolean)
    )

    if not target_values.eq(1).all():
        raise ValueError(
            "master_target_roles.csv contains "
            "non-target jobs."
        )

    salary_rows = jobs[
        jobs["salary_min"].notna()
        & jobs["salary_max"].notna()
    ].copy()

    salary_min = pd.to_numeric(
        salary_rows["salary_min"],
        errors="coerce",
    )

    salary_max = pd.to_numeric(
        salary_rows["salary_max"],
        errors="coerce",
    )

    invalid_salary = (
        salary_min
        > salary_max
    )

    if invalid_salary.any():
        raise ValueError(
            "Found salary_min greater than salary_max."
        )


def create_schema(
    connection: sqlite3.Connection,
) -> None:
    """Create relational warehouse tables and indexes."""

    connection.executescript(
        """
        PRAGMA foreign_keys = ON;

        CREATE TABLE sources (
            source TEXT PRIMARY KEY
        );

        CREATE TABLE jobs (
            source_record_key TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            source_job_id TEXT NOT NULL,
            job_fingerprint TEXT,
            job_title_raw TEXT NOT NULL,
            automated_role_family TEXT,
            role_family TEXT NOT NULL,
            is_target_data_role INTEGER NOT NULL
                CHECK (
                    is_target_data_role IN (0, 1)
                ),
            classification_method TEXT,
            role_override_applied INTEGER
                CHECK (
                    role_override_applied
                    IN (0, 1)
                    OR role_override_applied IS NULL
                ),
            override_decision TEXT,
            company_name TEXT,
            company_logo_url TEXT,
            category TEXT,
            tags TEXT,
            job_type TEXT,
            seniority_raw TEXT,
            publication_date TEXT,
            expiry_date TEXT,
            location_raw TEXT,
            timezone_raw TEXT,
            is_worldwide INTEGER
                CHECK (
                    is_worldwide
                    IN (0, 1)
                    OR is_worldwide IS NULL
                ),
            salary_min REAL,
            salary_max REAL,
            salary_currency TEXT,
            salary_period TEXT,
            salary_raw TEXT,
            description_text TEXT,
            job_url TEXT,
            search_queries TEXT,
            collected_at TEXT,

            FOREIGN KEY (source)
                REFERENCES sources(source)
        );

        CREATE TABLE skills (
            skill_key TEXT PRIMARY KEY,
            skill_name TEXT NOT NULL,
            skill_category TEXT NOT NULL
        );

        CREATE TABLE job_skills (
            source_record_key TEXT NOT NULL,
            skill_key TEXT NOT NULL,
            evidence_source TEXT,
            matched_aliases TEXT,
            evidence_field_count INTEGER NOT NULL
                CHECK (
                    evidence_field_count >= 1
                ),

            PRIMARY KEY (
                source_record_key,
                skill_key
            ),

            FOREIGN KEY (
                source_record_key
            )
                REFERENCES jobs(
                    source_record_key
                )
                ON DELETE CASCADE,

            FOREIGN KEY (
                skill_key
            )
                REFERENCES skills(
                    skill_key
                )
                ON DELETE CASCADE
        );

        CREATE TABLE pipeline_runs (
            run_id TEXT PRIMARY KEY,
            loaded_at TEXT NOT NULL,
            sources_loaded INTEGER NOT NULL,
            jobs_loaded INTEGER NOT NULL,
            skills_loaded INTEGER NOT NULL,
            job_skills_loaded INTEGER NOT NULL
        );

        CREATE INDEX idx_jobs_source
            ON jobs(source);

        CREATE INDEX idx_jobs_role_family
            ON jobs(role_family);

        CREATE INDEX idx_jobs_publication_date
            ON jobs(publication_date);

        CREATE INDEX idx_jobs_company_name
            ON jobs(company_name);

        CREATE INDEX idx_jobs_salary_currency
            ON jobs(salary_currency);

        CREATE INDEX idx_skills_category
            ON skills(skill_category);

        CREATE INDEX idx_job_skills_skill
            ON job_skills(skill_key);
        """
    )


def create_analytical_views(
    connection: sqlite3.Connection,
) -> None:
    """Create reporting views from the external SQL file."""

    if not ANALYTICAL_VIEWS_FILE.exists():
        raise FileNotFoundError(
            "Analytical views SQL file not found: "
            f"{ANALYTICAL_VIEWS_FILE}"
        )

    sql_script = (
        ANALYTICAL_VIEWS_FILE
        .read_text(
            encoding="utf-8"
        )
    )

    if not sql_script.strip():
        raise ValueError(
            "Analytical views SQL file is empty."
        )

    connection.executescript(
        sql_script
    )


def insert_sources(
    connection: sqlite3.Connection,
    jobs: pd.DataFrame,
) -> int:
    """Load unique source names."""

    sources = sorted(
        jobs["source"]
        .dropna()
        .astype(str)
        .str.strip()
        .unique()
    )

    connection.executemany(
        """
        INSERT INTO sources (
            source
        )
        VALUES (?);
        """,
        [
            (source,)
            for source in sources
        ],
    )

    return len(sources)


def insert_jobs(
    connection: sqlite3.Connection,
    jobs: pd.DataFrame,
) -> None:
    """Load target jobs into SQLite."""

    rows = []

    for row in jobs.itertuples(
        index=False
    ):
        rows.append(
            (
                normalize_text(
                    row.source_record_key
                ),
                normalize_text(
                    row.source
                ),
                normalize_text(
                    row.source_job_id
                ),
                normalize_text(
                    row.job_fingerprint
                ),
                normalize_text(
                    row.job_title_raw
                ),
                normalize_text(
                    row.automated_role_family
                ),
                normalize_text(
                    row.role_family
                ),
                normalize_boolean(
                    row.is_target_data_role
                ),
                normalize_text(
                    row.classification_method
                ),
                normalize_boolean(
                    row.role_override_applied
                ),
                normalize_text(
                    row.override_decision
                ),
                normalize_text(
                    row.company_name
                ),
                normalize_text(
                    row.company_logo_url
                ),
                normalize_text(
                    row.category
                ),
                normalize_text(
                    row.tags
                ),
                normalize_text(
                    row.job_type
                ),
                normalize_text(
                    row.seniority_raw
                ),
                normalize_text(
                    row.publication_date
                ),
                normalize_text(
                    row.expiry_date
                ),
                normalize_text(
                    row.location_raw
                ),
                normalize_text(
                    row.timezone_raw
                ),
                normalize_boolean(
                    row.is_worldwide
                ),
                normalize_float(
                    row.salary_min
                ),
                normalize_float(
                    row.salary_max
                ),
                normalize_text(
                    row.salary_currency
                ),
                normalize_text(
                    row.salary_period
                ),
                normalize_text(
                    row.salary_raw
                ),
                normalize_text(
                    row.description_text
                ),
                normalize_text(
                    row.job_url
                ),
                normalize_text(
                    row.search_queries
                ),
                normalize_text(
                    row.collected_at
                ),
            )
        )

    connection.executemany(
        """
        INSERT INTO jobs (
            source_record_key,
            source,
            source_job_id,
            job_fingerprint,
            job_title_raw,
            automated_role_family,
            role_family,
            is_target_data_role,
            classification_method,
            role_override_applied,
            override_decision,
            company_name,
            company_logo_url,
            category,
            tags,
            job_type,
            seniority_raw,
            publication_date,
            expiry_date,
            location_raw,
            timezone_raw,
            is_worldwide,
            salary_min,
            salary_max,
            salary_currency,
            salary_period,
            salary_raw,
            description_text,
            job_url,
            search_queries,
            collected_at
        )
        VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?
        );
        """,
        rows,
    )


def insert_skills(
    connection: sqlite3.Connection,
    skills: pd.DataFrame,
) -> None:
    """Load canonical skill dimension."""

    rows = [
        (
            normalize_text(
                row.skill_key
            ),
            normalize_text(
                row.skill_name
            ),
            normalize_text(
                row.skill_category
            ),
        )
        for row in skills.itertuples(
            index=False
        )
    ]

    connection.executemany(
        """
        INSERT INTO skills (
            skill_key,
            skill_name,
            skill_category
        )
        VALUES (?, ?, ?);
        """,
        rows,
    )


def insert_job_skills(
    connection: sqlite3.Connection,
    job_skills: pd.DataFrame,
) -> None:
    """Load the many-to-many job-skill bridge."""

    rows = [
        (
            normalize_text(
                row.source_record_key
            ),
            normalize_text(
                row.skill_key
            ),
            normalize_text(
                row.evidence_source
            ),
            normalize_text(
                row.matched_aliases
            ),
            normalize_integer(
                row.evidence_field_count
            ),
        )
        for row in job_skills.itertuples(
            index=False
        )
    ]

    connection.executemany(
        """
        INSERT INTO job_skills (
            source_record_key,
            skill_key,
            evidence_source,
            matched_aliases,
            evidence_field_count
        )
        VALUES (?, ?, ?, ?, ?);
        """,
        rows,
    )


def insert_pipeline_run(
    connection: sqlite3.Connection,
    source_count: int,
    job_count: int,
    skill_count: int,
    relationship_count: int,
) -> None:
    """Record metadata for this warehouse build."""

    run_id = str(
        uuid.uuid4()
    )

    loaded_at = (
        datetime.now(
            timezone.utc
        )
        .isoformat(
            timespec="seconds"
        )
        .replace(
            "+00:00",
            "Z",
        )
    )

    connection.execute(
        """
        INSERT INTO pipeline_runs (
            run_id,
            loaded_at,
            sources_loaded,
            jobs_loaded,
            skills_loaded,
            job_skills_loaded
        )
        VALUES (?, ?, ?, ?, ?, ?);
        """,
        (
            run_id,
            loaded_at,
            source_count,
            job_count,
            skill_count,
            relationship_count,
        ),
    )


def validate_database(
    connection: sqlite3.Connection,
    expected_jobs: int,
    expected_skills: int,
    expected_relationships: int,
    expected_sources: int,
) -> None:
    """Run post-load reconciliation and integrity checks."""

    counts = {
        "jobs": connection.execute(
            "SELECT COUNT(*) FROM jobs"
        ).fetchone()[0],

        "skills": connection.execute(
            "SELECT COUNT(*) FROM skills"
        ).fetchone()[0],

        "job_skills": connection.execute(
            "SELECT COUNT(*) FROM job_skills"
        ).fetchone()[0],

        "sources": connection.execute(
            "SELECT COUNT(*) FROM sources"
        ).fetchone()[0],
    }

    expected = {
        "jobs": expected_jobs,
        "skills": expected_skills,
        "job_skills": expected_relationships,
        "sources": expected_sources,
    }

    if counts != expected:
        raise ValueError(
            "Warehouse count reconciliation failed.\n"
            f"Expected: {expected}\n"
            f"Actual:   {counts}"
        )

    foreign_key_errors = (
        connection.execute(
            "PRAGMA foreign_key_check;"
        ).fetchall()
    )

    if foreign_key_errors:
        raise ValueError(
            "SQLite foreign-key validation failed: "
            f"{foreign_key_errors}"
        )

    integrity_result = (
        connection.execute(
            "PRAGMA integrity_check;"
        ).fetchone()[0]
    )

    if integrity_result != "ok":
        raise ValueError(
            "SQLite integrity check failed: "
            f"{integrity_result}"
        )

    orphan_jobs = connection.execute(
        """
        SELECT COUNT(*)
        FROM job_skills js

        LEFT JOIN jobs j
            ON js.source_record_key
             = j.source_record_key

        WHERE j.source_record_key IS NULL;
        """
    ).fetchone()[0]

    orphan_skills = connection.execute(
        """
        SELECT COUNT(*)
        FROM job_skills js

        LEFT JOIN skills s
            ON js.skill_key
             = s.skill_key

        WHERE s.skill_key IS NULL;
        """
    ).fetchone()[0]

    if orphan_jobs != 0:
        raise ValueError(
            f"Found {orphan_jobs} "
            "orphan job relationships."
        )

    if orphan_skills != 0:
        raise ValueError(
            f"Found {orphan_skills} "
            "orphan skill relationships."
        )

    actual_views = {
        row[0]
        for row in connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'view';
            """
        ).fetchall()
    }

    missing_views = (
        EXPECTED_ANALYTICAL_VIEWS
        - actual_views
    )

    if missing_views:
        raise ValueError(
            "Missing analytical views: "
            f"{sorted(missing_views)}"
        )


def print_report(
    connection: sqlite3.Connection,
) -> None:
    """Print warehouse build summary."""

    source_count = connection.execute(
        "SELECT COUNT(*) FROM sources"
    ).fetchone()[0]

    job_count = connection.execute(
        "SELECT COUNT(*) FROM jobs"
    ).fetchone()[0]

    skill_count = connection.execute(
        "SELECT COUNT(*) FROM skills"
    ).fetchone()[0]

    relationship_count = connection.execute(
        "SELECT COUNT(*) FROM job_skills"
    ).fetchone()[0]

    view_count = connection.execute(
        """
        SELECT COUNT(*)
        FROM sqlite_master
        WHERE type = 'view';
        """
    ).fetchone()[0]

    print()
    print("# SQLITE WAREHOUSE REPORT")
    print()

    print(
        f"Sources loaded: "
        f"{source_count}"
    )

    print(
        f"Jobs loaded: "
        f"{job_count}"
    )

    print(
        f"Skills loaded: "
        f"{skill_count}"
    )

    print(
        "Job-skill relationships loaded: "
        f"{relationship_count}"
    )

    print(
        "Analytical views created: "
        f"{view_count}"
    )

    print(
        "Foreign key integrity: PASS"
    )

    print(
        "SQLite integrity check: PASS"
    )

    print()
    print("## JOBS BY SOURCE")
    print()

    source_rows = connection.execute(
        """
        SELECT
            source,
            COUNT(*) AS job_count

        FROM jobs

        GROUP BY
            source

        ORDER BY
            job_count DESC;
        """
    ).fetchall()

    for source, count in source_rows:
        print(
            f"{source}: {count}"
        )

    print()
    print("## TOP 10 SKILLS")
    print()

    skill_rows = connection.execute(
        """
        SELECT
            s.skill_name,
            COUNT(*) AS job_count

        FROM job_skills js

        JOIN skills s
            ON js.skill_key
             = s.skill_key

        GROUP BY
            s.skill_key,
            s.skill_name

        ORDER BY
            job_count DESC,
            s.skill_name

        LIMIT 10;
        """
    ).fetchall()

    for skill_name, count in skill_rows:
        print(
            f"{skill_name}: {count}"
        )

    print()
    print("## ANALYTICAL VIEWS")
    print()

    view_rows = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'view'
        ORDER BY name;
        """
    ).fetchall()

    for (view_name,) in view_rows:
        print(
            view_name
        )

    print()
    print("## DATABASE CREATED")
    print()

    print(
        DATABASE_FILE
    )


def build_warehouse() -> None:
    """Build an atomic SQLite analytical warehouse."""

    DATABASE_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    jobs, skills, job_skills = (
        load_input_data()
    )

    validate_input_data(
        jobs=jobs,
        skills=skills,
        job_skills=job_skills,
    )

    if TEMP_DATABASE_FILE.exists():
        TEMP_DATABASE_FILE.unlink()

    connection = sqlite3.connect(
        TEMP_DATABASE_FILE
    )

    try:
        connection.execute(
            "PRAGMA foreign_keys = ON;"
        )

        # 1. Create relational tables/indexes.
        create_schema(
            connection
        )

        # 2. Create all analytical SQL views.
        #
        # Views only require the referenced tables
        # to exist. The tables do not need rows yet.
        create_analytical_views(
            connection
        )

        # 3. Load source dimension.
        source_count = insert_sources(
            connection,
            jobs,
        )

        # 4. Load target jobs.
        insert_jobs(
            connection,
            jobs,
        )

        # 5. Load canonical skills.
        insert_skills(
            connection,
            skills,
        )

        # 6. Load job-skill bridge.
        insert_job_skills(
            connection,
            job_skills,
        )

        # 7. Record warehouse-build metadata.
        insert_pipeline_run(
            connection=connection,
            source_count=source_count,
            job_count=len(jobs),
            skill_count=len(skills),
            relationship_count=len(
                job_skills
            ),
        )

        # 8. Validate the completed warehouse.
        validate_database(
            connection=connection,
            expected_jobs=len(jobs),
            expected_skills=len(skills),
            expected_relationships=len(
                job_skills
            ),
            expected_sources=source_count,
        )

        # 9. Commit only after validation passes.
        connection.commit()

        # 10. Print successful build report.
        print_report(
            connection
        )

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()

    # Replace the production DB only after the
    # temporary database has built successfully.
    os.replace(
        TEMP_DATABASE_FILE,
        DATABASE_FILE,
    )


if __name__ == "__main__":
    build_warehouse()