from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATABASE_FILE = (
    PROJECT_ROOT
    / "data"
    / "database"
    / "datarole_radar.db"
)

PROCESSED_DIRECTORY = (
    PROJECT_ROOT
    / "data"
    / "processed"
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


def connect() -> sqlite3.Connection:
    """Open the analytical warehouse with FK enforcement."""

    connection = sqlite3.connect(
        DATABASE_FILE
    )

    connection.execute(
        "PRAGMA foreign_keys = ON;"
    )

    return connection


def test_database_file_exists() -> None:
    """The warehouse database must exist."""

    assert DATABASE_FILE.exists(), (
        f"Database not found: "
        f"{DATABASE_FILE}"
    )


def test_expected_tables_exist() -> None:
    """Required warehouse tables must exist."""

    expected_tables = {
        "sources",
        "jobs",
        "skills",
        "job_skills",
        "pipeline_runs",
    }

    with connect() as connection:
        rows = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table';
            """
        ).fetchall()

    actual_tables = {
        row[0]
        for row in rows
        if not row[0].startswith(
            "sqlite_"
        )
    }

    assert expected_tables.issubset(
        actual_tables
    ), (
        "Missing warehouse tables: "
        f"{sorted(expected_tables - actual_tables)}"
    )


def test_database_counts_match_csv_inputs() -> None:
    """Database row counts must reconcile with source CSVs."""

    jobs = pd.read_csv(
        JOBS_FILE
    )

    skills = pd.read_csv(
        SKILLS_FILE
    )

    job_skills = pd.read_csv(
        JOB_SKILLS_FILE
    )

    with connect() as connection:
        database_counts = {
            "jobs": connection.execute(
                "SELECT COUNT(*) FROM jobs;"
            ).fetchone()[0],
            "skills": connection.execute(
                "SELECT COUNT(*) FROM skills;"
            ).fetchone()[0],
            "job_skills": connection.execute(
                """
                SELECT COUNT(*)
                FROM job_skills;
                """
            ).fetchone()[0],
        }

    expected_counts = {
        "jobs": len(jobs),
        "skills": len(skills),
        "job_skills": len(
            job_skills
        ),
    }

    assert (
        database_counts
        == expected_counts
    )


def test_source_count_matches_jobs() -> None:
    """Sources dimension must match unique job sources."""

    jobs = pd.read_csv(
        JOBS_FILE,
        dtype={
            "source": "string",
        },
    )

    expected_sources = (
        jobs["source"]
        .dropna()
        .str.strip()
        .nunique()
    )

    with connect() as connection:
        actual_sources = (
            connection.execute(
                """
                SELECT COUNT(*)
                FROM sources;
                """
            ).fetchone()[0]
        )

    assert (
        actual_sources
        == expected_sources
    )


def test_foreign_key_integrity() -> None:
    """No foreign-key violations may exist."""

    with connect() as connection:
        errors = connection.execute(
            "PRAGMA foreign_key_check;"
        ).fetchall()

    assert errors == [], (
        "Foreign-key violations found: "
        f"{errors}"
    )


def test_sqlite_integrity() -> None:
    """SQLite database file must pass integrity checking."""

    with connect() as connection:
        result = connection.execute(
            "PRAGMA integrity_check;"
        ).fetchone()[0]

    assert result == "ok"


def test_job_skill_primary_key_is_unique() -> None:
    """Each job-skill pair must occur only once."""

    with connect() as connection:
        duplicates = (
            connection.execute(
                """
                SELECT
                    source_record_key,
                    skill_key,
                    COUNT(*) AS row_count
                FROM job_skills
                GROUP BY
                    source_record_key,
                    skill_key
                HAVING COUNT(*) > 1;
                """
            ).fetchall()
        )

    assert duplicates == [], (
        "Duplicate job-skill pairs found: "
        f"{duplicates}"
    )


def test_no_orphan_job_skill_relationships() -> None:
    """Every relationship must resolve to a job and skill."""

    with connect() as connection:
        orphan_jobs = (
            connection.execute(
                """
                SELECT COUNT(*)
                FROM job_skills js
                LEFT JOIN jobs j
                    ON js.source_record_key
                     = j.source_record_key
                WHERE j.source_record_key IS NULL;
                """
            ).fetchone()[0]
        )

        orphan_skills = (
            connection.execute(
                """
                SELECT COUNT(*)
                FROM job_skills js
                LEFT JOIN skills s
                    ON js.skill_key
                     = s.skill_key
                WHERE s.skill_key IS NULL;
                """
            ).fetchone()[0]
        )

    assert orphan_jobs == 0
    assert orphan_skills == 0


def test_jobs_table_contains_only_target_roles() -> None:
    """Warehouse jobs table should contain target jobs only."""

    with connect() as connection:
        non_target_count = (
            connection.execute(
                """
                SELECT COUNT(*)
                FROM jobs
                WHERE is_target_data_role != 1
                   OR is_target_data_role IS NULL;
                """
            ).fetchone()[0]
        )

    assert non_target_count == 0


def test_top_skill_matches_processed_relationships() -> None:
    """SQL aggregation must agree with processed CSV data."""

    relationships = pd.read_csv(
        JOB_SKILLS_FILE,
        dtype={
            "skill_key": "string",
        },
    )

    skills = pd.read_csv(
        SKILLS_FILE,
        dtype={
            "skill_key": "string",
        },
    )

    expected = (
        relationships
        .merge(
            skills,
            on="skill_key",
            how="left",
            validate="many_to_one",
        )
        .groupby(
            "skill_name"
        )
        .size()
        .sort_values(
            ascending=False
        )
    )

    expected_skill = (
        expected.index[0]
    )

    expected_count = int(
        expected.iloc[0]
    )

    with connect() as connection:
        actual = connection.execute(
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
            LIMIT 1;
            """
        ).fetchone()

    assert actual is not None

    actual_skill = actual[0]
    actual_count = actual[1]

    assert (
        actual_skill
        == expected_skill
    )

    assert (
        actual_count
        == expected_count
    )


def test_pipeline_run_metadata_matches_database() -> None:
    """Latest pipeline-run metadata must describe the warehouse."""

    with connect() as connection:
        latest_run = (
            connection.execute(
                """
                SELECT
                    sources_loaded,
                    jobs_loaded,
                    skills_loaded,
                    job_skills_loaded
                FROM pipeline_runs
                ORDER BY loaded_at DESC
                LIMIT 1;
                """
            ).fetchone()
        )

        actual_counts = (
            connection.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM sources),
                    (SELECT COUNT(*) FROM jobs),
                    (SELECT COUNT(*) FROM skills),
                    (SELECT COUNT(*) FROM job_skills);
                """
            ).fetchone()
        )

    assert latest_run is not None

    assert (
        latest_run
        == actual_counts
    )