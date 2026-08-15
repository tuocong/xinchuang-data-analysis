"""
ADS 月度趋势表 ETL 脚本（最终修复版）
修复1：created_at存在多种时区格式，采用LEFT(created_at,7)方式提取月份
修复2：基础月份序列从ODS全量历史数据生成，完整覆盖2008~2026所有月份
数据源：ODS层 ods_repos_raw + DWS层 dws_project_daily
运行方式：cd 到项目根目录，python scripts/etl_ads_monthly_trend.py
"""
import pymysql
from pymysql.err import MySQLError

def etl_ads_monthly_trend():
    conn = pymysql.connect(
        host='localhost',
        user='root',
        password='Tuocong666;',
        database='xinchuang_dw',
        charset='utf8mb4'
    )
    cursor = conn.cursor()
    try:
        sql = """
        INSERT INTO ads_monthly_trend (stat_month, new_repos, active_repos, new_stars, cumulative_stars)
        SELECT
            m.stat_month,
            COALESCE(n.new_repos, 0)       AS new_repos,
            COALESCE(a.active_repos, 0)    AS active_repos,
            COALESCE(s.new_stars, 0)       AS new_stars,
            COALESCE(c.cumulative_stars, 0) AS cumulative_stars
        FROM (
            SELECT DISTINCT LEFT(created_at, 7) AS stat_month
            FROM ods_repos_raw
            WHERE created_at IS NOT NULL AND created_at != ''
        ) m
        LEFT JOIN (
            SELECT
                LEFT(created_at, 7) AS stat_month,
                COUNT(*) AS new_repos
            FROM ods_repos_raw
            WHERE created_at IS NOT NULL AND created_at != ''
            GROUP BY LEFT(created_at, 7)
        ) n ON m.stat_month = n.stat_month
        LEFT JOIN (
            SELECT
                DATE_FORMAT(snapshot_date, '%Y-%m') AS stat_month,
                COUNT(DISTINCT project_id) AS active_repos
            FROM dws_project_daily
            GROUP BY DATE_FORMAT(snapshot_date, '%Y-%m')
        ) a ON m.stat_month = a.stat_month
        LEFT JOIN (
            SELECT
                DATE_FORMAT(snapshot_date, '%Y-%m') AS stat_month,
                SUM(curr_day_new_stars) AS new_stars
            FROM dws_project_daily
            GROUP BY DATE_FORMAT(snapshot_date, '%Y-%m')
        ) s ON m.stat_month = s.stat_month
        LEFT JOIN (
            SELECT
                stat_month,
                SUM(max_cum) AS cumulative_stars
            FROM (
                SELECT
                    DATE_FORMAT(snapshot_date, '%Y-%m') AS stat_month,
                    project_id,
                    MAX(total_cum_stars) AS max_cum
                FROM dws_project_daily
                GROUP BY DATE_FORMAT(snapshot_date, '%Y-%m'), project_id
            ) t
            GROUP BY stat_month
        ) c ON m.stat_month = c.stat_month
        ON DUPLICATE KEY UPDATE
            new_repos        = VALUES(new_repos),
            active_repos     = VALUES(active_repos),
            new_stars        = VALUES(new_stars),
            cumulative_stars = VALUES(cumulative_stars);
        """
        cursor.execute(sql)
        conn.commit()
        print(f"✅ ADS 月度趋势 ETL 执行成功，影响行数：{cursor.rowcount}")
    except MySQLError as e:
        conn.rollback()
        print(f"❌ ETL 执行异常，已回滚：{e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    etl_ads_monthly_trend()
