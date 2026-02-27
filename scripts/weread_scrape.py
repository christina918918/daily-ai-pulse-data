#!/usr/bin/env python3
"""
weread_scrape.py — 从微信读书「我的订阅」抓取公众号文章
使用 WeRead 网页版 Cookie 鉴权，适合 GitHub Actions 定时运行。

═══════════════════════════════════════════════════════════
首次使用：只需获取 Cookie（一次性，在本地浏览器操作）
═══════════════════════════════════════════════════════════

1. Chrome 打开 https://weread.qq.com 并登录微信
2. 打开 DevTools (F12) → Network → 找任意一条 i.weread.qq.com 请求
3. 右键该请求 → Copy → Copy as cURL
4. 从 cURL 中找到 -H 'Cookie: ...' 那一行，复制完整 Cookie 字符串
5. 在 GitHub 仓库 → Settings → Secrets and variables → Actions → New secret
   Name: WEREAD_COOKIE
   Value: 粘贴第 4 步复制的完整 Cookie 字符串

【安全提示】
- Cookie 只存 GitHub Secrets，绝不放代码或日志
- Cookie 过期后（一般数月），重复上述步骤更新 WEREAD_COOKIE 即可
═══════════════════════════════════════════════════════════
"""

import os
import json
import time
import logging
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

# ═══════════════════════════════════════════════════════════
# ★ 用户配置区 ★（首次使用按说明填入）
# ═══════════════════════════════════════════════════════════

# 订阅列表 API（微信读书「我的订阅」公众号列表）
SUBS_API_URL = "https://i.weread.qq.com/mp/list"

# 某公众号文章列表 API 模板（{source_id} 会被替换为实际 mpId）
FEED_API_URL = "https://i.weread.qq.com/article/list?mpId={source_id}&count=20"

# 文章列表翻页参数名
FEED_PAGINATION_PARAM = "maxIndex"

# [按需] 订阅列表 API 额外 query 参数（留空则不加）
SUBS_EXTRA_PARAMS: dict = {}
# 例如：SUBS_EXTRA_PARAMS = {"type": "0", "count": "100"}

# [按需] 每个公众号最多抓取篇数
ARTICLES_PER_SOURCE = 20

# [按需] 只保留近 N 天的文章
RECENT_DAYS = 7

# ═══════════════════════════════════════════════════════════
# 输出路径（相对于 repo 根目录的 out/）
# ═══════════════════════════════════════════════════════════

OUT_DIR       = Path(__file__).parent.parent / "out"
SUBS_FILE     = OUT_DIR / "subscriptions.json"
ARTICLES_FILE = OUT_DIR / "articles.json"
DAILY_FILE    = OUT_DIR / "daily.md"
STATE_FILE    = OUT_DIR / "state.json"

# ═══════════════════════════════════════════════════════════
# 日志（脱敏：永不输出 cookie）
# ═══════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger(__name__)


def _safe_headers(headers: dict) -> dict:
    """返回脱敏副本用于日志，隐藏 Cookie 等敏感字段。"""
    return {
        k: ("***" if k.lower() in ("cookie", "authorization", "set-cookie") else v)
        for k, v in headers.items()
    }


# ═══════════════════════════════════════════════════════════
# HTTP 工具（带重试 + 鉴权错误检测）
# ═══════════════════════════════════════════════════════════

