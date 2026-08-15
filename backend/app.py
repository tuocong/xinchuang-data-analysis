"""
信创数据分析 — Flask API 后端 + 大屏前端
同时托管 API 和前端页面，浏览器访问 http://localhost:5000 即可看到大屏

启动方式：
    python backend/app.py

依赖：pip install flask flask-cors pymysql
"""
import sys
import json
import csv
import io
import datetime
from decimal import Decimal
from pathlib import Path

# 确保项目根目录在 sys.path 中，以便 import project_config
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flask import Flask, g, request, send_from_directory
from flask_cors import CORS
import pymysql
from project_config import DB_CONFIG
import os
import jwt
from functools import wraps
from werkzeug.security import check_password_hash, generate_password_hash
from dotenv import load_dotenv
load_dotenv()  # 自动读取 .env 文件里的环境变量

SECRET_KEY = os.getenv("JWT_SECRET","xinchuang-2026-secret")  # JWT 密钥，用于生成和验证 token

app = Flask(__name__, static_folder=None)
CORS(app)

# 前端文件目录（项目根目录下的 frontend/）
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


# ============================================================
# 自定义 JSON 序列化：date → "2026-08-09"，Decimal → float
# ============================================================
class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            return obj.strftime("%Y-%m-%d %H:%M:%S")
        if isinstance(obj, datetime.date):
            return obj.strftime("%Y-%m-%d")
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


app.json_encoder = CustomJSONEncoder


def json_result(data):
    """统一 JSON 响应，用自定义 encoder 处理 date/Decimal"""
    return app.response_class(
        response=json.dumps({"code": 0, "data": data}, cls=CustomJSONEncoder, ensure_ascii=False),
        mimetype="application/json; charset=utf-8",
    )
def json_error(msg, status=400):
    return app.response_class(
        response=json.dumps({"code": status, "msg": msg}, ensure_ascii=False),
        status=status, mimetype="application/json; charset=utf-8",
    )


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return json_error("未登录", 401)
        token = auth[7:]
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            return json_error("登录已过期，请重新登录", 401)
        except jwt.InvalidTokenError:
            return json_error("无效的登录凭证", 401)
        g.current_user = payload
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    """要求管理员角色（必须叠在 @login_required 下面，先登录后鉴权）"""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if g.current_user.get("role") != "admin":
            return json_error("无权限，需要管理员账号", 403)
        return f(*args, **kwargs)
    return wrapper


def log_action(username, action, detail=""):
    """写操作日志到 sys_log，写入失败不影响主流程"""
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO sys_log (username, action, detail, ip) VALUES (%s, %s, %s, %s)",
                (username, action, detail, request.remote_addr or "")
            )
        conn.commit()
        conn.close()
    except Exception:
        pass


# ============================================================
# 数据库连接工具
# ============================================================
def get_conn():
    return pymysql.connect(**DB_CONFIG)


def query_one(sql, params=None):
    """执行查询，返回单行 dict"""
    conn = get_conn()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute(sql, params)
            return cur.fetchone()
    finally:
        conn.close()


def query_all(sql, params=None):
    """执行查询，返回多行 list[dict]"""
    conn = get_conn()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute(sql, params)
            return cur.fetchall()
    finally:
        conn.close()


# ============================================================
# API-1：概览统计（大屏顶部4个数字卡片）
# GET /api/overview
# ============================================================
@app.route("/api/overview")
def api_overview():
    row = query_one("""
        SELECT
            stat_date        AS statDate,
            total_repos      AS totalRepos,
            total_stars      AS totalStars,
            total_forks      AS totalForks,
            avg_stars        AS avgStars,
            total_orgs       AS totalOrgs,
            gitee_repos      AS giteeRepos,
            github_repos     AS githubRepos
        FROM ads_overview
        ORDER BY stat_date DESC
        LIMIT 1
    """)
    return json_result(row)


