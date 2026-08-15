"""
仓库数据采集器【双平台支持：Gitee + GitHub】
运行方式：
    python scripts/collector.py              # 同时采集Gitee + GitHub + 关键词搜索
    python scripts/collector.py gitee        # 仅采集Gitee平台
    python scripts/collector.py github       # 仅采集GitHub平台
    python scripts/collector.py --no-search  # 跳过关键词搜索（仅按组织采集）
    python scripts/collector.py --resume     # 断点续传（从上次中断处继续）

输出文件：
    data/raw/gitee_repos_YYYYMMDD.json
    data/raw/github_repos_YYYYMMDD.json
"""
import requests
import os
import json
import time
import sys
import logging
from datetime import datetime
from pathlib import Path

# ---- 项目根目录 & 配置 ----
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from project_config import (
    GITEE_TOKEN, GITEE_API_BASE, GITEE_ORGS,
    GITHUB_TOKEN, GITHUB_API_BASE, GITHUB_ORGS,
    PER_PAGE, REQUEST_INTERVAL,
    SEARCH_KEYWORDS, SEARCH_MAX_PAGES,
)

# ---- 日志 ----
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


class BaseRepoCollector:
    """采集器父类：请求重试、限流等待、分页、持久化、断点续传"""

    def __init__(self, api_base: str, platform: str, token: str = ""):
        self.api_base = api_base.rstrip("/")
        self.platform = platform
        self.token = token
        self.session = requests.Session()

        headers = {"User-Agent": "XinchuangDataAnalysis/1.0"}
        if platform == "github":
            headers["Accept"] = "application/vnd.github+json"
            headers["X-GitHub-Api-Version"] = "2022-11-28"
            if token:
                headers["Authorization"] = f"Bearer {token}"
        else:  # gitee: token 通过 URL 参数传递，不用 header
            headers["Accept"] = "application/json"

        self.session.headers.update(headers)

        # 断点续传相关
        self.checkpoint_dir = PROJECT_ROOT / "data" / "raw"
        self.checkpoint_file = self.checkpoint_dir / f".{platform}_checkpoint.json"
        self.completed_orgs: set = set()
        self.collected_repos: list = []

    # ────────────────────── 请求层 ──────────────────────
    def _request(self, url: str, params: dict = None):
        """GET 请求：自动重试 + 限流等待 + 指数退避"""
        if params is None:
            params = {}
        # Gitee API v5 认证方式：URL 参数 ?access_token=xxx
        if self.platform == "gitee" and self.token:
            params["access_token"] = self.token

        max_retry = 5
        for attempt in range(1, max_retry + 1):
            try:
                resp = self.session.get(url, params=params, timeout=30)
            except requests.exceptions.RequestException as e:
                logger.warning(f"网络错误（第{attempt}/{max_retry}次）: {e}")
                if attempt < max_retry:
                    time.sleep(2 ** attempt)
                else:
                    logger.error(f"多次重试失败，放弃：{url}")
                    return []
                continue

            # 限流 → 等待后重试
            if resp.status_code in (401, 403) and "rate limit" in resp.text.lower():
                reset_time = resp.headers.get("X-RateLimit-Reset")
                if reset_time:
                    wait = max(int(reset_time) - time.time() + 2, 10)
                else:
                    wait = 60 * attempt  # 退避：60s → 120s → 180s ...
                logger.warning(
                    f"[WAIT] 被限流！等待 {wait:.0f} 秒后重试... "
                    f"(第{attempt}/{max_retry}次)"
                )
                time.sleep(wait)
                continue

            # 401 → 私有组织或 token 无效，跳过
            if resp.status_code == 401:
                logger.warning(f"401 Unauthorized，跳过：{url}")
                return []

            # 404 → 组织不存在或接口路径不对
            if resp.status_code == 404:
                logger.warning(f"接口返回 404，跳过：{url}")
                return []

            resp.raise_for_status()
            return resp.json()

        logger.error(f"达到最大重试次数，放弃：{url}")
        return []

    # ────────────────────── 数据标准化 ──────────────────────
    def _normalize(self, raw_data: dict, org_name: str):
        """子类必须实现"""
        raise NotImplementedError

    # ────────────────────── 关键词搜索 ──────────────────────
    def fetch_by_search(self, keyword: str, max_pages: int = SEARCH_MAX_PAGES):
        """按关键词搜索仓库，自动分页"""
        all_repos = []
        url = f"{self.api_base}/search/repositories"
        logger.info(f"[{self.platform}] [SEARCH] 搜索关键词：'{keyword}'，上限 {max_pages} 页")

        for page in range(1, max_pages + 1):
            params = {
                "q": keyword, "page": page, "per_page": PER_PAGE,
                "sort": "stars", "order": "desc",
            }
            resp_data = self._request(url, params)
            if not resp_data:
                break

            items = resp_data.get("items", resp_data) if isinstance(resp_data, dict) else []
            for repo_raw in items:
                if self.platform == "github":
                    org_name = (repo_raw.get("owner") or {}).get("login", "")
                else:
                    org_name = (repo_raw.get("namespace") or {}).get("path", "")
                all_repos.append(self._normalize(repo_raw, org_name))

            logger.info(
                f"[{self.platform}] 搜索'{keyword}' 第{page}页 "
                f"| 本页{len(items)}条 | 累计{len(all_repos)}条"
            )
            time.sleep(REQUEST_INTERVAL)

        logger.info(f"[{self.platform}] 搜索'{keyword}' 完成，共 {len(all_repos)} 条")
        return all_repos

    # ────────────────────── 组织采集 ──────────────────────
    def fetch_org_repos(self, org: str):
        """采集单个组织全部公开仓库，自动分页"""
        all_repos = []
        page = 1
        url = f"{self.api_base}/orgs/{org}/repos"
        logger.info(f"[{self.platform}] 开始采集组织：{org}")

        while True:
            params = {"type": "public", "page": page, "per_page": PER_PAGE}
            resp_data = self._request(url, params)
            if not resp_data:
                break

            for repo_raw in resp_data:
                all_repos.append(self._normalize(repo_raw, org))

            logger.info(
                f"[{self.platform}][{org}] 第{page}页 "
                f"| 本页{len(resp_data)}条 | 累计{len(all_repos)}条"
            )
            page += 1
            time.sleep(REQUEST_INTERVAL)

        logger.info(f"[{self.platform}][{org}] 采集完成，仓库总数：{len(all_repos)}")
        return all_repos

    # ────────────────────── 断点续传 ──────────────────────
    def _load_checkpoint(self):
        """加载上次中断时的进度"""
        if self.checkpoint_file.exists():
            try:
                with open(self.checkpoint_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.completed_orgs = set(data.get("completed_orgs", []))
                self.collected_repos = data.get("collected_repos", [])
                logger.info(
                    f"[CHECKPOINT] 发现断点：已完成 {len(self.completed_orgs)} 个组织，"
                    f"已采集 {len(self.collected_repos)} 个仓库"
                )
            except (json.JSONDecodeError, KeyError):
                logger.warning("断点文件损坏，从头开始")
                self.completed_orgs = set()
                self.collected_repos = []

    def _save_checkpoint(self, org_name: str = ""):
        """保存当前进度到磁盘"""
        if org_name:
            self.completed_orgs.add(org_name)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        with open(self.checkpoint_file, "w", encoding="utf-8") as f:
            json.dump({
                "completed_orgs": sorted(self.completed_orgs),
                "collected_repos": self.collected_repos,
                "last_updated": datetime.now().isoformat(),
            }, f, ensure_ascii=False, indent=2)

    def _clear_checkpoint(self):
        """采集全部完成后清理断点文件"""
        if self.checkpoint_file.exists():
            self.checkpoint_file.unlink()
            logger.info("[CLEANUP] 断点文件已清理")

    # ────────────────────── 持久化 ──────────────────────
    def save_json(self, data: list, filepath: Path):
        """持久化 JSON 文件"""
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"[{self.platform}] 数据已写入：{filepath}")

    # ────────────────────── 主入口 ──────────────────────
    def run(self, target_orgs: list, do_search: bool = True, resume: bool = False):
        """批量采集组织 + 关键词搜索 → 去重 → 保存"""
        start_time = time.time()
        seen = set()

        # 断点续传
        if resume:
            self._load_checkpoint()
            seen.update(
                (r["repo_id"], r["source_platform"])
                for r in self.collected_repos
            )
        else:
            self.collected_repos = []
            self.completed_orgs = set()
            if self.checkpoint_file.exists():
                self.checkpoint_file.unlink()

        # 过滤已完成的组织
        pending_orgs = [o for o in target_orgs if o not in self.completed_orgs]
        skipped = len(target_orgs) - len(pending_orgs)

        logger.info(
            f"\n{'='*60}\n"
            f"【{self.platform.upper()} 采集任务启动】\n"
            f"  总组织数：{len(target_orgs)} | 已完成：{skipped} | 待采集：{len(pending_orgs)}\n"
            f"{'='*60}"
        )

        # Phase 1: 按组织采集（逐组织保存断点）
        for org_name in pending_orgs:
            org_repos = self.fetch_org_repos(org_name)
            for r in org_repos:
                key = (r["repo_id"], r["source_platform"])
                if key not in seen:
                    seen.add(key)
                    self.collected_repos.append(r)
            # 每采完一个组织立刻保存断点
            self._save_checkpoint(org_name)

        # Phase 2: 按关键词搜索
        if do_search:
            logger.info(f"\n--- 开始关键词搜索（共 {len(SEARCH_KEYWORDS)} 个关键词）---")
            for kw in SEARCH_KEYWORDS:
                search_repos = self.fetch_by_search(kw)
                for r in search_repos:
                    key = (r["repo_id"], r["source_platform"])
                    if key not in seen:
                        seen.add(key)
                        self.collected_repos.append(r)
                self._save_checkpoint()  # 搜索完一个关键词也保存

        # 最终输出
        date_tag = datetime.now().strftime("%Y%m%d")
        output_path = (
            PROJECT_ROOT / "data" / "raw" / f"{self.platform}_repos_{date_tag}.json"
        )
        self.save_json(self.collected_repos, output_path)
        self._clear_checkpoint()

        cost_sec = time.time() - start_time
        logger.info(
            f"\n{'='*60}\n"
            f"【{self.platform.upper()} 采集任务结束】\n"
            f"  总仓库数：{len(self.collected_repos)}（去重后）\n"
            f"  总耗时：{cost_sec:.0f} 秒\n"
            f"{'='*60}"
        )
        return str(output_path)


