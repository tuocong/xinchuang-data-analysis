# 信创开源生态数据分析系统

> 基于 Flask + MySQL 的信创开源生态数据分析平台，采集 Gitee / GitHub 开源社区数据，构建 ODS → DWD → DWS → ADS 四层数据仓库，并以大屏可视化呈现信创生态全景。

## 📖 项目简介

本系统面向**信创（信息技术应用创新）**产业，对国产开源生态（openEuler、龙蜥、OpenHarmony、昇思、openGauss 等）进行数据采集、清洗、建模与可视化分析，帮助用户直观掌握信创开源生态的发展规模、活跃度与趋势。

核心特点：

- **双平台数据采集**：同时接入 Gitee 与 GitHub API，覆盖信创主流开源组织
- **四层数据仓库**：严格遵循 ODS（贴源）→ DWD（明细）→ DWS（汇总）→ ADS（应用）分层建模
- **大屏可视化**：ECharts 图表呈现排名、语言分布、组织对比、月度趋势
- **用户体系**：JWT 登录鉴权 + 管理员/普通用户角色权限
- **容器化部署**：Docker Compose 一键编排 MySQL + Web，开箱即用

## 🛠️ 技术栈

| 层次 | 技术 |
|---|---|
| 后端 | Python 3 · Flask · Flask-CORS |
| 数据库 | MySQL 8.0（utf8mb4） |
| 鉴权 | PyJWT（JWT Token）· Werkzeug（scrypt 密码哈希） |
| 数据采集 | requests（Gitee / GitHub API）· pandas（ETL 处理） |
| 前端 | 原生 HTML / CSS / JS · ECharts 5.5 |
| 部署 | Docker · Docker Compose |

## 🏗️ 系统架构

### 应用架构

```
                         ┌──────────────────────┐
                         │       前端大屏         │
                         │  HTML / JS / ECharts  │
                         └──────────┬───────────┘
                                    │ HTTP / JSON
                         ┌──────────▼───────────┐
                         │   Flask 后端（5000）   │
                         │  REST API + 页面托管   │
                         │  JWT 鉴权 · 角色权限   │
                         └──────────┬───────────┘
                                    │ PyMySQL
                         ┌──────────▼───────────┐
                         │     MySQL 8.0        │
                         │   四层数据仓库         │
                         └──────────▲───────────┘
                                    │ ETL 管道
        ┌───────────────────────────┴───────────────────────────┐
        │  Gitee API  ·  GitHub API（requests 采集）              │
        └─────────────────────────────────────────────────────────┘
```

### 数据仓库分层

| 分层 | 表 | 说明 |
|---|---|---|
| **ODS** 贴源层 | `ods_repos_raw` | 原始仓库数据（Gitee + GitHub 合并） |
| **DWD** 明细层 | `dim_project` / `dim_org` / `dim_date` / `fact_repo_stats` | 星型模型，仓库日快照事实表 |
| **DWS** 汇总层 | `dws_project_daily` / `dws_org_daily` / `dws_language_daily` / `dws_platform_daily` | 按日汇总的轻度聚合 |
| **ADS** 应用层 | `ads_overview` / `ads_project_ranking` / `ads_language_dist` / `ads_monthly_trend` / `ads_org_compare` | 直接供前端 API 查询 |

## ⚡ 核心功能

- **平台概览**：仓库总数、Star/Fork 总量、组织数、双平台占比（顶部数字卡片）
- **项目排名 TOP20**：按 Star 数 + 日增长量排序的柱状图
- **语言分布**：编程语言占比环形图
- **组织对比**：各开源组织活跃度横向对比
- **月度趋势**：新增仓库 / Star 增长趋势折线图
- **组织钻取**：点击组织下钻查看仓库明细
- **数据管理**：仓库全量明细分页查询 + CSV 导出
- **用户管理**：管理员增删改查用户、角色分配
- **操作日志**：登录 / 导出等关键操作审计

## 📁 目录结构