# ============================================================
# API-2：项目排名 TOP20（柱状图数据）
# GET /api/ranking
# ============================================================
@app.route("/api/ranking")
def api_ranking():
    rows = query_all("""
        SELECT
            rank_num        AS ranking,
            project_name    AS projectName,
            full_name       AS fullName,
            org_name        AS orgName,
            language        AS language,
            stars_count     AS starsCount,
            forks_count     AS forksCount,
            star_growth     AS starGrowth,
            source_platform AS platform
        FROM ads_project_ranking
        WHERE stat_date = (SELECT MAX(stat_date) FROM ads_project_ranking)
        ORDER BY rank_num
    """)
    return json_result(rows)


# ============================================================
# API-3：语言分布（饼图/环形图数据）
# GET /api/language
# ============================================================
@app.route("/api/language")
def api_language():
    rows = query_all("""
        SELECT
            language      AS language,
            repo_count    AS repoCount,
            total_stars   AS totalStars,
            pct_of_total  AS pctOfTotal
        FROM ads_language_dist
        WHERE stat_date = (SELECT MAX(stat_date) FROM ads_language_dist)
        ORDER BY repo_count DESC
    """)
    return json_result(rows)


# ============================================================
# API-4：月度趋势（折线图/面积图数据）
# GET /api/trend
# ============================================================
@app.route("/api/trend")
def api_trend():
    rows = query_all("""
        SELECT
            stat_month       AS month,
            new_repos        AS newRepos,
            active_repos     AS activeRepos,
            new_stars        AS newStars,
            cumulative_stars AS cumulativeStars
        FROM ads_monthly_trend
        ORDER BY stat_month ASC
    """)
    return json_result(rows)


# ============================================================
# API-5：组织对比（横向柱状图数据）
# GET /api/org-compare
# ============================================================
@app.route("/api/org-compare")
def api_org_compare():
    rows = query_all("""
        SELECT
            org_name        AS orgName,
            source_platform AS platform,
            repo_count      AS repoCount,
            total_stars     AS totalStars,
            avg_stars       AS avgStars,
            active_rate     AS activeRate
        FROM ads_org_compare
        WHERE stat_date = (SELECT MAX(stat_date) FROM ads_org_compare)
        ORDER BY total_stars DESC
    """)
    return json_result(rows)


# ============================================================
# API-6：组织仓库明细（组织钻取页，点击组织展开仓库列表）
# GET /api/org-repos?org=<组织名>
# ============================================================
@app.route("/api/org-repos")
def api_org_repos():
    org = (request.args.get("org") or "").strip()
    if not org:
        return json_result([])
    rows = query_all("""
        SELECT
            p.full_name       AS fullName,
            p.language        AS language,
            p.source_platform AS platform,
            f.stars_count     AS starsCount,
            f.forks_count     AS forksCount,
            f.watchers_count  AS watchersCount,
            f.snapshot_date   AS snapshotDate
        FROM fact_repo_stats f
        JOIN dim_project p ON p.project_id = f.project_id
        WHERE f.org_name = %s
          AND f.snapshot_date = (SELECT MAX(snapshot_date) FROM fact_repo_stats)
        ORDER BY f.stars_count DESC
    """, (org,))
    return json_result(rows)


# ============================================================
# API-7：仓库全量明细（数据管理分页表 + 仓库对比数据源）
# GET /api/repos
# ============================================================
@app.route("/api/repos")
def api_repos():
    rows = query_all("""
        SELECT
            p.full_name         AS fullName,
            p.language          AS language,
            p.source_platform   AS platform,
            f.org_name          AS orgName,
            f.stars_count       AS starsCount,
            f.forks_count       AS forksCount,
            f.watchers_count    AS watchersCount,
            f.open_issues_count AS openIssuesCount,
            f.snapshot_date     AS snapshotDate
        FROM fact_repo_stats f
        JOIN dim_project p ON p.project_id = f.project_id
        WHERE f.snapshot_date = (SELECT MAX(snapshot_date) FROM fact_repo_stats)
        ORDER BY f.stars_count DESC
    """)
    return json_result(rows)


