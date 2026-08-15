# ETL 故障排查日志

> 记录数仓四层链路（ODS → DWD → DWS → ADS）开发过程中遇到的问题、根因和解决方法。
> 时间：2026年8月9日，Day 9-10（DWS + ADS ETL 开发验证）

---

## 问题1：DWS 增量字段始终为 0（curr_day_new_stars / forks / issues）

### 现象
`dws_project_daily` 表的 `curr_day_new_stars`、`curr_day_new_forks`、`curr_day_new_issues` 全部为 0，即使同一项目在 `fact_repo_stats` 中有两天的数据。

### 根因（两个层面）

**层面A：代码逻辑缺陷**
原脚本在 INSERT 的子查询里用 LAG() 窗口函数计算增量：

```python
# 错误写法：LAG() 在 INSERT 子查询内
INSERT INTO dws_project_daily (...)
SELECT stars - LAG(stars, 1, stars) OVER (PARTITION BY project_id ORDER BY date) ...
FROM (
    SELECT ... FROM fact_repo_stats GROUP BY project_id, date
) t
```

子查询只包含当天从 `fact_repo_stats` 聚合出的行，看不到 DWS 表里已存在的历史行。当源表只有一天数据时，LAG() 永远命中默认值，增量恒为 0。

**层面B：数据本身没变**
验证后发现 `fact_repo_stats` 中 121,750 条 `(project_id, snapshot_date)` 记录中，8/7 到 8/8 之间没有任何一个项目的 Star 或 Fork 发生变化。两次采集间隔仅 1 天，Gitee/GitHub 仓库的 Star 数据确实没有增长。

### 解决方法

改为**两步法**：INSERT 只写入累计值，UPDATE 通过 LEFT JOIN DWS 自身昨日行计算增量。

```python
# 第1步：INSERT 累计值（不计算增量）
INSERT INTO dws_project_daily (project_id, snapshot_date, total_cum_stars, total_cum_forks)
SELECT project_id, snapshot_date, MAX(stars_count), MAX(forks_count)
FROM fact_repo_stats GROUP BY project_id, snapshot_date
ON DUPLICATE KEY UPDATE total_cum_stars = VALUES(total_cum_stars), ...;

# 第2步：UPDATE 从 DWS 历史行算增量
UPDATE dws_project_daily t
LEFT JOIN dws_project_daily y
    ON t.project_id = y.project_id
    AND y.snapshot_date = DATE_SUB(t.snapshot_date, INTERVAL 1 DAY)
SET t.curr_day_new_stars = t.total_cum_stars
    - COALESCE(y.total_cum_stars, t.total_cum_stars);
```

**关键技巧**：`COALESCE(y.total_cum_stars, t.total_cum_stars)` 让第一天（无昨日行）的增量 = 0，而不是 NULL。

### 验证方式
```sql
-- 找有 >=2 天数据的项目，手动验证增量 = 今天 - 昨天
SELECT project_id, snapshot_date, total_cum_stars, curr_day_new_stars
FROM dws_project_daily WHERE project_id = 某个ID ORDER BY snapshot_date;
```

### 教训
- LAG() 的窗口范围 = 子查询输出行，不是目标表
- 需要跨表/跨历史计算增量时，用 INSERT + UPDATE 两步法
- **增量为 0 不一定是 bug**——先查源数据是否真的变了

---

## 问题2：fact_repo_stats 大量重复行（60,975 → 24,375）

### 现象
`ads_project_ranking` 的 TOP20 中只有 4 个不同项目，每个出现 5 次。`ads_overview.total_stars` = 1995 万（实际应为 399 万）。

### 根因
`fact_repo_stats` 表缺少 UNIQUE 约束。DWD ETL 脚本 `etl_ods_to_dwd.py` 每次运行时直接 INSERT，不检查 `(project_id, snapshot_date)` 是否已存在。多次跑 ETL 后同一 `(project, date)` 累积了多个 `snapshot_id`，后续 SUM 被放大 5 倍。

