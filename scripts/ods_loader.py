"""
ODS层数据加载器【双平台幂等版】
功能：读取清洗后 repos_cleaned.json → 批量写入 ods_repos_raw
运行命令：python scripts/ods_loader.py

优化点：
1. DB配置从 project_config 统一读取，不再硬编码密码
2. 先删当日分区再写入，任务重跑不产生重复数据（幂等性）
3. 字段归一化兜底，规避KeyError、数据类型异常
"""
import json
import os
import sys
import logging
from pathlib import Path
from datetime import datetime

# ---- 项目根目录 & 配置 ----
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pymysql
from project_config import DB_CONFIG

# ====================== 日志 ======================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# ====================== 全局配置 ======================
CONFIG = {
    "cleaned_json_path": PROJECT_ROOT / "data" / "cleaned" / "repos_cleaned.json",
    "batch_size": 100,
    "target_table": "ods_repos_raw",
}
# DB配置从 project_config.DB_CONFIG 读取（唯一入口）
DB = DB_CONFIG


def normalize_row(item: dict, dt: str) -> dict:
    """数据行归一化：字段兜底、空值填充、bool→0/1、list→字符串"""
    license_val = item.get("license_type") or item.get("license", "")
    topics_val = item.get("topics", "")
    if isinstance(topics_val, list):
        topics_val = ", ".join(topics_val)

    # 兜底截断（防突破 MySQL VARCHAR/TEXT 限制）
    desc_val = str(item.get("description") or "")[:15000]
    full_name_val = str(item.get("full_name", ""))[:250]
    html_url_val = str(item.get("html_url", ""))[:250]

    return {
        "repo_id": item["repo_id"],
        "org": item.get("org", ""),
        "name": item.get("name", ""),
        "full_name": full_name_val,
        "description": desc_val,
        "stars_count": item.get("stars_count", 0),
        "forks_count": item.get("forks_count", 0),
        "watchers_count": item.get("watchers_count", 0),
        "open_issues_count": item.get("open_issues_count", 0),
        "language": item.get("language") or "未标注",
        "default_branch": item.get("default_branch", ""),
        "html_url": html_url_val,
        "topics": topics_val,
        "license_type": license_val,
        "homepage": item.get("homepage", ""),
        "archived": 1 if item.get("archived") in (True, 1, "1") else 0,
        "created_at": item.get("created_at", ""),
        "updated_at": item.get("updated_at", ""),
        "pushed_at": item.get("pushed_at", ""),
        "source_platform": item.get("source_platform", "unknown"),
        "dt": dt,
    }


def load_clean_data(file_path):
    """加载清洗后的JSON文件"""
    if not os.path.exists(file_path):
        logger.error(f"[ERROR] 文件不存在：{file_path}\n请先执行 cleaner.py 生成清洗文件！")
        raise FileNotFoundError("缺少 repos_cleaned.json")
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    logger.info(f"[OK] 加载清洗数据集：{len(data)} 条")
    return data


def get_insert_sql(table_name: str) -> str:
    """组装 INSERT SQL"""
    cols = [
        "repo_id", "org", "name", "full_name", "description",
        "stars_count", "forks_count", "watchers_count", "open_issues_count",
        "language", "default_branch", "html_url",
        "topics", "license_type", "homepage", "archived",
        "created_at", "updated_at", "pushed_at", "source_platform", "dt",
    ]
    placeholders = ", ".join(f"%({c})s" for c in cols)
    return f"INSERT INTO {table_name} ({', '.join(cols)}) VALUES ({placeholders})"


def main():
    dt = datetime.now().strftime("%Y-%m-%d")
    raw_data = load_clean_data(CONFIG["cleaned_json_path"])
    data_rows = [normalize_row(row, dt) for row in raw_data]

    gitee_count = sum(1 for r in data_rows if r["source_platform"] == "gitee")
    github_count = sum(1 for r in data_rows if r["source_platform"] == "github")
    logger.info(f"[STAT] 数据分布 | Gitee：{gitee_count} 条 | GitHub：{github_count} 条")

    insert_sql = get_insert_sql(CONFIG["target_table"])
    conn = None
    cursor = None
    try:
        conn = pymysql.connect(**DB)
        cursor = conn.cursor()

        # 幂等：先删当日分区，再写入
        del_sql = f"DELETE FROM {CONFIG['target_table']} WHERE dt = %s"
        del_rows = cursor.execute(del_sql, (dt,))
        if del_rows > 0:
            logger.info(f"[CLEAN] 清除当日历史重复数据：{del_rows} 条")
        conn.commit()

        # 批量写入
        total = len(data_rows)
        batch_size = CONFIG["batch_size"]
        for start in range(0, total, batch_size):
            batch = data_rows[start:start + batch_size]
            cursor.executemany(insert_sql, batch)
            conn.commit()
            finished = min(start + batch_size, total)
            logger.info(f"写入进度：{finished}/{total}")

        logger.info(f"[DONE] ODS入库完成！总计入库 {total} 条")

    except Exception as err:
        logger.error(f"[ERROR] 入库异常：{err}")
        if conn:
            conn.rollback()
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
        logger.info("数据库连接已释放")


if __name__ == "__main__":
    main()
