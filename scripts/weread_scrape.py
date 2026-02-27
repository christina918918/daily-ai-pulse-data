#!/usr/bin/env python3
"""
weread_scrape.py — 通过 weread.111965.xyz 中转平台抓取微信公众号文章
使用 WeRead 移动端扫码登录获取的 vid + JWT Token 鉴权。

═══════════════════════════════════════════════════════════
首次使用：扫码登录获取 Token（一次性操作，有效期约 10 年）
═══════════════════════════════════════════════════════════

1. 在本项目配套的登录页面或 wewe-rss 界面扫码登录微信读书
2. 获取 vid（数字 ID）和 token（JWT 字符串）
3. 在 GitHub 仓库 → Settings → Secrets and variables → Actions
   添加两个 Secret：
   - WEREAD_VID:   登录返回的 vid（纯数字，如 328863337）
   - WEREAD_TOKEN: 登录返回的 token（JWT 字符串，eyJhbGci… 开头）

【安全提示】
- Token 只存 GitHub Secrets，绝不放代码或日志
- Token 有效期极长（约 10 年），基本不需要续期
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
# 中转平台配置
# ═══════════════════════════════════════════════════════════

RELAY_BASE_URL = "https://weread.111965.xyz"
RELAY_ARTICLES_URL = RELAY_BASE_URL + "/api/platform/mps/{mp_id}/articles"

# 订阅的公众号列表（MP_WXS_{数字id} 格式，来自微信读书书架数据）
MP_LIST = [
    {"id": "MP_WXS_3572959446", "name": "晚点LatePost"},
    {"id": "MP_WXS_2397003540", "name": "华尔街见闻"},
    {"id": "MP_WXS_3236757533", "name": "量子位"},
    {"id": "MP_WXS_1432156401", "name": "虎嗅APP"},
    {"id": "MP_WXS_3264997043", "name": "36氪"},
    {"id": "MP_WXS_3010319264", "name": "十字路口Crossing"},
    {"id": "MP_WXS_3220199623", "name": "42章经"},
    {"id": "MP_WXS_3220072307", "name": "投资实习所"},
    {"id": "MP_WXS_3073282833", "name": "机器之心"},
    {"id": "MP_WXS_3869640945", "name": "海外独角兽"},
    {"id": "MP_WXS_3895742803", "name": "Founder Park"},
    {"id": "MP_WXS_3075486737", "name": "白鲸出海"},
]

# ═══════════════════════════════════════════════════════════
# 抓取参数
# ═══════════════════════════════════════════════════════════

# 只保留近 N 天的文章
RECENT_DAYS = 7

# ═══════════════════════════════════════════════════════════
# 输出路径（相对于 repo 根目录的 out/）
# ═══════════════════════════════════════════════════════════

OUT_DIR       = Path(__file__).parent.parent / "out"
SUBS_FILE     = OUT_DIR / "subscriptions.json"
ARTICLES_FILE = OUT_DIR / "articles.json"
DAILY_FILE    = OUT_DIR / "daily.md"
STATE_FILE    = OUT_DIR / "state.json"

# 前端读取的统一文章库（与 RSS 文章合并）
DATA_ARTICLES_FILE = Path(__file__).parent.parent / "data" / "articles.json"

# ═══════════════════════════════════════════════════════════
# 日志（脱敏：永不输出 token）
# ═══════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# HTTP 工具（带重试）
# ═══════════════════════════════════════════════════════════

def build_headers(vid: str, token: str) -> dict:
    """构造中转平台所需的请求头。"""
    return {
        "xid": vid,
        "Authorization": f"Bearer {token}",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json",
    }


def get_json(url: str, headers: dict,
             retries: int = 2, backoff: float = 2.0) -> list | dict:
    """发 GET 请求，自动重试 5xx/timeout，返回解析后的 JSON。"""
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=20)

            if resp.status_code in (401, 403):
                log.error("❌ HTTP %d — 响应体: %s", resp.status_code, resp.text[:300])
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
# A. 抓取单个公众号文章列表
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


def fetch_articles_for_mp(mp: dict, headers: dict) -> list[dict]:
    """
    调用中转平台 API 获取单个公众号的文章列表。
    返回标准化的文章列表。
    """
    mp_id = mp["id"]
    mp_name = mp["name"]
    url = RELAY_ARTICLES_URL.format(mp_id=mp_id)

    try:
        data = get_json(url, headers)
    except RuntimeError as e:
        if "auth_error" in str(e):
            raise
        log.warning("  ⚠️  跳过 [%s]：%s", mp_name, e)
        return []

    if not isinstance(data, list):
        log.warning("  ⚠️  [%s] 响应格式异常：%s", mp_name, type(data))
        return []

    if not data:
        log.info("  [%s] 暂无文章（可能尚未同步）", mp_name)
        return []

    articles = []
    for item in data:
        title = item.get("title", "").strip()
        if not title:
            continue

        article_url = item.get("url", "")
        pub_dt = _parse_pub_time(item.get("publishTime", 0))
        pic_url = item.get("picUrl", "")

        articles.append({
            "account_name": mp_name,
            "account_id":   mp_id,
            "title":        title,
            "url":          article_url,
            "pic_url":      pic_url,
            "publish_time": pub_dt.isoformat(),
            "summary":      "",
            "_uid":         _uid(mp_id, title, pub_dt.isoformat()),
        })

    log.info("  [%s] 抓到 %d 篇", mp_name, len(articles))
    return articles


def _uid(account_id: str, title: str, pub_time: str) -> str:
    """生成去重指纹（account_id + title + 日期）。"""
    raw = f"{account_id}|{title}|{pub_time[:10]}"
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


# ═══════════════════════════════════════════════════════════
# B. 状态管理（增量模式）
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
# C. 预留：推送到下游系统
# ═══════════════════════════════════════════════════════════

def send_to_downstream(articles: list[dict]) -> None:
    """
    预留接口：将今日文章推送到飞书 / Notion / 自定义 webhook 等。
    TODO: 取消注释并实现推送逻辑。
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
# D. 合并到前端统一文章库 data/articles.json
# ═══════════════════════════════════════════════════════════

