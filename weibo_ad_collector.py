# -*- coding: utf-8 -*-
"""微博广告帖采集器（基于 m.weibo.cn 内部 JSON 接口）

为什么不用 weiboSpider：
    weiboSpider 只能按 user_id 爬用户时间线，没有关键词搜索、不采集评论。
    本脚本走 m.weibo.cn 的搜索/评论接口，以满足「广告帖影响力研究」的采集范围定义。

输出（追加写入，不覆盖已有行）：
    posts.csv     帖子主表
    comments.csv  评论表
    skipped.log   跳过的条目及原因
    brands.txt    品牌词库（若不存在会自动创建模板，可自行增补）

用法示例：
    # 冒烟测试：每个关键词取 1 页，最多 3 条帖子，不抓评论页
    .\\weiboSpider\\venv\\Scripts\\python.exe weibo_ad_collector.py --limit 3 --delay 2

    # 正式采集：最多 100 条帖子，遵守 spec 的 1 请求/5 秒
    .\\weiboSpider\\venv\\Scripts\\python.exe weibo_ad_collector.py --limit 100 --delay 5
"""

import argparse
import csv
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "weiboSpider", "config.json")

POSTS_CSV = os.path.join(HERE, "posts.csv")
COMMENTS_CSV = os.path.join(HERE, "comments.csv")
SKIPPED_LOG = os.path.join(HERE, "skipped.log")
BRANDS_FILE = os.path.join(HERE, "brands.txt")
# 采样溯源（旁路文件）：posts.csv 表头必须严格符合 spec 不能加列，
# 但分层抽样需要知道每条帖子来自哪个关键词，所以单独记录。
SAMPLING_LOG = os.path.join(HERE, "sampling_log.csv")
SAMPLING_HEADERS = ["post_id", "keyword", "page", "collected_at"]

# ---- spec 第七节的关键词种子 ----
DEFAULT_KEYWORDS = ["#广告#", "#抽奖#", "#品牌日#", "种草", "推荐"]

SEARCH_URL = ("https://m.weibo.cn/api/container/getIndex"
              "?containerid=100103type%3D1%26q%3D{q}&page_type=searchall&page={page}")
COMMENTS_URL = "https://m.weibo.cn/comments/hotflow?id={mid}&mid={mid}&max_id_type=0"
LONGTEXT_URL = "https://m.weibo.cn/statuses/show?id={id}"

# ---- posts.csv 表头（ip_location 按实测改为 region_name + status_city）----
POST_HEADERS = [
    "platform", "post_id", "post_url", "created_at", "text", "hashtags",
    "mentions", "media_type", "media_urls", "is_ad_labeled", "ad_type",
    "brand_mentioned", "product_link", "author_id", "author_name",
    "author_followers", "author_verified", "author_verified_type",
    "region_name", "status_city", "reposts_count", "comments_count",
    "attitudes_count", "collected_at", "collection_method",
]

COMMENT_HEADERS = [
    "comment_id", "post_id", "comment_text", "comment_author_id",
    "comment_author_followers", "comment_likes", "comment_created_at",
    "comment_ip_location",
]

# ---- 广告判定规则（spec 第二节）----
AD_TAG_RE = re.compile(r"#\s*(广告|赞助|sponsored|ad)\s*#", re.I)
LOTTERY_KW = ["抽奖", "转发抽", "关注+转发", "关注并转发", "评论区抽", "转发微博抽",
              "中奖", "开奖", "转发本条"]
BRAND_CAMPAIGN_KW = ["品牌日", "联名", "新品发布", "首发", "上新", "限定", "campaign"]
KOL_KW = ["合作", "赞助", "品牌方", "PR", "广告推广", "商务合作", "恰饭"]
ORGANIC_KW = ["好用", "踩雷", "推荐", "避雷", "拔草", "种草", "回购", "测评", "实测"]

SHOP_HOSTS = ("taobao.com", "tmall.com", "tb.cn", "jd.com", "jd.hk", "u.jd.com",
              "3.cn", "douyin.com", "tb.cn", "s.click.taobao.com", "detail.tmall",
              "item.taobao", "m.tb.cn", "e.tb.cn", "pinduoduo.com", "yangkeduo.com")
