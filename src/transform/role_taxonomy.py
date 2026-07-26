from __future__ import annotations

from pathlib import Path
import re

import pandas as pd


ROLE_PATTERNS: tuple[tuple[str, str], ...] = (
    (
        "Analytics Engineer",
        r"\banalytics?\s+engineer\b|"
        r"\banalytics?\s+engineering\b",
    ),
    (
        "Data Engineer",
        r"\bdata\s+engineer\b|"
        r"\bdata\s+engineering\b|"
        r"\bdata\s+platform\s+engineer\b",
    ),
    (
        "Data Scientist",
        r"\bdata\s+scientist\b|"
        r"\bdata\s+science\b",
    ),
    (
        "Machine Learning",
        r"\bmachine\s+learning\b|"
        r"\bml\s+engineer\b|"
        r"\bml\s+scientist\b",
    ),
    (
        "BI Developer",
        r"\bpower\s*bi\s+"
        r"(?:developer|engineer|architect|consultant|specialist)\b|"
        r"\b(?:bi|business\s+intelligence)\s+"
        r"(?:developer|engineer|architect|consultant)\b|"
        r"\bengineer\b.*\bbusiness\s+intelligence\b",
    ),
    (
        "BI Analyst",
        r"\b(?:bi|business\s+intelligence)\s+analyst\b|"
        r"\bbus(?:iness)?\s+intellig(?:ence)?\s+analyst\b",
    ),
    (
        "Data Analyst",
        r"\bdata\s+analyst\b|"
        r"\bdata\s+analytics?\s+specialist\b",
    ),
    (
        "Decision Science",
        r"\bdecision\s+scientist\b|"
        r"\bdecision\s+science\s+analyst\b",
    ),
    (
        "Business Analyst",
        r"\bbusiness\s+analyst\b",
    ),
    (
        "Reporting Analyst",
        r"\breporting\s+analyst\b",
    ),
    (
        "Product Analyst",
        r"\bproduct\s+analyst\b",
    ),
    (
        "Marketing Analyst",
        r"\bmarketing\s+analyst\b",
    ),
    (
        "Operations Analyst",
        r"\boperations?\s+analyst\b",
    ),
    (
        "Insights Analyst",
        r"\binsights?\s+analyst\b",
    ),
    (
        "Analytics Manager",
        r"\banalytics?\s+manager\b|"
        r"\bbusiness\s+analytics?\s+manager\b|"
        r"\banalytics?\s+director\b|"
        r"\bdirector\b.*\banalytics?\b|"
        r"\bhead\s+of\s+analytics?\b",
    ),
    (
        "Other Analytics",
        r"\banalytics?\b",
    ),
)


ALLOWED_ROLE_FAMILIES = {
    "Data Analyst",
    "BI Analyst",
    "BI Developer",
    "Business Analyst",
    "Reporting Analyst",
    "Operations Analyst",
    "Insights Analyst",
    "Product Analyst",
    "Marketing Analyst",
    "Decision Science",
    "Data Scientist",
    "Data Engineer",
    "Analytics Engineer",
    "Machine Learning",
    "Analytics Manager",
    "Other Analytics",
    "Non-target Role",
}


def normalize_title(value: object) -> str:
    """Create a consistent title for rule-based matching."""

    if value is None:
        return ""

    text = str(value)

    text = re.sub(
        pattern=r"\s+",
        repl=" ",
        string=text,
    )

    return text.strip().lower()


def classify_role(job_title: object) -> str:
    """Predict a standardized role family from the job title."""

    normalized_title = normalize_title(
        job_title
    )

    for role_family, pattern in ROLE_PATTERNS:
        if re.search(
            pattern,
            normalized_title,
        ):
            return role_family

    return "Non-target Role"


def load_role_overrides(
    override_file: Path,
) -> pd.DataFrame:
    """Load and validate verified human classifications."""

    if not override_file.exists():
        return pd.DataFrame()

    overrides = pd.read_csv(
        override_file,
        dtype={
            "source_job_id": "string",
        },
    )

    required_columns = {
        "source_job_id",
        "correct_role_family",
    }

    missing_columns = (
        required_columns
        - set(overrides.columns)
    )

    if missing_columns:
        raise ValueError(
            "The role override file is missing: "
            f"{sorted(missing_columns)}"
        )

    overrides["source_job_id"] = (
        overrides["source_job_id"]
        .fillna("")
        .astype("string")
        .str.strip()
    )

    overrides["correct_role_family"] = (
        overrides["correct_role_family"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    # The current audit was created entirely from Himalayas.
    # Future override files should contain a source column.
    if "source" not in overrides.columns:
        overrides["source"] = "Himalayas"

    overrides["source"] = (
        overrides["source"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    if "manual_decision" not in overrides.columns:
        overrides["manual_decision"] = ""

    invalid_roles = sorted(
        set(overrides["correct_role_family"])
        - ALLOWED_ROLE_FAMILIES
    )

    if invalid_roles:
        raise ValueError(
            "Invalid override role families: "
            f"{invalid_roles}"
        )

    duplicate_keys = overrides.duplicated(
        subset=[
            "source",
            "source_job_id",
        ],
        keep=False,
    )

    if duplicate_keys.any():
        duplicate_records = overrides.loc[
            duplicate_keys,
            [
                "source",
                "source_job_id",
            ],
        ]

        raise ValueError(
            "Duplicate override keys were found:\n"
            f"{duplicate_records.to_string(index=False)}"
        )

    return overrides[
        [
            "source",
            "source_job_id",
            "correct_role_family",
            "manual_decision",
        ]
    ].copy()


def apply_role_classification(
    dataframe: pd.DataFrame,
    override_file: Path,
) -> pd.DataFrame:
    """Apply automated classification followed by verified overrides."""

    required_columns = {
        "source",
        "source_job_id",
        "job_title_raw",
    }

    missing_columns = (
        required_columns
        - set(dataframe.columns)
    )

    if missing_columns:
        raise ValueError(
            "Classification input is missing: "
            f"{sorted(missing_columns)}"
        )

    classified = dataframe.copy()

    classified["source"] = (
        classified["source"]
        .astype(str)
        .str.strip()
    )

    classified["source_job_id"] = (
        classified["source_job_id"]
        .astype("string")
        .str.strip()
    )

    classified["automated_role_family"] = (
        classified["job_title_raw"]
        .apply(classify_role)
    )

    classified["role_family"] = (
        classified["automated_role_family"]
    )

    classified["classification_method"] = (
        "Automated Rule"
    )

    classified["role_override_applied"] = False
    classified["override_decision"] = ""

    overrides = load_role_overrides(
        override_file
    )

    if not overrides.empty:
        classified = classified.merge(
            overrides,
            how="left",
            on=[
                "source",
                "source_job_id",
            ],
            validate="many_to_one",
        )

        override_mask = (
            classified["correct_role_family"]
            .notna()
        )

        classified.loc[
            override_mask,
            "role_family",
        ] = classified.loc[
            override_mask,
            "correct_role_family",
        ]

        classified.loc[
            override_mask,
            "classification_method",
        ] = "Manual Override"

        classified.loc[
            override_mask,
            "role_override_applied",
        ] = True

        classified.loc[
            override_mask,
            "override_decision",
        ] = classified.loc[
            override_mask,
            "manual_decision",
        ].fillna("")

        classified = classified.drop(
            columns=[
                "correct_role_family",
                "manual_decision",
            ]
        )

    classified["is_target_data_role"] = (
        classified["role_family"]
        != "Non-target Role"
    )

    return classified