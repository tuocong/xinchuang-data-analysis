-- ===== 5_组织对比.sql =====
-- 横向柱状图：各组织 Star/仓库/活跃率全方位对比
-- 数据来源：ADS 层 ads_org_compare 表
-- 对应 API：GET /api/org-compare

USE xinchuang_dw;

-- ============================================================
-- 方案A（推荐）：直接查 ADS 表
-- ============================================================
SELECT
    org_name        AS 组织,
    source_platform AS 平台,
    repo_count      AS 仓库数,
    total_stars     AS 总Star,
    avg_stars       AS 平均Star,
    active_rate     AS 活跃率
FROM ads_org_compare
WHERE stat_date = (SELECT MAX(stat_date) FROM ads_org_compare)
ORDER BY total_stars DESC;


-- ============================================================
-- 方案B（备选）：DWD 层聚合（跨平台组织归到首次入库平台）
-- ============================================================
-- SELECT
--     f.org_name,
--     MAX(p.source_platform) AS 平台,
--     COUNT(DISTINCT f.project_id) AS 仓库数,
--     SUM(f.stars_count)           AS 总Star,
--     ROUND(AVG(f.stars_count), 1) AS 平均Star,
--     SUM(CASE WHEN f.open_issues_count > 0 THEN 1 ELSE 0 END) AS 有Issue项目数
-- FROM fact_repo_stats f
-- JOIN dim_project p ON f.project_id = p.project_id
-- WHERE f.snapshot_date = (SELECT MAX(snapshot_date) FROM fact_repo_stats)
-- GROUP BY f.org_name
-- ORDER BY 总Star DESC;
