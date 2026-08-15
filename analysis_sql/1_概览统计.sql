-- ===== 1_概览统计.sql =====
-- 大屏顶部数字卡片：总仓库/总Star/总Fork/平均Star/平台占比
-- 数据来源：ADS 层 ads_overview 表（etl_dws_to_ads.py 每日刷新）
-- 对应 API：GET /api/overview

USE xinchuang_dw;

-- ============================================================
-- 方案A（推荐）：直接查 ADS 表，1 行查询，毫秒级
-- ============================================================
SELECT
    stat_date        AS 统计日期,
    total_repos      AS 总仓库数,
    total_stars      AS 总Star数,
    total_forks      AS 总Fork数,
    avg_stars        AS 平均Star,
    total_orgs       AS 组织数,
    gitee_repos      AS Gitee仓库,
    github_repos     AS GitHub仓库
FROM ads_overview
ORDER BY stat_date DESC
LIMIT 1;


-- ============================================================
-- 方案B（备选）：原始 DWD 层查询，不依赖 ADS
-- 适用于 ADS 表未刷新或需要实时计算时
-- ============================================================
-- SELECT
--     COUNT(DISTINCT project_id)                              AS 总仓库数,
--     SUM(stars_count)                                        AS 总Star数,
--     SUM(forks_count)                                        AS 总Fork数,
--     ROUND(AVG(stars_count), 1)                              AS 平均Star,
--     COUNT(DISTINCT org_name)                                AS 组织数,
--     COUNT(DISTINCT CASE WHEN source_platform='gitee'  THEN project_id END) AS Gitee仓库,
--     COUNT(DISTINCT CASE WHEN source_platform='github' THEN project_id END) AS GitHub仓库
-- FROM fact_repo_stats f
-- JOIN dim_project p ON f.project_id = p.project_id
-- WHERE f.snapshot_date = (SELECT MAX(snapshot_date) FROM fact_repo_stats);