```
原始: 24,375 条唯一 (project_id, snapshot_date)
实际: 85,350 条 = 24,375 × 多次重复运行
放大倍数: 3.5x → DWS/ADS 聚合时 SUM 被吹大 3.5 倍
```

### 解决方法

**第1步：清重复数据**
```sql
DELETE t1 FROM fact_repo_stats t1
INNER JOIN fact_repo_stats t2
ON t1.project_id = t2.project_id
   AND t1.snapshot_date = t2.snapshot_date
   AND t1.snapshot_id > t2.snapshot_id;
-- 删除 60,975 条，保留 24,375 条
```

**第2步：加唯一约束防止再次写入重复**
```sql
ALTER TABLE fact_repo_stats
ADD UNIQUE INDEX uq_project_date (project_id, snapshot_date);
```

**第3步：同步修改 DWD ETL 脚本**，INSERT 改为 `INSERT ... ON DUPLICATE KEY UPDATE`，避免未来重复。

### 验证方式
```sql
SELECT COUNT(*) FROM fact_repo_stats;
-- 应等于 SELECT COUNT(*) FROM (SELECT DISTINCT project_id, snapshot_date FROM fact_repo_stats) t
```

### 教训
- 事实表必须加 UNIQUE 约束，尤其是按 `(维度外键, 日期)` 组合的唯一性
- ETL 脚本必须幂等：多次跑同一个日期不应产生重复行
- **级联污染**：ODS 层一条脏数据 → DWD 重复 → DWS SUM 放大 → ADS 全错

---

## 问题3：Collation 冲突导致 JOIN 报错

### 现象
ADS-5（组织对比）执行时 MySQL 报错：
```
(1267, "Illegal mix of collations (utf8mb4_unicode_ci,IMPLICIT) and (utf8mb4_0900_ai_ci,IMPLICIT) for operation '='")
```

### 根因
不同表的 collation 不一致：

| 表 | 实际 collation | 来源 |
|----|---------------|------|
| `dim_org`, `fact_repo_stats` | `utf8mb4_0900_ai_ci` | MySQL 8.0 默认 |
| `dws_*`, `ads_*` | `utf8mb4_unicode_ci` | 手动建表 DDL 指定 |

JOIN 时两列 collation 不同，MySQL 无法完成字符串比较。

### 解决方法
统一 collation，以手动建表的 `utf8mb4_unicode_ci` 为准：

```sql
ALTER TABLE dim_org MODIFY org_name VARCHAR(100)
    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL;

ALTER TABLE fact_repo_stats MODIFY org_name VARCHAR(100)
    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 教训
- 所有 DDL 必须显式指定 `COLLATE`，不能依赖 MySQL 默认值
- 建表时统一 `ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci`
- MySQL 8.0 默认 `0900_ai_ci`，和 `unicode_ci` 是不同的排序规则

---

## 问题4：DATE_FORMAT 占位符转义错误

### 现象
`ads_monthly_trend` 的 `stat_month` 字段显示为字面量 `%Y-%m` 而非 `2026-08`。

### 根因
Python 字符串中 `%` 是 pymysql 的参数占位符前缀。SQL 里的 `%Y-%m` 被 Python 的 `%` 格式化语法干扰，需要转义为 `%%Y-%%m`。但这个 SQL 没有 pymysql 参数占位符（没有 `%s`），不需要转义。两种写法混用导致：

```python
# 错误：无 %s 参数但用了 %%Y-%%m
DATE_FORMAT(snapshot_date, '%%Y-%%m')  # → MySQL 收到的是字面量 %%Y-%%m

