WITH

params AS (
    SELECT
        'Data Analyst' AS target_role
),

candidate_skills(skill_key) AS (
    VALUES
        ('sql'),
        ('excel'),
        ('power_bi'),
        ('python')
),

role_skills AS (
    SELECT
        rsd.skill_key,
        rsd.skill_name,
        rsd.skill_category,
        rsd.skill_job_count,
        rsd.role_job_count,
        rsd.role_skill_share_pct

    FROM vw_role_skill_demand AS rsd
    CROSS JOIN params AS p

    WHERE
        rsd.role_family = p.target_role
),

missing_skills AS (
    SELECT
        rs.*

    FROM role_skills AS rs

    LEFT JOIN candidate_skills AS cs
        ON rs.skill_key = cs.skill_key

    WHERE
        cs.skill_key IS NULL
),

skill_connections AS (
    SELECT
        ms.skill_key AS missing_skill_key,
        ms.skill_name AS missing_skill_name,
        ms.skill_category,

        ms.skill_job_count,
        ms.role_job_count,
        ms.role_skill_share_pct,

        cs.skill_key AS known_skill_key,

        COALESCE(
            rsc.cooccurrence_jobs,
            0
        ) AS cooccurrence_jobs,

        CASE

            WHEN
                rsc.skill_1_key = cs.skill_key
                AND
                rsc.skill_2_key = ms.skill_key

            THEN
                rsc.pct_skill_1_with_skill_2

            WHEN
                rsc.skill_2_key = cs.skill_key
                AND
                rsc.skill_1_key = ms.skill_key

            THEN
                rsc.pct_skill_2_with_skill_1

            ELSE 0

        END AS complementarity_pct

    FROM missing_skills AS ms

    CROSS JOIN candidate_skills AS cs
    CROSS JOIN params AS p

    LEFT JOIN vw_role_skill_cooccurrence AS rsc

        ON rsc.role_family = p.target_role

        AND (
            (
                rsc.skill_1_key = cs.skill_key
                AND
                rsc.skill_2_key = ms.skill_key
            )

            OR

            (
                rsc.skill_2_key = cs.skill_key
                AND
                rsc.skill_1_key = ms.skill_key
            )
        )
)

SELECT
    missing_skill_key AS skill_key,
    missing_skill_name AS skill_name,
    skill_category,

    skill_job_count,
    role_job_count,

    role_skill_share_pct
        AS role_demand_pct,

    ROUND(
        AVG(complementarity_pct),
        2
    ) AS avg_complementarity_pct,

    SUM(
        CASE
            WHEN cooccurrence_jobs > 0
            THEN 1
            ELSE 0
        END
    ) AS known_skill_connections,

    SUM(cooccurrence_jobs)
        AS summed_pair_support,

    ROUND(
        (
            0.80 * role_skill_share_pct
        )
        +
        (
            0.20 * AVG(complementarity_pct)
        ),
        2
    ) AS priority_score,
CASE
        WHEN (
            0.80 * role_skill_share_pct
            +
            0.20 * AVG(complementarity_pct)
        ) >= 45
        THEN 'High Priority'
        WHEN (
            0.80 * role_skill_share_pct
            +
            0.20 * AVG(complementarity_pct)
        ) >= 25
        THEN 'Medium Priority'
        ELSE 'Lower Priority'
    END AS priority_tier


FROM skill_connections

GROUP BY
    missing_skill_key,
    missing_skill_name,
    skill_category,
    skill_job_count,
    role_job_count,
    role_skill_share_pct

ORDER BY
    priority_score DESC;
	
	
	WITH

params AS (
    SELECT
        'Data Analyst' AS target_role
),

candidate_skills(skill_key) AS (
    VALUES
        ('sql'),
        ('excel'),
        ('power_bi'),
        ('python')
),

target_jobs AS (
    SELECT
        j.source_record_key
    FROM jobs AS j
    CROSS JOIN params AS p
    WHERE
        j.role_family = p.target_role
),

job_match_counts AS (
    SELECT
        tj.source_record_key,

        COUNT(js.skill_key)
            AS detected_skill_count,

        SUM(
            CASE
                WHEN cs.skill_key IS NOT NULL
                THEN 1
                ELSE 0
            END
        ) AS matched_skill_count

    FROM target_jobs AS tj

    LEFT JOIN job_skills AS js
        ON tj.source_record_key
         = js.source_record_key

    LEFT JOIN candidate_skills AS cs
        ON js.skill_key
         = cs.skill_key

    GROUP BY
        tj.source_record_key
),

job_coverage AS (
    SELECT
        source_record_key,
        detected_skill_count,
        matched_skill_count,

        CASE
            WHEN detected_skill_count > 0
            THEN
                100.0
                * matched_skill_count
                / detected_skill_count

            ELSE NULL
        END AS observed_skill_coverage_pct

    FROM job_match_counts
)

SELECT
    COUNT(*) AS target_jobs,

    SUM(
        CASE
            WHEN detected_skill_count > 0
            THEN 1
            ELSE 0
        END
    ) AS jobs_with_detected_skills,

    ROUND(
        AVG(
            observed_skill_coverage_pct
        ),
        2
    ) AS avg_observed_skill_coverage_pct,

    SUM(
        CASE
            WHEN matched_skill_count >= 1
            THEN 1
            ELSE 0
        END
    ) AS jobs_with_1_plus_matches,

    ROUND(
        100.0
        * SUM(
            CASE
                WHEN matched_skill_count >= 1
                THEN 1
                ELSE 0
            END
        )
        / COUNT(*),
        2
    ) AS jobs_with_1_plus_matches_pct,

    SUM(
        CASE
            WHEN matched_skill_count >= 3
            THEN 1
            ELSE 0
        END
    ) AS jobs_with_3_plus_matches,

    ROUND(
        100.0
        * SUM(
            CASE
                WHEN matched_skill_count >= 3
                THEN 1
                ELSE 0
            END
        )
        / COUNT(*),
        2
    ) AS jobs_with_3_plus_matches_pct,

    SUM(
        CASE
            WHEN observed_skill_coverage_pct >= 50
            THEN 1
            ELSE 0
        END
    ) AS jobs_at_50pct_plus_coverage,

    ROUND(
        100.0
        * SUM(
            CASE
                WHEN observed_skill_coverage_pct >= 50
                THEN 1
                ELSE 0
            END
        )
        / COUNT(*),
        2
    ) AS jobs_at_50pct_plus_coverage_pct

FROM job_coverage;


