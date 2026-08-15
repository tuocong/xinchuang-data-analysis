-- ===== 4_月度趋势.sql =====
-- 折线图/面积图：最近12个月仓库/Star/活跃度月度变化
-- 数据来源：ADS 层 ads_monthly_trend 表
-- 对应 API：GET /api/trend
--
-- 说明：数据从 8 月开始积累，9 月之后才有明显的趋势线。
--       前几个月数据量少时，折线可能比较平。

USE xinchuang_dw;

-- ============================================================
-- 方案A（推荐）：直接查 ADS 表
-- ============================================================
SELECT
    stat_month       AS 月份,
    new_repos        AS 月增仓库,
    active_repos     AS 活跃仓库,
    new_stars        AS 月增Star,
    cumulative_stars AS 累计Star
FROM ads_monthly_trend
ORDER BY stat_month DESC
LIMIT 12;


-- ============================================================
-- 方案B（备选）：DWD 层按月聚合
-- 注意：DWD 层没有累计值，需要 SUM() OVER() 计算
-- ============================================================
-- SELECT
--     DATE_FORMAT(snapshot_date, '%Y-%m') AS 月份,
--     COUNT(DISTINCT project_id)          AS 仓库数,
--     SUM(stars_count)                    AS 当月Star,
--     SUM(SUM(stars_count)) OVER (
--         ORDER BY DATE_FORMAT(snapshot_date, '%Y-%m')
--     )                                   AS 累计Star
-- FROM fact_repo_stats
-- GROUP BY DATE_FORMAT(snapshot_date, '%Y-%m')
-- ORDER BY 月份 DESC
-- LIMIT 12;