# 正确：无 %s 参数的 SQL 直接用 %Y-%m
DATE_FORMAT(snapshot_date, '%Y-%m')    # → MySQL 正常执行
```

### 解决方法
该 SQL 没有 `%s` 占位符，直接使用 `%Y-%m`，无需双写 `%`。

### 教训
- pymysql 中只有带 `%s` 参数的 `cursor.execute(sql, args)` 才需要 `%%` 转义
- 不带参数的 `cursor.execute(sql)` 不需要转义 `%`

---

## 问题5：ads_monthly_trend cumulative_stars 跨天跨平台重复累加

### 现象
`cumulative_stars` = 2790 万，而 `ads_overview.total_stars` = 399 万。

### 根因
原 SQL 用 `SUM(plat.total_stars) OVER (ORDER BY month)` 做跨月累加，但 `plat` 子查询的 `SUM(total_stars)` 来自 `dws_platform_daily`——这张表每天有 Gitee + GitHub 两条，且 `total_stars` 是当天的全平台汇总值。用 SUM 跨天再累加 = 把两天的全量 Star 又加起来，数值翻倍。

### 解决方法
`cumulative_stars` 只取每月最后一天的平台汇总值：
```sql
(SELECT SUM(total_stars) FROM dws_platform_daily
 WHERE snapshot_date = (
     SELECT MAX(snapshot_date) FROM dws_platform_daily
     WHERE DATE_FORMAT(snapshot_date, '%Y-%m') = m.month
 )) AS cumulative_stars
```

### 教训
- 跨月 cumulative 值应取月末快照，不是 SUM 每天的值
- 平台汇总表每天的总 Star 是全量值（不是增量），跨天 SUM 会产生逻辑错误

---

## 问题6：ETL 脚本在 Windows 终端报 UnicodeEncodeError

### 现象
```python
print(f"  ✅ dws_project_daily...")
UnicodeEncodeError: 'gbk' codec can't encode character '✅'
```

### 根因
Windows 终端默认使用 GBK 编码，emoji 字符无法被编码。

### 解决方法
```bash
PYTHONIOENCODING=utf-8 python scripts/etl_dwd_to_dws.py
```
或者在代码中避免使用 emoji，用纯文本替代。

---

## 排查验证的标准动作

每次 ETL 完成后必须执行的一致性检查：

```sql
-- 1. 各层 Star 总数必须一致
SELECT SUM(total_cum_stars) FROM dws_project_daily WHERE snapshot_date = '最新日期';
SELECT SUM(total_stars) FROM dws_platform_daily WHERE snapshot_date = '最新日期';
SELECT total_stars FROM ads_overview WHERE stat_date = '最新日期';
SELECT cumulative_stars FROM ads_monthly_trend WHERE stat_month = '最新月份';

-- 2. 事实表不能有重复
SELECT project_id, snapshot_date, COUNT(*)
FROM fact_repo_stats
GROUP BY project_id, snapshot_date HAVING COUNT(*) > 1;
-- 必须返回 0 行

-- 3. 增量字段应有非零值（长间隔运行后）
SELECT COUNT(*) FROM dws_project_daily WHERE curr_day_new_stars != 0;
-- 短间隔全为 0 是正常的
```

---

## 全链路最终状态（2026-08-09）

| 层级 | 表 | 行数 | 备注 |
|------|-----|------|------|
| ODS | `ods_repos_raw` | 36,550 | 8/4 ~ 8/8 三次采集 |
| DWD | `dim_project` | 12,200 | 唯一项目 |
| DWD | `dim_org` | 2,060 | 组织维度 |
| DWD | `dim_date` | 7,670 | 预填充日期 |
| DWD | `fact_repo_stats` | 24,375 | 已去重+UNIQUE约束 |
| DWS | `dws_project_daily` | 24,375 | 增量两步法 |
| DWS | `dws_language_daily` | 210 | |
| DWS | `dws_org_daily` | 4,095 | |
| DWS | `dws_platform_daily` | 4 | Gitee+GitHub×2天 |
| ADS | `ads_overview` | 1 | 总Star=3,990,469 |
| ADS | `ads_project_ranking` | 20 | 不重复 |
| ADS | `ads_language_dist` | 105 | |
| ADS | `ads_monthly_trend` | 1 | 2026-08 |
| ADS | `ads_org_compare` | 2,063 | |

**四层 Star 数一致：3,990,469 ✅**
