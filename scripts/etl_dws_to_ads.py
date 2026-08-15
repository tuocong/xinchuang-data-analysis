"""
ADS ETL脚本：DWS汇总表 → ADS应用表（5张表，直接供前端 API / ECharts 查询）

与计划脚本的5处修正：
  1. today 改为 MAX(snapshot_date) —— 计划用 datetime.now()=2026-08-09，但库里有数据的只有 8/7、8/8
  2. ADS-2 star_growth 改用 dws_project_daily.curr_day_new_stars —— 不再在 fact 单天子查询里用 LAG()
  3. ADS-4 列名修复：new_repos→org表, active_repos→platform表, stars_count→total_cum_stars
  4. ADS-4 cumulative_stars 用 SUM() OVER() 跨月累加，而非单月值
  5. ADS-5 source_platform 从 dim_org JOIN 获取，不再硬编码 'gitee'
"""
import pymysql
from pymysql.err import MySQLError


def etl_dws_to_ads():
    conn = pymysql.connect(
        host='localhost',
        user='root',
        password='Tuocong666;',
        database='xinchuang_dw',
        charset='utf8mb4'
    )
    cursor = conn.cursor()

    try:
        # ============================================================
        # 公共：取最新数据日期（有数据的最新一天，不是 today）
        # ============================================================
        cursor.execute("SELECT MAX(snapshot_date) FROM fact_repo_stats")
        latest_date = cursor.fetchone()[0]
        if latest_date is None:
            print("❌ fact_repo_stats 无数据，请先跑 DWD ETL")
            return

        print(f"[DATE] 最新数据日期：{latest_date}")

        # ============================================================
        # ADS-1：平台概览（大屏顶部数字卡片）
        # 数据来源：dim_project + fact_repo_stats（一次性 JOIN 取全貌）
        # ============================================================
        sql_overview = """
        INSERT INTO ads_overview
            (stat_date, total_repos, total_stars, total_forks,
             total_orgs, gitee_repos, github_repos, avg_stars)
        SELECT
            %s,
            COUNT(DISTINCT p.project_id),
            COALESCE(SUM(f.stars_count), 0),
            COALESCE(SUM(f.forks_count), 0),
            COUNT(DISTINCT f.org_name),
            COUNT(DISTINCT CASE WHEN p.source_platform = 'gitee'  THEN p.project_id END),
            COUNT(DISTINCT CASE WHEN p.source_platform = 'github' THEN p.project_id END),
            ROUND(COALESCE(AVG(f.stars_count), 0), 2)
        FROM dim_project p
        LEFT JOIN fact_repo_stats f
            ON p.project_id = f.project_id
            AND f.snapshot_date = %s
        ON DUPLICATE KEY UPDATE
            total_repos  = VALUES(total_repos),
            total_stars  = VALUES(total_stars),
            total_forks  = VALUES(total_forks),
            total_orgs   = VALUES(total_orgs),
            gitee_repos  = VALUES(gitee_repos),
            github_repos = VALUES(github_repos),
            avg_stars    = VALUES(avg_stars);
        """
        cursor.execute(sql_overview, (latest_date, latest_date))
        print(f"  ✅ ads_overview —— {cursor.rowcount} 行")

        # ============================================================
        # ADS-2：项目排名 TOP20（柱状图）
        # 修正：star_growth 直接取 dws_project_daily.curr_day_new_stars
        #       （DWS ETL 已用两步法正确计算过增量，无需在 ADS 再算）
        # ============================================================
        sql_ranking = """
        INSERT INTO ads_project_ranking
            (stat_date, rank_num, project_name, full_name, org_name,
             language, stars_count, forks_count, star_growth, source_platform)
        SELECT
            %s,
            ROW_NUMBER() OVER (ORDER BY p.total_cum_stars DESC) AS rn,
            d.project_name,
            d.full_name,
            f.org_name,
            d.language,
            p.total_cum_stars,
            p.total_cum_forks,
            p.curr_day_new_stars,
            d.source_platform
        FROM dws_project_daily p
        JOIN dim_project d ON p.project_id = d.project_id
        LEFT JOIN fact_repo_stats f
            ON p.project_id = f.project_id
            AND p.snapshot_date = f.snapshot_date
        WHERE p.snapshot_date = %s
        ORDER BY p.total_cum_stars DESC
        LIMIT 20
        ON DUPLICATE KEY UPDATE
            project_name    = VALUES(project_name),
            full_name       = VALUES(full_name),
            org_name        = VALUES(org_name),
            language        = VALUES(language),
            stars_count     = VALUES(stars_count),
            forks_count     = VALUES(forks_count),
            star_growth     = VALUES(star_growth),
            source_platform = VALUES(source_platform);
        """
        cursor.execute(sql_ranking, (latest_date, latest_date))
        print(f"  ✅ ads_project_ranking —— {cursor.rowcount} 行")

        # ============================================================
        # ADS-3：语言分布（饼图/环形图）
        # 直接从 dws_language_daily 取，用 SUM() OVER() 算占比
        # ============================================================
        sql_language = """
        INSERT INTO ads_language_dist
            (stat_date, language, repo_count, total_stars, pct_of_total)
        SELECT
            %s,
            language,
            repo_count,
            total_stars,
            ROUND(total_stars * 100.0 / NULLIF(SUM(total_stars) OVER(), 0), 2) AS pct_of_total
        FROM dws_language_daily
        WHERE snapshot_date = %s
        ON DUPLICATE KEY UPDATE
            repo_count   = VALUES(repo_count),
            total_stars  = VALUES(total_stars),
            pct_of_total = VALUES(pct_of_total);
        """
        cursor.execute(sql_language, (latest_date, latest_date))
        print(f"  ✅ ads_language_dist —— {cursor.rowcount} 行")

        # ============================================================
        # ADS-4：月度趋势（折线图/面积图）
        # 修正：多表聚合 —— 新仓库从 org 层、增量从 project 层、活跃从 platform 层
        # cumulative_stars 取本月最后一天的平台汇总值（不是跨天跨平台累加）
        # ============================================================
        sql_monthly = """
        INSERT INTO ads_monthly_trend
            (stat_month, new_repos, active_repos, new_stars, cumulative_stars)
        SELECT
            m.month,
            COALESCE(o.new_repos_sum, 0),
            COALESCE(plat.active_sum, 0),
            COALESCE(p.new_stars_sum, 0),
            COALESCE(
                (SELECT SUM(total_stars)
                 FROM dws_platform_daily
                 WHERE snapshot_date = (
                     SELECT MAX(snapshot_date) FROM dws_platform_daily
                     WHERE DATE_FORMAT(snapshot_date, '%Y-%m') = m.month
                 )
                ), 0
            ) AS cumulative_stars
        FROM (
            SELECT DISTINCT DATE_FORMAT(snapshot_date, '%Y-%m') AS month
            FROM dws_project_daily
        ) m
        LEFT JOIN (
            SELECT DATE_FORMAT(snapshot_date, '%Y-%m') AS month,
                   SUM(curr_day_new_repos) AS new_repos_sum
            FROM dws_org_daily
            GROUP BY DATE_FORMAT(snapshot_date, '%Y-%m')
        ) o ON m.month = o.month
        LEFT JOIN (
            SELECT DATE_FORMAT(snapshot_date, '%Y-%m') AS month,
                   SUM(curr_day_new_stars) AS new_stars_sum
            FROM dws_project_daily
            GROUP BY DATE_FORMAT(snapshot_date, '%Y-%m')
        ) p ON m.month = p.month
        LEFT JOIN (
            SELECT DATE_FORMAT(snapshot_date, '%Y-%m') AS month,
                   SUM(active_projects) AS active_sum
            FROM dws_platform_daily
            GROUP BY DATE_FORMAT(snapshot_date, '%Y-%m')
        ) plat ON m.month = plat.month
        ON DUPLICATE KEY UPDATE
            new_repos        = VALUES(new_repos),
            active_repos     = VALUES(active_repos),
            new_stars        = VALUES(new_stars),
            cumulative_stars = VALUES(cumulative_stars);
        """
        cursor.execute(sql_monthly)
        print(f"  ✅ ads_monthly_trend —— {cursor.rowcount} 行")

        # ============================================================
        # ADS-5：组织对比（横向柱状图）
        # 修正：source_platform 从 dim_org JOIN 获取，不再硬编码 'gitee'
        # ============================================================
        sql_orgcmp = """
        INSERT INTO ads_org_compare
            (stat_date, org_name, source_platform,
             repo_count, total_stars, avg_stars, active_rate)
        SELECT
            %s,
            o.org_name,
            COALESCE(d.source_platform, 'unknown'),
            o.repo_count,
            o.total_stars,
            ROUND(o.total_stars * 1.0 / NULLIF(o.repo_count, 0), 2) AS avg_stars,
            -- 有新增仓库视为活跃，百分比在单个日期上为 0 或 100
            CASE WHEN o.curr_day_new_repos > 0 THEN 100.00 ELSE 0.00 END AS active_rate
        FROM dws_org_daily o
        LEFT JOIN dim_org d ON o.org_name = d.org_name
        WHERE o.snapshot_date = %s
        ORDER BY o.total_stars DESC
        ON DUPLICATE KEY UPDATE
            source_platform = VALUES(source_platform),
            repo_count      = VALUES(repo_count),
            total_stars     = VALUES(total_stars),
            avg_stars       = VALUES(avg_stars),
            active_rate     = VALUES(active_rate);
        """
        cursor.execute(sql_orgcmp, (latest_date, latest_date))
        print(f"  ✅ ads_org_compare —— {cursor.rowcount} 行")

        conn.commit()
        print(f"✅ ADS 全量 ETL 执行成功（5张表全部刷新，日期={latest_date}）")

    except MySQLError as e:
        conn.rollback()
        print(f"❌ ETL 执行异常，已回滚：{e}")
        raise
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    etl_dws_to_ads()
