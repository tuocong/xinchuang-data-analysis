"""
项目全局配置文件【双平台版：Gitee + GitHub】
所有敏感信息从 .env 环境变量读取，本文件可安全提交至 Git。
⚠️ 请复制 .env.example → .env，填入真实 Token 和数据库密码。
"""
import os
from pathlib import Path

# ===================== 项目根目录（自动识别） =====================
PROJECT_ROOT = Path(__file__).resolve().parent

# ===================== 加载 .env 文件（无需安装 python-dotenv） =====================
def _load_dotenv(env_path: Path):
    """手动解析 .env 文件，写入 os.environ"""
    if not env_path.exists():
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip()
            if value and key not in os.environ:  # 不覆盖已设的系统环境变量
                os.environ[key] = value

_load_dotenv(PROJECT_ROOT / ".env")

# ===================== 数据库配置（统一入口） =====================
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "xinchuang_dw"),
    "charset": "utf8mb4",
}

# ===================== Gitee 配置 =====================
GITEE_TOKEN = os.getenv("GITEE_TOKEN", "")
GITEE_API_BASE = "https://gitee.com/api/v5"
GITEE_ORGS = [
    "openeuler",
    "src-openeuler",
    "mindspore",
    "opengauss",
    "openlookeng",
    # === 信创生态 ===
    "anolis",               # 龙蜥社区（阿里）
    "deepin-community",     # 深度/deepin（统信）
    "openatom-foundation",  # 开放原子基金会（OpenHarmony等）
    "ubuntukylin",          # 优麒麟
    "openkylin",            # 开放麒麟
    "openEuler-riscv",      # openEuler RISC-V
    "kunpengcompute",       # 鲲鹏
]

# ===================== GitHub 配置 =====================
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_API_BASE = "https://api.github.com"
GITHUB_ORGS = [
    "mindspore-ai",
    "PaddlePaddle",
    "kubeedge",
    "karmada-io",
    "volcano-sh",
    "openlookeng",
    "openGemini",
    # === 大厂开源 + 云原生 ===
    "kubernetes",
    "apache",
    "tensorflow",
    "pytorch",
    "pingcap",              # TiDB
    "grafana",
    "prometheus",
    "etcd-io",
    "cncf",                 # 云原生计算基金会
    "trinodb",
    "rust-lang",
    "golang",
]

# ===================== 通用采集参数 =====================
PER_PAGE = 100               # 单页最大条数
REQUEST_INTERVAL = 0.5       # 请求休眠间隔（秒）

# ===================== 关键词搜索 =====================
SEARCH_KEYWORDS = [
    "xinchuang",
    "信创",
    "kunpeng",
    "ascend",
    "harmonyos",
    "openHarmony",
    "openEuler",
]
SEARCH_MAX_PAGES = 5          # 每个关键词最大页数

# 兼容旧版采集脚本（只跑 Gitee）
TARGET_ORGS = GITEE_ORGS
