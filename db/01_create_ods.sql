-- ==============================================
-- ODS 贴源层建表脚本（双平台版）
-- 使用方法：mysql -u root -p'Tuocong666;' < db/01_create_ods.sql
--
-- 设计说明：
-- - source_platform 字段区分 gitee/github 数据来源
-- - topics/license/homepage/archived 为 GitHub 特有字段，Gitee 数据填默认值
-- - 统一表结构方便后续 DWD/DWS/ADS 层处理
-- ==============================================

USE xinchuang_dw;

-- 如果旧表存在则删除重建（仅首次执行时）
-- DROP TABLE IF EXISTS ods_repos_raw;

CREATE TABLE IF NOT EXISTS ods_repos_raw (
    -- 基础标识
    repo_id           BIGINT        COMMENT '仓库ID',
    org               VARCHAR(100)  COMMENT '所属组织',
    name              VARCHAR(200)  COMMENT '仓库名',
    full_name         VARCHAR(500)  COMMENT '仓库全名，如 mindspore-ai/mindspore',
    description       TEXT          COMMENT '仓库描述',

    -- 核心指标
    stars_count       INT           COMMENT 'Star数',
    forks_count       INT           COMMENT 'Fork数',
    watchers_count    INT           COMMENT '关注者数',
    open_issues_count INT           COMMENT '未关闭Issue数',

    -- 仓库属性
    language          VARCHAR(50)   COMMENT '主要编程语言',
    default_branch    VARCHAR(50)   COMMENT '默认分支',
    html_url          VARCHAR(500)  COMMENT '仓库URL',

    -- GitHub 特有字段（Gitee 数据填默认值）
    topics            VARCHAR(500)  COMMENT '仓库标签（逗号分隔）',
    license_type      VARCHAR(100)  COMMENT '开源许可证类型',
    homepage          VARCHAR(500)  COMMENT '项目主页URL',
    archived          TINYINT(1)    COMMENT '是否已归档（1=是 0=否）',

    -- 时间字段
    created_at        VARCHAR(30)   COMMENT '仓库创建时间（ISO 8601格式）',
    updated_at        VARCHAR(30)   COMMENT '仓库最后更新时间',
    pushed_at         VARCHAR(30)   COMMENT '仓库最后推送时间',

    -- ETL 控制字段
    source_platform   VARCHAR(10)   COMMENT '数据来源：gitee 或 github',
    etl_time          TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'ETL加载时间',
    dt                VARCHAR(10)   COMMENT '数据日期分区，如 2026-08-04'
) COMMENT '开源仓库贴源数据表（Gitee + GitHub）';

-- 验证
SHOW TABLES;
SELECT
    COLUMN_NAME,
    COLUMN_TYPE,
    COLUMN_COMMENT
FROM information_schema.COLUMNS
WHERE table_schema = 'xinchuang_dw' AND table_name = 'ods_repos_raw'
ORDER BY ORDINAL_POSITION;
