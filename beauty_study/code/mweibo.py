# -*- coding: utf-8 -*-
"""m.weibo.cn 公开 JSON 接口客户端 + 微博对象解析器。

设计要点
- 默认不带登录态（需求 §2「微博公开页面」、§3「不绕过访问控制」）。
- 请求间隔 + 抖动、失败退避重试、每日请求上限（需求 §3）。
- 只读公开接口；不自建并发池，串行以保证限速可预测。
- 解析器为纯函数，便于单测。

实测接口（2026-09 复核）
- 用户资料    containerid=100505<uid>
- 主页时间线  containerid=107603<uid>&page=N  （或 &since_id=X）
- 帖子详情    /statuses/show?id=<mid>
- 评论        /comments/hotflow?id=<mid>&mid=<mid>
- 用户搜索    containerid=100103type%3D3%26q%3D<kw>
"""
from __future__ import annotations

import random
import re
import time
from datetime import datetime

import requests

from common import (
    RateLimiter,
    RequestBudget,
    age_hours,
    author_hash,
    count_mentions,
    extract_hashtags,
    extract_urls,
    iso,
    now_utc,
    parse_weibo_time,
    strip_html,
    to_int,
)

BASE = "https://m.weibo.cn"
UA_DEFAULT = ("Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
              "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1")

WEIBO_HOSTS = ("weibo.cn", "weibo.com", "sina.com.cn", "sina.cn")
SHOP_HOSTS = (
    "taobao.com", "tmall.com", "tb.cn", "jd.com", "jd.hk", "vip.com", "pinduoduo.com",
    "yangkeduo.com", "douyin.com", "xiaohongshu.com", "xhslink.com", "suning.com",
    "kaola.com", "shopee", "item.taobao", "detail.tmall", "3.cn", "douyin", "weibo",
)
LIVE_WORDS = ("直播", "直播间", "直播预告", "预约直播", "今晚八点", "锁定直播间")


class BudgetExhausted(RuntimeError):
    """当日请求额度用尽。"""


class RequestFailed(RuntimeError):
    """重试后仍失败。"""


def classify_host(url: str) -> str:
    u = (url or "").lower()
    for h in WEIBO_HOSTS:
        if h in u:
            return "weibo"
    if any(h in u for h in SHOP_HOSTS):
        return "shop"
    return "external"


