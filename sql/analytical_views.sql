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