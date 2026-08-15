"""一次性：初始化 admin 账号（admin / admin123），只跑一次"""
from werkzeug.security import generate_password_hash
import pymysql

conn = pymysql.connect(
    host='localhost', user='root', password='Tuocong666;',
    database='xinchuang_dw', charset='utf8mb4'
)
cur = conn.cursor()
cur.execute(
    "INSERT INTO sys_user (username, password_hash, role) VALUES (%s, %s, 'admin') "
    "ON DUPLICATE KEY UPDATE role='admin'",
    ('admin', generate_password_hash('123456'))
)
conn.commit()
conn.close()
print('admin 账号已初始化，密码 123456')