class MWeibo:
    def __init__(self, cfg: dict, cookie: str | None = None, use_cookie: bool | None = None,
                 log_fn=None):
        self.cfg = cfg
        r = cfg["request"]
        self.timeout = float(r.get("timeout_seconds", 20))
        self.max_retries = int(r.get("max_retries", 3))
        self.backoff = float(r.get("backoff_base_seconds", 5.0))
        self.budget = RequestBudget(cfg)
        self.limiter = RateLimiter(cfg)

        if use_cookie is None:
            use_cookie = bool(r.get("use_cookie", False))
        self.use_cookie = use_cookie and bool(cookie)

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": r.get("user_agent") or UA_DEFAULT,
            "Referer": "https://m.weibo.cn/",
            "X-Requested-With": "XMLHttpRequest",
            "MWeibo-Pwa": "1",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
        })
        if self.use_cookie:
            self.session.headers["Cookie"] = cookie

        proxy = r.get("proxy")
        if proxy:
            self.session.proxies.update({"http": proxy, "https": proxy})

        self.stats = {"req": 0, "ok": 0, "fail": 0, "blocked": 0, "budget_skip": 0}
        self._log = log_fn or (lambda *_a, **_k: None)

    # ---------------------------------------------------------- 底层请求

    def _get(self, path: str, params: dict | None = None) -> dict | None:
        url = path if path.startswith("http") else BASE + path
        attempt = 0
        while True:
            if not self.budget.take(1):
                self.stats["budget_skip"] += 1
                raise BudgetExhausted(
                    f"当日请求上限已用尽（limit={self.budget.limit}），剩余 {self.budget.remaining()}。")
            self.limiter.wait()
            self.stats["req"] += 1
            attempt += 1
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout)
            except requests.exceptions.RequestException as e:
                self._log(f"  请求异常({attempt}/{self.max_retries}): {type(e).__name__}: {e}")
                if attempt >= self.max_retries:
                    self.stats["fail"] += 1
                    return None
                time.sleep(self.backoff * attempt)
                continue

            if resp.status_code == 200:
                try:
                    data = resp.json()
                except ValueError:
                    self._log(f"  非 JSON 响应({resp.status_code})，按失败处理")
                    if attempt >= self.max_retries:
                        self.stats["fail"] += 1
                        return None
                    time.sleep(self.backoff * attempt)
                    continue
                if isinstance(data, dict) and data.get("ok") in (1, None):
                    self.stats["ok"] += 1
                    return data
                # ok==0：可能是目标不存在/被删，也可能是限流
                self._log(f"  接口 ok={data.get('ok')} msg={data.get('msg')!r}")
                if attempt >= self.max_retries:
                    self.stats["fail"] += 1
                    return data
                time.sleep(self.backoff * attempt)
                continue

            if resp.status_code in (403, 418, 429):
                self.stats["blocked"] += 1
                wait = self.backoff * (2 ** attempt) + random.uniform(0, 3)
                self._log(f"  被限流 HTTP {resp.status_code}，等待 {wait:.0f}s（第 {attempt} 次）")
                if attempt >= self.max_retries:
                    self.stats["fail"] += 1
                    return None
                time.sleep(wait)
                continue

            if resp.status_code == 404:
                self.stats["fail"] += 1
                self._log("  HTTP 404：目标不存在")
                return None

            self._log(f"  HTTP {resp.status_code}，第 {attempt} 次")
            if attempt >= self.max_retries:
                self.stats["fail"] += 1
                return None
            time.sleep(self.backoff * attempt)

    # ---------------------------------------------------------- 业务接口

    def get_profile(self, uid: str | int) -> dict | None:
        return self._get("/api/container/getIndex", {"containerid": f"100505{uid}"})

    def get_timeline(self, uid: str | int, page: int = 1, since_id: str | None = None) -> dict | None:
        params = {"containerid": f"107603{uid}"}
        if since_id:
            params["since_id"] = since_id
        else:
            params["page"] = page
        return self._get("/api/container/getIndex", params)

    def get_status(self, mid: str | int) -> dict | None:
        return self._get("/statuses/show", {"id": str(mid)})

    def get_comments(self, mid: str | int, max_id: str | None = None) -> dict | None:
        params = {"id": str(mid), "mid": str(mid), "max_id_type": "0"}
        if max_id:
            params["max_id"] = str(max_id)
        return self._get("/comments/hotflow", params)

    def search_users(self, keyword: str, page: int = 1) -> dict | None:
        cid = f"100103type=3&q={keyword}"
        return self._get("/api/container/getIndex",
                         {"containerid": cid, "page_type": "searchall", "page": page})


# ---------------------------------------------------------------- 纯解析器

def iter_mblogs(cards: list[dict] | None):
    """从 cards 递归取出所有 mblog 对象。"""
    if not cards:
        return
    for c in cards:
        if not isinstance(c, dict):
            continue
        if isinstance(c.get("mblog"), dict):
            yield c["mblog"]
        if isinstance(c.get("card_group"), list):
            yield from iter_mblogs(c["card_group"])
        if isinstance(c.get("cards"), list):
            yield from iter_mblogs(c["cards"])


def parse_user(u: dict | None) -> dict:
    u = u or {}
    return {
        "uid": str(u.get("id", "")) if u.get("id") is not None else "",
        "screen_name": u.get("screen_name", ""),
        "followers_count": to_int(u.get("followers_count")),
        "verified": bool(u.get("verified")),
        "verified_type": u.get("verified_type"),
        "verified_reason": u.get("verified_reason", "") or "",
        "description": u.get("description", "") or "",
    }


