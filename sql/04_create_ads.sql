-- ============ 04_create_ads.sql ============
-- ADS 应用层：5张表 —— 概览/排名/语言/趋势/对比，直接供前端 API 查询
-- 数据来源：DWS 汇总表 + dim_project
USE xinchuang_dw;

-- ================================================================
-- ADS-1：平台概览（大屏顶部4个数字卡片）
-- 数据来源：fact_repo_stats + dim_project
-- ================================================================
CREATE TABLE ads_overview (
    stat_date       DATE PRIMARY KEY COMMENT '统计日期',
    total_repos     INT COMMENT '仓库总数',
    total_stars     BIGINT COMMENT '总Star数',
    total_forks     BIGINT COMMENT '总Fork数',
    total_orgs      INT COMMENT '组织数',
    gitee_repos     INT COMMENT 'Gitee仓库数',
    github_repos    INT COMMENT 'GitHub仓库数',
    avg_stars       DECIMAL(10,2) COMMENT '平均Star数'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT 'ADS-平台概览';

-- ================================================================
-- ADS-2：项目排名（大屏 TOP20，柱状图数据源）
-- 数据来源：dws_project_daily + dim_project
-- ================================================================
CREATE TABLE ads_project_ranking (
    stat_date       DATE COMMENT '统计日期',
    rank_num        INT COMMENT '排名 1-20',
    project_name    VARCHAR(200) COMMENT '仓库名',
    full_name       VARCHAR(500) COMMENT '全名 org/repo',
    org_name        VARCHAR(100) COMMENT '所属组织',
    language        VARCHAR(50) COMMENT '主要编程语言',
    stars_count     INT COMMENT '当日Star数',
    forks_count     INT COMMENT '当日Fork数',
    star_growth     INT COMMENT '日Star增量（⭐核心指标，来自DWS curr_day_new_stars）',
    source_platform VARCHAR(10) COMMENT 'gitee/github',
    PRIMARY KEY (stat_date, rank_num)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT 'ADS-项目Star排名（TOP20，每日刷新）';

-- ================================================================
-- ADS-3：语言分布（大屏饼图/环形图数据源）
-- 数据来源：dws_language_daily
-- ================================================================
CREATE TABLE ads_language_dist (
    stat_date       DATE COMMENT '统计日期',
    language        VARCHAR(50) COMMENT '编程语言',
    repo_count      INT COMMENT '仓库数',
    total_stars     INT COMMENT '总Star',
    pct_of_total    DECIMAL(5,2) COMMENT '占比%',
    PRIMARY KEY (stat_date, language)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT 'ADS-语言分布统计';

-- ================================================================
-- ADS-4：月度趋势（大屏折线图/面积图数据源）
-- 数据来源：dws_project_daily + dws_org_daily（按月汇总）
-- 注意：当前只有 8/7-8/8 两天的数据，月度趋势需要积累至少1个月才有意义
-- ================================================================
CREATE TABLE ads_monthly_trend (
    stat_month      VARCHAR(7) COMMENT '月份，如 2026-08',
    new_repos       INT COMMENT '当月新增仓库（跨所有org求和）',
    active_repos    INT COMMENT '当月活跃仓库数',
    new_stars       INT COMMENT '当月新增Star',
    cumulative_stars BIGINT COMMENT '累计Star（持续累加）',
    PRIMARY KEY (stat_month)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT 'ADS-月度趋势';

-- ================================================================
-- ADS-5：组织对比（大屏横向柱状图数据源）
-- 数据来源：dws_org_daily
-- 注意：dim_org 的 PK 是 org_name（单列），同名组织跨平台时只保留首次入库的平台。
--       因此 source_platform 字段对跨平台组织可能不准确，展示时仅供参考。
-- ================================================================
CREATE TABLE ads_org_compare (
    stat_date       DATE COMMENT '统计日期',
    org_name        VARCHAR(100) COMMENT '组织名',
    source_platform VARCHAR(10) COMMENT '归属平台（跨平台组织仅显示首次入库平台）',
    repo_count      INT COMMENT '仓库总数',
    total_stars     INT COMMENT '总Star',
    avg_stars       DECIMAL(10,2) COMMENT '平均Star',
    active_rate     DECIMAL(5,2) COMMENT '活跃率%',
    PRIMARY KEY (stat_date, org_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT 'ADS-组织活跃度对比';
