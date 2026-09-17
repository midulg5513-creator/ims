# -*- coding: utf-8 -*-
"""可行性探测：检查 m.weibo.cn 的「关键词搜索」和「评论」接口能否满足采集 spec。

只输出字段结构信息（字段名、数量、是否存在），不输出帖子正文或评论内容。
用法：.\\weiboSpider\\venv\\Scripts\\python.exe probe_mweibo.py
"""

import json
import os
import sys
from urllib.parse import quote

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "weiboSpider", "config.json")

KEYWORD = "#抽奖#"
SEARCH_URL = (
    "https://m.weibo.cn/api/container/getIndex"
    "?containerid=100103type%3D1%26q%3D{}&page_type=searchall&page=1"
).format(quote(KEYWORD))


def load_cookie():
    with open(CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    return cfg.get("cookie", "")


def headers(cookie):
    return {
        "Cookie": cookie,
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Referer": "https://m.weibo.cn/",
        "X-Requested-With": "XMLHttpRequest",
        "MWeibo-Pwa": "1",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }


def probe_search(cookie):
    print("=" * 60)
    print("[1] 关键词搜索接口:", SEARCH_URL[:78], "...")
    try:
        r = requests.get(SEARCH_URL, headers=headers(cookie), timeout=25)
    except Exception as e:
        print("    请求失败:", type(e).__name__, e)
        return None

    print("    HTTP:", r.status_code, "| Content-Type:", r.headers.get("Content-Type"))
    try:
        data = r.json()
    except Exception:
        print("    返回非 JSON，前 200 字符:", r.text[:200])
        return None

    print("    ok 字段:", data.get("ok"))
    cards = (data.get("data") or {}).get("cards") or []
    print("    卡片数量:", len(cards))

    posts = []
    for c in cards:
        for grp in (c.get("card_group") or [c]):
            mblog = grp.get("mblog")
            if mblog:
                posts.append(mblog)
    print("    解析出微博条数:", len(posts))
    if not posts:
        print("    (无结果，可能关键词无匹配或被限制)")
        return None

    m = posts[0]
    print("    微博对象字段:", len(m.keys()), "个")
    info_keys = ["id", "mid", "created_at", "text", "textLength", "source",
                 "reposts_count", "comments_count", "attitudes_count",
                 "pics", "page_info", "ip_location", "region_name", "status_city"]
    for k in info_keys:
        print("      - {:<16} {}".format(k, "存在" if k in m else "缺失"))

    u = m.get("user") or {}
    print("    用户对象字段:", len(u.keys()), "个")
    for k in ["id", "screen_name", "followers_count", "verified",
              "verified_type", "verified_reason", "verified_type_ext",
              "status_total_counter"]:
        print("      - {:<20} {}".format(k, "存在" if k in u else "缺失"))
    return m


def probe_comments(cookie, mblog):
    mid = mblog.get("id") or mblog.get("mid")
    url = ("https://m.weibo.cn/comments/hotflow?id={0}&mid={0}&max_id_type=0"
           .format(mid))
    print()
    print("=" * 60)
    print("[2] 评论接口: id =", mid)
    try:
        r = requests.get(url, headers=headers(cookie), timeout=25)
    except Exception as e:
        print("    请求失败:", type(e).__name__, e)
        return
    print("    HTTP:", r.status_code)
    try:
        data = r.json()
    except Exception:
        print("    返回非 JSON，前 200 字符:", r.text[:200])
        return
    print("    ok 字段:", data.get("ok"))
    comments = (data.get("data") or {}).get("data") or []
    print("    评论条数:", len(comments))
    if not comments:
        print("    (无评论或该帖评论未开放)")
        return
    c = comments[0]
    print("    评论对象字段:", len(c.keys()), "个")
    for k in ["id", "text", "created_at", "like_count", "total_number",
              "ip_location", "source", "user"]:
        print("      - {:<16} {}".format(k, "存在" if k in c else "缺失"))
    cu = c.get("user") or {}
    print("    评论者字段:", ", ".join(sorted(cu.keys())[:12]), "...")
    print("      - followers_count:", "存在" if "followers_count" in cu else "缺失")


def main():
    cookie = load_cookie()
    if len(cookie) < 20:
        print("[x] config.json 里没有有效 cookie")
        return 1
    mblog = probe_search(cookie)
    if mblog:
        probe_comments(cookie, mblog)
    return 0


if __name__ == "__main__":
    sys.exit(main())