def clean_text(s: str) -> str:
    """正文清洗（§4.2 text_clean）：去掉微博链接占位符与多余空白，保留话题与正文。"""
    if not s:
        return ""
    s = re.sub(r"\s*O?网页链接\s*", " ", s)
    s = re.sub(r"\s*O\s*$", " ", s)
    s = re.sub(r"\s*\u200b\s*", " ", s)
    s = re.sub(r"[ \t]{2,}", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _media_type(mblog: dict, image_count: int, has_video: bool) -> str:
    if has_video and image_count > 0:
        return "mixed"
    if has_video:
        return "video"
    if image_count > 0:
        return "image"
    return "text"


def parse_mblog(mblog: dict, brand: str, brand_category: str, account: dict,
                collection_time: datetime | None = None) -> dict:
    """把原始 mblog 归一化为需求 §4 的帖子记录。"""
    collection_time = collection_time or now_utc()

    raw_text = mblog.get("text", "") or ""
    text_raw = strip_html(raw_text)
    text_clean = clean_text(text_raw)

    hashtags = extract_hashtags(raw_text) or extract_hashtags(text_raw)
    mentions = count_mentions(text_raw)
    urls = extract_urls(text_raw)

    page_info = mblog.get("page_info") or {}
    url_ori = page_info.get("url_ori") or page_info.get("page_url") or ""
    if url_ori and classify_host(url_ori) != "weibo":
        urls = urls + [url_ori]
    ext_links = [u for u in urls if classify_host(u) != "weibo"]

    pics = mblog.get("pics") or []
    pic_num = mblog.get("pic_num")
    image_count = max(len(pics), to_int(pic_num) or 0)

    ptype = (page_info.get("type") or "").lower()
    has_video = bool(ptype == "video" or page_info.get("media_info") or mblog.get("video_src"))

    has_live = any(w in text_raw for w in LIVE_WORDS) or any(
        "直播" in t for t in hashtags)

    retweeted = mblog.get("retweeted_status")
    is_original = retweeted is None
    parent_post_id = ""
    if isinstance(retweeted, dict):
        parent_post_id = str(retweeted.get("id", ""))

    published = parse_weibo_time(mblog.get("created_at"))
    mid = str(mblog.get("id", ""))

    missing = []
    for field, val in (("like_count", mblog.get("attitudes_count")),
                       ("comment_count", mblog.get("comments_count")),
                       ("repost_count", mblog.get("reposts_count")),
                       ("published_at", published)):
        if val is None:
            missing.append(field)

    return {
        # §4.1 帖子和账号
        "post_id": mid,
        "mid": mid,
        "post_url": f"{BASE}/detail/{mid}" if mid else "",
        "brand": brand,
        "brand_category": brand_category,
        "account_type": "brand_official",
        "account_uid": account.get("uid", ""),
        "account_name": account.get("screen_name", ""),
        "is_original": is_original,
        "parent_post_id": parent_post_id,
        "collection_time": iso(collection_time),
        # §4.2 正文和媒体
        "text_raw": text_raw,
        "text_clean": text_clean,
        "hashtags_raw": "|".join(hashtags),
        "mentions_count": mentions,
        "external_link_count": len(ext_links),
        "image_count": image_count,
        "has_video": has_video,
        "has_live": has_live,
        "media_type": _media_type(mblog, image_count, has_video),
        # §4.3 时间和互动
        "published_at": iso(published),
        "like_count": to_int(mblog.get("attitudes_count")),
        "comment_count": to_int(mblog.get("comments_count")),
        "repost_count": to_int(mblog.get("reposts_count")),
        "follower_count": account.get("followers_count"),
        "post_age_hours": age_hours(published, collection_time) if published else None,
        "metric_observation_window": "current",
        # §4.4 抓取状态
        "fetch_status": "success" if not missing else "partial",
        "missing_fields": "|".join(missing),
        "is_duplicate": False,
        "exclusion_reason": "",
        # 元数据（内部）
        "author_hash": author_hash(account.get("uid", "")),
        "region_name": mblog.get("region_name", "") or "",
        "source": mblog.get("source", "") or "",
        "page_info_type": ptype,
        "page_url_ori": url_ori,
        "has_external_link": bool(ext_links),
        "has_shop_link": any(classify_host(u) == "shop" for u in ext_links),
    }


POST_FIELDS = [
    "post_id", "mid", "post_url", "brand", "brand_category", "account_type",
    "account_uid", "account_name", "is_original", "parent_post_id", "collection_time",
    "text_raw", "text_clean", "hashtags_raw", "mentions_count", "external_link_count",
    "image_count", "has_video", "has_live", "media_type",
    "published_at", "like_count", "comment_count", "repost_count", "follower_count",
    "post_age_hours", "metric_observation_window",
    "fetch_status", "missing_fields", "is_duplicate", "exclusion_reason",
    "author_hash", "region_name", "source", "page_info_type", "page_url_ori",
    "has_external_link", "has_shop_link",
]
