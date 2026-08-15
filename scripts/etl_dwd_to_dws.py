"""
DWS ETL脚本：DWD事实表 → DWS汇总层

两步走设计（修复增量计算缺陷）：
  第1步 INSERT —— 只写入累计/基数值，不做任何增量计算
  第2步 UPDATE —— LEFT JOIN DWS 自身昨日行，今天值-昨天值=当日增量

为什么这样改：
  原来 LAG() 写在 INSERT 子查询里，子查询只看到当天从 fact_repo_stats
  聚合出的行，看不到 DWS 里已存在的历史行。如果源表只有一天的数据，
  LAG() 永远返回默认值，增量恒为 0/空。
  现在改为 INSERT 后 UPDATE，增量从 DWS 自己的历史行计算，
  无论源表有几天的数据，都能正确算出 delta。

运行前提：MySQL >=8.0，dim_project / fact_repo_stats 已有数据
"""
import pymysql
from pymysql.err import MySQLError


def etl_dwd_to_dws():
    conn = pymysql.connect(
        host='localhost',
        user='root',
        password='Tuocong666;',
        database='xinchuang_dw',
        charset='utf8mb4'
    )
    cursor = conn.cursor()

    try:
        # ================================================================
        # 1. DWS-项目日汇总（dws_project_daily）
        # ================================================================

        # 第1步：INSERT 累计值（不计算增量）
        sql_project_insert = """
        INSERT INTO dws_project_daily
            (project_id, snapshot_date, total_cum_stars, total_cum_forks)
        SELECT
            project_id,
            snapshot_date,
            MAX(stars_count)       AS total_cum_stars,
            MAX(forks_count)       AS total_cum_forks
        FROM fact_repo_stats
        GROUP BY project_id, snapshot_date
        ON DUPLICATE KEY UPDATE
            total_cum_stars = VALUES(total_cum_stars),
            total_cum_forks = VALUES(total_cum_forks);
        """
        cursor.execute(sql_project_insert)
        print(f"  ✅ dws_project_daily（累计值写入）—— {cursor.rowcount} 行")

        # 第2步：UPDATE 增量 = 今天累计 - 昨天累计
        # LEFT JOIN dws_project_daily 的昨日行 → COALESCE 兜底第一天（delta=0）
        sql_project_update = """
        UPDATE dws_project_daily t
        LEFT JOIN dws_project_daily y
            ON t.project_id = y.project_id
            AND y.snapshot_date = DATE_SUB(t.snapshot_date, INTERVAL 1 DAY)
        SET
            t.curr_day_new_stars = t.total_cum_stars
                                 - COALESCE(y.total_cum_stars, t.total_cum_stars),
            t.curr_day_new_forks = t.total_cum_forks
                                 - COALESCE(y.total_cum_forks, t.total_cum_forks);
        """
        cursor.execute(sql_project_update)
        print(f"  ✅ dws_project_daily（Star/Fork增量计算）—— {cursor.rowcount} 行")

        # 第3步：UPDATE issue 增量（DWS 没有 total_cum_issues 列，
        # 所以从 fact_repo_stats 自身前后天对比）
        sql_project_issues = """
        UPDATE dws_project_daily t
        JOIN fact_repo_stats today
            ON t.project_id = today.project_id
            AND t.snapshot_date = today.snapshot_date
        LEFT JOIN fact_repo_stats yesterday
            ON t.project_id = yesterday.project_id
            AND yesterday.snapshot_date = DATE_SUB(t.snapshot_date, INTERVAL 1 DAY)
        SET t.curr_day_new_issues =
            today.open_issues_count
            - COALESCE(yesterday.open_issues_count, today.open_issues_count);
        """
        cursor.execute(sql_project_issues)
        print(f"  ✅ dws_project_daily（Issue增量计算）—— {cursor.rowcount} 行")

        # ================================================================
        # 2. DWS-语言日汇总（无增量字段，直接聚合）
        # ================================================================
        sql_language = """
        INSERT INTO dws_language_daily
            (language, snapshot_date, repo_count, total_stars, total_forks, avg_stars)
        SELECT
            p.language,
            f.snapshot_date,
            COUNT(DISTINCT f.project_id),
            SUM(f.stars_count),
            SUM(f.forks_count),
            ROUND(AVG(f.stars_count), 2)
        FROM fact_repo_stats f
        JOIN dim_project p ON f.project_id = p.project_id
        GROUP BY p.language, f.snapshot_date
        ON DUPLICATE KEY UPDATE
            repo_count  = VALUES(repo_count),
            total_stars = VALUES(total_stars),
            total_forks = VALUES(total_forks),
            avg_stars   = VALUES(avg_stars);
        """
        cursor.execute(sql_language)
        print(f"  ✅ dws_language_daily —— {cursor.rowcount} 行")

        # ================================================================
        # 3. DWS-组织日汇总（dws_org_daily）
        # ================================================================

        # 第1步：INSERT 基础值
        sql_org_insert = """
        INSERT INTO dws_org_daily
            (org_name, snapshot_date, repo_count, total_stars, total_forks)
        SELECT
            org_name,
            snapshot_date,
            COUNT(DISTINCT project_id) AS repo_count,
            SUM(stars_count)           AS total_stars,
            SUM(forks_count)           AS total_forks
        FROM fact_repo_stats
        GROUP BY org_name, snapshot_date
        ON DUPLICATE KEY UPDATE
            repo_count  = VALUES(repo_count),
            total_stars = VALUES(total_stars),
            total_forks = VALUES(total_forks);
        """
        cursor.execute(sql_org_insert)
        print(f"  ✅ dws_org_daily（基础值写入）—— {cursor.rowcount} 行")

        # 第2步：UPDATE 增量 = 今天 repo_count - 昨天 repo_count
        sql_org_update = """
        UPDATE dws_org_daily t
        LEFT JOIN dws_org_daily y
            ON t.org_name = y.org_name
            AND y.snapshot_date = DATE_SUB(t.snapshot_date, INTERVAL 1 DAY)
        SET t.curr_day_new_repos = t.repo_count - COALESCE(y.repo_count, t.repo_count);
        """
        cursor.execute(sql_org_update)
        print(f"  ✅ dws_org_daily（增量计算）—— {cursor.rowcount} 行")

        # ================================================================
        # 4. DWS-平台日汇总（无增量字段，直接聚合）
        # ================================================================
        sql_platform = """
        INSERT INTO dws_platform_daily
            (source_platform, snapshot_date, repo_count, total_stars, active_projects)
        SELECT
            p.source_platform,
            f.snapshot_date,
            COUNT(DISTINCT f.project_id),
            SUM(f.stars_count),
            COUNT(DISTINCT CASE WHEN f.open_issues_count > 0
                                THEN f.project_id END) AS active_projects
        FROM fact_repo_stats f
        JOIN dim_project p ON f.project_id = p.project_id
        GROUP BY p.source_platform, f.snapshot_date
        ON DUPLICATE KEY UPDATE
            repo_count      = VALUES(repo_count),
            total_stars     = VALUES(total_stars),
            active_projects = VALUES(active_projects);
        """
        cursor.execute(sql_platform)
        print(f"  ✅ dws_platform_daily —— {cursor.rowcount} 行")

        conn.commit()
        print("✅ DWS 全量 ETL 执行成功（4张表全部刷新）")

    except MySQLError as e:
        conn.rollback()
        print(f"❌ ETL 执行异常，已回滚：{e}")
        raise
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    etl_dwd_to_dws()
