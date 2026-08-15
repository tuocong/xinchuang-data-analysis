"""
DWD ETL脚本: ODS贴源表 → DWD维度表 + 事实表（星型模型）
功能：ods_repos_raw → dim_project + dim_org + fact_repo_stats
运行命令：python scripts/etl_ods_to_dwd.py
"""
import sys
import logging
from pathlib import Path

# ---- 项目根目录 & 配置 ----
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pymysql
from project_config import DB_CONFIG

# ====================== 日志 ======================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

DB = DB_CONFIG  # 统一入口


def main():
    conn = pymysql.connect(**DB)
    cursor = conn.cursor()

    # 自动取 ODS 层最新数据日期
    cursor.execute("SELECT MAX(dt) FROM ods_repos_raw")
    latest_dt = cursor.fetchone()[0]
    if not latest_dt:
        raise RuntimeError("[ERROR] ods_repos_raw 表为空，请先运行 ods_loader.py 导入数据！")
    logger.info(f"[DATE] ODS 最新数据日期：{latest_dt}")

    try:
        # ===== 1. ODS → dim_project（SCD Type1：覆盖更新） =====
        cursor.execute("""
            INSERT INTO dim_project (project_id, project_name, full_name, description,
                language, topics, license_type, html_url, source_platform, created_at)
            SELECT repo_id, name, full_name, description,
                   language, topics, license_type, html_url, source_platform,
                   STR_TO_DATE(LEFT(created_at, 19), '%%Y-%%m-%%dT%%H:%%i:%%s')
            FROM ods_repos_raw
            WHERE dt = %s
            ON DUPLICATE KEY UPDATE
                project_name   = VALUES(project_name),
                full_name      = VALUES(full_name),
                description    = VALUES(description),
                language       = VALUES(language),
                topics         = VALUES(topics),
                license_type   = VALUES(license_type),
                html_url       = VALUES(html_url),
                source_platform = VALUES(source_platform),
                created_at     = VALUES(created_at);
        """, (latest_dt,))
        logger.info(f"dim_project 处理行数: {cursor.rowcount}")

        # ===== 2. ODS → dim_org（组织维度，去重） =====
        cursor.execute("""
            INSERT IGNORE INTO dim_org (org_name, source_platform)
            SELECT DISTINCT org, source_platform
            FROM ods_repos_raw WHERE dt = %s;
        """, (latest_dt,))
        logger.info(f"dim_org 新增行数: {cursor.rowcount}")

        # ===== 3. ODS → fact_repo_stats（日快照事实表） =====
        cursor.execute("""
            INSERT INTO fact_repo_stats (project_id, org_name, source_platform,
                snapshot_date, stars_count, forks_count, watchers_count,
                open_issues_count, dt)
            SELECT repo_id, org, source_platform, %s,
                   stars_count, forks_count, watchers_count,
                   open_issues_count, dt
            FROM ods_repos_raw WHERE dt = %s;
        """, (latest_dt, latest_dt))
        logger.info(f"fact_repo_stats 写入行数: {cursor.rowcount}")

        conn.commit()
        logger.info(f"[OK] DWD ETL 全部执行完成，日期：{latest_dt}")

    except Exception as e:
        conn.rollback()
        logger.error(f"[ERROR] ETL执行失败，已回滚！错误：{e}")
        raise
    finally:
        cursor.close()
        conn.close()
        logger.info("数据库连接已释放")


if __name__ == "__main__":
    main()
