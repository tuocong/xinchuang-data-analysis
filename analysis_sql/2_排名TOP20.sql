-- ===== 2_排名TOP20.sql =====
-- 柱状图：Star 前20 项目 + 日增长量
-- 数据来源：ADS 层 ads_project_ranking 表
-- 对应 API：GET /api/ranking
--
-- 说明：star_growth（日增量）由 DWS ETL 两步法计算：
--   今天累计 - 昨天累计 = 当日增量，避免了单天 LAG() 恒为 0 的问题

USE xinchuang_dw;

-- ============================================================
-- 方案A（推荐）：直接查 ADS 表
-- ============================================================
SELECT
    rank_num        AS 排名,
    project_name    AS 仓库名,
    full_name       AS 全称,
    org_name        AS 组织,
    language        AS 语言,
    stars_count     AS Star数,
    forks_count     AS Fork数,
    star_growth     AS 日增长,
    source_platform AS 平台
FROM ads_project_ranking
WHERE stat_date = (SELECT MAX(stat_date) FROM ads_project_ranking)
ORDER BY rank_num;


-- ============================================================
-- 方案B（备选）：DWD 层手动排名
-- 注意：单天 LAG() 取不到昨天数据，日增长恒为 0
-- ============================================================
-- SELECT
--     ROW_NUMBER() OVER (ORDER BY f.stars_count DESC) AS 排名,
--     p.full_name,
--     f.stars_count AS Star数,
--     p.language    AS 语言,
--     f.source_platform AS 平台
-- FROM fact_repo_stats f
-- JOIN dim_project p ON f.project_id = p.project_id
-- WHERE f.snapshot_date = (SELECT MAX(snapshot_date) FROM fact_repo_stats)
-- ORDER BY f.stars_count DESC
-- LIMIT 20;