def _to_frontend_format(article: dict) -> dict:
    """把 WeRead 文章格式转换为前端 app.js 期望的格式。"""
    pub_dt = datetime.fromisoformat(article["publish_time"])
    if pub_dt.tzinfo is None:
        pub_dt = pub_dt.replace(tzinfo=timezone.utc)
    # 转北京时间取日期
    beijing_date = (pub_dt + timedelta(hours=8)).strftime("%Y-%m-%d")
    return {
        "id":         article["_uid"],
        "date":       beijing_date,
        "sourceType": "wechat",
        "sourceName": article["account_name"],
        "company":    "",
        "language":   "zh",
        "title":      article["title"],
        "summary":    article.get("summary", ""),
        "url":        article["url"],
    }


def merge_into_data_articles(weread_articles: list[dict]) -> None:
    """
    将 WeRead 文章（转换格式后）合并进 data/articles.json。
    以 URL 去重，已存在的条目不覆盖（保留 RSS 抓取的摘要等字段）。
    """
    # 读取现有 data/articles.json
    existing: list[dict] = []
    if DATA_ARTICLES_FILE.exists():
        try:
            existing = json.loads(DATA_ARTICLES_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    existing_urls = {a.get("url", "") for a in existing}

    new_entries = [
        _to_frontend_format(a)
        for a in weread_articles
        if a.get("url") and a["url"] not in existing_urls
    ]

    if not new_entries:
        log.info("→ data/articles.json：无新增 WeChat 条目")
        return

    merged = existing + new_entries
    merged.sort(key=lambda x: x.get("date", ""), reverse=True)

    DATA_ARTICLES_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_ARTICLES_FILE.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.info("→ data/articles.json：新增 %d 篇 WeChat 文章（共 %d 篇）",
             len(new_entries), len(merged))


# ═══════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════

def run() -> None:
    # ── 读取鉴权信息（来自 GitHub Secrets 注入的环境变量）──
    vid = os.environ.get("WEREAD_VID", "").strip()
    token = os.environ.get("WEREAD_TOKEN", "").strip()

    if not vid or not token:
        raise RuntimeError(
            "环境变量 WEREAD_VID 或 WEREAD_TOKEN 未设置！\n"
            "GitHub → 仓库 Settings → Secrets and variables → Actions\n"
            "  WEREAD_VID:   扫码登录返回的 vid（纯数字）\n"
            "  WEREAD_TOKEN: 扫码登录返回的 token（JWT 字符串）"
        )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    headers  = build_headers(vid, token)
    state    = load_state()
    cutoff   = datetime.now(timezone.utc) - timedelta(days=RECENT_DAYS)
    today_cn = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")

    # ── Step 1：保存订阅列表 ──
    log.info("━━━ Step 1: 保存订阅列表 ━━━")
    SUBS_FILE.write_text(
        json.dumps(MP_LIST, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.info("→ %s (%d 个公众号)", SUBS_FILE, len(MP_LIST))

    # ── Step 2：文章抓取 ──
    log.info("━━━ Step 2: 抓取文章 ━━━")
    all_articles: list[dict] = []
    seen_uids:    set[str]   = set()

    for mp in MP_LIST:
        articles = fetch_articles_for_mp(mp, headers)

        for a in articles:
            uid = a["_uid"]
            if uid in seen_uids:
                continue
            try:
                pub_dt = datetime.fromisoformat(a["publish_time"])
            except ValueError:
                continue
            if pub_dt.tzinfo is None:
                pub_dt = pub_dt.replace(tzinfo=timezone.utc)
            if pub_dt < cutoff:
                continue
            seen_uids.add(uid)
            all_articles.append(a)

        if articles:
            latest = max(a["publish_time"] for a in articles)
            if not state.get(mp["id"]) or latest > state[mp["id"]]:
                state[mp["id"]] = latest

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
            link = a["url"] or "#"
            lines.append(f"- [{a['title']}]({link})")
        lines.append("")

    DAILY_FILE.write_text("\n".join(lines), encoding="utf-8")
    log.info("→ %s (%d 篇今日文章)", DAILY_FILE, len(today_articles))

    # ── Step 4：保存增量状态 ──
    save_state(state)
    log.info("→ %s (state 已更新)", STATE_FILE)

    # ── Step 5：合并到前端统一文章库 ──
    log.info("━━━ Step 5: 合并到 data/articles.json ━━━")
    merge_into_data_articles(all_articles)

    # ── Step 6：推送下游（预留） ──
    send_to_downstream(today_articles)

    log.info(
        "✅ 完成！共 %d 篇文章，今日新增 %d 篇",
        len(all_articles), len(today_articles),
    )


if __name__ == "__main__":
    run()