def build_session(cookie: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "Cookie":          cookie,
        "User-Agent":      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Referer":         "https://weread.qq.com/",
        "Accept":          "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    })
    return s


def get_json(session: requests.Session, url: str,
             params: dict | None = None,
             retries: int = 2, backoff: float = 2.0) -> dict | list:
    """
    发 GET 请求，自动重试 5xx/timeout，返回解析后的 JSON。
    401/403 立即报错（提示更新 WEREAD_COOKIE）。
    """
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            log.info("GET %s params=%s", url, params)
            resp = session.get(url, params=params, timeout=20)

            if resp.status_code in (401, 403):
                log.error(
                    "❌ HTTP %d：Cookie 可能已过期。"
                    "请重新登录 weread.qq.com，复制 Cookie，"
                    "更新 GitHub Secret WEREAD_COOKIE。",
                    resp.status_code,
                )
                raise RuntimeError(f"auth_error:{resp.status_code}")

            if resp.status_code >= 500:
                wait = backoff ** attempt
                log.warning("HTTP %d，%.0fs 后重试（%d/%d）…",
                            resp.status_code, wait, attempt + 1, retries + 1)
                time.sleep(wait)
                continue

            resp.raise_for_status()
            return resp.json()

        except RuntimeError:
            raise
        except requests.exceptions.Timeout as e:
            last_err = e
            wait = backoff ** attempt
            log.warning("Timeout，%.0fs 后重试（%d/%d）…", wait, attempt + 1, retries + 1)
            time.sleep(wait)
        except Exception as e:
            last_err = e
            if attempt < retries:
                wait = backoff ** attempt
                log.warning("错误：%s，%.0fs 后重试…", e, wait)
                time.sleep(wait)

    raise RuntimeError(f"请求失败（已重试 {retries + 1} 次）：{last_err}")


# ═══════════════════════════════════════════════════════════
# A. 抓取订阅列表
# ═══════════════════════════════════════════════════════════

def fetch_subscriptions(session: requests.Session) -> list[dict]:
    """调用 SUBS_API_URL，返回标准化的订阅源列表。"""
    data = get_json(session, SUBS_API_URL, params=SUBS_EXTRA_PARAMS or None)

    # 兼容多种常见响应结构（WeRead 返回 "mps" 或 "mpList"）
    raw_list = (
        data.get("mps")
        or data.get("subscriptions")
        or data.get("mpList")
        or data.get("sources")
        or data.get("items")
        or data.get("list")
        or data.get("data")
        or (data if isinstance(data, list) else [])
    )

    if not raw_list:
        log.warning("⚠️  订阅列表为空。原始响应字段：%s", list(data.keys()) if isinstance(data, dict) else type(data))
        return []

    result = []
    for src in raw_list:
        sid = str(
            src.get("id") or src.get("mpId") or src.get("sourceId")
            or src.get("vid") or src.get("bookId") or ""
        )
        name = (
            src.get("name") or src.get("title") or src.get("mpName")
            or src.get("nickName") or sid
        )
        result.append({
            "id":    sid,
            "name":  name,
            "cover": src.get("cover") or src.get("avatar") or src.get("icon") or "",
            "intro": src.get("intro") or src.get("desc") or src.get("description") or "",
        })

    log.info("✅ 订阅公众号 %d 个", len(result))
    return result


# ═══════════════════════════════════════════════════════════
# B. 抓取单个公众号文章列表
# ═══════════════════════════════════════════════════════════

def _parse_pub_time(raw) -> datetime:
    """将各种格式的发布时间统一为 UTC datetime。"""
    if isinstance(raw, (int, float)) and raw > 1_000_000_000:
        return datetime.fromtimestamp(raw, tz=timezone.utc)
    if isinstance(raw, str) and raw:
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def fetch_articles_for_source(
    session: requests.Session,
    source: dict,
    max_count: int = ARTICLES_PER_SOURCE,
) -> list[dict]:
    """对一个订阅源调用 FEED_API_URL，返回文章列表。"""
    source_id = source["id"]
    url = FEED_API_URL.replace("{source_id}", source_id)

    articles: list[dict] = []
    offset = 0

    while len(articles) < max_count:
        try:
            data = get_json(session, url, params={FEED_PAGINATION_PARAM: offset})
        except RuntimeError as e:
            if "auth_error" in str(e):
                raise
            log.warning("  ⚠️  跳过 [%s]：%s", source["name"], e)
            break

        # 兼容多种常见响应结构（WeRead 返回 "articles" 或 "list"）
        items = (
            data.get("articles")
            or data.get("papers")
            or data.get("pubs")
            or data.get("article")
            or data.get("items")
            or data.get("list")
            or (data if isinstance(data, list) else [])
        )
        if not items:
            break

        for item in items:
            title = item.get("title") or item.get("name") or ""
            if not title:
                continue

            # URL：优先 mp.weixin.qq.com 链接
            url_val = (
                item.get("url") or item.get("link")
                or item.get("jumpUrl") or item.get("readUrl") or ""
            )

            pub_dt = _parse_pub_time(
                item.get("publishTime") or item.get("publish_time")
                or item.get("updateTime") or item.get("createTime") or 0
            )

            summary = (
                item.get("intro") or item.get("desc") or item.get("summary")
                or item.get("pureDescText") or ""
            )

            articles.append({
                "account_name": source["name"],
                "account_id":   source_id,
                "title":        title,
                "url":          url_val,
                "publish_time": pub_dt.isoformat(),
                "summary":      summary[:200],
                "_uid":         _uid(source_id, title, pub_dt.isoformat()),
            })

        # 若本批返回 < 10 条，说明已到末页
        if len(items) < 10:
            break
        offset += len(items)
        time.sleep(0.3)   # 避免请求过快

    log.info("  [%s] 抓到 %d 篇", source["name"], len(articles))
    return articles[:max_count]


def _uid(account_id: str, title: str, pub_time: str) -> str:
    """生成去重指纹（account_id + title + 日期）。"""
    raw = f"{account_id}|{title}|{pub_time[:10]}"
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


# ═══════════════════════════════════════════════════════════
# C. 状态管理（增量模式）
# ═══════════════════════════════════════════════════════════

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ═══════════════════════════════════════════════════════════
# D. 预留：推送到下游系统
# ═══════════════════════════════════════════════════════════

def send_to_downstream(articles: list[dict]) -> None:
    """
    预留接口：将今日文章推送到飞书 / Notion / 自定义 webhook 等。
    TODO: 取消注释并实现推送逻辑。

    payload 格式示例：
    {
        "date": "2026-02-27",
        "count": 12,
        "articles": [{"title":..., "url":..., "account_name":..., "publish_time":...}, ...]
    }
    """
    if not articles:
        return
    # import requests as _req
    # webhook_url = os.environ.get("WEBHOOK_URL", "")
    # if webhook_url:
    #     payload = {
    #         "date": articles[0]["publish_time"][:10],
    #         "count": len(articles),
    #         "articles": [
    #             {k: v for k, v in a.items() if not k.startswith("_")}
    #             for a in articles
    #         ],
    #     }
    #     _req.post(webhook_url, json=payload, timeout=10)


# ═══════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════

def run() -> None:
    # ── 读取 Cookie（来自 GitHub Secrets 注入的环境变量）──
    cookie = os.environ.get("WEREAD_COOKIE", "").strip()
    if not cookie:
        raise RuntimeError(
            "环境变量 WEREAD_COOKIE 未设置！\n"
            "GitHub → 仓库 Settings → Secrets and variables → Actions → New secret\n"
            "Name: WEREAD_COOKIE\n"
            "Value: 从 DevTools Network 请求的 Cookie 字段粘贴完整字符串"
        )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    session  = build_session(cookie)
    state    = load_state()
    cutoff   = datetime.now(timezone.utc) - timedelta(days=RECENT_DAYS)
    today_cn = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")

    # ── Step 1：订阅列表 ──
    log.info("━━━ Step 1: 获取订阅列表 ━━━")
    subscriptions = fetch_subscriptions(session)
    SUBS_FILE.write_text(
        json.dumps(subscriptions, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.info("→ %s (%d 个公众号)", SUBS_FILE, len(subscriptions))

    # ── Step 2：文章抓取 ──
    log.info("━━━ Step 2: 抓取文章 ━━━")
    all_articles: list[dict] = []
    seen_uids:    set[str]   = set()

    for source in subscriptions:
        articles = fetch_articles_for_source(session, source)

        for a in articles:
            uid = a["_uid"]
            if uid in seen_uids:
                continue
            try:
                pub_dt = datetime.fromisoformat(a["publish_time"])
            except ValueError:
                continue
            # 兼容 naive datetime
            if pub_dt.tzinfo is None:
                pub_dt = pub_dt.replace(tzinfo=timezone.utc)
            if pub_dt < cutoff:
                continue
            seen_uids.add(uid)
            all_articles.append(a)

        # 记录最新发布时间（增量用）
        if articles:
            latest = max(a["publish_time"] for a in articles)
            if not state.get(source["id"]) or latest > state[source["id"]]:
                state[source["id"]] = latest

        time.sleep(0.5)   # 公共礼貌间隔

    all_articles.sort(key=lambda x: x["publish_time"], reverse=True)

    ARTICLES_FILE.write_text(
        json.dumps(all_articles, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.info("→ %s (%d 篇近 %d 天文章)", ARTICLES_FILE, len(all_articles), RECENT_DAYS)

    # ── Step 3：生成 daily.md ──
    log.info("━━━ Step 3: 生成 daily.md ━━━")
    today_articles = [a for a in all_articles if a["publish_time"][:10] == today_cn]

    lines = [
        f"# 每日 AI 公众号速报 — {today_cn}",
        "",
        f"> 共 {len(today_articles)} 篇新文章（来自微信读书订阅）",
        "",
    ]
    by_account: dict[str, list] = {}
    for a in today_articles:
        by_account.setdefault(a["account_name"], []).append(a)

    for acc, arts in sorted(by_account.items()):
        lines.append(f"## {acc}\n")
        for a in arts:
            link    = a["url"] or "#"
            summary = f" — {a['summary']}" if a.get("summary") else ""
            lines.append(f"- [{a['title']}]({link}){summary}")
        lines.append("")

    DAILY_FILE.write_text("\n".join(lines), encoding="utf-8")
    log.info("→ %s (%d 篇今日文章)", DAILY_FILE, len(today_articles))

    # ── Step 4：保存增量状态 ──
    save_state(state)
    log.info("→ %s (state 已更新)", STATE_FILE)

    # ── Step 5：推送下游（预留） ──
    send_to_downstream(today_articles)

    log.info(
        "✅ 完成！共 %d 篇文章，今日新增 %d 篇",
        len(all_articles), len(today_articles),
    )


if __name__ == "__main__":
    run()