# ══════════════════════════════════════════════════════════
# 平台实现
# ══════════════════════════════════════════════════════════

class GiteeCollector(BaseRepoCollector):
    """Gitee 平台采集实现"""

    def __init__(self):
        super().__init__(GITEE_API_BASE, "gitee", GITEE_TOKEN)

    def _normalize(self, raw: dict, org: str):
        return {
            "repo_id":           raw.get("id"),
            "org":               org,
            "name":              raw.get("name", ""),
            "full_name":         raw.get("full_name", ""),
            "description":       raw.get("description") or "",
            "language":          raw.get("language") or "",
            "stars_count":       raw.get("stargazers_count", 0),
            "forks_count":       raw.get("forks_count", 0),
            "watchers_count":    raw.get("watchers_count", 0),
            "open_issues_count": raw.get("open_issues_count", 0),
            "default_branch":    raw.get("default_branch", ""),
            "html_url":          raw.get("html_url", ""),
            "topics":            "",
            "license_type":      "",
            "homepage":          "",
            "archived":          False,
            "created_at":        raw.get("created_at", ""),
            "updated_at":        raw.get("updated_at", ""),
            "pushed_at":         raw.get("pushed_at", ""),
            "source_platform":   "gitee",
        }


class GitHubCollector(BaseRepoCollector):
    """GitHub 平台采集实现"""

    def __init__(self):
        super().__init__(GITHUB_API_BASE, "github", GITHUB_TOKEN)

    def _normalize(self, raw: dict, org: str):
        license_info = raw.get("license") or {}
        topic_list = raw.get("topics", [])
        return {
            "repo_id":           raw.get("id"),
            "org":               org,
            "name":              raw.get("name", ""),
            "full_name":         raw.get("full_name", ""),
            "description":       raw.get("description") or "",
            "language":          raw.get("language") or "",
            "stars_count":       raw.get("stargazers_count", 0),
            "forks_count":       raw.get("forks_count", 0),
            "watchers_count":    raw.get("watchers_count", 0),
            "open_issues_count": raw.get("open_issues_count", 0),
            "default_branch":    raw.get("default_branch", ""),
            "html_url":          raw.get("html_url", ""),
            "topics":            ", ".join(topic_list) if topic_list else "",
            "license_type":      license_info.get("spdx_id", ""),
            "homepage":          raw.get("homepage", ""),
            "archived":          raw.get("archived", False),
            "created_at":        raw.get("created_at", ""),
            "updated_at":        raw.get("updated_at", ""),
            "pushed_at":         raw.get("pushed_at", ""),
            "source_platform":   "github",
        }


# ══════════════════════════════════════════════════════════
# CLI 入口
# ══════════════════════════════════════════════════════════
if __name__ == "__main__":
    run_target = sys.argv[1].lower() if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else "all"
    skip_search = "--no-search" in sys.argv
    do_resume = "--resume" in sys.argv

    if run_target in ("gitee", "all"):
        if GITEE_TOKEN.strip():
            GiteeCollector().run(GITEE_ORGS, do_search=not skip_search, resume=do_resume)
        else:
            logger.warning("GITEE_TOKEN 为空，跳过 Gitee 采集（检查 .env 文件）")

    if run_target in ("github", "all"):
        if GITHUB_TOKEN.strip():
            GitHubCollector().run(GITHUB_ORGS, do_search=not skip_search, resume=do_resume)
        else:
            logger.warning("GITHUB_TOKEN 为空，跳过 GitHub 采集（检查 .env 文件）")