```
xinchuang-data-analysis/
├── backend/
│   └── app.py                # Flask 主程序（API + 前端托管）
├── frontend/                 # 前端页面（原生 HTML + ECharts）
│   ├── index.html            # 首页入口
│   ├── dashboard.html        # 大屏仪表盘
│   ├── ranking.html          # 项目排名
│   ├── language.html         # 语言分布
│   ├── org-compare.html      # 组织对比
│   ├── org-drill.html        # 组织钻取
│   ├── trend.html            # 月度趋势
│   ├── data.html             # 数据管理
│   ├── users.html            # 用户管理
│   ├── log.html              # 操作日志
│   ├── login.html / profile.html
│   └── js/auth.js            # 登录态管理
├── db/                       # 建表 SQL + 数据转储
│   ├── 01_create_ods.sql
│   ├── 02_create_dwd.sql
│   ├── xinchuang_dw.sql      # 完整数据转储（Docker 自动导入）
├── sql/04_create_ads.sql     # ADS 建表脚本
├── scripts/                  # 数据采集 + ETL 管道
│   ├── collector.py          # 采集（Gitee/GitHub API → JSON）
│   ├── cleaner.py            # 清洗
│   ├── ods_loader.py         # 加载 ODS
│   ├── etl_ods_to_dwd.py     # ODS → DWD
│   ├── etl_dwd_to_dws.py     # DWD → DWS
│   ├── etl_dws_to_ads.py     # DWS → ADS
│   ├── fill_dim_date.py      # 日期维度填充
│   ├── etl_ads_monthly_trend.py
│   └── init_admin.py         # 初始化管理员
├── docs/                     # 开题报告 / 设计文档 / 测试报告
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── project_config.py         # 全局配置（读 .env）
└── test_db.py                # 数据库连接测试
```

## 🚀 快速开始

### 方式一：Docker 一键部署（推荐）

```bash
# 1. 克隆项目
git clone https://github.com/tuocong/xinchuang-data-analysis.git
cd xinchuang-data-analysis

# 2.（可选）复制环境变量模板，按需修改数据库密码
cp .env.example .env

# 3. 一键启动（首次启动会自动导入表结构 + 演示数据，约 30~60 秒）
docker compose up -d

# 4. 浏览器访问
# http://localhost:5000
```

> 首次启动 MySQL 会执行 `db/xinchuang_dw.sql` 自动建库建表并导入演示数据。
> 查看状态：`docker compose ps` · 查看日志：`docker compose logs -f web`
> 重置数据（清空卷）：`docker compose down -v && docker compose up -d`

### 方式二：本地运行

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量
cp .env.example .env   # 填入 DB_PASSWORD、GITEE_TOKEN 等

# 3. 初始化数据库（二选一）
#    A. 直接导入完整转储（含演示数据）
mysql -u root -p < db/xinchuang_dw.sql
#    B. 或按顺序建表 + 跑 ETL（见下方"数据采集与 ETL"）

# 4. 启动服务
python backend/app.py

# 5. 访问 http://localhost:5000
```

## 🔄 数据采集与 ETL 流程

```bash
cd scripts

python collector.py            # 1. 采集：Gitee/GitHub API → data/raw/*.json
python cleaner.py              # 2. 清洗 → data/cleaned/repos_cleaned.json
python ods_loader.py           # 3. 加载到 ODS 层
python etl_ods_to_dwd.py       # 4. ODS → DWD（星型模型）
python etl_dwd_to_dws.py       # 5. DWD → DWS（日汇总）
python etl_dws_to_ads.py       # 6. DWS → ADS（应用层，供 API 查询）
python fill_dim_date.py        # 7. 日期维度预填充（首次）
python etl_ads_monthly_trend.py# 8. 月度趋势汇总
```

采集目标（`project_config.py` 中可配置）覆盖 openEuler、龙蜥 Anolis、OpenHarmony、昇思 MindSpore、openGauss、openKylin、openEuler-riscv、鲲鹏 Kunpeng 等信创组织。

## 🔌 API 接口

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/api/overview` | 平台概览（顶部卡片） | 公开 |
| GET | `/api/ranking` | 项目排名 TOP20 | 公开 |
| GET | `/api/language` | 语言分布 | 公开 |
| GET | `/api/trend` | 月度趋势 | 公开 |
| GET | `/api/org-compare` | 组织对比 | 公开 |
| GET | `/api/org-repos?org=` | 组织仓库明细 | 公开 |
| GET | `/api/repos` | 仓库全量明细 | 公开 |
| GET | `/api/health` | 健康检查 | 公开 |
| POST | `/api/login` | 登录获取 Token | 公开 |
| GET | `/api/me` | 当前用户信息 | 登录 |
| GET/POST/PUT/DELETE | `/api/users` | 用户管理 | 管理员 |
| GET | `/api/logs` | 操作日志 | 管理员 |
| POST | `/api/change-password` | 修改密码 | 登录 |
| GET | `/api/my-stats` | 个人统计 | 登录 |
| GET | `/api/export` | 导出 CSV | 登录 |

## 👤 账号说明

| 账号 | 密码 | 角色 |
|---|---|---|
| admin | 123456（默认，可在页面修改） | 管理员 |
| student1 | （见数据转储） | 普通用户 |

## 🧪 测试

```bash
python test_db.py            # 数据库连接测试（应输出 (1,)）
pytest                       # 单元测试（如已配置）
```

## 📄 许可

MIT License
