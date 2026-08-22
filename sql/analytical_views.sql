CREATE VIEW vw_skill_demand AS

SELECT
    s.skill_key,
    s.skill_name,
    s.skill_category,
    COUNT(DISTINCT js.source_record_key) AS job_count,

    ROUND(
        100.0 * COUNT(DISTINCT js.source_record_key)
        / (SELECT COUNT(*) FROM jobs),
        2
    ) AS job_share_pct

FROM job_skills AS js

JOIN skills AS s
    ON js.skill_key = s.skill_key

GROUP BY
    s.skill_key,
    s.skill_name,
    s.skill_category;
	
	CREATE VIEW vw_role_summary AS

SELECT
    role_family,
    COUNT(*) AS job_count,

    ROUND(
        100.0 * COUNT(*)
        / (SELECT COUNT(*) FROM jobs),
        2
    ) AS job_share_pct,

    COUNT(DISTINCT company_name) AS company_count

FROM jobs

GROUP BY
    role_family;
	
	DROP VIEW IF EXISTS vw_role_skill_demand;

CREATE VIEW vw_role_skill_demand AS

WITH role_counts AS (
    SELECT
        role_family,
        COUNT(*) AS role_job_count
    FROM jobs
    GROUP BY role_family
)

SELECT
    j.role_family,
    s.skill_key,
    s.skill_name,
    s.skill_category,

    COUNT(DISTINCT js.source_record_key)
        AS skill_job_count,

    rc.role_job_count,

    ROUND(
        100.0
        * COUNT(DISTINCT js.source_record_key)
        / rc.role_job_count,
        2
    ) AS role_skill_share_pct

FROM job_skills AS js

JOIN jobs AS j
    ON js.source_record_key
     = j.source_record_key

JOIN skills AS s
    ON js.skill_key
     = s.skill_key

JOIN role_counts AS rc
    ON j.role_family
     = rc.role_family

GROUP BY
    j.role_family,
    s.skill_key,
    s.skill_name,
    s.skill_category,
    rc.role_job_count;
	
DROP VIEW IF EXISTS vw_skill_cooccurrence;

CREATE VIEW vw_skill_cooccurrence AS

WITH skill_counts AS (
    SELECT
        skill_key,
        COUNT(DISTINCT source_record_key) AS skill_job_count
    FROM job_skills
    GROUP BY skill_key
),

pair_counts AS (
    SELECT
        js1.skill_key AS skill_1_key,
        js2.skill_key AS skill_2_key,
        COUNT(DISTINCT js1.source_record_key) AS cooccurrence_jobs
    FROM job_skills AS js1

    JOIN job_skills AS js2
        ON js1.source_record_key = js2.source_record_key
       AND js1.skill_key < js2.skill_key

    GROUP BY
        js1.skill_key,
        js2.skill_key
)

SELECT
    p.skill_1_key,
    s1.skill_name AS skill_1_name,
    p.skill_2_key,
    s2.skill_name AS skill_2_name,
    c1.skill_job_count AS skill_1_jobs,
    c2.skill_job_count AS skill_2_jobs,
    p.cooccurrence_jobs,

    ROUND(
        100.0 * p.cooccurrence_jobs
        / (SELECT COUNT(*) FROM jobs),
        2
    ) AS pair_job_share_pct,

    ROUND(
        100.0 * p.cooccurrence_jobs
        / c1.skill_job_count,
        2
    ) AS pct_skill_1_with_skill_2,

    ROUND(
        100.0 * p.cooccurrence_jobs
        / c2.skill_job_count,
        2
    ) AS pct_skill_2_with_skill_1,

    ROUND(
        1.0 * p.cooccurrence_jobs
        / (
            c1.skill_job_count
            + c2.skill_job_count
            - p.cooccurrence_jobs
        ),
        4
    ) AS jaccard_similarity,

    ROUND(
        1.0 * p.cooccurrence_jobs
        * (SELECT COUNT(*) FROM jobs)
        / (
            c1.skill_job_count
            * c2.skill_job_count
        ),
        4
    ) AS lift

FROM pair_counts AS p

JOIN skills AS s1
    ON p.skill_1_key = s1.skill_key

JOIN skills AS s2
    ON p.skill_2_key = s2.skill_key

JOIN skill_counts AS c1
    ON p.skill_1_key = c1.skill_key

