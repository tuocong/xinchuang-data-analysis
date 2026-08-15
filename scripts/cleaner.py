"""
数据清洗器（Pandas版本 · 双平台支持）
输入：data/raw/gitee_repos_*.json + data/raw/github_repos_*.json
输出：data/cleaned/repos_cleaned.json（双平台合并清洗后的干净数据）

清洗规则：
  1. 按 repo_id 去重（同一平台内）
  2. description 空值填充
  3. Gitee：删除 description 含"迁移/migrated"的已废弃仓库
     GitHub：删除 archived=True 的已归档仓库
  4. language 为空 → 标记为"未标注"
  5. 补充缺失字段（GitHub 特有字段在 Gitee 数据上填默认值）

知识点：drop_duplicates() / isna() / str.contains() / pd.cut() / groupby() / pd.concat()
"""
import json
import os
import sys
from pathlib import Path

# ---- 项目根目录 ----
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd


# ==========================================
# 数据加载
# ==========================================
def load_all_raw_files(raw_dir: str) -> pd.DataFrame:
    """加载 raw/ 下所有 JSON 文件，合并为一个 DataFrame"""
    all_files = sorted([
        f for f in os.listdir(raw_dir)
        if f.endswith('.json') and ('gitee' in f or 'github' in f)
    ])

    if not all_files:
        print("[ERROR] 没找到原始数据文件！请先运行 collector.py")
        return pd.DataFrame()

    print(f"发现 {len(all_files)} 个原始数据文件：")
    frames = []
    for f in all_files:
        filepath = os.path.join(raw_dir, f)
        # 跳过空文件（API 请求失败时可能残留空数组 []）
        if os.path.getsize(filepath) < 10:
            print(f"  [跳过] {f}: 文件为空（<10 bytes），可能 API 请求失败")
            continue
        with open(filepath, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
        # 跳过非列表数据（如 checkpoint、空对象等）
        if not isinstance(data, list):
            print(f"  [跳过] {f}: 非仓库列表数据（类型={type(data).__name__}）")
            continue
        if len(data) == 0:
            print(f"  [跳过] {f}: 空数组，无数据")
            continue
        df = pd.DataFrame(data)
        print(f"  {f}: {len(df)} 条")
        frames.append(df)

    merged = pd.concat(frames, ignore_index=True)
    print(f"\n合并后总计：{len(merged)} 条")
    return merged


# ==========================================
# 清洗逻辑
# ==========================================
def clean_data(df: pd.DataFrame) -> pd.DataFrame:
    """核心清洗逻辑"""
    original_count = len(df)
    print(f"\n{'='*60}")
    print("开始数据清洗...")
    print(f"{'='*60}")

    # --- 第1步：统一字段 ---
    # GitHub 数据有 topics/license/homepage/archived 字段，Gitee 没有
    # 补全缺失列，避免后续报 KeyError
    for col, default in [
        ("topics", ""),
        ("license", ""),
        ("homepage", ""),
        ("archived", False),
        ("source_platform", "unknown"),
    ]:
        if col not in df.columns:
            df[col] = default

    # --- 第2步：按 repo_id 去重（同平台内的重复） ---
    # 不同平台的 repo_id 可能冲突，用 (repo_id, source_platform) 组合去重
    df = df.drop_duplicates(subset=["repo_id", "source_platform"], keep="first")
    after_dup = len(df)
    print(f"去重后：{after_dup} 条（删除 {original_count - after_dup} 条重复）")

    # --- 第3步：description 空值填充 ---
    empty_desc = (df["description"].isna() | (df["description"] == "")).sum()
    df.loc[df["description"].isna() | (df["description"] == ""), "description"] = "无"
    print(f"补充空描述：{empty_desc} 条")

    # --- 第4步：过滤无效仓库 ---
    # Gitee：删除已迁移到 AtomGit 的空壳仓库
    # GitHub：删除已归档仓库
    # 兼容处理：source_platform 可能是 "gitee"/"github"/"unknown"(旧数据)/缺失

    is_gitee = df.get("source_platform", pd.Series(["unknown"] * len(df)))  # noqa
    if isinstance(is_gitee, pd.Series):
        is_gitee = is_gitee.isin(["gitee", "unknown"])  # unknown 默认按 gitee 规则处理
    else:
        is_gitee = pd.Series(["unknown"] * len(df)).isin(["gitee", "unknown"])

    is_migrated = (
        is_gitee
        & df["description"].str.contains("迁移|migrated", na=False, case=False)
    )

    # GitHub：删除已归档（archived）的仓库
    is_github = df["source_platform"] == "github"
    is_archived = is_github & (df.get("archived", pd.Series([False] * len(df))) == True)

    # 汇总
    if is_migrated.sum() > 0:
        print(f"\n  Gitee 已迁移空壳：{is_migrated.sum()} 条 → 删除")
    if is_archived.sum() > 0:
        print(f"  GitHub 已归档仓库：{is_archived.sum()} 条 → 删除")

    invalid = is_migrated | is_archived
    df = df[~invalid]
    print(f"  共删除 {invalid.sum()} 条无效仓库，当前 {len(df)} 条")

    # --- 第4.5步：过滤超长描述（政治垃圾/spam 仓库） + 截断 ---
    DESC_MAX = 15000  # 远低于 TEXT 65535字节限制，留足够余量
    is_spam = df["description"].str.len() > DESC_MAX
    if is_spam.sum() > 0:
        spam_names = df.loc[is_spam, "full_name"].tolist()
        print(f"\n  [SPAM] 超长描述垃圾仓库：{is_spam.sum()} 条 → 删除")
        for n in spam_names[:5]:
            print(f"     - {n}")
    df = df[~is_spam]
    # 兜底截断：剩余的 description 统一截断到 DESC_MAX
    too_long = df["description"].str.len() > DESC_MAX
    df.loc[too_long, "description"] = df.loc[too_long, "description"].str.slice(0, DESC_MAX)
    # full_name 和 html_url 也截断（VARCHAR 255）
    df["full_name"] = df["full_name"].str.slice(0, 250)
    df["html_url"] = df["html_url"].str.slice(0, 250)

    # --- 第5步：language 为空统一标记 ---
    lang_empty = df["language"].isna() | (df["language"] == "")
    df.loc[lang_empty, "language"] = "未标注"

    gitee_no_lang = (lang_empty & (df["source_platform"].isin(["gitee", "unknown"]))).sum()
    github_no_lang = (lang_empty & (df["source_platform"] == "github")).sum()
    print(f"  language 标记为'未标注'：Gitee {gitee_no_lang} 条，GitHub {github_no_lang} 条")

    # --- 第6步：topics 列表 → 逗号分隔字符串（方便存数据库） ---
    df["topics"] = df["topics"].apply(
        lambda x: ", ".join(x) if isinstance(x, list) and len(x) > 0 else ""
    )

    print(f"\n清洗完成！最终保留 {len(df)} 条")
    return df


# ==========================================
# 统计报告
# ==========================================
def print_statistics(df: pd.DataFrame):
    """多维度统计报告（含平台对比）"""
    sep = "=" * 60

    # ---- 总览 ----
    print(f"\n{sep}")
    print("===== 数据概览 =====")
    print(f"  总仓库数：{len(df)}")
    print(f"  总 Star 数：{df['stars_count'].sum():,}")
    print(f"  总 Fork 数：{df['forks_count'].sum():,}")
    print(f"  平均 Star：{df['stars_count'].mean():.1f}")
    print(f"  Star 中位数：{df['stars_count'].median():.0f}")

    # ---- 按平台对比 ----
    print(f"\n===== 按平台对比 =====")
    if "source_platform" in df.columns:
        platform_stats = df.groupby("source_platform").agg(
            仓库数=("repo_id", "count"),
            总Star=("stars_count", "sum"),
            平均Star=("stars_count", "mean"),
            有语言标签=("language", lambda x: (x != "未标注").sum()),
        )
        for plat, row in platform_stats.iterrows():
            lang_rate = row["有语言标签"] / row["仓库数"] * 100 if row["仓库数"] > 0 else 0
            print(f"  [{plat}] {int(row['仓库数'])}个仓库 | "
                  f"总Star={int(row['总Star']):,} | "
                  f"平均Star={row['平均Star']:.1f} | "
                  f"语言覆盖率={lang_rate:.1f}%")

    # ---- 按组织分布 ----
    print(f"\n===== 按组织分布 =====")
    org_stats = df.groupby(["org", "source_platform"]).agg(
        仓库数=("repo_id", "count"),
        总Star=("stars_count", "sum"),
    ).sort_values("总Star", ascending=False)

    for (org, plat), row in org_stats.iterrows():
        print(f"  [{plat}] {org}: {int(row['仓库数'])}个仓库, 总Star={int(row['总Star']):,}")

    # ---- Star 分布 ----
    print(f"\n===== Star 数分布区间 =====")
    bins = [0, 1, 10, 50, 100, 500, 1000, float("inf")]
    labels = ["0", "1-9", "10-49", "50-99", "100-499", "500-999", "1000+"]
    star_range = pd.cut(df["stars_count"], bins=bins, labels=labels, right=False)
    star_dist = star_range.value_counts().sort_index()
    for rng, cnt in star_dist.items():
        pct = cnt / len(df) * 100
        bar = "█" * int(pct / 2)
        print(f"  Star {rng:>8}: {cnt:>6} 个 ({pct:5.1f}%) {bar}")

    # ---- TOP15 ----
    print(f"\n===== TOP15 高 Star 仓库 =====")
    top15_cols = ["full_name", "stars_count", "forks_count", "language", "source_platform"]
    top15_cols = [c for c in top15_cols if c in df.columns]
    top15 = df.nlargest(15, "stars_count")[top15_cols]
    for _, row in top15.iterrows():
        plat = row.get("source_platform", "?")
        print(f"  [{plat}] {row['full_name']:<45} ⭐{int(row['stars_count']):>7}  "
              f"🍴{int(row['forks_count']):>5}  [{row['language']}]")

    # ---- 语言分布 ----
    print(f"\n===== 按语言分布 TOP10 =====")
    lang_counts = df["language"].value_counts().head(10)
    for lang, cnt in lang_counts.items():
        pct = cnt / len(df) * 100
        print(f"  {lang}: {cnt} 个 ({pct:.1f}%)")

    # ---- 时间趋势 ----
    print(f"\n===== 按创建年份分布 =====")
    year_series = pd.to_datetime(df["created_at"], errors="coerce", utc=True).dt.year
    year_counts = year_series.value_counts().sort_index()
    for year, cnt in year_counts.items():
        print(f"  {int(year)}年: {cnt} 个仓库")

    # ---- 许可证分布（仅 GitHub） ----
    if "license_type" in df.columns or "license" in df.columns:
        lic_col = "license_type" if "license_type" in df.columns else "license"
        licenses = df[df[lic_col] != ""][lic_col]
        if len(licenses) > 0:
            print(f"\n===== 开源许可证分布 =====")
            for lic, cnt in licenses.value_counts().head(10).items():
                print(f"  {lic}: {cnt} 个")


# ==========================================
# 保存
# ==========================================
def save_clean_data(df: pd.DataFrame, filepath: str):
    """保存清洗结果"""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    # 删除分析用的辅助列再保存
    save_df = df.drop(columns=[c for c in ["star_range", "created_year"] if c in df.columns], errors="ignore")
    data_list = save_df.to_dict("records")
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data_list, f, ensure_ascii=False, indent=2)
    print(f"\n[OK] 清洗后数据已保存至 {filepath}，共 {len(df)} 条")


# ==========================================
# 主入口
# ==========================================
if __name__ == '__main__':
    raw_dir = PROJECT_ROOT / "data" / "raw"
    out_path = PROJECT_ROOT / "data" / "cleaned" / "repos_cleaned.json"

    df_raw = load_all_raw_files(str(raw_dir))
    if df_raw.empty:
        exit(1)

    df_clean = clean_data(df_raw)
    print_statistics(df_clean)
    save_clean_data(df_clean, str(out_path))
