-- ===== 3_语言分布.sql =====
-- 饼图/环形图：各语言仓库数 + Star 占比
-- 数据来源：ADS 层 ads_language_dist 表
-- 对应 API：GET /api/language

USE xinchuang_dw;

-- ============================================================
-- 方案A（推荐）：直接查 ADS 表
-- ============================================================
SELECT
    language      AS 语言,
    repo_count    AS 仓库数,
    total_stars   AS 总Star,
    pct_of_total  AS 占比
FROM ads_language_dist
WHERE stat_date = (SELECT MAX(stat_date) FROM ads_language_dist)
ORDER BY repo_count DESC;


-- ============================================================
-- 方案B（备选）：DWD 层实时聚合
-- ============================================================
-- SELECT
--     language,
--     COUNT(DISTINCT p.project_id) AS 仓库数,
--     ROUND(COUNT(DISTINCT p.project_id) * 100.0
--         / SUM(COUNT(DISTINCT p.project_id)) OVER(), 1) AS 占比
-- FROM dim_project p
-- JOIN fact_repo_stats f ON p.project_id = f.project_id
-- WHERE f.snapshot_date = (SELECT MAX(snapshot_date) FROM fact_repo_stats)
-- GROUP BY language
-- ORDER BY 仓库数 DESC
-- LIMIT 10;
