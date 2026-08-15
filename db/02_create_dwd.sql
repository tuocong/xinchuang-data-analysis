-- ==============================================
-- DWD 明细层建表脚本（星型模型：3维度 + 1事实）
-- 使用方法：mysql -u root -p < db/02_create_dwd.sql
--
-- 设计说明：
--   dim_project   → 项目维度（SCD Type1，覆盖更新）
--   dim_org       → 组织维度（联合主键 org+platform）
--   dim_date      → 日期维度（需运行 fill_dim_date.py 预填充）
--   fact_repo_stats → 仓库日快照事实表
-- ==============================================

USE xinchuang_dw;

-- ==================================================
-- 维度表1：项目维度（SCD Type1）
-- 主键 project_id 天然支持 ON DUPLICATE KEY UPDATE
-- ==================================================
CREATE TABLE IF NOT EXISTS dim_project (
    project_id      BIGINT        PRIMARY KEY COMMENT '仓库唯一ID，关联ODS repo_id',
    project_name    VARCHAR(200)  COMMENT '仓库名称',
    full_name       VARCHAR(500)  COMMENT '仓库全称，如 mindspore-ai/mindspore',
    description     TEXT          COMMENT '项目描述',
    language        VARCHAR(50)   COMMENT '主要开发语言',
    topics          VARCHAR(500)  COMMENT '项目标签',
    license_type    VARCHAR(100)  COMMENT '开源协议类型',
    html_url        VARCHAR(500)  COMMENT '仓库访问地址',
    source_platform VARCHAR(10)   COMMENT '来源平台：gitee / github',
    created_at      DATETIME      COMMENT '仓库创建时间',
    etl_time        TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'ETL更新时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='DWD-项目维度表';

-- ==================================================
-- 维度表2：组织维度
-- 联合主键解决同名组织跨平台冲突
-- ==================================================
CREATE TABLE IF NOT EXISTS dim_org (
    org_name        VARCHAR(100) COMMENT '组织名称',
    source_platform VARCHAR(10)  COMMENT '来源平台：gitee / github',
    etl_time        TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'ETL写入时间',
    PRIMARY KEY (org_name, source_platform)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='DWD-组织维度表';

-- ==================================================
-- 维度表3：日期维度（标准日期维度，方便按年/季/月/周分析）
-- 数据由 scripts/fill_dim_date.py 预填充
-- ==================================================
CREATE TABLE IF NOT EXISTS dim_date (
    date_id        DATE      PRIMARY KEY COMMENT '标准日期',
    year           SMALLINT  COMMENT '年份',
    quarter        TINYINT   COMMENT '季度 1~4',
    month          TINYINT   COMMENT '月份 1~12',
    day            TINYINT   COMMENT '日期 1~31',
    week_of_year   TINYINT   COMMENT '年内周序号',
    day_of_week    TINYINT   COMMENT '星期 1~7（周一=1）',
    is_weekend     TINYINT   COMMENT '是否周末 0=否 1=是'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='DWD-日期维度表';

-- ==================================================
-- 事实表：仓库日快照事实表
-- 每个仓库每天一条记录，追踪Star/Fork等指标变化
-- ==================================================
CREATE TABLE IF NOT EXISTS fact_repo_stats (
    snapshot_id       BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '快照自增主键',
    project_id        BIGINT        COMMENT '关联 dim_project',
    org_name          VARCHAR(100)  COMMENT '组织名称',
    source_platform   VARCHAR(10)   COMMENT '平台（联合匹配 dim_org）',
    snapshot_date     DATE          COMMENT '快照日期，关联 dim_date',
    stars_count       INT           COMMENT 'Star数量',
    forks_count       INT           COMMENT 'Fork数量',
    watchers_count    INT           COMMENT '关注人数',
    open_issues_count INT           COMMENT '未关闭Issue数',
    etl_time          TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'ETL加载时间',
    dt                VARCHAR(10)   COMMENT 'ETL分区日期',
    INDEX idx_project (project_id),
    INDEX idx_org (org_name, source_platform),
    INDEX idx_date (snapshot_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='DWD-仓库日快照事实表';

-- 验证
SHOW TABLES LIKE 'dim_%';
SHOW TABLES LIKE 'fact_%';