JOIN skill_counts AS c2
    ON p.skill_2_key = c2.skill_key;
	
	DROP VIEW IF EXISTS vw_salary_by_role;

CREATE VIEW vw_salary_by_role AS

WITH salary_base AS (

    SELECT
        role_family,
        salary_currency,
        salary_period,
        salary_min,
        salary_max,

        CASE
            WHEN salary_min IS NOT NULL
             AND salary_max IS NOT NULL
            THEN (
                salary_min + salary_max
            ) / 2.0

            WHEN salary_min IS NOT NULL
            THEN salary_min

            WHEN salary_max IS NOT NULL
            THEN salary_max
        END AS salary_midpoint

    FROM jobs

    WHERE
        (
            salary_min IS NOT NULL
            OR salary_max IS NOT NULL
        )

        AND salary_currency IS NOT NULL
        AND salary_period IS NOT NULL
)

SELECT
    role_family,
    salary_currency,
    salary_period,

    COUNT(*) AS salary_job_count,

    ROUND(
        AVG(salary_min),
        2
    ) AS avg_salary_min,

    ROUND(
        AVG(salary_max),
        2
    ) AS avg_salary_max,

    ROUND(
        AVG(salary_midpoint),
        2
    ) AS avg_salary_midpoint

FROM salary_base

GROUP BY
    role_family,
    salary_currency,
    salary_period;
	
	DROP VIEW IF EXISTS vw_role_skill_cooccurrence;

CREATE VIEW vw_role_skill_cooccurrence AS

WITH role_counts AS (
    SELECT
        role_family,
        COUNT(*) AS role_job_count
    FROM jobs
    GROUP BY role_family
),

role_skill_counts AS (
    SELECT
        j.role_family,
        js.skill_key,
        COUNT(DISTINCT js.source_record_key)
            AS skill_job_count
    FROM job_skills AS js

    JOIN jobs AS j
        ON js.source_record_key
         = j.source_record_key

    GROUP BY
        j.role_family,
        js.skill_key
),

role_pair_counts AS (
    SELECT
        j.role_family,
        js1.skill_key AS skill_1_key,
        js2.skill_key AS skill_2_key,

        COUNT(DISTINCT js1.source_record_key)
            AS cooccurrence_jobs

    FROM job_skills AS js1

    JOIN job_skills AS js2
        ON js1.source_record_key
         = js2.source_record_key
       AND js1.skill_key
         < js2.skill_key

    JOIN jobs AS j
        ON js1.source_record_key
         = j.source_record_key

    GROUP BY
        j.role_family,
        js1.skill_key,
        js2.skill_key
)

SELECT
    p.role_family,

    p.skill_1_key,
    s1.skill_name AS skill_1_name,

    p.skill_2_key,
    s2.skill_name AS skill_2_name,

    c1.skill_job_count AS skill_1_jobs,
    c2.skill_job_count AS skill_2_jobs,

    p.cooccurrence_jobs,
    rc.role_job_count,

    ROUND(
        100.0 * p.cooccurrence_jobs
        / rc.role_job_count,
        2
    ) AS pair_role_share_pct,

    ROUND(
        100.0 * p.cooccurrence_jobs
        / c1.skill_job_count,
        2
    ) AS pct_skill_1_with_skill_2,

    ROUND(
        100.0 * p.cooccurrence_jobs
        / c2.skill_job_count,
        2
    ) AS pct_skill_2_with_skill_1,

    ROUND(
        1.0 * p.cooccurrence_jobs
        /
        (
            c1.skill_job_count
            + c2.skill_job_count
            - p.cooccurrence_jobs
        ),
        4
    ) AS jaccard_similarity,

    ROUND(
        1.0
        * p.cooccurrence_jobs
        * rc.role_job_count
        /
        (
            c1.skill_job_count
            * c2.skill_job_count
        ),
        4
    ) AS lift

FROM role_pair_counts AS p

JOIN role_counts AS rc
    ON p.role_family
     = rc.role_family

JOIN role_skill_counts AS c1
    ON p.role_family
     = c1.role_family
   AND p.skill_1_key
     = c1.skill_key

JOIN role_skill_counts AS c2
    ON p.role_family
     = c2.role_family
   AND p.skill_2_key
     = c2.skill_key

JOIN skills AS s1
    ON p.skill_1_key
     = s1.skill_key

JOIN skills AS s2
    ON p.skill_2_key
     = s2.skill_key;