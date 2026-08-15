"""数据库连接测试"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pymysql
from project_config import DB_CONFIG

conn = pymysql.connect(**DB_CONFIG)
cursor = conn.cursor()
cursor.execute("SELECT 1 AS ok")
print(cursor.fetchone())  # 应输出 (1,)
conn.close()
print("OK - DB connection works")