URL_RE = re.compile(r"https?://[^\s，。；、）】\"'<>]+")
TAG_RE = re.compile(r"#([^#\s]{1,40})#")
MENTION_RE = re.compile(r"@([A-Za-z0-9\u4e00-\u9fa5_\-]{1,30})")
HTML_RE = re.compile(r"<[^>]+>")


# --------------------------------------------------------------------------
# 工具函数
# --------------------------------------------------------------------------
def load_cookie():
    with open(CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    return cfg.get("cookie", "")


def make_headers(cookie):
    return {
        "Cookie": cookie,
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/124.0.0.0 Safari/537.36"),
        "Referer": "https://m.weibo.cn/",
        "X-Requested-With": "XMLHttpRequest",
        "MWeibo-Pwa": "1",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }


def strip_html(s):
    """去掉 HTML 标签，保留内部文本（@昵称、话题等文字得以保留）。"""
    if not s:
        return ""
    return HTML_RE.sub("", s).replace("&nbsp;", " ").replace("&amp;", "&").strip()


def to_iso_utc(s):
    """把微博的 'Thu Sep 17 10:00:00 +0800 2026' 转成 ISO 8601 UTC。

    解析失败（如「10分钟前」这类相对时间）时原样返回，并计入统计。
    """
    if not s:
        return ""
    for fmt in ("%a %b %d %H:%M:%S %z %Y", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(s.strip(), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone(timedelta(hours=8)))
            return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            continue
    return s.strip()


def now_iso_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def to_int(v):
    """把微博的计数转成整数。

    m.weibo.cn 有时返回格式化字符串，如 '1.2万' / '1.2亿' / '1,234'，
    spec 要求这些列是 integer，所以统一还原为数值。
    """
    if v is None:
        return 0
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v).strip().replace(",", "").replace("+", "")
    if not s:
        return 0
    mul = 1
    if s.endswith("万"):
        mul, s = 10000, s[:-1]
    elif s.endswith("亿"):
        mul, s = 100000000, s[:-1]
    elif s.endswith("千"):
        mul, s = 1000, s[:-1]
    try:
        return int(float(s) * mul)
    except ValueError:
        return 0


def clean_region(v):
    """去掉 '发布于 上海' 里的前缀，只保留地名。"""
    if not v:
        return ""
    s = str(v).strip()
    for p in ("发布于", "发布于 ", "来自"):
        if s.startswith(p):
            s = s[len(p):].strip()
    return s


def load_brands():
    """读取品牌词库；不存在则创建模板。返回品牌名列表。"""
    if not os.path.isfile(BRANDS_FILE):
        with open(BRANDS_FILE, "w", encoding="utf-8") as f:
            f.write("# 品牌词库：每行一个品牌名，# 开头为注释行\n")
            f.write("# 脚本会用这些词在微博正文/话题里做精确子串匹配，填入 brand_mentioned\n")
            f.write("# 示例（请替换成你研究涉及的品牌）：\n")
            f.write("# 兰蔻\n# 华为\n# 元气森林\n")
        return []
    brands = []
    with open(BRANDS_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                brands.append(line)
    return brands


def log_skip(reason, detail):
    with open(SKIPPED_LOG, "a", encoding="utf-8") as f:
        f.write("{}\t{}\t{}\n".format(now_iso_utc(), reason, detail))


# --------------------------------------------------------------------------
# 字段加工
# --------------------------------------------------------------------------
def extract_hashtags(text):
    return [t.strip() for t in TAG_RE.findall(text or "") if t.strip()]


def extract_mentions(text):
    seen, out = set(), []
    for m in MENTION_RE.findall(text or ""):
        if m not in seen:
            seen.add(m)
            out.append(m)
    return out


def extract_shop_link(text):
    for u in URL_RE.findall(text or ""):
        low = u.lower()
        if any(h in low for h in SHOP_HOSTS):
            return u
    return ""


def media_of(mblog):
    """返回 (media_type, media_urls, page_url)。优先级 video > image > link > text。"""
    pics = mblog.get("pics") or []
    pic_urls = []
    for p in pics:
        if not isinstance(p, dict):
            continue
        u = (p.get("large") or {}).get("url") or p.get("url")
        if u:
            pic_urls.append(u)

    pi = mblog.get("page_info") or {}
    ptype = pi.get("type")

    if ptype == "video":
        mi = pi.get("media_info") or {}
        vurl = mi.get("stream_url_hd") or mi.get("stream_url") or ""
        urls = pic_urls + ([vurl] if vurl else [])
        return "video", urls, pi.get("page_url") or pi.get("url") or ""

    if pic_urls:
        return "image", pic_urls, pi.get("page_url") or ""

    purl = pi.get("url") or pi.get("page_url") or ""
    if purl:
        return "link", [], purl

    return "text", [], ""


def classify_ad(text, hashtags, author_verified, product_link, brands):
    """按 spec 第二节的 A/B/C/D 规则打标。返回 (is_ad_labeled, ad_type, brand_mentioned)。"""
    blob = (text or "") + " " + " ".join(hashtags or [])

    hit_brands = [b for b in brands if b and b in blob]
    brand_mentioned = "|".join(hit_brands)

    explicit = bool(AD_TAG_RE.search(blob))
    has_lottery = any(k in blob for k in LOTTERY_KW)
    has_campaign = any(k in blob for k in BRAND_CAMPAIGN_KW)
    has_kol = any(k in blob for k in KOL_KW)
    has_organic = any(k in blob for k in ORGANIC_KW)

    if explicit or product_link:
        return True, "explicit_ad", brand_mentioned
    if has_lottery or has_campaign:
        return True, "brand_campaign", brand_mentioned
    if author_verified and has_kol:
        return True, "kol_collab", brand_mentioned
    if brand_mentioned and has_organic:
        return False, "organic", brand_mentioned
    if brand_mentioned:
        return False, "unknown", brand_mentioned
    return False, "unknown", brand_mentioned


# --------------------------------------------------------------------------
# 采集
# --------------------------------------------------------------------------
class Collector(object):
    def __init__(self, cookie, delay, comment_pages, days):
        self.session = requests.Session()
        self.session.headers.update(make_headers(cookie))
        self.delay = delay
        self.comment_pages = comment_pages
        self.days = days
        self.brands = load_brands()
        self.stats = {
            "posts": 0, "comments": 0, "skipped": 0, "failed_requests": 0,
            "ad_type": {}, "missing": {}, "time_parse_failed": 0,
        }
        for h in POST_HEADERS:
            self.stats["missing"][h] = 0

    def _get_json(self, url, what, attempts=3):
        """带速率限制 + 退避重试的 GET，返回 dict 或 None。

        重试是必要的：本机走 127.0.0.1:7897 代理，间歇性抛 ProxyError/SSLError。
        原先一次失败就返回 None，会让 search() 拿到空列表并 break 掉整个关键词，
        在长跑（数百次请求）里等于随机丢掉整段样本。
        """
        last = ""
        for i in range(max(1, attempts)):
            # 重试时把间隔翻倍：delay, 2*delay, ...
            time.sleep(self.delay * (2 ** i) if i else self.delay)
            try:
                r = self.session.get(url, timeout=30)
            except Exception as e:
                last = "request_error {} {}".format(type(e).__name__, e)
                continue
            if r.status_code != 200:
                last = "http_{}".format(r.status_code)
                continue
            try:
                return r.json()
            except Exception:
                last = "not_json"
                continue

        log_skip(last.split(" ")[0], "{} ({} 次重试后仍失败) {}".format(what, attempts, last))
        self.stats["skipped"] += 1
        self.stats["failed_requests"] = self.stats.get("failed_requests", 0) + 1
        return None

    def search(self, keyword, page):
        url = SEARCH_URL.format(q=quote(keyword), page=page)
        data = self._get_json(url, "search:{}:p{}".format(keyword, page))
        if not data or not data.get("ok"):
            return []
        mblogs = []
        for card in (data.get("data") or {}).get("cards") or []:
            for grp in (card.get("card_group") or [card]):
                mb = grp.get("mblog")
                if mb:
                    mblogs.append(mb)
        return mblogs

    def full_text(self, mblog):
        if not mblog.get("isLongText"):
            return None
        data = self._get_json(LONGTEXT_URL.format(id=mblog.get("id")),
                              "longtext:{}".format(mblog.get("id")))
        if data and data.get("ok"):
            return data.get("data") or {}
        return None

    def build_post_row(self, mblog, longtext):
        text = strip_html((longtext or {}).get("longText")
                          or (longtext or {}).get("text")
                          or mblog.get("text"))
        hashtags = extract_hashtags(text)
        mentions = extract_mentions(text)
        mtype, murls, page_url = media_of(mblog)
        product_link = extract_shop_link(text) or extract_shop_link(page_url)

        user = mblog.get("user") or {}
        verified = bool(user.get("verified"))
        vtype = user.get("verified_type")
        vreason = user.get("verified_reason") or ""

        # 认证类型：cookie 版无法拿到结构化类型，这里用 verified_type + 文本兜底
        if not verified:
            verified_type_str = ""
        elif vtype in (0, None):
            verified_type_str = "个人认证"
        elif vtype in (2, 3, 4, 5, 6, 7):
            verified_type_str = "企业/机构认证"
        else:
            verified_type_str = "其他认证"
        if vreason:
            verified_type_str = (verified_type_str + "：" + vreason)[:120]

        is_ad, ad_type, brand_mentioned = classify_ad(
            text, hashtags, verified, product_link, self.brands)

        row = {
            "platform": "weibo",
            "post_id": str(mblog.get("id") or ""),
            "post_url": "https://m.weibo.cn/detail/{}".format(mblog.get("id") or ""),
            "created_at": to_iso_utc(mblog.get("created_at")),
            "text": text,
            "hashtags": "|".join(hashtags),
            "mentions": "|".join(mentions),
            "media_type": mtype,
            "media_urls": "|".join(murls),
            "is_ad_labeled": "true" if is_ad else "false",
            "ad_type": ad_type,
            "brand_mentioned": brand_mentioned,
            "product_link": product_link,
            "author_id": str(user.get("id") or ""),
            "author_name": user.get("screen_name") or "",
            "author_followers": to_int(user.get("followers_count")),
            "author_verified": "true" if verified else "false",
            "author_verified_type": verified_type_str,
            "region_name": clean_region(mblog.get("region_name")),
            "status_city": clean_region(mblog.get("status_city")),
            "reposts_count": to_int(mblog.get("reposts_count")),
            "comments_count": to_int(mblog.get("comments_count")),
            "attitudes_count": to_int(mblog.get("attitudes_count")),
            "collected_at": now_iso_utc(),
            "collection_method": "api",
        }
        if not row["created_at"]:
            self.stats["time_parse_failed"] += 1
        return row

    def fetch_comments(self, post_id):
        rows = []
        max_id = 0
        max_id_type = 0
        for _ in range(max(0, self.comment_pages)):
            url = COMMENTS_URL.format(mid=post_id)
            if max_id:
                url += "&max_id={}&max_id_type={}".format(max_id, max_id_type)
            data = self._get_json(url, "comments:{}".format(post_id))
            if not data or not data.get("ok"):
                break
            d = data.get("data") or {}
            items = d.get("data") or []
            if not items:
                break
            for c in items:
                cu = c.get("user") or {}
                rows.append({
                    "comment_id": str(c.get("id") or ""),
                    "post_id": post_id,
                    "comment_text": strip_html(c.get("text")),
                    "comment_author_id": str(cu.get("id") or ""),
                    "comment_author_followers": to_int(cu.get("followers_count")),
                    "comment_likes": to_int(c.get("like_count")),
                    "comment_created_at": to_iso_utc(c.get("created_at")),
                    "comment_ip_location": c.get("ip_location") or "",
                })
            max_id = d.get("max_id") or 0
            if not max_id:
                break
            max_id_type = d.get("max_id_type") or 0
        return rows


# --------------------------------------------------------------------------
# CSV 写入
# --------------------------------------------------------------------------
def append_rows(path, headers, rows):
    if not rows:
        return
    exists = os.path.isfile(path) and os.path.getsize(path) > 0
    # utf-8-sig：UTF-8 编码，带 BOM，保证 Excel 直接打开不乱码
    with open(path, "a", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        if not exists:
            w.writeheader()
        w.writerows(rows)


def do_reclassify():
    """用当前 brands.txt 重新推导 posts.csv 的分类字段（不联网）。

    分类只依赖 text / hashtags / author_verified / product_link 四个已存字段，
    所以补完品牌词库后重跑本模式即可，无需重新采集。
    """
    if not os.path.isfile(POSTS_CSV):
        print("[x] 找不到 {}".format(POSTS_CSV))
        return 1

    brands = load_brands()
    print("[i] 品牌词库: {} 个词".format(len(brands)))
    if not brands:
        print("[!] brands.txt 里没有有效品牌词（只有注释行）。")
        print("    请先编辑 {}，每行一个品牌名。".format(BRANDS_FILE))
        print("    否则 brand_mentioned 仍会全空、organic 分类仍为 0。")
        return 1

    with open(POSTS_CSV, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        print("[x] posts.csv 没有数据行")
        return 1

    before = {}
    changed = 0
    for r in rows:
        tags = [t for t in (r.get("hashtags") or "").split("|") if t]
        is_ad, ad_type, brand = classify_ad(
            r.get("text") or "", tags,
            (r.get("author_verified") or "").lower() == "true",
            r.get("product_link") or "", brands)
        before[r.get("ad_type")] = before.get(r.get("ad_type"), 0) + 1
        if r.get("ad_type") != ad_type or r.get("brand_mentioned") != brand:
            changed += 1
        r["is_ad_labeled"] = "true" if is_ad else "false"
        r["ad_type"] = ad_type
        r["brand_mentioned"] = brand

    with open(POSTS_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=POST_HEADERS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    after = {}
    for r in rows:
        after[r["ad_type"]] = after.get(r["ad_type"], 0) + 1

    n = len(rows)
    print()
    print("重算完成，共 {} 条，其中 {} 条的分类发生变化".format(n, changed))
    print("  {:<16} {:>6}  ->  {:>6}".format("ad_type", "重算前", "重算后"))
    for k in sorted(set(list(before) + list(after))):
        print("  {:<16} {:>6}  ->  {:>6}".format(
            k, before.get(k, 0), after.get(k, 0)))
    filled = sum(1 for r in rows if r.get("brand_mentioned"))
    print()
    print("  brand_mentioned 非空: {}/{} ({:.1f}%)".format(
        filled, n, filled * 100.0 / max(1, n)))
    print()
    print("[v] 已就地更新 {}".format(POSTS_CSV))
    return 0


def main():
    ap = argparse.ArgumentParser(description="微博广告帖采集器（m.weibo.cn）")
    ap.add_argument("--keywords", default=",".join(DEFAULT_KEYWORDS),
                    help="关键词，逗号分隔")
    ap.add_argument("--limit", type=int, default=100, help="最多采集多少条帖子")
    ap.add_argument("--delay", type=float, default=5.0,
                    help="每次请求间隔秒数（spec 要求 <=1 请求/5 秒）")
    ap.add_argument("--pages", type=int, default=20, help="每个关键词最多翻多少页")
    ap.add_argument("--comment-pages", type=int, default=1,
                    help="每条帖子最多抓多少页评论（每页约 20 条）")
    ap.add_argument("--per-keyword", type=int, default=0,
                    help="每个关键词的配额上限；0 表示不限制（由 --limit 统一控制）。"
                         "设为 --limit/关键词数 可避免单一关键词独占样本造成偏差")
    ap.add_argument("--days", type=int, default=90,
                    help="只保留最近 N 天的帖子；0 表示不过滤")
    ap.add_argument("--reclassify", action="store_true",
                    help="不联网重算：用当前 brands.txt 重新推导 posts.csv 里的 "
                         "is_ad_labeled / ad_type / brand_mentioned")
    args = ap.parse_args()

    if args.reclassify:
        return do_reclassify()

    cookie = load_cookie()
    if len(cookie) < 20:
        print("[x] weiboSpider/config.json 里没有有效 cookie")
        return 1

    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]
    c = Collector(cookie, args.delay, args.comment_pages, args.days)

    print("[i] 关键词: {}".format(", ".join(keywords)))
    print("[i] 上限 {} 条 | 请求间隔 {} 秒 | 每帖评论 {} 页 | 时间范围 {} 天"
          .format(args.limit, args.delay, args.comment_pages, args.days))
    print("[i] 品牌词库: {} 个词".format(len(c.brands)))
    print()

    seen = set()
    # 断点续采：把 posts.csv 里已有的 post_id 预先装入集合，
    # 这样重复运行不会产生重复行（spec 要求追加写入，但不应重复）
    if os.path.isfile(POSTS_CSV):
        try:
            with open(POSTS_CSV, encoding="utf-8-sig", newline="") as f:
                for row in csv.DictReader(f):
                    if row.get("post_id"):
                        seen.add(row["post_id"])
        except Exception as e:
            print("[!] 读取已有 posts.csv 失败，将不做去重：", e)
    if seen:
        print("[i] 已有 {} 条记录，本次将跳过重复的 post_id".format(len(seen)))

    cutoff = None
    if args.days > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)

    for kw in keywords:
        if c.stats["posts"] >= args.limit:
            break
        # 每个关键词的配额：避免第一个关键词把总配额吃光导致样本偏差
        kw_target = args.per_keyword if args.per_keyword > 0 else args.limit
        kw_count = 0
        print("--- 关键词: {}（本关键词上限 {} 条）---".format(kw, kw_target))
        for page in range(1, args.pages + 1):
            if c.stats["posts"] >= args.limit or kw_count >= kw_target:
                break
            mblogs = c.search(kw, page)
            if not mblogs:
                print("    第 {} 页无结果，换下一个关键词".format(page))
                break

            batch_posts, batch_comments = [], []
            for mb in mblogs:
                if c.stats["posts"] + len(batch_posts) >= args.limit:
                    break
                if kw_count + len(batch_posts) >= kw_target:
                    break
                pid = str(mb.get("id") or "")
                if not pid or pid in seen:
                    continue
                seen.add(pid)

                lt = c.full_text(mb)
                row = c.build_post_row(mb, lt)

                # 时间范围过滤（相对时间无法解析则保留）
                ca = row["created_at"]
                if cutoff and ca and re.match(r"^\d{4}-\d{2}-\d{2}T", ca):
                    try:
                        dt = datetime.strptime(ca, "%Y-%m-%dT%H:%M:%SZ").replace(
                            tzinfo=timezone.utc)
                        if dt < cutoff:
                            continue
                    except ValueError:
                        pass

                batch_posts.append(row)
                batch_comments.extend(c.fetch_comments(pid))

            if batch_posts:
                append_rows(POSTS_CSV, POST_HEADERS, batch_posts)
                append_rows(COMMENTS_CSV, COMMENT_HEADERS, batch_comments)
                append_rows(SAMPLING_LOG, SAMPLING_HEADERS, [
                    {"post_id": r["post_id"], "keyword": kw, "page": page,
                     "collected_at": r["collected_at"]} for r in batch_posts])
                c.stats["posts"] += len(batch_posts)
                c.stats["comments"] += len(batch_comments)
                kw_count += len(batch_posts)
                for r in batch_posts:
                    c.stats["ad_type"][r["ad_type"]] = \
                        c.stats["ad_type"].get(r["ad_type"], 0) + 1
                    for h in POST_HEADERS:
                        v = r.get(h)
                        # 只有 None / 空字符串算缺失；0 是合法数据（0 转发、0 点赞）
                        if v is None or v == "":
                            c.stats["missing"][h] += 1
                print("    第 {} 页: +{} 帖 / +{} 评论（累计 {} 帖）"
                      .format(page, len(batch_posts), len(batch_comments),
                              c.stats["posts"]))

    # ---- 统计报告 ----
    print()
    print("=" * 62)
    print("采集完成")
    print("  帖子数  :", c.stats["posts"])
    print("  评论数  :", c.stats["comments"])
    print("  跳过数  :", c.stats["skipped"],
          "(详见 {})".format(os.path.basename(SKIPPED_LOG))
          if c.stats["skipped"] else "")
    print("  其中请求彻底失败(已重试3次):", c.stats.get("failed_requests", 0))
    print("  时间解析失败:", c.stats["time_parse_failed"])
    print()
    print("  ad_type 分布:")
    total = max(1, c.stats["posts"])
    for k, v in sorted(c.stats["ad_type"].items(), key=lambda x: -x[1]):
        print("    {:<16} {:>4}  ({:.1f}%)".format(k, v, v * 100.0 / total))
    print()
    print("  字段缺失率:")
    for h in POST_HEADERS:
        miss = c.stats["missing"][h]
        print("    {:<24} {:>4}/{:<4} {:.1f}%".format(h, miss, c.stats["posts"],
                                                      miss * 100.0 / total))
    print()
    print("  输出文件:")
    for p in (POSTS_CSV, COMMENTS_CSV, SAMPLING_LOG, SKIPPED_LOG):
        if os.path.isfile(p):
            print("    {}  ({} 字节)".format(p, os.path.getsize(p)))
    print("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())