# ============================================================
# 健康检查
# ============================================================
@app.route("/api/health")
def api_health():
    try:
        conn = get_conn()
        conn.ping()
        conn.close()
        return json_result({"msg": "ok", "db": "connected"})
    except Exception as e:
        return json_result({"msg": str(e), "db": "disconnected"})

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json() or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")

    row = query_one("SELECT * FROM sys_user WHERE username = %s", (username,))
    if not row or row["status"] != 1:
        return json_error("用户名不存在或已被禁用", 401)

    if not check_password_hash(row["password_hash"], password):
        return json_error("密码错误", 401)

    token = jwt.encode(
        {"user_id": row["user_id"], "username": row["username"], "role": row["role"]},
        SECRET_KEY, algorithm="HS256",
    )
    log_action(row["username"], "登录", "用户登录成功")
    return json_result({
        "token": token,
        "user": {"username": row["username"], "role": row["role"]}
    })

@app.route("/api/me")
@login_required
def api_me():
    return json_result({"username": g.current_user["username"],
                        "role": g.current_user["role"]})


# ============================================================
# 用户管理（管理员专属，注意：不返回 password_hash）
# ============================================================
@app.route("/api/users")
@login_required
@admin_required
def api_users():
    rows = query_all("""
        SELECT user_id, username, role, status, create_time
        FROM sys_user ORDER BY user_id
    """)
    return json_result(rows)


@app.route("/api/users", methods=["POST"])
@login_required
@admin_required
def api_user_create():
    data = request.get_json() or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")
    role = data.get("role", "user")
    if not username or not password:
        return json_error("用户名和密码不能为空", 400)
    if role not in ("admin", "user"):
        return json_error("角色只能是 admin 或 user", 400)
    if query_one("SELECT user_id FROM sys_user WHERE username = %s", (username,)):
        return json_error("用户名已存在", 400)
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO sys_user (username, password_hash, role) VALUES (%s, %s, %s)",
                (username, generate_password_hash(password), role)
            )
        conn.commit()
    finally:
        conn.close()
    log_action(g.current_user["username"], "新增用户", username)
    return json_result({"msg": "创建成功"})


@app.route("/api/users/<int:user_id>", methods=["PUT"])
@login_required
@admin_required
def api_user_update(user_id):
    data = request.get_json() or {}
    role = data.get("role")
    status = data.get("status")
    # 防止管理员把自己降级锁死
    if user_id == g.current_user["user_id"] and role and role != "admin":
        return json_error("不能修改自己的角色", 400)
    sets, params = [], []
    if role:
        if role not in ("admin", "user"):
            return json_error("角色只能是 admin 或 user", 400)
        sets.append("role = %s"); params.append(role)
    if status is not None:
        sets.append("status = %s"); params.append(status)
    if not sets:
        return json_error("没有需要更新的字段", 400)
    params.append(user_id)
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(f"UPDATE sys_user SET {', '.join(sets)} WHERE user_id = %s", params)
        conn.commit()
    finally:
        conn.close()
    log_action(g.current_user["username"], "修改用户", f"user_id={user_id}")
    return json_result({"msg": "更新成功"})


@app.route("/api/users/<int:user_id>", methods=["DELETE"])
@login_required
@admin_required
def api_user_delete(user_id):
    if user_id == g.current_user["user_id"]:
        return json_error("不能删除自己", 400)
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM sys_user WHERE user_id = %s", (user_id,))
        conn.commit()
    finally:
        conn.close()
    log_action(g.current_user["username"], "删除用户", f"user_id={user_id}")
    return json_result({"msg": "删除成功"})


# ============================================================
# 操作日志查询（管理员专属）
# ============================================================
@app.route("/api/logs")
@login_required
@admin_required
def api_logs():
    rows = query_all("""
        SELECT log_id, username, action, detail, ip, create_time
        FROM sys_log ORDER BY log_id DESC LIMIT 200
    """)
    return json_result(rows)


