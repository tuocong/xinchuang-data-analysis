# 信创运维监控系统

> 基于 Docker Compose 的轻量级运维监控方案：Prometheus 采集指标 → Grafana 可视化 → Alertmanager 告警通知

---

## 架构总览

```
                        ┌──────────────────────┐
                        │      用户浏览器        │
                        └──────────┬───────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    │          Nginx :80          │
                    │       （反向代理 + 静态资源）  │
                    └──────────────┬──────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                    │
              ▼                    ▼                    ▼
    ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
    │  Flask App      │  │   Prometheus    │  │    Grafana      │
    │  :5000          │  │   :9090         │  │    :3000         │
    │ （后端API+巡检）  │  │ （指标采集+存储） │  │ （仪表盘可视化）   │
    └─────────────────┘  └────────┬────────┘  └─────────────────┘
                                  │
                    ┌─────────────┴─────────────┐
                    │     Node Exporter :9100   │
                    │  （宿主机CPU/内存/磁盘/网络） │
                    └───────────────────────────┘
```

---

## 技术栈

| 组件 | 版本 | 用途 |
|------|------|------|
| Flask | Python 3.x | 后端 API + 系统巡检脚本 |
| Nginx | latest | 反向代理，80 端口统一入口 |
| Prometheus | latest | 时序指标采集与存储（pull 模式，每15s抓取） |
| Node Exporter | latest | 暴露宿主机 CPU/内存/磁盘/网络/运行时长指标 |
| Grafana | latest (OSS) | 仪表盘可视化，数据源对接 Prometheus |
| Docker Compose | v3 | 一键部署，5 个服务容器编排 |

---

## 快速部署

### 前置条件

- Docker Engine ≥ 20.10
- Docker Compose ≥ v2
- 内核 ≥ 4.x（openEuler 24.03 验证通过）

### 部署步骤

```bash
# 1. 克隆项目
cd /path/to/project

# 2. 设置 Grafana 管理员密码（已在 docker-compose.yml 中配置）
#    默认: admin / Tuocong666

# 3. 一键启动
docker compose up -d

# 4. 验证所有服务
docker compose ps
# 预期：5个服务均为 Up 状态

# 5. 访问各组件
#    Grafana:     http://服务器IP:3000
#    Prometheus:  http://服务器IP:9090
#    Flask API:   http://服务器IP/api/
```

---

## 端口说明

| 端口 | 服务 | 说明 |
|------|------|------|
| 80 | Nginx | 对外的统一入口 |
| 3000 | Grafana | 仪表盘（管理员密码: Tuocong666） |
| 9090 | Prometheus | 指标查询 + 告警规则 |
| 9100 | Node Exporter | 宿主机指标暴露（仅内网访问） |
| 5000 | Flask App | 后端 API（仅内网，不对外暴露） |

---

## 监控指标一览

| 面板 | 数据来源 | 说明 |
|------|---------|------|
| CPU 使用率 | `node_cpu_seconds_total` | 用户态/系统态/iowait/空闲占比 |
| 内存使用 | `node_memory_MemAvailable_bytes` | 可用内存 / 总量 |
| 磁盘使用 | `node_filesystem_avail_bytes` | 各挂载点使用率 |
| 网络流量 | `node_network_receive_bytes_total` | 入站/出站流量速率 |
| 运行时长 | `node_boot_time_seconds` | 系统启动后运行时间 |

---

## 遇到的坑（面试重点）

| 故障 | 根因 | 解决 | 详细记录 |
|------|------|------|---------|
| Grafana 报 `no such host: prometheus` | Grafana 声明了 `monitor-net` 网络，Prometheus 在默认网络，DNS 不互通 | 统一所有监控组件到 `monitor-net` | [docs/故障排查日志.md](docs/故障排查日志.md) |
| Pressure 面板 No data | openEuler 24.03 内核未开启 `CONFIG_PSI`，`/proc/pressure/` 不存在 | 删除该面板（不可修复） | [docs/故障排查日志.md](docs/故障排查日志.md) |

---

## PromQL 常用查询

```promql
# 所有抓取目标状态（1=UP, 0=DOWN）
up

# CPU 使用率（5分钟平均）
100 - (avg by(instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)

# 内存可用百分比
node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes * 100

# 磁盘使用率
(node_filesystem_size_bytes - node_filesystem_avail_bytes) / node_filesystem_size_bytes * 100

# 网络入站速率
rate(node_network_receive_bytes_total[5m])
```

---

## 截图

> 以下截图放置于 `docs/screenshots/` 目录：

| 截图内容 | 文件名 |
|---------|--------|
| Grafana 仪表盘总览 | `grafana-dashboard.png` |
| Prometheus Targets 页面 | `prometheus-targets.png` |
| CPU 面板 | `panel-cpu.png` |
| 内存面板 | `panel-memory.png` |
| 磁盘面板 | `panel-disk.png` |
| docker compose ps 输出 | `docker-ps.png` |

---

## 项目结构

```
project/
├── docker-compose.yml          # 5服务编排
├── Dockerfile                  # Flask App 镜像构建
├── app.py                      # Flask 主应用
├── scripts/                    # 系统巡检脚本
├── nginx/
│   └── nginx.conf              # Nginx 反向代理配置
├── prometheus/
│   └── prometheus.yml          # Prometheus 抓取规则 + 告警规则
├── grafana-data/               # Grafana 持久化数据（仪表盘 + 配置）
├── docs/
│   ├── 故障排查日志.md          # ⭐ 面试素材
│   └── screenshots/            # 截图
└── README.md
```
