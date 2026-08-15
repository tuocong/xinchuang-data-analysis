"""
日期维度表填充脚本（一次性运行）
功能：生成 dim_date 表 2010-01-01 ~ 2030-12-31 的完整日期维度数据
运行命令：python scripts/fill_dim_date.py
"""
import sys
import logging
from pathlib import Path
from datetime import date, timedelta

# ---- 项目根目录 & 配置 ----
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pymysql
from project_config import DB_CONFIG

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

DB = DB_CONFIG

START_DATE = date(2010, 1, 1)
END_DATE = date(2030, 12, 31)

INSERT_SQL = """
    INSERT INTO dim_date (date_id, year, quarter, month, day,
                          week_of_year, day_of_week, is_weekend)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
        year = VALUES(year),
        quarter = VALUES(quarter),
        month = VALUES(month),
        day = VALUES(day),
        week_of_year = VALUES(week_of_year),
        day_of_week = VALUES(day_of_week),
        is_weekend = VALUES(is_weekend)
"""


def generate_rows(start: date, end: date):
    """生成日期维度行"""
    current = start
    while current <= end:
        iso = current.isocalendar()
        yield (
            current,                          # date_id
            current.year,                     # year
            (current.month - 1) // 3 + 1,     # quarter
            current.month,                    # month
            current.day,                      # day
            iso[1],                           # week_of_year (ISO)
            current.isoweekday(),             # day_of_week (1=Mon, 7=Sun)
            1 if current.isoweekday() >= 6 else 0,  # is_weekend
        )
        current += timedelta(days=1)


def main():
    conn = pymysql.connect(**DB)
    cursor = conn.cursor()

    # 检查是否已有数据
    cursor.execute("SELECT COUNT(*) FROM dim_date")
    existing = cursor.fetchone()[0]
    if existing > 0:
        logger.info(f"dim_date 表已有 {existing} 条数据，跳过填充（如需重建请先 TRUNCATE）")
        cursor.close()
        conn.close()
        return

    total_days = (END_DATE - START_DATE).days + 1
    logger.info(f"开始填充 dim_date：{START_DATE} ~ {END_DATE}，共 {total_days} 天")

    batch = []
    batch_size = 1000
    inserted = 0

    for row in generate_rows(START_DATE, END_DATE):
        batch.append(row)
        if len(batch) >= batch_size:
            cursor.executemany(INSERT_SQL, batch)
            conn.commit()
            inserted += len(batch)
            logger.info(f"进度：{inserted}/{total_days}")
            batch.clear()

    # 最后一批
    if batch:
        cursor.executemany(INSERT_SQL, batch)
        conn.commit()
        inserted += len(batch)

    cursor.close()
    conn.close()
    logger.info(f"[OK] dim_date 填充完成！共插入/更新 {inserted} 条")


if __name__ == "__main__":
    main()