@app.route("/api/change-password", methods=["POST"])
@login_required
def api_change_password():
    data = request.get_json() or {}
    old = data.get("old_password", "")
    new = data.get("new_password", "")
    if not old or len(new) < 6:
        return json_error("新密码至少 6 位", 400)
    row = query_one("SELECT password_hash FROM sys_user WHERE user_id = %s",
                    (g.current_user["user_id"],))
    if not row or not check_password_hash(row["password_hash"], old):
        return json_error("原密码错误", 400)
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE sys_user SET password_hash = %s WHERE user_id = %s",
                        (generate_password_hash(new), g.current_user["user_id"]))
        conn.commit()
    finally:
        conn.close()
    log_action(g.current_user["username"], "修改密码", "修改登录密码")
    return json_result({"msg": "密码修改成功"})


@app.route("/api/my-stats")
@login_required
def api_my_stats():
    uname = g.current_user["username"]
    login_count = query_one("SELECT COUNT(*) AS c FROM sys_log WHERE username=%s AND action='登录'", (uname,))["c"]
    export_count = query_one("SELECT COUNT(*) AS c FROM sys_log WHERE username=%s AND action='导出'", (uname,))["c"]
    log_count = query_one("SELECT COUNT(*) AS c FROM sys_log WHERE username=%s", (uname,))["c"]
    return json_result({"loginCount": login_count, "exportCount": export_count, "logCount": log_count, "favCount": 0})


@app.route("/api/export")
@login_required
def api_export():
    q = (request.args.get("q") or "").strip()
    sql = """
        SELECT p.full_name AS fullName, f.org_name AS orgName, p.language AS language,
               p.source_platform AS platform, f.stars_count AS stars,
               f.forks_count AS forks, f.watchers_count AS watchers,
               f.open_issues_count AS issues, f.snapshot_date AS statDate
        FROM fact_repo_stats f
        JOIN dim_project p ON p.project_id = f.project_id
        WHERE f.snapshot_date = (SELECT MAX(snapshot_date) FROM fact_repo_stats)
    """
    params = None
    if q:
        sql += " AND (p.full_name LIKE %s OR f.org_name LIKE %s OR p.language LIKE %s)"
        like = f"%{q}%"
        params = (like, like, like)
    sql += " ORDER BY f.stars_count DESC"
    rows = query_all(sql, params)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["仓库全名", "组织", "语言", "平台", "Star", "Fork", "Watch", "Issues", "统计日期"])
    for r in rows:
        writer.writerow([r["fullName"], r["orgName"], r["language"], r["platform"],
                         r["stars"], r["forks"], r["watchers"], r["issues"], r["statDate"]])
    resp = app.response_class("﻿" + buf.getvalue(), mimetype="text/csv")
    resp.headers["Content-Disposition"] = "attachment; filename=repos_export.csv"
    log_action(g.current_user["username"], "导出", "导出仓库数据" + ("（筛选：" + q + "）" if q else ""))
    return resp


# ============================================================
# 前端页面托管（同源访问，无需跨域）
# ============================================================
@app.route("/")
def serve_index():
    return send_from_directory(str(FRONTEND_DIR), "index.html")


@app.route("/<path:filename>")
def serve_static(filename):
    return send_from_directory(str(FRONTEND_DIR), filename)


# ============================================================
# 启动入口
# ============================================================
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    print(f"""
╔══════════════════════════════════════════╗
║   信创数据分析 — 大屏 API 服务           ║
╠══════════════════════════════════════════╣
║   大屏: http://localhost:{args.port}              ║
║   概览: /api/overview                   ║
║   排名: /api/ranking                    ║
║   语言: /api/language                   ║
║   趋势: /api/trend                      ║
║   对比: /api/org-compare                ║
║   健康: /api/health                     ║
╚══════════════════════════════════════════╝
    """)
    app.run(host=args.host, port=args.port, debug=True)
